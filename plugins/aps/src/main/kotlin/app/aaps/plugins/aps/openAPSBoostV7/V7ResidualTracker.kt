package app.aaps.plugins.aps.openAPSBoostV7

import app.aaps.plugins.aps.openAPSBoostV5.MealHypothesis
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.round

/**
 * Residual-pool regime — the debiasing fix for foundation-report acceptance criterion (b).
 *
 * The offline substrate (backtesting/reports/2026-07_v7_foundation_REPORT.md §1) showed a
 * systematic +12..+38 mg/dL median residual at 60 min because unannounced-carb absorption lives
 * in the IOB-only residual, and the offline "quiet" regime (defined purely by V5 state) still
 * contained unannounced meal ONSETS (rising IDLE/OBSERVING cycles), so the bias survived regime
 * conditioning. The revised on-device pools therefore condition on V5 state + CGM DYNAMICS + hour:
 *
 *  - [MEAL]       — V5 meal-session states (CONFIRMED/COMMITTED/RECOVERING): absorption is
 *                   expected in the residual, by construction.
 *  - [NIGHT]      — non-meal cycles outside 07:00–22:59 local (matches the backtest's day split).
 *  - [QUIET_FLAT] — non-meal daytime cycles that are ALSO flat by CGM dynamics
 *                   (|delta| and |shortAvgDelta| ≤ [V7ResidualTracker.FLAT_DELTA_5M]).
 *
 * Non-meal daytime cycles that are NOT flat (the unannounced-onset pollution the report
 * identified) fit no pool and are EXCLUDED — both from pooling and from sizing (the shadow logs
 * pool="excluded" and abstains). Criterion (b) is met when the QUIET_FLAT 30-min median residual
 * (`boostV7_q50Drift`) reads ≈0 in the field.
 */
enum class V7Regime { QUIET_FLAT, MEAL, NIGHT }

/**
 * Classify the current cycle into a residual regime, or null when it fits no pool (excluded).
 * MEAL takes precedence (a meal session at night is still a meal); [mealState] == null (V5
 * decision unavailable this cycle) is treated as non-meal.
 */
fun classifyV7Regime(mealState: MealHypothesis?, delta: Double, shortAvgDelta: Double, hour: Int): V7Regime? = when {
    mealState == MealHypothesis.CONFIRMED || mealState == MealHypothesis.COMMITTED || mealState == MealHypothesis.RECOVERING -> V7Regime.MEAL
    hour < 7 || hour > 22                                                                                                    -> V7Regime.NIGHT
    abs(delta) <= V7ResidualTracker.FLAT_DELTA_5M && abs(shortAvgDelta) <= V7ResidualTracker.FLAT_DELTA_5M                   -> V7Regime.QUIET_FLAT
    else                                                                                                                     -> null
}

/**
 * V7ResidualTracker — the on-device substrate for the V7 shadow (Transplant-1 substrate, GO per
 * the 2026-07 foundation report; the SIZING rule built on it was NO-GO and is instrumented
 * read-only by [V7Shadow]).
 *
 * Each cycle it records the IOB-only projection at h ∈ {30, 60, 90} min. Since 2026-07-27 the
 * projection is oref's decaying-activity IOB prediction curve (rT.predBGs.IOB — the purple
 * IOB-only line), passed in by [V7Shadow]. The original substrate held the INSTANTANEOUS
 * activity constant over the horizon (projBG = bg + BGI5 × h/5), which overstates the fall in
 * proportion to IOB; field calibration 2026-07-27 showed the resulting pLow90 error is monotone
 * in IOB (high-IOB tertile predicted 36% vs 14% realised; low-IOB 9% vs 27%) and the QUIET_FLAT
 * 30-min median residual sat at +15 mg/dL instead of ≈0 — a bias the regime pools cannot absorb
 * because they are not IOB-conditioned. SERIAL_VERSION bumped 1→2: the residual definition
 * changed, so persisted v1 pools deserialize to a cold tracker and re-warm (~3-6 days). When a horizon matures (a later cycle lands inside the maturation
 * window), residual = observed − projected is added to the pool keyed by the REGIME AT
 * PROJECTION TIME ([V7Regime] — the criterion-(b) debiasing). Pools are windowed (~21 days,
 * size-capped) and expose empirical quantiles (numpy-style linear interpolation, matching the
 * offline scripts) plus counts. Cold pools (< [WARM_MIN_SAMPLES]) return null — consumers abstain.
 *
 * Persistence follows the V5StateStore idiom: a single JSON blob in a StringKey, cached
 * in memory by the orchestrator ([V7Shadow]) so rapid multi-invokes never read stale state;
 * the pref write is only restart recovery. Corrupt state deserializes to a fresh tracker
 * (cold start — fails safe: the sizer abstains until pools re-warm).
 *
 * Multi-invoke handling: AAPS invokes the engine up to every 1–3 min during SMB delivery. A
 * projection recorded in the same 5-min bucket as the previous one REPLACES it (the final
 * invoke of the cycle wins — the same dedup rule as the offline loader), and maturation fills
 * each horizon at most once.
 */
class V7ResidualTracker {

    companion object {

        /** Rolling window: samples older than this are evicted. ~21 days per the shadow spec. */
        const val WINDOW_MS: Long = 21L * 86_400_000L

        /** Hard per-(regime,horizon) size cap — bounds the persisted blob; quantile precision
         *  is unaffected (the offline regime quantiles used n ≥ 150). Oldest evicted first. */
        const val MAX_SAMPLES_PER_POOL = 2000

        /** Below this per-(regime,horizon) count the pool is "warming" and consumers abstain.
         *  2026-07-07: lowered 150 → 60 for the SHADOW-EVAL warm-up. At the observed live fill
         *  rate (~24 meal / ~12 quiet-flat matured residuals per day) 150 was ~1–2 weeks to first
         *  signal; 60 gives a usable regime-quantile estimate in ~3–6 days. This is a SHADOW-ONLY
         *  read (no dosing) — 60 is ample for an evaluation quantile; a production dosing gate would
         *  restore 150 (the offline 03_distributional_sizing fit minimum). */
        const val WARM_MIN_SAMPLES = 60

        /** Flat-CGM threshold (mg/dL per 5 min) for the QUIET_FLAT regime, applied to both delta
         *  and shortAvgDelta — "quiet defined by CGM dynamics rather than V6 state" (report §VERDICT b). */
        const val FLAT_DELTA_5M = 3.0

        /** Projection horizons, minutes. Sizer uses 60; q50Drift uses 30; pLow uses 90. */
        val HORIZONS_MIN = intArrayOf(30, 60, 90)

        /** Maturation window around ts+h: accept an observation up to 90 s early (nearest 5-min
         *  grid neighbour) or 300 s late (the offline forward_bg tolerance). */
        const val MATURE_EARLY_TOL_MS = 90_000L
        const val MATURE_LATE_TOL_MS = 300_000L

        /** 5-min cycle bucket for multi-invoke dedup — same bucketing as the offline loader. */
        const val CYCLE_BUCKET_MS = 300_000L

        /** The five exposed percentiles (5/25/50/75/95) — the substrate's validated surface;
         *  the ≤5% left tail is NOT fittable (report §1 tail honesty). */
        val POOL_PERCENTILES = doubleArrayOf(5.0, 25.0, 50.0, 75.0, 95.0)

        private const val SERIAL_VERSION = 2

        /** Deserialize a persisted blob; blank/corrupt → fresh tracker (cold start, fails safe). */
        fun deserialize(raw: String?): V7ResidualTracker {
            val tracker = V7ResidualTracker()
            if (raw.isNullOrBlank()) return tracker
            try {
                val json = JSONObject(raw)
                if (json.optInt("v") != SERIAL_VERSION) return V7ResidualTracker()
                val pend = json.optJSONArray("pend") ?: JSONArray()
                for (i in 0 until pend.length()) {
                    val p = pend.getJSONArray(i)
                    val regime = V7Regime.valueOf(p.getString(1))
                    val projections = DoubleArray(HORIZONS_MIN.size) { p.getDouble(2 + it) }
                    val mask = p.getInt(2 + HORIZONS_MIN.size)
                    val matured = BooleanArray(HORIZONS_MIN.size) { (mask shr it) and 1 == 1 }
                    tracker.pending.addLast(Pending(p.getLong(0) * 1000L, regime, projections, matured))
                }
                val pools = json.optJSONObject("pools") ?: JSONObject()
                for (key in pools.keys()) {
                    val flat = pools.getJSONArray(key)
                    val deque = ArrayDeque<Sample>(flat.length() / 2)
                    var i = 0
                    while (i + 1 < flat.length()) {
                        deque.addLast(Sample(flat.getLong(i) * 1000L, flat.getDouble(i + 1)))
                        i += 2
                    }
                    tracker.pools[key] = deque
                }
                return tracker
            } catch (_: Exception) {
                // Corrupt persisted state — cold start (sizer abstains until pools re-warm).
                return V7ResidualTracker()
            }
        }
    }

    /** An in-flight projection awaiting maturation at each horizon. */
    private class Pending(
        val tsMs: Long,
        val regime: V7Regime,
        /** Projected BG at each of [HORIZONS_MIN], mg/dL. */
        val projections: DoubleArray,
        /** Per-horizon "done" flag — set on residual capture OR on a missed window (data gap). */
        val matured: BooleanArray,
    )

    private class Sample(val tsMs: Long, val residual: Double)

    /** Oldest-first in-flight projections (≤ ~19 live at any time: 90 min / 5 min + tolerance). */
    private val pending = ArrayDeque<Pending>()

    /** (regime,horizon) → oldest-first residual samples. */
    private val pools = LinkedHashMap<String, ArrayDeque<Sample>>()

    private fun poolKey(regime: V7Regime, horizonMin: Int) = "${regime.name}:$horizonMin"

    /**
     * One engine invoke: mature any due horizons against the observed [bg], evict expired
     * samples, then record this cycle's projection (only when the cycle classifies into a
     * regime AND finite [projections] aligned with [HORIZONS_MIN] are available — otherwise the
     * cycle contributes observations to maturation but no new projection).
     */
    fun onCycle(nowMs: Long, bg: Double, projections: DoubleArray?, regime: V7Regime?) {
        mature(nowMs, bg)
        evict(nowMs)
        if (regime != null && projections != null && projections.size == HORIZONS_MIN.size &&
            projections.all { it.isFinite() } && bg > 0.0
        ) record(nowMs, projections, regime)
    }

    private fun mature(nowMs: Long, bg: Double) {
        if (bg <= 0.0) return
        val it = pending.iterator()
        while (it.hasNext()) {
            val p = it.next()
            for (h in HORIZONS_MIN.indices) {
                if (p.matured[h]) continue
                val dueMs = p.tsMs + HORIZONS_MIN[h] * 60_000L
                when {
                    nowMs >= dueMs - MATURE_EARLY_TOL_MS && nowMs <= dueMs + MATURE_LATE_TOL_MS -> {
                        val pool = pools.getOrPut(poolKey(p.regime, HORIZONS_MIN[h])) { ArrayDeque() }
                        pool.addLast(Sample(nowMs, round((bg - p.projections[h]) * 10.0) / 10.0))
                        p.matured[h] = true
                    }

                    nowMs > dueMs + MATURE_LATE_TOL_MS                                          -> p.matured[h] = true // missed (CGM/loop gap) — no sample
                }
            }
            if (p.matured.all { m -> m }) it.remove()
        }
    }

    private fun evict(nowMs: Long) {
        val cutoff = nowMs - WINDOW_MS
        for (pool in pools.values) {
            while (pool.isNotEmpty() && (pool.first().tsMs < cutoff || pool.size > MAX_SAMPLES_PER_POOL)) pool.removeFirst()
        }
    }

    private fun record(nowMs: Long, projections: DoubleArray, regime: V7Regime) {
        // Multi-invoke dedup: a projection in the same 5-min bucket replaces the previous one
        // (final invoke of the cycle wins — offline loader's DISTINCT ON ... ORDER BY ts DESC).
        val last = pending.lastOrNull()
        if (last != null && last.tsMs / CYCLE_BUCKET_MS == nowMs / CYCLE_BUCKET_MS) pending.removeLast()
        pending.addLast(Pending(nowMs, regime, projections.copyOf(), BooleanArray(HORIZONS_MIN.size)))
    }

    /** Sample count for a (regime, horizon) pool. */
    fun count(regime: V7Regime, horizonMin: Int): Int = pools[poolKey(regime, horizonMin)]?.size ?: 0

    /**
     * Empirical residual quantiles (mg/dL) for a (regime, horizon) pool, or null while the pool
     * is cold (< [WARM_MIN_SAMPLES] — the cold-start abstention). [percentiles] are 0–100;
     * interpolation is numpy-default linear, matching the offline scripts.
     */
    fun quantiles(regime: V7Regime, horizonMin: Int, percentiles: DoubleArray = POOL_PERCENTILES): DoubleArray? {
        val pool = pools[poolKey(regime, horizonMin)] ?: return null
        if (pool.size < WARM_MIN_SAMPLES) return null
        val sorted = pool.map { it.residual }.sorted()
        return DoubleArray(percentiles.size) { i ->
            val idx = (sorted.size - 1) * percentiles[i] / 100.0
            val lo = floor(idx).toInt()
            val hi = ceil(idx).toInt()
            sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo)
        }
    }

    /** Median residual (mg/dL) at [horizonMin] for [regime] — null while cold. The 30-min value
     *  is `boostV7_q50Drift`, the live criterion-(b) instrument. */
    fun median(regime: V7Regime, horizonMin: Int): Double? = quantiles(regime, horizonMin, doubleArrayOf(50.0))?.get(0)

    /** Serialize to the persisted JSON blob (see [deserialize]). Timestamps stored in seconds and
     *  residuals rounded to 0.1 mg/dL to keep the blob compact. */
    fun serialize(): String {
        val pend = JSONArray()
        for (p in pending) {
            val arr = JSONArray().put(p.tsMs / 1000L).put(p.regime.name)
            for (proj in p.projections) arr.put(round(proj * 10.0) / 10.0)
            var mask = 0
            for (h in p.matured.indices) if (p.matured[h]) mask = mask or (1 shl h)
            arr.put(mask)
            pend.put(arr)
        }
        val poolsJson = JSONObject()
        for ((key, pool) in pools) {
            val flat = JSONArray()
            for (s in pool) {
                flat.put(s.tsMs / 1000L)
                flat.put(s.residual)
            }
            poolsJson.put(key, flat)
        }
        return JSONObject().put("v", SERIAL_VERSION).put("pend", pend).put("pools", poolsJson).toString()
    }
}

/**
 * Sens-frozen efficacy innovation (log-only) — the Backtest-2 follow-up.
 *
 * The foundation report §2 showed the innovation statistic has NO teeth when computed against
 * the already-adapted `variable_sens` (Cohen's d = 0.02 on the festival window): the dynISF +
 * activity-load pipelines absorb exercise into sens BEFORE the innovation measures it, so the
 * statistic is centered exactly when the adaptation works. This tracker computes the same
 * innovation with sensitivity FROZEN at the PROFILE (static) ISF:
 *
 *     innov = ΔBG(5m) − BGI5_frozen = delta + iob_activity × profile_sens × 5
 *
 * and exposes the rolling 30-min SUM (`boostV7_innovSensFrozen`). Log-only: no behaviour, no
 * damper — it only tests whether the frozen reconstruction has the signal the adapted one lacks.
 * In-memory only (a restart cold-starts the 30-min window — fails safe to null).
 */
class V7InnovationTracker {

    companion object {

        const val WINDOW_MS = 30L * 60_000L
    }

    private class Entry(val tsMs: Long, val innovation: Double)

    private val entries = ArrayDeque<Entry>()

    /**
     * Record this cycle's sens-frozen innovation and return the rolling 30-min sum (mg/dL),
     * or null when nothing is in the window (cold start) or inputs are unusable.
     * Multi-invoke dedup: an entry in the same 5-min bucket replaces the previous one.
     */
    fun onCycle(nowMs: Long, delta5: Double, iobActivity: Double, sensFrozen: Double): Double? {
        if (!delta5.isFinite() || !iobActivity.isFinite() || !sensFrozen.isFinite() || sensFrozen <= 0.0) {
            trim(nowMs)
            return sum()
        }
        val innovation = delta5 + iobActivity * sensFrozen * 5.0
        val last = entries.lastOrNull()
        if (last != null && last.tsMs / V7ResidualTracker.CYCLE_BUCKET_MS == nowMs / V7ResidualTracker.CYCLE_BUCKET_MS) entries.removeLast()
        entries.addLast(Entry(nowMs, innovation))
        trim(nowMs)
        return sum()
    }

    private fun trim(nowMs: Long) {
        // <= so an entry exactly 30 min old drops: the rolling sum spans 6 five-min cycles
        // (the innov30 semantics of Backtest 2), not 7.
        while (entries.isNotEmpty() && entries.first().tsMs <= nowMs - WINDOW_MS) entries.removeFirst()
    }

    private fun sum(): Double? = if (entries.isEmpty()) null else entries.sumOf { it.innovation }
}
