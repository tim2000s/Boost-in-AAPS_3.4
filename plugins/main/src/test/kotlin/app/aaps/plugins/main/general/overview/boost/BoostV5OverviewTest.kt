package app.aaps.plugins.main.general.overview.boost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Pure-function tests for the V5 overview model: the `boostV5_gateReduction` parser and the
 * state-name mapping. No engine/DI dependencies — both are static.
 */
class BoostV5OverviewTest {

    // --- gateReduction parser ---

    @Test fun `null empty and none yield no brakes`() {
        assertThat(BoostOverviewHelper.parseGateReductions(null)).isEmpty()
        assertThat(BoostOverviewHelper.parseGateReductions("")).isEmpty()
        assertThat(BoostOverviewHelper.parseGateReductions("none")).isEmpty()
        assertThat(BoostOverviewHelper.parseGateReductions("none,none")).isEmpty()
    }

    @Test fun `soft brakes that did not bite are dropped`() {
        // sensor:1.00 is a no-op; only the two that actually reduced should surface
        val brakes = BoostOverviewHelper.parseGateReductions("iobHeadroom:0.85,decel:0.50,sensor:1.00,none")
        assertThat(brakes.map { it.label }).containsExactly("decel", "iobHeadroom").inOrder() // strongest (lowest factor) first
        assertThat(brakes.none { it.isHard }).isTrue()
    }

    @Test fun `hard gate is flagged and sorts first`() {
        val brakes = BoostOverviewHelper.parseGateReductions("iobHeadroom:0.85,HARD:min_guard_bg")
        assertThat(brakes.first().isHard).isTrue()
        assertThat(brakes.first().label).isEqualTo("min_guard_bg")
        assertThat(brakes.last().label).isEqualTo("iobHeadroom")
    }

    @Test fun `maxIOB and spike clamps are hard`() {
        val brakes = BoostOverviewHelper.parseGateReductions("maxIOB,spike")
        assertThat(brakes).hasSize(2)
        assertThat(brakes.all { it.isHard }).isTrue()
    }

    // --- state mapping ---

    @Test fun `state names map case-insensitively, unknown falls back to IDLE`() {
        assertThat(BoostOverviewHelper.BoostV5State.fromName("CONFIRMED")).isEqualTo(BoostOverviewHelper.BoostV5State.CONFIRMED)
        assertThat(BoostOverviewHelper.BoostV5State.fromName("recovering")).isEqualTo(BoostOverviewHelper.BoostV5State.RECOVERING)
        assertThat(BoostOverviewHelper.BoostV5State.fromName(null)).isEqualTo(BoostOverviewHelper.BoostV5State.IDLE)
        assertThat(BoostOverviewHelper.BoostV5State.fromName("garbage")).isEqualTo(BoostOverviewHelper.BoostV5State.IDLE)
    }

    @Test fun `every state has a distinct short label and colour`() {
        val states = BoostOverviewHelper.BoostV5State.entries
        assertThat(states.map { it.short }.toSet()).hasSize(states.size)
        assertThat(states.map { it.colorHex }.toSet()).hasSize(states.size)
    }
}
