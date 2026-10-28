package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-06-19 intraday activity-load (shadow): today's cumulative steps vs typical pace by hour →
 * raise-only ISF nudge (acute exercise = more sensitive). Pure-function tests.
 */
class IntradayActivityFactorTest {

    private val baseline = 14000   // ~typical daily steps

    @Test fun `running well ahead of pace raises ISF`() {
        // 15:00 → diurnal fraction ~0.66 → expected ≈ 9240. 18000 today = ~1.95x → near the cap.
        val f = DailyStepHistoryTracker.intradayFactor(stepsToday = 18000, baseline = baseline, hour = 15)
        assertThat(f.ratio!!).isGreaterThan(1.5)
        assertThat(f.wouldDeltaIsfPct).isGreaterThan(10.0)   // approaching the 15% cap
    }

    @Test fun `on-pace gives no factor`() {
        // 12:00 → fraction ~0.44 → expected ≈ 6160. 6160 today = 1.0x → 0%.
        val f = DailyStepHistoryTracker.intradayFactor(stepsToday = 6160, baseline = baseline, hour = 12)
        assertThat(f.wouldDeltaIsfPct).isEqualTo(0.0)
    }

    @Test fun `below pace returns zero - raise-only, next-day factor owns the low side`() {
        val f = DailyStepHistoryTracker.intradayFactor(stepsToday = 2000, baseline = baseline, hour = 15)
        assertThat(f.wouldDeltaIsfPct).isEqualTo(0.0)
    }

    @Test fun `capped at the activity max`() {
        val f = DailyStepHistoryTracker.intradayFactor(stepsToday = 40000, baseline = baseline, hour = 16)
        assertThat(f.wouldDeltaIsfPct).isWithin(0.001).of(DailyStepHistoryTracker.ACTIVITY_MAX_ISF_PCT)
    }

    @Test fun `no baseline yet means no factor`() {
        val f = DailyStepHistoryTracker.intradayFactor(stepsToday = 20000, baseline = null, hour = 14)
        assertThat(f.ratio).isNull()
        assertThat(f.wouldDeltaIsfPct).isEqualTo(0.0)
    }

    @Test fun `overnight tiny expected does not divide-by-zero`() {
        // hour 3 → fraction floored at 0.02 → expected ≈ 280; a 500-step night walk reads as ahead.
        val f = DailyStepHistoryTracker.intradayFactor(stepsToday = 500, baseline = baseline, hour = 3)
        assertThat(f.ratio).isNotNull()
        assertThat(f.wouldDeltaIsfPct).isAtLeast(0.0)
    }
}
