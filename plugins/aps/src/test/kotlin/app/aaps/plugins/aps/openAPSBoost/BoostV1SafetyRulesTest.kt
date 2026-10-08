package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import com.google.common.truth.Truth.assertWithMessage
import org.junit.jupiter.api.Test

/**
 * Worked numbers for the V1 dose-path rules in BoostV1SafetyRules.kt (audit of 8 October 2026,
 * items 4, 5, 19 and 20). BoostV1SafetyEngineTest covers the same rules through determine_basal.
 */
class BoostV1SafetyRulesTest {

    /** The divisor as determine_basal composes it: insulinReq% divisor minus the reduction. */
    private fun mainDivisor(bg: Double, insulinReqPercent: Double, percentScale: Double): Double {
        val pct = 100.0 / insulinReqPercent
        val scalePct = Math.round(100.0 / percentScale * 1000) / 1000.0
        return pct - boostPercentScaleReduction(bg, pct - scalePct)
    }

    private fun tier6Divisor(bg: Double, insulinReqPercent: Double, percentScale: Double?): Double {
        val pct = 100.0 / insulinReqPercent
        val scalePct = if (percentScale == null) pct else Math.round(100.0 / percentScale * 1000) / 1000.0
        return pct - boostPercentScaleReduction(bg, pct - (2 * scalePct))
    }

    // insulinReq% 50 (divisor 2.0), percent scale 200 (0.5). Old: 0.750, 2.000, 1.167, 0.333, -0.083.
    @Test fun `divisor at insulinReq 50 percent and percent scale 200`() {
        val expected = mapOf(120.0 to 0.75, 180.0 to 2.0, 220.0 to 2.0, 260.0 to 2.0, 280.0 to 2.0)
        for ((bg, d) in expected) assertWithMessage("bg $bg").that(mainDivisor(bg, 50.0, 200.0)).isWithin(1e-3).of(d)
    }

    // insulinReq% 85 (1.176), percent scale 250 (0.4). Old: 0.529, 1.176, 0.745, 0.314, 0.098 (a 10x dose at 280).
    @Test fun `divisor at insulinReq 85 percent and percent scale 250`() {
        val expected = mapOf(120.0 to 0.5294, 180.0 to 1.1765, 220.0 to 1.1765, 260.0 to 1.1765, 280.0 to 1.1765)
        for ((bg, d) in expected) assertWithMessage("bg $bg").that(mainDivisor(bg, 85.0, 250.0)).isWithin(1e-3).of(d)
    }

    // insulinReq% 85, percent scale 200 and insulinReq% 50, percent scale 250 at the same points.
    @Test fun `divisor at the other two setting pairs`() {
        val a = mapOf(120.0 to 0.6127, 180.0 to 1.1765, 220.0 to 1.1765, 260.0 to 1.1765, 280.0 to 1.1765)
        for ((bg, d) in a) assertWithMessage("85/200 bg $bg").that(mainDivisor(bg, 85.0, 200.0)).isWithin(1e-3).of(d)
        val b = mapOf(120.0 to 0.6667, 180.0 to 2.0, 220.0 to 2.0, 260.0 to 2.0, 280.0 to 2.0)
        for ((bg, d) in b) assertWithMessage("50/250 bg $bg").that(mainDivisor(bg, 50.0, 250.0)).isWithin(1e-3).of(d)
    }

    // The old divisor crossed zero at 180 + 72 x pct / (pct - scalePct): 276 mg/dL at 50/200, 289 at 85/250.
    @Test fun `divisor never reaches zero or below above 180`() {
        for (bg in 181..400) {
            assertWithMessage("50/200 bg $bg").that(mainDivisor(bg.toDouble(), 50.0, 200.0)).isAtLeast(2.0)
            assertWithMessage("85/250 bg $bg").that(mainDivisor(bg.toDouble(), 85.0, 250.0)).isAtLeast(100.0 / 85.0)
        }
    }

    // Tier 5 runs 110 to 180 mg/dL: the reduction there is the original abs(bg - 180) / 72 x slope.
    @Test fun `at and below 180 the reduction is the original formula`() {
        for (bg in 108..180) {
            val slope = 100.0 / 85.0 - 0.4
            assertThat(boostPercentScaleReduction(bg.toDouble(), slope)).isWithin(1e-12).of(Math.abs(bg - 180.0) / 72 * slope)
        }
    }

    // Tier 6 at 85/250: old 0.967 at 220, 0.758 at 260, 0.654 at 280; now 1.176 above 180.
    @Test fun `tier 6 divisor holds at the 180 value above 180`() {
        assertThat(tier6Divisor(120.0, 85.0, 250.0)).isWithin(1e-3).of(0.8627)
        for (bg in listOf(220.0, 260.0, 280.0)) assertThat(tier6Divisor(bg, 85.0, 250.0)).isWithin(1e-3).of(1.1765)
    }

    // Tier 6 with percent scale off passes slope -pct, so its divisor grows above 180 (the conservative
    // direction). That is kept: at 85% and 260 mg/dL it is 1.176 x (1 + 80/72) = 2.484.
    @Test fun `a divisor that grows above 180 is left as it was`() {
        assertThat(tier6Divisor(260.0, 85.0, null)).isWithin(1e-3).of(1.17647 * (1 + 80.0 / 72))
        // percent scale below insulinReq%: 85% and 70% (scalePct 1.429 > pct 1.176), slope negative.
        assertThat(mainDivisor(260.0, 85.0, 70.0)).isWithin(1e-3).of(1.17647 - (80.0 / 72) * (1.17647 - 1.429))
    }

    // Item 5: max_iob 3.0, IOB 2.0 leave 1.0 U; IOB 2.73 leaves 0.27, floored to 0.25 at 0.05 U.
    @Test fun `SMB is clamped to the max_iob headroom and floored to the increment`() {
        assertThat(boostSmbWithinMaxIob(2.5, 3.0, 2.0, 0.05)).isWithin(1e-9).of(1.0)
        assertThat(boostSmbWithinMaxIob(2.5, 3.0, 2.73, 0.05)).isWithin(1e-9).of(0.25)
        assertThat(boostSmbWithinMaxIob(2.5, 3.0, 2.73, 0.1)).isWithin(1e-9).of(0.2)
    }

    @Test fun `SMB inside the headroom is returned unchanged`() {
        assertThat(boostSmbWithinMaxIob(0.65, 3.0, 2.0, 0.05)).isEqualTo(0.65)
        assertThat(boostSmbWithinMaxIob(1.0, 3.0, 2.0, 0.05)).isEqualTo(1.0)
        assertThat(boostSmbWithinMaxIob(0.0, 3.0, 2.0, 0.05)).isEqualTo(0.0)
    }

    @Test fun `no headroom gives no SMB`() {
        assertThat(boostSmbWithinMaxIob(0.5, 3.0, 3.0, 0.05)).isEqualTo(0.0)
        assertThat(boostSmbWithinMaxIob(0.5, 3.0, 3.4, 0.05)).isEqualTo(0.0)
        assertThat(boostSmbWithinMaxIob(0.5, Double.NaN, 1.0, 0.05)).isEqualTo(0.0)
    }

    // Item 19: the hold no longer depends on a recent low. The three remaining conditions are unchanged.
    @Test fun `G3 hold conditions`() {
        assertThat(boostG3HoldConditionsMet(0.0, 6.0, 4.0)).isTrue()
        assertThat(boostG3HoldConditionsMet(1.0, 6.0, 4.0)).isFalse()
        assertThat(boostG3HoldConditionsMet(0.0, 4.9, 4.0)).isFalse()
        assertThat(boostG3HoldConditionsMet(0.0, 6.0, 2.9)).isFalse()
    }

    // Item 20.
    @Test fun `spike override only on tier 8 and never in the post-rescue window or under ML downgrade`() {
        assertThat(boostSpikeOverrideAllowed(true, "REGULAR_OREF1", false, false)).isTrue()
        assertThat(boostSpikeOverrideAllowed(false, "REGULAR_OREF1", false, false)).isFalse()
        assertThat(boostSpikeOverrideAllowed(true, "REGULAR_OREF1", true, false)).isFalse()
        assertThat(boostSpikeOverrideAllowed(true, "REGULAR_OREF1", false, true)).isFalse()
        for (t in listOf("ACCELERATION", "ENHANCED_OREF1", "UAM_BOOST", "PERCENT_SCALE", "COB_PRIMARY", "NONE", null))
            assertWithMessage("tier $t").that(boostSpikeOverrideAllowed(true, t, false, false)).isFalse()
    }
}
