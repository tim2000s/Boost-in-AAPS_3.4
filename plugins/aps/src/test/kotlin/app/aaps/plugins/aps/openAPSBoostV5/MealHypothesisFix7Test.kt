package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Fix 7 (2026-06-12) — multi-phase meal re-engagement.
 *
 * On a two-phase meal the mid-meal deceleration sends COMMITTED → RECOVERING; RECOVERING previously
 * had no path back to active dosing, so V5 dribbled at 0.4× through the whole second climb (BG ran
 * to 192). Fix 7 adds a RECOVERING → COMMITTED transition when the meal genuinely re-accelerates
 * while still well above target. [step] is a pure function, tested directly.
 */
class MealHypothesisFix7Test {

    private fun recovering(age: Int) =
        MealHypothesisState(MealHypothesis.RECOVERING, ageCycles = age, committedInSession = true)

    @Test fun `re-accelerating well above target re-engages COMMITTED`() {
        val next = step(
            current = recovering(age = 1),
            score = 0.5, eventualBg = 170.0, targetBg = 99.0,  // offset 71 > 20
            delta = 8.0, deltaAccl = 15.0, deltaDeclining = false,
        )
        assertThat(next.state).isEqualTo(MealHypothesis.COMMITTED)
        // Fix 6 preserved: no new CONFIRMED commit-shot, session lock stays set.
        assertThat(next.committedInSession).isTrue()
    }

    @Test fun `re-acceleration near target does NOT re-engage`() {
        val next = step(
            current = recovering(age = 2),
            score = 0.5, eventualBg = 110.0, targetBg = 99.0,  // offset 11 <= 20
            delta = 8.0, deltaAccl = 15.0, deltaDeclining = false,
        )
        assertThat(next.state).isEqualTo(MealHypothesis.RECOVERING)
    }

    @Test fun `same-cycle re-acceleration is blocked by min-age (no flicker)`() {
        val next = step(
            current = recovering(age = 0),
            score = 0.5, eventualBg = 170.0, targetBg = 99.0,
            delta = 8.0, deltaAccl = 15.0, deltaDeclining = false,
        )
        assertThat(next.state).isEqualTo(MealHypothesis.RECOVERING)
    }

    @Test fun `weak rise below accl threshold does NOT re-engage`() {
        val next = step(
            current = recovering(age = 2),
            score = 0.5, eventualBg = 170.0, targetBg = 99.0,
            delta = 4.0, deltaAccl = 6.0, deltaDeclining = false,  // accl 6 < 10
        )
        assertThat(next.state).isEqualTo(MealHypothesis.RECOVERING)
    }

    // ─── No-regression: existing RECOVERING exits unchanged ───

    // This test used to pin that the RECOVERING to IDLE exit also cleared the session lock. That was
    // the defect in dose-path audit item 7 (2026-10-08): the exit fires on one negative delta, the
    // trough between two phases of a meal, and clearing the lock there let the fast path CONFIRM a
    // second time. With a clock the lock now outlives the exit (see MealSessionLockTest); only a
    // caller with no clock keeps the old clearing.
    @Test fun `declining BG still exits RECOVERING to IDLE and keeps the session lock`() {
        val next = step(
            current = recovering(age = 2),
            score = 0.5, eventualBg = 170.0, targetBg = 99.0,
            delta = -2.0, deltaAccl = 15.0, deltaDeclining = false,  // delta<0 wins
            nowMs = 1_800_000_000_000L,
        )
        assertThat(next.state).isEqualTo(MealHypothesis.IDLE)
        assertThat(next.committedInSession).isTrue()
    }

    @Test fun `with no clock the exit clears the lock as before`() {
        val next = step(
            current = recovering(age = 2),
            score = 0.5, eventualBg = 170.0, targetBg = 99.0,
            delta = -2.0, deltaAccl = 15.0, deltaDeclining = false,
        )
        assertThat(next.state).isEqualTo(MealHypothesis.IDLE)
        assertThat(next.committedInSession).isFalse()
    }

    @Test fun `gentle positive drift stays in RECOVERING`() {
        val next = step(
            current = recovering(age = 2),
            score = 0.5, eventualBg = 170.0, targetBg = 99.0,
            delta = 1.0, deltaAccl = 2.0, deltaDeclining = false,  // no re-accel, delta>=0, score ok
        )
        assertThat(next.state).isEqualTo(MealHypothesis.RECOVERING)
    }

    @Test fun `COMMITTED back-off to RECOVERING is unchanged`() {
        val next = step(
            current = MealHypothesisState(MealHypothesis.COMMITTED, ageCycles = 3, committedInSession = true),
            score = 0.5, eventualBg = 160.0, targetBg = 99.0,
            delta = 4.0, deltaAccl = -8.0, deltaDeclining = true,  // decel + declining
        )
        assertThat(next.state).isEqualTo(MealHypothesis.RECOVERING)
    }
}
