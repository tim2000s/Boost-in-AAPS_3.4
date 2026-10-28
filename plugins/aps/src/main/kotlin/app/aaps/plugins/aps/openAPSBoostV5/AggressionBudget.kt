package app.aaps.plugins.aps.openAPSBoostV5

import kotlin.math.max

/**
 * V5 Phase 1.c — AggressionBudget.
 *
 * Collapses V4's multiplicative brake stack (postSmbScale × mlRiskScale × fastCarbScale ×
 * Activity-mode target compression — which had no overall floor and could drive doses to
 * <5% of baseline under stacked high-risk) into TWO multipliers WITH a hard floor.
 *
 *     budget = max(0.30 × baseInsulinReq, baseInsulinReq × mlHypoRiskScale × postExerciseRecoveryModifier)
 *
 * Both modifiers are SAFETY REDUCERS; neither amplifies. Composition is bounded and explicit.
 *
 * **CRITICAL: `baseInsulinReq` is Boost-flavoured oref calc**, not vanilla oref. It carries
 * the entire Boost sensitivity stack unchanged: DynISF V1 formula reinstated in V3, 7D-only TDD
 * with W8H pull-down rule, TDD-anchored EMA sensitivity (ratio = EMA τ=3h on tdd_24h/tdd_7d),
 * autosens, hour-of-day basal rates, hour-of-day ISF, TempTargets, and the delta_accl
 * denominator floor `max(|shortAvgDelta|, 2.0)`. **V5 contains zero sensitivity logic of its
 * own.** Do NOT swap the caller's source for `baseInsulinReq` to vanilla oref's standard
 * formula — that would silently lose DynISF + EMA sensitivity, a regression invisible to unit
 * tests but visible in production hypos. See `MIGRATION.md` for the full inheritance map.
 *
 * **Why only two multipliers** (not the four originally drafted in the V5 proposal):
 *
 * - `exerciseStateModifier` was DROPPED. V4's exercise modes (VIGOROUS_AEROBIC, RESISTANCE,
 *   ACTIVE, STRESS, INACTIVE, RESTING) act through profile% and target BG, both of which feed
 *   `baseInsulinReq` already. A multiplier on top would double-count.
 * - `timeOfDayModifier` (dawn 1.1×) was DROPPED. AAPS profiles already have hour-of-day basal
 *   rates and optional hour-of-day ISF; dawn coverage flows through `baseInsulinReq`.
 * - `bgRangeModifier` (high 1.2×, low 0.5×) was DROPPED. `(eventualBG - target) / sens`
 *   already scales with BG; minGuardBG handles low; CONFIRMED 1.8× and dynamicSpikeCap
 *   handle high. The multiplier was redundant.
 *
 * `postExerciseRecoveryModifier` was RETAINED because V4's post-exercise recovery has TWO
 * effects: (1) sets a TT at 130 (flows through baseInsulinReq via the target term — handled
 * automatically); (2) scales `boost_bolus`/`boost_scale` by `postExerciseRecoveryScale`
 * (e.g., 0.5×). V5 doesn't use boost_bolus, so #2 needs an explicit V5 home. The physiology
 * is real: resistance / anaerobic exercise creates a delayed sensitivity bump lasting hours;
 * per-cycle mlHypoRiskScale isn't built to anticipate it.
 */

/** HARDCODED budget constants. Per `boost_v5_constants_calibration.md`. */
internal const val BUDGET_FLOOR_FRACTION = 0.30                  // hard floor: 30% × baseInsulinReq
internal const val ML_HYPO_RISK_THRESHOLD = 0.30                 // below this risk, scale = 1.0
internal const val ML_HYPO_RISK_FLOOR = 0.50                     // floor on mlScale at knob 1.0 (Hypo Caution knob LOWERS it: 0.50/knob)
internal const val POST_EXERCISE_RECOVERY_SCALE = 0.50           // V4-equivalent boost_bolus reduction during recovery window

data class AggressionBudgetResult(
    val budget: Double,
    val mlHypoRiskScale: Double,
    val postExerciseRecoveryScale: Double,
    val aggressionModifier: Double,
    val rawBudget: Double,
    val floorBudget: Double,
)

/**
 * Compute the per-cycle aggression budget.
 *
 * @param baseInsulinReq Boost-flavoured oref insulinReq for this cycle. See KDoc above for the
 *   full inheritance contract.
 * @param mlHypoRisk hypo-risk model output ∈ [0, 1], or null if model not yet loaded.
 * @param inPostExerciseWindow true if V4's post-exercise tracking state has the recovery window
 *   active (read directly from V4's existing state — V5 does NOT reimplement detection).
 * @param hypoCautionUserKnob user-facing "Hypo Caution" multiplier ∈ [1.0, 2.0]. Default 1.0.
 *   Higher = MORE caution = LESS insulin when the ML hypo-risk model is elevated. It deepens and
 *   widens the mlHypoRiskScale backoff (and lowers its floor 0.50→0.25 across 1.0→2.0) so a
 *   hypo-prone user (e.g. the 2026-06-15 backtest's User D, whose pre-severe-low over-dosing all
 *   sits in the mid risk band 0.30–0.60) can be trimmed where it matters. Default 1.0 is an exact
 *   no-op vs the prior calibration. **2026-06-15 fix:** the previous implementation RAISED the
 *   floor with the knob — i.e. raising "Hypo Caution" REMOVED damping and dosed MORE (inverted).
 *   This is one of V5's ≤3 user-facing knobs.
 * @param sensitivityUserKnob user-facing "Sensitivity" multiplier ∈ [0.8, 1.2]. Default 1.0.
 *   A per-user calibration lever on the whole budget: <1.0 trims V5 for users where it runs
 *   hot (the 2026-06-15 backtest's User-D over-dosed before lows), >1.0 lets it run firmer for
 *   resistant users. Bounded; the BUDGET_FLOOR still protects the downside and downstream caps +
 *   maxIOB clamp the upside. This is the live lever a future nightly per-user learner will drive
 *   (loop deferred — see boost_v6_delivery_plan Phase 3).
 */
fun aggressionBudget(
    baseInsulinReq: Double,
    mlHypoRisk: Double?,
    inPostExerciseWindow: Boolean,
    hypoCautionUserKnob: Double = 1.0,
    sensitivityUserKnob: Double = 1.0,
): AggressionBudgetResult {
    val mlScale = mlHypoRiskScale(mlHypoRisk, hypoCautionUserKnob)
    val postExScale = postExerciseRecoveryModifier(inPostExerciseWindow)
    val sensitivity = sensitivityUserKnob.coerceIn(0.8, 1.2)
    val aggressionModifier = mlScale * postExScale * sensitivity
    val rawBudget = baseInsulinReq * aggressionModifier
    val floorBudget = BUDGET_FLOOR_FRACTION * baseInsulinReq
    val budget = max(floorBudget, rawBudget)
    return AggressionBudgetResult(
        budget = budget,
        mlHypoRiskScale = mlScale,
        postExerciseRecoveryScale = postExScale,
        aggressionModifier = aggressionModifier,
        rawBudget = rawBudget,
        floorBudget = floorBudget,
    )
}

/**
 * Graduated damper based on ML hypo-risk. Linear from 1.0 at risk = 0.30 down to `floor`
 * at risk = 1.0. Below 0.30 the scale is 1.0 (no damping).
 *
 * Subsumes V4's three separate brakes on the same metric: `mlRiskScale` (graduated 0–1.0),
 * `mlPostSmbScale` (post-SMB damper, now in Phase 3 as `postActionRiskCheck`), and
 * `mlTierDowngrade` (binary tier-skip at 0.6). V5's single graduated curve eliminates the
 * double-braking problem.
 */
internal fun mlHypoRiskScale(mlHypoRisk: Double?, hypoCautionKnob: Double = 1.0): Double {
    if (mlHypoRisk == null) return 1.0
    if (mlHypoRisk <= ML_HYPO_RISK_THRESHOLD) return 1.0
    val span = 1.0 - ML_HYPO_RISK_THRESHOLD
    if (span <= 0.0) return ML_HYPO_RISK_FLOOR
    val knob = hypoCautionKnob.coerceAtLeast(1.0)
    // Base reduction fraction: 0 at the threshold, 1.0 at risk = 1.0. Hypo Caution scales the cut
    // UP (more backoff), and lowers the floor (0.50 @ knob 1.0 → 0.25 @ knob 2.0) so the deeper cut
    // can actually land. At knob 1.0 this is identical to the prior `max(0.5, 1 − (risk−0.3)/span)`.
    val reduction = ((mlHypoRisk - ML_HYPO_RISK_THRESHOLD) / span * knob).coerceIn(0.0, 1.0)
    val floor = ML_HYPO_RISK_FLOOR / knob
    return max(floor, 1.0 - reduction)
}

/**
 * Post-exercise recovery damper. Returns `POST_EXERCISE_RECOVERY_SCALE` when V4's existing
 * recovery window is active, else 1.0. Does NOT detect; only consumes V4's tracking state.
 *
 * The recovery window is set up by V4's exercise classifier when a session of
 * RESISTANCE / VIGOROUS_AEROBIC / ACTIVE-with-duration ends. V5 reuses that state directly
 * to avoid re-implementing detection.
 */
internal fun postExerciseRecoveryModifier(inPostExerciseWindow: Boolean): Double =
    if (inPostExerciseWindow) POST_EXERCISE_RECOVERY_SCALE else 1.0
