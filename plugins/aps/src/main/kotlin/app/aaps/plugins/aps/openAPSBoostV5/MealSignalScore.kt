package app.aaps.plugins.aps.openAPSBoostV5

import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min

/**
 * V5 Phase 1.a — meal_signal_score.
 *
 * Continuous 0-1 weighted combination of 6 signals indicating likelihood of an active meal.
 * Drives the MealHypothesis state machine's IDLE→OBSERVING and OBSERVING→CONFIRMED transitions.
 *
 * Replaces V4's binary G3 pre-UAM hold + meal-model-release + fast-carb-rebound triad with
 * one continuous score. The "binary cliff" failure modes (UAM_BOOST eligibility just-misses
 * — see 2026-05-05 incident) are eliminated by construction.
 *
 * Weights are HARDCODED constants calibrated by backtest #3 on the 19-user oref cohort
 * (`boost_v5_constants_calibration.md`). The user-facing settings surface contains NO
 * score-weight knobs — per V5's minimal-settings tenet, users have no basis to choose them.
 */

// Weight constants. Sum = 1.07 (> 1.0 acceptable; score is clipped to [0, 1] regardless).
// Calibrated 2026-05-06 per boost_v5_constants_calibration.md sweep results.
// SCORE_WEIGHT_SUSTAINED_RISE added 2026-05-22 (Fix 4 — slow-meal detection).
internal const val SCORE_WEIGHT_DELTA = 0.30
internal const val SCORE_WEIGHT_DELTA_ACCL = 0.16          // calibrated: 0.20 → 0.16 (-1.4pp false_conf)
internal const val SCORE_WEIGHT_ML_MEAL_LIKELY = 0.20
internal const val SCORE_WEIGHT_NOT_RECENTLY_LOW = 0.12    // calibrated: 0.15 → 0.12 (-1.3pp false_conf)
internal const val SCORE_WEIGHT_MEAL_TIME_OF_DAY = 0.10
internal const val SCORE_WEIGHT_NOT_EXERCISING = 0.04      // calibrated: 0.05 → 0.04
internal const val SCORE_WEIGHT_SUSTAINED_RISE = 0.15      // Fix 4 (2026-05-22) — catches slow meals

internal const val DELTA_NORMALIZE_HI_MGDL = 20.0          // delta saturates at 20 mg/dL/5min
internal const val DELTA_ACCL_NORMALIZE_HI_PCT = 30.0      // accl saturates at 30%

/**
 * Sustained-rise term bounds. A cumulative BG rise of [SUSTAINED_RISE_NORMALIZE_LO_MGDL] over the
 * last ~30 minutes contributes 0; a rise of [SUSTAINED_RISE_NORMALIZE_HI_MGDL] saturates at 1.0.
 *
 * Designed to catch slow-but-sustained meal climbs (≤4 mg/dL per 5-min cycle) that the
 * single-cycle [DELTA_NORMALIZE_HI_MGDL] = 20 saturator and the [DELTA_ACCL_NORMALIZE_HI_PCT] = 30
 * saturator both miss. See `boost_v5_fix4_slow_meal_scope.md` (2026-05-22) for the trigger event
 * (5/15 evening meal: 71 → 168 mg/dL over 2h15m, V5 stuck in OBSERVING throughout).
 *
 * Works in concert with Fix 1's peak-score CONFIRMED transition: a sustained rise produces a
 * steady score bump that doesn't dip cycle-to-cycle, lifting max-score-in-OBSERVING above the
 * 0.55 threshold even when individual-cycle scores fluctuate just below it.
 */
internal const val SUSTAINED_RISE_NORMALIZE_LO_MGDL = 20.0
internal const val SUSTAINED_RISE_NORMALIZE_HI_MGDL = 60.0

/**
 * Number of consecutive null-mlMealLikely cycles after which the score formula falls back
 * to a 5-weight version (mlMealLikely weight dropped, others scaled by 1/(1-W)).
 * Addresses the V3ML lazy-load bug noted in `boost_v3ml_production_validation.md`.
 */
internal const val ML_MEAL_RENORMALIZE_AFTER_CYCLES = 3

/** Sum of all seven score weights. NOT 1.0 — the 2026-05/06 calibration retunes adjusted
 *  individual weights (and Fix 4 added sustainedRise) without renormalizing the total. */
internal const val SCORE_WEIGHT_TOTAL =
    SCORE_WEIGHT_DELTA + SCORE_WEIGHT_DELTA_ACCL + SCORE_WEIGHT_ML_MEAL_LIKELY +
        SCORE_WEIGHT_NOT_RECENTLY_LOW + SCORE_WEIGHT_MEAL_TIME_OF_DAY +
        SCORE_WEIGHT_NOT_EXERCISING + SCORE_WEIGHT_SUSTAINED_RISE

/**
 * Rescale factor when the mlMealLikely weight is dropped after a long null streak.
 * 2026-07-06 parity fix: was 1/(1−W) = 1.25, which assumes the weights sum to 1.0 — they sum
 * to [SCORE_WEIGHT_TOTAL] (1.07), so the correct restore-scale is TOTAL/(TOTAL−W) ≈ 1.2299.
 * The old value over-scaled ML-outage scores by ~1.6% (marginally earlier confirms exactly when
 * the ML input was missing). The Trio port had already corrected this; Android now matches.
 */
internal const val ML_MEAL_RENORMALIZE_FACTOR =
    SCORE_WEIGHT_TOTAL / (SCORE_WEIGHT_TOTAL - SCORE_WEIGHT_ML_MEAL_LIKELY)

/** Per-component values that went into the final score. Emitted to NS for observability. */
data class ScoreComponents(
    val deltaTerm: Double,
    val deltaAcclTerm: Double,
    val mlMealLikelyTerm: Double,
    val notRecentlyLowTerm: Double,
    val mealTimeOfDayTerm: Double,
    val notExercisingTerm: Double,
    val sustainedRiseTerm: Double,
)

data class ScoreResult(
    val score: Double,
    val components: ScoreComponents,
    val mlWeightsRenormalized: Boolean,
)

/**
 * Compute meal_signal_score for one cycle.
 *
 * @param delta BG delta over the last 5 minutes, mg/dL/5min.
 * @param deltaAccl acceleration of delta, percent (`(delta - shortAvgDelta) / max(|shortAvgDelta|, 2.0) × 100`).
 * @param mlMealLikely ML meal-likelihood model output ∈ [0, 1], or null if model not yet loaded.
 * @param recentLowBg minimum BG in the last 60 min, mg/dL.
 * @param hour hour of day, 0-23.
 * @param exerciseActive true if any exercise mode currently engaged in the activity classifier.
 * @param cumulativeRise30min approximate cumulative BG rise over the last ~30 min, mg/dL.
 *        Caller derives from `shortAvgDelta * 6` (Fix 4, 2026-05-22). Clamped non-negative.
 * @param mlMealLikelyNullStreak count of consecutive prior cycles where mlMealLikely was null.
 *        Caller maintains this counter — the score function only reads it.
 */
fun mealSignalScore(
    delta: Double,
    deltaAccl: Double,
    mlMealLikely: Double?,
    recentLowBg: Double,
    hour: Int,
    exerciseActive: Boolean,
    cumulativeRise30min: Double,
    mlMealLikelyNullStreak: Int = 0,
): ScoreResult {
    val deltaTerm = clipNormalize(delta, 0.0, DELTA_NORMALIZE_HI_MGDL)
    val deltaAcclTerm = clipNormalize(deltaAccl, 0.0, DELTA_ACCL_NORMALIZE_HI_PCT)
    val notRecentlyLowTerm = notRecentlyLowPenalty(recentLowBg)
    val mealTimeOfDayTerm = mealTimeOfDayBump(hour)
    val notExercisingTerm = if (exerciseActive) 0.0 else 1.0
    val sustainedRiseTerm = clipNormalize(
        cumulativeRise30min,
        SUSTAINED_RISE_NORMALIZE_LO_MGDL,
        SUSTAINED_RISE_NORMALIZE_HI_MGDL,
    )

    val renormalize = mlMealLikely == null && mlMealLikelyNullStreak >= ML_MEAL_RENORMALIZE_AFTER_CYCLES
    val mlMealLikelyTerm = mlMealLikely ?: 0.0

    val rawScore = if (renormalize) {
        // Drop ml_meal_likely weight; rescale the remaining 6 to compensate so that the score
        // ceiling stays the same as when ML is available. Without this, a multi-cycle ML outage
        // would silently lower the score and freeze V5 in IDLE.
        ML_MEAL_RENORMALIZE_FACTOR * (
            SCORE_WEIGHT_DELTA * deltaTerm +
            SCORE_WEIGHT_DELTA_ACCL * deltaAcclTerm +
            SCORE_WEIGHT_NOT_RECENTLY_LOW * notRecentlyLowTerm +
            SCORE_WEIGHT_MEAL_TIME_OF_DAY * mealTimeOfDayTerm +
            SCORE_WEIGHT_NOT_EXERCISING * notExercisingTerm +
            SCORE_WEIGHT_SUSTAINED_RISE * sustainedRiseTerm
        )
    } else {
        SCORE_WEIGHT_DELTA * deltaTerm +
        SCORE_WEIGHT_DELTA_ACCL * deltaAcclTerm +
        SCORE_WEIGHT_ML_MEAL_LIKELY * mlMealLikelyTerm +
        SCORE_WEIGHT_NOT_RECENTLY_LOW * notRecentlyLowTerm +
        SCORE_WEIGHT_MEAL_TIME_OF_DAY * mealTimeOfDayTerm +
        SCORE_WEIGHT_NOT_EXERCISING * notExercisingTerm +
        SCORE_WEIGHT_SUSTAINED_RISE * sustainedRiseTerm
    }

    val score = max(0.0, min(1.0, rawScore))

    return ScoreResult(
        score = score,
        components = ScoreComponents(
            deltaTerm = deltaTerm,
            deltaAcclTerm = deltaAcclTerm,
            mlMealLikelyTerm = mlMealLikelyTerm,
            notRecentlyLowTerm = notRecentlyLowTerm,
            mealTimeOfDayTerm = mealTimeOfDayTerm,
            notExercisingTerm = notExercisingTerm,
            sustainedRiseTerm = sustainedRiseTerm,
        ),
        mlWeightsRenormalized = renormalize,
    )
}

private fun clipNormalize(value: Double, lo: Double, hi: Double): Double {
    if (hi <= lo) return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))
}

/**
 * Continuous penalty for recent-low BG. Returns 1.0 if recentLowBg ≥ 100 mg/dL, **0.4** at ≤ 70,
 * linear between.
 *
 * Replaces V4's binary G3-hold floor (`recentLowBG ≥ 70` as a binary gate). The continuous
 * version eliminates the cliff at 70 that caused unhelpful tier transitions when BG hovered
 * around 70.
 *
 * ## 2026-05-15 floor softening
 *
 * The original floor was 0.0, which removed 0.12 from the score ceiling whenever recentLowBg ≤
 * 70 — i.e., for ~4 hours following every hypo episode. For users with TBR > 5% (the developer's
 * pump runs 5–7%), this structurally blocked CONFIRMED transitions through ~17% of the day,
 * even when delta, delta_accl, and mlMealLikely were all firing strongly. Shadow data showed 4
 * CONFIRMED transitions in 8 days across all V5 cycles — this floor was a load-bearing
 * contributor to that drought.
 *
 * Raising the floor to 0.4 preserves a meaningful penalty (still down 7 pp from the
 * no-low ceiling) without making CONFIRMED structurally unreachable in the post-low window.
 * The hypo damper from `mlHypoRisk` and the V5 hard gate (also fixed in this revision) provide
 * the right counterweights when an actual meal does need to fire post-hypo.
 */
private const val NOT_RECENTLY_LOW_FLOOR = 0.4

private fun notRecentlyLowPenalty(recentLowBg: Double): Double =
    max(NOT_RECENTLY_LOW_FLOOR, clipNormalize(recentLowBg, 70.0, 100.0))

/**
 * Smooth peaks at typical meal hours (08:00, 13:00, 19:00). Gaussian-shaped with width 2h.
 *
 * NOTE: This is a meal-LIKELIHOOD signal — it raises the prior that a rise during typical
 * meal hours is a meal. It is NOT a dose amplifier. V5 has no time-of-day dose amplifier;
 * dawn coverage is owned by the AAPS profile (hour-of-day basal rates / hour-of-day ISF).
 */
private fun mealTimeOfDayBump(hour: Int): Double {
    val centres = intArrayOf(8, 13, 19)
    val width = 2.0
    var maxBump = 0.0
    for (centre in centres) {
        val diff = (hour - centre).toDouble()
        val bump = exp(-(diff * diff) / (2.0 * width * width))
        if (bump > maxBump) maxBump = bump
    }
    return maxBump
}
