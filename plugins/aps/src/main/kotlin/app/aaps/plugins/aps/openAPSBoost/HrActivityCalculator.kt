package app.aaps.plugins.aps.openAPSBoost

import app.aaps.core.data.model.HR
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag

/**
 * Classifies exercise type by combining Karvonen Heart Rate Reserve (HRR%) zones
 * with step count signals from StepService.
 *
 * ## Zone definitions (Karvonen HRR%)
 * HRR% = (currentHR - HRrest) / (HRmax - HRrest) * 100
 *
 *   Zone 1 — Very Light :  < 30% HRR  (recovery, rest)
 *   Zone 2 — Light       : 30–40% HRR  (easy aerobic)
 *   Zone 3 — Moderate    : 40–60% HRR  (aerobic conditioning)
 *   Zone 4 — Hard        : 60–80% HRR  (vigorous aerobic / strength)
 *   Zone 5 — Maximum     :  > 80% HRR  (near-maximal effort)
 *
 * ## Combined exercise states
 *
 *   VIGOROUS_AEROBIC  — High steps + Zone 3–5
 *     Effect on T1D: immediate insulin sensitivity increase, hypo risk.
 *     Response: reduce profile %, raise target BG.
 *
 *   MODERATE_AEROBIC  — Moderate steps + Zone 2–3
 *     Effect on T1D: moderate sensitivity increase.
 *     Response: reduce profile % (same as step-only ACTIVE).
 *
 *   LIGHT_AEROBIC     — Steps elevated + Zone 1–2
 *     Effect on T1D: mild sensitivity change.
 *     Response: same as step-only ACTIVE (mild profile reduction).
 *
 *   RESISTANCE        — Low/no steps + Zone 3–4
 *     Effect on T1D: acute BG rise short-term, delayed hypo risk.
 *     Response: raise target BG, do NOT reduce profile % yet.
 *
 *   STRESS            — Low steps + Zone 2–3, no exercise context
 *     Effect on T1D: cortisol/adrenaline raise BG → insulin resistance.
 *     Response: raise target BG (if stress detection enabled).
 *
 *   RESTING           — Normal HR (Zone 1) + low steps
 *   INACTIVE          — Very low steps + normal HR (confirms step-only INACTIVE)
 *
 * This class is intentionally stateless and functional — no side effects, no stored state.
 * Thread safety: all inputs are immutable; safe to call from any thread.
 */
object HrActivityCalculator {

    /** Karvonen HR zone classification (1–5, or 0 if HR data unavailable). */
    enum class HrZone(val label: String) {
        NONE("none"),
        ZONE_1_VERY_LIGHT("zone1"),
        ZONE_2_LIGHT("zone2"),
        ZONE_3_MODERATE("zone3"),
        ZONE_4_HARD("zone4"),
        ZONE_5_MAX("zone5"),
    }

    /**
     * Confidence in the classification.
     * HIGH   — both HR and step signals agree
     * MEDIUM — only one signal available or signals are consistent but not confirmatory
     * LOW    — signals contradict each other (e.g. high HR but zero steps for non-resistance context)
     */
    enum class Confidence { HIGH, MEDIUM, LOW }

    /** Combined exercise state from HR + step fusion. */
    enum class ExerciseState {
        VIGOROUS_AEROBIC,
        MODERATE_AEROBIC,
        LIGHT_AEROBIC,
        RESISTANCE,
        STRESS,
        RESTING,
        INACTIVE,
    }

    data class HrClassificationResult(
        val exerciseState: ExerciseState,
        val hrZone: HrZone,
        val averageHrBpm: Double?,      // null if no valid HR readings in window
        val hrrPercent: Double?,        // null if no valid HR readings
        val confidence: Confidence,
        val debugInfo: String
    )

    // Step thresholds for HR-fusion classification (deliberately modest; fine-tuning is
    // left to the existing ApsBoostActivitySteps prefs for the step-only path).
    private const val STEPS_15MIN_HIGH_THRESHOLD = 300     // ~20 steps/min = brisk walk
    private const val STEPS_15MIN_MODERATE_THRESHOLD = 100 // ~7 steps/min = slow walk
    private const val STEPS_15MIN_LOW_THRESHOLD = 30       // near-stationary

    /** Minimum in-window readings before a zero-variance run is judged "frozen" (below this we
     *  can't distinguish a stuck value from merely sparse data, so we don't suppress). */
    private const val FROZEN_MIN_READINGS = 4

    /**
     * True when the HR window holds enough readings that are ALL bit-identical — the signature of a
     * stuck sensor value (a wear HR listener repeating its last reading), NOT a heartbeat: a genuine
     * 1-minute-averaged HR always has some spread over a 15-min window. Used to reject a phantom
     * elevated HR that would otherwise mis-fire RESISTANCE/STRESS every cycle.
     */
    fun isHrWindowFrozen(readings: List<HR>, nowMillis: Long, windowMinutes: Int): Boolean {
        val windowMs = windowMinutes * 60_000L
        val cutoff = nowMillis - windowMs
        val inWindow = readings.filter { it.isValid && it.timestamp > cutoff && it.timestamp <= nowMillis }
        if (inWindow.size < FROZEN_MIN_READINGS) return false
        return inWindow.minOf { it.beatsPerMinute } == inWindow.maxOf { it.beatsPerMinute }
    }

    /**
     * Computes the average heart rate over [windowMinutes] from the provided list of
     * [HR] readings, returns null if no valid readings exist in the window.
     *
     * Each HR record's [HR.beatsPerMinute] is weighted by [HR.duration] (milliseconds)
     * to produce a duration-weighted average, matching how the watch sends 1-minute
     * averaged values.
     */
    fun averageHrInWindow(
        readings: List<HR>,
        nowMillis: Long,
        windowMinutes: Int,
    ): Double? {
        val windowMs = windowMinutes * 60_000L
        val cutoff = nowMillis - windowMs
        val inWindow = readings.filter { it.isValid && it.timestamp > cutoff && it.timestamp <= nowMillis }
        if (inWindow.isEmpty()) return null
        val totalDuration = inWindow.sumOf { it.duration.toDouble() }
        if (totalDuration <= 0.0) return null
        val weightedSum = inWindow.sumOf { it.beatsPerMinute * it.duration }
        return weightedSum / totalDuration
    }

    /**
     * Classifies a heart rate reading into a Karvonen zone.
     *
     * @param bpm       current (averaged) BPM
     * @param hrMax     user's maximum HR (default 180)
     * @param hrResting user's resting HR (default 60)
     */
    fun classifyZone(bpm: Double, hrMax: Int, hrResting: Int): HrZone {
        val reserve = (hrMax - hrResting).coerceAtLeast(1)
        val hrrPct = ((bpm - hrResting) / reserve) * 100.0
        return when {
            hrrPct < 30.0 -> HrZone.ZONE_1_VERY_LIGHT
            hrrPct < 40.0 -> HrZone.ZONE_2_LIGHT
            hrrPct < 60.0 -> HrZone.ZONE_3_MODERATE
            hrrPct < 80.0 -> HrZone.ZONE_4_HARD
            else           -> HrZone.ZONE_5_MAX
        }
    }

    /**
     * Produces a [HrClassificationResult] by fusing the HR zone with step counts.
     *
     * @param hrReadings         Raw HR records from PersistenceLayer (pre-fetched by caller)
     * @param nowMillis          Current system time in ms
     * @param hrWindowMinutes    Minutes of HR history to average
     * @param hrMax              Configured HRmax BPM
     * @param hrResting          Configured resting BPM
     * @param stepsLast15Min     Step count from StepService over the last 15 min
     * @param stressDetection    Whether to classify STRESS state (opt-in)
     * @param aapsLogger         Logger (nullable so unit tests don't need it)
     */
    fun classify(
        hrReadings: List<HR>,
        nowMillis: Long,
        hrWindowMinutes: Int,
        hrMax: Int,
        hrResting: Int,
        stepsLast15Min: Int,
        stressDetection: Boolean,
        aapsLogger: AAPSLogger? = null,
    ): HrClassificationResult {
        val debug = StringBuilder()

        val avgBpm = averageHrInWindow(hrReadings, nowMillis, hrWindowMinutes)
        if (avgBpm == null) {
            debug.append("HR: no valid readings in ${hrWindowMinutes}m window — falling back to step-only")
            return HrClassificationResult(
                exerciseState = ExerciseState.RESTING,
                hrZone = HrZone.NONE,
                averageHrBpm = null,
                hrrPercent = null,
                confidence = Confidence.LOW,
                debugInfo = debug.toString()
            )
        }

        // Frozen/stuck-value guard: a run of bit-identical readings is a sensor artifact (e.g. the
        // wear HR listener repeating its last value), not a heartbeat. Trusting a stuck ELEVATED
        // value mis-fires RESISTANCE/STRESS on every cycle (observed: a value pinned at 124 bpm all
        // night). Treat it as unavailable: zone NONE, which the plugin reads as "no usable HR". That
        // withholds every HR-driven activity and target modifier. It must not be read as rest: with HR
        // integration on, the INACTIVE raise requires positive HR evidence of rest and is withheld when
        // the classification is unavailable (see [inactivityRaiseBlockedByHr]).
        if (isHrWindowFrozen(hrReadings, nowMillis, hrWindowMinutes)) {
            debug.append("HR: frozen value ${String.format("%.1f", avgBpm)} bpm across ${hrWindowMinutes}m window (stuck sensor?) — treating as unavailable")
            aapsLogger?.debug(LTag.APS, "HrActivityCalculator: $debug")
            return HrClassificationResult(
                exerciseState = ExerciseState.RESTING,
                hrZone = HrZone.NONE,
                averageHrBpm = null,
                hrrPercent = null,
                confidence = Confidence.LOW,
                debugInfo = debug.toString()
            )
        }

        val reserve = (hrMax - hrResting).coerceAtLeast(1)
        val hrrPct = ((avgBpm - hrResting) / reserve) * 100.0
        val zone = classifyZone(avgBpm, hrMax, hrResting)

        debug.append("HR: avg=${String.format("%.1f", avgBpm)} bpm | HRR=${String.format("%.1f", hrrPct)}% | zone=${zone.label}")
        debug.append(" | steps15m=$stepsLast15Min")

        aapsLogger?.debug(LTag.APS, "HrActivityCalculator: $debug")

        val highSteps = stepsLast15Min >= STEPS_15MIN_HIGH_THRESHOLD
        val moderateSteps = stepsLast15Min >= STEPS_15MIN_MODERATE_THRESHOLD
        val lowSteps = stepsLast15Min < STEPS_15MIN_LOW_THRESHOLD

        val (state, confidence) = when {
            // Vigorous aerobic: high steps + zone 3 or above
            highSteps && zone >= HrZone.ZONE_3_MODERATE ->
                ExerciseState.VIGOROUS_AEROBIC to Confidence.HIGH

            // Moderate aerobic: moderate steps + zone 2 or above
            moderateSteps && zone >= HrZone.ZONE_2_LIGHT ->
                ExerciseState.MODERATE_AEROBIC to if (highSteps || zone >= HrZone.ZONE_3_MODERATE) Confidence.HIGH else Confidence.MEDIUM

            // Light aerobic: any steps above sedentary + zone 1–2
            !lowSteps && zone <= HrZone.ZONE_2_LIGHT ->
                ExerciseState.LIGHT_AEROBIC to Confidence.MEDIUM

            // Resistance / non-step exercise: HR clearly elevated (zone 3–4) with steps below the
            // MODERATE-aerobic threshold. 2026-07-21 FIX: was `lowSteps` (<30), which left a DEAD ZONE —
            // 30–100 steps + zone 3/4 matched no branch and fell through to RESTING, so a cyclist/rower
            // with incidental stepping mis-classified RESTING and the INACTIVE branch then ADDED insulin
            // (real incident: BG 85 falling 12/5min got profile 130% at zone3). Widen to !moderateSteps.
            !moderateSteps && zone >= HrZone.ZONE_3_MODERATE && zone <= HrZone.ZONE_4_HARD ->
                ExerciseState.RESISTANCE to Confidence.MEDIUM

            // Stress: low steps + zone 2–3 (elevated HR without movement)
            stressDetection && lowSteps && zone >= HrZone.ZONE_2_LIGHT && zone <= HrZone.ZONE_3_MODERATE ->
                ExerciseState.STRESS to Confidence.LOW

            // Inactive: low steps + zone 1
            lowSteps && zone == HrZone.ZONE_1_VERY_LIGHT ->
                ExerciseState.INACTIVE to Confidence.HIGH

            // Default resting
            else ->
                ExerciseState.RESTING to Confidence.MEDIUM
        }

        debug.append(" => $state ($confidence)")
        aapsLogger?.debug(LTag.APS, "HrActivityCalculator: classified as $state ($confidence)")

        return HrClassificationResult(
            exerciseState = state,
            hrZone = zone,
            averageHrBpm = avgBpm,
            hrrPercent = hrrPct,
            confidence = confidence,
            debugInfo = debug.toString()
        )
    }

    /**
     * 2026-07-21 SAFETY GUARD — the belt-and-braces companion to the RESISTANCE dead-zone fix above.
     *
     * The inactivity branch RAISES basal (adds insulin) on the assumption the user is sedentary. An
     * ELEVATED heart rate flatly contradicts that assumption: zone ≥ 3 (HRR ≥ 40%) is exercise-range,
     * whatever the step count says. A real incident added profile 130% at zone3 into a BG falling
     * 12 mg/dL per 5 min because the step count (64) landed in the classifier dead zone and the state
     * came back RESTING. This guard keys on the HR **zone directly**, so it holds even if the fused
     * exerciseState is wrong — the inactivity insulin must never fire while the heart says exercise.
     *
     * @return true when the inactivity profile-raise must be suppressed (raise target instead).
     */
    fun inactivitySuppressedByElevatedHr(result: HrClassificationResult?): Boolean =
        result != null && result.hrZone >= HrZone.ZONE_3_MODERATE

    /**
     * 2026-09-28 guard below [inactivitySuppressedByElevatedHr]: blocks the inactivity profile-raise
     * from zone 2 (HRR >= 30%) upward. Easy endurance work such as cycling sits in zone 2 with almost
     * no steps, so it passed the zone-3 guard, read as sedentary and got the insulin-adding raise for
     * as long as the rider stayed easy. At zone 2 only the raise is withheld: the target and the
     * activity state are left alone, because ordinary daily HR (stress, caffeine, digestion) also
     * reaches zone 2 and should not start exercise handling. Zone 3 and above keep the full guard.
     *
     * A null [result] also blocks (2026-10-08). The caller passes null when HR integration is on but
     * there is no usable HR: no reading in the window, or a stuck value. The raise adds insulin on the
     * claim that the user is sedentary, and a user who has switched HR integration on has chosen HR as
     * part of the evidence for that claim, so a missing heart rate is unknown rather than resting. This
     * is the same reasoning the step feed applies to a dark pedometer (F1, 2026-07-07). It fails closed
     * rather than open because the field record showed the open direction carrying almost all of the
     * raise for one participant (B: 3,997 of 4,146 raised cycles had no HR zone). Callers only consult
     * this with HR integration on; with it off the raise stays step-only, as it always was.
     */
    fun inactivityRaiseBlockedByHr(result: HrClassificationResult?): Boolean =
        result == null || result.hrZone == HrZone.NONE || result.hrZone >= HrZone.ZONE_2_LIGHT
}
