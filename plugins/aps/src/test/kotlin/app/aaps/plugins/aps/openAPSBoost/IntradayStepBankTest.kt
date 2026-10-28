package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Intraday running-max bank (2026-07-07) — the daily-step rollover undercount fix.
 *
 * 07-06 telemetry (recurring DESPITE the hold-higher merge): wear stepsToday peaked 4142 at
 * 22:58 BST, the wear counter reset at DEVICE midnight 23:04 (device TZ ≠ phone-local midnight),
 * and the day closed at 739 (the phone count) — a 5.6× undercount, silent at the rollover cycle.
 * Root cause: day-close read each source's CURRENT count at/after rollover, and wear's candidate
 * was already 0 at exactly the moment it mattered. The bank records per-source per-day running
 * maxima as cycles pass and day-close resolves from the BANK, never from post-reset live reads.
 */
class IntradayStepBankTest {

    private val D = 20_000L   // arbitrary day index

    private fun bank() = DailyStepHistoryTracker.IntradayStepBank()

    @Test fun `wear peaks then resets before close - day records the banked wear max`() {
        // Evening cycles: wear climbing to its 22:58 peak, phone small.
        var b = bank()
        b = DailyStepHistoryTracker.bankCycle(b, D, mapOf("wear" to 3800, "phone" to 700)).bank
        b = DailyStepHistoryTracker.bankCycle(b, D, mapOf("wear" to 4142, "phone" to 739)).bank
        // Device-midnight reset at 23:04: wear reads 0 for the rest of the phone-local day —
        // the bank must hold the peak.
        b = DailyStepHistoryTracker.bankCycle(b, D, mapOf("wear" to 0, "phone" to 739)).bank
        // Phone-local rollover: the closed day comes from the BANK, not the live reads.
        val r = DailyStepHistoryTracker.bankCycle(b, D + 1, mapOf("wear" to 12, "phone" to 3))
        assertThat(r.closedDayTotals.map { it.dayIndex }.distinct()).containsExactly(D)
        val closed = r.closedDayTotals.associate { it.source to it.steps }
        assertThat(closed["wear"]).isEqualTo(4142)
        assertThat(closed["phone"]).isEqualTo(739)
        // New day's bank starts from the rollover cycle's counts only.
        assertThat(r.bank.dayIndex).isEqualTo(D + 1)
        assertThat(r.bank.maxBySource).containsExactly("wear", 12, "phone", 3)

        // …and merged into the history, the completed day resolves to the wear peak (hold-higher
        // + phone-anchored window), exactly what 07-06 should have recorded.
        var multi = DailyStepHistoryTracker.MultiSourceHistory()
        for (t in r.closedDayTotals) multi = DailyStepHistoryTracker.mergeSource(multi, t.source, listOf(t), D + 1)
        val window = DailyStepHistoryTracker.phoneAnchoredWindow(multi, D + 1)
        assertThat(window.history.days[D]!!.steps).isEqualTo(4142)
        assertThat(window.history.days[D]!!.source).isEqualTo("wear")
        assertThat(window.heldNote).isEqualTo("held wear 4142 over phone 739")
    }

    @Test fun `app restart mid-evening - the bank survives via serialization`() {
        var b = bank()
        b = DailyStepHistoryTracker.bankCycle(b, D, mapOf("wear" to 4142, "phone" to 739)).bank
        // Process death + restart: the plugin reloads the bank from preferences.
        val restored = DailyStepHistoryTracker.IntradayStepBank.deserialize(b.serialize())
        assertThat(restored.dayIndex).isEqualTo(D)
        assertThat(restored.maxBySource).containsExactly("wear", 4142, "phone", 739)
        // Post-restart live reads are cold/small — the peak must still close the day.
        var b2 = DailyStepHistoryTracker.bankCycle(restored, D, mapOf("wear" to 0, "phone" to 100)).bank
        val r = DailyStepHistoryTracker.bankCycle(b2, D + 1, emptyMap())
        assertThat(r.closedDayTotals.associate { it.source to it.steps })
            .containsExactly("wear", 4142, "phone", 739)
    }

    @Test fun `phone-higher day unchanged - phone still wins the close`() {
        var b = bank()
        b = DailyStepHistoryTracker.bankCycle(b, D, mapOf("wear" to 2000, "phone" to 8000)).bank
        val r = DailyStepHistoryTracker.bankCycle(b, D + 1, emptyMap())
        var multi = DailyStepHistoryTracker.MultiSourceHistory()
        for (t in r.closedDayTotals) multi = DailyStepHistoryTracker.mergeSource(multi, t.source, listOf(t), D + 1)
        val window = DailyStepHistoryTracker.phoneAnchoredWindow(multi, D + 1)
        assertThat(window.history.days[D]!!.steps).isEqualTo(8000)
        assertThat(window.history.days[D]!!.source).isEqualTo("phone")
    }

    @Test fun `counts only ever raise the banked max, and zero counts are not banked`() {
        var b = bank()
        b = DailyStepHistoryTracker.bankCycle(b, D, mapOf("wear" to 500)).bank
        b = DailyStepHistoryTracker.bankCycle(b, D, mapOf("wear" to 300)).bank   // dip: ignored
        assertThat(b.maxBySource["wear"]).isEqualTo(500)
        b = DailyStepHistoryTracker.bankCycle(b, D, mapOf("wear" to 501, "phone" to 0)).bank
        assertThat(b.maxBySource["wear"]).isEqualTo(501)
        // a source that never reported > 0 does not fabricate a 0-step completed day
        val r = DailyStepHistoryTracker.bankCycle(b, D + 1, emptyMap())
        assertThat(r.closedDayTotals.map { it.source }).containsExactly("wear")
    }

    @Test fun `stale or future bank day is discarded, never banked as history`() {
        // Clock jump / long app death: a bank older than the rolling window (or from the future)
        // must not close into the history.
        val old = DailyStepHistoryTracker.IntradayStepBank(D - DailyStepHistoryTracker.WINDOW_DAYS - 1, mapOf("wear" to 4000))
        assertThat(DailyStepHistoryTracker.bankCycle(old, D, emptyMap()).closedDayTotals).isEmpty()
        val future = DailyStepHistoryTracker.IntradayStepBank(D + 3, mapOf("wear" to 4000))
        assertThat(DailyStepHistoryTracker.bankCycle(future, D, emptyMap()).closedDayTotals).isEmpty()
        // fresh bank state after either discard
        assertThat(DailyStepHistoryTracker.bankCycle(old, D, mapOf("wear" to 7)).bank.maxBySource).containsExactly("wear", 7)
    }

    @Test fun `sources are canonicalised into the bank`() {
        val b = DailyStepHistoryTracker.bankCycle(bank(), D, mapOf("com.garmin.android.apps.connectmobile" to 900)).bank
        assertThat(b.maxBySource).containsExactly("garmin", 900)
    }
}
