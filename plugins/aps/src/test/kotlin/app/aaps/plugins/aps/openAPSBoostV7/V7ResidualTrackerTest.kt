package app.aaps.plugins.aps.openAPSBoostV7

import app.aaps.plugins.aps.openAPSBoostV5.MealHypothesis
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * V7ResidualTracker — the on-device substrate for the V7 shadow (foundation report
 * `backtesting/reports/2026-07_v7_foundation_REPORT.md`: substrate GO, sizing NO-GO).
 *
 * Covers: regime classification + pool conditioning (the criterion-(b) debias), residual
 * arithmetic against the v7_common expected-BG model, cold-start abstention at the warm
 * threshold, ~21-day windowing + size cap, persistence round-trip (V5StateStore idiom),
 * corrupt-blob cold start, multi-invoke dedup, and missed-maturation gaps.
 */
class V7ResidualTrackerTest {

    private val cycleMs = 300_000L

    /** Drive [n] consecutive 5-min cycles with constant inputs, starting at [startMs]. */
    /** Old constant-BGI5 projection, kept in tests to preserve the residual arithmetic. */
    private fun proj(bg: Double, bgi5: Double?): DoubleArray? =
        bgi5?.let { b -> DoubleArray(V7ResidualTracker.HORIZONS_MIN.size) { i -> bg + b * V7ResidualTracker.HORIZONS_MIN[i] / 5.0 } }

    private fun drive(tracker: V7ResidualTracker, n: Int, bg: Double, bgi5: Double?, regime: V7Regime?, startMs: Long = 0L): Long {
        var t = startMs
        repeat(n) {
            tracker.onCycle(t, bg, proj(bg, bgi5), regime)
            t += cycleMs
        }
        return t
    }

    // ── Regime classification (the criterion-(b) conditioning) ─────────────────────────────────

    @Test fun `meal-session states classify MEAL regardless of hour or delta`() {
        for (state in listOf(MealHypothesis.CONFIRMED, MealHypothesis.COMMITTED, MealHypothesis.RECOVERING)) {
            assertThat(classifyV7Regime(state, delta = 9.0, shortAvgDelta = 8.0, hour = 3)).isEqualTo(V7Regime.MEAL)
            assertThat(classifyV7Regime(state, delta = 0.0, shortAvgDelta = 0.0, hour = 13)).isEqualTo(V7Regime.MEAL)
        }
    }

    @Test fun `non-meal night hours classify NIGHT`() {
        assertThat(classifyV7Regime(MealHypothesis.IDLE, 0.0, 0.0, hour = 23)).isEqualTo(V7Regime.NIGHT)
        assertThat(classifyV7Regime(MealHypothesis.OBSERVING, 12.0, 10.0, hour = 3)).isEqualTo(V7Regime.NIGHT)
        assertThat(classifyV7Regime(null, 0.0, 0.0, hour = 6)).isEqualTo(V7Regime.NIGHT)
    }

    @Test fun `non-meal daytime flat cycles classify QUIET_FLAT`() {
        assertThat(classifyV7Regime(MealHypothesis.IDLE, 1.5, -2.0, hour = 12)).isEqualTo(V7Regime.QUIET_FLAT)
        assertThat(classifyV7Regime(null, 0.0, 0.0, hour = 7)).isEqualTo(V7Regime.QUIET_FLAT)
        assertThat(classifyV7Regime(MealHypothesis.OBSERVING, -3.0, 3.0, hour = 22)).isEqualTo(V7Regime.QUIET_FLAT)
    }

    @Test fun `non-meal daytime RISING cycles are EXCLUDED - the unannounced-onset pollution`() {
        // This is the debias: the offline "quiet" pool kept these and inherited the +12..+38 bias.
        assertThat(classifyV7Regime(MealHypothesis.IDLE, 6.0, 4.0, hour = 12)).isNull()
        assertThat(classifyV7Regime(MealHypothesis.OBSERVING, 3.5, 1.0, hour = 15)).isNull()
        assertThat(classifyV7Regime(null, 0.0, -3.5, hour = 10)).isNull()
    }

    // ── Pool conditioning + residual arithmetic ─────────────────────────────────────────────────

    @Test fun `residual = observed minus IOB-only projection, pooled by regime at projection time`() {
        // Constant bg=100, bgi5=-2 (IOB actively dropping 2 mg/dL per 5 min in the model, flat in
        // reality): proj30 = 100-12 = 88, proj60 = 76, proj90 = 64 → residuals +12 / +24 / +36.
        val tracker = V7ResidualTracker()
        drive(tracker, 250, bg = 100.0, bgi5 = -2.0, regime = V7Regime.MEAL)
        assertThat(tracker.median(V7Regime.MEAL, 30)!!).isWithin(1e-9).of(12.0)
        assertThat(tracker.median(V7Regime.MEAL, 60)!!).isWithin(1e-9).of(24.0)
        assertThat(tracker.median(V7Regime.MEAL, 90)!!).isWithin(1e-9).of(36.0)
        // Identical samples → every percentile equals the median.
        val q = tracker.quantiles(V7Regime.MEAL, 60)!!
        assertThat(q.toList()).containsExactly(24.0, 24.0, 24.0, 24.0, 24.0).inOrder()
        // Conditioning: nothing leaked into the other pools.
        assertThat(tracker.count(V7Regime.QUIET_FLAT, 60)).isEqualTo(0)
        assertThat(tracker.count(V7Regime.NIGHT, 60)).isEqualTo(0)
    }

    @Test fun `excluded cycles pool nothing but still mature earlier projections`() {
        val tracker = V7ResidualTracker()
        // One MEAL projection at t=0, then excluded cycles (regime null) supply the observations.
        tracker.onCycle(0L, 100.0, proj(100.0, -2.0), V7Regime.MEAL)
        var t = cycleMs
        repeat(20) {
            tracker.onCycle(t, 100.0, proj(100.0, -2.0), null)
            t += cycleMs
        }
        // The MEAL projection matured at all three horizons off excluded-cycle observations…
        assertThat(tracker.count(V7Regime.MEAL, 30)).isEqualTo(1)
        assertThat(tracker.count(V7Regime.MEAL, 60)).isEqualTo(1)
        assertThat(tracker.count(V7Regime.MEAL, 90)).isEqualTo(1)
        // …and the excluded cycles themselves contributed no projections to any pool.
        assertThat(tracker.count(V7Regime.QUIET_FLAT, 30)).isEqualTo(0)
        assertThat(tracker.count(V7Regime.NIGHT, 30)).isEqualTo(0)
    }

    // ── Cold start / warm threshold ─────────────────────────────────────────────────────────────

    @Test fun `cold start - quantiles and median are null, counts zero`() {
        val tracker = V7ResidualTracker()
        assertThat(tracker.count(V7Regime.QUIET_FLAT, 60)).isEqualTo(0)
        assertThat(tracker.quantiles(V7Regime.QUIET_FLAT, 60)).isNull()
        assertThat(tracker.median(V7Regime.MEAL, 30)).isNull()
    }

    @Test fun `pool abstains below WARM_MIN_SAMPLES and warms exactly at it`() {
        val tracker = V7ResidualTracker()
        // Cycle i's 30-min horizon matures at cycle i+6 → after N cycles, count(30) = N-6.
        drive(tracker, V7ResidualTracker.WARM_MIN_SAMPLES + 5, bg = 100.0, bgi5 = 0.0, regime = V7Regime.QUIET_FLAT)
        assertThat(tracker.count(V7Regime.QUIET_FLAT, 30)).isEqualTo(V7ResidualTracker.WARM_MIN_SAMPLES - 1)
        assertThat(tracker.quantiles(V7Regime.QUIET_FLAT, 30)).isNull()
        // One more cycle matures the 150th sample → warm.
        tracker.onCycle((V7ResidualTracker.WARM_MIN_SAMPLES + 5) * cycleMs, 100.0, proj(100.0, 0.0), V7Regime.QUIET_FLAT)
        assertThat(tracker.count(V7Regime.QUIET_FLAT, 30)).isEqualTo(V7ResidualTracker.WARM_MIN_SAMPLES)
        assertThat(tracker.quantiles(V7Regime.QUIET_FLAT, 30)).isNotNull()
    }

    // ── Windowing ───────────────────────────────────────────────────────────────────────────────

    @Test fun `samples older than the 21-day window are evicted`() {
        val tracker = V7ResidualTracker()
        val end = drive(tracker, 20, bg = 100.0, bgi5 = 0.0, regime = V7Regime.MEAL)
        assertThat(tracker.count(V7Regime.MEAL, 30)).isEqualTo(14) // 20 cycles − 6 not yet due
        // 22 days later: everything in the pool predates the window → evicted.
        tracker.onCycle(end + 22L * 86_400_000L, 100.0, proj(100.0, 0.0), V7Regime.MEAL)
        assertThat(tracker.count(V7Regime.MEAL, 30)).isEqualTo(0)
    }

    @Test fun `per-pool size cap holds the newest MAX_SAMPLES_PER_POOL samples`() {
        val tracker = V7ResidualTracker()
        drive(tracker, V7ResidualTracker.MAX_SAMPLES_PER_POOL + 110, bg = 100.0, bgi5 = 0.0, regime = V7Regime.MEAL)
        assertThat(tracker.count(V7Regime.MEAL, 30)).isEqualTo(V7ResidualTracker.MAX_SAMPLES_PER_POOL)
    }

    // ── Persistence (V5StateStore idiom: JSON blob) ─────────────────────────────────────────────

    @Test fun `persistence round-trip preserves pools and quantiles`() {
        val tracker = V7ResidualTracker()
        drive(tracker, 250, bg = 100.0, bgi5 = -2.0, regime = V7Regime.MEAL)
        val restored = V7ResidualTracker.deserialize(tracker.serialize())
        for (h in intArrayOf(30, 60, 90)) {
            assertThat(restored.count(V7Regime.MEAL, h)).isEqualTo(tracker.count(V7Regime.MEAL, h))
            assertThat(restored.quantiles(V7Regime.MEAL, h)!!.toList())
                .isEqualTo(tracker.quantiles(V7Regime.MEAL, h)!!.toList())
        }
    }

    @Test fun `persistence round-trip preserves PENDING projections - they mature after a restart`() {
        val tracker = V7ResidualTracker()
        tracker.onCycle(0L, 100.0, proj(100.0, -2.0), V7Regime.MEAL) // in-flight projection, nothing matured
        val restored = V7ResidualTracker.deserialize(tracker.serialize())
        assertThat(restored.count(V7Regime.MEAL, 30)).isEqualTo(0)
        restored.onCycle(30 * 60_000L, 100.0, proj(100.0, null), null) // observation 30 min later
        assertThat(restored.count(V7Regime.MEAL, 30)).isEqualTo(1)
        assertThat(restored.median(V7Regime.MEAL, 30)).isNull() // still cold — abstains
    }

    @Test fun `blank or corrupt blob deserializes to a cold-start tracker`() {
        for (raw in listOf(null, "", "not json {", """{"v":99,"pools":{}}""", """{"v":1,"pend":"bad"}""")) {
            val tracker = V7ResidualTracker.deserialize(raw)
            assertThat(tracker.count(V7Regime.MEAL, 60)).isEqualTo(0)
            assertThat(tracker.quantiles(V7Regime.QUIET_FLAT, 60)).isNull()
        }
    }

    // ── Multi-invoke + gap behaviour ────────────────────────────────────────────────────────────

    // The dedup bucket narrowed from 5 min to 1 min on 2026-08-01: at 5 min a one-minute loop
    // had four of every five entries silently replaced. It still collapses a re-run of the SAME
    // cycle, which is all it was ever for, so the gap here is sub-cycle rather than a minute.
    @Test fun `re-invoking within the same cycle dedups to a single projection`() {
        val tracker = V7ResidualTracker()
        tracker.onCycle(0L, 100.0, proj(100.0, -2.0), V7Regime.MEAL)
        tracker.onCycle(20_000L, 101.0, proj(101.0, -2.0), V7Regime.MEAL)  // same bucket → replaces
        var t = cycleMs
        repeat(8) {
            tracker.onCycle(t, 100.0, proj(100.0, null), null)
            t += cycleMs
        }
        assertThat(tracker.count(V7Regime.MEAL, 30)).isEqualTo(1)
    }

    @Test fun `two cycles a minute apart are kept as distinct entries`() {
        // The behaviour the narrowing exists to restore: on a one-minute feed these are two real
        // cycles, and before the change the second silently replaced the first.
        val tracker = V7ResidualTracker()
        tracker.onCycle(0L, 100.0, proj(100.0, -2.0), V7Regime.MEAL)
        tracker.onCycle(60_000L, 101.0, proj(101.0, -2.0), V7Regime.MEAL)
        var t = cycleMs
        repeat(8) {
            tracker.onCycle(t, 100.0, proj(100.0, null), null)
            t += cycleMs
        }
        assertThat(tracker.count(V7Regime.MEAL, 30)).isEqualTo(2)
    }

    @Test fun `a missed maturation window (data gap) yields no sample for that horizon only`() {
        val tracker = V7ResidualTracker()
        tracker.onCycle(0L, 100.0, proj(100.0, -2.0), V7Regime.MEAL)
        // Next observation 40 min later: the 30-min window (due 30, late tol +5) was missed…
        tracker.onCycle(40 * 60_000L, 100.0, proj(100.0, null), null)
        assertThat(tracker.count(V7Regime.MEAL, 30)).isEqualTo(0)
        // …but the 60-min horizon still matures on time.
        tracker.onCycle(60 * 60_000L, 100.0, proj(100.0, null), null)
        assertThat(tracker.count(V7Regime.MEAL, 60)).isEqualTo(1)
    }
}
