package app.aaps.plugins.aps.openAPSBoost

import app.aaps.core.keys.BooleanKey
import app.aaps.core.keys.DoubleKey
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.ENGINE_MODE_V1
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.ENGINE_MODE_V6
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.isSwitchToV6
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.isTddJustEnabled
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.reconcileSensitivitySettings
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-09-24. With TDD-based ISF off, "TDD sensitivity adjustment" fell back to the DynISF curve ratio,
 * which lowered targets as BG rose and so counted BG twice in the dose. These pin the rule that
 * removes that state: TDD off forces the adjustment off and BG impact on ISF to 0, and the first V6
 * run after V1 clears the adjustment. Switching TDD-based ISF on sets BG impact back to 100%, once.
 */
class BoostSensitivitySettingsReconcileTest {

    @Test fun `TDD off clears the adjustment and zeroes BG impact`() {
        val r = reconcileSensitivitySettings(useTdd = false, adjustSens = true, velocityPct = 100.0, switchedToV6 = false)
        assertThat(r.adjustSens).isFalse()
        assertThat(r.velocityPct).isEqualTo(0.0)
        assertThat(r.clearedAdjustSens).isTrue()
        assertThat(r.zeroedVelocity).isTrue()
        assertThat(r.changed).isTrue()
    }

    @Test fun `TDD off with settings already safe changes nothing`() {
        val r = reconcileSensitivitySettings(useTdd = false, adjustSens = false, velocityPct = 0.0, switchedToV6 = false)
        assertThat(r.changed).isFalse()
        assertThat(r.adjustSens).isFalse()
        assertThat(r.velocityPct).isEqualTo(0.0)
    }

    @Test fun `TDD on under V1 leaves both settings as the user set them`() {
        val r = reconcileSensitivitySettings(useTdd = true, adjustSens = true, velocityPct = 60.0, switchedToV6 = false)
        assertThat(r.changed).isFalse()
        assertThat(r.adjustSens).isTrue()
        assertThat(r.velocityPct).isEqualTo(60.0)
    }

    @Test fun `first V6 run clears the adjustment even with TDD on, and keeps BG impact`() {
        val r = reconcileSensitivitySettings(useTdd = true, adjustSens = true, velocityPct = 60.0, switchedToV6 = true)
        assertThat(r.adjustSens).isFalse()
        assertThat(r.clearedAdjustSens).isTrue()
        assertThat(r.velocityPct).isEqualTo(60.0)
        assertThat(r.zeroedVelocity).isFalse()
    }

    @Test fun `adjustment re-enabled with TDD on after the switch is respected`() {
        val r = reconcileSensitivitySettings(useTdd = true, adjustSens = true, velocityPct = 100.0, switchedToV6 = false)
        assertThat(r.adjustSens).isTrue()
        assertThat(r.changed).isFalse()
    }

    @Test fun `switching TDD on sets BG impact to the on value`() {
        val r = reconcileSensitivitySettings(useTdd = true, adjustSens = false, velocityPct = 0.0, switchedToV6 = false, tddJustEnabled = true, velocityOnPct = 100.0)
        assertThat(r.velocityPct).isEqualTo(100.0)
        assertThat(r.restoredVelocity).isTrue()
        assertThat(r.zeroedVelocity).isFalse()
        assertThat(r.changed).isTrue()
    }

    @Test fun `a BG impact chosen after TDD was switched on is kept`() {
        val r = reconcileSensitivitySettings(useTdd = true, adjustSens = false, velocityPct = 40.0, switchedToV6 = false, tddJustEnabled = false, velocityOnPct = 100.0)
        assertThat(r.velocityPct).isEqualTo(40.0)
        assertThat(r.changed).isFalse()
    }

    @Test fun `switching TDD on does not turn the sensitivity adjustment on`() {
        val r = reconcileSensitivitySettings(useTdd = true, adjustSens = false, velocityPct = 0.0, switchedToV6 = false, tddJustEnabled = true)
        assertThat(r.adjustSens).isFalse()
    }

    @Test fun `TDD switched on is detected only from a recorded off`() {
        assertThat(isTddJustEnabled("false", useTdd = true)).isTrue()
        assertThat(isTddJustEnabled("true", useTdd = true)).isFalse()
        assertThat(isTddJustEnabled("", useTdd = true)).isFalse()
        assertThat(isTddJustEnabled("false", useTdd = false)).isFalse()
    }

    @Test fun `without a TDD switch-on the reconcile can only turn settings down`() {
        for (useTdd in listOf(true, false)) for (adjust in listOf(true, false)) for (sw in listOf(true, false))
            for (v in listOf(0.0, 50.0, 100.0)) {
                val r = reconcileSensitivitySettings(useTdd, adjust, v, sw)
                if (!adjust) assertThat(r.adjustSens).isFalse()
                assertThat(r.velocityPct).isAtMost(v)
            }
    }

    @Test fun `switch to V6 is detected from V1 and from no record, not from V6`() {
        assertThat(isSwitchToV6(ENGINE_MODE_V1, v5Active = true)).isTrue()
        assertThat(isSwitchToV6("", v5Active = true)).isTrue()
        assertThat(isSwitchToV6(ENGINE_MODE_V6, v5Active = true)).isFalse()
        assertThat(isSwitchToV6(ENGINE_MODE_V6, v5Active = false)).isFalse()
        assertThat(isSwitchToV6(ENGINE_MODE_V1, v5Active = false)).isFalse()
    }

    @Test fun `keys - autosens drives sensitivity without TDD by default, and TDD-only settings depend on TDD`() {
        assertThat(BooleanKey.ApsBoostAutosensWhenNoTdd.defaultValue).isTrue()
        assertThat(BooleanKey.ApsBoostAdjustSensitivity.dependency).isEqualTo(BooleanKey.ApsBoostUseTdd)
        assertThat(DoubleKey.ApsBoostDynIsfVelocity.dependency).isEqualTo(BooleanKey.ApsBoostUseTdd)
    }
}
