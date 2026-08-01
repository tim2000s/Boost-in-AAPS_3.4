package app.aaps.plugins.aps.openAPSBoostTwin

import app.aaps.plugins.aps.openAPSBoostTwin.AnticipationHabitModel.Companion.WEEK_MIN
import app.aaps.plugins.aps.openAPSBoostTwin.AnticipationHabitModel.Companion.defaultExercisePrior
import app.aaps.plugins.aps.openAPSBoostTwin.AnticipationHabitModel.Companion.defaultMealPrior
import app.aaps.plugins.aps.openAPSBoostTwin.AnticipationHabitModel.Companion.weekMinute
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Pure-logic tests for the per-user onset-hazard model (KAIROS anticipation shadow, 2026-07-27).
 * The model doses nothing; these pin the hazard arithmetic that drives the shadow telemetry.
 */
class AnticipationHabitModelTest {

    private val model = AnticipationHabitModel()

    /** A person who exercises every weekday at 17:00 → high hazard there, near-zero far from it. */
    @Test fun `habitual weekday-evening onset concentrates hazard at that slot`() {
        val wm = weekMinute(0, 17 * 60)                       // Monday 17:00
        // 5 weekdays x 4 recent weeks = 20 onsets, all at ~the same clock slot.
        val mins = ArrayList<Int>(); val ages = ArrayList<Double>()
        for (week in 0 until 4) for (d in 0 until 5) {
            mins.add(weekMinute(d, 17 * 60))
            ages.add(week * 7.0 + 0.1)
        }
        val f = model.fit(mins.toIntArray(), ages.toDoubleArray(), historyDays = 28.0,
                          prior = defaultExercisePrior())
        val pAt = model.predict(f, wm, minsSinceLastOnset = 999.0)!!
        val pFar = model.predict(f, weekMinute(0, 3 * 60), minsSinceLastOnset = 999.0)!! // Mon 03:00
        assertThat(pAt).isGreaterThan(0.5)
        assertThat(pFar).isLessThan(0.15)
        assertThat(pAt).isGreaterThan(pFar * 3)
        assertThat(f.source).isAnyOf("peruser", "blend")      // 20 events → blending toward per-user
    }

    @Test fun `refractory factor suppresses right after an onset`() {
        val mins = IntArray(20) { weekMinute(it % 5, 17 * 60) }
        val ages = DoubleArray(20) { (it / 5) * 7.0 + 0.1 }
        val f = model.fit(mins, ages, 28.0, defaultExercisePrior())
        val wm = weekMinute(0, 17 * 60)
        val fresh = model.predict(f, wm, minsSinceLastOnset = 5.0)!!   // 5 min after an onset
        val settled = model.predict(f, wm, minsSinceLastOnset = 999.0)!!
        assertThat(fresh).isLessThan(settled)
        assertThat(fresh).isWithin(1e-9).of(settled * (5.0 / 60.0))
    }

    @Test fun `cold start leans on the prior`() {
        val f = model.fit(IntArray(0), DoubleArray(0), historyDays = 1.0, prior = defaultMealPrior())
        assertThat(f.source).isEqualTo("prior")
        // Dinner slot (19:00) should carry the prior bump; 03:00 should be low.
        val dinner = model.predict(f, weekMinute(2, 19 * 60), 999.0)!!
        val night = model.predict(f, weekMinute(2, 3 * 60), 999.0)!!
        assertThat(dinner).isGreaterThan(night)
        assertThat(dinner).isGreaterThan(0.1)
    }

    @Test fun `unfitted predict returns null`() {
        assertThat(model.predict(null, 0, 0.0)).isNull()
    }

    @Test fun `weekMinute wraps and bounds`() {
        assertThat(weekMinute(0, 0)).isEqualTo(0)
        assertThat(weekMinute(6, 23 * 60 + 59)).isEqualTo(WEEK_MIN - 1)
        assertThat(weekMinute(9, 99 * 60)).isIn(0 until WEEK_MIN)   // out-of-range coerced
    }

    @Test fun `meal prior has three daily bumps`() {
        val p = defaultMealPrior()
        val slots = WEEK_MIN / 30
        // Tuesday breakfast/lunch/dinner slots exceed a night slot.
        fun slotOf(d: Int, minute: Int) = (d * 24 * 60 + minute) / 30 % slots
        val night = p[slotOf(1, 3 * 60)]
        for (m in listOf(8 * 60, 13 * 60, 19 * 60)) assertThat(p[slotOf(1, m)]).isGreaterThan(night)
    }
}
