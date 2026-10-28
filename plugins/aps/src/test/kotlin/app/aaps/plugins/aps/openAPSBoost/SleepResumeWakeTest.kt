package app.aaps.plugins.aps.openAPSBoost

import app.aaps.core.data.model.HR
import app.aaps.plugins.aps.openAPSBoost.SleepStateDetector.SleepState
import app.aaps.plugins.aps.openAPSBoost.SleepStateDetector.State
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Transmission-resume wake on a batched HR feed (2026-10-08). Some watches upload overnight HR in
 * batches every 12 to 15 min, mostly one or two samples and every so often several. Each larger
 * batch after a drought of >= 30 min met the resume condition and woke the detector with nobody
 * awake, giving SLEEPING, AWAKE, PRE_SLEEP, SLEEPING cycles all night. A burst now needs steps
 * before the scheduled-wake grace window; inside it, and through the lie-in, the burst alone
 * still wakes.
 */
class SleepResumeWakeTest {

    private val T = SleepStateDetector
    private val MIN = 60_000L
    private val T0 = 1_000_000_000_000L

    /** Batched feed: a batch every 15 min, sizes 2, 2, 5 in turn, timestamps spread back from 1 min before arrival. */
    private val batches: List<Pair<Long, List<HR>>> = (0 until 24).map { k ->
        val arrive = T0 + k * 15 * MIN
        val size = if (k % 3 == 2) 5 else 2
        arrive to (1..size).map { j -> HR(duration = 60_000, timestamp = arrive - j * MIN, beatsPerMinute = 58.0, device = "watch") }
    }

    /** What getHeartRatesFromTime(now - 30 min) returns: samples that have arrived and are under 30 min old. */
    private fun readings(now: Long) = batches.filter { it.first <= now }.flatMap { it.second }
        .filter { it.timestamp > now - 30 * MIN && it.timestamp <= now }

    private fun cycle(prev: State, now: Long, minuteOfDay: Int, stepsToday: Int, steps15: Int = 0, lieInMin: Int = 0) =
        T.evaluate(
            prev,
            SleepStateDetector.Inputs(
                nowMs = now, minuteOfDay = minuteOfDay, hrReadings = readings(now),
                hrResting = 60, stepsLast15Min = steps15, mlMealLikely = null,
                nightStartMin = 1320, nightEndMin = 420, stepsToday = stepsToday,
                sleepInStepsThreshold = if (lieInMin > 0) 250 else 0, sleepInWindowMin = lieInMin
            )
        )

    /** SLEEPING at 01:00 with the last reliable sample 40 min ago, so the drought is established. */
    private fun asleepAt0100() = State(
        state = SleepState.SLEEPING, enteredAtMs = T0 - 2 * 3_600_000L, lastFreshHrSampleMs = T0 - 40 * MIN
    )

    @Test fun `batched HR with 15-min gaps overnight does not wake`() {
        var s = asleepAt0100()
        var ignored = 0
        // 01:00 to 05:00 at five-minute cycles, no steps at all
        for (c in 0..48) {
            val now = T0 + c * 5 * MIN
            val r = cycle(s, now, minuteOfDay = 60 + c * 5, stepsToday = 4200)
            assertThat(r.newState.state).isEqualTo(SleepState.SLEEPING)
            if (r.debug.contains("resume-burst-ignored")) ignored++
            s = r.newState
        }
        // the fixture does reach the old wake condition (burst after drought) several times
        assertThat(ignored).isAtLeast(3)
    }

    @Test fun `burst with steps mid-night still wakes at once`() {
        var s = asleepAt0100()
        var woke: Pair<Int, String?>? = null
        for (c in 0..48) {
            val now = T0 + c * 5 * MIN
            val minute = 60 + c * 5
            val up = minute >= 180                           // out of bed at 03:00, as a 5-sample batch lands
            val r = cycle(s, now, minute, stepsToday = if (up) 4260 else 4200, steps15 = if (up) 60 else 0)
            s = r.newState
            if (s.state == SleepState.AWAKE) { woke = minute to r.wakeReason; break }
        }
        // the 02:15 batch is ignored (no steps); the 03:00 batch arrives with steps and wakes on that cycle
        assertThat(woke).isEqualTo(180 to "resume")
    }

    @Test fun `burst near the scheduled wake wakes without steps`() {
        var s = asleepAt0100()
        var woke: Pair<Int, String?>? = null
        // same feed shifted to 05:30 onwards: inside SLEEP_SCHEDULE_TOLERANCE_MIN of the 07:00 wake
        for (c in 0..24) {
            val now = T0 + c * 5 * MIN
            val minute = 330 + c * 5
            val r = cycle(s, now, minute, stepsToday = 4200)
            s = r.newState
            if (s.state == SleepState.AWAKE) { woke = minute to r.wakeReason; break }
        }
        assertThat(woke).isEqualTo(360 to "resume")          // the first 5-sample batch, 30 min in
    }

    @Test fun `burst in the lie-in wakes without steps`() {
        // past the 07:00 scheduled wake, inside a 2-h lie-in: the morning burst often lands before
        // the steps do, so it still wakes on its own there
        var s = asleepAt0100()
        var woke: Pair<Int, String?>? = null
        for (c in 0..24) {
            val now = T0 + c * 5 * MIN
            val minute = 420 + c * 5
            val r = cycle(s, now, minute, stepsToday = 4200, lieInMin = 120)
            s = r.newState
            if (s.state == SleepState.AWAKE) { woke = minute to r.wakeReason; break }
        }
        assertThat(woke).isEqualTo(450 to "resume")
    }

    @Test fun `genuine wake on HR and steps keeps its latency`() {
        // live feed, near the scheduled wake: HR above the floor plus a step lump wakes two cycles
        // after the rise, as before the change (WAKE_HR_SUSTAIN_CYCLES then wakeHrHysteresisMin)
        var s = State(state = SleepState.SLEEPING, enteredAtMs = T0 - 6 * 3_600_000L, lastFreshHrSampleMs = T0 - MIN)
        var minute = 345
        var cycles = 0
        while (s.state == SleepState.SLEEPING && cycles < 10) {
            val now = T0 + cycles * 5 * MIN
            val r = T.evaluate(s, SleepStateDetector.Inputs(
                nowMs = now, minuteOfDay = minute,
                hrReadings = (1..4).map { HR(duration = 60_000, timestamp = now - it * MIN, beatsPerMinute = 86.0, device = "watch") },
                hrResting = 60, stepsLast15Min = 0, mlMealLikely = null,
                nightStartMin = 1320, nightEndMin = 420, stepsToday = 4200 + cycles * 150
            ))
            s = r.newState; cycles++; minute += 5
            if (s.state == SleepState.AWAKE) assertThat(r.wakeReason).isEqualTo("hr_steps")
        }
        assertThat(s.state).isEqualTo(SleepState.AWAKE)
        assertThat(cycles).isEqualTo(3)
    }
}
