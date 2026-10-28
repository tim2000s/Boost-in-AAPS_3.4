package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-07-17 — velocity-budget floor ([velocityBudgetFloorTarget]): SHADOW semantics + per-user
 * activation with the non-meal-cap exemption.
 *
 * Addresses the budget≈0 high tail — cycles where oref's insulinReq ≤ 0 (the model says "covered")
 * but the user is sitting high — the population the composed floor EXCLUDES (it requires budget>0).
 * On user H's data this is 55% of his time over 180 mg/dL. Because V1 also doses ~0 when
 * insulinReq ≤ 0, delivering here means OUT-dosing V1 in a non-meal state, so the ACTIVE floor sets
 * [V5Decision.velocityBudgetExempt] and the override seam treats the cycle as a meal state
 * (committedCap + maxIOB bounded).
 *
 * Pure-function tests pin the conditions; decide()-level tests pin the shadow arithmetic, the
 * activation delivery, the exempt flag, mutual exclusivity with the composed floor (budget), and
 * the maxIOB / committedCap bounds.
 */
class VelocityBudgetFloorTest {

    private val determineBasal = DetermineBasalBoostV5()

    // ── Pure function: conditions + target value ────────────────────────────────────────────────

    @Test fun `conditions met - target is min(tier, committedCap)`() {
        // IDLE, BG 200, budget 0, awake, not post-rescue, no hard gate.
        assertThat(velocityBudgetFloorTarget(MealHypothesis.IDLE, 200.0, 0.0, 1.5, false, false, false))
            .isWithin(1e-9).of(VELOCITY_BUDGET_TIER_U)                 // 0.5, below committedCap 1.5
    }

    @Test fun `committedCap bounds the target below the tier`() {
        assertThat(velocityBudgetFloorTarget(MealHypothesis.IDLE, 200.0, 0.0, 0.3, false, false, false))
            .isWithin(1e-9).of(0.3)
    }

    @Test fun `bg at or below 180 - null`() {
        assertThat(velocityBudgetFloorTarget(MealHypothesis.IDLE, 180.0, 0.0, 1.5, false, false, false)).isNull()
    }

    @Test fun `budget above the epsilon - null (composed-floor territory, mutually exclusive)`() {
        assertThat(velocityBudgetFloorTarget(MealHypothesis.IDLE, 200.0, 0.5, 1.5, false, false, false)).isNull()
    }

    @Test fun `RECOVERING excluded - null (no dosing into a decelerating high)`() {
        assertThat(velocityBudgetFloorTarget(MealHypothesis.RECOVERING, 200.0, 0.0, 1.5, false, false, false)).isNull()
    }

    @Test fun `asleep - null`() {
        assertThat(velocityBudgetFloorTarget(MealHypothesis.IDLE, 200.0, 0.0, 1.5, true, false, false)).isNull()
    }

    @Test fun `post-rescue window - null`() {
        assertThat(velocityBudgetFloorTarget(MealHypothesis.IDLE, 200.0, 0.0, 1.5, false, true, false)).isNull()
    }

    @Test fun `hard gate fired - 0_0 not the tier (floor never bypasses a hard gate)`() {
        assertThat(velocityBudgetFloorTarget(MealHypothesis.IDLE, 200.0, 0.0, 1.5, false, false, true))
            .isWithin(1e-9).of(0.0)
    }

    @Test fun `fires in non-meal states (IDLE, OBSERVING, CONFIRMED, COMMITTED) - not RECOVERING`() {
        for (s in listOf(MealHypothesis.IDLE, MealHypothesis.OBSERVING, MealHypothesis.CONFIRMED, MealHypothesis.COMMITTED)) {
            assertThat(velocityBudgetFloorTarget(s, 200.0, 0.0, 1.5, false, false, false)).isNotNull()
        }
    }

    // ── decide()-level: a budget≈0 high cycle that stays non-RECOVERING ─────────────────────────

    /** baseInsulinReq 0 → budget 0; BG 200; flat/quiet signal so it stays IDLE/OBSERVING. */
    private fun budgetZeroHighInputs() = V5Inputs(
        delta = 0.0,
        shortAvgDelta = 0.0,
        deltaAccl = 0.0,
        bg = 200.0,
        eventualBg = 200.0,
        targetBg = 100.0,
        maxDelta = 0.0,
        minGuardBg = 190.0,
        minGuardThreshold = 80.0,
        deltaHistory = listOf(0.0, 0.0, 0.0),
        iob = 2.0,
        maxIob = 10.0,
        baseInsulinReq = 0.0,        // budget = 0 → the target population
        roundSmbTo = 0.05,
        enableSmbPreChecks = true,
        mlHypoRisk = null,
        mlMealLikely = 0.0,
        recentLowBg = 120.0,
        cumulativeRise30min = 0.0,
        hour = 12,
        exerciseActive = false,
        inPostExerciseWindow = false,
        asleep = false,
        committedCapU = 1.5,
        confirmedCapU = 4.0,
        postRescueWindow = false,
        v1WouldDoseU = 0.0,          // V1 also doses 0 here — the exemption is what lets the floor act
    )

    @Test fun `shadow (toggle OFF) - logs wouldAdd, delivered dose 0, not exempt`() {
        val d = determineBasal.decide(budgetZeroHighInputs(), V5PersistedState())
        assertThat(d.mealHypothesis).isNotEqualTo(MealHypothesis.RECOVERING)
        assertThat(d.aggressionBudget.budget).isWithin(1e-12).of(0.0)
        assertThat(d.finalDose).isWithin(1e-9).of(0.0)                 // pipeline untouched
        assertThat(d.velocityBudgetWouldAdd!!).isWithin(1e-9).of(VELOCITY_BUDGET_TIER_U)   // 0.5 would-add
        assertThat(d.velocityBudgetExempt).isFalse()
    }

    @Test fun `active (toggle ON) - delivers the floored hold and flags exempt`() {
        val d = determineBasal.decide(budgetZeroHighInputs().copy(velocityBudgetActive = true), V5PersistedState())
        // min(tier 0.5, committedCap 1.5, maxIob headroom 8.0) = 0.5 → pump-rounded 0.50 delivered.
        assertThat(d.finalDose).isWithin(1e-9).of(0.5)
        assertThat(d.velocityBudgetExempt).isTrue()
        assertThat(d.velocityBudgetWouldAdd!!).isWithin(1e-9).of(0.5)
    }

    @Test fun `active - committedCap bounds the delivered hold`() {
        val d = determineBasal.decide(budgetZeroHighInputs().copy(velocityBudgetActive = true, committedCapU = 0.3), V5PersistedState())
        // min(0.5, 0.3) = 0.30 → rounds to 0.30.
        assertThat(d.finalDose).isWithin(1e-9).of(0.30)
        assertThat(d.velocityBudgetExempt).isTrue()
    }

    @Test fun `active - maxIOB headroom bounds the delivered hold`() {
        val d = determineBasal.decide(budgetZeroHighInputs().copy(velocityBudgetActive = true, iob = 9.7), V5PersistedState())
        // headroom 10 − 9.7 = 0.3 → min(0.5, 0.3) = 0.30. The floor can never push IOB past maxIOB.
        assertThat(d.finalDose).isWithin(1e-9).of(0.30)
        assertThat(d.finalDose).isAtMost(10.0 - 9.7 + 1e-9)
    }

    @Test fun `active but bg below 180 - no floor, delivery unchanged, not exempt`() {
        val d = determineBasal.decide(budgetZeroHighInputs().copy(velocityBudgetActive = true, bg = 170.0, minGuardBg = 160.0), V5PersistedState())
        assertThat(d.finalDose).isWithin(1e-9).of(0.0)
        assertThat(d.velocityBudgetWouldAdd).isNull()
        assertThat(d.velocityBudgetExempt).isFalse()
    }

    @Test fun `active - hard gate still zeroes the dose (minGuardBG)`() {
        // A predicted low zeroes the dose regardless of the floor — the floor never bypasses it.
        val d = determineBasal.decide(budgetZeroHighInputs().copy(velocityBudgetActive = true, minGuardBg = 70.0), V5PersistedState())
        assertThat(d.finalDose).isWithin(1e-9).of(0.0)
        assertThat(d.velocityBudgetExempt).isFalse()
        assertThat(d.velocityBudgetWouldAdd!!).isWithin(1e-9).of(0.0)
    }

    @Test fun `mutually exclusive with the composed floor - budget over 0 gives no velocity-budget target`() {
        // A budget>0 high cycle is composed-floor territory; the velocity-budget floor abstains.
        val d = determineBasal.decide(budgetZeroHighInputs().copy(velocityBudgetActive = true, baseInsulinReq = 0.5), V5PersistedState())
        assertThat(d.velocityBudgetWouldAdd).isNull()
        assertThat(d.velocityBudgetExempt).isFalse()
    }

    @Test fun `delivered dose identical whether or not the shadow computes (shadow invariant)`() {
        val on = determineBasal.decide(budgetZeroHighInputs(), V5PersistedState())               // toggle OFF (shadow)
        val nulled = determineBasal.decide(budgetZeroHighInputs().copy(bg = 150.0, minGuardBg = 140.0), V5PersistedState())
        assertThat(on.finalDose).isEqualTo(nulled.finalDose)         // both 0 — shadow never doses
        assertThat(on.velocityBudgetWouldAdd).isNotNull()
        assertThat(nulled.velocityBudgetWouldAdd).isNull()
    }
}
