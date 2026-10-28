package app.aaps.plugins.aps.openAPSBoost

import app.aaps.plugins.aps.openAPSBoost.DailyStepHistoryTracker.DailyTotal
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * V-activity SHADOW (2026-06-16) — DailyStepHistoryTracker. Pure functions: baseline (median,
 * cold-start guard, excludes recent days), deviation→shadow ISF factor (activity +, inactivity −,
 * smaller), merge/trim, serialize round-trip. SHADOW — nothing here doses.
 */
class DailyStepHistoryTrackerTest {

    private val T = DailyStepHistoryTracker
    private fun hist(vararg pairs: Pair<Long, Int>) =
        DailyStepHistoryTracker.History(pairs.associate { (d, s) -> d to DailyTotal(d, s, "pkg.a") }.toMutableMap())

    @Test fun `cold start - no factor until enough days`() {
        val h = hist(*(1L..5L).map { it to 8000 }.toTypedArray())   // only 5 days < MIN 7
        val f = T.shadowFactors(h, todayIndex = 10)
        assertThat(f.wouldDeltaIsfPct).isEqualTo(0.0)
        assertThat(f.note).isEqualTo("insufficient-history")
        assertThat(T.baseline(h, 10)).isNull()
    }

    @Test fun `baseline is median of completed days excluding the most recent two`() {
        // days 1..10 = 8000, but day 9,10 spiked to 20000 — excluded from baseline (excludeRecent=2 vs today=11)
        val days = (1L..8L).map { it to 8000 }.toTypedArray()
        val h = DailyStepHistoryTracker.History(
            (days.toList() + listOf(9L to 20000, 10L to 20000)).associate { (d, s) -> d to DailyTotal(d, s, "p") }.toMutableMap()
        )
        assertThat(T.baseline(h, todayIndex = 11)).isEqualTo(8000)   // median of the 8000 days, spike excluded
    }

    @Test fun `activity above baseline raises ISF, saturating at 2x`() {
        val base = (1L..10L).map { it to 8000 }
        // yesterday (day 11) + day-before (12? no) ... today=12 → uses day 11 & 10
        val h = DailyStepHistoryTracker.History(
            (base + listOf(11L to 16000)).associate { (d, s) -> d to DailyTotal(d, s, "p") }.toMutableMap()
        )
        val f = T.shadowFactors(h, todayIndex = 12)
        assertThat(f.wouldDeltaIsfPct).isGreaterThan(0.0)
        assertThat(f.note).isEqualTo("activity-load")
        // weighted load = (16000*1 + 8000*0.5)/1.5 = 13333 → ratio 1.67 → ~67% of the way to 2x cap
        assertThat(f.wouldDeltaIsfPct).isWithin(2.0).of(DailyStepHistoryTracker.ACTIVITY_MAX_ISF_PCT * (1.667 - 1.0))
        assertThat(f.wouldDeltaIsfPct).isAtMost(DailyStepHistoryTracker.ACTIVITY_MAX_ISF_PCT)
    }

    @Test fun `huge excess caps at ACTIVITY_MAX`() {
        val base = (1L..10L).map { it to 8000 }
        val h = DailyStepHistoryTracker.History(
            (base + listOf(11L to 40000)).associate { (d, s) -> d to DailyTotal(d, s, "p") }.toMutableMap()
        )
        val f = T.shadowFactors(h, todayIndex = 12)
        assertThat(f.wouldDeltaIsfPct).isWithin(1e-9).of(DailyStepHistoryTracker.ACTIVITY_MAX_ISF_PCT)
    }

    @Test fun `inactivity below baseline lowers ISF and is smaller magnitude than activity`() {
        val base = (1L..10L).map { it to 10000 }
        val h = DailyStepHistoryTracker.History(
            (base + listOf(11L to 1000)).associate { (d, s) -> d to DailyTotal(d, s, "p") }.toMutableMap()
        )
        val f = T.shadowFactors(h, todayIndex = 12)
        assertThat(f.wouldDeltaIsfPct).isLessThan(0.0)
        assertThat(f.note).isEqualTo("inactivity")
        // inactivity cap (8) < activity cap (15) — asymmetric caution
        assertThat(f.wouldDeltaIsfPct).isAtLeast(-DailyStepHistoryTracker.INACTIVITY_MAX_ISF_PCT)
        assertThat(DailyStepHistoryTracker.INACTIVITY_MAX_ISF_PCT).isLessThan(DailyStepHistoryTracker.ACTIVITY_MAX_ISF_PCT)
    }

    @Test fun `at baseline the factor is ~zero`() {
        val h = hist(*(1L..11L).map { it to 9000 }.toTypedArray())
        val f = T.shadowFactors(h, todayIndex = 12)
        assertThat(f.wouldDeltaIsfPct).isWithin(0.5).of(0.0)
    }

    @Test fun `merge keeps only completed days within window and trims old`() {
        var h = DailyStepHistoryTracker.History()
        h = T.merge(h, listOf(DailyTotal(100, 9000, "p"), DailyTotal(101, 9000, "p"), DailyTotal(102, 5000, "p")), todayIndex = 102)
        assertThat(h.days.keys).containsExactly(100L, 101L)   // 102 = today (partial) excluded
        // add an ancient day → trimmed
        h = T.merge(h, listOf(DailyTotal(50, 9999, "p")), todayIndex = 102)
        assertThat(h.days.keys).doesNotContain(50L)          // < 102-28 window
    }

    @Test fun `serialize round-trips`() {
        val h = hist(1L to 8000, 2L to 12000)
        val back = DailyStepHistoryTracker.History.deserialize(h.serialize())
        assertThat(back.days.keys).containsExactly(1L, 2L)
        assertThat(back.days[2L]!!.steps).isEqualTo(12000)
    }

    @Test fun `corrupt blob deserializes to empty`() {
        assertThat(DailyStepHistoryTracker.History.deserialize("{{bad").days).isEmpty()
        assertThat(DailyStepHistoryTracker.History.deserialize("").days).isEmpty()
    }

    @Test fun `dayIndex respects local offset`() {
        // 1970-01-02 00:30 UTC with +1h offset → still epoch-day 1 (01:30 local)
        val ms = 86_400_000L + 30 * 60_000L
        assertThat(T.dayIndex(ms, 3_600_000L)).isEqualTo(1L)
    }
}
