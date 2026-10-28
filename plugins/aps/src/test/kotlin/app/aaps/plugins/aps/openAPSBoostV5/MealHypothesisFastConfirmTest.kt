package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-06-16 fast-carb fast-path. Single-cycle OBSERVING/IDLE → CONFIRMED when the rise is sharp
 * (delta ≥ FAST_CONFIRM_DELTA) AND accelerating (deltaAccl ≥ FAST_CONFIRM_ACCL) AND score
 * corroborates (≥ FAST_CONFIRM_SCORE) AND awake AND not exercising AND the toggle is on —
 * replay-validated to recover the ~15-min confirm latency that crashed the 2026-06-16 fast carb,
 * without firing on sleep/compression. Retuned 2026-07-03 (Δ 8→6, accl 15→10, score 0.60→0.65 —
 * see MealHypothesis.kt). Pure-function tests on step().
 */
class MealHypothesisFastConfirmTest {

    private fun obs(age: Int = 0, committed: Boolean = false) =
        MealHypothesisState(MealHypothesis.OBSERVING, age, 0.5, 10.0, committed)
    private fun idle() = MealHypothesisState(MealHypothesis.IDLE, 0, 0.0, 0.0, false)

    // strong fast-carb signals
    private val D = 12.0; private val A = 30.0; private val S = 0.7

    @Test fun `fast-confirm fires from OBSERVING in one cycle`() {
        val r = step(obs(age = 0), score = S, eventualBg = 150.0, targetBg = 100.0,
            delta = D, deltaAccl = A, deltaDeclining = false,
            asleep = false, exerciseActive = false, fastConfirmEnabled = true)
        assertThat(r.state).isEqualTo(MealHypothesis.CONFIRMED)
        assertThat(r.committedInSession).isTrue()
    }

    @Test fun `fast-confirm fires straight from IDLE`() {
        val r = step(idle(), score = S, eventualBg = 150.0, targetBg = 100.0,
            delta = D, deltaAccl = A, deltaDeclining = false,
            asleep = false, exerciseActive = false, fastConfirmEnabled = true)
        assertThat(r.state).isEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `does NOT fire while asleep (compression guard)`() {
        val r = step(obs(), S, 150.0, 100.0, D, A, false, asleep = true, exerciseActive = false, fastConfirmEnabled = true)
        assertThat(r.state).isNotEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `does NOT fire while exercising`() {
        val r = step(obs(), S, 150.0, 100.0, D, A, false, asleep = false, exerciseActive = true, fastConfirmEnabled = true)
        assertThat(r.state).isNotEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `does NOT fire when score does not corroborate`() {
        val r = step(obs(), score = 0.45, eventualBg = 150.0, targetBg = 100.0, delta = D, deltaAccl = A,
            deltaDeclining = false, asleep = false, exerciseActive = false, fastConfirmEnabled = true)
        assertThat(r.state).isNotEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `does NOT fire on a slow rise even if accelerating`() {
        val r = step(obs(), S, 150.0, 100.0, delta = 4.0, deltaAccl = A, deltaDeclining = false,
            asleep = false, exerciseActive = false, fastConfirmEnabled = true)
        assertThat(r.state).isNotEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `respects Fix-6 single-confirm guard (no re-confirm in same session)`() {
        val r = step(obs(age = 1, committed = true), S, 150.0, 100.0, D, A, false,
            asleep = false, exerciseActive = false, fastConfirmEnabled = true)
        assertThat(r.state).isNotEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `disabled toggle = unchanged behaviour (young OBSERVING stays OBSERVING)`() {
        // fast signals but toggle off; age 0 < CONFIRM_MIN_OBSERVING_AGE so normal path won't confirm
        val r = step(obs(age = 0), S, 150.0, 100.0, D, A, false,
            asleep = false, exerciseActive = false, fastConfirmEnabled = false)
        assertThat(r.state).isEqualTo(MealHypothesis.OBSERVING)
    }

    @Test fun `default args (no fast-path params) preserve legacy behaviour`() {
        // Existing call sites that don't pass the new args must behave exactly as before.
        val r = step(idle(), score = 0.5, eventualBg = 150.0, targetBg = 100.0, delta = D, deltaAccl = A, deltaDeclining = false)
        assertThat(r.state).isEqualTo(MealHypothesis.OBSERVING)   // score≥ENTER_OBSERVING → OBSERVING, not fast-confirm
    }

    // ── 2026-07-02 post-hypo rescue-carb guard (fastConfirmAllowed) ──────────────────────────

    @Test fun `rescue guard suppresses the fast path within an hour of a hypo`() {
        // 60-min low 55 (rescue-carb rebound): guard off → step must NOT fast-confirm
        assertThat(fastConfirmAllowed(fastCarbConfirmEnabled = true, recentLowBg = 55.0)).isFalse()
        val r = step(idle(), S, 150.0, 100.0, D, A, false, asleep = false, exerciseActive = false,
            fastConfirmEnabled = fastConfirmAllowed(true, 55.0))
        assertThat(r.state).isNotEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `rescue guard boundary - exactly 80 allows, just below blocks`() {
        assertThat(fastConfirmAllowed(true, FAST_CONFIRM_MIN_RECENT_LOW_MGDL)).isTrue()
        assertThat(fastConfirmAllowed(true, FAST_CONFIRM_MIN_RECENT_LOW_MGDL - 0.1)).isFalse()
    }

    @Test fun `rescue guard passes through a disabled toggle`() {
        assertThat(fastConfirmAllowed(fastCarbConfirmEnabled = false, recentLowBg = 150.0)).isFalse()
    }

    @Test fun `no recent low - fast path fires as before`() {
        val r = step(idle(), S, 150.0, 100.0, D, A, false, asleep = false, exerciseActive = false,
            fastConfirmEnabled = fastConfirmAllowed(true, 110.0))
        assertThat(r.state).isEqualTo(MealHypothesis.CONFIRMED)
    }
}
