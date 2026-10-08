package app.aaps.plugins.aps.openAPSBoost

import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.boostGateOpen
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
}
