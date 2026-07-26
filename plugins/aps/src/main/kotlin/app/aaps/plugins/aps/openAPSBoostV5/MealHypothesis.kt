package app.aaps.plugins.aps.openAPSBoostV5

import kotlin.math.max

/**
 * V5 Phase 1.b — MealHypothesis state machine.
 *
 * Persisted across cycles via RT fields (`mealHypothesis: String?`, `mealHypothesisAge: Int?`,
 * and from 2026-05-15 `maxScoreInObserving: Double?`). V4 had no equivalent — meal recognition
 * was implicit in tier-ladder selection. V5 makes the hypothesis a first-class state the
 * algorithm reasons about, then commits doses against.
 *
 * Five states: IDLE → OBSERVING → CONFIRMED → COMMITTED → RECOVERING → IDLE.
 *
 * Transition thresholds are HARDCODED and calibrated against shadow data
 * (`boost_v5_constants_calibration.md` and the 2026-05-15 V5-fixes review). They are NOT
 * user-facing knobs.
 *
 * State persistence is non-trivial (state from prior cycles influences this cycle's decision),
 * so all reset paths are explicit: see [resetIfNeeded].
 *
 * ## 2026-05-15 fixes applied
 *
 * Shadow data review on 2026-05-15 (`boost_2026-05-14_evening_excursion.md`) showed CONFIRMED
 * fired only 4 times across 8 days because the OBSERVING → CONFIRMED predicate required ALL
 * three conditions to hold ON THE SAME CYCLE — but score is volatile cycle-to-cycle and peaked
 * 1–2 cycles before the age gate (CONFIRM_MIN_OBSERVING_AGE=2) opened. By the time age=2 the
 * score had already retreated.
 *
 * Fix: track the max score observed during the current OBSERVING run and use it for the
 * eligibility check, not the instantaneous score. This preserves the age hysteresis (which
 * matters for noise rejection) while allowing brief score peaks to drive the transition.
 *
 * CONFIRM_SCORE also lowered from 0.66 → 0.55 per the recalibration plan (the original
 * calibration was against an idealised cohort; p95 of observed scores in production is 0.532).
 *
 * ## 2026-05-22 Fix 5 — eventualBG peak-tracking
 *
 * 7d validation backtest against the 2026-05-15 evening meal showed Fix 4 (sustainedRise score
 * component) alone wasn't enough: V5's score peak rose from 0.600 to 0.689 with Fix 4, well
 * above the 0.55 threshold, but CONFIRMED still didn't fire. The third predicate condition —
 * `eventualBg > targetBg + 50` — was checked snapshot-only on each cycle, and during the slow
 * meal window the eventualBG forecast peaked at +42 above target (just below the +50 gate)
 * while the high-score window kept retreating elsewhere.
 *
 * Same shape as the score wobble Fix 1 addressed: a value that crosses the bar briefly during
 * OBSERVING but isn't sitting above the bar on the exact cycle the predicate is evaluated.
 *
 * Fix: peak-track `(eventualBg - targetBg)` across the OBSERVING run and check the max against
 * the threshold, mirroring Fix 1's max-score logic. With peak-tracking, the threshold is also
 * lowered 50 → 30 because peak-over-window is naturally higher than snapshot — the original
 * calibration was for snapshot reads.
 *
 * ## 2026-05-26 Fix 6 — single-CONFIRMED-per-session guard
 *
 * Diagnosed from the 2026-05-25 evening meal trace: V5 fired CONFIRMED 4 times in 20 min during
 * a single meal climb, producing 8U of cumulative shadow dose (vs V4.4.2's actual 1.5U, which
 * was already enough to crash BG from 192 → 48 over 1h 40m). Root cause: AAPS re-invokes the
 * V4.4.2 plugin (and therefore V5's runShadow) every 1-3 min during SMB delivery, not every 5
 * min as the state machine assumes. Combined with the SharedPreferences async-flush race
 * (addressed by V5StateStore's in-memory cache, Fix 6 Part A), the state machine could re-enter
 * OBSERVING after CONFIRMING and re-CONFIRM in the same meal.
 *
 * Fix: persist a `committedInSession` flag through CONFIRMED / COMMITTED / RECOVERING. The
 * OBSERVING → CONFIRMED transition predicate now requires `!committedInSession`. Reset to false
 * only on the RECOVERING → IDLE exit (session complete) or fresh OBSERVING entry from IDLE.
 *
 * Defense in depth: even if the state-persistence race resurfaces, the cached state's
 * committedInSession flag blocks a second commit-shot for the same meal.
 */

enum class MealHypothesis { IDLE, OBSERVING, CONFIRMED, COMMITTED, RECOVERING }

/**
 * Persisted state. The plugin reads this from RT each cycle and writes it back after [step].
 *
 * @property maxScoreInObserving peak meal_signal_score observed during the current OBSERVING run.
 *   Reset to 0.0 whenever state transitions OUT of OBSERVING. Allows CONFIRMED to fire on
 *   accumulated evidence rather than instantaneous score — added 2026-05-15 to fix the
 *   transient-peak-misses-age-gate issue described in the class docstring.
 * @property maxEventualBgOffsetInObserving peak `(eventualBg - targetBg)` observed during the
 *   current OBSERVING run, mg/dL. Reset to 0.0 on state transitions out of OBSERVING. Fix 5
 *   (2026-05-22) — same shape as maxScoreInObserving, applied to the eventualBG offset that the
 *   CONFIRMED predicate also requires.
 * @property committedInSession true once V5 has CONFIRMED in the current meal session. Reset to
 *   false on entry to OBSERVING from IDLE (fresh session) and on entry to IDLE from RECOVERING
 *   (session complete). Blocks OBSERVING → CONFIRMED re-firing within the same session — Fix 6
 *   (2026-05-26), defense-in-depth alongside the V5StateStore in-memory cache. Even if state
 *   appeared to reset mid-meal due to a persistence race, this flag in the cached state prevents
 *   a second commit-shot in the same meal.
 */
data class MealHypothesisState(
    val state: MealHypothesis = MealHypothesis.IDLE,
    val ageCycles: Int = 0,
    val maxScoreInObserving: Double = 0.0,
    val maxEventualBgOffsetInObserving: Double = 0.0,
    val committedInSession: Boolean = false,
)

// Calibrated transition thresholds (HARDCODED).
// Per boost_v5_constants_calibration.md, with 2026-05-15 revisions noted inline.
internal const val ENTER_OBSERVING_SCORE = 0.44                 // calibrated: 0.40 → 0.44
internal const val CONFIRM_SCORE = 0.55                         // 2026-05-15: 0.66 → 0.55 (was at p99 of observed scores; lowered with peak-score tracking)
internal const val CONFIRM_EVENTUAL_BG_OFFSET_MGDL = 30.0       // 2026-05-22: 50.0 → 30.0 (Fix 5 — paired with peak-offset tracking)
internal const val CONFIRM_MIN_OBSERVING_AGE = 2                // hysteresis: age enters OBSERVING at 0 and increments post-check, so confirm is first possible on the 4th OBSERVING cycle (age ≥ 2 checked on the 3rd increment)

/**
 * 2026-07-03 sustained-score early confirm: OBSERVING → CONFIRMED may fire before
 * [CONFIRM_MIN_OBSERVING_AGE] when the INSTANTANEOUS score has been ≥ [CONFIRM_SCORE] on BOTH
 * this cycle and the immediately preceding one (`scoreReadyStreak` — supplied by the caller,
 * same cross-cycle-input pattern as `deltaDeclining`). All other confirm conditions (peak
 * eventualBG offset ≥ 30, confirmDoseAdequate, !committedInSession) are unchanged.
 *
 * WHY: replay vs the cohort DB (2026-07-03) showed 53% of confirm latency was purely
 * mechanical — the score was already ≥ CONFIRM_SCORE for ≥2 cycles before the age gate
 * opened. Shifting the SAME commit-shot 1 cycle earlier measured 0.0pp additional pre-low
 * exposure, vs +14–17% for added-insulin levers evaluated in the same sweep. The early path
 * requires the CURRENT score ≥ threshold (not just the tracked max) because the whole point
 * is a sustained-ready score, not a transient peak.
 *
 * This is the DEFAULT early path (the early-dosing audit priced the `- 1` step at 0.0pp harm).
 */
internal const val CONFIRM_MIN_OBSERVING_AGE_SCORE_READY = CONFIRM_MIN_OBSERVING_AGE - 1

/**
 * 2026-07-17 (user H "confirm sooner") — AGGRESSIVE early confirm, one cycle earlier again
 * (`- 2` = 0), so a meal whose score is confirm-strength on two consecutive cycles confirms as
 * soon as it enters OBSERVING. Still MOVES the same commit-shot (no added insulin) with the
 * scoreReadyStreak protection, BUT the pre-push backtest showed ~28% of its candidates are
 * fizzle-catches (episodes that would have fallen back to IDLE) = new insulin at ~base rate — so
 * it is NOT a clean cohort default. It is therefore OPT-IN and AUTO-CONFIG MANAGED
 * (BooleanKey.ApsBoostV5AggressiveEarlyConfirm, enabled by BoostV5AutoConfig ONLY for clearly
 * well-controlled users — the same class the fastCarbConfirm derivation gates). Threaded via the
 * `aggressiveEarlyConfirm` flag; false (default) keeps the audit-validated `- 1` timing.
 * See backtesting/scripts/2026-07-userh-levers/.
 */
internal const val CONFIRM_MIN_OBSERVING_AGE_SCORE_READY_AGGRESSIVE = CONFIRM_MIN_OBSERVING_AGE - 2
// 2026-07-02 dose-adequacy gate: the confirm floor is committedCapU, clamped to at most this fraction
// of confirmedCapU so a manual committedCap ≥ confirmedCap can't make the gate unsatisfiable (which
// would silently disable V6's meal response). See DetermineBasalBoostV5.decide().
internal const val CONFIRM_DOSE_FLOOR_MAX_FRAC_OF_CONFIRMED_CAP = 0.8

/**
 * 2026-07-06 confirm-floor pin: the committedCapU term of the confirm dose floor is pinned at
 * the FACTORY default COMMITTED cap (0.5 U — `DoubleKey.ApsBoostV5CommittedCapU` default),
 * regardless of the live preference value.
 *
 * The floor's job is "the commit-shot must beat one ROUTINE hold". A user-RAISED committedCap
 * describes a bigger PERMITTED hold, not a bigger routine one — so it must not move the floor.
 * Without the pin, raising committedCap silently TIGHTENS the confirm gate: the 2026-07-06
 * backtest on live telemetry showed a 0.5 → 1.0 cap raise would newly block ~18% of confirms
 * (prospective shots ≤ 1.0 U) — exactly the mid-meal starvation the gate exists to prevent.
 * A user-LOWERED committedCap still lowers the floor (min semantics preserved — see
 * [confirmDoseFloorU]).
 */
internal const val CONFIRM_FLOOR_COMMITTED_TERM_MAX = 0.5

/**
 * The OBSERVING→CONFIRMED dose-adequacy floor (U):
 * `min(min(committedCapU, CONFIRM_FLOOR_COMMITTED_TERM_MAX), 0.8 × confirmedCapU)`.
 *
 * The committedCap term is pinned at the factory default ([CONFIRM_FLOOR_COMMITTED_TERM_MAX])
 * so raising the COMMITTED cap can't tighten the confirm gate (2026-07-06 — see the pin KDoc);
 * lowering it below the pin still lowers the floor. The confirmedCap clamp
 * ([CONFIRM_DOSE_FLOOR_MAX_FRAC_OF_CONFIRMED_CAP], 2026-07-02) keeps the gate satisfiable.
 */
internal fun confirmDoseFloorU(committedCapU: Double, confirmedCapU: Double): Double =
    minOf(
        minOf(committedCapU, CONFIRM_FLOOR_COMMITTED_TERM_MAX),
        CONFIRM_DOSE_FLOOR_MAX_FRAC_OF_CONFIRMED_CAP * confirmedCapU,
    )
internal const val FALL_BACK_TO_IDLE_SCORE = 0.36               // calibrated: 0.30 → 0.36
internal const val FALL_BACK_TO_IDLE_AGE = 2                    // hysteresis: falls back when TOTAL OBSERVING age ≥ 2 AND the CURRENT cycle is below threshold (not "2 consecutive below" — one sub-threshold blip after age 2 exits)
internal const val CONFIRMED_TO_COMMITTED_AGE = 0               // 2026-05-26 Fix 6: 1 → 0 (true single-cycle commit; previously CONFIRMED stayed for 2 invokes due to age semantics, allowing 2× CONFIRMED-mult doses)
internal const val RECOVERING_DECEL_THRESHOLD = -5.0            // delta_accl < -5 enters RECOVERING (with delta declining)
internal const val RECOVERING_TO_IDLE_SCORE = 0.18              // calibrated: 0.20 → 0.18

// 2026-06-12 Fix 7 — multi-phase meal re-engagement. On a two-phase meal (rise → decel → rise),
// the mid-meal deceleration sends COMMITTED → RECOVERING, and RECOVERING previously had no path
// back to active dosing — V5 dribbled at 0.4× through the entire second climb (BG ran to 192 on
// 2026-06-12). These thresholds let RECOVERING resume COMMITTED (1.0×, NOT a new 1.8× CONFIRMED
// commit — Fix 6 stays intact) when the meal genuinely re-accelerates while still well above target.
// The −5 back-off vs +10 re-engage dead-band + min-age give hysteresis against flicker.
// Initial estimates; revisit after a few two-phase meals.
internal const val RECOVERING_REENGAGE_ACCL = 10.0             // delta_accl must exceed this to re-engage
internal const val RECOVERING_REENGAGE_DELTA = 3.0            // BG must actually be rising (mg/dL per 5 min)
internal const val RECOVERING_REENGAGE_OFFSET_MGDL = 20.0    // eventualBg − targetBg must exceed this (meal still material)
internal const val RECOVERING_REENGAGE_MIN_AGE = 1          // ≥1 cycle in RECOVERING before re-engaging (no same-cycle flicker)

// 2026-06-16 — fast-carb fast-path. The observe→confirm latency commits ~1 cycle late on fast
// carbs (the 2026-06-16 meal: peak 185 then crash 54). When the rise is sharp AND accelerating
// AND the meal score corroborates AND we're awake & not exercising, promote OBSERVING/IDLE →
// CONFIRMED in a SINGLE cycle, bypassing CONFIRM_MIN_OBSERVING_AGE + the eventualBg-offset gate.
// Thresholds replay-validated (backtesting/replay.py, 2026-06-16): the corroborated rule caught
// ~⅓ of meals ~15 min earlier with ZERO sleep-fires and ~1 false fire/day; the raw delta+accl
// rule (no score/awake gate) fired during sleep (compression risk) and ~2×/day falsely.
// Still respects the Fix-6 single-CONFIRMED-per-session guard (committedInSession).
//
// 2026-07-03 retune (replay sweep over the cohort): Δ 8→6, accl 15→10, score 0.60→0.65. This
// point catches +21 meals ~9 min earlier while REDUCING false fires 39%→32% — the score raise
// pays for the physics relaxation. A plain physics relaxation WITHOUT the score raise is worse
// (40% false); the tighter score gate is what makes the looser Δ/accl thresholds safe. All
// guards (awake, not exercising, recentLowBg ≥ 80, !committedInSession, pref toggle) unchanged.
internal const val FAST_CONFIRM_DELTA = 6.0                    // mg/dL per 5 min — sharp rise (2026-07-03: 8.0 → 6.0)
internal const val FAST_CONFIRM_ACCL = 10.0                    // delta_accl % — accelerating (2026-07-03: 15.0 → 10.0)
internal const val FAST_CONFIRM_SCORE = 0.65                   // meal score must corroborate (2026-07-03: 0.60 → 0.65; > ENTER_OBSERVING 0.44)
// 2026-07-02 post-hypo rescue-carb guard: the fast path is suppressed when the 60-min BG low is
// below this. A rescue-carb rebound routinely satisfies the fast-path Δ/accl/score thresholds, and the
// fast path is EXEMPT from the confirmDoseAdequate gate — so it was the only unguarded CONFIRMED
// entry within an hour of a hypo. Replay over 613 real fast-path firings (7 users, May–Jul):
// threshold 80 blocks 36% of firings, 47 of which preceded a SECOND low <70 within 2h; the rest
// are rebound-shaped meals whose confirm arrives ~2 cycles later via the normal path (V1 base
// dosing continues meanwhile). 100 over-blocked (63%, normal pre-meal dips); 80→90 marginal trade
// is poor (8 more catches for 80 more blocks). See v6-safety-review-2026-07-02.
internal const val FAST_CONFIRM_MIN_RECENT_LOW_MGDL = 80.0

/**
 * Effective fast-carb fast-path enable for this cycle: the user toggle AND the post-hypo
 * rescue-carb guard ([FAST_CONFIRM_MIN_RECENT_LOW_MGDL]). Computed by the caller (decide())
 * and passed to [step] as `fastConfirmEnabled` — same pattern as `confirmDoseAdequate`.
 */
fun fastConfirmAllowed(fastCarbConfirmEnabled: Boolean, recentLowBg: Double): Boolean =
    fastCarbConfirmEnabled && recentLowBg >= FAST_CONFIRM_MIN_RECENT_LOW_MGDL

/** Time-jump threshold (minutes) for forcing IDLE on clock changes (e.g. timezone switch). */
internal const val TIME_JUMP_RESET_MINUTES = 30.0

/**
 * OBSERVING → CONFIRMED eligibility EXCLUDING the dose-adequacy gate — the exact sub-conditions
 * [step]'s OBSERVING branch checks (age gate incl. the 2026-07-03 sustained-score early path,
 * peak score, peak eventualBG offset, single-confirm-per-session lock), minus confirmDoseAdequate.
 *
 * Exposed for gate telemetry (`boostV5_confirmGate`, 2026-07-03): decide() labels each cycle
 * "pass" / "blocked" / "n/a" so a dose-adequacy gate block is distinguishable from a score fade
 * in NS — needed for the 2026-07-10 live gate review. [step] calls this SAME function for its
 * dosing decision, so the telemetry and dosing predicates can never diverge.
 */
fun confirmEligibleExceptDoseGate(
    current: MealHypothesisState,
    score: Double,
    eventualBg: Double,
    targetBg: Double,
    scoreReadyStreak: Boolean = false,
    // 2026-07-17: when true, the sustained-score early path opens ONE cycle earlier again (age −2
    // instead of −1). Opt-in + auto-config managed — see CONFIRM_MIN_OBSERVING_AGE_SCORE_READY_AGGRESSIVE.
    aggressiveEarlyConfirm: Boolean = false,
): Boolean {
    if (current.state != MealHypothesis.OBSERVING || current.committedInSession) return false
    val newMaxScore = max(current.maxScoreInObserving, score)
    val newMaxOffset = max(current.maxEventualBgOffsetInObserving, eventualBg - targetBg)
    val age = current.ageCycles
    // 2026-07-03: age gate opens one cycle early when the score has been ≥ CONFIRM_SCORE on BOTH
    // this cycle and the previous one (see CONFIRM_MIN_OBSERVING_AGE_SCORE_READY). The early path
    // checks the CURRENT score, not the tracked max — a sustained-ready score, not a transient
    // peak, is what justifies shaving the hysteresis. 2026-07-17: the aggressive opt-in shaves one
    // more cycle (age −2).
    val scoreReadyFloor = if (aggressiveEarlyConfirm) CONFIRM_MIN_OBSERVING_AGE_SCORE_READY_AGGRESSIVE
    else CONFIRM_MIN_OBSERVING_AGE_SCORE_READY
    val ageEligible = age >= CONFIRM_MIN_OBSERVING_AGE ||
        (age >= scoreReadyFloor && score >= CONFIRM_SCORE && scoreReadyStreak)
    return ageEligible && newMaxScore >= CONFIRM_SCORE && newMaxOffset >= CONFIRM_EVENTUAL_BG_OFFSET_MGDL
}

/**
 * Single-step transition. Pure function; no side effects. Caller threads state across cycles.
 *
 * @param current state from the previous cycle.
 * @param score `meal_signal_score` from this cycle's Phase 1.a.
 * @param eventualBg oref's eventualBG projection, mg/dL.
 * @param targetBg current target BG, mg/dL.
 * @param delta this cycle's BG delta, mg/dL/5min.
 * @param deltaAccl this cycle's delta_accl, percent.
 * @param deltaDeclining whether delta has been monotonically declining over the last ≥2 cycles
 *   (computed by the caller from delta history). COMMITTED → RECOVERING requires both
 *   `delta_accl < -5` AND this declining-2-cycles condition.
 */
fun step(
    current: MealHypothesisState,
    score: Double,
    eventualBg: Double,
    targetBg: Double,
    delta: Double,
    deltaAccl: Double,
    deltaDeclining: Boolean,
    asleep: Boolean = false,
    exerciseActive: Boolean = false,
    fastConfirmEnabled: Boolean = false,
    // 2026-07-02: OBSERVING→CONFIRMED dose-adequacy gate. Caller sets it true when the prospective
    // commit-shot (budget × CONFIRMED mult) exceeds one routine COMMITTED hold (committedCapU, clamped
    // < confirmedCapU). Defaults true so the fast-carb path and existing callers/tests are unaffected.
    confirmDoseAdequate: Boolean = true,
    // 2026-07-03: sustained-score early confirm. True when the PREVIOUS cycle's score was already
    // ≥ CONFIRM_SCORE — computed by the caller from last cycle's score (cross-cycle input, same
    // pattern as deltaDeclining). With the CURRENT score also ≥ CONFIRM_SCORE, the age gate opens
    // one cycle early (CONFIRM_MIN_OBSERVING_AGE_SCORE_READY). Defaults false = legacy timing for
    // all existing callers/tests.
    scoreReadyStreak: Boolean = false,
    // 2026-07-17: aggressive early-confirm opt-in (auto-config managed). Shaves the score-ready path
    // one more cycle (age −2). Defaults false = the audit-validated −1 timing for existing callers/tests.
    aggressiveEarlyConfirm: Boolean = false,
): MealHypothesisState {
    val state = current.state
    val age = current.ageCycles
    val maxScore = current.maxScoreInObserving
    val maxOffset = current.maxEventualBgOffsetInObserving
    val committedInSession = current.committedInSession
    val currentOffset = eventualBg - targetBg

    // 2026-06-16 fast-carb fast-path (corroborated; replay-validated). Single-cycle promotion to
    // CONFIRMED on a sharp, accelerating, score-corroborated rise while awake and not exercising.
    val fastConfirm = fastConfirmEnabled && !asleep && !exerciseActive &&
        delta >= FAST_CONFIRM_DELTA && deltaAccl >= FAST_CONFIRM_ACCL && score >= FAST_CONFIRM_SCORE

    return when (state) {
        MealHypothesis.IDLE ->
            if (fastConfirm)
                // Fast carb caught from IDLE — go straight to CONFIRMED (committedInSession=true).
                MealHypothesisState(MealHypothesis.CONFIRMED, 0, 0.0, 0.0, true)
            else if (score >= ENTER_OBSERVING_SCORE)
                // Fresh session: seed both peaks with entry-cycle values; committedInSession=false
                // explicitly (new meal session begins here — Fix 6).
                MealHypothesisState(MealHypothesis.OBSERVING, 0, score, currentOffset, false)
            else MealHypothesisState(state, age + 1, 0.0, 0.0, false)

        MealHypothesis.OBSERVING -> {
            // 2026-05-15 Fix 1: track running max-score in this OBSERVING run, use it for the
            // CONFIRMED eligibility check (not the instantaneous score). Score is volatile;
            // peaks 1–2 cycles before the age gate opens. Tracking the max lets a brief
            // high-score cycle drive the transition once age conditions are met.
            //
            // 2026-05-22 Fix 5: same treatment for (eventualBg - targetBg). The eventualBG
            // forecast also moves cycle-to-cycle and can be high during the meal-rise window
            // but retreat by the time score + age conditions align. Peak-track it too.
            //
            // 2026-05-26 Fix 6: single-CONFIRMED-per-session guard. If this OBSERVING run is a
            // re-entry within the same meal session (committedInSession=true — meaning V5 already
            // CONFIRMED in this meal but state appeared to reset mid-stream), block re-CONFIRMING.
            // The 5/25 evening meal showed V5 CONFIRMED 4 times in 20 min producing 8U total
            // shadow dose; this guard caps it to a single commit-shot per meal session.
            val newMaxScore = max(maxScore, score)
            val newMaxOffset = max(maxOffset, currentOffset)
            // Eligibility sub-conditions (age gate incl. the 2026-07-03 sustained-score early path,
            // peak score, peak offset, session lock) live in confirmEligibleExceptDoseGate — shared
            // with decide()'s boostV5_confirmGate telemetry so the two can never diverge (2026-07-03).
            val confirmEligible = confirmEligibleExceptDoseGate(current, score, eventualBg, targetBg, scoreReadyStreak, aggressiveEarlyConfirm) &&
                confirmDoseAdequate   // 2026-07-02: don't spend the token on a shot < one COMMITTED hold
            when {
                // Fast-carb fast-path: confirm in a single OBSERVING cycle, bypassing the age +
                // eventualBg-offset gates, but still honouring the Fix-6 single-confirm guard.
                fastConfirm && !committedInSession -> MealHypothesisState(MealHypothesis.CONFIRMED, 0, 0.0, 0.0, true)
                confirmEligible -> MealHypothesisState(MealHypothesis.CONFIRMED, 0, 0.0, 0.0, true)
                score < FALL_BACK_TO_IDLE_SCORE && age >= FALL_BACK_TO_IDLE_AGE ->
                    MealHypothesisState(MealHypothesis.IDLE, 0, 0.0, 0.0, false)
                else -> MealHypothesisState(state, age + 1, newMaxScore, newMaxOffset, committedInSession)
            }
        }

        MealHypothesis.CONFIRMED ->
            if (age >= CONFIRMED_TO_COMMITTED_AGE)
                // Preserve committedInSession through CONFIRMED → COMMITTED so the session lock
                // survives in case a downstream invoke loops back through OBSERVING.
                MealHypothesisState(MealHypothesis.COMMITTED, 0, 0.0, 0.0, true)
            else MealHypothesisState(state, age + 1, 0.0, 0.0, true)

        MealHypothesis.COMMITTED -> {
            // BOTH conditions required to back off — prevents flicker on transient deceleration
            // mid-rise (e.g. CGM noise). V4's tier ladder had this flicker problem.
            val backOff = deltaAccl < RECOVERING_DECEL_THRESHOLD && deltaDeclining
            if (backOff) MealHypothesisState(MealHypothesis.RECOVERING, 0, 0.0, 0.0, true)
            else MealHypothesisState(state, age + 1, 0.0, 0.0, true)
        }

        MealHypothesis.RECOVERING -> {
            // Fix 7 (2026-06-12): multi-phase meal re-engagement. If the meal re-accelerates while
            // still well above target, resume COMMITTED (1.0× sustained dosing) rather than dribble
            // at 0.4× through a second rise. Resumes COMMITTED — NOT a second CONFIRMED commit-shot —
            // so committedInSession stays true and the Fix 6 multi-CONFIRMED guard is untouched.
            val reEngage = age >= RECOVERING_REENGAGE_MIN_AGE &&
                deltaAccl > RECOVERING_REENGAGE_ACCL &&
                delta > RECOVERING_REENGAGE_DELTA &&
                currentOffset > RECOVERING_REENGAGE_OFFSET_MGDL
            when {
                reEngage -> MealHypothesisState(MealHypothesis.COMMITTED, 0, 0.0, 0.0, true)
                // EITHER condition exits to IDLE (more permissive than entry — easier to leave RECOVERING).
                // On exit to IDLE the session is complete — reset committedInSession=false so the next
                // meal can CONFIRM normally.
                delta < 0 || score < RECOVERING_TO_IDLE_SCORE ->
                    MealHypothesisState(MealHypothesis.IDLE, 0, 0.0, 0.0, false)
                else -> MealHypothesisState(state, age + 1, 0.0, 0.0, true)
            }
        }
    }
}

/**
 * Force IDLE on conditions where prior state shouldn't carry over. All five paths are explicit
 * because silently inheriting a stale meal hypothesis could cause unsafe dosing on resume.
 *
 * Returns Pair(newState, didReset).
 *
 * @param current the (possibly-stale) state from RT or last cycle.
 * @param profileSwitched true if active profile changed since last cycle.
 * @param pumpDisconnected true if pump is currently disconnected.
 * @param loopSuspended true if user has suspended the loop.
 * @param timeJumpMinutes absolute minutes between expected and actual cycle time
 *   (e.g. 60 if device clock jumped due to timezone change).
 */
fun resetIfNeeded(
    current: MealHypothesisState,
    profileSwitched: Boolean = false,
    pumpDisconnected: Boolean = false,
    loopSuspended: Boolean = false,
    timeJumpMinutes: Double = 0.0,
): Pair<MealHypothesisState, Boolean> {
    if (profileSwitched || pumpDisconnected || loopSuspended || timeJumpMinutes > TIME_JUMP_RESET_MINUTES) {
        return Pair(MealHypothesisState(MealHypothesis.IDLE, 0, 0.0, 0.0, false), true)
    }
    return Pair(current, false)
}

/**
 * Helper: compute whether delta has been declining over the last `windowCycles` cycles.
 * Used as input to [step] for the COMMITTED → RECOVERING transition.
 *
 * @param deltaHistory ordered oldest → newest delta values, including the current cycle.
 *   For "declining over last 2 cycles" pass at least 3 deltas.
 */
fun deltaDeclining(deltaHistory: List<Double>, windowCycles: Int = 2): Boolean {
    if (deltaHistory.size < windowCycles + 1) return false
    val tail = deltaHistory.takeLast(windowCycles + 1)
    for (i in 0 until tail.size - 1) {
        if (tail[i] <= tail[i + 1]) return false
    }
    return true
}
