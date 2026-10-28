package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Dose-path audit item 16, live gate. Aggressive early confirm is insulin-adding and had no live
 * time-below-range gate: once on, it stayed on however the person's lows developed until someone
 * changed the setting. It now uses the composed floor's fail-closed 14-day test, as the
 * velocity-budget floor does (TBR<63 under 2.0% and TBR<70 under 3.5%).
 */
class AggressiveEarlyConfirmTbrGateTest {

    @Test fun `on and inside both limits runs`() {
        assertThat(aggressiveEarlyConfirmAllowed(true, 1.0, 2.0)).isTrue()
    }

    @Test fun `time below 70 at or over 3_5 percent blocks it`() {
        assertThat(aggressiveEarlyConfirmAllowed(true, 1.0, 3.5)).isFalse()
        assertThat(aggressiveEarlyConfirmAllowed(true, 1.0, 6.0)).isFalse()
    }

    @Test fun `time below 63 at or over 2 percent blocks it`() {
        assertThat(aggressiveEarlyConfirmAllowed(true, 2.0, 3.0)).isFalse()
    }

    @Test fun `too little CGM history fails closed`() {
        assertThat(aggressiveEarlyConfirmAllowed(true, null, 1.0)).isFalse()
        assertThat(aggressiveEarlyConfirmAllowed(true, 1.0, null)).isFalse()
        assertThat(aggressiveEarlyConfirmAllowed(true, null, null)).isFalse()
    }

    @Test fun `off stays off`() {
        assertThat(aggressiveEarlyConfirmAllowed(false, 0.0, 0.0)).isFalse()
    }

    @Test fun `the limits are the velocity-budget floor's`() {
        for (t63 in listOf(null, 0.0, 1.99, 2.0, 5.0)) for (t70 in listOf(null, 0.0, 3.49, 3.5, 8.0))
            assertThat(aggressiveEarlyConfirmAllowed(true, t63, t70)).isEqualTo(composedFloorAllowedByTbr(t63, t70))
    }
}
