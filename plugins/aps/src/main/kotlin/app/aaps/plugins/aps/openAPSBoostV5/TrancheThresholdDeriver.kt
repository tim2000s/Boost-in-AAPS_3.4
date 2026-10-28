package app.aaps.plugins.aps.openAPSBoostV5

/**
 * Derives a person's confirm-tranche release threshold from their own confirm episodes.
 *
 * The release rule's coefficients are population derived and the same for everyone (see
 * [ConfirmTrancheController]). The threshold is personal: over the 27 August 2026 derivation the
 * per-participant best ran 0.30 to 0.65 with a median of 0.48, and it could not be predicted from a
 * participant's own share of large excursions (r = -0.32). It therefore has to be measured on each
 * person's episodes, which is what this does. The method reproduces
 * backtesting/scripts/2026-08-meal-size-readability/tranche_rule_derive.py, and the offline replay in
 * backtesting/scripts/2026-10-tranche-autoconfig/replay.py runs the same steps on the database; a
 * shared fixture checks that the two agree.
 *
 * An episode is the first CONFIRMED cycle after a cycle in any other state. Its features are read
 * from the glucose series ten minutes after the confirm: glucose at the confirm, glucose now, the
 * rise since, the largest rise since and the last reading's change. The outcome is the peak over
 * the following 180 minutes relative to glucose at the confirm. A peak of at least 75 mg/dL is a
 * large excursion and one under 30 mg/dL a small one; episodes in between carry no label. The
 * threshold chosen is the grid value that maximises Youden's J, the share of small episodes
 * withheld minus the share of large episodes withheld, a hold being withheld when p <= threshold
 * as in the controller. Ties go to the lowest grid value, as in the derivation.
 *
 * Pure: no Android, no I/O. The caller supplies the cycle states and the glucose series.
 */
object TrancheThresholdDeriver {

    /** History window, as in the 27 August derivation. */
    const val LOOKBACK_DAYS = 45L

    const val OFFSET_MS = 10L * 60_000
    const val FORWARD_MS = 180L * 60_000
    const val LARGE_MGDL = 75.0
    const val SMALL_MGDL = 30.0

    /** Minimum evidence for any suggestion: labelled episodes, and episodes in each class. */
    const val MIN_LABELLED = 15
    const val MIN_PER_CLASS = 5

    /**
     * The derivation only places the threshold on the grid, so it is bounded by the preference's own
     * range (DoubleKey.ApsBoostV5TrancheThreshold, 0.20 to 0.80) in steps of 0.05.
     */
    val GRID: List<Double> = (0..12).map { Math.round((0.20 + 0.05 * it) * 100.0) / 100.0 }

    enum class Label { SMALL, LARGE }

    data class Episode(
        val confirmMs: Long,
        val bgConfirm: Double,
        val bgNow: Double,
        val riseSince: Double,
        val maxRiseSince: Double,
        val slopeNow: Double,
        val peak: Double,
        val p: Double,
        val label: Label?
    )

    /** Why no threshold was derived. [NONE] when one was. */
    enum class Shortfall { NONE, TOO_FEW_LABELLED, CLASS_TOO_SMALL }

    data class Derivation(
        val episodes: List<Episode>,
        val nSmall: Int,
        val nLarge: Int,
        /** The chosen threshold, or null when the evidence fell short. */
        val threshold: Double?,
        /** Youden's J at [threshold], or null when none was chosen. */
        val youdenJ: Double?,
        val shortfall: Shortfall
    ) {
        val nLabelled: Int get() = nSmall + nLarge
    }

    /**
     * Confirm onsets from the cycle stream, oldest first: the time of every CONFIRMED cycle whose
     * predecessor was not CONFIRMED. The first cycle has no predecessor and never counts. The stream
     * must be the cycles themselves; collapsing them to five-minute buckets loses confirm cycles on a
     * one-minute loop.
     */
    fun confirmOnsets(cycles: List<Pair<Long, String?>>): List<Long> {
        val c = cycles.sortedBy { it.first }
        val out = ArrayList<Long>()
        for (i in 1 until c.size) {
            if (c[i].second == CONFIRMED && c[i - 1].second != CONFIRMED) out += c[i].first
        }
        return out
    }

    /** Builds the scored episodes. [glucose] is (timestamp ms, mg/dL) in any order. */
    fun episodes(confirmTimesMs: List<Long>, glucose: List<Pair<Long, Double>>): List<Episode> {
        val g = glucose.filter { it.second.isFinite() && it.second > 0.0 }.sortedBy { it.first }
        val ts = LongArray(g.size) { g[it].first }
        val bg = DoubleArray(g.size) { g[it].second }
        val out = ArrayList<Episode>()
        for (t0 in confirmTimesMs) {
            val j = bisectRight(ts, t0) - 1
            val m = bisectRight(ts, t0 + OFFSET_MS) - 1
            if (j < 1 || m <= j || m >= ts.size - 12) continue
            val b = bisectRight(ts, t0 + FORWARD_MS)
            if (b - j < 14) continue
            var segMax = Double.NEGATIVE_INFINITY
            for (k in j until b) if (bg[k] > segMax) segMax = bg[k]
            var winMax = Double.NEGATIVE_INFINITY
            for (k in j..m) if (bg[k] > winMax) winMax = bg[k]
            val bgConfirm = bg[j]
            val bgNow = bg[m]
            val rise = bgNow - bgConfirm
            val maxRise = winMax - bgConfirm
            val slope = bgNow - bg[m - 1]
            val peak = segMax - bgConfirm
            val p = ConfirmTrancheController.releaseProbability(bgConfirm, rise, maxRise, slope, bgNow)
            val label = when {
                peak >= LARGE_MGDL -> Label.LARGE
                peak < SMALL_MGDL  -> Label.SMALL
                else               -> null
            }
            out += Episode(t0, bgConfirm, bgNow, rise, maxRise, slope, peak, p, label)
        }
        return out
    }

    /** Youden's J at [t]: share of small episodes withheld minus share of large episodes withheld. */
    fun youden(episodes: List<Episode>, t: Double): Double {
        val small = episodes.filter { it.label == Label.SMALL }
        val large = episodes.filter { it.label == Label.LARGE }
        val ws = small.count { it.p <= t }.toDouble() / maxOf(small.size, 1)
        val wl = large.count { it.p <= t }.toDouble() / maxOf(large.size, 1)
        return ws - wl
    }

    fun derive(confirmTimesMs: List<Long>, glucose: List<Pair<Long, Double>>): Derivation =
        fromEpisodes(episodes(confirmTimesMs, glucose))

    fun fromEpisodes(eps: List<Episode>): Derivation {
        val nSmall = eps.count { it.label == Label.SMALL }
        val nLarge = eps.count { it.label == Label.LARGE }
        val shortfall = when {
            nSmall + nLarge < MIN_LABELLED                 -> Shortfall.TOO_FEW_LABELLED
            nSmall < MIN_PER_CLASS || nLarge < MIN_PER_CLASS -> Shortfall.CLASS_TOO_SMALL
            else                                           -> Shortfall.NONE
        }
        if (shortfall != Shortfall.NONE) return Derivation(eps, nSmall, nLarge, null, null, shortfall)
        var bestT = GRID.first()
        var bestJ = Double.NEGATIVE_INFINITY
        for (t in GRID) {
            val j = youden(eps, t)
            if (j > bestJ) { bestJ = j; bestT = t }        // strict: ties keep the lower value
        }
        return Derivation(eps, nSmall, nLarge, bestT, bestJ, Shortfall.NONE)
    }

    private const val CONFIRMED = "CONFIRMED"

    /** Index of the first element strictly greater than [x] (Python's bisect.bisect_right). */
    private fun bisectRight(a: LongArray, x: Long): Int {
        var lo = 0
        var hi = a.size
        while (lo < hi) {
            val mid = (lo + hi) ushr 1
            if (x < a[mid]) hi = mid else lo = mid + 1
        }
        return lo
    }
}
