package app.aaps.plugins.aps.openAPSBoostV5

import kotlin.math.floor
import kotlin.math.max

/**
 * V5 Phase 3 — ordered safety gates.
 *
 * Hard gates short-circuit (zero the dose). Soft gates damp (multiplicative). Final clamp
 * rounds, applies the dynamic spike cap, and floors at 0.
 *
 * **CRITICAL: gate ordering is load-bearing and must NOT be reshuffled.** Specifically:
 *
 * - `iobHeadroomBrake` runs FIRST in soft gates so `postActionRiskCheck` projects against
 *   the already-damped dose, not the raw Phase 2 output. Reordering would project against
 *   an unrealistic dose and either over- or under-brake.
 * - Hard gates run before any soft gate so a binary disable short-circuits cleanly without
 *   wasting computation on multiplicative damping.
 *
 * V4 Tier 7's hard IOB cap (deletion of which caused a 5.5× hypo regression in V2;
 * reinstatement in V3 fixed it — see `MIGRATION.md`) is replaced here by `iobHeadroomBrake`,
 * a graduated curve that fires regardless of delta_accl direction. Equivalent safety,
 * smoother behaviour.
 */

/**
 * Inputs to Phase 3 that come from elsewhere in the cycle (oref state, profile, glucose status).
 * Caller assembles this struct before invoking [applyPhase3].
 */
data class Phase3Inputs(
    /** Phase 2 output: the budget × action_multiplier dose, before safety damping. */
    val insulinToDeliver: Double,
    /** Whether the full V4 enableSMB pre-check chain passed (microBolusAllowed, BG > threshold, etc.). */
    val enableSmbPreChecks: Boolean,
    val minGuardBg: Double,
    val minGuardThreshold: Double,
    /** maxDelta from oref glucose status. Hard-disables SMB if maxDelta > 0.30 × bg. */
    val maxDelta: Double,
    val bg: Double,
    val iob: Double,
    val maxIob: Double,
    /** delta_accl with V3's denominator floor (`max(|shortAvgDelta|, 2.0)`) already applied. */
    val deltaAccl: Double,
    /** Signed per-cycle delta (mg/dL/5min) — for the decelerationBrake velocity fallback. */
    val delta: Double = 0.0,
    /** baseInsulinReq used by [dynamicSpikeCap] to compute a per-cycle ceiling. */
    val baseInsulinReq: Double,
    /** Pump's SMB rounding step, e.g. 0.05 U. */
    val roundSmbTo: Double,
    /** True if CGM data quality is acceptable. False engages the soft sensor-quality damper. */
    val sensorQualityOk: Boolean = true,
    /**
     * Optional: a function that re-evaluates ML hypo risk at the projected post-SMB IOB.
     * If provided, V5 invokes it AFTER `iobHeadroomBrake` has already damped the dose, so the
     * projection sees a realistic delivery. Pass null to disable this gate.
     */
    val riskAtProjectedIob: ((projectedIob: Double) -> Double)? = null,
    /** Current ML hypo-risk reading, used as the baseline for [postActionRiskCheck] comparison. */
    val mlHypoRisk: Double? = null,
)

/** What each gate did to the dose (for observability + NS field reconstruction). */
data class GateReductions(
    val hardGateFired: String? = null,
    val maxIobClampApplied: Boolean = false,
    val iobHeadroomBrake: Double = 1.0,
    val postActionRiskCheck: Double = 1.0,
    val decelerationBrake: Double = 1.0,
    val sensorQualityCheck: Double = 1.0,
    val dynamicSpikeCapped: Boolean = false,
)

data class Phase3Result(val finalDose: Double, val reductions: GateReductions)

// HARD gate constants
internal const val MAX_DELTA_BG_RATIO_DISABLE = 0.30           // V4 maxDelta gate retained verbatim

// iobHeadroomBrake constants — V3 Tier-7-cap equivalent (graduated). Calibrated 2026-05-06.
// Curve fires REGARDLESS of delta_accl direction (key V3 invariant: V2 deletion caused 5.5× hypo regression).
internal const val IOB_HEADROOM_THRESHOLD_0 = 0.50              // iob_fraction < 0.5 → no brake
internal const val IOB_HEADROOM_THRESHOLD_1 = 0.70
internal const val IOB_HEADROOM_THRESHOLD_2 = 0.85
internal const val IOB_HEADROOM_SCALE_1 = 0.85                  // 0.5 ≤ iob_frac < 0.7
internal const val IOB_HEADROOM_SCALE_2 = 0.60                  // 0.7 ≤ iob_frac < 0.85
internal const val IOB_HEADROOM_SCALE_3 = 0.40                  // iob_frac ≥ 0.85

// decelerationBrake — 2026-06-14 re-spec, anchored on V1's switch: V1 gates its boost tiers on
// delta_accl > 0 (DetermineBasalBoost.kt T5 :1526 / T3 :1475) with a delta > 8 velocity fallback
// (T4 :1505) to keep covering a sustained-but-decelerating climb. Ease off once accl crosses zero
// (first sign insulin is biting), UNLESS still climbing fast. Replaces the old <−10 reversal gate.
internal const val DECEL_BRAKE_ACCL_FULL = -15.0               // full brake at/below this delta_accl
internal const val DECEL_BRAKE_FLOOR = 0.30                    // min scale (never fully quits a still-high meal)
internal const val DECEL_BRAKE_VELOCITY_FALLBACK = 8.0         // mg/dL/5min — still climbing fast → keep dosing (V1 T4)

// postActionRiskCheck — V4's mlPostSmbScale moved to Phase 3 where projection makes sense
internal const val POST_ACTION_RISK_THRESHOLD = 0.40
internal const val POST_ACTION_RISK_DELTA_THRESHOLD = 0.15
internal const val POST_ACTION_RISK_FLOOR = 0.30

// sensorQualityCheck (placeholder; ship enabled if defined; otherwise pass-through)
internal const val SENSOR_QUALITY_BAD_SCALE = 0.7

// dynamicSpikeCap — applies on EVERY cycle, not just one tier (V4 had spike override only on Tier 8).
// Must be ABOVE the maximum normal CONFIRMED output: action_multiplier 1.8 × max user Aggression knob 1.3
// = 2.34. Cap set to 2.5 leaves a small headroom over that maximum so the cap only fires on genuine
// outliers (e.g., budget unexpectedly inflated by a sensitivity-stack glitch). Earlier value 1.5 was
// a bug — it capped every CONFIRMED dose and defeated the catch-up commit.
internal const val DYNAMIC_SPIKE_CAP_MULTIPLIER = 2.5

/** Run Phase 3 in the load-bearing order. Returns final dose + per-gate reductions. */
fun applyPhase3(input: Phase3Inputs): Phase3Result {
    var dose = input.insulinToDeliver

    // ─── HARD gates (binary disable) ───
    if (!input.enableSmbPreChecks) {
        return Phase3Result(0.0, GateReductions(hardGateFired = "enable_smb_pre_checks"))
    }
    if (input.minGuardBg < input.minGuardThreshold) {
        return Phase3Result(0.0, GateReductions(hardGateFired = "min_guard_bg"))
    }
    if (input.maxDelta > MAX_DELTA_BG_RATIO_DISABLE * input.bg) {
        return Phase3Result(0.0, GateReductions(hardGateFired = "max_delta"))
    }
    val maxIobClampApplied: Boolean
    val headroom = max(0.0, input.maxIob - input.iob)
    if (dose > headroom) {
        dose = headroom
        maxIobClampApplied = true
    } else {
        maxIobClampApplied = false
    }

    // ─── SOFT gates (damp; ORDERED) ───
    val iobBrake = iobHeadroomBrake(input.iob, input.maxIob)
    dose *= iobBrake

    val parScale = postActionRiskCheck(
        dose = dose,
        currentMlHypoRisk = input.mlHypoRisk,
        currentIob = input.iob,
        riskAtProjectedIob = input.riskAtProjectedIob,
    )
    dose *= parScale

    val decelScale = decelerationBrake(input.deltaAccl, input.delta)
    dose *= decelScale

    val sensorScale = sensorQualityCheck(input.sensorQualityOk)
    dose *= sensorScale

    // ─── FINAL clamp ───
    // Use small epsilon to avoid FP precision losing a step at exact boundaries
    // (e.g. 0.3 / 0.05 = 5.999... → floor 5 → 0.25 instead of 0.30).
    if (input.roundSmbTo > 0.0) {
        dose = floor(dose / input.roundSmbTo + 1e-9) * input.roundSmbTo
    }
    val spikeCap = dynamicSpikeCap(input.baseInsulinReq)
    val spikeCapped: Boolean
    if (dose > spikeCap) {
        dose = spikeCap
        spikeCapped = true
    } else {
        spikeCapped = false
    }
    dose = max(0.0, dose)

    return Phase3Result(
        finalDose = dose,
        reductions = GateReductions(
            hardGateFired = null,
            maxIobClampApplied = maxIobClampApplied,
            iobHeadroomBrake = iobBrake,
            postActionRiskCheck = parScale,
            decelerationBrake = decelScale,
            sensorQualityCheck = sensorScale,
            dynamicSpikeCapped = spikeCapped,
        )
    )
}

/**
 * V3 Tier-7 cap equivalent. Graduated curve on iob_fraction. Fires REGARDLESS of delta_accl
 * direction — that's the V3 invariant whose deletion in V2 caused a 5.5× hypo regression
 * (see MIGRATION.md). At iob_fraction ≥ 0.85, dose is reduced to 40% of input.
 */
internal fun iobHeadroomBrake(iob: Double, maxIob: Double): Double {
    if (maxIob <= 0.0) return 1.0
    val fraction = iob / maxIob
    return when {
        fraction < IOB_HEADROOM_THRESHOLD_0 -> 1.0
        fraction < IOB_HEADROOM_THRESHOLD_1 -> IOB_HEADROOM_SCALE_1
        fraction < IOB_HEADROOM_THRESHOLD_2 -> IOB_HEADROOM_SCALE_2
        else -> IOB_HEADROOM_SCALE_3
    }
}

/**
 * V1-anchored ease-off. V1 gates its boost tiers on `delta_accl > 0` with a `delta > 8` velocity
 * fallback; this mirrors that. Returns 1.0 while still accelerating (accl ≥ 0) or still climbing
 * fast (delta > 8); once accl crosses below zero and BG isn't rising fast — the first sign insulin
 * is biting — it scales the dose down linearly from 1.0 (accl=0) to [DECEL_BRAKE_FLOOR] (accl ≤
 * [DECEL_BRAKE_ACCL_FULL]). IOB-independent (iobHeadroomBrake covers IOB separately).
 */
internal fun decelerationBrake(deltaAccl: Double, delta: Double): Double {
    if (delta > DECEL_BRAKE_VELOCITY_FALLBACK) return 1.0   // still climbing fast — keep dosing (V1 T4 fallback)
    if (deltaAccl >= 0.0) return 1.0                         // still accelerating — full dose
    // accl < 0 and not climbing fast: graduated ease-off, 1.0 at accl=0 → FLOOR at accl≤FULL
    val frac = ((deltaAccl - DECEL_BRAKE_ACCL_FULL) / (0.0 - DECEL_BRAKE_ACCL_FULL)).coerceIn(0.0, 1.0)
    return DECEL_BRAKE_FLOOR + (1.0 - DECEL_BRAKE_FLOOR) * frac
}

/**
 * V4's mlPostSmbScale, relocated to Phase 3 where post-SMB projection makes structural sense.
 * Re-runs the hypo-risk model at the projected IOB (`iob + dose`); if projected risk is
 * materially higher than current, damps the dose proportionally. Floors at 0.30.
 */
internal fun postActionRiskCheck(
    dose: Double,
    currentMlHypoRisk: Double?,
    currentIob: Double,
    riskAtProjectedIob: ((projectedIob: Double) -> Double)?,
): Double {
    if (riskAtProjectedIob == null || currentMlHypoRisk == null) return 1.0
    val projected = riskAtProjectedIob(currentIob + dose)
    if (projected > currentMlHypoRisk + POST_ACTION_RISK_DELTA_THRESHOLD &&
        projected > POST_ACTION_RISK_THRESHOLD) {
        val raw = 1.0 - (projected - POST_ACTION_RISK_THRESHOLD) / (1.0 - POST_ACTION_RISK_THRESHOLD)
        return max(POST_ACTION_RISK_FLOOR, raw)
    }
    return 1.0
}

/** Optional CGM data quality damper. Returns 0.7 if sensor not OK; pass-through otherwise. */
internal fun sensorQualityCheck(sensorOk: Boolean): Double =
    if (sensorOk) 1.0 else SENSOR_QUALITY_BAD_SCALE

/**
 * Per-cycle dynamic cap. Applies on EVERY cycle (V4 had spike override only on Tier 8).
 * Equal to [DYNAMIC_SPIKE_CAP_MULTIPLIER] (2.5) × baseInsulinReq — above any normal Phase 2 output (CONFIRMED 1.8×
 * with full mlHypoRiskScale × postExerciseRecoveryModifier active would already be capped
 * by the AggressionBudget hard floor; in practice this gate fires only when both AggressionBudget
 * and Phase 2 produce an outlier, e.g. via the user-facing Aggression knob at 1.3×).
 */
internal fun dynamicSpikeCap(baseInsulinReq: Double): Double =
    DYNAMIC_SPIKE_CAP_MULTIPLIER * baseInsulinReq
