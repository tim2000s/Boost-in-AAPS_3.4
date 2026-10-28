package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-07-30 new-install window on the history backfill.
 *
 * A backfill asks NSClient for a full-sync-flagged load, and that flag bypasses the NsClientAccept*
 * preferences (all of which ship OFF). Each request therefore opens a brief window in which records
 * this phone did not create are accepted — correct for a new install, wrong months later, when a long
 * pump break or a deleted history would otherwise reopen it silently.
 */
class BoostHistorySyncWindowTest {

    private val thin = BoostHistorySync.History(daysWithTdd = 2, bgReadings = 430, treatments = 18)
    private val fat = BoostHistorySync.History(daysWithTdd = 14, bgReadings = 4000, treatments = 300)
    private fun state(attempts: Int = 0, last: Long = 0, firstSeen: Long = 0) =
        BoostHistorySync.State(attempts, last, 0, 0, firstSeen)

    @Test fun `first sight stamps the anchor and requests`() {
        val d = BoostHistorySync.decide(thin, nsAvailable = true, now = 1_000_000L, isoNow = "T", state = state())
        assertThat(d.requestBackfill).isTrue()
        assertThat(d.newState!!.firstSeenMs).isEqualTo(1_000_000L)
    }

    @Test fun `still requests inside the window`() {
        val t0 = 1_000_000L
        val within = t0 + BoostHistorySync.NEW_INSTALL_WINDOW_MS - 1
        val d = BoostHistorySync.decide(thin, true, within, "T", state(attempts = 1, last = 0, firstSeen = t0))
        assertThat(d.requestBackfill).isTrue()
        assertThat(d.newState!!.firstSeenMs).isEqualTo(t0)   // anchor preserved, not restarted
    }

    @Test fun `past the window it never requests again, however thin the history`() {
        val t0 = 1_000_000L
        val after = t0 + BoostHistorySync.NEW_INSTALL_WINDOW_MS + 1
        val d = BoostHistorySync.decide(thin, true, after, "T", state(firstSeen = t0))
        assertThat(d.requestBackfill).isFalse()
        assertThat(d.summary).contains("outside-new-install-window")
    }

    @Test fun `the closure is reported once, then it goes quiet`() {
        val t0 = 1_000_000L
        val after = t0 + BoostHistorySync.NEW_INSTALL_WINDOW_MS + 1
        val first = BoostHistorySync.decide(thin, true, after, "T", state(firstSeen = t0))
        assertThat(first.summary).isNotNull()
        // Same call one cooldown later: still no request, and no repeated breadcrumb.
        val later = after + BoostHistorySync.RETRY_COOLDOWN_MS + 1
        val second = BoostHistorySync.decide(thin, true, later, "T", first.newState!!)
        assertThat(second.requestBackfill).isFalse()
        assertThat(second.summary).isNull()
    }

    @Test fun `an install that starts healthy still gets an anchor, and the window expires unused`() {
        val d = BoostHistorySync.decide(fat, true, 1_000_000L, "T", state())
        assertThat(d.requestBackfill).isFalse()
        assertThat(d.newState!!.firstSeenMs).isEqualTo(1_000_000L)
        // ...and if history degrades long afterwards, no window reopens.
        val after = 1_000_000L + BoostHistorySync.NEW_INSTALL_WINDOW_MS + 1
        assertThat(BoostHistorySync.decide(thin, true, after, "T", d.newState!!).requestBackfill).isFalse()
    }

    @Test fun `closing the gap keeps the anchor so the window cannot restart`() {
        val t0 = 1_000_000L
        val d = BoostHistorySync.decide(fat, true, t0 + 1000, "T", state(attempts = 1, firstSeen = t0))
        assertThat(d.summary).contains("filled")
        assertThat(d.newState!!.firstSeenMs).isEqualTo(t0)
        assertThat(d.newState!!.attempts).isEqualTo(0)
    }
}
