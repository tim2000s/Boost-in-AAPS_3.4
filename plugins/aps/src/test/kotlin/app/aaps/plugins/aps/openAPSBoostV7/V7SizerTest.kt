package app.aaps.plugins.aps.openAPSBoostV7

import app.aaps.plugins.aps.openAPSBoostV5.MealHypothesis
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * V7Sizer — the revised distributional-sizing rule (shadow-only).
 *
 * The headline test is acceptance criterion (a) from the foundation report
 * (`backtesting/reports/2026-07_v7_foundation_REPORT.md` §VERDICT): on a synthetic DEBIASED
 * pool whose q5 shoulder projects below 70, cost-ratio sensitivity MUST appear — the offline
 * 3-point formulation was structurally incapable of it (R×1 > 3 high-side quantiles the moment
 * any quantile crossed 70). Expected doses are pinned from an independent replication of the
 * interpolated-CDF math (19 equal-probability points over the 5/25/50/75/95 knots).
 *
 * The bounds tests replay 03_distributional_sizing.py's guard structure: state-multiplier
 * envelope, committedCap/confirmedCap, non-meal v1-bound, post-rescue exclusion, cumulative-cap
 * awareness, budget ≤ 0 ⇒ 0, and abstention on missing inputs.
 */
class V7SizerTest {

    /** Debiased synthetic pool: median 0 (criterion b satisfied), wide validated shoulders. */
    private val debiased = doubleArrayOf(-80.0, -20.0, 0.0, 30.0, 90.0)

    /** User A's 30d h=60 quantiles from the report §1 — the biased field pathology. */
    private val biased = doubleArrayOf(-15.0, 9.0, 31.0, 63.0, 122.0)

    private fun inputs(
        bg: Double = 200.0,
        base60: Double = bg,
        sens: Double = 80.0,
        state: MealHypothesis? = MealHypothesis.CONFIRMED,
        budgetU: Double? = 2.0,
        committedCapU: Double = 0.5,
        confirmedCapU: Double = 3.0,
        v1WouldDoseU: Double? = null,
        postRescueWindow: Boolean = false,
        cumulativeCapU: Double = 0.0,
        smbVol60MinU: Double = 0.0,
        quantiles: DoubleArray = debiased,
    ) = V7Sizer.Inputs(
        bg = bg, base60 = base60, sens = sens, state = state, budgetU = budgetU,
        committedCapU = committedCapU, confirmedCapU = confirmedCapU,
        v1WouldDoseU = v1WouldDoseU, postRescueWindow = postRescueWindow,
        cumulativeCapU = cumulativeCapU, smbVol60MinU = smbVol60MinU,
        residualQuantiles = quantiles,
    )

    // ── Acceptance criterion (a): cost-ratio sensitivity on a debiased pool ─────────────────────

    @Test fun `R-sensitivity APPEARS on a debiased pool whose q5 shoulder projects below 70`() {
        // bg 200, sens 80 (F_ACT 0.5 → 40 mg/dL per U), q5 = −80: the left shoulder crosses 70
        // as the dose grows, so the R-weighted low arm binds at different doses per R.
        val r = V7Sizer.size(inputs())!!
        assertThat(r.doseR4).isWithin(1e-9).of(1.65)
        assertThat(r.doseR7).isWithin(1e-9).of(1.60)
        assertThat(r.doseR10).isWithin(1e-9).of(1.40)
        // The criterion itself: strictly more caution as the low-side cost ratio rises.
        assertThat(r.doseR4).isGreaterThan(r.doseR7)
        assertThat(r.doseR7).isGreaterThan(r.doseR10)
        assertThat(r.dosesDiffer).isTrue()
    }

    @Test fun `the offline pathology reproduces - a biased pool rides the envelope identically at every R`() {
        // Report §3 finding 1: with every projection shifted +30ish, the q25 shoulder never
        // projects <70 and the rule doses to the envelope — the safety knob does nothing.
        val r = V7Sizer.size(inputs(bg = 160.0, sens = 50.0, quantiles = biased))!!
        assertThat(r.doseR4).isWithin(1e-9).of(3.0)   // = min(budget 2.0 × 1.8, confirmedCap 3.0, grid 3.0)
        assertThat(r.doseR7).isWithin(1e-9).of(3.0)
        assertThat(r.doseR10).isWithin(1e-9).of(3.0)
        assertThat(r.dosesDiffer).isFalse()
    }

    // ── Bounds (03's guard structure, bounds-not-gates) ─────────────────────────────────────────

    @Test fun `confirmedCap bounds the CONFIRMED envelope`() {
        val r = V7Sizer.size(inputs(confirmedCapU = 0.4))!!
        assertThat(r.envelopeU).isWithin(1e-9).of(0.4)
        assertThat(r.doses.toList()).containsExactly(0.4, 0.4, 0.4).inOrder() // optimum ≥ 1.4 ∀R → all cap-bound
    }

    @Test fun `committedCap bounds the COMMITTED envelope`() {
        val r = V7Sizer.size(inputs(state = MealHypothesis.COMMITTED, committedCapU = 0.5))!!
        assertThat(r.envelopeU).isWithin(1e-9).of(0.5)  // min(budget 2.0 × 1.0, cap 0.5)
        assertThat(r.doses.all { it <= 0.5 + 1e-9 }).isTrue()
    }

    @Test fun `non-meal states are v1-bound - IDLE with v1WouldDose 0_15 doses at most 0_15`() {
        val r = V7Sizer.size(inputs(state = MealHypothesis.IDLE, v1WouldDoseU = 0.15))!!
        assertThat(r.envelopeU).isWithin(1e-9).of(0.15)
        assertThat(r.doses.toList()).containsExactly(0.15, 0.15, 0.15).inOrder()
    }

    @Test fun `non-meal with NO v1 dose available bounds to zero - fail closed like 03's fillna(0)`() {
        val r = V7Sizer.size(inputs(state = MealHypothesis.RECOVERING, v1WouldDoseU = null))!!
        assertThat(r.envelopeU).isWithin(1e-9).of(0.0)
        assertThat(r.doses.toList()).containsExactly(0.0, 0.0, 0.0).inOrder()
    }

    @Test fun `post-rescue window suppresses the meal-state exemption - COMMITTED is v1-bound too`() {
        val r = V7Sizer.size(inputs(state = MealHypothesis.COMMITTED, postRescueWindow = true, v1WouldDoseU = 0.1))!!
        assertThat(r.envelopeU).isWithin(1e-9).of(0.1)
        assertThat(r.doses.all { it <= 0.1 + 1e-9 }).isTrue()
    }

    @Test fun `cumulative-cap awareness - only the remaining 60-min headroom is grantable`() {
        val r = V7Sizer.size(inputs(cumulativeCapU = 1.0, smbVol60MinU = 0.9))!!
        assertThat(r.envelopeU).isWithin(1e-9).of(0.1)
        // Cap disabled (≤ 0) → no bound from it.
        val unbounded = V7Sizer.size(inputs(cumulativeCapU = 0.0, smbVol60MinU = 5.0))!!
        assertThat(unbounded.envelopeU).isWithin(1e-9).of(3.0)
    }

    @Test fun `budget zero or negative doses zero - restraint preserved by construction`() {
        for (budget in listOf(0.0, -0.2)) {
            val r = V7Sizer.size(inputs(budgetU = budget))!!
            assertThat(r.envelopeU).isWithin(1e-9).of(0.0)
            assertThat(r.doses.toList()).containsExactly(0.0, 0.0, 0.0).inOrder()
        }
    }

    @Test fun `abstains (null) on missing state, budget, or unusable sens`() {
        assertThat(V7Sizer.size(inputs(state = null))).isNull()
        assertThat(V7Sizer.size(inputs(budgetU = null))).isNull()
        assertThat(V7Sizer.size(inputs(sens = 0.0))).isNull()
        assertThat(V7Sizer.size(inputs(sens = Double.NaN))).isNull()
        assertThat(V7Sizer.size(inputs(quantiles = doubleArrayOf(1.0, 2.0)))).isNull()
        assertThat(V7Sizer.size(inputs(quantiles = doubleArrayOf(1.0, 2.0, Double.NaN, 4.0, 5.0)))).isNull()
    }

    // ── pLow (display-only left shoulder) ───────────────────────────────────────────────────────

    @Test fun `pLow interpolates the piecewise-linear CDF between the validated knots`() {
        val q90 = doubleArrayOf(-45.0, -15.0, 0.0, 15.0, 45.0)
        // base90 100 → threshold 70−100 = −30, halfway between q5(−45) and q25(−15) → p 0.15.
        assertThat(V7Sizer.pLow(100.0, q90)!!).isWithin(1e-9).of(0.15)
    }

    @Test fun `pLow truncates left of the 5 pct knot - the unfittable tail reads zero`() {
        val q90 = doubleArrayOf(-45.0, -15.0, 0.0, 15.0, 45.0)
        assertThat(V7Sizer.pLow(200.0, q90)!!).isWithin(1e-9).of(0.0)   // threshold −130 < q5
        assertThat(V7Sizer.pLow(25.0, q90)!!).isWithin(1e-9).of(1.0)    // threshold 45 ≥ q95
    }
}
