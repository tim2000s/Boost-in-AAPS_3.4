package app.aaps.plugins.aps.openAPSBoost

import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.baseOrefSmb
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.boostGateOpen
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.v6UnavailableSmb
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-10-08: V1's Boost tiers must not reach the pump where Boost is not supposed to be active.
 *
 * Field case (user F, 05:30 local): night mode switched off, detector SLEEPING, inside the default
 * night window. The gate read open, Tier 5 sized 1.06 U of insulin required to 1.95 U, V6 stood down
 * for sleep and V1's 1.95 U was delivered.
 */
class V6StandDownTest {

    // ── The gate ──

    @Test fun `field case - night mode off, inside window, V6 sleeping - gate closed`() {
        assertThat(boostGateOpen(nightSleepPeriod = false, inNightWindow = true, v6Active = true, detectorSleeping = true)).isFalse()
    }

    @Test fun `inside the window the gate is closed whatever the detector or toggle say`() {
        assertThat(boostGateOpen(nightSleepPeriod = false, inNightWindow = true, v6Active = true, detectorSleeping = false)).isFalse()
        assertThat(boostGateOpen(nightSleepPeriod = false, inNightWindow = true, v6Active = false, detectorSleeping = false)).isFalse()
    }

    @Test fun `outside the window, V6 sleeping closes the gate`() {
        assertThat(boostGateOpen(nightSleepPeriod = false, inNightWindow = false, v6Active = true, detectorSleeping = true)).isFalse()
    }

    @Test fun `outside the window, V1-only sleeping keeps the toggle-governed behaviour`() {
        assertThat(boostGateOpen(nightSleepPeriod = false, inNightWindow = false, v6Active = false, detectorSleeping = true)).isTrue()
        assertThat(boostGateOpen(nightSleepPeriod = true, inNightWindow = false, v6Active = false, detectorSleeping = true)).isFalse()
    }

    @Test fun `daytime, awake - gate open`() {
        assertThat(boostGateOpen(nightSleepPeriod = false, inNightWindow = false, v6Active = true, detectorSleeping = false)).isTrue()
    }

    // ── Base oref SMB ──

    @Test fun `field case - 1_06 U required, 0_6 U per h basal, 20 min cap - 0_2 U`() {
        val smb = baseOrefSmb(insulinReq = 1.06, iob = 0.278, currentBasal = 0.6, maxUamSmbBasalMinutes = 20,
            maxSmbBasalMinutes = 20, boostInsulinReqPct = 85.0, bolusIncrement = 0.05)
        assertThat(smb).isWithin(1e-9).of(0.2)
    }

    @Test fun `below the cap the dose is insulinReq times the percentage, floored to the increment`() {
        // 0.5 x 0.85 = 0.425 -> 0.40 at 0.05; cap 1.5 x 30 / 60 = 0.75
        val smb = baseOrefSmb(0.5, 0.0, 1.5, 30, 30, 85.0, 0.05)
        assertThat(smb).isWithin(1e-9).of(0.4)
    }

    @Test fun `negative IOB uses the SMB minutes, not the UAM minutes`() {
        // UAM minutes would allow 1.0 U; SMB minutes cap it at 0.3 U
        val smb = baseOrefSmb(2.0, -0.5, 1.0, 60, 18, 100.0, 0.05)
        assertThat(smb).isWithin(1e-9).of(0.3)
    }

    @Test fun `no insulin required - no SMB`() {
        assertThat(baseOrefSmb(0.0, 0.0, 1.0, 30, 30, 85.0, 0.05)).isEqualTo(0.0)
        assertThat(baseOrefSmb(-0.4, 0.0, 1.0, 30, 30, 85.0, 0.05)).isEqualTo(0.0)
    }

    // ── V6 error fallback (audit #9) ──

    @Test fun `V6 unavailable - a tiered V1 dose is capped at base oref`() {
        // The field case's numbers: Tier 5 sized 1.95 U where base oref was 0.2 U.
        assertThat(v6UnavailableSmb(1.95, 0.2)).isWithin(1e-9).of(0.2)
    }

    @Test fun `V6 unavailable - a V1 dose at or below base oref is left alone`() {
        assertThat(v6UnavailableSmb(0.15, 0.2)).isWithin(1e-9).of(0.15)
        assertThat(v6UnavailableSmb(null, 0.2)).isNull()
    }
}
