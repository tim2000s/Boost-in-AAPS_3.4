package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-06-24 reset-resilient steps-today (phone = authoritative step source). Tests the pure
 * delta-accumulation rule that must not lose the day when the hardware step counter resets.
 */
class StepServiceTodayTest {

    @Test fun `forward readings give the delta`() {
        assertThat(StepService.stepDelta(1300, 1000)).isEqualTo(300)
        assertThat(StepService.stepDelta(9000, 5000)).isEqualTo(4000)
    }

    @Test fun `no movement gives zero`() {
        assertThat(StepService.stepDelta(5000, 5000)).isEqualTo(0)
    }

    @Test fun `counter reset (reboot) counts steps-since-reset, not a negative`() {
        // pre-reboot cumulative 9000, reboot → counter restarts at 200
        assertThat(StepService.stepDelta(200, 9000)).isEqualTo(200)
        // and continues forward from there
        assertThat(StepService.stepDelta(700, 200)).isEqualTo(500)
    }

    /** Accumulating across a reset preserves the day (the bug we saw: 9492 → reset → undercount). */
    @Test fun `accumulation survives a mid-day reset`() {
        var today = 0; var last = 0
        for ((cur, _) in listOf(0 to 0, 4000 to 0, 9000 to 0)) { today += StepService.stepDelta(cur, last); last = cur }
        assertThat(today).isEqualTo(9000)
        // reboot to a small cumulative, keep walking
        for (cur in listOf(200, 700, 1500)) { today += StepService.stepDelta(cur, last); last = cur }
        assertThat(today).isEqualTo(10500)   // 9000 + 1500 since reboot, nothing lost
    }
}
