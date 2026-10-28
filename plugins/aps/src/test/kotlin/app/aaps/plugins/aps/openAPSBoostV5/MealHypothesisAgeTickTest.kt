package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-07-30 wall-clock age tick.
 *
 * The state machine's ages are cycle COUNTS tuned on a ~5-minute loop. Measured on live data, time
 * from OBSERVING entry to age>=2 is 10.0 min (p10 9.7-10.0) for every 5-minute user and 2.0 min for
 * the 1-minute user — the same thresholds elapsing 5x sooner. AGE_TICK_MS gates the increment on
 * elapsed time so the constants mean the same thing at any cadence.
 */
class MealHypothesisAgeTickTest {

    private fun observing(age: Int = 0, lastAgeMs: Long = 0L) =
        MealHypothesisState(MealHypothesis.OBSERVING, age, 0.5, 20.0, false, lastAgeMs)

    /** Sub-threshold score so the state stays OBSERVING and only the age moves. */
    private fun tick(s: MealHypothesisState, nowMs: Long) = step(
        current = s, score = 0.50, eventualBg = 150.0, targetBg = 100.0,
        delta = 2.0, deltaAccl = 5.0, deltaDeclining = false, nowMs = nowMs
    )

    @Test fun `nowMs 0 ticks every call - legacy callers and tests are unaffected`() {
        var s = observing()
        repeat(3) { s = tick(s, 0L) }
        assertThat(s.ageCycles).isEqualTo(3)
    }

    @Test fun `a 1-minute loop does NOT advance the age every cycle`() {
        var s = observing(lastAgeMs = 1_000_000L)
        for (m in 1..3) s = tick(s, 1_000_000L + m * 60_000L)   // 1, 2, 3 min later
        assertThat(s.ageCycles).isEqualTo(0)                    // under AGE_TICK_MS throughout
    }

    @Test fun `a 1-minute loop reaches age 2 in about 8 minutes, not 2`() {
        var s = observing(lastAgeMs = 1_000_000L)
        var t = 1_000_000L
        var minutesToAge2 = -1
        for (m in 1..15) {
            t += 60_000L
            s = tick(s, t)
            if (s.ageCycles >= 2 && minutesToAge2 < 0) minutesToAge2 = m
        }
        assertThat(minutesToAge2).isEqualTo(8)                  // 2 ticks x 4 min
    }

    @Test fun `a 5-minute loop is unaffected - every cycle still increments`() {
        // Live 5-min users increment about every 4.85-5.0 min; all clear the 4-min tick.
        var s = observing(lastAgeMs = 1_000_000L)
        var t = 1_000_000L
        repeat(3) { t += 291_000L; s = tick(s, t) }             // 4.85 min apart
        assertThat(s.ageCycles).isEqualTo(3)
    }

    @Test fun `the anchor advances only when the age does`() {
        val s0 = observing(lastAgeMs = 1_000_000L)
        val s1 = tick(s0, 1_060_000L)                           // +1 min, no tick
        assertThat(s1.lastAgeMs).isEqualTo(1_000_000L)          // anchor held
        val s2 = tick(s1, 1_300_000L)                           // +5 min from anchor, ticks
        assertThat(s2.ageCycles).isEqualTo(1)
        assertThat(s2.lastAgeMs).isEqualTo(1_300_000L)          // anchor re-stamped
    }

    @Test fun `a hard reset clears the anchor so the next cycle ticks immediately`() {
        val (reset, did) = resetIfNeeded(observing(age = 3, lastAgeMs = 1_000_000L), pumpDisconnected = true)
        assertThat(did).isTrue()
        assertThat(reset.ageCycles).isEqualTo(0)
        assertThat(reset.lastAgeMs).isEqualTo(0L)
    }
}
