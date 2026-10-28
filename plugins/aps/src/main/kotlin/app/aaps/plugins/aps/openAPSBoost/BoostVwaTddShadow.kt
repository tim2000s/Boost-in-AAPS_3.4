package app.aaps.plugins.aps.openAPSBoost

import kotlin.math.max
import kotlin.math.min

/**
 * Silent shadow of a volume-weighted total-daily-dose blend.
 *
 * The shipped blend projects a day from the last eight hours by multiplying by three, which is
 * exact only if any eight hours holds a third of the day's insulin. Measured across nine
 * participants the share runs from about half the daily rate in the small hours to 1.4 times in
 * the afternoon, so the term reads the clock as much as the person: its downward trigger fires on
 * 60 to 97 per cent of small-hours cycles and 0 to 16 per cent of afternoon ones.
 *
 * This computes an alternative and logs it. Half the seven-day average, and half a projection of
 * today: the insulin delivered since the day's quiet anchor, read against the share of a day the
 * participant's own delivery curve says has passed by now.
 *
 * IT DOES NOT DOSE. The candidate was evaluated against four pre-registered targets and failed one
 * of them, detection lag across daily shifts, so it is not a replacement and is not offered as
 * one. It is here to accumulate the on-device curve and the paired estimates a within-person trial
 * would need, which is the only route by which it could become a dosing change.
 *
 * The curve is learned by observation rather than by querying history. Each cycle records the
 * cumulative share delivered by the current five-minute bucket; at the day boundary that day is
 * normalised and folded into the persisted curve, so the cost is constant per cycle and no
 * historical recomputation is needed. Until a participant has days of their own, the population
 * shape carries it, and it is shrunk out as their own days accumulate.
 *
 * The shape is a share of a day. It is turned into expected units by scaling against the
 * participant's own seven-day dose, which is recomputed at start-up and once a day thereafter
 * rather than every cycle, since a seven-day average does not move within a day.
 *
 * State persisted as JSON:
 *   curve      288 cumulative fractions, one per five minutes from the anchor
 *   expected   the same curve expressed in units, rebuilt daily from the seven-day dose
 *   curveDays  how many of the participant's own days the curve rests on
 *   warmedDays how many historical days have been read in, one per cycle
 *   anchorHour the participant's quiet hour, where the day is cut
 *   dayStartMs the anchor instant of the day in progress
 *   dayBuckets the cumulative delivery observed in the day so far, by half hour
 *   prevTotal  the previous day's completed total
 */
class BoostVwaTddShadow(
    private val loadState: () -> String,
    private val saveState: (String) -> Unit,
    private val logInfo: (String) -> Unit = {},
) {

    companion object {

        const val BUCKETS = 288                    // five-minute buckets in a day
        const val SHRINK_DAYS = 10.0               // days at which own and population weigh equally
        const val FRACTION_FLOOR = 0.10            // below this a projection divides by too little
        const val SANITY_LO = 0.5
        const val SANITY_HI = 2.0
        const val WEIGHT = 0.5                     // the projection's share of the blend
        const val MIN_DAY_UNITS = 1.0              // a day below this is not evidence of a shape
        const val WARM_SLICES = 48                 // half-hour slices used to read a past day
        const val WARM_DAYS = 7                    // days of history folded in, one per cycle

        /**
         * Population delivery curve, cumulative share of a day by five-minute bucket from the
         * quiet anchor, over 106 users of the wider record rather than this fork's cohort.
         *
         * A seed is for a phone with no history, so the quantity that decides it is how far an
         * unseen user is likely to sit from it. Against the 106, this curve is a mean absolute
         * 0.046 away in cumulative share and the ten-participant cohort curve is 0.062; the
         * wider one is closer for 83 per cent of them, at a signed-rank p of 4e-13.
         *
         * That is not because the small cohort is noisy. It is more homogeneous, not less: its
         * users differ from each other by 0.045 at the median bucket against 0.069 in the wider
         * record, and its weekday and weekend shapes differ by 0.007. The cohort curve is a
         * tight fit to nine people who may sit off-centre, and a median over a hundred cannot
         * carry any one person's habit into itself.
         *
         * Built from suggested delivery, which totals 1.10 times recorded delivery where both
         * are known, so the shape is used and the level is not. It is shrunk out as a
         * participant's own days accumulate.
         */
        val POPULATION_CURVE = doubleArrayOf(
        // 288 five-minute buckets, cumulative share of a day, from the quiet anchor
        0.00000, 0.00000, 0.00000, 0.00173, 0.00482, 0.00812, 0.01111, 0.01370, 0.01626, 0.01897, 0.02182, 0.02444,
        0.02682, 0.03121, 0.03445, 0.03794, 0.04069, 0.04370, 0.04722, 0.05150, 0.05441, 0.05681, 0.06051, 0.06309,
        0.06568, 0.06985, 0.07140, 0.07534, 0.07828, 0.08204, 0.08603, 0.09019, 0.09362, 0.09622, 0.10008, 0.10298,
        0.10732, 0.10967, 0.11375, 0.11775, 0.12263, 0.12615, 0.12822, 0.13117, 0.13382, 0.13737, 0.13749, 0.14142,
        0.14669, 0.15136, 0.15416, 0.15605, 0.16029, 0.16517, 0.16938, 0.16938, 0.17065, 0.17238, 0.17572, 0.17785,
        0.18062, 0.18687, 0.19005, 0.19442, 0.19701, 0.19864, 0.20247, 0.20423, 0.20861, 0.21230, 0.21662, 0.22075,
        0.22590, 0.22837, 0.23176, 0.23480, 0.23817, 0.24612, 0.24842, 0.24927, 0.25294, 0.25749, 0.25929, 0.26227,
        0.26602, 0.26718, 0.27033, 0.27402, 0.27727, 0.28017, 0.28060, 0.28427, 0.28742, 0.29051, 0.29337, 0.29648,
        0.30082, 0.30700, 0.31028, 0.31544, 0.31811, 0.32216, 0.32433, 0.32713, 0.32919, 0.33340, 0.33719, 0.33990,
        0.34093, 0.34377, 0.34527, 0.34728, 0.35326, 0.35326, 0.35946, 0.36193, 0.36542, 0.36746, 0.37262, 0.37629,
        0.37808, 0.38053, 0.38608, 0.38798, 0.39244, 0.39397, 0.39629, 0.39959, 0.40291, 0.40564, 0.41293, 0.41701,
        0.42074, 0.42645, 0.43254, 0.43633, 0.44100, 0.44181, 0.44437, 0.44826, 0.45220, 0.45667, 0.45971, 0.46519,
        0.46812, 0.47187, 0.47611, 0.48074, 0.48971, 0.49585, 0.49621, 0.49984, 0.50385, 0.50864, 0.50986, 0.51362,
        0.51639, 0.52572, 0.53002, 0.53434, 0.54000, 0.54435, 0.54742, 0.54972, 0.55186, 0.55792, 0.56126, 0.56380,
        0.56753, 0.57277, 0.57408, 0.57712, 0.58179, 0.58500, 0.58802, 0.59153, 0.59482, 0.59916, 0.60146, 0.60756,
        0.61126, 0.61185, 0.61588, 0.62014, 0.62490, 0.62732, 0.63116, 0.63440, 0.63684, 0.64212, 0.64282, 0.64949,
        0.65108, 0.65504, 0.66009, 0.66273, 0.66709, 0.66915, 0.67304, 0.67728, 0.68262, 0.68765, 0.69075, 0.69342,
        0.69757, 0.70155, 0.70451, 0.70998, 0.71353, 0.71916, 0.72264, 0.72653, 0.72848, 0.73314, 0.73779, 0.74333,
        0.74573, 0.74602, 0.74943, 0.75240, 0.75543, 0.75665, 0.76490, 0.77004, 0.77264, 0.77682, 0.77902, 0.78699,
        0.79023, 0.79597, 0.79965, 0.80374, 0.80623, 0.81112, 0.81559, 0.81937, 0.82176, 0.82614, 0.83011, 0.83332,
        0.83907, 0.84022, 0.84564, 0.85087, 0.85442, 0.85762, 0.86094, 0.86493, 0.86987, 0.87326, 0.87723, 0.88055,
        0.88513, 0.88947, 0.89376, 0.89785, 0.90065, 0.90443, 0.90785, 0.91189, 0.91640, 0.92063, 0.92441, 0.92778,
        0.93109, 0.93547, 0.94008, 0.94359, 0.94603, 0.94963, 0.95274, 0.95832, 0.96261, 0.96685, 0.97065, 0.97492,
        0.97750, 0.98048, 0.98272, 0.98596, 0.98908, 0.99142, 0.99422, 0.99828, 1.00000, 1.00000, 1.00000, 1.00000
        )

        const val DEFAULT_ANCHOR_HOUR = 3          // the cohort's quiet hour, until one is learned
        private const val DAY_MS = 24L * 60 * 60 * 1000
        private const val BUCKET_MS = DAY_MS / BUCKETS
    }

    data class Result(
        /** The blend this shadow proposes. Logged; never dosed. */
        val vwaBlend: Double,
        /** The projection of today's total on its own, before blending with the seven-day term. */
        val projection: Double,
        /** Share of the day the curve says has passed, so a reader can see why a cycle abstained. */
        val dayFraction: Double,
        /** Units delivered since the day's anchor. */
        val deliveredToday: Double,
        /** Units the curve expected by now, at the current calibration. */
        val expectedToday: Double,
        /** The seven-day dose the buckets are currently scaled against. */
        val calibratedTdd: Double,
        /** How many of the participant's own days the curve rests on. */
        val curveDays: Int,
        /** True where too little of the day has passed and the previous day carried the estimate. */
        val usedPreviousDay: Boolean,
        val debugLine: String,
    )

    private var curve: DoubleArray = POPULATION_CURVE.copyOf()
    private var curveDays: Int = 0
    private var anchorHour: Int = DEFAULT_ANCHOR_HOUR
    private var dayStartMs: Long = 0L
    private var dayBuckets: DoubleArray = DoubleArray(BUCKETS)
    private var prevTotal: Double = 0.0
    private var loaded = false

    /** The curve expressed in units rather than shares, rebuilt when the day rolls. */
    private var warmedDays: Int = 0             // historical days already folded in
    private var expectedUnits: DoubleArray = DoubleArray(BUCKETS)
    private var calibratedTdd: Double = 0.0
    private var calibratedMs: Long = 0L

    /**
     * @param nowMs             wall clock for this cycle
     * @param deliveredSinceDayStart  insulin delivered since the day's anchor, in units
     * @param tdd7D             the seven-day average the shipped blend already computes
     * @return null when the inputs cannot support an estimate, which the caller logs as an
     *         abstention rather than substituting a value
     */
    fun compute(nowMs: Long, deliveredSinceDayStart: Double?, tdd7D: Double?): Result? {
        if (deliveredSinceDayStart == null || tdd7D == null || tdd7D <= 0.0) return null
        if (deliveredSinceDayStart < 0.0) return null
        ensureLoaded()

        rollDayIfNeeded(nowMs)
        calibrateIfDue(nowMs, tdd7D)
        val elapsed = nowMs - dayStartMs
        val bucket = min(BUCKETS - 1, max(0, (elapsed / BUCKET_MS).toInt()))
        dayBuckets[bucket] = max(dayBuckets[bucket], deliveredSinceDayStart)

        val fraction = curve[bucket]
        val usedPrev: Boolean
        val projection: Double
        if (fraction >= FRACTION_FLOOR) {
            projection = deliveredSinceDayStart / fraction
            usedPrev = false
        } else if (prevTotal > 0.0) {
            // Too little of the day has passed to divide by. Reverting to the seven-day term
            // here would discard what yesterday established at every anchor, and a day that ran
            // heavy is the best evidence available about the one starting.
            projection = prevTotal
            usedPrev = true
        } else {
            projection = tdd7D
            usedPrev = true
        }

        val bounded = min(max(projection, SANITY_LO * tdd7D), SANITY_HI * tdd7D)
        val blend = (1.0 - WEIGHT) * tdd7D + WEIGHT * bounded
        persist()

        val line = "VwaTdd: day=${fmt(fraction)} deliv=${fmt(deliveredSinceDayStart)}" +
            " proj=${fmt(projection)}${if (usedPrev) "(prev)" else ""}" +
            " expected=${fmt(expectedUnits[bucket])}" +
            " bounded=${fmt(bounded)} 7D=${fmt(tdd7D)} → blend=${fmt(blend)}" +
            " curveDays=$curveDays anchor=${anchorHour}h"
        logInfo(line)
        return Result(blend, projection, fraction, deliveredSinceDayStart,
                      expectedUnits[bucket], calibratedTdd, curveDays, usedPrev, line)
    }

    /**
     * Turn the shape into expected units against the participant's own seven-day dose.
     *
     * Done at start-up and once a day thereafter rather than every cycle: a seven-day average
     * does not move within a day, and rebuilding 288 buckets on every pass would be work for
     * nothing. A change in the seven-day figure of more than a twentieth also triggers it, so a
     * participant whose requirement steps does not wait until the anchor to be measured against
     * the right scale.
     */
    private fun calibrateIfDue(nowMs: Long, tdd7D: Double) {
        val stale = calibratedMs == 0L || nowMs - calibratedMs >= DAY_MS
        val moved = calibratedTdd <= 0.0 ||
            kotlin.math.abs(tdd7D - calibratedTdd) / calibratedTdd > 0.05
        if (!stale && !moved) return
        for (i in 0 until BUCKETS) expectedUnits[i] = curve[i] * tdd7D
        calibratedTdd = tdd7D
        calibratedMs = nowMs
    }

    /** Units the curve expects to have been delivered by this bucket, at the current calibration. */
    fun expectedByBucket(bucket: Int): Double =
        expectedUnits[bucket.coerceIn(0, BUCKETS - 1)]

    private fun rollDayIfNeeded(nowMs: Long) {
        if (dayStartMs == 0L) {
            dayStartMs = anchorFor(nowMs)
            dayBuckets = DoubleArray(BUCKETS)
            return
        }
        if (nowMs - dayStartMs < DAY_MS) return
        foldDayIntoCurve()
        dayStartMs = anchorFor(nowMs)
        dayBuckets = DoubleArray(BUCKETS)
    }

    /** Normalise the completed day and shrink it into the curve by how many days it rests on. */
    private fun foldDayIntoCurve() {
        // The day's total is the largest cumulative figure seen, not the last bucket's. A cycle
        // need not land in the final half hour, and requiring one meant the curve never learned.
        var total = 0.0
        for (v in dayBuckets) total = max(total, v)
        if (total < MIN_DAY_UNITS) return
        val observed = DoubleArray(BUCKETS)
        var running = 0.0
        for (i in 0 until BUCKETS) {
            running = max(running, dayBuckets[i])          // the series is cumulative already
            observed[i] = (running / total).coerceIn(0.0, 1.0)
        }
        val n = curveDays + 1
        val w = n / (n + SHRINK_DAYS)
        var prev = 0.0
        for (i in 0 until BUCKETS) {
            val blended = w * observed[i] + (1.0 - w) * curve[i]
            prev = max(prev, blended)                       // a cumulative curve cannot fall
            curve[i] = prev.coerceIn(0.0, 1.0)
        }
        val last = curve[BUCKETS - 1]
        if (last > 0.0) for (i in 0 until BUCKETS) curve[i] = curve[i] / last
        curveDays = n
        prevTotal = total
    }

    private fun anchorFor(nowMs: Long): Long {
        val dayIndex = Math.floorDiv(nowMs - anchorHour * 60L * 60 * 1000, DAY_MS)
        return dayIndex * DAY_MS + anchorHour * 60L * 60 * 1000
    }

    private fun fmt(v: Double) = String.format("%.2f", v)

    private fun ensureLoaded() {
        if (loaded) return
        loaded = true
        try {
            val raw = loadState()
            if (raw.isBlank()) return
            val o = org.json.JSONObject(raw)
            o.optJSONArray("curve")?.let { arr ->
                if (arr.length() == BUCKETS) {
                    for (i in 0 until BUCKETS) curve[i] = arr.optDouble(i, curve[i])
                }
            }
            curveDays = o.optInt("curveDays", 0)
            warmedDays = o.optInt("warmedDays", 0)
            anchorHour = o.optInt("anchorHour", DEFAULT_ANCHOR_HOUR)
            dayStartMs = o.optLong("dayStartMs", 0L)
            prevTotal = o.optDouble("prevTotal", 0.0)
            o.optJSONArray("dayBuckets")?.let { arr ->
                if (arr.length() == BUCKETS) {
                    for (i in 0 until BUCKETS) dayBuckets[i] = arr.optDouble(i, 0.0)
                }
            }
        } catch (e: Exception) {
            logInfo("VwaTdd: state load failed (${e.message}); starting from the population curve")
        }
    }

    private fun persist() {
        try {
            val o = org.json.JSONObject()
                .put("curve", org.json.JSONArray(curve.toList()))
                .put("curveDays", curveDays)
                .put("warmedDays", warmedDays)
                .put("anchorHour", anchorHour)
                .put("dayStartMs", dayStartMs)
                .put("prevTotal", prevTotal)
                .put("dayBuckets", org.json.JSONArray(dayBuckets.toList()))
            saveState(o.toString())
        } catch (e: Exception) {
            logInfo("VwaTdd: state persist failed (${e.message})")
        }
    }

    /** The instant the current day was cut at, so a caller can ask how much of it has passed. */
    fun dayAnchorMs(nowMs: Long): Long {
        ensureLoaded()
        return anchorFor(nowMs)
    }

    /**
     * Fold one day of the phone's own history into the curve, oldest first.
     *
     * Learning the curve by observation alone takes as many days as the shrinkage needs, and
     * for the first of them the estimate is the population's rather than the participant's.
     * The history to avoid that is already on the phone: the dose calculator can total any
     * past window, so a past day can be read directly instead of waited for.
     *
     * One day per cycle rather than all of them at once. A day costs 48 half-hour totals, and
     * seven days read at start-up would be several hundred queries in a single loop pass, on
     * the path that decides a dose. Spread across cycles the same history is in hand within
     * the hour and no pass carries more than a day's worth.
     *
     * The half-hour slices are interpolated onto the five-minute grid. A seed does not need
     * five-minute detail; the live observation supplies that from the first day forward.
     *
     * @param totalBetween returns units delivered between two hour offsets from now, or null
     *        where the phone cannot answer, in which case warming stops rather than guessing.
     */
    fun warmFromHistory(nowMs: Long, totalBetween: (Long, Long) -> Double?) {
        ensureLoaded()
        if (warmedDays >= WARM_DAYS || curveDays >= WARM_DAYS) return

        val dayBack = warmedDays + 1L                       // 1 = yesterday
        val sliceH = 24.0 / WARM_SLICES
        val cumulative = DoubleArray(WARM_SLICES)
        var running = 0.0
        for (i in 0 until WARM_SLICES) {
            val endH = -(dayBack * 24L) + ((i + 1) * sliceH).toLong()
            val startH = -(dayBack * 24L) + (i * sliceH).toLong()
            val units = totalBetween(startH, endH) ?: return   // stop rather than invent
            running += max(0.0, units)
            cumulative[i] = running
        }
        warmedDays++
        val total = cumulative[WARM_SLICES - 1]
        if (total < MIN_DAY_UNITS) {
            persist()
            return
        }
        // onto the five-minute grid, then folded in as an observed day would be
        val perBucket = BUCKETS / WARM_SLICES
        var prev = 0.0
        for (i in 0 until WARM_SLICES) {
            val lo = if (i == 0) 0.0 else cumulative[i - 1] / total
            val hi = cumulative[i] / total
            for (k in 0 until perBucket) {
                val f = (k + 1).toDouble() / perBucket
                val v = lo + (hi - lo) * f
                dayBuckets[i * perBucket + k] = max(prev, v) * total
                prev = max(prev, v)
            }
        }
        foldDayIntoCurve()
        dayBuckets = DoubleArray(BUCKETS)
        persist()
        logInfo("VwaTdd: warmed day -$dayBack from history, curveDays=$curveDays")
    }

    /** Testing seam: the curve currently in force. */
    fun curveSnapshot(): DoubleArray = curve.copyOf()
}
