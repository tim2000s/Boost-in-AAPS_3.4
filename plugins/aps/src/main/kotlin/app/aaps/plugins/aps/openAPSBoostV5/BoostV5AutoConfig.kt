package app.aaps.plugins.aps.openAPSBoostV5

import kotlin.math.max
import kotlin.math.min

/**
 * Boost V5 auto-configuration — derive sensible initial V5 knobs from the user's own V1 dosing
 * history (default: last 14 days) when they first switch to the Boost V5 plugin.
 *
 * Rationale (see SHADOW_EQUIVALENCE_REPORT): V5's dose calibration is a *heuristic co-adapted with
 * the user*, so the safe onboarding is to **start where their V1 left off**, not on cohort defaults.
 * This computes a conservative, transparent suggestion from their proven dosing + glycaemia.
 *
 * PURE function — no Android / no I/O. The plugin gathers the [V1Profile] and applies + logs the
 * result. It is **suggestion** logic: the caller only writes knobs still at their factory default
 * (never overrides a user who has already tuned them) and surfaces what it set.
 *
 * Design principles:
 *  - **Conservative.** Never auto-RAISE aggression above neutral (1.0); only ease it down for a
 *    hypo-prone history. Safety knobs (HypoCaution, caps) are derived to bound, not to embolden.
 *  - **Carry proven constraints.** maxIOB / bolus cap mirror the user's existing AAPS values.
 *  - **Refine later.** Aggression can only be matched precisely once shadow data exists (paired
 *    V1/V5 cycles); the day-1 value is a gentle starting point, intentionally on the cautious side.
 */
object BoostV5AutoConfig {

    // Minimum data before we'll auto-configure at all (else leave factory defaults).
    const val MIN_DAYS = 7
    const val MIN_BG_READINGS = 1500          // ~7 days of 5-min CGM minus gaps

    // Glycaemic thresholds that trigger extra caution (international consensus targets).
    private const val TBR70_TARGET = 4.0      // % time <70 mg/dL

    /** Hypo-prone history cut-points (drive both the Aggression ease-down and fastCarbConfirm). */
    const val SEV54_HYPO_PRONE = 1.5
    const val TBR70_HYPO_PRONE = 6.0

    /**
     * 2026-07-17 — STRICT well-controlled cut-points that auto-enable the insulin-ADDING opt-in
     * switches (aggressive early confirm, velocity-budget floor). Much tighter than the hypo-prone
     * cut above: these switches deliberately add a little insulin, so they may only auto-engage for
     * users with clearly low trailing low-glucose exposure. The pre-push cohort backtest
     * (backtesting/scripts/2026-07-userh-levers/) set these — TBR<70 < 1.5% AND time<54 < 0.3%
     * enables A/E/H (user H clean at 0.0% fizzle pre-low) and excludes B/C/F/tim. A user may still
     * enable either switch manually; auto-config only sets a safe default and the velocity-budget
     * floor additionally has a live fail-closed 14d-TBR gate.
     */
    const val WELL_CONTROLLED_MAX_TBR70 = 1.5
    const val WELL_CONTROLLED_MAX_SEV54 = 0.3

    /** History window for auto-config (also used by the plugin's data pulls). */
    const val LOOKBACK_DAYS = 14L
    private const val SEV54_TARGET = 1.0      // % time <54 mg/dL

    /**
     * Minimum manual (NORMAL) boluses in the window before their p90 may drive the Confirmed cap.
     * Backtest evidence (7-user migration cohort, 2026-07-06): one user's derived confirmedCap of
     * 6.8 U rested on a p90 of just FOUR manual boluses — one of them an 8 U outlier. A percentile
     * of n=4 is noise, not a dose habit. Below this floor the Confirmed cap falls back to the SMB
     * p95 alone (still clamped to [1.5, 7.5]).
     */
    const val MIN_MANUAL_BOLUS_SAMPLES = 10

    /**
     * Upper clamp of the derived rolling-60-min cumulative SMB cap — the preference range max of
     * ApsBoostCumulativeSmbCap60Min (0..10). The cap formula is "one confirm shot + two holds"; the
     * clamp only stops it exceeding what the preference can express.
     */
    const val CUMULATIVE_CAP_MAX_U = 10.0

    /** What the plugin gathers from the user's last-N-day V1 history. */
    data class V1Profile(
        val daysWithData: Int,
        val bgReadingCount: Int,
        val tddMedianU: Double,
        val manualBolusesU: List<Double>,     // NORMAL (meal/manual) boluses
        val smbAmountsU: List<Double>,        // SMB micro-boluses
        val tbrBelow70Pct: Double,
        val timeBelow54Pct: Double,
        val meanGlucoseMgdl: Double,
        val currentMaxIobU: Double,           // the user's existing AAPS maxIOB
        val currentMaxBolusU: Double          // the user's existing AAPS max bolus
    )

    /** Suggested V5 knobs (each already clamped to its preference range) + human-readable reasons. */
    data class V5Suggestion(
        val aggression: Double,
        val hypoCaution: Double,
        val confirmedCapU: Double,
        val committedCapU: Double,
        val cumulativeSmbCap60MinU: Double,
        val maxIobU: Double,
        val bolusCapU: Double,
        val fastCarbConfirm: Boolean,
        // 2026-07-17 insulin-adding opt-in switches — enabled only for clearly well-controlled users.
        val aggressiveEarlyConfirm: Boolean,
        val velocityBudgetFloor: Boolean,
        val rationale: List<String>
    )

    /** Returns null when there isn't enough data to responsibly auto-configure. */
    fun compute(p: V1Profile): V5Suggestion? {
        if (p.daysWithData < MIN_DAYS || p.bgReadingCount < MIN_BG_READINGS) return null

        val reasons = mutableListOf<String>()
        val hypoProne = p.timeBelow54Pct > SEV54_HYPO_PRONE || p.tbrBelow70Pct > TBR70_HYPO_PRONE

        // HypoCaution [1.0..2.0]: scale up with time-below-range above target.
        val cautionRaw = 1.0 +
            max(0.0, p.tbrBelow70Pct - TBR70_TARGET) / 4.0 +       // +1.0 per +4% TBR over target
            max(0.0, p.timeBelow54Pct - SEV54_TARGET) * 0.5         // +0.5 per +1% severe over target
        val hypoCaution = round1(cautionRaw.coerceIn(1.0, 2.0))
        reasons += "HypoCaution $hypoCaution (TBR<70 ${pct(p.tbrBelow70Pct)}, <54 ${pct(p.timeBelow54Pct)} vs targets 4%/1%)"

        // Aggression [0.7..1.3]: NEVER auto-raise above 1.0. Ease down for a hypo-prone history.
        val aggression = round2(
            when {
                hypoProne                                       -> 0.85
                p.tbrBelow70Pct > TBR70_TARGET                  -> 0.92
                else                                            -> 1.0
            }
        )
        reasons += "Aggression $aggression (start ${if (aggression < 1.0) "gentle — hypo history" else "neutral"}; refines after shadow period)"

        // Confirmed cap [1.5..7.5]: cover their biggest typical single dose (meal bolus p90 or SMB
        // p95). The manual-bolus p90 participates only with a statistically honest sample
        // (>= MIN_MANUAL_BOLUS_SAMPLES in the window) — see the constant's KDoc for the n=4 case.
        val manualP90 =
            if (p.manualBolusesU.size >= MIN_MANUAL_BOLUS_SAMPLES) percentile(p.manualBolusesU, 90.0) else 0.0
        val confirmedCapU = round2(
            max(manualP90, percentile(p.smbAmountsU, 95.0)).coerceIn(1.5, 7.5)
        )
        reasons += "Confirmed cap ${confirmedCapU}U (≈ your biggest typical single dose)"

        // Committed cap [0.25..2.5]: routine per-cycle hold = max(typical SMB p75, TDD/40), floored.
        val committedCapU = round2(
            max(percentile(p.smbAmountsU, 75.0), p.tddMedianU / 40.0).coerceIn(0.25, 2.5)
        )
        reasons += "Committed cap ${committedCapU}U (max of your routine SMB size and TDD/40)"

        val cumulativeSmbCap60MinU = cumulativeCap60Min(confirmedCapU, committedCapU)
        reasons += "Cumulative SMB cap/60min ${cumulativeSmbCap60MinU}U (limits dose frequency)"

        // Carry proven constraints.
        val maxIobU = round1(p.currentMaxIobU.coerceIn(0.1, 12.0))
        val bolusCapU = round1(p.currentMaxBolusU.coerceIn(0.1, 10.0))
        reasons += "maxIOB ${maxIobU}U / bolus cap ${bolusCapU}U carried from your AAPS settings"

        // Fast-carb confirm: keep on unless markedly hypo-prone (then off for caution).
        val fastCarbConfirm = !hypoProne
        if (hypoProne) reasons += "Fast-carb confirm OFF (cautious start — notable hypo history)"

        // 2026-07-17 insulin-ADDING opt-in switches (aggressive early confirm, velocity-budget floor)
        // — auto-enable ONLY for clearly well-controlled users (strict low-glucose cut). They add a
        // little insulin, so the bar is tighter than fastCarbConfirm's !hypoProne. A user can still
        // enable either manually; this only sets a safe default. (Velocity-budget floor ALSO has a
        // live fail-closed 14d-TBR gate downstream.)
        val wellControlled = p.tbrBelow70Pct < WELL_CONTROLLED_MAX_TBR70 && p.timeBelow54Pct < WELL_CONTROLLED_MAX_SEV54
        val aggressiveEarlyConfirm = wellControlled
        val velocityBudgetFloor = wellControlled
        reasons += if (wellControlled)
            "Aggressive early confirm + velocity-budget floor ON (low-glucose exposure well within target: <70 ${pct(p.tbrBelow70Pct)}, <54 ${pct(p.timeBelow54Pct)})"
        else
            "Aggressive early confirm + velocity-budget floor OFF (enabled only for very low low-glucose exposure)"

        return V5Suggestion(
            aggression = aggression, hypoCaution = hypoCaution,
            confirmedCapU = confirmedCapU, committedCapU = committedCapU,
            cumulativeSmbCap60MinU = cumulativeSmbCap60MinU,
            maxIobU = maxIobU, bolusCapU = bolusCapU,
            fastCarbConfirm = fastCarbConfirm,
            aggressiveEarlyConfirm = aggressiveEarlyConfirm,
            velocityBudgetFloor = velocityBudgetFloor,
            rationale = reasons
        )
    }

    /**
     * Rolling-60-min cumulative SMB cap: bounds dose *frequency* (the per-shot caps only bound
     * magnitude). Budget = one confirm shot plus two holds per hour, clamped only to the
     * preference's expressible range [1.0, 10.0].
     *
     * History: the previous ceiling was `max(5.0, confirmedCap)`, which collapsed
     * "one confirm + 2 holds" to "confirm + ~0 holds" for any big-confirm user (the 2026-07-06
     * 7-user migration backtest attributed 6 of one user's 8 projected suppressions to exactly
     * this, and left another user's cumulative == confirmedCap so a single confirm exhausted the
     * hour). The clamp is now the pref range max: the formula is the policy, the clamp is only a
     * bound.
     *
     * Exposed separately from [compute] because the apply layer must recompute it from the FINAL
     * operative per-shot caps (kept-user-tuned or derived), not from the derivation's own caps —
     * a cumulative budget sized from a derived confirmedCap that never applies is incoherent
     * (cohort user E: cumulative sized from derived 4.65 while his operative cap was 2.0).
     */
    fun cumulativeCap60Min(confirmedCapU: Double, committedCapU: Double): Double =
        round1((confirmedCapU + 2.0 * committedCapU).coerceIn(1.0, CUMULATIVE_CAP_MAX_U))

    // ── helpers ──────────────────────────────────────────────────────────────────────────────
    /** Linear-interpolated percentile (0..100) of a value list; 0.0 if empty. */
    fun percentile(values: List<Double>, p: Double): Double {
        val v = values.filter { it.isFinite() && it > 0.0 }.sorted()
        if (v.isEmpty()) return 0.0
        if (v.size == 1) return v[0]
        val rank = (p / 100.0) * (v.size - 1)
        val lo = rank.toInt()
        val hi = min(lo + 1, v.size - 1)
        val frac = rank - lo
        return v[lo] + (v[hi] - v[lo]) * frac
    }

    private fun round1(x: Double) = Math.round(x * 10.0) / 10.0
    private fun round2(x: Double) = Math.round(x * 100.0) / 100.0
    private fun pct(x: Double) = "${Math.round(x * 10.0) / 10.0}%"
}
