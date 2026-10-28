package app.aaps.plugins.aps.openAPSBoostTing

import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min

/**
 * TING engine — core planner (2026-07-18).
 *
 * The strategic finding (backtesting/scripts/2026-07-ting-frontier): **TING (time in 63–140 mg/dL)
 * is a VARIANCE problem, not a dose-more problem.** Across the cohort, TING vs glucose CV r=−0.81
 * (r²=0.65) and TING vs the 140–180 "mild-high" band r=−0.86 (r²=0.74). The low-TING users are the
 * high-CV users; each +1% CV costs ~1.3pp TING. The addressable loss is the 140–180 band. The lever
 * is EARLIER + SMOOTHER dosing that compresses that band and drops CV — NOT bigger corrections,
 * which feed the high-IOB low-tail (the thrice-rejected "dose-more-into-highs" class).
 *
 * So this planner is a deliberate *smoother*, not an amplifier. It differs from the V6 reactive
 * engine in three ways, all aimed at CV:
 *   1. It acts on the FORECAST (short-horizon predicted BG), so it nudges *before* BG is high.
 *   2. It applies a low-gain PROPORTIONAL nudge toward a safety-biased aim INSIDE the band, and
 *      rate-limits the change from the last dose — a glide, not a slam. This is the anti-ringing
 *      mechanism that turns a 36%-CV sawtooth into a ~20%-CV glide.
 *   3. It NEVER chases glucose downward and NEVER breaches the low-tail: it holds when the forecast
 *      is in/under the band, and hard-clips every dose so the worst-case predicted low stays above
 *      the hypo floor.
 *
 * SAFETY / STATUS: this is a PURE function that returns a *would-dose*. It doses nothing itself.
 * It is SHADOW-first by construction and must be validated (offline characterisation, then live
 * shadow logging, then the two-test bar) before it is ever allowed to influence a delivered dose.
 * A dosing POLICY cannot be validated counterfactually (no glucodynamic simulator — the
 * identification constraint), so the offline backtest can only show it is *smoother and
 * floor-respecting*; earning the right to dose comes later, one shadow-validated step at a time.
 * The absolute floors are sacred and can only tighten (hard rule 3).
 */

/** Tight normo band (mg/dL). Matches the TING metric (3.5–7.8 mmol/L = 63–140 mg/dL). */
const val TING_LOW = 63.0
const val TING_HIGH = 140.0

/**
 * Aim point inside the band (mg/dL). Deliberately BELOW the 140 ceiling and comfortably ABOVE the
 * 63 floor — safety-biased low-of-centre so that forecast error costs high-time (recoverable) far
 * more readily than low-time (dangerous). We would rather sit at 110 and drift up than aim at 100
 * and risk the floor.
 */
const val TING_AIM = 112.0

/**
 * Proportional gain on the forecast gap. LOW on purpose: a gentle, repeated nudge is what keeps CV
 * down. A high gain would close the gap fast and ring the glucose — the exact sawtooth that costs
 * TING. 0.5 = close ~half the residual per cycle; the rest is handled by the next cycle's nudge.
 */
const val TING_GAIN = 0.5

/**
 * Fraction of a bolus that has acted by the planning horizon (~30–45 min). Rapid-acting insulin is
 * roughly a third active by then; the dose is sized so that fraction closes the forecast gap, not
 * the whole bolus (which would over-deliver and land as a low two hours later).
 */
const val TING_HORIZON_ACTIVITY = 0.35

/**
 * Anti-ringing rate limit (U): the would-dose may not exceed the last delivered dose by more than
 * this per cycle. Smoothness IS the objective — a controller that can leap dose-to-dose reintroduces
 * the variance we are trying to remove. The limit only caps INCREASES; cutting to zero is always
 * allowed (safety may always tighten).
 */
const val TING_MAX_STEP_UP_U = 0.20

/** Safety margin (mg/dL) held above the low-guard threshold when floor-clipping the dose. */
const val TING_FLOOR_MARGIN_MGDL = 8.0

data class TingInputs(
    /** Current glucose, mg/dL. */
    val bg: Double,
    /** Short-horizon predicted BG at the planning horizon (e.g. eventualBG or a UKF forecast), mg/dL. */
    val forecastBg: Double,
    /** Worst-case predicted low over the short horizon (the floor sensor — same source V5 uses), mg/dL. */
    val minGuardBg: Double,
    /** Low-glucose-suspend threshold, mg/dL. */
    val minGuardThreshold: Double,
    /** Insulin sensitivity, mg/dL per U (variable / DynISF). */
    val isf: Double,
    /** Insulin on board, U. */
    val iob: Double,
    /** IOB ceiling, U. */
    val maxIob: Double,
    /** Previous cycle's delivered dose, U (for the smoothness rate limit). */
    val lastDoseU: Double,
    /** Pump increment, U. */
    val roundSmbTo: Double,
)

data class TingDecision(
    /** The planner's would-dose, U. SHADOW: not delivered by this function. */
    val wouldDoseU: Double,
    /** Predicted BG at the horizon AFTER this dose acts, mg/dL — for telemetry / validation. */
    val projectedBg: Double,
    /** True if the dose was clipped by the low-tail floor (would-be dose exceeded the floor-safe cap). */
    val floorClipped: Boolean,
    /** Human-readable reason for the outcome. */
    val reason: String,
)

/**
 * One-step, risk-limited smoothing plan. Pure; no side effects. Returns a would-dose only.
 *
 * Order of operations (safety first, then smoothness):
 *  0. Hard floor — if a low is already imminent, dose 0 (the floor is sacred).
 *  1. Hold — if the forecast is in or below the band, dose 0 (never chase glucose down → never
 *     manufacture a low; below-band is the next cycle's problem for the base engine, not ours).
 *  2. Nudge — size a LOW-GAIN proportional dose to move the forecast a fraction of the way toward
 *     the aim, discounted by horizon activity.
 *  3. Smooth — rate-limit the increase over the last dose (anti-ringing).
 *  4. Clip — never let the worst-case predicted low fall below the floor+margin after this dose;
 *     never breach maxIOB; round to the pump step.
 */
fun tingPlan(inp: TingInputs): TingDecision {
    val isf = if (inp.isf > 1.0) inp.isf else 1.0
    val perU = isf * TING_HORIZON_ACTIVITY                    // mg/dL drop at the horizon per U dosed

    // 0. Hard floor — imminent low ⇒ nothing.
    if (inp.minGuardBg <= inp.minGuardThreshold) {
        return TingDecision(0.0, inp.forecastBg, floorClipped = true, reason = "floor: minGuard ${round1(inp.minGuardBg)} ≤ threshold")
    }
    // 1. Hold — forecast already in or below the tight band ⇒ nothing (never chase down).
    if (inp.forecastBg <= TING_AIM) {
        return TingDecision(0.0, inp.forecastBg, floorClipped = false, reason = "hold: forecast ${round1(inp.forecastBg)} ≤ aim (in/under band)")
    }
    // 2. Low-gain proportional nudge toward the aim, discounted by horizon activity.
    val gap = inp.forecastBg - TING_AIM                       // mg/dL above the aim
    val rawDose = (TING_GAIN * gap) / perU

    // 3. Smoothness: cap the increase over the last dose (cutting is always allowed).
    val smoothCap = inp.lastDoseU + TING_MAX_STEP_UP_U
    var dose = min(rawDose, smoothCap)

    // 4a. Floor clip — the worst-case predicted low must stay above threshold + margin after dosing.
    val floorHeadroomMgdl = inp.minGuardBg - (inp.minGuardThreshold + TING_FLOOR_MARGIN_MGDL)
    val floorCapU = max(0.0, floorHeadroomMgdl / perU)
    val floorClipped = dose > floorCapU + 1e-9
    dose = min(dose, floorCapU)
    // 4b. maxIOB headroom.
    dose = min(dose, max(0.0, inp.maxIob - inp.iob))
    // 4c. pump rounding (floor, never round up past a bound).
    if (inp.roundSmbTo > 0.0) dose = floor(dose / inp.roundSmbTo + 1e-9) * inp.roundSmbTo
    dose = max(0.0, dose)

    val projected = inp.forecastBg - dose * perU
    val reason = if (floorClipped) "nudge floor-clipped to ${round2(dose)}U (forecast ${round1(inp.forecastBg)}→${round1(projected)})"
    else "nudge ${round2(dose)}U (forecast ${round1(inp.forecastBg)}→${round1(projected)}, gap ${round1(gap)})"
    return TingDecision(dose, projected, floorClipped, reason)
}

private fun round1(v: Double) = kotlin.math.round(v * 10.0) / 10.0
private fun round2(v: Double) = kotlin.math.round(v * 100.0) / 100.0
