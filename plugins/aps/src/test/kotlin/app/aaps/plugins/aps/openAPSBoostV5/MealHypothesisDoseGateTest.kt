package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-07-02 — OBSERVING→CONFIRMED dose-adequacy gate (committedCap anchor).
 *
 * The single per-session CONFIRMED commit-shot must be worth more than one routine COMMITTED hold
 * (committedCapU). The caller (DetermineBasalBoostV5.decide) computes
 *   confirmDoseAdequate = (budget × CONFIRMED mult) > min(committedCapU, 0.8 × confirmedCapU)
 * and threads it into step(). These are pure-function tests on step(): the gate applies to the NORMAL
 * path only; the fast-carb fast-path is intentionally exempt.
 */
class MealHypothesisDoseGateTest {

    // An OBSERVING run that already satisfies the score + eventualBG-offset peaks and the age gate, so
    // the ONLY remaining variable is confirmDoseAdequate.
    private fun observedReady() =
        MealHypothesisState(MealHypothesis.OBSERVING, ageCycles = 2, maxScoreInObserving = 0.60, maxEventualBgOffsetInObserving = 40.0, committedInSession = false)

    private val score = 0.60
    private val eventualBg = 150.0
    private val targetBg = 100.0

    @Test fun `confirms when the shot is adequate`() {
        val r = step(observedReady(), score, eventualBg, targetBg, delta = 6.0, deltaAccl = 2.0,
            deltaDeclining = false, confirmDoseAdequate = true)
        assertThat(r.state).isEqualTo(MealHypothesis.CONFIRMED)
    }

    @Test fun `does NOT confirm when the shot is inadequate - holds in OBSERVING`() {
        val r = step(observedReady(), score, eventualBg, targetBg, delta = 6.0, deltaAccl = 2.0,
            deltaDeclining = false, confirmDoseAdequate = false)
        // All other confirm predicates pass; only the dose floor blocks it. Score is above the
        // fall-back threshold, so it holds in OBSERVING rather than dropping to IDLE.
        assertThat(r.state).isEqualTo(MealHypothesis.OBSERVING)
    }

    @Test fun `default arg preserves legacy behaviour (adequate)`() {
        val r = step(observedReady(), score, eventualBg, targetBg, delta = 6.0, deltaAccl = 2.0,
            deltaDeclining = false)
        assertThat(r.state).isEqualTo(MealHypothesis.CONFIRMED)
    }

    // ── 2026-07-03 gate telemetry: the exposed eligibility predicate (boostV5_confirmGate) ────
    // confirmEligibleExceptDoseGate is the SAME predicate step() doses with, minus the adequacy
    // gate — decide() uses it to label cycles "pass"/"blocked"/"n/a".

    @Test fun `eligibility predicate matches the OBSERVING confirm sub-conditions`() {
        // Eligible-except-gate on the ready state...
        assertThat(confirmEligibleExceptDoseGate(observedReady(), score, eventualBg, targetBg)).isTrue()
        // ...false when the session lock is held...
        assertThat(confirmEligibleExceptDoseGate(observedReady().copy(committedInSession = true), score, eventualBg, targetBg)).isFalse()
        // ...false outside OBSERVING...
        assertThat(confirmEligibleExceptDoseGate(MealHypothesisState(), score, eventualBg, targetBg)).isFalse()
        // ...and false when the age gate hasn't opened (no streak).
        assertThat(confirmEligibleExceptDoseGate(observedReady().copy(ageCycles = 1), score, eventualBg, targetBg)).isFalse()
    }

    // ── 2026-07-06 confirm-floor pin (confirmDoseFloorU) ───────────────────────────────────────
    // The committedCap term is pinned at the FACTORY default (CONFIRM_FLOOR_COMMITTED_TERM_MAX =
    // 0.5 U): the floor means "shot must beat one ROUTINE hold" — a user-RAISED committedCap is a
    // bigger PERMITTED hold, not a bigger routine one. Backtest 2026-07-06: without the pin, a
    // 0.5 → 1.0 cap raise would newly block ~18% of live confirms.

    @Test fun `floor unchanged at the factory committedCap (0_5)`() {
        // 0.8 × confirmedCap (2.5) = 2.0 does not bind; committedCap term = min(0.5, pin 0.5) = 0.5.
        assertThat(confirmDoseFloorU(committedCapU = 0.5, confirmedCapU = 2.5)).isWithin(1e-12).of(0.5)
    }

    @Test fun `RAISED committedCap does NOT raise the floor (pin binds)`() {
        // A 0.5 → 1.0 cap raise: without the pin the floor would double to 1.0 and newly block
        // every confirm shot ≤ 1.0 U. With the pin it stays at the factory 0.5.
        assertThat(confirmDoseFloorU(committedCapU = 1.0, confirmedCapU = 2.5)).isWithin(1e-12).of(0.5)
    }

    @Test fun `LOWERED committedCap still lowers the floor (min semantics preserved)`() {
        assertThat(confirmDoseFloorU(committedCapU = 0.3, confirmedCapU = 2.5)).isWithin(1e-12).of(0.3)
    }

    @Test fun `confirmedCap clamp still binds when smaller than the pinned term`() {
        // 0.8 × confirmedCap (0.5) = 0.4 < pinned committedCap term (0.5) → floor 0.4.
        assertThat(confirmDoseFloorU(committedCapU = 0.5, confirmedCapU = 0.5)).isWithin(1e-12).of(0.4)
    }

    @Test fun `fast-carb path is NOT gated by dose adequacy`() {
        // Sharp, corroborated rise with the toggle on still confirms in one cycle even when
        // confirmDoseAdequate=false — the fast-path is intentionally exempt.
        val r = step(MealHypothesisState(MealHypothesis.OBSERVING, 0, 0.5, 10.0, false),
            score = 0.7, eventualBg = eventualBg, targetBg = targetBg, delta = 12.0, deltaAccl = 30.0,
            deltaDeclining = false, asleep = false, exerciseActive = false,
            fastConfirmEnabled = true, confirmDoseAdequate = false)
        assertThat(r.state).isEqualTo(MealHypothesis.CONFIRMED)
    }
}
