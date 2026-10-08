package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-10-08, dose-path audit item 10 (engine part).
 *
 * The primer was sized before Phase 3 and ignored its hard gates, so it dosed on cycles where both
 * floors and the pipeline dose were zero because the 30-minute minGuardBG was under the low
 * threshold. It also ignored mlHypoRisk, which damps the aggression budget, and in bolus mode it made
 * the whole finalDose of an OBSERVING cycle exempt from the override seam's V1 bound. Written against
 * the API that existed before the fix so it runs on the old code too.
 */
class PrimerSafetyGateTest {

    private val engine = DetermineBasalBoostV5()

    /** The PrimerTest base cycle: OBSERVING age 0, a real rise, every floor clear. */
    private fun base() = V5Inputs(
        delta = 6.0, shortAvgDelta = 5.0, deltaAccl = 15.0, bg = 140.0, eventualBg = 150.0, targetBg = 100.0,
        maxDelta = 6.0, minGuardBg = 135.0, minGuardThreshold = 80.0, deltaHistory = listOf(4.0, 5.0, 6.0),
        iob = 0.0, maxIob = 8.0, baseInsulinReq = 1.0, roundSmbTo = 0.05, enableSmbPreChecks = true,
        mlHypoRisk = null, mlMealLikely = 0.5, recentLowBg = 120.0, cumulativeRise30min = 30.0, hour = 12,
        exerciseActive = false, inPostExerciseWindow = false, asleep = false, postRescueWindow = false,
        committedCapU = 1.5, confirmedCapU = 4.0, primerCapU = 0.5, primerUseTempBasal = false,
    )

    private fun observing() = V5PersistedState(mealHypothesis = MealHypothesisState(MealHypothesis.OBSERVING, ageCycles = 0))

    @Test fun `precondition - the base cycle primes`() {
        assertThat(engine.decide(base(), observing()).primerBolusU).isGreaterThan(0.0)
    }

    @Test fun `no primer when the minGuardBG hard gate fired`() {
        val d = engine.decide(base().copy(minGuardBg = 70.0), observing())
        assertThat(d.phase3.reductions.hardGateFired).isEqualTo("min_guard_bg")
        assertThat(d.primerBolusU).isEqualTo(0.0)
        assertThat(d.finalDose).isEqualTo(0.0)
    }

    @Test fun `no primer when SMB pre-checks fail`() {
        val d = engine.decide(base().copy(enableSmbPreChecks = false), observing())
        assertThat(d.primerBolusU).isEqualTo(0.0)
        assertThat(d.finalDose).isEqualTo(0.0)
    }

    @Test fun `no temp-basal primer either when a hard gate fired`() {
        val d = engine.decide(base().copy(minGuardBg = 70.0, primerUseTempBasal = true), observing())
        assertThat(d.primerBolusU).isEqualTo(0.0)
    }

    @Test fun `the once-per-session guard is not spent by a gated cycle`() {
        val d = engine.decide(base().copy(minGuardBg = 70.0), observing())
        assertThat(d.newPersistedState.primerAppliedU).isEqualTo(0.0)
        assertThat(d.newPersistedState.primerIobU).isEqualTo(0.0)
    }

    @Test fun `elevated mlHypoRisk scales the primer down as it does the budget`() {
        val clear = engine.decide(base(), observing()).primerBolusU
        val risky = engine.decide(base().copy(mlHypoRisk = 0.8), observing()).primerBolusU
        // mlHypoRiskScale(0.8) = max(0.5, 1 - 0.5/0.7) = 0.5
        assertThat(risky).isLessThan(clear)
        assertThat(risky).isAtMost(clear * mlHypoRiskScale(0.8) + 1e-9)
    }

    @Test fun `low mlHypoRisk leaves the primer unchanged`() {
        val clear = engine.decide(base(), observing()).primerBolusU
        val low = engine.decide(base().copy(mlHypoRisk = 0.2), observing()).primerBolusU
        assertThat(low).isEqualTo(clear)
    }

    @Test fun `bolus mode - only the primer escapes the V1 bound, the OBSERVING dose does not`() {
        // V1 would dose nothing this cycle; the OBSERVING pipeline dose on its own would be capped to
        // 0 at the seam, but the seam exempts the whole finalDose once a bolus primer is present.
        val withV1Zero = base().copy(v1WouldDoseU = 0.0, baseInsulinReq = 2.0)
        val noPrimer = engine.decide(withV1Zero.copy(primerCapU = 0.0), observing())
        assertThat(noPrimer.finalDose).isGreaterThan(0.0)   // there is a pipeline dose to bound
        val d = engine.decide(withV1Zero, observing())
        assertThat(d.primerBolusU).isGreaterThan(0.0)
        assertThat(d.finalDose).isWithin(1e-9).of(d.primerBolusU)
    }

    @Test fun `bolus mode - a V1 dose above the pipeline dose leaves it unbounded`() {
        val generousV1 = base().copy(v1WouldDoseU = 5.0, baseInsulinReq = 2.0)
        val noPrimer = engine.decide(generousV1.copy(primerCapU = 0.0), observing())
        val d = engine.decide(generousV1, observing())
        assertThat(d.finalDose).isWithin(1e-9).of(noPrimer.finalDose + d.primerBolusU)
    }
}
