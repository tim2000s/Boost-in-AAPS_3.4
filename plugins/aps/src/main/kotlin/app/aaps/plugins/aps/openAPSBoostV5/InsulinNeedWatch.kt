package app.aaps.plugins.aps.openAPSBoostV5

import kotlin.math.abs
import kotlin.math.sqrt

/**
 * The insulin-need watch (breadcrumb token ndw=). A daily check for a change in how much insulin the person is taking: the mean total daily dose of
 * the last [WINDOW_DAYS] complete days against the [BASELINE_DAYS] before them, flagged when it lies
 * more than [K_SD] standard deviations of single days from that month's mean (2026-10-20).
 *
 * It reports and never doses. Insulin sensitivity is not identifiable from these records, because
 * food the loop is not told about absorbs any change in how well insulin works, so the notification
 * describes the change in dose and glucose and leaves the cause to the person.
 *
 * Measured offline over 45 users and 562 user-months (backtesting/scripts/2026-10-insulin-need-alerts/
 * tdd_rule.py): 0.23 alerts a user-month; in the week after an upward alert insulin ran a median
 * 14.6% above the month (10.1 to 18.9) against 0.5% after random days, about a third of the alert's
 * own change. On the developer's October 2026 change it fired on 11 October, six days before any
 * glucose rule.
 *
 * Days are TddCalculator's: 24 hours from each local midnight, so they include profile basal (on a
 * clock-change day the hour lost or repeated is about 4% of a day, well inside the band). A day under
 * [GAP_FRACTION] of the median of the span is a gap in the record, not a dose. A change in the
 * profile's daily basal of more than [PROFILE_CHANGE] within the span would move the dose by itself,
 * whether it was a deliberate change or a new insulin concentration, so it is reported as that and
 * not as a change in need.
 */
object InsulinNeedWatch {

    const val WINDOW_DAYS = 3
    const val BASELINE_DAYS = 30
    const val MIN_BASELINE_DAYS = 20
    const val K_SD = 2.0
    const val GAP_FRACTION = 0.25
    const val PROFILE_CHANGE = 0.15
    const val COOLDOWN_DAYS = 14L

    /** One complete local day: its total daily dose and the profile's daily basal in force at its middle. */
    data class Day(val startMs: Long, val tddU: Double, val profileBasalU: Double?)

    enum class Status { FEW_DAYS, PROFILE_CHANGED, WITHIN, ABOVE, BELOW }

    data class Result(
        val status: Status,
        val recentMeanU: Double = Double.NaN,
        val baselineMeanU: Double = Double.NaN,
        val baselineSdU: Double = Double.NaN,
        val baselineDays: Int = 0,
        val windowStartMs: Long = 0L,
        val baselineStartMs: Long = 0L,
    ) {
        val z: Double get() = if (baselineSdU > 0) (recentMeanU - baselineMeanU) / baselineSdU else Double.NaN
        val percent: Double get() = if (baselineMeanU > 0) 100.0 * (recentMeanU - baselineMeanU) / baselineMeanU else Double.NaN

        /** Breadcrumb for the auto-config summary, e.g. ndw=ABOVE/z=2.3/p=+31/n=30. */
        fun token(): String = when (status) {
            Status.FEW_DAYS        -> "ndw=FEW_DAYS/n=$baselineDays"
            Status.PROFILE_CHANGED -> "ndw=PROFILE_CHANGED"
            else                   -> "ndw=${status.name}/z=${fmt1(z)}/p=${signed(percent)}/n=$baselineDays"
        }
    }

    /**
     * [days] are complete days, oldest first. Missing days may simply be absent. [lastDayStartMs] is
     * the start of yesterday, so that a missing yesterday leaves the window short rather than moving
     * it back a day. Returns the status of the [WINDOW_DAYS] days ending yesterday against the
     * [BASELINE_DAYS] before them.
     */
    fun evaluate(days: List<Day>, lastDayStartMs: Long = days.lastOrNull()?.startMs ?: 0L): Result {
        if (days.size < WINDOW_DAYS) return Result(Status.FEW_DAYS)
        val dayMs = 24L * 60 * 60 * 1000
        val lastStart = lastDayStartMs
        val windowStart = lastStart - (WINDOW_DAYS - 1) * dayMs
        val baselineStart = windowStart - BASELINE_DAYS * dayMs
        val span = days.filter { it.startMs >= baselineStart - dayMs / 2 }
        val median = percentile(span.map { it.tddU }.filter { it > 0 }, 50.0)
        val usable = span.filter { it.tddU > 0 && it.tddU >= GAP_FRACTION * median }
        // Window days are matched to their expected start within half a day, which absorbs DST.
        val window = usable.filter { it.startMs > windowStart - dayMs / 2 }
        val baseline = usable.filter { it.startMs <= windowStart - dayMs / 2 }
        if (window.size < WINDOW_DAYS || baseline.size < MIN_BASELINE_DAYS)
            return Result(Status.FEW_DAYS, baselineDays = baseline.size)

        val basals = span.mapNotNull { it.profileBasalU }.filter { it > 0 }
        if (basals.isNotEmpty()) {
            val ref = percentile(baseline.mapNotNull { it.profileBasalU }.filter { it > 0 }.ifEmpty { basals }, 50.0)
            if (span.any { (it.profileBasalU ?: ref) > 0 && abs((it.profileBasalU ?: ref) - ref) > PROFILE_CHANGE * ref })
                return Result(Status.PROFILE_CHANGED, baselineDays = baseline.size)
        }

        val recent = window.map { it.tddU }.average()
        val mean = baseline.map { it.tddU }.average()
        val sd = sqrt(baseline.sumOf { (it.tddU - mean) * (it.tddU - mean) } / (baseline.size - 1))
        val status = when {
            sd <= 0.0                  -> Status.WITHIN
            recent - mean > K_SD * sd  -> Status.ABOVE
            mean - recent > K_SD * sd  -> Status.BELOW
            else                       -> Status.WITHIN
        }
        return Result(status, recent, mean, sd, baseline.size, windowStart, baselineStart)
    }

    /**
     * The profile's own daily basal from an effective profile switch. Its stored blocks already carry
     * the switch's percentage, so a temporary switch (an exercise 70% or a sick-day 120%) is divided
     * back out: it is a short-term choice, not a new profile. A permanent percentage is kept, since it
     * changes the dose the person takes from then on.
     */
    fun profileDailyBasal(storedBasalSumU: Double, originalPercentage: Int, originalDurationMs: Long): Double =
        if (originalDurationMs > 0 && originalPercentage > 0) storedBasalSumU * 100.0 / originalPercentage else storedBasalSumU

    /** Whether to notify: the status is outside the band and the same direction has not been notified within [COOLDOWN_DAYS]. */
    fun shouldNotify(result: Result, lastAboveMs: Long, lastBelowMs: Long, now: Long): Boolean {
        val cooldownMs = COOLDOWN_DAYS * 24L * 60 * 60 * 1000
        return when (result.status) {
            Status.ABOVE -> lastAboveMs == 0L || now - lastAboveMs >= cooldownMs
            Status.BELOW -> lastBelowMs == 0L || now - lastBelowMs >= cooldownMs
            else         -> false
        }
    }

    private fun percentile(xs: List<Double>, p: Double): Double {
        if (xs.isEmpty()) return 0.0
        val s = xs.sorted()
        val r = p / 100.0 * (s.size - 1)
        val lo = r.toInt()
        val hi = minOf(lo + 1, s.size - 1)
        return s[lo] + (s[hi] - s[lo]) * (r - lo)
    }

    private fun fmt1(x: Double) = if (x.isNaN()) "NA" else "%.1f".format(java.util.Locale.ROOT, x)
    private fun signed(x: Double) = if (x.isNaN()) "NA" else "%+.0f".format(java.util.Locale.ROOT, x)
}
