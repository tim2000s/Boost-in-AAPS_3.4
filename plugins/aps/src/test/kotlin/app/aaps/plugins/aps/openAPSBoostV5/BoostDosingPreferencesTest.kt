package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.core.data.model.GlucoseUnit
import app.aaps.core.interfaces.profile.ProfileUtil
import app.aaps.core.keys.DoubleKey
import app.aaps.core.keys.UnitDoubleKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.plugins.aps.getBoostDosing
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test
import org.mockito.kotlin.mock
import org.mockito.kotlin.whenever

/**
 * Regression tests for the Simple-Mode dosing-key mask bug
 * (`backtesting/reports/2026-07_maxiob_consistency_REPORT.md`).
 *
 * ROOT CAUSE: `PreferencesImpl.get(DoublePreferenceKey)` returns the FACTORY DEFAULT for any
 * `defaultedBySM = true` key while Simple Mode is ON. Every Boost dosing key is `defaultedBySM`, so
 * in Simple Mode the doser read `boost_maxIOB = 1.0` (not the user's 8), `confirmedCap = 2.5`,
 * `committedCap = 0.5` — zeroing both engines. `getBoostDosing` reads the raw stored value
 * (mirroring auto-config's `getIfExists ?: default`) to un-mask the dose path while the keys stay
 * hidden in the Simple-Mode UI.
 *
 * These tests model Simple Mode by mocking `getIfExists` to return the user's STORED value: that is
 * exactly what `getIfExists` does regardless of Simple Mode (it never masks), and it is what
 * `getBoostDosing` delegates to. A plain masking `get()` would instead have returned the key
 * default — the value we prove the doser no longer sees.
 */
class BoostDosingPreferencesTest {

    // ── The read helper: stored value wins, bypassing the Simple-Mode mask ──

    @Test fun `maxIOB reads the stored 8, not the masked factory default 1`() {
        val prefs = mock<Preferences>()
        whenever(prefs.getIfExists(DoubleKey.ApsBoostMaxIob)).thenReturn(8.0)   // user/auto-config stored value
        // Sanity: the factory default that Simple Mode would have masked to is 1.0.
        assertThat(DoubleKey.ApsBoostMaxIob.defaultValue).isEqualTo(1.0)
        assertThat(prefs.getBoostDosing(DoubleKey.ApsBoostMaxIob)).isEqualTo(8.0)
    }

    @Test fun `confirmed and committed caps read the stored values, not masked 2_5 and 0_5`() {
        val prefs = mock<Preferences>()
        whenever(prefs.getIfExists(DoubleKey.ApsBoostV5ConfirmedCapU)).thenReturn(6.0)
        whenever(prefs.getIfExists(DoubleKey.ApsBoostV5CommittedCapU)).thenReturn(1.2)
        assertThat(DoubleKey.ApsBoostV5ConfirmedCapU.defaultValue).isEqualTo(2.5)
        assertThat(DoubleKey.ApsBoostV5CommittedCapU.defaultValue).isEqualTo(0.5)
        assertThat(prefs.getBoostDosing(DoubleKey.ApsBoostV5ConfirmedCapU)).isEqualTo(6.0)
        assertThat(prefs.getBoostDosing(DoubleKey.ApsBoostV5CommittedCapU)).isEqualTo(1.2)
    }

    @Test fun `never-set key falls back to the factory default`() {
        val prefs = mock<Preferences>()
        whenever(prefs.getIfExists(DoubleKey.ApsBoostMaxIob)).thenReturn(null)   // getIfExists null == never persisted
        assertThat(prefs.getBoostDosing(DoubleKey.ApsBoostMaxIob)).isEqualTo(1.0)   // == defaultValue
    }

    // ── UnitDouble overload: the fallback default MUST be unit-converted (mmol night-mode bug) ──
    // getIfExists(UnitDoubleKey) returns the stored value already run through fromMgdlToUnits, i.e. in
    // DISPLAY units. On an unset key we must supply the default in the SAME frame — what get() does. The
    // old code handed back the raw mg/dL default, so a mmol user's unset night-mode BG offset came back
    // as 27 and convertToMgdl(27, MMOL) = 486 mg/dL downstream → SMBs disabled all night.

    @Test fun `UnitDouble never-set key falls back to the UNIT-CONVERTED default, not raw mgdl`() {
        val prefs = mock<Preferences>()
        val profileUtil = mock<ProfileUtil>()
        whenever(prefs.getIfExists(UnitDoubleKey.ApsBoostNightModeBgOffset)).thenReturn(null) // never persisted
        whenever(profileUtil.units).thenReturn(GlucoseUnit.MMOL)
        whenever(profileUtil.fromMgdlToUnits(27.0, GlucoseUnit.MMOL)).thenReturn(1.5)          // 27 mg/dL == 1.5 mmol
        // Sanity: the raw default is 27 (mg/dL-canonical); the bug returned this unconverted.
        assertThat(UnitDoubleKey.ApsBoostNightModeBgOffset.defaultValue).isEqualTo(27.0)
        // The fix: the fallback is the unit-converted default (1.5), so convertToMgdl(1.5, MMOL)=27 downstream.
        assertThat(prefs.getBoostDosing(UnitDoubleKey.ApsBoostNightModeBgOffset, profileUtil)).isEqualTo(1.5)
    }

    @Test fun `UnitDouble stored value is returned via getIfExists unchanged`() {
        val prefs = mock<Preferences>()
        val profileUtil = mock<ProfileUtil>()
        // getIfExists already returns the converted stored value; getBoostDosing passes it through and
        // never consults the default, so no conversion of the stored value happens here.
        whenever(prefs.getIfExists(UnitDoubleKey.ApsBoostNightModeBgOffset)).thenReturn(2.0)
        assertThat(prefs.getBoostDosing(UnitDoubleKey.ApsBoostNightModeBgOffset, profileUtil)).isEqualTo(2.0)
    }

    @Test fun `bit-identity - stored value is returned unchanged (== what get returns when unmasked)`() {
        // With Simple Mode OFF, get() returns sp.getDouble == the stored value; getIfExists returns the
        // same stored value; so getBoostDosing(stored) == get(stored). No behaviour change when unmasked.
        val prefs = mock<Preferences>()
        whenever(prefs.getIfExists(DoubleKey.ApsBoostMaxIob)).thenReturn(3.55)
        assertThat(prefs.getBoostDosing(DoubleKey.ApsBoostMaxIob)).isEqualTo(3.55)
    }

    // ── Engine-level FLIP: the masked ceiling zeroed the real SafetyGates dose path ──
    // applyPhase3 is the exact V6 function the report cites (hard clamp headroom = maxIob − iob,
    // then iobHeadroomBrake fraction = iob / maxIob). user H's 17:34 CONFIRMED cycle: iob 1.04,
    // a 4.0U confirmed shot, on a genuine rise. Reproduces fd = 0 at masked maxIob 1.0 and the
    // real delivery at his stored maxIob 8.0 — the outcome flips solely on which value the doser reads.

    private fun userHCycle(maxIob: Double) = Phase3Inputs(
        insulinToDeliver = 4.0,          // his confirmedCap-sized shot (budget × mult, pre-safety)
        enableSmbPreChecks = true,
        minGuardBg = 148.0, minGuardThreshold = 80.0,
        maxDelta = 3.0, bg = 148.0,
        iob = 1.04,
        maxIob = maxIob,
        deltaAccl = 5.0, delta = 4.0,    // still accelerating → decel brake 1.0
        baseInsulinReq = 5.64,           // his budget; dynamicSpikeCap = 2.5 × 5.64 well above 4.0
        roundSmbTo = 0.05,
        sensorQualityOk = true,
    )

    @Test fun `masked maxIOB 1_0 zeroes the confirmed shot (the bug)`() {
        val r = applyPhase3(userHCycle(maxIob = 1.0))
        assertThat(r.finalDose).isEqualTo(0.0)                 // headroom = max(0, 1.0 − 1.04) = 0
        assertThat(r.reductions.maxIobClampApplied).isTrue()
    }

    @Test fun `stored maxIOB 8_0 lets the confirmed shot land (the fix)`() {
        val r = applyPhase3(userHCycle(maxIob = 8.0))
        assertThat(r.finalDose).isEqualTo(4.0)                 // headroom 6.96, iob_frac 0.13 → no brake
        assertThat(r.reductions.maxIobClampApplied).isFalse()
    }

    @Test fun `the ONLY difference is the ceiling the doser reads`() {
        // Same cycle, same everything except maxIob → 0.0 vs 4.0. This is the whole bug.
        assertThat(applyPhase3(userHCycle(maxIob = 1.0)).finalDose).isEqualTo(0.0)
        assertThat(applyPhase3(userHCycle(maxIob = 8.0)).finalDose).isEqualTo(4.0)
    }

    // ── Cap sizing flip: a confirmed shot clipped by the masked cap now sizes to the real cap ──
    @Test fun `confirmed shot clipped at masked cap 2_5 now sizes to the stored cap 6_0`() {
        val prefs = mock<Preferences>()
        whenever(prefs.getIfExists(DoubleKey.ApsBoostV5ConfirmedCapU)).thenReturn(6.0)
        val desiredShot = 4.0
        // Under masking the effective cap was the factory default 2.5 → shot clipped to 2.5.
        val maskedCap = DoubleKey.ApsBoostV5ConfirmedCapU.defaultValue
        assertThat(minOf(desiredShot, maskedCap)).isEqualTo(2.5)
        // With the fix the doser reads the real 6.0 → the full 4.0 shot is delivered.
        val realCap = prefs.getBoostDosing(DoubleKey.ApsBoostV5ConfirmedCapU)
        assertThat(minOf(desiredShot, realCap)).isEqualTo(4.0)
    }
}
