package app.aaps.plugins.aps.openAPSBoostV7

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Sens-frozen efficacy innovation (log-only) — the Backtest-2 follow-up: the adapted
 * `variable_sens` absorbs the exercise signal before the innovation can measure it (Cohen's
 * d = 0.02, report §2), so the shadow computes the SAME statistic with sens frozen at the
 * static profile ISF. These tests pin the arithmetic (frozen ≠ adapted whenever sens differs),
 * the 30-min rolling window, cold-start null, and multi-invoke dedup.
 */
class V7InnovationTrackerTest {

    private val cycleMs = 300_000L

    @Test fun `sens-frozen innovation differs from the adapted value whenever sens differs`() {
        // delta +2, activity 0.01 U/min: frozen (profile ISF 50) → 2 + 0.01×50×5 = 4.5;
        // the adapted pipeline (variable_sens 100) would have measured 2 + 0.01×100×5 = 7.0.
        val frozen = V7InnovationTracker().onCycle(0L, delta5 = 2.0, iobActivity = 0.01, sensFrozen = 50.0)!!
        val adapted = V7InnovationTracker().onCycle(0L, delta5 = 2.0, iobActivity = 0.01, sensFrozen = 100.0)!!
        assertThat(frozen).isWithin(1e-9).of(4.5)
        assertThat(adapted).isWithin(1e-9).of(7.0)
        assertThat(frozen).isNotEqualTo(adapted) // the whole point of the sens-frozen variant
    }

    @Test fun `returns the rolling 30-min SUM and drops entries older than the window`() {
        val tracker = V7InnovationTracker()
        var sum: Double? = null
        var t = 0L
        repeat(6) { // 6 cycles × 4.5 fill the 30-min window
            sum = tracker.onCycle(t, 2.0, 0.01, 50.0)
            t += cycleMs
        }
        assertThat(sum!!).isWithin(1e-9).of(27.0)
        // The 7th cycle evicts the t=0 entry (window is strictly 30 min): sum stays 6 × 4.5.
        assertThat(tracker.onCycle(t, 2.0, 0.01, 50.0)!!).isWithin(1e-9).of(27.0)
        // A long gap flushes the window down to the single fresh entry.
        assertThat(tracker.onCycle(t + 3_600_000L, 2.0, 0.01, 50.0)!!).isWithin(1e-9).of(4.5)
    }

    @Test fun `cold start and unusable sens yield null`() {
        val tracker = V7InnovationTracker()
        assertThat(tracker.onCycle(0L, 2.0, 0.01, sensFrozen = 0.0)).isNull()     // invalid sens, empty window
        assertThat(tracker.onCycle(cycleMs, 2.0, 0.01, sensFrozen = Double.NaN)).isNull()
    }

    // Bucket narrowed 5 min -> 1 min (2026-08-01); a re-run of the same cycle still replaces.
    @Test fun `re-invoking within the same cycle replaces the entry instead of double-counting`() {
        val tracker = V7InnovationTracker()
        tracker.onCycle(0L, 2.0, 0.01, 50.0)
        val sum = tracker.onCycle(20_000L, 4.0, 0.01, 50.0)!! // same bucket → replaces (4 + 2.5 = 6.5)
        assertThat(sum).isWithin(1e-9).of(6.5)
    }
}
