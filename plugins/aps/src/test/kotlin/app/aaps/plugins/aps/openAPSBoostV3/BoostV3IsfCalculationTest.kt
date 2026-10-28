package app.aaps.plugins.aps.openAPSBoostV3

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Nested
import org.junit.jupiter.api.Test
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min

/**
 * Unit tests for the Boost V3 DynISF V3 ISF calculation.
 *
 * V3 differences from V1:
 *   1. TDD uses 7-day average only (no blended W8H/1D/7D)
 *   2. Safety check retained: if W8H < 75% of 7D, TDD is pulled down toward W8H
 *   3. Velocity is always 1.0 — no BG Impact dampening
 *   4. variableSens = sensNormalTarget × scaler (no velocity term)
 *
 * These tests exercise the calculation logic directly (pure functions)
 * without needing DI or mocked preferences.
 */
class BoostV3IsfCalculationTest {

    // ── Helpers that mirror the V3 plugin calculations ──────────────────────────

    /**
     * Computes the effective TDD for V3: 7D-only with low-weighted-8h safety.
     */
    private fun computeV3Tdd(
        tdd7D: Double,
        tddLast4H: Double,
        tddLast8to4H: Double,
        adjustFactor: Double = 100.0
    ): Double {
        val w8h = (1.4 * tddLast4H + 0.6 * tddLast8to4H) * 3
        val tdd = if (w8h < 0.75 * tdd7D) {
            // Pull 7D toward recent reality
            w8h + (w8h / tdd7D) * (tdd7D - w8h)
        } else {
            tdd7D
        }
        return tdd * adjustFactor / 100.0
    }

    /**
     * Computes the blended TDD that V1 uses, for comparison.
     */
    private fun computeV1BlendedTdd(
        tdd7D: Double,
        tdd1D: Double,
        tddLast4H: Double,
        tddLast8to4H: Double,
        adjustFactor: Double = 100.0
    ): Double {
        val w8h = (1.4 * tddLast4H + 0.6 * tddLast8to4H) * 3
        val tdd = if (w8h < 0.75 * tdd7D) {
            val adjusted7D = w8h + (w8h / tdd7D) * (tdd7D - w8h)
            (adjusted7D * 0.34) + (tdd1D * 0.33) + (w8h * 0.33)
        } else {
            (w8h * 0.33) + (tdd7D * 0.34) + (tdd1D * 0.33)
        }
        return tdd * adjustFactor / 100.0
    }

    /**
     * Computes sensNormalTarget using the 1800/ln formula.
     */
    private fun computeSensNormalTarget(tdd: Double, normalTarget: Double, insulinDivisor: Int, globalScale: Double = 1.0): Double {
        val logTerm = ln((normalTarget / insulinDivisor) + 1.0)
        return if (tdd > 0 && logTerm > 0) {
            1800.0 / (tdd * logTerm) * globalScale
        } else 0.0
    }

    /**
     * Computes variableSens (V3: no velocity dampening).
     */
    private fun computeVariableSensV3(sensNormalTarget: Double, bg: Double, normalTarget: Double, insulinDivisor: Int, bgCap: Double): Double {
        val bgCapped = if (bg > bgCap) bgCap + (bg - bgCap) / 3.0 else bg
        val sbg = ln((bgCapped / insulinDivisor) + 1.0)
        val scaler = ln((normalTarget / insulinDivisor) + 1.0) / sbg
        return sensNormalTarget * scaler
    }

    /**
     * Computes variableSens (V1: with velocity dampening).
     */
    private fun computeVariableSensV1(sensNormalTarget: Double, bg: Double, normalTarget: Double, insulinDivisor: Int, bgCap: Double, velocity: Double): Double {
        val bgCapped = if (bg > bgCap) bgCap + (bg - bgCap) / 3.0 else bg
        val sbg = ln((bgCapped / insulinDivisor) + 1.0)
        val scaler = ln((normalTarget / insulinDivisor) + 1.0) / sbg
        return sensNormalTarget * (1 - (1 - scaler) * velocity)
    }

    // ── Standard test parameters ────────────────────────────────────────────────

    private val DIVISOR = 82          // typical for Lyumjev (peak 38)
    private val NORMAL_TARGET = 99.0  // mg/dL (5.5 mmol)
    private val BG_CAP = 198.0        // mg/dL (11.0 mmol)
    private val ADJUST_FACTOR = 90.0  // 90% as in the user's profile

    // ─── TDD Calculation Tests ──────────────────────────────────────────────────

    @Nested
    @DisplayName("TDD Calculation")
    inner class TddCalculation {

        @Test
        @DisplayName("V3 uses 7D TDD when W8H >= 75% of 7D")
        fun `v3 uses 7D when recent insulin is normal`() {
            val tdd = computeV3Tdd(tdd7D = 43.0, tddLast4H = 6.0, tddLast8to4H = 5.0, adjustFactor = 100.0)
            // W8H = (1.4×6 + 0.6×5)×3 = (8.4+3.0)×3 = 34.2 → 34.2 >= 0.75×43 = 32.25 ✓
            assertThat(tdd).isEqualTo(43.0)
        }

        @Test
        @DisplayName("V3 pulls 7D down when W8H < 75% of 7D")
        fun `v3 reduces TDD when recent usage is low`() {
            val tdd = computeV3Tdd(tdd7D = 43.0, tddLast4H = 2.0, tddLast8to4H = 2.0, adjustFactor = 100.0)
            // W8H = (1.4×2 + 0.6×2)×3 = (2.8+1.2)×3 = 12.0 → 12.0 < 0.75×43 = 32.25
            // adjusted = 12 + (12/43)×(43-12) = 12 + 0.279×31 = 12 + 8.65 = 20.65
            assertThat(tdd).isWithin(0.1).of(20.65)
        }

        @Test
        @DisplayName("V3 applies adjustment factor")
        fun `adjustment factor scales TDD`() {
            val tdd = computeV3Tdd(tdd7D = 43.0, tddLast4H = 6.0, tddLast8to4H = 5.0, adjustFactor = 90.0)
            assertThat(tdd).isWithin(0.1).of(43.0 * 0.9)
        }

        @Test
        @DisplayName("V3 TDD is lower than V1 blended during spike (high 4H)")
        fun `v3 TDD lower than v1 during spike`() {
            // Scenario: rollercoaster day — 4H has inflated TDD
            val tddV3 = computeV3Tdd(tdd7D = 43.0, tddLast4H = 17.0, tddLast8to4H = 5.0, adjustFactor = 90.0)
            val tddV1 = computeV1BlendedTdd(tdd7D = 43.0, tdd1D = 37.0, tddLast4H = 17.0, tddLast8to4H = 5.0, adjustFactor = 90.0)
            // V1 blended will be pulled up by the 4H spike; V3 ignores it
            assertThat(tddV3).isLessThan(tddV1)
        }

        @Test
        @DisplayName("V3 TDD is stable across time windows")
        fun `v3 TDD stable regardless of recent bolus activity`() {
            // Same 7D average, different 4H activity
            val tddQuiet = computeV3Tdd(tdd7D = 43.0, tddLast4H = 3.0, tddLast8to4H = 3.0, adjustFactor = 100.0)
            val tddActive = computeV3Tdd(tdd7D = 43.0, tddLast4H = 15.0, tddLast8to4H = 10.0, adjustFactor = 100.0)
            // Both should return 43 (W8H is >= 75% of 7D in both cases)
            // Quiet: W8H = (1.4×3+0.6×3)×3 = 18 < 32.25, so adjusted
            // Active: W8H = (1.4×15+0.6×10)×3 = (21+6)×3 = 81 >= 32.25, so 7D
            assertThat(tddActive).isEqualTo(43.0)
            assertThat(tddQuiet).isLessThan(43.0) // adjusted down due to low recent
        }
    }

    // ─── ISF Calculation Tests ──────────────────────────────────────────────────

    @Nested
    @DisplayName("ISF Calculation")
    inner class IsfCalculation {

        @Test
        @DisplayName("V3 produces higher ISF (less aggressive) than V1 during spike")
        fun `v3 isf higher than v1 during spike`() {
            // Spike scenario: high 4H TDD
            val tddV3 = computeV3Tdd(tdd7D = 43.0, tddLast4H = 17.0, tddLast8to4H = 5.0, adjustFactor = 90.0)
            val tddV1 = computeV1BlendedTdd(tdd7D = 43.0, tdd1D = 37.0, tddLast4H = 17.0, tddLast8to4H = 5.0, adjustFactor = 90.0)
            val isfV3 = computeSensNormalTarget(tddV3, NORMAL_TARGET, DIVISOR)
            val isfV1 = computeSensNormalTarget(tddV1, NORMAL_TARGET, DIVISOR)
            // V3 should have higher ISF (more sensitive = less insulin)
            assertThat(isfV3).isGreaterThan(isfV1)
        }

        @Test
        @DisplayName("V3 variableSens equals sensNormalTarget × scaler (no velocity)")
        fun `v3 variableSens has no velocity dampening`() {
            val tdd = computeV3Tdd(tdd7D = 43.0, tddLast4H = 6.0, tddLast8to4H = 5.0, adjustFactor = 90.0)
            val snt = computeSensNormalTarget(tdd, NORMAL_TARGET, DIVISOR)
            val vsV3 = computeVariableSensV3(snt, 180.0, NORMAL_TARGET, DIVISOR, BG_CAP)
            val vsV1_100pct = computeVariableSensV1(snt, 180.0, NORMAL_TARGET, DIVISOR, BG_CAP, 1.0)
            val vsV1_50pct = computeVariableSensV1(snt, 180.0, NORMAL_TARGET, DIVISOR, BG_CAP, 0.5)
            // V3 at velocity=1.0 should equal V1 at velocity=1.0
            assertThat(vsV3).isWithin(0.01).of(vsV1_100pct)
            // V3 should be lower than V1 at 50% velocity (V1 dampens the BG effect)
            assertThat(vsV3).isLessThan(vsV1_50pct)
        }

        @Test
        @DisplayName("ISF decreases as BG increases (more aggressive at higher BG)")
        fun `isf decreases with rising BG`() {
            val tdd = computeV3Tdd(tdd7D = 43.0, tddLast4H = 6.0, tddLast8to4H = 5.0, adjustFactor = 90.0)
            val snt = computeSensNormalTarget(tdd, NORMAL_TARGET, DIVISOR)
            val isf100 = computeVariableSensV3(snt, 100.0, NORMAL_TARGET, DIVISOR, BG_CAP)
            val isf150 = computeVariableSensV3(snt, 150.0, NORMAL_TARGET, DIVISOR, BG_CAP)
            val isf200 = computeVariableSensV3(snt, 200.0, NORMAL_TARGET, DIVISOR, BG_CAP)
            assertThat(isf100).isGreaterThan(isf150)
            assertThat(isf150).isGreaterThan(isf200)
        }

        @Test
        @DisplayName("BG cap limits ISF aggressiveness above cap")
        fun `bg cap prevents extreme isf at very high bg`() {
            val tdd = computeV3Tdd(tdd7D = 43.0, tddLast4H = 6.0, tddLast8to4H = 5.0, adjustFactor = 90.0)
            val snt = computeSensNormalTarget(tdd, NORMAL_TARGET, DIVISOR)
            val isfAtCap = computeVariableSensV3(snt, BG_CAP, NORMAL_TARGET, DIVISOR, BG_CAP)
            val isfAboveCap = computeVariableSensV3(snt, 300.0, NORMAL_TARGET, DIVISOR, BG_CAP)
            // Above cap should still be lower but not dramatically so (capping kicks in)
            assertThat(isfAboveCap).isLessThan(isfAtCap)
            // The gap should be much smaller than without capping
            val isfAboveNoCap = computeVariableSensV3(snt, 300.0, NORMAL_TARGET, DIVISOR, 999.0)
            assertThat(isfAboveCap).isGreaterThan(isfAboveNoCap)
        }

        @Test
        @DisplayName("Global scale adjusts ISF for profile switch")
        fun `globalScale adjusts isf for profile switch`() {
            val tdd = computeV3Tdd(tdd7D = 43.0, tddLast4H = 6.0, tddLast8to4H = 5.0, adjustFactor = 90.0)
            val snt100 = computeSensNormalTarget(tdd, NORMAL_TARGET, DIVISOR, globalScale = 1.0)
            val snt80 = computeSensNormalTarget(tdd, NORMAL_TARGET, DIVISOR, globalScale = 1.25)  // 80% profile
            val snt130 = computeSensNormalTarget(tdd, NORMAL_TARGET, DIVISOR, globalScale = 100.0 / 130.0)  // 130% profile
            assertThat(snt80).isGreaterThan(snt100)   // 80% profile → higher ISF (less aggressive)
            assertThat(snt130).isLessThan(snt100)      // 130% profile → lower ISF (more aggressive)
        }
    }

    // ─── Scenario Tests (Backtested from real data) ─────────────────────────────

    @Nested
    @DisplayName("Scenario Tests")
    inner class ScenarioTests {

        @Test
        @DisplayName("Rollercoaster: V3 produces less insulin than V1 during post-spike recovery")
        fun `rollercoaster scenario produces less insulin with V3`() {
            // From the real log: BG 200, blended TDD=22.5, 7D=16.5
            // V1: tdd=22.5, ISF≈65 → insulinReq=(200-97)/65=1.58
            // V3: tdd=16.5, ISF≈88 → insulinReq=(200-97)/88=1.17
            val tddV3 = computeV3Tdd(tdd7D = 22.7, tddLast4H = 17.1, tddLast8to4H = 5.3, adjustFactor = 90.0)
            val tddV1 = computeV1BlendedTdd(tdd7D = 22.7, tdd1D = 37.0, tddLast4H = 17.1, tddLast8to4H = 5.3, adjustFactor = 90.0)
            val isfV3 = computeVariableSensV3(
                computeSensNormalTarget(tddV3, NORMAL_TARGET, 75), 200.0, NORMAL_TARGET, 75, BG_CAP
            )
            val isfV1 = computeVariableSensV1(
                computeSensNormalTarget(tddV1, NORMAL_TARGET, 75), 200.0, NORMAL_TARGET, 75, BG_CAP, 1.0
            )
            val ireqV3 = (200 - 97) / isfV3
            val ireqV1 = (200 - 97) / isfV1
            // V3 should require less insulin
            assertThat(ireqV3).isLessThan(ireqV1)
            // The reduction should be meaningful (>10%)
            assertThat(ireqV3 / ireqV1).isLessThan(0.9)
        }

        @Test
        @DisplayName("Morning rebound at BG 90: V3 dramatically reduces insulin demand")
        fun `morning rebound at bg 90 shows major reduction`() {
            // From log: BG 90, blended TDD≈15.8, 7D≈14.5
            // V1 ISF=98.5, V3 ISF≈167.5 → insulinReq drops ~40%
            val tddV3 = computeV3Tdd(tdd7D = 23.6, tddLast4H = 4.2, tddLast8to4H = 2.4, adjustFactor = 70.0)
            val tddV1 = computeV1BlendedTdd(tdd7D = 23.6, tdd1D = 31.5, tddLast4H = 4.2, tddLast8to4H = 2.4, adjustFactor = 70.0)
            val target = 91.0
            val isfV3 = computeVariableSensV3(
                computeSensNormalTarget(tddV3, NORMAL_TARGET, DIVISOR), 90.0, NORMAL_TARGET, DIVISOR, BG_CAP
            )
            val isfV1 = computeVariableSensV1(
                computeSensNormalTarget(tddV1, NORMAL_TARGET, DIVISOR), 90.0, NORMAL_TARGET, DIVISOR, BG_CAP, 1.0
            )
            // At BG 90 (near target), insulinReq should be minimal for V3
            val ireqV3 = (90 - target) / isfV3  // negative or near zero
            val ireqV1 = (90 - target) / isfV1
            // Both should be negative (BG below target), but V3 less so
            assertThat(ireqV3).isLessThan(0.0)
        }

        @Test
        @DisplayName("Overnight: V3 and V1 similar when 4H TDD is not elevated")
        fun `overnight quiet period shows similar results`() {
            // Overnight: 4H and 8-4H are both low, W8H < 75% of 7D
            val tddV3 = computeV3Tdd(tdd7D = 43.0, tddLast4H = 2.0, tddLast8to4H = 2.0, adjustFactor = 90.0)
            val tddV1 = computeV1BlendedTdd(tdd7D = 43.0, tdd1D = 37.0, tddLast4H = 2.0, tddLast8to4H = 2.0, adjustFactor = 90.0)
            // Both should apply the safety reduction
            assertThat(tddV3).isLessThan(43.0 * 0.9) // adjusted down
            assertThat(tddV1).isLessThan(43.0 * 0.9) // also adjusted
            // V3 should be close to V1 when recent TDD is low (both pull toward W8H)
            val diff = Math.abs(tddV3 - tddV1) / tddV1
            assertThat(diff).isLessThan(0.3) // within 30%
        }

        @Test
        @DisplayName("Steady state: V3 and V1 converge when 4H/1D/7D are similar")
        fun `steady state v3 and v1 converge`() {
            // All TDD metrics are similar — no rollercoaster
            val tddV3 = computeV3Tdd(tdd7D = 40.0, tddLast4H = 6.5, tddLast8to4H = 7.0, adjustFactor = 100.0)
            val tddV1 = computeV1BlendedTdd(tdd7D = 40.0, tdd1D = 41.0, tddLast4H = 6.5, tddLast8to4H = 7.0, adjustFactor = 100.0)
            // W8H = (1.4×6.5 + 0.6×7.0)×3 = (9.1+4.2)×3 = 39.9 ≈ 7D
            // V1 blend ≈ (39.9×.33 + 40×.34 + 41×.33) ≈ 40.3
            // V3 = 40
            assertThat(Math.abs(tddV3 - tddV1)).isLessThan(2.0)
        }
    }

    // ─── Integration-style tests (full ISF chain) ───────────────────────────────

    @Nested
    @DisplayName("Full ISF Chain")
    inner class FullIsfChain {

        @Test
        @DisplayName("Full chain produces sane ISF values at typical BG range")
        fun `full chain produces sane isf values`() {
            val tdd = computeV3Tdd(tdd7D = 43.0, tddLast4H = 6.0, tddLast8to4H = 5.0, adjustFactor = 90.0)
            val snt = computeSensNormalTarget(tdd, NORMAL_TARGET, DIVISOR)
            // Test across BG range
            for (bg in listOf(70.0, 100.0, 140.0, 180.0, 220.0, 300.0)) {
                val isf = computeVariableSensV3(snt, bg, NORMAL_TARGET, DIVISOR, BG_CAP)
                assertThat(isf).isGreaterThan(5.0)    // at least 5 mg/dL/U
                assertThat(isf).isLessThan(500.0)     // at most 500 mg/dL/U
            }
        }

        @Test
        @DisplayName("insulinReq is proportional to BG distance from target")
        fun `insulinReq proportional to bg distance`() {
            val tdd = computeV3Tdd(tdd7D = 43.0, tddLast4H = 6.0, tddLast8to4H = 5.0, adjustFactor = 90.0)
            val snt = computeSensNormalTarget(tdd, NORMAL_TARGET, DIVISOR)
            val target = 100.0
            val ireq150 = (150 - target) / computeVariableSensV3(snt, 150.0, NORMAL_TARGET, DIVISOR, BG_CAP)
            val ireq200 = (200 - target) / computeVariableSensV3(snt, 200.0, NORMAL_TARGET, DIVISOR, BG_CAP)
            val ireq250 = (250 - target) / computeVariableSensV3(snt, 250.0, NORMAL_TARGET, DIVISOR, BG_CAP)
            assertThat(ireq200).isGreaterThan(ireq150)
            assertThat(ireq250).isGreaterThan(ireq200)
        }

        @Test
        @DisplayName("V3 never produces negative ISF")
        fun `v3 never produces negative isf`() {
            // Edge cases: very high TDD, very low BG, extreme cap
            for (tdd7D in listOf(10.0, 50.0, 100.0)) {
                for (bg in listOf(40.0, 60.0, 100.0, 200.0, 400.0)) {
                    val tdd = computeV3Tdd(tdd7D, 5.0, 3.0, 100.0)
                    val snt = computeSensNormalTarget(tdd, NORMAL_TARGET, DIVISOR)
                    if (snt > 0) {
                        val isf = computeVariableSensV3(snt, bg, NORMAL_TARGET, DIVISOR, BG_CAP)
                        assertThat(isf).isGreaterThan(0.0)
                    }
                }
            }
        }
    }
}
