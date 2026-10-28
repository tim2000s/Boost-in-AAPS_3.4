package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-10-08, dose-path audit item 7: a second CONFIRMED shot within one meal.
 *
 * The single-confirm lock was cleared on the RECOVERING to IDLE exit, which fires on one negative
 * delta, the trough between two phases of a meal. The fast path then went IDLE to CONFIRMED without
 * the eventualBG-offset or dose-adequacy gates. The lock now holds for SESSION_LOCK_MIN_MS after the
 * last CONFIRMED or COMMITTED cycle unless SESSION_END_NON_POSITIVE_MS of non-positive deltas ends
 * the session first, and inside it a rise can re-engage COMMITTED through the slow path only.
 *
 * Every test drives step() with a wall clock, using only the API that existed before the fix, so
 * that the same file runs against the old code and shows which behaviours changed.
 */
class MealSessionLockTest {

    private val t0 = 1_800_000_000_000L
    private fun min(m: Int) = t0 + m * 60_000L

    /** A COMMITTED meal at t0, backed off to RECOVERING at +5 and out to IDLE on one negative delta at +10. */
    private fun troughAfterFirstPhase(): MealHypothesisState {
        val committed = step(
            MealHypothesisState(MealHypothesis.COMMITTED, committedInSession = true),
            score = 0.6, eventualBg = 200.0, targetBg = 100.0, delta = 6.0, deltaAccl = 5.0,
            deltaDeclining = false, nowMs = t0,
        )
        assertThat(committed.state).isEqualTo(MealHypothesis.COMMITTED)
        val recovering = step(committed, score = 0.5, eventualBg = 180.0, targetBg = 100.0, delta = 2.0,
            deltaAccl = -20.0, deltaDeclining = true, nowMs = min(5))
        assertThat(recovering.state).isEqualTo(MealHypothesis.RECOVERING)
        val idle = step(recovering, score = 0.4, eventualBg = 170.0, targetBg = 100.0, delta = -1.0,
            deltaAccl = -5.0, deltaDeclining = true, nowMs = min(10))
        assertThat(idle.state).isEqualTo(MealHypothesis.IDLE)
        return idle
    }

    /** Fast-path signals: sharp, accelerating, corroborated. */
    private fun fastRise(s: MealHypothesisState, at: Long, eventualBg: Double = 160.0) = step(
        s, score = 0.7, eventualBg = eventualBg, targetBg = 100.0, delta = 9.0, deltaAccl = 25.0,
        deltaDeclining = false, fastConfirmEnabled = true, nowMs = at,
    )

    @Test fun `a single negative delta between meal phases does not reopen the confirm`() {
        val idle = troughAfterFirstPhase()
        assertThat(idle.committedInSession).isTrue()
        val second = fastRise(idle, min(15))
        assertThat(second.state).isNotEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `the fast path cannot confirm from OBSERVING inside the lock either`() {
        val idle = troughAfterFirstPhase()
        val observing = step(idle, score = 0.5, eventualBg = 120.0, targetBg = 100.0, delta = 2.0,
            deltaAccl = 0.0, deltaDeclining = false, nowMs = min(15))
        assertThat(observing.state).isEqualTo(MealHypothesis.OBSERVING)
        // eventualBG offset 10 < 30, so the slow path is not eligible; only the fast path could fire.
        val next = fastRise(observing, min(20), eventualBg = 110.0)
        assertThat(next.state).isEqualTo(MealHypothesis.OBSERVING)
    }

    @Test fun `a second phase that passes the slow-path gates re-engages COMMITTED, not CONFIRMED`() {
        var s = troughAfterFirstPhase()
        var sawCommitted = false
        for (m in listOf(15, 20, 25, 30, 35)) {
            s = step(s, score = 0.6, eventualBg = 190.0, targetBg = 100.0, delta = 4.0, deltaAccl = 5.0,
                deltaDeclining = false, nowMs = min(m))
            assertThat(s.state).isNotEqualTo(MealHypothesis.CONFIRMED)
            if (s.state == MealHypothesis.COMMITTED) sawCommitted = true
        }
        assertThat(sawCommitted).isTrue()
        assertThat(s.committedInSession).isTrue()
    }

    @Test fun `inside the lock a rise that fails the dose-adequacy gate does not re-engage`() {
        var s = troughAfterFirstPhase()
        for (m in listOf(15, 20, 25, 30, 35)) {
            s = step(s, score = 0.6, eventualBg = 190.0, targetBg = 100.0, delta = 4.0, deltaAccl = 5.0,
                deltaDeclining = false, confirmDoseAdequate = false, nowMs = min(m))
        }
        assertThat(s.state).isEqualTo(MealHypothesis.OBSERVING)
    }

    @Test fun `ninety minutes after the last commit a new meal can confirm again`() {
        var s = troughAfterFirstPhase()
        // Wobbling glucose so the non-positive run never reaches 30 minutes; only the time bound ends it.
        var m = 15
        while (m < 95) {
            s = step(s, score = 0.2, eventualBg = 110.0, targetBg = 100.0, delta = if (m % 10 == 5) 1.0 else -1.0,
                deltaAccl = 0.0, deltaDeclining = false, nowMs = min(m))
            m += 5
        }
        assertThat(s.state).isEqualTo(MealHypothesis.IDLE)
        assertThat(s.committedInSession).isFalse()
        assertThat(fastRise(s, min(95)).state).isEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `thirty minutes of non-positive deltas ends the session early`() {
        var s = troughAfterFirstPhase()
        for (m in 15..45 step 5) {
            s = step(s, score = 0.2, eventualBg = 100.0, targetBg = 100.0, delta = -2.0, deltaAccl = 0.0,
                deltaDeclining = false, nowMs = min(m))
        }
        assertThat(s.committedInSession).isFalse()
        assertThat(fastRise(s, min(50)).state).isEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `a reset keeps the lock, so a gap or restart after a confirm cannot open a second one`() {
        val locked = MealHypothesisState(MealHypothesis.RECOVERING, ageCycles = 2, committedInSession = true)
        val (reset, did) = resetIfNeeded(locked, pumpDisconnected = true)
        assertThat(did).isTrue()
        assertThat(reset.state).isEqualTo(MealHypothesis.IDLE)
        assertThat(reset.committedInSession).isTrue()
    }

    @Test fun `decide - a re-engaged COMMITTED is not a new meal session`() {
        val d = DetermineBasalBoostV5()
        val inputs = V5Inputs(
            delta = 4.0, shortAvgDelta = 4.0, deltaAccl = 0.0, bg = 170.0, eventualBg = 200.0, targetBg = 100.0,
            maxDelta = 4.0, minGuardBg = 150.0, minGuardThreshold = 80.0, deltaHistory = listOf(4.0, 4.0, 4.0),
            iob = 1.0, maxIob = 10.0, baseInsulinReq = 2.0, roundSmbTo = 0.05, enableSmbPreChecks = true,
            mlHypoRisk = null, mlMealLikely = 0.9, recentLowBg = 120.0, cumulativeRise30min = 60.0, hour = 12,
            exerciseActive = false, inPostExerciseWindow = false, nowMs = min(30),
        )
        val locked = MealHypothesisState(MealHypothesis.OBSERVING, ageCycles = 3, maxScoreInObserving = 0.7,
            maxEventualBgOffsetInObserving = 90.0, committedInSession = true, lastAgeMs = min(25))
        val out = d.decide(inputs, V5PersistedState(mealHypothesis = locked))
        assertThat(out.mealHypothesis).isNotEqualTo(MealHypothesis.CONFIRMED)
        assertThat(out.mealSessionStarted).isFalse()
    }
}
