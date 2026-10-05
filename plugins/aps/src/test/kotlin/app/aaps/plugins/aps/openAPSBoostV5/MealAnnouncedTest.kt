package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-10-05 announced-meal route. A meal announced by carbs on board or a recent manual or wizard
 * bolus confirms into COMMITTED rather than CONFIRMED, so oref's insulinReq, which already nets the
 * pre-bolus and the carbs, is not multiplied by the 1.8x catch-up. The field case: a child with TDD
 * about 20 U, 1.5 U pre-bolus, 24 g entered, insulinReq 0.93 U, CONFIRMED delivered 1.25 U and BG
 * reached 74 within 45 minutes.
 */
class MealAnnouncedTest {

    private val determineBasal = DetermineBasalBoostV5()

    /** The reported cycle, approximately: rising after a covered meal, confirm-eligible. */
    private fun reportedCycle(announced: Boolean) = V5Inputs(
        delta = 5.0,
        shortAvgDelta = 4.0,
        deltaAccl = 5.0,
        bg = 155.0,
        eventualBg = 190.0,
        targetBg = 100.0,
        maxDelta = 5.0,
        minGuardBg = 120.0,
        minGuardThreshold = 80.0,
        deltaHistory = listOf(3.0, 4.0, 5.0),
        iob = 1.6,
        maxIob = 6.0,
        baseInsulinReq = 0.93,
        roundSmbTo = 0.05,
        enableSmbPreChecks = true,
        mlHypoRisk = null,
        mlMealLikely = 0.6,
        recentLowBg = 120.0,
        cumulativeRise30min = 39.5,     // velocity factor 0.748, which reproduces the reported 1.25 U
        hour = 9,
        exerciseActive = false,
        inPostExerciseWindow = false,
        asleep = false,
        postRescueWindow = false,
        committedCapU = 0.5,
        confirmedCapU = 2.5,
        mealAnnounced = announced,
    )

    /** OBSERVING past the age gate with peak score and offset already over the confirm bar. */
    private fun readyToConfirm() = V5PersistedState(
        mealHypothesis = MealHypothesisState(
            MealHypothesis.OBSERVING, ageCycles = 2, maxScoreInObserving = 0.7,
            maxEventualBgOffsetInObserving = 60.0, committedInSession = false,
        )
    )

    @Test fun `unannounced, the reported cycle still confirms with the catch-up shot`() {
        val d = determineBasal.decide(reportedCycle(announced = false), readyToConfirm())
        assertThat(d.mealHypothesis).isEqualTo(MealHypothesis.CONFIRMED)
        assertThat(d.insulinToDeliver).isWithin(0.01).of(0.93 * 1.8 * 0.748)
        assertThat(d.mealSessionStarted).isTrue()
    }

    @Test fun `announced, the same cycle commits at oref's requirement under the committed cap`() {
        val plain = determineBasal.decide(reportedCycle(announced = false), readyToConfirm())
        val d = determineBasal.decide(reportedCycle(announced = true), readyToConfirm())
        assertThat(d.mealHypothesis).isEqualTo(MealHypothesis.COMMITTED)
        assertThat(d.actionMultiplier).isEqualTo(1.0)
        assertThat(d.insulinToDeliver).isAtMost(0.5)
        assertThat(d.insulinToDeliver).isAtMost(0.93)
        assertThat(d.finalDose).isLessThan(plain.finalDose)
        // Still a session start, so the meal-time learner records it and the lock is set.
        assertThat(d.mealSessionStarted).isTrue()
        assertThat(d.newPersistedState.mealHypothesis.committedInSession).isTrue()
    }

    @Test fun `announced meals take the fast path into COMMITTED as well`() {
        val fromIdle = step(
            MealHypothesisState(), score = 0.8, eventualBg = 200.0, targetBg = 100.0, delta = 9.0,
            deltaAccl = 20.0, deltaDeclining = false, fastConfirmEnabled = true, mealAnnounced = true,
        )
        assertThat(fromIdle.state).isEqualTo(MealHypothesis.COMMITTED)
        assertThat(fromIdle.committedInSession).isTrue()
        val unannounced = step(
            MealHypothesisState(), score = 0.8, eventualBg = 200.0, targetBg = 100.0, delta = 9.0,
            deltaAccl = 20.0, deltaDeclining = false, fastConfirmEnabled = true,
        )
        assertThat(unannounced.state).isEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `carbs on board alone do not move IDLE`() {
        val s = step(
            MealHypothesisState(), score = 0.1, eventualBg = 150.0, targetBg = 100.0, delta = 0.0,
            deltaAccl = 0.0, deltaDeclining = false, mealAnnounced = true,
        )
        assertThat(s.state).isEqualTo(MealHypothesis.IDLE)
    }

    @Test fun `an announced meal cannot confirm later in the same session`() {
        val committed = step(
            readyToConfirm().mealHypothesis, score = 0.7, eventualBg = 190.0, targetBg = 100.0, delta = 5.0,
            deltaAccl = 5.0, deltaDeclining = false, mealAnnounced = true,
        )
        // Re-entering OBSERVING with the lock still set (the Fix 6 persistence-race shape).
        val reEntered = committed.copy(state = MealHypothesis.OBSERVING, ageCycles = 3, maxScoreInObserving = 0.8,
            maxEventualBgOffsetInObserving = 80.0)
        val next = step(reEntered, score = 0.8, eventualBg = 200.0, targetBg = 100.0, delta = 6.0,
            deltaAccl = 8.0, deltaDeclining = false, mealAnnounced = false)
        assertThat(next.state).isNotEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `session start excludes continuations of a session`() {
        val idle = MealHypothesisState()
        val observing = MealHypothesisState(MealHypothesis.OBSERVING)
        val confirmed = MealHypothesisState(MealHypothesis.CONFIRMED, committedInSession = true)
        val committed = MealHypothesisState(MealHypothesis.COMMITTED, committedInSession = true)
        val recovering = MealHypothesisState(MealHypothesis.RECOVERING, committedInSession = true)
        assertThat(sessionCommittedThisCycle(observing, confirmed)).isTrue()
        assertThat(sessionCommittedThisCycle(idle, confirmed)).isTrue()
        assertThat(sessionCommittedThisCycle(observing, committed)).isTrue()
        assertThat(sessionCommittedThisCycle(idle, committed)).isTrue()
        assertThat(sessionCommittedThisCycle(confirmed, committed)).isFalse()
        assertThat(sessionCommittedThisCycle(recovering, committed)).isFalse()
        assertThat(sessionCommittedThisCycle(committed, committed)).isFalse()
        assertThat(sessionCommittedThisCycle(idle, observing)).isFalse()
    }

    @Test fun `no primer on an announced meal`() {
        val observingRise = reportedCycle(announced = true).copy(
            delta = 6.0, deltaAccl = 15.0, bg = 140.0, iob = 1.0, maxIob = 8.0, primerCapU = 0.3,
        )
        val observing = V5PersistedState(mealHypothesis = MealHypothesisState(MealHypothesis.OBSERVING, ageCycles = 0))
        assertThat(determineBasal.decide(observingRise, observing).primerBolusU).isEqualTo(0.0)
        assertThat(determineBasal.decide(observingRise.copy(mealAnnounced = false), observing).primerBolusU).isGreaterThan(0.0)
    }
}
