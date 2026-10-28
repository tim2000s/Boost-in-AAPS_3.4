package app.aaps.plugins.aps.openAPSBoost

import app.aaps.core.keys.DoubleKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.plugins.aps.getBoostDosing
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test
import org.mockito.kotlin.mock
import org.mockito.kotlin.whenever
import kotlin.math.max

/**
 * Base-engine (V1/oref) half of the Simple-Mode dosing-mask regression
 * (`backtesting/reports/2026-07_maxiob_consistency_REPORT.md`).
 *
 * `profile.boost_maxIOB` feeds BOTH engines. In the base engine every boost tier is guarded
 * `iob < boostMaxIOB` and clamps its dose to `boostMaxIOB − iob`
 * (DetermineBasalBoost.kt:1491/1496/1529…). At the Simple-Mode-masked boostMaxIOB = 1.0 and
 * iob = 1.04: `1.04 < 1.0` is false → ALL boost tiers skip, and the clamp `1.0 − 1.04 = −0.04` → 0,
 * so base oref delivers ~0 (v1_units = 0). At the user's real boostMaxIOB = 8.0 the guard passes and
 * the clamp leaves 6.96U of headroom. `getBoostDosing` restores the real ceiling in Simple Mode.
 *
 * This models the tier guard + clamp verbatim, driven by the value the base engine now reads.
 */
class BoostMaxIobMaskBypassTest {

    private val iob = 1.04   // user H's 17:34 CONFIRMED cycle

    /** DetermineBasalBoost tier guard (`iob < boostMaxIOB`) + clamp (`boostMaxIOB − iob`, floored at 0). */
    private fun tierFiresAndHeadroom(boostMaxIob: Double): Pair<Boolean, Double> =
        (iob < boostMaxIob) to max(0.0, boostMaxIob - iob)

    @Test fun `masked boostMaxIOB 1_0 skips every base tier and clamps to zero`() {
        val prefs = mock<Preferences>()
        // Simulate the masked read the way the bug behaved: the doser saw the factory default.
        val maskedMaxIob = DoubleKey.ApsBoostMaxIob.defaultValue
        assertThat(maskedMaxIob).isEqualTo(1.0)
        val (fires, headroom) = tierFiresAndHeadroom(maskedMaxIob)
        assertThat(fires).isFalse()          // 1.04 < 1.0 == false → tier skipped
        assertThat(headroom).isEqualTo(0.0)  // 1.0 − 1.04 floored → 0 → base delivers ~0
    }

    @Test fun `stored boostMaxIOB 8_0 fires the tier and leaves real headroom`() {
        val prefs = mock<Preferences>()
        whenever(prefs.getIfExists(DoubleKey.ApsBoostMaxIob)).thenReturn(8.0)
        val realMaxIob = prefs.getBoostDosing(DoubleKey.ApsBoostMaxIob)
        assertThat(realMaxIob).isEqualTo(8.0)
        val (fires, headroom) = tierFiresAndHeadroom(realMaxIob)
        assertThat(fires).isTrue()                     // 1.04 < 8.0 → tier fires
        assertThat(headroom).isWithin(1e-9).of(6.96)   // 8.0 − 1.04
    }

    @Test fun `the guard outcome flips solely on the masked-vs-stored ceiling`() {
        val prefs = mock<Preferences>()
        whenever(prefs.getIfExists(DoubleKey.ApsBoostMaxIob)).thenReturn(8.0)
        // Masked (get() in Simple Mode) → default 1.0 → tier skipped.
        assertThat(tierFiresAndHeadroom(DoubleKey.ApsBoostMaxIob.defaultValue).first).isFalse()
        // Fixed (getBoostDosing) → stored 8.0 → tier fires.
        assertThat(tierFiresAndHeadroom(prefs.getBoostDosing(DoubleKey.ApsBoostMaxIob)).first).isTrue()
    }
}
