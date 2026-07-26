package app.aaps.plugins.aps.openAPSBoostV5

/**
 * V5 Phase 2 — single decision rule.
 *
 * The entire V4 8-tier if-else ladder + 5 modulators collapses into:
 *
 *     insulin_to_deliver = aggression_budget × meal_action_multiplier(mealHypothesis)
 *
 * The state machine encodes "what hypothesis am I operating under"; this multiplier encodes
 * "given that hypothesis, dose this much relative to baseline budget."
 *
 * V4 → V5 mapping:
 * - Tiers 1, 2 (COB): COB > 0 → mealHypothesis goes straight to COMMITTED; baseInsulinReq
 *   already accounts for COB.
 * - Tiers 3, 4 (UAM_BOOST / UAM_HIGH_BOOST): mealHypothesis CONFIRMED → COMMITTED.
 * - Tiers 5, 6 (PERCENT_SCALE / ACCELERATION): score components drive IDLE → OBSERVING →
 *   CONFIRMED transitions; OBSERVING tests, CONFIRMED commits.
 * - Tiers 7, 8 (default oref1): mealHypothesis IDLE → action multiplier 1.0× → standard dose.
 */

/**
 * Action multipliers per state. HARDCODED.
 *
 * - **IDLE** (1.0×): standard oref1 dose; no meal hypothesis.
 * - **OBSERVING** (0.3×): test-dose fraction. Encodes Tim's "test then commit" intent —
 *   small dose to validate the hypothesis without committing.
 * - **CONFIRMED** (1.8×): catch-up dose. Larger than baseline because we waited 2+ cycles
 *   in OBSERVING to confirm. This is the riskiest single decision V5 makes; mitigated by
 *   AggressionBudget hard floor on the lower side and Phase 3 gates on the upper side.
 *   The user-facing "Aggression" knob (∈ [0.7, 1.6], default 1.0) scales THIS multiplier
 *   only — that's the one place users genuinely have a basis for per-user variation.
 * - **COMMITTED** (1.0×): sustained meal dosing at baseline. We've committed; now we follow oref.
 * - **RECOVERING** (0.4×): backing off as IOB bites and BG decelerates. Conservative.
 *
 * IDLE and COMMITTED stay at 1.0 by definition (they ARE "baseline behaviour"); calibration
 * cannot meaningfully tune them. Per `boost_v5_constants_calibration.md`, the OBSERVING and
 * RECOVERING multipliers are not load-bearing on cohort data; defaults retained.
 */
private val ACTION_MULTIPLIERS: Map<MealHypothesis, Double> = mapOf(
    MealHypothesis.IDLE to 1.0,
    MealHypothesis.OBSERVING to 0.3,
    MealHypothesis.CONFIRMED to 1.8,
    MealHypothesis.COMMITTED to 1.0,
    MealHypothesis.RECOVERING to 0.4,
)

/**
 * Phase 2 multiplier for the given meal hypothesis state.
 *
 * @param state current MealHypothesis state.
 * @param aggressionUserKnob user-facing "Aggression" setting ∈ [0.7, 1.6]. Default 1.0. Scales
 *   the CONFIRMED multiplier ONLY — IDLE / OBSERVING / COMMITTED / RECOVERING are unaffected.
 *   This concentrates the user's tuning power on the single-most-impactful decision V5 makes.
 */
fun mealActionMultiplier(
    state: MealHypothesis,
    aggressionUserKnob: Double = 1.0,
): Double {
    val base = ACTION_MULTIPLIERS[state]
        ?: error("Unhandled MealHypothesis state: $state")
    return if (state == MealHypothesis.CONFIRMED) base * aggressionUserKnob else base
}
