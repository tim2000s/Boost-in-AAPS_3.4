package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-10-08, V6 review item 6: the sustained-score early confirm's "two consecutive cycles" was
 * counted per invocation, so a one-minute loop, or a re-invoke seconds after the previous one, met it
 * almost at once. With a clock the streak now needs a confirm-strength run of at least AGE_TICK_MS.
 * Driven through decide() with only the API that existed before the fix.
 */
class ScoreStreakCadenceTest {

    private val t0 = 1_800_000_000_000L
    private fun sec(s: Int) = t0 + s * 1000L
    private val engine = DetermineBasalBoostV5()

    /** A cycle whose own score is confirm-strength and whose eventualBG is well over target. */
    private fun strong(now: Long) = V5Inputs(
        delta = 8.0, shortAvgDelta = 7.0, deltaAccl = 5.0, bg = 160.0, eventualBg = 220.0, targetBg = 100.0,
        maxDelta = 8.0, minGuardBg = 150.0, minGuardThreshold = 80.0, deltaHistory = listOf(6.0, 7.0, 8.0),
        iob = 0.5, maxIob = 10.0, baseInsulinReq = 2.0, roundSmbTo = 0.05, enableSmbPreChecks = true,
        mlHypoRisk = null, mlMealLikely = 0.95, recentLowBg = 120.0, cumulativeRise30min = 60.0, hour = 12,
        exerciseActive = false, inPostExerciseWindow = false, nowMs = now,
    )

    /** OBSERVING at age 1, one tick short of the standard gate, so only the early path can confirm. */
    private fun observingAge1(lastAgeMs: Long) = V5PersistedState(
        mealHypothesis = MealHypothesisState(MealHypothesis.OBSERVING, ageCycles = 1, maxScoreInObserving = 0.7,
            maxEventualBgOffsetInObserving = 100.0, lastAgeMs = lastAgeMs),
    )

    @Test fun `precondition - the strong cycle scores at confirm strength`() {
        assertThat(engine.decide(strong(sec(0)), observingAge1(sec(0))).score).isAtLeast(CONFIRM_SCORE)
    }

    @Test fun `a re-invoke thirty seconds later does not count as a second cycle`() {
        val first = engine.decide(strong(sec(0)), observingAge1(sec(-60)))
        assertThat(first.mealHypothesis).isEqualTo(MealHypothesis.OBSERVING)
        val second = engine.decide(strong(sec(30)), first.newPersistedState)
        assertThat(second.mealHypothesis).isEqualTo(MealHypothesis.OBSERVING)
    }

    @Test fun `on a one-minute loop the early path waits for four minutes of confirm-strength scores`() {
        var p = observingAge1(sec(-60))
        val states = mutableListOf<MealHypothesis>()
        for (m in 0..4) {
            val d = engine.decide(strong(sec(m * 60)), p)
            states += d.mealHypothesis
            p = d.newPersistedState
            if (d.mealHypothesis == MealHypothesis.CONFIRMED) break
        }
        // minutes 0 to 3 are under four minutes of run; the age tick (also four minutes) and the
        // streak open together at minute 4.
        assertThat(states.take(4)).doesNotContain(MealHypothesis.CONFIRMED)
        assertThat(states.last()).isEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `on a five-minute loop the previous cycle still counts, as before`() {
        // Start from age 0 so that the standard age gate cannot be what confirms.
        val fresh = V5PersistedState(mealHypothesis = MealHypothesisState(MealHypothesis.OBSERVING, ageCycles = 0,
            maxScoreInObserving = 0.7, maxEventualBgOffsetInObserving = 100.0, lastAgeMs = sec(-300)))
        val a = engine.decide(strong(sec(0)), fresh)
        assertThat(a.mealHypothesis).isEqualTo(MealHypothesis.OBSERVING)
        val b = engine.decide(strong(sec(300)), a.newPersistedState)
        // age 1 with a streak from the previous five-minute cycle: the early path confirms.
        assertThat(b.mealHypothesis).isEqualTo(MealHypothesis.CONFIRMED)
    }
}
