package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * V6 MealTimeLearner — clustering of V5-CONFIRMED meal commits into habitual meal modes, and the
 * pre-meal lead-window query that drives the anticipatory low target. Pure functions, tested
 * directly with offset = 0 so an event's UTC ms maps 1:1 to its local minute-of-day.
 */
class MealTimeLearnerTest {

    private val offset = 0L
    private val dayMs = 24L * 60L * 60L * 1000L

    /** Event at `minute` of local day `day`, with offset 0 → msToMinOfDay == minute, dayIndex == day. */
    private fun ev(day: Long, minute: Int): Long = day * dayMs + minute * 60_000L

    private fun historyOf(vararg events: Long) =
        MealTimeLearner.History(events.toMutableList())

    // ─── empty / corrupt ──────────────────────────────────────────────────────

    @Test fun `empty history yields no modes and no window`() {
        val h = MealTimeLearner.History()
        assertThat(MealTimeLearner.modes(h, offset)).isEmpty()
        assertThat(MealTimeLearner.preMealWindow(h, nowMin = 420, localOffsetMs = offset, leadMaxMin = 60)).isNull()
    }

    @Test fun `corrupt blob deserializes to empty history`() {
        assertThat(MealTimeLearner.History.deserialize("not json {{").events).isEmpty()
        assertThat(MealTimeLearner.History.deserialize("").events).isEmpty()
    }

    @Test fun `serialize round-trips`() {
        val h = historyOf(ev(1, 480), ev(2, 485))
        val back = MealTimeLearner.History.deserialize(h.serialize())
        assertThat(back.events).containsExactly(ev(1, 480), ev(2, 485)).inOrder()
    }

    // ─── confidence thresholds ──────────────────────────────────────────────────

    @Test fun `fewer than MIN_SESSIONS events yields no mode`() {
        // 5 breakfast events (< 6) → not trusted
        val h = historyOf(ev(1, 480), ev(2, 481), ev(3, 479), ev(4, 482), ev(5, 478))
        assertThat(MealTimeLearner.modes(h, offset)).isEmpty()
    }

    @Test fun `enough events but too few distinct days yields no mode`() {
        // 6 events but all on 3 days (< MIN_DISTINCT_DAYS = 4) → a binge day can't make a mode
        val h = historyOf(
            ev(1, 480), ev(1, 485), ev(2, 478), ev(2, 482), ev(3, 479), ev(3, 481)
        )
        assertThat(MealTimeLearner.modes(h, offset)).isEmpty()
    }

    @Test fun `6 events over 6 days forms one trusted mode near the cluster centre`() {
        val h = historyOf(
            ev(1, 478), ev(2, 482), ev(3, 480), ev(4, 479), ev(5, 481), ev(6, 480)
        )
        val modes = MealTimeLearner.modes(h, offset)
        assertThat(modes).hasSize(1)
        assertThat(modes[0].centreMin).isWithin(2).of(480)   // ~08:00
        assertThat(modes[0].distinctDays).isEqualTo(6)
    }

    @Test fun `two separated clusters form two modes`() {
        val days = (1L..6L)
        val breakfast = days.map { ev(it, 480) }            // 08:00
        val dinner = days.map { ev(it, 1140) }              // 19:00
        val h = MealTimeLearner.History((breakfast + dinner).toMutableList())
        val centres = MealTimeLearner.modes(h, offset).map { it.centreMin }.sorted()
        assertThat(centres).hasSize(2)
        assertThat(centres[0]).isWithin(2).of(480)
        assertThat(centres[1]).isWithin(2).of(1140)
    }

    // ─── circular wrap ───────────────────────────────────────────────────────────

    @Test fun `cluster straddling midnight is centred near zero not noon`() {
        // events at 23:50, 23:55, 23:58, 00:05, 00:08, 00:10 across 6 days
        val mins = listOf(1430, 1435, 1438, 5, 8, 10)
        val h = MealTimeLearner.History(mins.mapIndexed { i, m -> ev((i + 1).toLong(), m) }.toMutableList())
        val modes = MealTimeLearner.modes(h, offset)
        assertThat(modes).hasSize(1)
        // circular mean should be within a few minutes of midnight (0 / 1440), NOT ~720
        val c = modes[0].centreMin
        assertThat(c < 30 || c > 1410).isTrue()
    }

    // ─── pre-meal lead window edges ───────────────────────────────────────────────

    private fun breakfastHistory() = MealTimeLearner.History(
        (1L..6L).map { ev(it, 480) }.toMutableList()    // mode at 08:00
    )

    @Test fun `window opens leadMax before and closes 45 before the meal`() {
        // mode centre ≈ 08:00 (480, may round to 479). leadMax = 60 → window covers ~[45, 60] min
        // before the meal. Use interior points (margin ≥ 2 min) to stay robust to ±1 centre rounding.
        val h = breakfastHistory()
        assertThat(MealTimeLearner.preMealWindow(h, 425, offset, 60)).isNotNull()   // ~54 min before — inside
        assertThat(MealTimeLearner.preMealWindow(h, 432, offset, 60)).isNotNull()   // ~47 min before — inside
        assertThat(MealTimeLearner.preMealWindow(h, 470, offset, 60)).isNull()      // ~10 min before — too close
        assertThat(MealTimeLearner.preMealWindow(h, 414, offset, 60)).isNull()      // ~65 min before — too early
        assertThat(MealTimeLearner.preMealWindow(h, 480, offset, 60)).isNull()      // at the meal — past window
    }

    @Test fun `minutesBeforeMeal is reported`() {
        val hit = MealTimeLearner.preMealWindow(breakfastHistory(), 425, offset, 60)
        assertThat(hit).isNotNull()
        // centre ≈ 480 (may round to 479) → 54..55 min before
        assertThat(hit!!.minutesBeforeMeal).isIn(54..55)
    }

    @Test fun `low leadMax setting still yields a usable window (min-span guaranteed)`() {
        // leadMax = 30 → open clamped to floor(45)+min-span(10) = 55 → window covers ~[45,55] before.
        val h = breakfastHistory()
        assertThat(MealTimeLearner.preMealWindow(h, 427, offset, 30)).isNotNull()   // ~52 min before — inside
        assertThat(MealTimeLearner.preMealWindow(h, 420, offset, 30)).isNull()      // ~59 min before — before open
        assertThat(MealTimeLearner.preMealWindow(h, 470, offset, 30)).isNull()      // ~10 min before — too close
    }

    // ─── record + prune ───────────────────────────────────────────────────────────

    @Test fun `record appends and prunes events older than the 60-day window`() {
        val now = 100L * dayMs
        val old = now - 61L * dayMs        // outside 60-day window
        val recent = now - 3L * dayMs
        var h = MealTimeLearner.History(mutableListOf(old, recent))
        h = MealTimeLearner.record(h, now)
        assertThat(h.events).containsExactly(recent, now).inOrder()   // old pruned, new kept
    }

    // ─── night filter (2026-10-08, audit #8) ─────────────────────────────────────

    @Test fun `night window wrapping midnight - both sides are inside, the end is not`() {
        // 22:00 to 07:00
        assertThat(MealTimeLearner.inNightMinutes(23 * 60 + 30, 1320, 420)).isTrue()
        assertThat(MealTimeLearner.inNightMinutes(3 * 60, 1320, 420)).isTrue()
        assertThat(MealTimeLearner.inNightMinutes(0, 1320, 420)).isTrue()
        assertThat(MealTimeLearner.inNightMinutes(420, 1320, 420)).isFalse()
        assertThat(MealTimeLearner.inNightMinutes(12 * 60, 1320, 420)).isFalse()
    }

    @Test fun `night window inside one day and equal times`() {
        // 01:00 to 06:00, no wrap
        assertThat(MealTimeLearner.inNightMinutes(3 * 60, 60, 360)).isTrue()
        assertThat(MealTimeLearner.inNightMinutes(23 * 60, 60, 360)).isFalse()
        // equal times are an empty window, as NightWindow.contains has it
        assertThat(MealTimeLearner.inNightMinutes(3 * 60, 360, 360)).isFalse()
    }

    @Test fun `learned overnight sessions are dropped and daytime sessions kept`() {
        // Six 04:30 sessions on six days form a trusted mode; filtered, they cannot.
        val night = (1L..6L).map { ev(it, 4 * 60 + 30) }
        val day = (1L..6L).map { ev(it, 8 * 60) }
        val h = MealTimeLearner.History((night + day).toMutableList())
        assertThat(MealTimeLearner.preMealWindow(h, 3 * 60 + 40, offset, 60)).isNotNull()
        val f = MealTimeLearner.withoutNightEvents(h, nightStartMin = 22 * 60, nightEndMin = 7 * 60, localOffsetMs = offset)
        assertThat(f.events).containsExactlyElementsIn(day)
        // the lowered target can no longer open at 03:40 for the 04:30 mode
        assertThat(MealTimeLearner.preMealWindow(f, 3 * 60 + 40, offset, 60)).isNull()
        // the breakfast mode survives
        assertThat(MealTimeLearner.preMealWindow(f, 7 * 60 + 5, offset, 60)).isNotNull()
    }
}
