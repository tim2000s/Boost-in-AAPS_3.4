package app.aaps.plugins.aps.openAPSBoostV5

import javax.inject.Inject
import javax.inject.Singleton

/**
 * Boost V5 algorithm core — Observe-Confirm-Commit pipeline orchestrator.
 *
 * Status: PRODUCTION — this is the dosing core behind the selectable "Boost V6" plugin
 * (header corrected 2026-07-02; previously said PRE-ALPHA from the shadow era). Phase 1.a
 * (meal_signal_score), 1.b (state machine), 1.c (AggressionBudget), 2 (action multiplier), and
 * 3 (safety gates) live in their respective files; the orchestrator below stitches them into the
 * single `decide()` entry point, wired from oref/Boost services by OpenAPSBoostV5Plugin.
 *
 * Architecture (mirrors `boost_v5_redesign_proposal.md` exactly):
 *
 *   Phase 1 — state estimation (no commitment):
 *     - mealSignalScore          (MealSignalScore.kt)
 *     - step + resetIfNeeded     (MealHypothesis.kt)
 *     - aggressionBudget         (AggressionBudget.kt)
 *
 *   Phase 2 — single decision rule:
 *     - mealActionMultiplier(state) × budget   (MealActionMultiplier.kt)
 *
 *   Phase 3 — ordered safety gates:
 *     - applyPhase3              (SafetyGates.kt)
 *
 * `baseInsulinReq` MUST come from Boost-flavoured oref calc (DynISF + 7D TDD with W8H pull-down +
 * TDD-anchored EMA sensitivity + autosens + hour-of-day ISF + TempTargets — all unchanged).
 * V5 contains zero sensitivity logic of its own. See `MIGRATION.md` and the AggressionBudget
 * KDoc for the full inheritance contract.
 */

/** All inputs V5 needs for one cycle. Caller assembles from oref + Boost services. */
data class V5Inputs(
    // Glucose status
    val delta: Double,
    val shortAvgDelta: Double,
    val deltaAccl: Double,
    val bg: Double,
    val eventualBg: Double,
    val targetBg: Double,
    val maxDelta: Double,
    val minGuardBg: Double,
    val minGuardThreshold: Double,
    /** Last ≥3 deltas (oldest → newest, including current). For [deltaDeclining]. */
    val deltaHistory: List<Double>,

    // IOB / dose context
    val iob: Double,
    val maxIob: Double,
    /** Boost-flavoured oref insulinReq for this cycle. NOT vanilla oref — see KDoc. */
    val baseInsulinReq: Double,
    val roundSmbTo: Double,
    val enableSmbPreChecks: Boolean,

    // ML model outputs
    val mlHypoRisk: Double?,
    val mlMealLikely: Double?,
    /** ML model invocation: re-run hypo risk at projected IOB. Null disables postActionRiskCheck. */
    val riskAtProjectedIob: ((projectedIob: Double) -> Double)? = null,

    // Cycle context
    val recentLowBg: Double,
    /** Cumulative BG rise over the last ~30 min, mg/dL. Derived from `shortAvgDelta * 6`. Fix 4 (2026-05-22). */
    val cumulativeRise30min: Double,
    val hour: Int,
    val exerciseActive: Boolean,
    val inPostExerciseWindow: Boolean,
    /** SLEEPING (prior-cycle sleep state). Gates the fast-carb fast-path off overnight. 2026-06-16. */
    val asleep: Boolean = false,
    /** Fast-carb fast-path toggle (ApsBoostV5FastCarbConfirm). Single-cycle confirm on sharp+accel+score. */
    val fastCarbConfirmEnabled: Boolean = false,
    /** 2026-07-17 aggressive early-confirm toggle (ApsBoostV5AggressiveEarlyConfirm, auto-config
     *  managed). Shaves the sustained-score early-confirm path one more cycle (age −2). Default false
     *  = the audit-validated −1 timing. See CONFIRM_MIN_OBSERVING_AGE_SCORE_READY_AGGRESSIVE. */
    val aggressiveEarlyConfirmEnabled: Boolean = false,
    val sensorQualityOk: Boolean = true,
    /** True when inside the post-rescue window (recentLowBG45Min < 75, computed at the override
     *  seam — same source/threshold as V1's Fix A v2 tier guard). Gates the composed floor off
     *  ([composedFloorTargetDose], 2026-07-06) — both the shadow field and, when
     *  [composedFloorActive], the delivered floor. */
    val postRescueWindow: Boolean = false,
    /** V1's would-dose SMB this cycle (rT.units BEFORE any V6 override), U. Used ONLY by the
     *  composed floor: RECOVERING is a non-meal state capped at V1's would-dose at the
     *  override seam (2026-07-02 non-meal-state cap), so the floored dose (shadow and active
     *  alike) is bounded the same way. Null = bound unavailable (not applied). */
    val v1WouldDoseU: Double? = null,
    /** 2026-07 composed brake-floor ACTIVATION (BooleanKey.ApsBoostV5ComposedFloorActive ∧ V6 is
     *  the active doser). False (default) = shadow semantics: [V5Decision.floorWouldAdd] logs what
     *  the floor WOULD add, delivered dosing untouched. True = the delivered dose is floored at
     *  the composed-floor target on qualifying cycles (see decide()); the same field then logs
     *  the uplift actually applied. Per-user activation only — TBR-gated, see the key's KDoc. */
    val composedFloorActive: Boolean = false,
    /** 2026-07-17 velocity-budget floor ACTIVATION (BooleanKey.ApsBoostV5VelocityBudgetActive ∧ V6
     *  active ∧ fail-closed 14d-TBR gate). False (default) = shadow: [V5Decision.velocityBudgetWouldAdd]
     *  logs what the floor WOULD add, delivered dosing untouched. True = the delivered dose is floored
     *  at the velocity-budget target on qualifying budget≈0 high cycles, and the cycle is flagged
     *  [V5Decision.velocityBudgetExempt] so the override seam lets it out-dose V1 (committedCap-bounded).
     *  Per-user opt-in only — see velocityBudgetFloorTarget + the key's KDoc. */
    val velocityBudgetActive: Boolean = false,

    // Reset triggers
    val profileSwitched: Boolean = false,
    val pumpDisconnected: Boolean = false,
    val loopSuspended: Boolean = false,
    val timeJumpMinutes: Double = 0.0,

    // User-facing knobs
    val aggressionUserKnob: Double = 1.0,
    val hypoCautionUserKnob: Double = 1.0,
    /** Per-user "Sensitivity" budget multiplier ∈ [0.8, 1.2]. Default 1.0 = no change. */
    val sensitivityUserKnob: Double = 1.0,

    // Alpha: user-adjustable dose caps (default to the validated Fix-6 values). Let the operator
    // tighten V5's commit/holding doses live during active-dosing alpha.
    val confirmedCapU: Double = MAX_CONFIRMED_COMMIT_DOSE_U,
    val committedCapU: Double = MAX_COMMITTED_DOSE_U,
)

/** Persisted V5 state read from RT at cycle start, written back at cycle end. */
data class V5PersistedState(
    val mealHypothesis: MealHypothesisState = MealHypothesisState(),
    val mlMealLikelyNullStreak: Int = 0,
    /**
     * Previous cycle's meal_signal_score — input to the sustained-score early confirm
     * ([CONFIRM_MIN_OBSERVING_AGE_SCORE_READY], 2026-07-03). Held in V5StateStore's IN-MEMORY
     * cache only, deliberately NOT serialized to the preferences JSON blob: a process restart
     * loses it, which fails safe (streak=false → legacy confirm timing for one cycle).
     */
    val lastCycleScore: Double? = null,
)

/** Full per-cycle V5 output. Every field is reconstructable into the ~6 NS RT fields. */
data class V5Decision(
    val finalDose: Double,
    val score: Double,
    val scoreComponents: ScoreComponents,
    val mlWeightsRenormalized: Boolean,
    val mealHypothesis: MealHypothesis,
    val mealHypothesisAge: Int,
    val stateReset: Boolean,
    val aggressionBudget: AggressionBudgetResult,
    val actionMultiplier: Double,
    val velocityFactor: Double,      // 2026-07-10 telemetry: climb-velocity dose scale on the raw shot
    val insulinToDeliver: Double,    // = dose after velocity + state cap, before Phase-3 brakes
    val phase3: Phase3Result,        // phase3.finalDose = dose after the composed brake stack
    val newPersistedState: V5PersistedState,
    // 2026-07-03 gate telemetry (read-only; needed for the 2026-07-10 live gate review — a
    // dose-adequacy gate block was previously indistinguishable from a score fade in NS):
    /** "pass" = confirm-eligible OBSERVING cycle whose adequacy gate passed; "blocked" =
     *  eligibility met EXCEPT the gate; "n/a" otherwise. → `boostV5_confirmGate`. */
    val confirmGate: String = "n/a",
    /** Velocity-scaled prospective confirm shot (budget × CONFIRMED mult × velocityFactor), U —
     *  the exact quantity the adequacy gate compares to the floor. → `boostV5_prospectiveShot`. */
    val prospectiveConfirmShot: Double = 0.0,
    /** Composed Phase-3 floor (F = [PHASE3_COMPOSED_FLOOR]) telemetry — DUAL semantics keyed on
     *  [V5Inputs.composedFloorActive] (→ `boostV5_floorWouldAdd`, null when the floor conditions
     *  are unmet either way):
     *  - toggle OFF (shadow, 2026-07-06): extra U the floor WOULD have added this cycle vs the
     *    actual pipeline output; never affects [finalDose].
     *  - toggle ON (activation, 2026-07): the uplift actually APPLIED to [finalDose] —
     *    delivered-with-floor − what-unfloored-would-have-delivered; 0.0 when no uplift.
     *  See [composedFloorTargetDose]. */
    val floorWouldAdd: Double? = null,
    /** 2026-07-17 velocity-budget floor telemetry — DUAL semantics keyed on
     *  [V5Inputs.velocityBudgetActive] (→ `boostV5_velocityBudgetWouldAdd`; null when the floor's
     *  conditions are unmet either way): toggle OFF (shadow) = extra U the floor WOULD add vs the
     *  pipeline output; toggle ON (active) = the uplift actually applied to [finalDose]. */
    val velocityBudgetWouldAdd: Double? = null,
    /** 2026-07-17: true only when the ACTIVE velocity-budget floor lifted the delivered dose. The
     *  override seam reads this to exempt the cycle from the non-meal cap (the floor doses when V1
     *  doses ~0, so it must out-dose V1). The dose it exempts is committedCap + maxIOB bounded. */
    val velocityBudgetExempt: Boolean = false,
)

@Singleton
class DetermineBasalBoostV5 @Inject constructor() {
    /** Run one full V5 cycle. Pure function over inputs + prior state. */
    fun decide(inputs: V5Inputs, persisted: V5PersistedState): V5Decision {
        // Reset state machine if any reset condition fired (reboot equivalents)
        val (resetState, didReset) = resetIfNeeded(
            current = persisted.mealHypothesis,
            profileSwitched = inputs.profileSwitched,
            pumpDisconnected = inputs.pumpDisconnected,
            loopSuspended = inputs.loopSuspended,
            timeJumpMinutes = inputs.timeJumpMinutes,
        )

        // Phase 1.a — meal_signal_score
        val nextNullStreak =
            if (inputs.mlMealLikely == null) persisted.mlMealLikelyNullStreak + 1 else 0
        val scoreResult = mealSignalScore(
            delta = inputs.delta,
            deltaAccl = inputs.deltaAccl,
            mlMealLikely = inputs.mlMealLikely,
            recentLowBg = inputs.recentLowBg,
            hour = inputs.hour,
            exerciseActive = inputs.exerciseActive,
            cumulativeRise30min = inputs.cumulativeRise30min,
            mlMealLikelyNullStreak = nextNullStreak,
        )

        // Phase 1.c HOISTED — AggressionBudget is state-independent (takes no meal-state input), so
        // compute it BEFORE the state step so the OBSERVING→CONFIRMED dose-adequacy gate can size the
        // prospective commit-shot. Pure reorder, no behaviour change. (2026-07-02)
        val budget = aggressionBudget(
            baseInsulinReq = inputs.baseInsulinReq,
            mlHypoRisk = inputs.mlHypoRisk,
            inPostExerciseWindow = inputs.inPostExerciseWindow,
            hypoCautionUserKnob = inputs.hypoCautionUserKnob,
            sensitivityUserKnob = inputs.sensitivityUserKnob,
        )

        // Dose-adequacy gate for OBSERVING→CONFIRMED (2026-07-02): the single per-session commit-shot
        // must beat one routine COMMITTED hold cycle (committedCapU) to be worth spending — else a
        // trivial pre-meal upswing burns the token and the committedInSession lock starves the meal on
        // holds alone (the 2026-07-01 eventualBG→372 incident). Uses the mlHypoRisk-DAMPED budget, so
        // confirm is also held back when hypo risk is elevated. Clamped strictly below confirmedCapU so
        // a manual committedCap ≥ confirmedCap can't make the gate unsatisfiable (which would silently
        // disable V6 meal response). Fast-carb fast-path is exempt (handled inside step()).
        // 2026-07-02 (2): the gate sizes the shot as it would actually DELIVER — including velocity
        // scaling — not the pre-velocity raw. Backtest (1,860 deduped cohort confirms): the raw gate
        // passed 1,072 of which 384 (35.8%) delivered BELOW the floor after velocity scaling — token
        // burnt on a sub-hold shot, recreating the starvation the gate exists to prevent. The
        // velocityFactor is hoisted here (pure fn of inputs) and reused by Phase 2.5 below.
        val velocityFactor = velocityScaledDoseFactor(inputs.cumulativeRise30min)
        val prospectiveConfirmShot = budget.budget * mealActionMultiplier(MealHypothesis.CONFIRMED, inputs.aggressionUserKnob) * velocityFactor
        // 2026-07-06: committedCap term of the floor is PINNED at the factory default (0.5 U) so a
        // user-raised committedCap can't silently tighten the confirm gate — see confirmDoseFloorU.
        val confirmDoseFloor = confirmDoseFloorU(inputs.committedCapU, inputs.confirmedCapU)
        val confirmDoseAdequate = prospectiveConfirmShot > confirmDoseFloor

        // 2026-07-03 sustained-score early confirm input: was LAST cycle's score already
        // confirm-ready? Sourced from the in-memory persisted state (null on cold start → false →
        // legacy timing). Used by step() AND the confirmGate telemetry below.
        val scoreReadyStreak = (persisted.lastCycleScore ?: 0.0) >= CONFIRM_SCORE

        // 2026-07-03 gate telemetry (boostV5_confirmGate) — read-only, ZERO dosing-path effect.
        // Labels this cycle's OBSERVING→CONFIRMED adequacy-gate outcome so a gate block is
        // distinguishable from a score fade in NS (needed for the 2026-07-10 live gate review):
        //   "pass"    — confirm-eligible OBSERVING cycle, adequacy gate passed
        //   "blocked" — eligibility met EXCEPT the adequacy gate
        //   "n/a"     — not otherwise eligible this cycle
        // Uses the SAME predicate step() doses with (confirmEligibleExceptDoseGate), so the two
        // can never diverge.
        val confirmGate = when {
            !confirmEligibleExceptDoseGate(resetState, scoreResult.score, inputs.eventualBg, inputs.targetBg, scoreReadyStreak, inputs.aggressiveEarlyConfirmEnabled) -> "n/a"
            confirmDoseAdequate                                                                                                -> "pass"
            else                                                                                                               -> "blocked"
        }

        // Phase 1.b — state machine step
        val newHypothesisState = step(
            current = resetState,
            score = scoreResult.score,
            eventualBg = inputs.eventualBg,
            targetBg = inputs.targetBg,
            delta = inputs.delta,
            deltaAccl = inputs.deltaAccl,
            deltaDeclining = deltaDeclining(inputs.deltaHistory, windowCycles = 2),
            asleep = inputs.asleep,
            exerciseActive = inputs.exerciseActive,
            // 2026-07-02: post-hypo rescue-carb guard — fast path suppressed when the 60-min low
            // is < FAST_CONFIRM_MIN_RECENT_LOW_MGDL (replay-calibrated; see MealHypothesis.kt).
            fastConfirmEnabled = fastConfirmAllowed(inputs.fastCarbConfirmEnabled, inputs.recentLowBg),
            confirmDoseAdequate = confirmDoseAdequate,
            scoreReadyStreak = scoreReadyStreak,   // 2026-07-03 sustained-score early confirm (hoisted above)
            aggressiveEarlyConfirm = inputs.aggressiveEarlyConfirmEnabled,   // 2026-07-17 opt-in age −2
        )

        // Phase 2 — single decision rule
        val actionMult = mealActionMultiplier(newHypothesisState.state, inputs.aggressionUserKnob)
        val rawInsulinToDeliver = budget.budget * actionMult

        // Phase 2.5 — Fix 6 dose calibration (2026-05-26)
        //
        // Diagnosed from 2026-05-25 evening meal: V5's CONFIRMED commit-shot produces 2.5-3.15U
        // single doses on slow-meal climbs, calibrated for the sharp-meal case where the 1.8×
        // CONFIRMED multiplier matches a genuine "catch-up" need. For slow meals (the case
        // Fix 4+5 was added to detect), 3U commits are dangerously aggressive — V4.4.2's actual
        // 1.5U delivery on the same climb caused a hypo (BG 192 → 48). V5 dosing 2-3× more
        // would be catastrophic.
        //
        // Two-stage calibration applied here:
        //   1. Velocity scaling — scale the dose by climb velocity (Fix 4's cumulativeRise30min
        //      signal). Sharp meals (≥50 mg/dL over 30 min) keep the full dose; slow meals
        //      (≤25 mg/dL) get 40% of it; linear interpolation between.
        //   2. State-specific hard cap — regardless of computed dose, CONFIRMED commits cap at
        //      MAX_CONFIRMED_COMMIT_DOSE_U; COMMITTED holding doses cap at MAX_COMMITTED_DOSE_U.
        //      These caps are calibrated so V5 cannot deliver more than V4.4.2 would on the same
        //      cycle, regardless of any upstream bug.
        // velocityFactor hoisted above the state step (used by the confirm dose gate). (2026-07-02)
        val velocityScaled = rawInsulinToDeliver * velocityFactor
        val cappedInsulinToDeliver = applyStateDoseCap(newHypothesisState.state, velocityScaled, inputs.confirmedCapU, inputs.committedCapU)
        val insulinToDeliver = cappedInsulinToDeliver

        // Phase 3 — ordered safety gates
        val phase3 = applyPhase3(Phase3Inputs(
            insulinToDeliver = insulinToDeliver,
            enableSmbPreChecks = inputs.enableSmbPreChecks,
            minGuardBg = inputs.minGuardBg,
            minGuardThreshold = inputs.minGuardThreshold,
            maxDelta = inputs.maxDelta,
            bg = inputs.bg,
            iob = inputs.iob,
            maxIob = inputs.maxIob,
            deltaAccl = inputs.deltaAccl,
            delta = inputs.delta,
            baseInsulinReq = inputs.baseInsulinReq,
            roundSmbTo = inputs.roundSmbTo,
            sensorQualityOk = inputs.sensorQualityOk,
            riskAtProjectedIob = inputs.riskAtProjectedIob,
            mlHypoRisk = inputs.mlHypoRisk,
        ))

        // 2026-07-06 composed Phase-3 floor. Computed here because this is the one place the whole
        // composed multiplier stack (state mult × velocityFactor × iobHeadroomBrake ×
        // decelerationBrake) has already been applied (phase3.finalDose). See
        // composedFloorTargetDose for the defect + backtest evidence. Target semantics: null =
        // floor conditions unmet; 0.0 = a Phase-3 HARD gate fired; else the bounded floored dose
        // min(budget × F, committedCapU) (v1-bounded in RECOVERING).
        val floorTarget = composedFloorTargetDose(
            state = newHypothesisState.state,
            bg = inputs.bg,
            eventualBg = inputs.eventualBg,
            targetBg = inputs.targetBg,
            asleep = inputs.asleep,
            postRescueWindow = inputs.postRescueWindow,
            budgetU = budget.budget,
            committedCapU = inputs.committedCapU,
            v1WouldDoseU = inputs.v1WouldDoseU,
            hardGateFired = phase3.reductions.hardGateFired != null,
        )
        var finalDose: Double
        val floorWouldAdd: Double?
        if (!inputs.composedFloorActive) {
            // SHADOW (toggle OFF, or V6 not the active doser) — zero dosing-path effect, the field
            // logs what the floor WOULD have added. Bit-identical to the 2026-07-06 shadow.
            finalDose = phase3.finalDose
            floorWouldAdd = floorTarget?.let { kotlin.math.max(0.0, it - phase3.finalDose) }
        } else {
            // ACTIVE (2026-07 per-user activation): deliver max(pipeline dose, floored dose). The
            // floored dose passes through the SAME downstream clamps the pipeline dose already
            // received after the soft-brake product, so no hard gate or cap is ever bypassed:
            //  - Phase-3 HARD gates: floorTarget is 0.0 whenever one fired (checked above);
            //  - maxIOB clamp: explicit min against the same headroom applyPhase3 clamps to;
            //  - state caps: floorTarget ≤ committedCapU by construction (min inside the target);
            //  - dynamic spike cap: explicit min (provably slack — 0.25 × budget ≤ 0.3 ×
            //    baseInsulinReq < 2.5 × baseInsulinReq — but enforced anyway);
            //  - pump-step floor-rounding: same rule + epsilon as applyPhase3's final clamp;
            //  - override-seam caps (non-meal v1-bound, post-rescue cap, cumulative cap, sleep
            //    gate, boost-active gate) all run downstream on decision.finalDose exactly as
            //    today; RECOVERING is additionally v1-bounded inside floorTarget so the logged
            //    uplift matches what the seam actually delivers.
            val deliverableFloor = floorTarget?.let { target ->
                var f = minOf(target, kotlin.math.max(0.0, inputs.maxIob - inputs.iob))
                f = minOf(f, dynamicSpikeCap(inputs.baseInsulinReq))
                if (inputs.roundSmbTo > 0.0) f = kotlin.math.floor(f / inputs.roundSmbTo + 1e-9) * inputs.roundSmbTo
                kotlin.math.max(0.0, f)
            } ?: 0.0
            finalDose = kotlin.math.max(phase3.finalDose, deliverableFloor)
            // ACTIVE semantics of the same NS field: the uplift actually applied (0.0 when the
            // pipeline dose already met the floor) — the 07-10 review reads one field either way.
            floorWouldAdd = floorTarget?.let { finalDose - phase3.finalDose }
        }

        // 2026-07-17 velocity-budget floor (budget≈0 high tail). Mutually exclusive with the composed
        // floor by the budget condition (composed needs budget>0, this needs budget≤0.01), so at most
        // one target is non-null; layered here on top of the composed result. When ACTIVE and it
        // lifts the dose, the cycle is flagged velocityBudgetExempt so the override seam lets it
        // out-dose V1 (this floor doses when V1 doses ~0). Exposure is committedCap + maxIOB bounded;
        // the dynamic spike cap is deliberately NOT applied (2.5×baseInsulinReq ≈ 0 here would zero it).
        val vbTarget = velocityBudgetFloorTarget(
            state = newHypothesisState.state,
            bg = inputs.bg,
            budgetU = budget.budget,
            committedCapU = inputs.committedCapU,
            asleep = inputs.asleep,
            postRescueWindow = inputs.postRescueWindow,
            hardGateFired = phase3.reductions.hardGateFired != null,
        )
        val velocityBudgetWouldAdd: Double?
        var velocityBudgetExempt = false
        if (!inputs.velocityBudgetActive) {
            // SHADOW (toggle OFF, or V6 not the active doser) — logs what the floor WOULD add;
            // delivered dose untouched.
            velocityBudgetWouldAdd = vbTarget?.let { kotlin.math.max(0.0, it - phase3.finalDose) }
        } else {
            val vbDeliverable = vbTarget?.let { target ->
                var f = minOf(target, kotlin.math.max(0.0, inputs.maxIob - inputs.iob))
                if (inputs.roundSmbTo > 0.0) f = kotlin.math.floor(f / inputs.roundSmbTo + 1e-9) * inputs.roundSmbTo
                kotlin.math.max(0.0, f)
            } ?: 0.0
            val lifted = kotlin.math.max(finalDose, vbDeliverable)
            velocityBudgetExempt = vbTarget != null && lifted > finalDose
            finalDose = lifted
            // ACTIVE: the uplift actually applied (finalDose-before-VB == phase3.finalDose here,
            // since composed and VB never co-fire).
            velocityBudgetWouldAdd = vbTarget?.let { finalDose - phase3.finalDose }
        }

        return V5Decision(
            finalDose = finalDose,
            score = scoreResult.score,
            scoreComponents = scoreResult.components,
            mlWeightsRenormalized = scoreResult.mlWeightsRenormalized,
            mealHypothesis = newHypothesisState.state,
            mealHypothesisAge = newHypothesisState.ageCycles,
            stateReset = didReset,
            aggressionBudget = budget,
            actionMultiplier = actionMult,
            velocityFactor = velocityFactor,
            insulinToDeliver = insulinToDeliver,
            phase3 = phase3,
            newPersistedState = V5PersistedState(
                mealHypothesis = newHypothesisState,
                mlMealLikelyNullStreak = nextNullStreak,
                lastCycleScore = scoreResult.score,
            ),
            confirmGate = confirmGate,
            prospectiveConfirmShot = prospectiveConfirmShot,
            floorWouldAdd = floorWouldAdd,
            velocityBudgetWouldAdd = velocityBudgetWouldAdd,
            velocityBudgetExempt = velocityBudgetExempt,
        )
    }
}

// ===== Fix 6 dose calibration (2026-05-26) =====

/**
 * Hard upper cap on the CONFIRMED commit-shot dose, in units. The 5/25 evening meal showed
 * V5's raw CONFIRMED dose reaches 2.5-3.15U for slow-meal climbs at typical baseInsulinReq —
 * far exceeding what V4.4.2 actually delivers in the same scenario (~1.5U cumulative across
 * multiple small SMBs), and on a climb where 1.5U already caused a hypo. 1.0U is the DEFAULT
 * CONFIRMED commit cap. NOTE: the effective cap at runtime is `Inputs.confirmedCapU`
 * (preferences.ApsBoostV5ConfirmedCapU, defaulting to this value) — this constant is the default,
 * not a hard floor/ceiling; a user/auto-config pref above 1.0 will raise the actual cap.
 */
internal const val MAX_CONFIRMED_COMMIT_DOSE_U = 1.0

/**
 * Hard upper cap on COMMITTED holding doses (post-commit-shot, sustaining meal coverage).
 * V4.4.2's per-cycle SMBs in this phase are typically 0.10-0.20U. Set to 0.25U: matches V4.4.x
 * per-cycle magnitude, while leaving room for slightly larger holding doses on genuine
 * sustained climbs. With rapid invokes (every 1-3 min in practice during meal events), this
 * caps the COMMITTED holding-dose stream to ≤0.25U per invoke.
 */
internal const val MAX_COMMITTED_DOSE_U = 0.25

/**
 * Cumulative-rise (mg/dL over last 30 min, from Fix 4) below this threshold scales the dose
 * to [VELOCITY_SCALE_FLOOR]. Above [VELOCITY_RISE_HI_MGDL] the dose is unscaled. Linear in
 * between.
 */
internal const val VELOCITY_RISE_LO_MGDL = 25.0
internal const val VELOCITY_RISE_HI_MGDL = 50.0
internal const val VELOCITY_SCALE_FLOOR = 0.40

/**
 * Velocity-aware dose scaling factor. Returns 1.0 for sharp meals (cumulative rise ≥ 50 mg/dL
 * over 30 min — full V5 dose applies), [VELOCITY_SCALE_FLOOR] for slow meals (≤ 25 mg/dL —
 * 40% of dose), linear interpolation between.
 *
 * Rationale: V5's CONFIRMED 1.8× catch-up multiplier is calibrated for sharp meals where waiting
 * 2 cycles in OBSERVING genuinely warrants a larger commit. Fix 4+5 unlocked V5 detection on
 * slow meals where the same 1.8× multiplier produces over-aggressive commits relative to the
 * actual carb absorption rate. Scaling by the same Fix 4 signal that triggered the detection
 * is the natural calibration knob.
 */
internal fun velocityScaledDoseFactor(cumulativeRise30min: Double): Double {
    if (cumulativeRise30min >= VELOCITY_RISE_HI_MGDL) return 1.0
    if (cumulativeRise30min <= VELOCITY_RISE_LO_MGDL) return VELOCITY_SCALE_FLOOR
    val span = VELOCITY_RISE_HI_MGDL - VELOCITY_RISE_LO_MGDL
    val frac = (cumulativeRise30min - VELOCITY_RISE_LO_MGDL) / span
    return VELOCITY_SCALE_FLOOR + (1.0 - VELOCITY_SCALE_FLOOR) * frac
}

/**
 * State-specific hard upper cap on the dose. Defense-in-depth: even if the upstream multiplier
 * stack produces a large value, this clamps it to a known-safe magnitude per state.
 *
 * - **CONFIRMED**: capped at [MAX_CONFIRMED_COMMIT_DOSE_U] (1.0 U). The commit-shot is the
 *   single most dose-impactful decision V5 makes; safety floor it tightly until validation
 *   data justifies raising the cap.
 * - **COMMITTED**: capped at [MAX_COMMITTED_DOSE_U] (0.25 U default; runtime cap is the
 *   auto-configured `Inputs.committedCapU`). Multiple of these can fire per meal (one per cycle
 *   while COMMITTED), so the per-cycle cap must be smaller.
 * - **IDLE / OBSERVING / RECOVERING**: NO cap here — IDLE is 1.0× and RECOVERING 0.4× of budget
 *   (they DO dose). Since 2026-07-02 these states are instead capped at V1's would-dose at the
 *   override site (OpenAPSBoostPlugin, "non-meal-state cap") — V6 may only out-dose V1 when it
 *   holds a meal hypothesis.
 */
internal fun applyStateDoseCap(
    state: MealHypothesis,
    dose: Double,
    confirmedCapU: Double = MAX_CONFIRMED_COMMIT_DOSE_U,
    committedCapU: Double = MAX_COMMITTED_DOSE_U,
): Double = when (state) {
    MealHypothesis.CONFIRMED -> dose.coerceAtMost(confirmedCapU)
    MealHypothesis.COMMITTED -> dose.coerceAtMost(committedCapU)
    else -> dose
}

// ===== 2026-07-06 composed Phase-3 floor (F = 0.25) — shadow first, per-user activatable =====

/**
 * Floor fraction of the (mlHypoRisk-damped) AggressionBudget the composed multiplier stack may
 * not push the dose below on a meal-session high cycle.
 *
 * 2026-07-06 forensic + 40,180-cycle cohort backtest: on meal-session high cycles
 * (CONFIRMED/COMMITTED/RECOVERING ∧ BG > 160 ∧ eventualBG > target+20 ∧ awake ∧ budget > 0) the
 * composed post-budget multiplier — stateMult × velocityFactor × iobHeadroomBrake ×
 * decelerationBrake — has MEDIAN 0.037. That is the V4-era "multiplicative brake stack"
 * reassembled from individually-sane gates: each brake is calibrated alone, but their product
 * drives the dose below one pump step, so it floor-rounds to ZERO for 30+ minutes mid-meal.
 * Tim's Episode B: BG 268–277, six consecutive zero-dose cycles, ended 297 + a manual bolus.
 * This is a pipeline defect (independent brakes multiplying), not a calibration issue.
 *
 * F = 0.25 backtests at +0.76 U/user-day with 16.6% pre-low incidence — the base rate, i.e. no
 * added hypo exposure. SHADOW window first: with the toggle OFF, [composedFloorTargetDose] only
 * feeds the `boostV5_floorWouldAdd` telemetry (what the floor WOULD have added) and delivered
 * dosing is untouched. 2026-07 activation: BooleanKey.ApsBoostV5ComposedFloorActive (Advanced,
 * default OFF) applies the floor to the delivered dose — PER-USER only, TBR-gated (the same-day
 * re-review excluded cohort users B/C/D, whose TBR would cross the 3.5% / 0.8% absolutes).
 */
internal const val PHASE3_COMPOSED_FLOOR = 0.25

/** Composed-floor shadow: BG must exceed this (mg/dL) — "high cycle" condition. */
internal const val COMPOSED_FLOOR_MIN_BG_MGDL = 160.0

/** Composed-floor shadow: eventualBG must exceed target by more than this (mg/dL). */
internal const val COMPOSED_FLOOR_MIN_EVENTUAL_OFFSET_MGDL = 20.0

/**
 * The composed Phase-3 floor's target dose (U) for this cycle — the single source of truth for
 * BOTH the shadow field (toggle OFF: `wouldAdd = max(0, target − actualFinalDose)`) and the
 * delivered floor (toggle ON: `finalDose = max(pipeline, clamped-and-rounded target)`), so the
 * two can never diverge. See [PHASE3_COMPOSED_FLOOR] for the 2026-07-06 forensic/backtest
 * rationale.
 *
 * Returns:
 * - **null** when the floor conditions are unmet. Conditions (ALL required): meal session
 *   (CONFIRMED/COMMITTED/RECOVERING) ∧ bg > 160 ∧ eventualBg > targetBg + 20 ∧ !asleep ∧
 *   !postRescueWindow ∧ budget > 0. The budget > 0 condition makes the Episode-A guard hold BY
 *   CONSTRUCTION: a zero budget (e.g. baseInsulinReq = 0 near target, or a fully-damped
 *   hypo-risk cycle) can never produce a floored dose.
 * - **0.0** when a Phase-3 HARD gate fired (enableSMB pre-checks, minGuardBG, maxDelta): those
 *   zero the dose regardless of any multiplier floor, so the floor may add nothing.
 * - Otherwise the bounded floored dose = min(budget × F, committedCapU) — one routine hold is
 *   the ceiling — additionally bounded at [v1WouldDoseU] in RECOVERING, which is a NON-meal
 *   state at the override seam (capped at V1's would-dose since the 2026-07-02 non-meal-state
 *   cap). Both bounds keep the shadow honest AND keep the active floor inside the seam's caps.
 */
/**
 * Composed brake-floor hypo-gate thresholds (trailing 14 days). The floor is insulin-ADDING, so it
 * may only ever alter delivered dose for users with low hypo exposure (Tim, 2026-07-08). BOTH must
 * hold — enforced, not advisory:
 *  - time-below-63 mg/dL (3.5 mmol, the TING lower bound) < [COMPOSED_FLOOR_MAX_TBR63_PCT], AND
 *  - time-below-70 mg/dL < [COMPOSED_FLOOR_MAX_TBR70_PCT] (the two-test-bar PRIMARY gate — added
 *    2026-07-08 so the gate keys on the same axis the two-test bar does, not the <63 proxy alone).
 *    BOTH use the SAME 14d window. NB: on 14d the re-validation's borderline user C ENGAGES (her
 *    14d <70 3.12%, <63 1.56% — both under bar); the manual HOLD on C came from her 30d <70 (3.95%),
 *    a different window now deliberately superseded by this self-updating 14d gate, which auto-holds
 *    any user the moment their 14d <70 reaches 3.5% or <63 reaches 2.0%.
 */
const val COMPOSED_FLOOR_MAX_TBR63_PCT = 2.0
const val COMPOSED_FLOOR_MAX_TBR70_PCT = 3.5

/**
 * Whether the composed brake-floor may engage, given the user's trailing-14d time-below-63 AND
 * time-below-70 mg/dL. FAIL-CLOSED: a null in EITHER (not yet computed, or insufficient CGM history
 * to trust the fraction) means NOT allowed — an insulin-adding feature never engages without evidence
 * the user is not hypo-prone. Thresholds are strict (<), so a user exactly at either limit is blocked.
 */
internal fun composedFloorAllowedByTbr(
    tbrBelow63Pct: Double?,
    tbrBelow70Pct: Double?,
    max63: Double = COMPOSED_FLOOR_MAX_TBR63_PCT,
    max70: Double = COMPOSED_FLOOR_MAX_TBR70_PCT
): Boolean =
    tbrBelow63Pct != null && tbrBelow63Pct < max63 &&
        tbrBelow70Pct != null && tbrBelow70Pct < max70

internal fun composedFloorTargetDose(
    state: MealHypothesis,
    bg: Double,
    eventualBg: Double,
    targetBg: Double,
    asleep: Boolean,
    postRescueWindow: Boolean,
    budgetU: Double,
    committedCapU: Double,
    v1WouldDoseU: Double?,
    hardGateFired: Boolean,
): Double? {
    val mealSession = state == MealHypothesis.CONFIRMED ||
        state == MealHypothesis.COMMITTED ||
        state == MealHypothesis.RECOVERING
    val conditionsMet = mealSession &&
        bg > COMPOSED_FLOOR_MIN_BG_MGDL &&
        eventualBg > targetBg + COMPOSED_FLOOR_MIN_EVENTUAL_OFFSET_MGDL &&
        !asleep &&
        !postRescueWindow &&
        budgetU > 0.0
    if (!conditionsMet) return null
    // Hard gates (enableSMB pre-checks, minGuardBG, maxDelta) zero the dose regardless of any
    // multiplier floor — the floored pipeline would deliver 0 too, so the floor adds nothing.
    if (hardGateFired) return 0.0
    val flooredDose = minOf(budgetU * PHASE3_COMPOSED_FLOOR, committedCapU)
    // RECOVERING: v1-bound where applicable (non-meal-state cap at the override seam).
    return if (state == MealHypothesis.RECOVERING && v1WouldDoseU != null)
        minOf(flooredDose, v1WouldDoseU) else flooredDose
}

// ===== 2026-07-17 velocity-budget floor (user H "postprandial highs") — budget≈0 high tail =====

/** Velocity-budget floor: current BG must exceed this (mg/dL). Higher than the composed floor's
 *  160 — this floor deliberately doses when oref's insulinReq is ~0 (budget≈0), so it is confined
 *  to a genuinely high BG. */
internal const val VELOCITY_BUDGET_MIN_BG_MGDL = 180.0

/** Budget at/below this (U) is "oref says covered" (baseInsulinReq≈0) — the population the composed
 *  floor EXCLUDES (it requires budget>0). The two floors are mutually exclusive by this condition. */
internal const val VELOCITY_BUDGET_MAX_BUDGET_U = 0.01

/** Tier-equivalent hold delivered by the velocity-budget floor (U), before the committedCap and
 *  maxIOB bounds. ≈ V1's per-cycle velocity-tier addition (~0.5U) that V6 drops to 0 on this tail. */
internal const val VELOCITY_BUDGET_TIER_U = 0.5

/**
 * Velocity-budget floor target dose (U), or null when its conditions are unmet. Addresses the
 * budget≈0 high tail — cycles where oref's insulinReq ≤ 0 (the model says "covered") but the user
 * is sitting high — the population [composedFloorTargetDose] deliberately EXCLUDES (it requires
 * budget > 0).
 *
 * This floor is unique: when delivered it must OUT-DOSE V1 in a non-meal state (V1 also doses ~0
 * when insulinReq ≤ 0), so the caller flags the cycle exempt from the override seam's non-meal cap.
 * The exposure is bounded to ONE routine hold — target = min(tier, committedCap) — and the caller
 * additionally clamps to maxIOB headroom + pump rounding (NOT the dynamic spike cap, which is
 * 2.5×baseInsulinReq ≈ 0 here and would wrongly zero the floor). It NEVER bypasses a Phase-3 HARD
 * gate (returns 0.0 when one fired) nor the cumulative-60min / boost-active / sleep / post-rescue
 * seam guards (all upstream of the exemption). PER-USER opt-in + fail-closed 14d-TBR gate only
 * (BooleanKey.ApsBoostV5VelocityBudgetActive ∧ composedFloorTbrAllowed) — it deliberately overrides
 * a prediction that was right-by-outcome on the shadow data, justified only by low hypo exposure.
 *
 * Conditions (ALL): state ≠ RECOVERING ∧ bg > 180 ∧ budget ≤ 0.01 ∧ !asleep ∧ !postRescueWindow.
 * - RECOVERING is EXCLUDED: dosing into a decelerating high is the RECOVERING-SMB pattern rejected
 *   2026-07-03 (adds into a high-IOB tail → lows).
 * - Deliberately NOT gated on "rising": the 2026-07-17 sizing showed the rising (delta>3) sub-cell
 *   is crash-prone (10.7% pre-low, n=28) while the sustained high tail prices under the base rate
 *   (4.3% vs 5.8%). Sustained-high is the safer target than sharp-rise.
 */
internal fun velocityBudgetFloorTarget(
    state: MealHypothesis,
    bg: Double,
    budgetU: Double,
    committedCapU: Double,
    asleep: Boolean,
    postRescueWindow: Boolean,
    hardGateFired: Boolean,
): Double? {
    val conditionsMet = state != MealHypothesis.RECOVERING &&
        bg > VELOCITY_BUDGET_MIN_BG_MGDL &&
        budgetU <= VELOCITY_BUDGET_MAX_BUDGET_U &&
        !asleep &&
        !postRescueWindow
    if (!conditionsMet) return null
    if (hardGateFired) return 0.0
    return minOf(VELOCITY_BUDGET_TIER_U, committedCapU)
}
