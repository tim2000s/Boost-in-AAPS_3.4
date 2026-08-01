package app.aaps.plugins.aps.openAPSBoostV7

import app.aaps.plugins.aps.openAPSBoostV5.MealHypothesis
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min

/**
 * V7Sizer — the REVISED distributional-sizing rule, shadow-only.
 *
 * Lineage: the offline rule (backtesting/scripts/2026-07-v7-foundation/03_distributional_sizing.py)
 * was NO-GO (report §3): (a) cost-ratio INSENSITIVE — R=4/7/10 produced identical doses for every
 * user because the biased q25 shoulder never projected <70, so the safety knob did nothing and the
 * rule rode the substrate's +12..+38 median bias; (b) it added sub-120-BG insulin nobody asked for.
 * This class is the LIVE instrument for iterating past criterion (a); the regime-conditioned pools
 * ([V7Regime]) are the instrument for criterion (b).
 *
 * What is ported EXACTLY from 03:
 *  - the asymmetric linear utility: loss(d) = mean over the predictive distribution of
 *    R × max(0, 70 − BG(d)) + max(0, BG(d) − 140), R ∈ {4, 7, 10} (low-side cost ratio ×
 *    high-side per-mg·min proxy);
 *  - the h=60 point projection base = bg + BGI5 × 12 and the mid-curve dose action F_ACT = 0.5;
 *  - the dose grid 0..envelope step 0.05 (global grid ceiling 3.0 U), first-minimum tie-break;
 *  - the full bounds-not-gates guard structure: state-multiplier envelope, committedCap
 *    (COMMITTED), confirmedCap (CONFIRMED), non-meal v1-bound, post-rescue v1-bound (post-rescue
 *    exclusion of the meal-state exemption), rolling cumulative-cap awareness, budget ≤ 0 ⇒ 0.
 *
 * What is REVISED (the formulation change the shadow instruments):
 *  - the predictive distribution is no longer the 3-point {q25,q50,q75} set. With 3 equally
 *    weighted quantiles and R ≥ 4, a single quantile crossing below 70 always outweighs every
 *    high-side quantile (R×1 > 3), so the argmin is STRUCTURALLY identical for all R ∈ {4,7,10} —
 *    the offline insensitivity was baked into the formulation, not just the bias. Instead the
 *    pool's five validated quantiles (5/25/50/75/95) define a piecewise-linear inverse CDF,
 *    discretized at [TAIL_PROBS] (19 equal-probability points, 5%..95% step 5%), giving the left
 *    tail GRADED mass so the marginal condition R × P(BG<70) vs P(BG>140) resolves at different
 *    doses for different R. Beyond the 5%/95% knots the distribution is truncated — the report's
 *    tail-honesty finding (§1): the ≤5% tail is not fittable and may only ever TIGHTEN.
 *
 * Every cycle the shadow evaluates R = 4, 7 and 10 and logs all three doses
 * (boostV7_wouldDoseR4/R7/R10) — the live criterion-(a) instrument: if they remain identical in
 * the field, the formulation is still wrong.
 */
object V7Sizer {

    /** Fraction of a dose acting by the h=60 horizon (bilinear mid-curve) — 03's F_ACT. */
    const val F_ACT = 0.5

    /** Dose grid step, U — 03's grid. */
    const val GRID_STEP = 0.05

    /** Global grid ceiling, U — 03 used np.arange(0, 3.01, 0.05). */
    const val GRID_MAX_U = 3.0

    /** Asymmetric-utility thresholds, mg/dL — 03's low/high arms. */
    const val LOW_BG = 70.0
    const val HIGH_BG = 140.0

    /** Low:high cost ratios evaluated EVERY cycle (criterion-(a) instrument). */
    val COST_RATIOS = doubleArrayOf(4.0, 7.0, 10.0)

    /** State multiplier envelope (bounds-not-gates) — 03's MULT verbatim. */
    val STATE_MULT = mapOf(
        MealHypothesis.IDLE to 1.0,
        MealHypothesis.OBSERVING to 0.3,
        MealHypothesis.CONFIRMED to 1.8,
        MealHypothesis.COMMITTED to 1.0,
        MealHypothesis.RECOVERING to 0.4,
    )

    /** Probabilities of the five validated pool quantile knots. */
    val KNOT_PROBS = doubleArrayOf(0.05, 0.25, 0.50, 0.75, 0.95)

    /** Equal-probability discretization of the piecewise-linear inverse CDF (5%..95% step 5%). */
    val TAIL_PROBS = DoubleArray(19) { 0.05 * (it + 1) }

    /**
     * Per-cycle sizer inputs — everything is the live value at the shadow seam (same inputs the
     * V5 shadow just consumed; rT.units is still V1's would-dose there).
     */
    data class Inputs(
        val bg: Double,
        /** Undosed IOB-only projection of BG at the h=60 horizon (mg/dL) — oref's decaying-
         *  activity predBGs.IOB curve at 60 min (2026-07-27; replaces the constant-BGI5 hold,
         *  whose fall-overstatement grew with IOB and drove the pLow90 miscalibration). */
        val base60: Double,
        /** Adapted variable_sens (mg/dL/U) — the sens the projection used; also prices the dose. */
        val sens: Double,
        /** V5 meal-hypothesis state this cycle; null = V5 decision unavailable (abstain). */
        val state: MealHypothesis?,
        /** V5 aggression budget (U); null = unavailable (abstain). Budget ≤ 0 ⇒ dose 0 (03). */
        val budgetU: Double?,
        val committedCapU: Double,
        val confirmedCapU: Double,
        /** V1's would-dose (U) at the seam — the non-meal / post-rescue bound. Null → 0.0 (03's fillna). */
        val v1WouldDoseU: Double?,
        /** recentLowBG45Min < 75 — suppresses the meal-state exemption (post-rescue exclusion). */
        val postRescueWindow: Boolean,
        /** Rolling-60-min cumulative SMB cap (U); ≤ 0 = cap disabled (live pref semantics). */
        val cumulativeCapU: Double,
        /** SMB volume delivered in the trailing 60 min (U). */
        val smbVol60MinU: Double,
        /** Active regime pool residual quantiles at h=60, aligned with [KNOT_PROBS] (5/25/50/75/95). */
        val residualQuantiles: DoubleArray,
    )

    /** Would-doses aligned with [COST_RATIOS], plus the operative envelope for telemetry. */
    data class Result(val doses: DoubleArray, val envelopeU: Double) {

        val doseR4 get() = doses[0]
        val doseR7 get() = doses[1]
        val doseR10 get() = doses[2]
        val dosesDiffer get() = doses.any { kotlin.math.abs(it - doses[0]) > 1e-9 }
    }

    /**
     * Size the would-dose at every cost ratio. Returns null when the rule ABSTAINS (no V5
     * state/budget, unusable sens, or malformed quantiles) — distinct from a computed 0.0.
     */
    fun size(inp: Inputs): Result? {
        val state = inp.state ?: return null
        val budget = inp.budgetU ?: return null
        if (!inp.sens.isFinite() || inp.sens <= 0.0 || !inp.bg.isFinite() || !inp.base60.isFinite()) return null
        if (inp.residualQuantiles.size != KNOT_PROBS.size || inp.residualQuantiles.any { !it.isFinite() }) return null

        // Envelope — 03's bounds, verbatim order. budget ≤ 0 ⇒ 0 (restraint preserved by construction).
        if (budget <= 0.0) return Result(DoubleArray(COST_RATIOS.size), 0.0)
        var env = budget * (STATE_MULT[state] ?: 1.0)
        if (state == MealHypothesis.COMMITTED) env = min(env, inp.committedCapU)
        if (state == MealHypothesis.CONFIRMED) env = min(env, inp.confirmedCapU)
        if (state != MealHypothesis.CONFIRMED && state != MealHypothesis.COMMITTED || inp.postRescueWindow)
            env = min(env, inp.v1WouldDoseU ?: 0.0)
        if (inp.cumulativeCapU > 0.0) env = min(env, max(0.0, inp.cumulativeCapU - inp.smbVol60MinU))
        if (env <= 0.0) return Result(DoubleArray(COST_RATIOS.size), 0.0)

        // Predictive distribution: base + interpolated residual draws (graded left tail).
        val base = inp.base60
        val draws = DoubleArray(TAIL_PROBS.size) { base + interpolateQuantile(TAIL_PROBS[it], inp.residualQuantiles) }

        val steps = floor(min(env, GRID_MAX_U) / GRID_STEP + 1e-9).toInt()
        val doses = DoubleArray(COST_RATIOS.size)
        for (r in COST_RATIOS.indices) {
            val ratio = COST_RATIOS[r]
            var bestDose = 0.0
            var bestLoss = Double.MAX_VALUE
            for (k in 0..steps) {
                val d = k * 5 / 100.0   // exact grid values (k × 0.05 accumulates float dust)
                val drop = d * inp.sens * F_ACT
                var loss = 0.0
                for (draw in draws) {
                    val bgq = draw - drop
                    loss += ratio * max(0.0, LOW_BG - bgq) + max(0.0, bgq - HIGH_BG)
                }
                // Strict less-than: ties keep the LOWEST dose (np.argmin first-minimum semantics).
                if (loss < bestLoss - 1e-12) {
                    bestLoss = loss
                    bestDose = d
                }
            }
            doses[r] = bestDose
        }
        return Result(doses, env)
    }

    /** Piecewise-linear inverse CDF through the five knots; clamped to [q5, q95] outside. */
    fun interpolateQuantile(p: Double, quantiles: DoubleArray): Double {
        if (p <= KNOT_PROBS.first()) return quantiles.first()
        if (p >= KNOT_PROBS.last()) return quantiles.last()
        for (i in 1 until KNOT_PROBS.size) {
            if (p <= KNOT_PROBS[i]) {
                val f = (p - KNOT_PROBS[i - 1]) / (KNOT_PROBS[i] - KNOT_PROBS[i - 1])
                return quantiles[i - 1] + f * (quantiles[i] - quantiles[i - 1])
            }
        }
        return quantiles.last()
    }

    /**
     * p(BG < 70 within 90 min) read off the piecewise-linear CDF of the regime pool's h=90
     * quantiles, evaluated at the UNDOSED projection [base90] (oref's decaying-activity
     * predBGs.IOB value at 90 min, 2026-07-27): the probability that residual < 70 − base90.
     * LEFT-SHOULDER TRUNCATION: below the 5% knot the tail is not fitted (report §1 tail
     * honesty), so values under 0.05 read 0.0. DISPLAY ONLY — never used for permission (the
     * chance constraint, when it comes, may only tighten).
     */
    fun pLow(base90: Double, quantiles90: DoubleArray): Double? {
        if (!base90.isFinite()) return null
        if (quantiles90.size != KNOT_PROBS.size || quantiles90.any { !it.isFinite() }) return null
        val threshold = LOW_BG - base90
        if (threshold < quantiles90.first()) return 0.0            // left of the validated shoulder
        if (threshold >= quantiles90.last()) return 1.0
        for (i in 1 until KNOT_PROBS.size) {
            if (threshold <= quantiles90[i]) {
                val span = quantiles90[i] - quantiles90[i - 1]
                val f = if (span <= 0.0) 1.0 else (threshold - quantiles90[i - 1]) / span
                return KNOT_PROBS[i - 1] + f * (KNOT_PROBS[i] - KNOT_PROBS[i - 1])
            }
        }
        return 1.0
    }
}
