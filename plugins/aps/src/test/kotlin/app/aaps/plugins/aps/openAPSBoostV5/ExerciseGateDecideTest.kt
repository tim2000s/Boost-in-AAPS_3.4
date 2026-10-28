package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * F2 (2026-07-07) — V5-level proof that the exercise inputs actually gate dosing behaviour when
 * the profile fields are set. The live V1 engine never filled `v5_exerciseActive` (dead since the
 * V6 plugin split — only the retired V3MLG3 plugin set it), so the fastConfirm !exercising gate
 * had NEVER engaged on the live path. These tests drive the FULL decide() pipeline with a strong
 * fast-carb fixture and flip only `exerciseActive` — locking that, now the field is wired, the
 * fast-path confirm is blocked during exercise and the meal score is damped.
 */
class ExerciseGateDecideTest {

    private val determineBasal = DetermineBasalBoostV5()

    /**
     * Strong fast-carb rise: delta 15 (≥ FAST_CONFIRM_DELTA 6), accl 30 (≥ FAST_CONFIRM_ACCL 10),
     * lunchtime, no recent low, ML corroborates — score well above FAST_CONFIRM_SCORE 0.65 when
     * not exercising. From IDLE with the fast-carb toggle on, this confirms in one cycle.
     */
    private fun fastCarbInputs(exercising: Boolean) = V5Inputs(
        delta = 15.0,
        shortAvgDelta = 10.0,
        deltaAccl = 30.0,
        bg = 180.0,
        eventualBg = 250.0,
        targetBg = 100.0,
        maxDelta = 15.0,
        minGuardBg = 150.0,
        minGuardThreshold = 80.0,
        deltaHistory = listOf(8.0, 10.0, 15.0),
        iob = 0.5,
        maxIob = 10.0,
        baseInsulinReq = 0.8,
        roundSmbTo = 0.05,
        enableSmbPreChecks = true,
        mlHypoRisk = null,
        mlMealLikely = 0.9,
        recentLowBg = 120.0,          // ≥ 80: post-hypo rescue guard does not suppress the fast path
        cumulativeRise30min = 60.0,   // sharp: full velocity factor
        hour = 13,
        exerciseActive = exercising,
        inPostExerciseWindow = false,
        asleep = false,
        fastCarbConfirmEnabled = true,
    )

    private fun idle() = V5PersistedState(mealHypothesis = MealHypothesisState())

    @Test fun `not exercising - fast-carb rise fast-confirms in one cycle (control)`() {
        val d = determineBasal.decide(fastCarbInputs(exercising = false), idle())
        assertThat(d.mealHypothesis).isEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `exercising - identical rise does NOT confirm (fastConfirm gate engages)`() {
        // Same cycle, only v5_exerciseActive→exerciseActive flipped: the !exercising fast-path
        // gate (MealHypothesis.step) must block the single-cycle confirm. Exercise-driven BG
        // rises must not be treated as fast carbs — the exercise-into-correction hypo class.
        val d = determineBasal.decide(fastCarbInputs(exercising = true), idle())
        assertThat(d.mealHypothesis).isNotEqualTo(MealHypothesis.CONFIRMED)
        assertThat(d.mealHypothesis).isNotEqualTo(MealHypothesis.COMMITTED)
    }

    @Test fun `exercising also damps the meal score (notExercisingTerm drops)`() {
        val calm = determineBasal.decide(fastCarbInputs(exercising = false), idle())
        val active = determineBasal.decide(fastCarbInputs(exercising = true), idle())
        assertThat(active.scoreComponents.notExercisingTerm).isEqualTo(0.0)
        assertThat(calm.scoreComponents.notExercisingTerm).isEqualTo(1.0)
        assertThat(active.score).isLessThan(calm.score)
    }

    @Test fun `post-exercise window damps the aggression budget`() {
        // The other dead field: v5_inPostExerciseWindow feeds AggressionBudget's post-exercise
        // recovery damper. Same inputs, window flag flipped → strictly smaller budget.
        val base = determineBasal.decide(fastCarbInputs(exercising = false), idle())
        val recov = determineBasal.decide(fastCarbInputs(exercising = false).copy(inPostExerciseWindow = true), idle())
        assertThat(recov.aggressionBudget.budget).isLessThan(base.aggressionBudget.budget)
    }
}
