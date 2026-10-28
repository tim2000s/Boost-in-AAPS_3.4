package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-07-30 install-time history-gap detection + bounded Nightscout backfill.
 *
 * Field case: a cross-fork migration onto a fresh AAPS database. TDD read 3.1-4.1 U/day against a
 * true ~20 (which broke dynamic ISF — see DynIsfTddGuardTest for the safety half), and auto-config
 * declined for insufficient history so the user also sat on factory caps. Both symptoms are the same
 * cause: the local database was days old while their Nightscout site was not.
 */
class BoostHistorySyncTest {

    private val iso = "2026-07-30T12:00:00Z"
    private val t0 = 1_785_000_000_000L
    private val fresh = BoostHistorySync.State(attempts = 0, lastAttemptMs = 0, preBgReadings = 0, preTreatments = 0)

    /** A phone that has been looping normally for a fortnight. */
    private val healthy = BoostHistorySync.History(daysWithTdd = 14, bgReadings = 3900, treatments = 620)

    /** The field case: two days on a new database. */
    private val migrated = BoostHistorySync.History(daysWithTdd = 2, bgReadings = 430, treatments = 18)

    // ── detection thresholds ──────────────────────────────────────────────────────────────────────

    @Test fun `a fortnight of normal looping is sufficient`() {
        assertThat(BoostHistorySync.isSufficient(healthy)).isTrue()
    }

    @Test fun `the field case is detected as insufficient`() {
        assertThat(BoostHistorySync.isSufficient(migrated)).isFalse()
    }

    @Test fun `each of the three signals is sufficient on its own to flag a gap`() {
        // Days of TDD short, everything else fine.
        assertThat(BoostHistorySync.isSufficient(healthy.copy(daysWithTdd = 6))).isFalse()
        // CGM short.
        assertThat(BoostHistorySync.isSufficient(healthy.copy(bgReadings = 1499))).isFalse()
        // Treatments short.
        assertThat(BoostHistorySync.isSufficient(healthy.copy(treatments = 49))).isFalse()
    }

    @Test fun `the thresholds sit exactly at the auto-config minimums`() {
        // The point of matching them: anything auto-config would decline is something we try to fix.
        assertThat(BoostHistorySync.MIN_DAYS_WITH_TDD).isEqualTo(BoostV5AutoConfig.MIN_DAYS)
        assertThat(BoostHistorySync.MIN_BG_READINGS).isEqualTo(BoostV5AutoConfig.MIN_BG_READINGS)
        // Boundary is inclusive — exactly at the minimum is enough, one below is not.
        assertThat(BoostHistorySync.isSufficient(BoostHistorySync.History(7, 1500, 50))).isTrue()
        assertThat(BoostHistorySync.isSufficient(BoostHistorySync.History(6, 1500, 50))).isFalse()
    }

    @Test fun `the backfill window covers both consumers and no more`() {
        assertThat(BoostHistorySync.BACKFILL_DAYS).isEqualTo(BoostV5AutoConfig.LOOKBACK_DAYS)
        assertThat(BoostHistorySync.BACKFILL_DAYS).isAtLeast(7L)   // the TDD blend
    }

    // ── the happy path ────────────────────────────────────────────────────────────────────────────

    @Test fun `adequate history stays silent, and stamps the anchor exactly once`() {
        // 2026-07-30: this test previously asserted NO preference write at all for healthy users.
        // That property was deliberately traded for one Long write per install. The new-install
        // window needs an anchor set BEFORE any gap appears — anchoring on first-gap-sighting would
        // let a user who is healthy for months and then degrades (long pump break, deleted history)
        // silently reopen a records-acceptance window, which is exactly what the window prevents.
        // Still no breadcrumb, and still nothing on subsequent cycles.
        val d = BoostHistorySync.decide(healthy, nsAvailable = true, now = t0, isoNow = iso, state = fresh)
        assertThat(d.requestBackfill).isFalse()
        assertThat(d.summary).isNull()                          // no breadcrumb for healthy users
        assertThat(d.newState!!.firstSeenMs).isEqualTo(t0)      // one write: the anchor
        assertThat(d.newState!!.attempts).isEqualTo(0)
        // Second cycle, anchor already set -> genuinely nothing.
        assertThat(BoostHistorySync.decide(healthy, true, t0 + 300_000, iso, d.newState!!).newState).isNull()
    }

    @Test fun `a gap plus a configured Nightscout requests the bounded backfill`() {
        val d = BoostHistorySync.decide(migrated, nsAvailable = true, now = t0, isoNow = iso, state = fresh)
        assertThat(d.requestBackfill).isTrue()
        assertThat(d.summary).isEqualTo("requested:14d,attempt=1/3,days=2/7,bg=430/1500,tr=18/50@$iso")
        assertThat(d.newState!!.attempts).isEqualTo(1)
        assertThat(d.newState!!.lastAttemptMs).isEqualTo(t0)
        // Pre-counts snapshotted so the eventual outcome line can report a real delta.
        assertThat(d.newState!!.preBgReadings).isEqualTo(430)
        assertThat(d.newState!!.preTreatments).isEqualTo(18)
    }

    @Test fun `once the gap closes the outcome is reported once, with deltas, then goes quiet`() {
        val after = BoostHistorySync.decide(
            healthy, nsAvailable = true, now = t0 + 90 * 60_000, isoNow = iso,
            state = BoostHistorySync.State(attempts = 1, lastAttemptMs = t0, preBgReadings = 430, preTreatments = 18)
        )
        assertThat(after.requestBackfill).isFalse()
        assertThat(after.summary).isEqualTo("filled:14d,treatments=+602,bg=+3470@$iso")
        // Counters zeroed — that is what closes the episode. The first-seen anchor is deliberately
        // KEPT: zeroing it would let the new-install window restart if history later degraded.
        assertThat(after.newState!!.attempts).isEqualTo(0)
        assertThat(after.newState!!.preBgReadings).isEqualTo(0)
        assertThat(after.newState!!.preTreatments).isEqualTo(0)
        assertThat(after.newState!!.firstSeenMs).isEqualTo(t0 + 90 * 60_000)
        // ...and the very next cycle says nothing more, so the "filled" line simply persists.
        // Carry the CLOSED state through (not `fresh`), or the anchor would be re-stamped.
        val next = BoostHistorySync.decide(healthy, nsAvailable = true, now = t0 + 95 * 60_000, isoNow = iso, state = after.newState!!)
        assertThat(next.summary).isNull()
        assertThat(next.newState).isNull()
    }

    // ── skip and failure paths ────────────────────────────────────────────────────────────────────

    @Test fun `no Nightscout configured - records why, and does not consume an attempt`() {
        val d = BoostHistorySync.decide(migrated, nsAvailable = false, now = t0, isoNow = iso, state = fresh)
        assertThat(d.requestBackfill).isFalse()
        assertThat(d.summary).isEqualTo("skipped:ns-unavailable,days=2/7,bg=430/1500,tr=18/50@$iso")
        // Only the cooldown clock moves: configuring Nightscout later still gets a full 3 attempts.
        assertThat(d.newState!!.attempts).isEqualTo(0)
        assertThat(d.newState!!.lastAttemptMs).isEqualTo(t0)
    }

    @Test fun `the cooldown stops a thin install asking on every five-minute cycle`() {
        val justAfter = BoostHistorySync.decide(
            migrated, nsAvailable = true, now = t0 + 5 * 60_000, isoNow = iso,
            state = BoostHistorySync.State(attempts = 1, lastAttemptMs = t0, preBgReadings = 430, preTreatments = 18)
        )
        assertThat(justAfter.requestBackfill).isFalse()
        assertThat(justAfter.summary).isNull()   // and does not churn the breadcrumb either
        // Anchor stamped once (the fixture state carries firstSeenMs = 0); nothing else moves.
        assertThat(justAfter.newState!!.attempts).isEqualTo(1)
        assertThat(justAfter.newState!!.lastAttemptMs).isEqualTo(t0)

        val afterCooldown = BoostHistorySync.decide(
            migrated, nsAvailable = true, now = t0 + BoostHistorySync.RETRY_COOLDOWN_MS, isoNow = iso,
            state = BoostHistorySync.State(attempts = 1, lastAttemptMs = t0, preBgReadings = 430, preTreatments = 18)
        )
        assertThat(afterCooldown.requestBackfill).isTrue()
        assertThat(afterCooldown.newState!!.attempts).isEqualTo(2)
    }

    @Test fun `the cooldown also throttles the skip path`() {
        val d = BoostHistorySync.decide(
            migrated, nsAvailable = false, now = t0 + 60_000, isoNow = iso,
            state = fresh.copy(lastAttemptMs = t0)
        )
        assertThat(d.summary).isNull()
        // Only the first-seen anchor is written (fresh has firstSeenMs = 0); no breadcrumb, no attempt.
        assertThat(d.newState!!.firstSeenMs).isEqualTo(t0 + 60_000)
        assertThat(d.newState!!.attempts).isEqualTo(0)
        // With the anchor already set, the same call writes nothing at all.
        assertThat(BoostHistorySync.decide(migrated, false, t0 + 60_000, iso, d.newState!!).newState).isNull()
    }

    @Test fun `attempts are capped - a site with genuinely no history is left alone`() {
        var state = fresh
        var now = t0
        repeat(BoostHistorySync.MAX_ATTEMPTS) {
            val d = BoostHistorySync.decide(migrated, nsAvailable = true, now = now, isoNow = iso, state = state)
            assertThat(d.requestBackfill).isTrue()
            state = d.newState!!
            now += BoostHistorySync.RETRY_COOLDOWN_MS
        }
        assertThat(state.attempts).isEqualTo(BoostHistorySync.MAX_ATTEMPTS)

        val exhausted = BoostHistorySync.decide(migrated, nsAvailable = true, now = now, isoNow = iso, state = state)
        assertThat(exhausted.requestBackfill).isFalse()
        assertThat(exhausted.summary).isEqualTo("exhausted:3,days=2/7,bg=430/1500,tr=18/50@$iso")
        // Still capped a cooldown later, and forever after.
        val stillExhausted = BoostHistorySync.decide(
            migrated, nsAvailable = true, now = now + 10 * BoostHistorySync.RETRY_COOLDOWN_MS, isoNow = iso,
            state = exhausted.newState!!
        )
        assertThat(stillExhausted.requestBackfill).isFalse()
    }

    @Test fun `a partial backfill still counts as filled if it crossed the thresholds`() {
        // NS only had 9 days. That is enough for the 7-day TDD blend and for auto-config, so the
        // episode closes rather than burning the remaining attempts on data that does not exist.
        val partial = BoostHistorySync.History(daysWithTdd = 9, bgReadings = 2500, treatments = 400)
        val d = BoostHistorySync.decide(
            partial, nsAvailable = true, now = t0 + 60 * 60_000, isoNow = iso,
            state = BoostHistorySync.State(attempts = 1, lastAttemptMs = t0, preBgReadings = 430, preTreatments = 18)
        )
        assertThat(d.summary).isEqualTo("filled:14d,treatments=+382,bg=+2070@$iso")
        assertThat(d.newState!!.attempts).isEqualTo(0)
    }

    @Test fun `a backfill that recovered nothing does not report a bogus positive delta`() {
        // Counts unchanged and still short -> no "filled" line; it stays in the retry loop.
        val d = BoostHistorySync.decide(
            migrated, nsAvailable = true, now = t0 + BoostHistorySync.RETRY_COOLDOWN_MS, isoNow = iso,
            state = BoostHistorySync.State(attempts = 1, lastAttemptMs = t0, preBgReadings = 430, preTreatments = 18)
        )
        assertThat(d.summary).doesNotContain("filled")
        assertThat(d.requestBackfill).isTrue()
    }

    @Test fun `an empty database is handled, not divided by`() {
        val empty = BoostHistorySync.History(daysWithTdd = 0, bgReadings = 0, treatments = 0)
        val d = BoostHistorySync.decide(empty, nsAvailable = true, now = t0, isoNow = iso, state = fresh)
        assertThat(d.requestBackfill).isTrue()
        assertThat(d.summary).contains("days=0/7,bg=0/1500,tr=0/50")
    }
}
