package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-07-20 — V1-acceleration early primer (LIVE). Reclaims V1's ~15-min-earlier acceleration
 * response as a small fizzle-safe primer during OBSERVING, delivered as an advance on the CONFIRMED
 * commit-shot: additive up to the fizzle-safe base (primerCapU); the acceleration-scaled excess is
 * netted off the commit-shot (move-not-add). See backtesting/scripts/2026-07-v1-acceleration.
 *
 * decide()-level tests pin: the primer fires only in OBSERVING on an accelerating rise with every
 * floor clear; bolus mode folds it into finalDose while temp-basal mode does not; scaled excess sets
 * the netting residual; once-per-session; and the residual is netted off the confirmed/committed dose.
 */
class PrimerTest {

    private val determineBasal = DetermineBasalBoostV5()

    /** OBSERVING (age 0, no confirm this cycle), accelerating rise, floors clear, maxIOB headroom. */
    private fun observingAccelInputs() = V5Inputs(
        delta = 6.0,
        shortAvgDelta = 5.0,
        deltaAccl = 15.0,               // > PRIMER_ACCEL_THRESHOLD (10) — shape confirmer only, no longer scales
        bg = 140.0,
        eventualBg = 150.0,
        targetBg = 100.0,
        maxDelta = 6.0,
        minGuardBg = 135.0,
        minGuardThreshold = 80.0,
        deltaHistory = listOf(4.0, 5.0, 6.0),
        iob = 1.0,
        maxIob = 8.0,
        baseInsulinReq = 1.0,
        roundSmbTo = 0.05,
        enableSmbPreChecks = true,
        mlHypoRisk = null,
        mlMealLikely = 0.5,
        recentLowBg = 120.0,            // ≥ 80 → rescue-carb floor clear
        cumulativeRise30min = 30.0,
        hour = 12,
        exerciseActive = false,
        inPostExerciseWindow = false,
        asleep = false,
        postRescueWindow = false,
        committedCapU = 1.5,
        confirmedCapU = 4.0,
        primerCapU = 0.3,
        primerUseTempBasal = false,
    )

    /** Persisted state pinned to OBSERVING age 0 (cannot confirm this cycle → stays OBSERVING). */
    private fun observing() = V5PersistedState(mealHypothesis = MealHypothesisState(MealHypothesis.OBSERVING, ageCycles = 0))

    @Test fun `bolus primer fires in OBSERVING on a real rise - state-scaled below the ceiling`() {
        val d = determineBasal.decide(observingAccelInputs(), observing())
        assertThat(d.mealHypothesis).isEqualTo(MealHypothesis.OBSERVING)
        // fRise (6.0−1.5)/(8.0−1.5)=0.6923 × fBg 1.0 (bg 140 in band) × fIob 1−1/8=0.875
        //   → 0.3 × 0.6058 = 0.1817 → pump-rounded down to 0.15
        assertThat(d.primerBolusU).isWithin(1e-9).of(0.15)
        assertThat(d.primerBolusU).isAtMost(observingAccelInputs().primerCapU)   // cap is a CEILING now
        assertThat(d.finalDose).isAtLeast(0.15)                               // folded into the delivered SMB
        assertThat(d.newPersistedState.primerAppliedU).isWithin(1e-9).of(0.15)
        assertThat(d.newPersistedState.primerNettingResidualU).isWithin(1e-9).of(0.0)   // netting deferred to CONFIRMED
        assertThat(d.newPersistedState.primerIobU).isWithin(1e-9).of(0.15)              // accrued for the confirm-time net-off
        assertThat(d.primerScaleDebug).contains("fR=0.69")                     // factors are logged for the shadow
    }

    // ── 2026-07-30 sizing rework: the absolute-delta floor and the two suppressors ────────────────
    @Test fun `no primer below the absolute delta floor even when acceleration is huge`() {
        // The flat-trace failure mode: tiny delta, enormous ratio. deltaAccl 75 clears the old gate on
        // its own; the delta floor is what now blocks it. This is the 2026-07-29 live incident shape.
        val jitter = observingAccelInputs().copy(delta = 2.9, shortAvgDelta = 0.5, deltaAccl = 75.0)
        assertThat(determineBasal.decide(jitter, observing()).primerBolusU).isEqualTo(0.0)
    }

    @Test fun `near-target BG sizes the primer to nothing (fBg lower shoulder)`() {
        // An observed live fire sat at BG 92 on jitter. At bg 95 fBg = (95−90)/20 = 0.25, so even a
        // genuine delta 6 rise sizes below the pump increment and delivers nothing.
        val low = observingAccelInputs().copy(bg = 95.0)
        assertThat(determineBasal.decide(low, observing()).primerBolusU).isEqualTo(0.0)
    }

    @Test fun `high BG fades the primer out entirely (no adding into a recovering tail)`() {
        val high = observingAccelInputs().copy(bg = 225.0)   // above PRIMER_BG_CEIL
        assertThat(determineBasal.decide(high, observing()).primerBolusU).isEqualTo(0.0)
    }

    @Test fun `primerCapU is a true ceiling - never exceeded however strong the rise`() {
        // Full strength: delta at PRIMER_DELTA_FULL, BG mid-band, no IOB → all three factors 1.0.
        val full = observingAccelInputs().copy(delta = 8.0, shortAvgDelta = 6.0, deltaAccl = 33.0,
                                               bg = 150.0, iob = 0.0)
        val d = determineBasal.decide(full, observing())
        assertThat(d.primerBolusU).isAtMost(full.primerCapU)
        // and it does reach the ceiling rather than being stuck far below it
        assertThat(d.primerBolusU).isAtLeast(full.primerCapU - full.roundSmbTo)
    }

    @Test fun `IOB headroom scales the primer down (fIob)`() {
        val lowIob = determineBasal.decide(observingAccelInputs().copy(iob = 0.0), observing())
        val highIob = determineBasal.decide(observingAccelInputs().copy(iob = 6.0), observing())
        assertThat(highIob.primerBolusU).isLessThan(lowIob.primerBolusU)
    }

    @Test fun `primer off when primerCapU is 0`() {
        val d = determineBasal.decide(observingAccelInputs().copy(primerCapU = 0.0), observing())
        assertThat(d.primerBolusU).isWithin(1e-9).of(0.0)
    }

    @Test fun `floors gate the primer - recent low, asleep, exercise, post-rescue`() {
        assertThat(determineBasal.decide(observingAccelInputs().copy(recentLowBg = 79.0), observing()).primerBolusU).isEqualTo(0.0)
        assertThat(determineBasal.decide(observingAccelInputs().copy(asleep = true), observing()).primerBolusU).isEqualTo(0.0)
        assertThat(determineBasal.decide(observingAccelInputs().copy(exerciseActive = true), observing()).primerBolusU).isEqualTo(0.0)
        assertThat(determineBasal.decide(observingAccelInputs().copy(postRescueWindow = true), observing()).primerBolusU).isEqualTo(0.0)
    }

    @Test fun `no primer without acceleration (deltaAccl at or below threshold)`() {
        assertThat(determineBasal.decide(observingAccelInputs().copy(deltaAccl = 10.0), observing()).primerBolusU).isEqualTo(0.0)
    }

    @Test fun `temp-basal mode - primer computed but NOT folded into finalDose`() {
        val tbr = determineBasal.decide(observingAccelInputs().copy(primerUseTempBasal = true), observing())
        val off = determineBasal.decide(observingAccelInputs().copy(primerCapU = 0.0), observing())
        assertThat(tbr.primerBolusU).isWithin(1e-9).of(0.15)
        assertThat(tbr.primerUseTempBasal).isTrue()
        // finalDose in temp-basal mode equals the primer-off finalDose (the primer rides a temp basal,
        // set at the seam — it does NOT inflate the SMB).
        assertThat(tbr.finalDose).isWithin(1e-9).of(off.finalDose)
    }

    @Test fun `once per session - does not re-prime when already primed`() {
        val primed = observing().copy(primerAppliedU = 0.35, primerNettingResidualU = 0.05)
        val d = determineBasal.decide(observingAccelInputs(), primed)
        assertThat(d.primerBolusU).isWithin(1e-9).of(0.0)                     // no second primer
        assertThat(d.newPersistedState.primerAppliedU).isWithin(1e-9).of(0.35) // carried, not reset
    }

    @Test fun `netting residual is subtracted from a COMMITTED dose (move-not-add)`() {
        val committed = V5PersistedState(mealHypothesis = MealHypothesisState(MealHypothesis.COMMITTED, ageCycles = 0, committedInSession = true))
        val base = observingAccelInputs()   // COMMITTED will hold-dose; delta declining not required to stay COMMITTED at age 0
        val withResidual = determineBasal.decide(base, committed.copy(primerNettingResidualU = 0.2))
        val noResidual = determineBasal.decide(base, committed.copy(primerNettingResidualU = 0.0))
        // The COMMITTED hold is ≥ 0.2 here, so the full residual is netted off.
        assertThat(noResidual.finalDose - withResidual.finalDose).isWithin(1e-9).of(0.2)
        assertThat(withResidual.newPersistedState.primerNettingResidualU).isWithin(1e-9).of(0.0)
    }

    @Test fun `primer resets on IDLE but the IOB accumulator carries (cross-session)`() {
        val idleInputs = observingAccelInputs().copy(delta = -2.0, shortAvgDelta = -2.0, deltaAccl = 0.0, mlMealLikely = 0.0, eventualBg = 90.0)
        val stale = V5PersistedState(mealHypothesis = MealHypothesisState(MealHypothesis.IDLE),
            primerAppliedU = 0.35, primerNettingResidualU = 0.05, primerIobU = 0.3)
        val d = determineBasal.decide(idleInputs, stale)
        assertThat(d.mealHypothesis).isEqualTo(MealHypothesis.IDLE)
        assertThat(d.newPersistedState.primerAppliedU).isWithin(1e-9).of(0.0)          // session guard resets
        assertThat(d.newPersistedState.primerNettingResidualU).isWithin(1e-9).of(0.0)  // netting resets
        assertThat(d.newPersistedState.primerIobU).isWithin(1e-9).of(0.3)              // accumulator carries (nowMs=0 → no decay)
    }

    @Test fun `CONFIRM nets accumulated primer IOB beyond one base off the commit-shot (confirm-net rule)`() {
        // Fast-path confirm from IDLE with 0.7U accumulated primer IOB (prior fizzles) on board.
        val ci = observingAccelInputs().copy(delta = 8.0, shortAvgDelta = 7.0, deltaAccl = 15.0,
            mlMealLikely = 0.9, fastCarbConfirmEnabled = true, eventualBg = 200.0, primerCapU = 0.3)
        val idle = V5PersistedState(mealHypothesis = MealHypothesisState(MealHypothesis.IDLE))
        val withIob = determineBasal.decide(ci, idle.copy(primerIobU = 0.7))
        val atBase  = determineBasal.decide(ci, idle.copy(primerIobU = 0.3))  // == one base → nets 0
        assertThat(withIob.mealHypothesis).isEqualTo(MealHypothesis.CONFIRMED)
        // net-off = 0.7 − 0.3 base = 0.4 removed from the commit-shot (which is ≥ 0.4 here)
        assertThat(atBase.finalDose - withIob.finalDose).isWithin(1e-9).of(0.4)
        // credited excess consumed → accumulator held at one base (no double-credit next meal)
        assertThat(withIob.newPersistedState.primerIobU).isWithin(1e-9).of(0.3)
    }
}
