package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-10-08, dose-path audit item 17: stale meal-state evidence confirming a meal.
 *
 * The OBSERVING peaks never expired, the persisted state was restored with no age check and the
 * confirm test ran before the fall-back test, so evidence from hours earlier could CONFIRM on a
 * cycle whose own glucose did not support it (the audit harness produced 1.4 U three hours after a
 * restore). Written against the API that existed before the fix so it runs on the old code too.
 */
class StaleMealStateTest {

    private val t0 = 1_800_000_000_000L
    private fun min(m: Int) = t0 + m * 60_000L
    private val engine = DetermineBasalBoostV5()

    /** A moderate cycle: score between the fall-back and confirm bars, eventualBG only 10 over target. */
    private fun moderateCycle(now: Long) = V5Inputs(
        delta = 3.0, shortAvgDelta = 3.0, deltaAccl = 0.0, bg = 140.0, eventualBg = 110.0, targetBg = 100.0,
        maxDelta = 3.0, minGuardBg = 120.0, minGuardThreshold = 80.0, deltaHistory = listOf(3.0, 3.0, 3.0),
        iob = 0.5, maxIob = 10.0, baseInsulinReq = 1.5, roundSmbTo = 0.05, enableSmbPreChecks = true,
        mlHypoRisk = null, mlMealLikely = 0.6, recentLowBg = 120.0, cumulativeRise30min = 18.0, hour = 12,
        exerciseActive = false, inPostExerciseWindow = false, nowMs = now,
    )

    /** OBSERVING past the age gate with high peaks, as it was saved three hours ago. */
    private fun savedThreeHoursAgo() = V5PersistedState(
        mealHypothesis = MealHypothesisState(MealHypothesis.OBSERVING, ageCycles = 3, maxScoreInObserving = 0.7,
            maxEventualBgOffsetInObserving = 80.0, committedInSession = false, lastAgeMs = min(0)),
    )

    @Test fun `a state restored three hours old is reset rather than confirmed on its old peaks`() {
        val d = engine.decide(moderateCycle(min(180)), savedThreeHoursAgo())
        assertThat(d.mealHypothesis).isNotEqualTo(MealHypothesis.CONFIRMED)
        assertThat(d.stateReset).isTrue()
    }

    @Test fun `the same state saved four minutes ago is not reset`() {
        val d = engine.decide(moderateCycle(min(4)), savedThreeHoursAgo())
        assertThat(d.stateReset).isFalse()
    }

    @Test fun `fall-back is tested before confirm - a collapsed current score cannot confirm on peaks`() {
        val observing = MealHypothesisState(MealHypothesis.OBSERVING, ageCycles = 2, maxScoreInObserving = 0.7,
            maxEventualBgOffsetInObserving = 80.0)
        val r = step(observing, score = 0.30, eventualBg = 105.0, targetBg = 100.0, delta = 0.0, deltaAccl = 0.0,
            deltaDeclining = false)
        assertThat(r.state).isEqualTo(MealHypothesis.IDLE)
    }

    @Test fun `peaks older than the window no longer count towards the confirm`() {
        // Strong entry at t0, then a long run of moderate cycles during which the dose-adequacy gate
        // holds the confirm back. When the gate opens 40 minutes later the entry peaks have expired.
        var s = step(MealHypothesisState(), score = 0.7, eventualBg = 180.0, targetBg = 100.0, delta = 6.0,
            deltaAccl = 5.0, deltaDeclining = false, nowMs = min(0))
        assertThat(s.state).isEqualTo(MealHypothesis.OBSERVING)
        for (m in 5..35 step 5) {
            s = step(s, score = 0.45, eventualBg = 110.0, targetBg = 100.0, delta = 2.0, deltaAccl = 0.0,
                deltaDeclining = false, confirmDoseAdequate = false, nowMs = min(m))
            assertThat(s.state).isEqualTo(MealHypothesis.OBSERVING)
        }
        val r = step(s, score = 0.45, eventualBg = 110.0, targetBg = 100.0, delta = 2.0, deltaAccl = 0.0,
            deltaDeclining = false, confirmDoseAdequate = true, nowMs = min(40))
        assertThat(r.state).isEqualTo(MealHypothesis.OBSERVING)
    }

    @Test fun `peaks inside the window still confirm, as Fix 1 and Fix 5 intend`() {
        var s = step(MealHypothesisState(), score = 0.7, eventualBg = 180.0, targetBg = 100.0, delta = 6.0,
            deltaAccl = 5.0, deltaDeclining = false, nowMs = min(0))
        for (m in listOf(5, 10)) {
            s = step(s, score = 0.45, eventualBg = 110.0, targetBg = 100.0, delta = 2.0, deltaAccl = 0.0,
                deltaDeclining = false, nowMs = min(m))
        }
        val r = step(s, score = 0.45, eventualBg = 110.0, targetBg = 100.0, delta = 2.0, deltaAccl = 0.0,
            deltaDeclining = false, nowMs = min(15))
        assertThat(r.state).isEqualTo(MealHypothesis.CONFIRMED)
    }
}
