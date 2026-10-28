package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-07-06 — composed Phase-3 floor (F = 0.25): SHADOW semantics + 2026-07 per-user activation.
 *
 * Forensic + 40,180-cycle cohort backtest: on meal-session high cycles the composed post-budget
 * multiplier (stateMult × velocityFactor × iobHeadroomBrake × decelerationBrake) has MEDIAN
 * 0.037 — the V4-era multiplicative brake stack reassembled — and doses floor-round to zero for
 * 30+ min mid-meal (Episode B: BG 268–277, six zero cycles, ended 297 + manual bolus).
 *
 * These tests drive the FULL decide() pipeline with an Episode-B-like fixture and assert:
 * (a) the shadow arithmetic, (b) every gating condition flips floorWouldAdd to null,
 * (c) budget = 0 → null (Episode-A guard BY CONSTRUCTION), and (d) with the toggle OFF the
 * DELIVERED dose is unchanged in all cases — the floor is telemetry only.
 *
 * ACTIVATION matrix (composedFloorActive = true — BooleanKey.ApsBoostV5ComposedFloorActive AND
 * V6 is the active doser; 2026-07): the delivered dose becomes max(pipeline, floored dose) where
 * the floored dose passes the SAME downstream clamps the pipeline dose received (maxIOB
 * headroom, dynamic spike cap, pump-step floor-rounding); floorWouldAdd switches to logging the
 * uplift actually applied. Asserted: toggle OFF stays bit-identical, Episode B delivers the
 * pump-rounded floor, budget = 0 and hard gates still zero, and the committedCap bound, the
 * RECOVERING v1-bound, the post-rescue window, and the maxIOB headroom all still bind.
 */
class ComposedFloorShadowTest {

    private val determineBasal = DetermineBasalBoostV5()

    /**
     * Episode-B-like fixture: persisted COMMITTED holding state on a high, slow, decelerating
     * meal tail. Composed soft multiplier = velocityFactor 0.40 (rise 12 ≤ 25) × iobHeadroomBrake
     * 0.40 (iob 8.5/10 ≥ 0.85) × decelerationBrake 0.30 (accl −15, delta 2 ≤ 8) = 0.048 — the
     * backtest's ~0.04 median. Pipeline: budget 0.5 × COMMITTED 1.0 → velocity 0.2 → state cap
     * 0.2 → brakes → 0.024 → rounds (0.05 step) to ZERO. deltaHistory is flat, so deltaDeclining
     * is false and COMMITTED does NOT back off to RECOVERING despite accl −15.
     */
    private fun episodeBInputs() = V5Inputs(
        delta = 2.0,
        shortAvgDelta = 2.0,
        deltaAccl = -15.0,
        bg = 270.0,
        eventualBg = 280.0,
        targetBg = 100.0,
        maxDelta = 2.0,
        minGuardBg = 150.0,
        minGuardThreshold = 80.0,
        deltaHistory = listOf(2.0, 2.0, 2.0),
        iob = 8.5,
        maxIob = 10.0,
        baseInsulinReq = 0.5,        // budget = 0.5 (no ML damping, no post-ex, sensitivity 1.0)
        roundSmbTo = 0.05,
        enableSmbPreChecks = true,
        mlHypoRisk = null,
        mlMealLikely = 0.5,
        recentLowBg = 120.0,
        cumulativeRise30min = 12.0,  // ≤ 25 → velocityFactor 0.40
        hour = 12,
        exerciseActive = false,
        inPostExerciseWindow = false,
        asleep = false,
        committedCapU = 0.5,
        confirmedCapU = 2.5,
        postRescueWindow = false,
        v1WouldDoseU = null,
    )

    private fun committedState() = V5PersistedState(
        mealHypothesis = MealHypothesisState(MealHypothesis.COMMITTED, ageCycles = 1, committedInSession = true)
    )

    private fun recoveringState() = V5PersistedState(
        mealHypothesis = MealHypothesisState(MealHypothesis.RECOVERING, ageCycles = 1, committedInSession = true)
    )

    // ── Arithmetic on the Episode-B fixture ─────────────────────────────────────────────────────

    @Test fun `Episode-B-like COMMITTED zero-dose cycle - floor would add 0_125U, delivery untouched`() {
        val d = determineBasal.decide(episodeBInputs(), committedState())
        assertThat(d.mealHypothesis).isEqualTo(MealHypothesis.COMMITTED)
        // The defect: composed mult 0.048 drives 0.2U pre-brake dose to 0.024U → rounds to ZERO.
        assertThat(d.finalDose).isWithin(1e-9).of(0.0)
        // Shadow: flooredDose = min(budget 0.5 × 0.25, committedCap 0.5) = 0.125; wouldAdd =
        // max(0, 0.125 − 0.0) = 0.125. Exactly the spec fixture (budget 0.5, composed ~0.04).
        assertThat(d.floorWouldAdd).isNotNull()
        assertThat(d.floorWouldAdd!!).isWithin(1e-9).of(0.125)
    }

    @Test fun `committedCap bounds the floored dose (one routine hold is the ceiling)`() {
        val d = determineBasal.decide(episodeBInputs().copy(committedCapU = 0.1), committedState())
        // min(0.5 × 0.25, 0.1) = 0.1 → wouldAdd 0.1.
        assertThat(d.floorWouldAdd!!).isWithin(1e-9).of(0.1)
    }

    // ── Condition gating: each condition flips the shadow to null ──────────────────────────────

    @Test fun `bg at or below 160 - null`() {
        val d = determineBasal.decide(episodeBInputs().copy(bg = 150.0), committedState())
        assertThat(d.floorWouldAdd).isNull()
    }

    @Test fun `eventualBg not more than target+20 - null`() {
        val d = determineBasal.decide(episodeBInputs().copy(eventualBg = 115.0), committedState())
        assertThat(d.floorWouldAdd).isNull()
    }

    @Test fun `asleep - null`() {
        val d = determineBasal.decide(episodeBInputs().copy(asleep = true), committedState())
        assertThat(d.floorWouldAdd).isNull()
    }

    @Test fun `post-rescue window - null`() {
        val d = determineBasal.decide(episodeBInputs().copy(postRescueWindow = true), committedState())
        assertThat(d.floorWouldAdd).isNull()
    }

    @Test fun `non-meal-session state - null`() {
        // Persisted IDLE; whatever the step produces (IDLE or OBSERVING) is outside the
        // CONFIRMED/COMMITTED/RECOVERING meal-session set.
        val d = determineBasal.decide(episodeBInputs(), V5PersistedState())
        assertThat(d.mealHypothesis).isAnyOf(MealHypothesis.IDLE, MealHypothesis.OBSERVING)
        assertThat(d.floorWouldAdd).isNull()
    }

    @Test fun `budget zero - null (Episode-A guard BY CONSTRUCTION)`() {
        // baseInsulinReq = 0 → budget = 0 (the AggressionBudget floor is a FRACTION of
        // baseInsulinReq, so it is 0 too). A zero-budget cycle — the Episode-A shape — can never
        // produce a floored dose: the budget > 0 condition nulls the shadow by construction.
        val d = determineBasal.decide(episodeBInputs().copy(baseInsulinReq = 0.0), committedState())
        assertThat(d.aggressionBudget.budget).isWithin(1e-12).of(0.0)
        assertThat(d.floorWouldAdd).isNull()
        assertThat(d.finalDose).isWithin(1e-9).of(0.0)
    }

    @Test fun `phase-3 HARD gate fired - wouldAdd is zero, not the floored dose`() {
        // minGuardBg below threshold → hard gate zeroes the dose regardless of any multiplier
        // floor, so the floored pipeline would deliver 0 too. Conditions ARE met → 0.0, not null.
        val d = determineBasal.decide(episodeBInputs().copy(minGuardBg = 70.0), committedState())
        assertThat(d.finalDose).isWithin(1e-9).of(0.0)
        assertThat(d.floorWouldAdd).isNotNull()
        assertThat(d.floorWouldAdd!!).isWithin(1e-9).of(0.0)
    }

    // ── RECOVERING: v1-bound where applicable (non-meal-state cap at the override seam) ─────────

    @Test fun `RECOVERING floored dose is bounded at V1's would-dose`() {
        // delta 2 ≥ 0, score ≈0.38 ≥ 0.18, accl −15 ≤ re-engage threshold → stays RECOVERING.
        val d = determineBasal.decide(episodeBInputs().copy(v1WouldDoseU = 0.05), recoveringState())
        assertThat(d.mealHypothesis).isEqualTo(MealHypothesis.RECOVERING)
        // flooredDose 0.125 → bounded to v1Would 0.05 (RECOVERING is v1-capped at the seam).
        assertThat(d.floorWouldAdd!!).isWithin(1e-9).of(0.05)
    }

    @Test fun `RECOVERING without a v1 bound uses the unbounded floored dose`() {
        val d = determineBasal.decide(episodeBInputs().copy(v1WouldDoseU = null), recoveringState())
        assertThat(d.mealHypothesis).isEqualTo(MealHypothesis.RECOVERING)
        assertThat(d.floorWouldAdd!!).isWithin(1e-9).of(0.125)
    }

    @Test fun `COMMITTED is NOT v1-bound (meal state keeps the full floored dose)`() {
        val d = determineBasal.decide(episodeBInputs().copy(v1WouldDoseU = 0.05), committedState())
        assertThat(d.mealHypothesis).isEqualTo(MealHypothesis.COMMITTED)
        assertThat(d.floorWouldAdd!!).isWithin(1e-9).of(0.125)
    }

    // ── SHADOW-ONLY invariant: delivered dose unchanged in all cases ───────────────────────────

    @Test fun `delivered dose is identical whether or not the shadow computes`() {
        val active = determineBasal.decide(episodeBInputs(), committedState())
        val nulled = determineBasal.decide(episodeBInputs().copy(postRescueWindow = true), committedState())
        // postRescueWindow feeds ONLY the shadow — every dosing output must be bit-identical.
        assertThat(active.finalDose).isEqualTo(nulled.finalDose)
        assertThat(active.insulinToDeliver).isEqualTo(nulled.insulinToDeliver)
        assertThat(active.phase3.reductions).isEqualTo(nulled.phase3.reductions)
        assertThat(active.floorWouldAdd).isNotNull()
        assertThat(nulled.floorWouldAdd).isNull()
    }

    // ══ 2026-07 ACTIVATION (composedFloorActive = true) ════════════════════════════════════════

    private fun activeB() = episodeBInputs().copy(composedFloorActive = true)

    @Test fun `toggle OFF - bit-identical outputs to the pre-activation pipeline across the fixtures`() {
        // Explicit toggle-OFF sweep over the existing fixture matrix: delivered dose and the
        // shadow field must be exactly the values the 2026-07-06 shadow tests pinned.
        val expectations = listOf(
            Triple(episodeBInputs(), 0.0, 0.125),                              // Episode B
            Triple(episodeBInputs().copy(committedCapU = 0.1), 0.0, 0.1),      // committedCap bound
            Triple(episodeBInputs().copy(minGuardBg = 70.0), 0.0, 0.0),        // hard gate fired
        )
        for ((inputs, expectedDose, expectedWouldAdd) in expectations) {
            val d = determineBasal.decide(inputs.copy(composedFloorActive = false), committedState())
            assertThat(d.finalDose).isWithin(1e-9).of(expectedDose)
            assertThat(d.floorWouldAdd!!).isWithin(1e-9).of(expectedWouldAdd)
        }
        // Null-shadow fixtures stay null and undosed with the toggle explicitly OFF too.
        val zeroBudget = determineBasal.decide(episodeBInputs().copy(baseInsulinReq = 0.0, composedFloorActive = false), committedState())
        assertThat(zeroBudget.finalDose).isWithin(1e-9).of(0.0)
        assertThat(zeroBudget.floorWouldAdd).isNull()
        val postRescue = determineBasal.decide(episodeBInputs().copy(postRescueWindow = true, composedFloorActive = false), committedState())
        assertThat(postRescue.finalDose).isWithin(1e-9).of(0.0)
        assertThat(postRescue.floorWouldAdd).isNull()
    }

    @Test fun `toggle ON Episode B - delivers the pump-rounded floored dose, field logs the applied uplift`() {
        val d = determineBasal.decide(activeB(), committedState())
        assertThat(d.mealHypothesis).isEqualTo(MealHypothesis.COMMITTED)
        // Floored target = min(budget 0.5 × 0.25, committedCap 0.5) = 0.125 U. Same pump-step
        // floor-rounding rule as the pipeline (0.05 step, +1e-9 epsilon): floor(0.125/0.05) = 2
        // steps → 0.10 U delivered (NOT nearest-rounded 0.15). Unfloored pipeline delivered 0.
        assertThat(d.finalDose).isWithin(1e-9).of(0.10)
        // ACTIVE semantics: the field now logs the uplift actually applied (0.10 − 0.0).
        assertThat(d.floorWouldAdd!!).isWithin(1e-9).of(0.10)
    }

    @Test fun `toggle ON budget zero - still delivers 0 (Episode-A guard holds under activation)`() {
        val d = determineBasal.decide(activeB().copy(baseInsulinReq = 0.0), committedState())
        assertThat(d.aggressionBudget.budget).isWithin(1e-12).of(0.0)
        assertThat(d.finalDose).isWithin(1e-9).of(0.0)
        assertThat(d.floorWouldAdd).isNull()
    }

    @Test fun `toggle ON hard gate fired - still delivers 0 (floor never bypasses a hard gate)`() {
        val d = determineBasal.decide(activeB().copy(minGuardBg = 70.0), committedState())
        assertThat(d.phase3.reductions.hardGateFired).isEqualTo("min_guard_bg")
        assertThat(d.finalDose).isWithin(1e-9).of(0.0)
        assertThat(d.floorWouldAdd!!).isWithin(1e-9).of(0.0)
    }

    @Test fun `toggle ON committedCap bounds the delivered floored dose`() {
        val d = determineBasal.decide(activeB().copy(committedCapU = 0.1), committedState())
        // min(0.125, committedCap 0.1) = 0.1 → rounds to 0.10 delivered.
        assertThat(d.finalDose).isWithin(1e-9).of(0.10)
        assertThat(d.floorWouldAdd!!).isWithin(1e-9).of(0.10)
    }

    @Test fun `toggle ON RECOVERING - floored delivery still v1-bounded at the seam's bound`() {
        val d = determineBasal.decide(activeB().copy(v1WouldDoseU = 0.05), recoveringState())
        assertThat(d.mealHypothesis).isEqualTo(MealHypothesis.RECOVERING)
        // Floored target 0.125 → v1-bound 0.05 → rounds to 0.05 delivered. The override seam's
        // non-meal cap (min with V1's would-dose) can therefore never be exceeded by the floor.
        assertThat(d.finalDose).isWithin(1e-9).of(0.05)
        assertThat(d.floorWouldAdd!!).isWithin(1e-9).of(0.05)
    }

    @Test fun `toggle ON post-rescue window - no floor, delivery unchanged`() {
        val d = determineBasal.decide(activeB().copy(postRescueWindow = true), committedState())
        assertThat(d.finalDose).isWithin(1e-9).of(0.0)
        assertThat(d.floorWouldAdd).isNull()
    }

    @Test fun `toggle ON asleep - no floor, delivery unchanged`() {
        val d = determineBasal.decide(activeB().copy(asleep = true), committedState())
        assertThat(d.finalDose).isWithin(1e-9).of(0.0)
        assertThat(d.floorWouldAdd).isNull()
    }

    @Test fun `toggle ON pipeline already above the floor - dose unchanged, uplift logged as 0`() {
        // Sharp rise (velocity 1.0), low IOB (no headroom brake), accl 0 (no decel brake):
        // pipeline = budget 0.5 × COMMITTED 1.0 → state cap 0.5 → no soft damping → 0.5 U.
        // Floored target 0.125 < 0.5 → floor adds nothing; ACTIVE field logs uplift 0.0.
        val d = determineBasal.decide(
            activeB().copy(cumulativeRise30min = 60.0, iob = 2.0, deltaAccl = 0.0),
            committedState()
        )
        assertThat(d.mealHypothesis).isEqualTo(MealHypothesis.COMMITTED)
        assertThat(d.finalDose).isWithin(1e-9).of(0.5)
        assertThat(d.floorWouldAdd!!).isWithin(1e-9).of(0.0)
    }

    @Test fun `toggle ON maxIOB headroom still caps the floored dose`() {
        // iob 9.95 / maxIob 10 → headroom 0.05 U. Floored target 0.125 is clamped to the SAME
        // headroom applyPhase3 clamps to, then pump-rounded → 0.05 delivered. The floor can never
        // push IOB past maxIOB.
        val d = determineBasal.decide(activeB().copy(iob = 9.95), committedState())
        assertThat(d.finalDose).isWithin(1e-9).of(0.05)
        assertThat(d.finalDose).isAtMost(10.0 - 9.95 + 1e-9)
        assertThat(d.floorWouldAdd!!).isWithin(1e-9).of(0.05)
    }

    // ── 2026-07-08 hypo-gate: floor engages only if BOTH TBR<63 < 2.0% AND TBR<70 < 3.5% (fail-closed) ──

    @Test fun `hypo-gate allows the floor below both thresholds`() {
        assertThat(composedFloorAllowedByTbr(0.0, 0.0)).isTrue()
        assertThat(composedFloorAllowedByTbr(1.99, 3.49)).isTrue()
    }

    @Test fun `hypo-gate blocks on TBR-below-63 at or above 2 percent`() {
        assertThat(composedFloorAllowedByTbr(2.0, 1.0)).isFalse()   // strict <, exactly 2.0% blocked
        assertThat(composedFloorAllowedByTbr(3.5, 1.0)).isFalse()
    }

    @Test fun `hypo-gate blocks on elevated TBR-below-70 even when below-63 is low`() {
        // The two-test-bar co-check: a low <63 must NOT engage the floor if <70 is over the primary
        // bar (both on the same 14d window). e.g. a 30d-C-like profile <63 1.56% / <70 3.95% → HOLD.
        assertThat(composedFloorAllowedByTbr(1.56, 3.95)).isFalse()
        assertThat(composedFloorAllowedByTbr(1.0, 3.5)).isFalse()   // strict <, exactly 3.5% blocked
    }

    @Test fun `hypo-gate ENGAGES a borderline user whose 14d figures are both under bar`() {
        // Honest record: on the SAME 14d window, re-validation user C actually engages (14d <70 3.12%,
        // <63 1.56% — both under). The manual hold on C was 30d-based; the 14d gate supersedes it.
        assertThat(composedFloorAllowedByTbr(1.56, 3.12)).isTrue()
    }

    @Test fun `hypo-gate is fail-closed when either TBR is unknown`() {
        assertThat(composedFloorAllowedByTbr(null, 1.0)).isFalse()  // no/insufficient CGM history → floor off
        assertThat(composedFloorAllowedByTbr(1.0, null)).isFalse()
    }
}
