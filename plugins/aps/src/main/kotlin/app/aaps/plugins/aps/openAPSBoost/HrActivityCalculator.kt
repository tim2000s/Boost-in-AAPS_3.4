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

            // Resistance: low steps but HR clearly elevated (zone 3–4)
            lowSteps && zone >= HrZone.ZONE_3_MODERATE && zone <= HrZone.ZONE_4_HARD ->
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
}
