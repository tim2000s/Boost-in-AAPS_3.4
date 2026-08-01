package app.aaps.plugins.aps.openAPSBoostTwin

import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

/**
 * KAIROS — per-user onset-hazard model (2026-07-27). READ-ONLY substrate for the anticipation
 * shadow; it predicts, it never doses.
 *
 * WHY per-user + this form. Measured 2026-07-27 (`backtesting/scripts/2026-07-peruser-anticipation/`):
 * predicting exercise onset within 45 min from habit features (clock position + recency) is
 * decisively better PER-USER than cross-cohort (temporal AUC 0.78, every user 0.72–0.83, vs
 * cross-user 0.67) — exercise timing is idiosyncratic, so a pooled model cannot see a held-out
 * person's routine. Meal timing is more universal, so meals blend a cross-user PRIOR with per-user
 * adaptation as volume accrues. This class is deliberately an interpretable hazard TABLE, not a
 * black box: p(onset in the next [windowMin]) as a function of week-slot, recency-weighted over a
 * rolling window, circularly smoothed, blended with a prior. It is refit OFFLINE/periodically (the
 * orchestrator calls [fit] ~nightly) and applied at inference — the "robust statistic computed
 * periodically" carve-out, never learn-and-dose in a cycle (hard rule #2).
 *
 * The model works in LOCAL WEEK-MINUTES (minutes since Monday 00:00 local, [0, [WEEK_MIN])) so it
 * is pure and timezone-agnostic: the caller converts an epoch to a week-minute. That keeps the
 * clock structure (breakfast, the 5pm walk) and the weekend/weekday split in one integer.
 */
class AnticipationHabitModel(
    /** Slot width in minutes → [SLOTS] = [WEEK_MIN]/slotMinutes buckets across the week. */
    private val slotMinutes: Int = 30,
    /** Forecast horizon: p(onset within this many minutes). Matches the 45-min lead we validated. */
    val windowMin: Int = 45,
    /** Recency half-life (days): a bout 4 weeks ago counts half a bout yesterday. Tracks drift. */
    private val halfLifeDays: Double = 28.0,
    /** Circular smoothing radius in slots (events don't recur at the exact minute). */
    private val smoothingSlots: Int = 1,
    /** Whole-model source label flips to "peruser" once this many (recency-weighted) events accrue. */
    private val warmEvents: Double = 40.0,
    /** Per-SLOT confidence saturates at this recency-weighted onset mass in the slot; below it the
     *  slot blends toward the prior. Low, because a habit concentrates onsets into a few slots and a
     *  couple of confirmations already make a slot trustworthy. */
    private val slotWarm: Double = 2.0,
    /** Refractory window (min): right after an onset a second one within the horizon is unlikely. */
    private val refractoryMin: Double = 60.0,
) {

    companion object {
        const val WEEK_MIN = 7 * 24 * 60           // 10080

        /** Local week-minute (Mon 00:00 = 0) from a day-of-week (Mon=0..Sun=6) and minutes-past-midnight. */
        fun weekMinute(dowMonday0: Int, minutesPastMidnight: Int): Int =
            ((dowMonday0.coerceIn(0, 6) * 24 * 60 + minutesPastMidnight.coerceIn(0, 24 * 60 - 1)) % WEEK_MIN)

        /** Cross-user MEAL prior: gentle bumps at breakfast/lunch/dinner, every day. Semi-universal
         *  structure (2026-07-27: cross-user meal AUC 0.72). Values are p(meal in next window)≈. */
        fun defaultMealPrior(slotMinutes: Int = 30): DoubleArray {
            val slots = WEEK_MIN / slotMinutes
            val p = DoubleArray(slots) { 0.02 }
            val bumps = listOf(8 * 60 to 0.22, 13 * 60 to 0.20, 19 * 60 to 0.24) // local minute-of-day, peak
            for (d in 0 until 7) for ((center, peak) in bumps) {
                val c = (d * 24 * 60 + center) / slotMinutes
                for (o in -3..3) {
                    val s = ((c + o) % slots + slots) % slots
                    p[s] = max(p[s], peak * 0.5.pow((o * o) / 2.0))
                }
            }
            return p
        }

        /** Cross-user EXERCISE prior: essentially flat/low — exercise timing does NOT generalise
         *  across people (2026-07-27), so the prior is uninformative and per-user carries it. */
        fun defaultExercisePrior(slotMinutes: Int = 30): DoubleArray =
            DoubleArray(WEEK_MIN / slotMinutes) { 0.03 }
    }

    val slots = WEEK_MIN / slotMinutes

    /** A fitted hazard table plus provenance. [source]: "peruser" | "blend" | "prior". */
    data class Fitted(val hazard: DoubleArray, val nEffective: Double, val source: String)

    /**
     * Fit the hazard table from this user's own onset history.
     *
     * @param onsetWeekMinutes each onset's local week-minute (caller-converted from epoch).
     * @param onsetAgeDays     matching age of each onset in days (for recency weighting).
     * @param historyDays      span of usable history (for the per-slot exposure denominator).
     * @param prior            cross-user prior over slots (use [defaultMealPrior]/[defaultExercisePrior]).
     */
    fun fit(
        onsetWeekMinutes: IntArray,
        onsetAgeDays: DoubleArray,
        historyDays: Double,
        prior: DoubleArray,
    ): Fitted {
        require(onsetWeekMinutes.size == onsetAgeDays.size) { "onset arrays must align" }
        require(prior.size == slots) { "prior size ${prior.size} != slots $slots" }

        // Recency-weighted onset mass per slot.
        val num = DoubleArray(slots)
        var nEff = 0.0
        for (i in onsetWeekMinutes.indices) {
            val w = 0.5.pow(onsetAgeDays[i] / halfLifeDays)
            val slot = (onsetWeekMinutes[i] / slotMinutes).coerceIn(0, slots - 1)
            num[slot] += w
            nEff += w
        }
        // Per-slot exposure: each slot is visited once per week, so exposure is the recency-weighted
        // week count (same for every slot). hazard ≈ expected onsets per week-visit in this slot.
        val weeks = max(1, ceil(historyDays / 7.0).toInt())
        var exposure = 0.0
        for (w in 0 until weeks) exposure += 0.5.pow((w * 7.0) / halfLifeDays)
        exposure = max(exposure, 1e-6)

        val raw = DoubleArray(slots) { min(1.0, num[it] / exposure) }

        // Per-SLOT confidence blend BEFORE smoothing: a slot with its own onset mass is trusted;
        // an unvisited slot falls to the prior. Blending pre-smooth means the smoothing then lifts a
        // habit slot's NEIGHBOURS (catching a walk that drifts ±20 min) without flattening the peak.
        val blended = DoubleArray(slots) {
            val c = min(1.0, num[it] / slotWarm)
            c * raw[it] + (1.0 - c) * prior[it]
        }
        val hazard = circularSmooth(blended)
        for (i in hazard.indices) hazard[i] = hazard[i].coerceIn(0.0, 1.0)

        // Whole-model provenance label (per-slot confidence already handled the blending above).
        val w = min(1.0, nEff / warmEvents)
        val source = when {
            nEff < 1.0        -> "prior"
            w >= 0.999        -> "peruser"
            else              -> "blend"
        }
        return Fitted(hazard, nEff, source)
    }

    /**
     * p(onset within [windowMin]) at [nowWeekMinute], suppressed just after a recent onset
     * ([minsSinceLastOnset]) by the refractory factor. Returns null if the model is unfitted.
     */
    fun predict(fitted: Fitted?, nowWeekMinute: Int, minsSinceLastOnset: Double): Double? {
        if (fitted == null) return null
        val slot = (nowWeekMinute / slotMinutes).coerceIn(0, slots - 1)
        val base = fitted.hazard[slot]
        val refractory = if (minsSinceLastOnset >= refractoryMin) 1.0
        else (minsSinceLastOnset / refractoryMin).coerceIn(0.0, 1.0)
        return (base * refractory).coerceIn(0.0, 1.0)
    }

    private fun circularSmooth(x: DoubleArray): DoubleArray {
        if (smoothingSlots <= 0) return x
        val out = DoubleArray(x.size)
        for (i in x.indices) {
            var s = 0.0; var wsum = 0.0
            for (o in -smoothingSlots..smoothingSlots) {
                val j = ((i + o) % x.size + x.size) % x.size
                val wt = 0.5.pow(2.0 * o * o)             // 1, 0.25, 0.0039… (light — preserves peaks)
                s += x[j] * wt; wsum += wt
            }
            out[i] = s / wsum
        }
        return out
    }
}
