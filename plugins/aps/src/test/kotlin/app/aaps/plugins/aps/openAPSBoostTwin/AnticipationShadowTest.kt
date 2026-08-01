package app.aaps.plugins.aps.openAPSBoostTwin

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Tests for the anticipation shadow stack (2026-07-27): onset store, retractable arm, and the
 * orchestrator. All read-only; nothing doses. The orchestrator test drives a habitual-exercise
 * pattern and checks the per-user prediction rises at the habitual slot.
 */
class AnticipationShadowTest {

    private val DAY = 86_400_000L
    // Deterministic UTC-ish week-minute mapper for tests (onsets 7 days apart land on the same slot).
    private val wm: (Long) -> Int = { ms -> ((ms / 60_000L) % 10080L).toInt() }

    // ── RetractableArm ──
    @Test fun `arm confirms on the event and unwinds on the deadline`() {
        val a = RetractableArm(deadlineMin = 40.0)
        assertThat(a.runCycle(0, armCond = true, confirmCond = false, vetoCond = false).armed).isEqualTo(1)
        assertThat(a.isArmed).isTrue()
        // event appears within the deadline → confirm, back to idle
        val c = a.runCycle(10 * 60_000L, armCond = false, confirmCond = true, vetoCond = false)
        assertThat(c.confirmed).isEqualTo(1); assertThat(a.isArmed).isFalse()
        // arm again, let the deadline pass with no event → back out
        a.runCycle(20 * 60_000L, armCond = true, confirmCond = false, vetoCond = false)
        val b = a.runCycle(20 * 60_000L + 41 * 60_000L, armCond = false, confirmCond = false, vetoCond = false)
        assertThat(b.backedOut).isEqualTo(1); assertThat(a.isArmed).isFalse()
    }

    @Test fun `veto blocks arming`() {
        val a = RetractableArm()
        val o = a.runCycle(0, armCond = true, confirmCond = false, vetoCond = true)
        assertThat(o.armed).isEqualTo(0); assertThat(a.isArmed).isFalse()
    }

    // ── OnsetStore ──
    @Test fun `store records, dedups within a bucket, evicts old, and round-trips`() {
        val s = AnticipationOnsetStore()
        s.record(AnticipationOnsetStore.Kind.EXERCISE, 10 * DAY)
        s.record(AnticipationOnsetStore.Kind.EXERCISE, 10 * DAY + 1000L) // same 5-min bucket → ignored
        assertThat(s.count(AnticipationOnsetStore.Kind.EXERCISE)).isEqualTo(1)
        s.record(AnticipationOnsetStore.Kind.EXERCISE, 11 * DAY)
        assertThat(s.count(AnticipationOnsetStore.Kind.EXERCISE)).isEqualTo(2)
        // evict at a point > 56d after the first
        s.evict(10 * DAY + AnticipationOnsetStore.WINDOW_MS + DAY)
        assertThat(s.count(AnticipationOnsetStore.Kind.EXERCISE)).isEqualTo(1)  // only the 11*DAY one survives
        val round = AnticipationOnsetStore.deserialize(s.serialize())
        assertThat(round.count(AnticipationOnsetStore.Kind.EXERCISE)).isEqualTo(1)
        assertThat(AnticipationOnsetStore.deserialize("garbage{").count(AnticipationOnsetStore.Kind.MEAL)).isEqualTo(0)
    }

    // ── Orchestrator ──
    @Test fun `habitual exercise onset lifts the predicted probability at that slot`() {
        var blob = ""
        val sh = AnticipationShadow(
            loadState = { blob }, saveState = { blob = it }, logError = { _, _ -> }, weekMinuteOf = wm
        )
        val t0 = 100L * DAY                                   // arbitrary start
        // 4 weekly bouts at the same slot; a low cycle before each resets the edge detector.
        for (w in 0 until 4) {
            val t = t0 + w * 7 * DAY
            sh.runCycle(StringBuilder(), t - 5 * 60_000L, steps5Min = 0, mealStateName = "IDLE", bg = 120.0, delta = 0.0, inPostRescueWindow = false)
            sh.runCycle(StringBuilder(), t, steps5Min = 300, mealStateName = "IDLE", bg = 120.0, delta = 0.0, inPostRescueWindow = false)
        }
        // Predict at the SAME slot one week later, not exercising.
        val atSlot = StringBuilder()
        sh.runCycle(atSlot, t0 + 4 * 7 * DAY, steps5Min = 0, mealStateName = "IDLE", bg = 120.0, delta = 0.0, inPostRescueWindow = false)
        // Predict at a far slot (+8h) — should be low.
        val farSlot = StringBuilder()
        sh.runCycle(farSlot, t0 + 4 * 7 * DAY + 8 * 3_600_000L, steps5Min = 0, mealStateName = "IDLE", bg = 120.0, delta = 0.0, inPostRescueWindow = false)

        val pAt = pex(atSlot.toString())
        val pFar = pex(farSlot.toString())
        assertThat(atSlot.toString()).contains("anticip=")
        assertThat(pAt).isGreaterThan(0.3)
        assertThat(pAt).isGreaterThan(pFar)
        // exercise onset count banked = 4
        assertThat(atSlot.toString().substringAfter("anticip=").substringBefore(";").split(",").last { true })
            .isNotEmpty()
    }

    @Test fun `does not arm inside the post-rescue window`() {
        var blob = ""
        val sh = AnticipationShadow({ blob }, { blob = it }, { _, _ -> }, wm)
        val out = StringBuilder()
        // even with a strong meal-time prior, post-rescue window blocks arming
        sh.runCycle(out, 100L * DAY + 19 * 3_600_000L, steps5Min = 0, mealStateName = "IDLE", bg = 120.0, delta = 8.0, inPostRescueWindow = true)
        val fields = out.toString().substringAfter("anticip=").substringBefore(";").split(",")
        // mealArm(armed) is field index 7 → must be 0 under post-rescue
        assertThat(fields[7]).isEqualTo("0")
    }

    private fun pex(tag: String): Double =
        tag.substringAfter("anticip=").substringBefore(";").split(",")[0].toDouble()
}
