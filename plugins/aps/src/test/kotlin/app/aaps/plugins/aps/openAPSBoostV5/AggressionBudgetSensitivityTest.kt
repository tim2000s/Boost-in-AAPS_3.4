package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * V6 (2026-06-15) — the previously-unused Sensitivity knob is now a per-user budget multiplier
 * ∈ [0.8, 1.2]. Default 1.0 must be a no-op (regression guard); the budget floor still protects
 * the downside and the knob is clamped. Pure function, tested directly.
 */
class AggressionBudgetSensitivityTest {

    private fun budget(base: Double, sensitivity: Double) =
        aggressionBudget(
            baseInsulinReq = base,
            mlHypoRisk = null,                 // → mlScale 1.0
            inPostExerciseWindow = false,      // → postExScale 1.0
            hypoCautionUserKnob = 1.0,
            sensitivityUserKnob = sensitivity,
        ).budget

    @Test fun `default 1_0 is a no-op`() {
        // base above floor → budget == base
        assertThat(budget(2.0, 1.0)).isWithin(1e-9).of(2.0)
    }

    @Test fun `below 1_0 trims the budget proportionally`() {
        assertThat(budget(2.0, 0.9)).isWithin(1e-9).of(1.8)
    }

    @Test fun `above 1_0 firms the budget proportionally`() {
        assertThat(budget(2.0, 1.2)).isWithin(1e-9).of(2.4)
    }

    @Test fun `knob is clamped to the 0_8 - 1_2 range`() {
        assertThat(budget(2.0, 0.1)).isWithin(1e-9).of(1.6)   // clamped up to 0.8
        assertThat(budget(2.0, 5.0)).isWithin(1e-9).of(2.4)   // clamped down to 1.2
    }

    @Test fun `budget floor still protects the downside`() {
        // base 1.0, sensitivity 0.8 → raw 0.8 still above floor 0.3 → 0.8
        assertThat(budget(1.0, 0.8)).isWithin(1e-9).of(0.8)
        // a tiny base: floor = 0.30 * base dominates regardless of sensitivity
        assertThat(budget(0.1, 0.8)).isWithin(1e-9).of(0.08) // 0.30*0.1=0.03 vs 0.1*0.8=0.08 → 0.08
    }
}
