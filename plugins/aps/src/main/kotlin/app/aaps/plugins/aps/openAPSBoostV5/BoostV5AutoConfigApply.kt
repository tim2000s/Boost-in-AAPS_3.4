package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.core.keys.DoubleKey
import kotlin.math.abs

/**
 * Pure helpers for applying a [BoostV5AutoConfig.V5Suggestion] to preferences while respecting any
 * value the user — or a preset (e.g. a pre-seeded keystore/import) — has ALREADY set.
 *
 * Separated from [OpenAPSBoostV5Plugin]'s preference I/O so the invariants that matter are
 * unit-testable: presetting ONE V6 knob must NOT block the others — the preset value is kept and
 * every other unset knob is still configured.
 *
 * ── Per-key resolution (2026-07 fix, field evidence: user H) ──────────────────────────────────
 * The original design used one global "did run" flag plus a raw `sp.contains(key)` presence test.
 * Two field failure modes:
 *  1. Presence false-positives: anything that persists a knob AT its factory default (settings
 *     import, opening the pref dialog and tapping OK) made auto-config skip it forever — the user
 *     never objected, yet kept the stock value (user H: committedCap stuck at factory 0.5 while his
 *     derived value was 1.24).
 *  2. Global one-shot: once the flag was consumed (older build, or carried in via a settings
 *     import), settings ADDED to auto-config later were never derived for existing installs.
 * The fix: each managed knob is tracked individually as RESOLVED once it has either been applied
 * once or been skipped because the user tuned it (stored value differs from the factory default).
 * Insufficient data resolves nothing, so unresolved knobs genuinely retry on later cycles.
 * "User tuned it" now means *value differs from every factory default the key has ever shipped
 * with* — mere presence in storage no longer blocks a suggestion (value == a factory default means
 * nobody objected).
 *
 * ── 2026-07-06 amendments (7-user migration-cohort backtest) ─────────────────────────────────
 *  - Historical factory defaults: the at-factory test must recognise the defaults of EVERY build
 *    era, or a user whose prefs persisted an OLD factory value reads as "user-tuned" and is frozen
 *    at the tightest-ever values (cohort users C/D: committedCap 0.25 / confirmedCap 1.0 /
 *    cumulative 6.0 eras). See [historicalFactoryDefaults].
 *  - The cumulative 60-min cap is recomputed here from the FINAL operative per-shot caps
 *    (kept-or-derived), not taken verbatim from the derivation (cohort user E incoherence).
 *  - TBR raise-guard: a dose-cap RAISE is priced badly for a TBR-heavy user, and value==factory
 *    cannot distinguish "never touched" from "deliberately reverted to factory". See
 *    [TBR_RAISE_GUARD_PCT].
 *  - Every knob's classification is returned as a [Resolution] with a human-readable reason, so
 *    field diagnosis never needs inference again.
 */
internal object BoostV5AutoConfigApply {

    /**
     * Tolerance for "still at factory default": preference values can round-trip through Float
     * (AdaptiveDoublePreference persists floats), so exact Double equality would be fragile.
     */
    private const val DEFAULT_EPS = 1e-4

    /**
     * Max acceptable 14-day time-below-70 (%) for auto-APPLYING a dose-cap RAISE. At or below this,
     * raises apply as normal; above it they are only *suggested* (surfaced in the notification and
     * the log) and the knob resolves without being written.
     *
     * Backtest evidence (7-user migration cohort, 2026-07-06 — cohort user B, TBR<70 4.26%): the
     * insulin his raised caps would have added priced at 44.7% delivered within 3 h of a <70 mg/dL
     * reading, vs 32.8% for his baseline dosing — a raise is exactly the wrong medicine for a
     * TBR-heavy user. LOWERINGS and non-cap tightenings (HypoCaution, Aggression ≤ 1.0,
     * FastCarbConfirm OFF, the cumulative cap when it tightens) always apply. 4.0% is the
     * international consensus TBR<70 target the derivation already uses.
     */
    const val TBR_RAISE_GUARD_PCT = 4.0

    /**
     * Severe-hypo co-guard on the same raise-guard (2026-07-07): a dose-cap RAISE is also held
     * (suggested-not-applied) when 14-day time-below-54 is at or above this. 1.0% is the
     * international consensus <54 target the derivation already uses (SEV54_TARGET). Catches the
     * user-B pattern the <70-only guard missed: TBR<70 3.83% (under the 4.0% line) but <54 1.01%
     * (over the severe line) — severe exposure is the stronger contraindication for a raise, and a
     * user can sit under the <70 gate while over the <54 one. Same suggested-not-applied
     * notification path as [TBR_RAISE_GUARD_PCT]; lowerings and non-cap tightenings still always
     * apply.
     */
    const val TBR54_RAISE_GUARD_PCT = 1.0

    /**
     * Every factory default each managed key has EVER shipped with, beyond the current one.
     * Verified from git history across all branches (2026-07-06, `git log --all -p -G<key>` on
     * core/keys/DoubleKey.kt; the keys never lived anywhere else):
     *  - boost_v5_confirmed_cap_u: 1.0 (introduced bcda0a68d4) → 2.5 (ae1f263a24, 2026-06-26)
     *  - boost_v5_committed_cap_u: 0.25 (introduced bcda0a68d4) → 0.5 (ae1f263a24, 2026-06-26)
     *  - boost_cumulative_smb_cap_60min: 1.5 (introduced 780f5769) → 6.0 (1114e387a9,
     *    Boost-ML-Beta-2 era, 2026-06-16) → 10.0 (20d7b8b54c, 2026-06-29)
     * The other managed keys (Aggression 1.0, HypoCaution 1.0, MaxIob 1.0, Bolus 2.5) have never
     * changed default. A stored value matching ANY of these (±[DEFAULT_EPS]) is at-factory, i.e.
     * derivable — without this, a user whose old build persisted an old factory value reads as
     * "user-tuned" and is frozen at the tightest-ever values (cohort users C/D).
     */
    private val historicalFactoryDefaults: Map<String, List<Double>> = mapOf(
        DoubleKey.ApsBoostV5ConfirmedCapU.key to listOf(1.0),
        DoubleKey.ApsBoostV5CommittedCapU.key to listOf(0.25),
        DoubleKey.ApsBoostCumulativeSmbCap60Min.key to listOf(1.5, 6.0)
    )

    /** Current + historical factory defaults for [key] (current first). */
    fun factoryDefaults(key: DoubleKey): List<Double> =
        listOf(key.defaultValue) + (historicalFactoryDefaults[key.key] ?: emptyList())

    /**
     * The dose-cap knobs subject to the [TBR_RAISE_GUARD_PCT] raise-guard. MaxIob/Bolus are NOT
     * here: they mirror the user's own existing AAPS constraints, so "raising" them only matches a
     * limit the user already runs elsewhere.
     */
    val doseCapKeys: Set<DoubleKey> = setOf(
        DoubleKey.ApsBoostV5ConfirmedCapU,
        DoubleKey.ApsBoostV5CommittedCapU,
        DoubleKey.ApsBoostCumulativeSmbCap60Min
        // ApsBoostV5PrimerCapU is deliberately NOT here. It was briefly added on 2026-07-30 and then
        // removed the same day: raise-guarding it meant a hypo-prone user at the 0.0 factory default had
        // the cap withheld AND marked resolved, so the primer was never provisioned for them at all —
        // including the retractable temp-basal route that is precisely their SAFE path. Auto-config
        // RECOMMENDS the temp-basal routing for these users (ApsBoostV5PrimerTbrFallback) and the
        // recommendation is recorded, but the user override always wins: auto-config may set a default,
        // it may never make a setting unreachable.
    )

    /** The double-valued V5 knobs auto-config manages (stable order). */
    val managedDoubleKeys: List<DoubleKey> = listOf(
        DoubleKey.ApsBoostV5Aggression,
        DoubleKey.ApsBoostV5HypoCaution,
        DoubleKey.ApsBoostV5ConfirmedCapU,
        DoubleKey.ApsBoostV5CommittedCapU,
        DoubleKey.ApsBoostCumulativeSmbCap60Min,
        DoubleKey.ApsBoostMaxIob,
        DoubleKey.ApsBoostBolus,
        DoubleKey.ApsBoostV5PrimerCapU   // NOT raise-guarded — safety is the locked TBR delivery, see doseCapKeys
    )

    /** [managedDoubleKeys] paired with their suggested values (same stable order). */
    fun managedDoubleKnobs(s: BoostV5AutoConfig.V5Suggestion): List<Pair<DoubleKey, Double>> = listOf(
        DoubleKey.ApsBoostV5Aggression to s.aggression,
        DoubleKey.ApsBoostV5HypoCaution to s.hypoCaution,
        DoubleKey.ApsBoostV5ConfirmedCapU to s.confirmedCapU,
        DoubleKey.ApsBoostV5CommittedCapU to s.committedCapU,
        DoubleKey.ApsBoostCumulativeSmbCap60Min to s.cumulativeSmbCap60MinU,
        DoubleKey.ApsBoostMaxIob to s.maxIobU,
        DoubleKey.ApsBoostBolus to s.bolusCapU,
        DoubleKey.ApsBoostV5PrimerCapU to s.primerCapU   // 2026-07-20 V1-acceleration primer
    )

    /**
     * "User (or preset) has tuned this knob": a value exists in storage AND it differs from every
     * factory default the key has ever shipped with ([factoryDefaults]). A missing value, or a
     * value persisted AT any-era factory default (settings-screen visit, import of stock settings,
     * an old build's default), does NOT count as tuned — nobody objected to a default, so the
     * suggestion may still be applied.
     */
    fun isUserTuned(key: DoubleKey, storedValue: Double?): Boolean =
        storedValue != null && factoryDefaults(key).none { abs(storedValue - it) <= DEFAULT_EPS }

    /** How a knob was classified by [applyAutoConfig] this run. */
    enum class Outcome {
        APPLIED, KEPT_USER_TUNED, SUGGESTED_NOT_APPLIED_TBR,
        // periodic re-derivation outcomes (2026-08-03)
        REDRIVEN,                 // the knob was moved by a scheduled re-derivation
        INSIDE_DEADBAND,          // move smaller than the measurement error; it accumulates
        AWAITING_CONFIRMATION,    // quantised knob: a new value must repeat once before it is written
        BASELINE_RECORDED,        // first sight: where the derivation sits; nothing written
        RETIRED_USER_EDITED       // the user has changed it since we wrote it — never revisit
    }

    /**
     * ── Periodic re-derivation (2026-08-03, rev 2) ─────────────────────────────────────────────
     *
     * Tracks how far each knob's DRIVER has moved and applies that movement to whatever the knob is
     * currently set to — rather than overwriting it with a fresh absolute derivation.
     *
     * Why. A user who raised committedCap from a derived 1.24 to 1.8 was expressing a judgement the
     * formula does not capture. Overwriting it discards that; freezing it means the knob never
     * tracks anything again. Applying the movement keeps both: if TDD then rises 20%, they go to
     * 2.16 and their own +45% offset survives.
     *
     * The load-bearing property: because the knob is scaled by exactly the ratio the derivation
     * moved, `current / derived` is INVARIANT across a re-derivation. The user's offset neither
     * decays nor compounds — only the driver's own movement is tracked. That is also why this
     * needs no notion of who "owns" a knob, and hence no ownership ledger: nothing is ever
     * overwritten, so it never matters whether auto-config or the user set the current value.
     * (rev 1 used an applied-value ledger and was inert on every existing install, because the
     * ledger could only be populated by the onboarding path, which had already run.)
     *
     * Two families, because a ratio is meaningless for a knob with three possible values:
     *  - RATIO knobs (committedCap, confirmedCap) are U quantities that scale with dose size:
     *        proposed = current × (derivedNow / baseline)
     *  - OFFSET knobs (aggression, hypoCaution) are bounded scales stepping by a fixed quantum:
     *        proposed = current + (derivedNow − baseline)
     *  - COMPUTED knobs (cumulative60, primerCap) are not tracked at all — they are recomputed from
     *    the operative per-shot caps exactly as the derivation itself computes them, so they follow
     *    automatically and can never drift out of step with the caps they bound.
     *
     * The baseline is the DERIVED value at the last write, and is only advanced WHEN we write, so
     * movement suppressed by the deadband or held by the raise-guard accumulates rather than being
     * lost. On the very first evaluation there is no baseline, so no TRACKED knob is written — the
     * run records where the derivation currently sits and tracking begins from the next one.
     *
     * The COMPUTED knobs are the exception and CAN be written on that first run: they are not
     * tracked, they are recomputed from the operative caps every time, so if the stored cumulative
     * cap has drifted out of step with `confirmedCap + 2 x committedCap` it is corrected
     * immediately. Observed in the field on 2026-08-04: a first run reported ch=2, both of them
     * computed knobs. That is intended — a budget sized from a cap that no longer applies is the
     * incoherence the 2026-07-06 migration backtest found — but "the first run changes nothing" is
     * NOT true, and was stated as such when this shipped.
     *
     * Note also that cumulative60 passes through the raise-guard when it increases and primerCap
     * does NOT, matching the onboarding path: the primer's safety is its delivery routing rather
     * than a cap.
     */
    val REDRIVE_RATIO_KEYS: List<DoubleKey> = listOf(
        DoubleKey.ApsBoostV5CommittedCapU,
        DoubleKey.ApsBoostV5ConfirmedCapU
    )

    val REDRIVE_OFFSET_KEYS: List<DoubleKey> = listOf(
        DoubleKey.ApsBoostV5Aggression,
        DoubleKey.ApsBoostV5HypoCaution
    )

    /** Tracked knobs, in the order they must be processed (caps before the knobs computed from them). */
    val REDRIVE_KEYS: List<DoubleKey> = REDRIVE_RATIO_KEYS + REDRIVE_OFFSET_KEYS

    /**
     * Largest single-step change, as a ratio of the current value. Bounds one evaluation's move
     * when a driver jumps — a pump-site change or a fortnight of illness can shift median TDD
     * sharply, and a 28-day window carries that in as a step. Clipped movement is NOT lost: on a
     * write the baseline advances only by the movement actually applied, so the remainder arrives
     * over subsequent evaluations until the knob reaches its target.
     */
    const val REDRIVE_MAX_STEP_RATIO = 0.25

    /**
     * Minimum move worth writing, per knob — that knob's day-block bootstrap half-width over a
     * 28-day window (REDRIVE_REPORT.md §4b). Below it the move is inside the noise of measuring it.
     * OFFSET knobs are absent deliberately: their own rounding is already the filter, and a band
     * wider than the quantum (hypoCaution: 0.16 vs 0.1) would freeze them below a double step.
     */
    val REDRIVE_DEADBAND: Map<DoubleKey, Double> = mapOf(
        DoubleKey.ApsBoostV5CommittedCapU to 0.07,
        DoubleKey.ApsBoostV5ConfirmedCapU to 0.47
    )

    /**
     * OFFSET knobs get hysteresis instead of a deadband: a new value must be derived twice
     * consecutively before it is written, so a knob cannot flap across a threshold (cohort user C
     * flipped aggression 1.0/0.92 across the 4% TBR line depending on the window).
     */
    val REDRIVE_CONFIRM_TWICE: Set<DoubleKey> = REDRIVE_OFFSET_KEYS.toSet()

    /** Why a re-derivation did nothing — logged and surfaced so a silent no-op is impossible. */
    enum class RedriveSkip { NOT_DUE, ONBOARDING_INCOMPLETE, INSUFFICIENT_HISTORY, BASELINE_SEEDED }

    /**
     * Apply the derivation's MOVEMENT to each tracked knob's current value. See the design note
     * above: nothing is overwritten, so no ownership is needed and the user's offset is preserved.
     */
    fun redrive(
        suggestion: BoostV5AutoConfig.V5Suggestion,
        tbrBelow70Pct: Double,
        timeBelow54Pct: Double,
        storedValue: (DoubleKey) -> Double?,
        baselineValue: (DoubleKey) -> Double?,
        pendingValue: (DoubleKey) -> Double?,
        put: (DoubleKey, Double) -> Unit,
        setBaseline: (DoubleKey, Double) -> Unit,
        setPending: (DoubleKey, Double?) -> Unit
    ): List<Resolution> {
        val out = mutableListOf<Resolution>()
        val raiseGuard = tbrBelow70Pct > TBR_RAISE_GUARD_PCT || timeBelow54Pct >= TBR54_RAISE_GUARD_PCT
        val derivedFor = managedDoubleKnobs(suggestion).toMap()
        val operative = mutableMapOf<DoubleKey, Double>()
        for (k in managedDoubleKeys) operative[k] = storedValue(k) ?: k.defaultValue

        for (key in REDRIVE_KEYS) {
            val current = operative.getValue(key)
            val derivedNow = derivedFor.getValue(key)
            val baseline = baselineValue(key)

            // First sight: record where the derivation sits and change nothing. We track MOVEMENT,
            // and none has been observed yet.
            if (baseline == null || baseline <= 0.0) {
                setBaseline(key, derivedNow)
                out += Resolution(key, Outcome.BASELINE_RECORDED, derivedNow, current,
                                  "baseline recorded at $derivedNow; tracking starts next run")
                continue
            }

            val rawProposed = if (key in REDRIVE_RATIO_KEYS) current * (derivedNow / baseline)
                              else current + (derivedNow - baseline)
            val stepCap = abs(current) * REDRIVE_MAX_STEP_RATIO
            val bounded = when {
                rawProposed > current + stepCap -> current + stepCap
                rawProposed < current - stepCap -> current - stepCap
                else                            -> rawProposed
            }
            val proposed = round2(bounded.coerceIn(key.min, key.max))
            val delta = proposed - current

            if (abs(delta) <= DEFAULT_EPS) {
                // Clear any pending confirmation: "twice consecutively" must mean CONSECUTIVELY, or
                // a knob alternating either side of a threshold accumulates a match across the gap
                // and eventually writes the flap.
                setPending(key, null)
                out += Resolution(key, Outcome.INSIDE_DEADBAND, proposed, current,
                                  "no movement: derivation $baseline → $derivedNow leaves $current unchanged")
                continue
            }

            if (key in REDRIVE_CONFIRM_TWICE) {
                val pending = pendingValue(key)
                if (pending == null || abs(pending - proposed) > DEFAULT_EPS) {
                    setPending(key, proposed)
                    out += Resolution(key, Outcome.AWAITING_CONFIRMATION, proposed, current,
                                      "held for confirmation: $current → $proposed must repeat next run")
                    continue
                }
            } else {
                val band = REDRIVE_DEADBAND[key] ?: 0.0
                if (abs(delta) <= band) {
                    // Baseline deliberately NOT advanced — the movement accumulates for next time.
                    out += Resolution(key, Outcome.INSIDE_DEADBAND, proposed, current,
                                      "no change: move ${round2(delta)} within the ±$band noise band (accumulating)")
                    continue
                }
            }

            // hypoCaution RISING is a tightening; for the caps a rise is a loosening.
            val loosening = if (key == DoubleKey.ApsBoostV5HypoCaution) delta < 0 else delta > 0
            if (loosening && key in doseCapKeys && raiseGuard) {
                setPending(key, null)
                out += Resolution(key, Outcome.SUGGESTED_NOT_APPLIED_TBR, proposed, current,
                                  "raise held: $current → $proposed; TBR<70=$tbrBelow70Pct% <54=$timeBelow54Pct%")
                continue
            }

            put(key, proposed)
            // Advance the baseline by the movement ACTUALLY APPLIED, not by the movement derived.
            // When the step cap clips a large move, advancing to derivedNow here would DISCARD the
            // remainder and strand the knob permanently short of its target — e.g. an insulin
            // concentration change that doubles TDD-in-units would move a cap by +25% once and then
            // stop, ~40% below where it belongs. Advancing proportionally leaves the residual in
            // place, so it arrives over subsequent evaluations. Unclipped moves are unaffected:
            // proposed/current == derivedNow/baseline, so this reduces to derivedNow exactly.
            val appliedBaseline =
                if (key in REDRIVE_RATIO_KEYS) {
                    if (abs(current) > DEFAULT_EPS) baseline * (proposed / current) else derivedNow
                } else baseline + (proposed - current)
            setBaseline(key, appliedBaseline)
            setPending(key, null)
            operative[key] = proposed
            out += Resolution(key, Outcome.REDRIVEN, proposed, proposed,
                              "tracked $current → $proposed (derivation moved $baseline → $derivedNow)")
        }

        // COMPUTED knobs follow the operative caps, exactly as the derivation computes them.
        val cum = DoubleKey.ApsBoostCumulativeSmbCap60Min
        val curCum = operative.getValue(cum)
        val newCum = BoostV5AutoConfig.cumulativeCap60Min(
            operative.getValue(DoubleKey.ApsBoostV5ConfirmedCapU),
            operative.getValue(DoubleKey.ApsBoostV5CommittedCapU))
        if (abs(newCum - curCum) > DEFAULT_EPS) {
            if (newCum > curCum && raiseGuard) {
                out += Resolution(cum, Outcome.SUGGESTED_NOT_APPLIED_TBR, newCum, curCum,
                                  "raise held: $curCum → $newCum; TBR<70=$tbrBelow70Pct%")
            } else {
                put(cum, newCum)
                out += Resolution(cum, Outcome.REDRIVEN, newCum, newCum,
                                  "recomputed $curCum → $newCum from the operative caps")
            }
        }
        // primerCap is a fraction of committedCap; take the fraction from the derivation so the
        // hypo-prone / well-controlled policy is never duplicated here.
        val primer = DoubleKey.ApsBoostV5PrimerCapU
        if (suggestion.committedCapU > 0.0) {
            val frac = suggestion.primerCapU / suggestion.committedCapU
            val curPrimer = operative.getValue(primer)
            val newPrimer = round2((operative.getValue(DoubleKey.ApsBoostV5CommittedCapU) * frac)
                                       .coerceIn(primer.min, primer.max))
            if (abs(newPrimer - curPrimer) > 0.056) {
                put(primer, newPrimer)
                out += Resolution(primer, Outcome.REDRIVEN, newPrimer, newPrimer,
                                  "recomputed $curPrimer → $newPrimer from committedCap")
            }
        }
        return out
    }

    private fun round2(x: Double) = Math.round(x * 100.0) / 100.0

    /**
     * Per-knob classification record. [suggestedValue] is the final derived value for the knob
     * (for the cumulative cap: recomputed from the operative per-shot caps); [operativeValue] is
     * what governs dosing after this run; [reason] is the human-readable classification the plugin
     * logs verbatim so field diagnosis never needs inference.
     */
    data class Resolution(
        val key: DoubleKey,
        val outcome: Outcome,
        val suggestedValue: Double,
        val operativeValue: Double,
        val reason: String
    )

    /**
     * Apply the suggestion with per-knob resolution. For each knob, in order:
     *  - already RESOLVED (applied or skipped in an earlier run) → untouched (no [Resolution]);
     *  - user-tuned ([isUserTuned], any-era factory-aware) → kept, marked resolved (never revisited);
     *  - a dose-cap ([doseCapKeys]) whose derived value would RAISE the operative value while the
     *    14-day TBR<70 exceeds [TBR_RAISE_GUARD_PCT] OR the 14-day time-below-54 is ≥
     *    [TBR54_RAISE_GUARD_PCT] → NOT written, marked resolved, returned as
     *    [Outcome.SUGGESTED_NOT_APPLIED_TBR] so the caller can surface the suggestion;
     *  - otherwise → suggested value written, marked resolved.
     *
     * The cumulative 60-min cap is recomputed HERE from the FINAL operative per-shot caps
     * (kept-or-derived-or-guard-held), via [BoostV5AutoConfig.cumulativeCap60Min] — never taken
     * verbatim from the derivation, whose caps may not be the ones that apply.
     *
     * Per-knob and independent — presetting one never blocks the others. Pure: the lambdas inject
     * the preference I/O so all skip/resolve behaviour is testable without the plugin/DI.
     *
     * NOT called when there is insufficient history (the caller gets no suggestion), so unresolved
     * knobs remain eligible and genuinely retry on a later cycle.
     */
    fun applyAutoConfig(
        suggestion: BoostV5AutoConfig.V5Suggestion,
        tbrBelow70Pct: Double,
        timeBelow54Pct: Double = 0.0,
        isResolved: (DoubleKey) -> Boolean,
        storedValue: (DoubleKey) -> Double?,
        put: (DoubleKey, Double) -> Unit,
        markResolved: (DoubleKey) -> Unit
    ): List<Resolution> {
        val resolutions = mutableListOf<Resolution>()
        val operative = mutableMapOf<DoubleKey, Double>()
        // Raise-guard trigger: <70 over its line OR <54 at/over the consensus severe line (2026-07-07).
        val raiseGuardTripped = tbrBelow70Pct > TBR_RAISE_GUARD_PCT || timeBelow54Pct >= TBR54_RAISE_GUARD_PCT

        fun resolve(key: DoubleKey, derived: Double) {
            val stored = storedValue(key)
            val current = stored ?: key.defaultValue
            if (isResolved(key)) {
                operative[key] = current                    // untouched; feeds the cumulative recompute
                return
            }
            if (isUserTuned(key, stored)) {
                markResolved(key)                           // user value kept; never revisit
                operative[key] = current
                resolutions += Resolution(key, Outcome.KEPT_USER_TUNED, derived, current, "kept-user-tuned value=$current (suggested $derived)")
                return
            }
            if (key in doseCapKeys && derived > current + DEFAULT_EPS && raiseGuardTripped) {
                markResolved(key)                           // suggestion surfaced, not written
                operative[key] = current
                resolutions += Resolution(
                    key, Outcome.SUGGESTED_NOT_APPLIED_TBR, derived, current,
                    "suggested-not-applied (TBR): suggested=$derived current=$current " +
                        "TBR<70=$tbrBelow70Pct% (guard >$TBR_RAISE_GUARD_PCT%) <54=$timeBelow54Pct% (guard ≥$TBR54_RAISE_GUARD_PCT%)"
                )
                return
            }
            put(key, derived)
            markResolved(key)
            operative[key] = derived
            resolutions += Resolution(key, Outcome.APPLIED, derived, derived, "applied $derived")
        }

        resolve(DoubleKey.ApsBoostV5Aggression, suggestion.aggression)
        resolve(DoubleKey.ApsBoostV5HypoCaution, suggestion.hypoCaution)
        resolve(DoubleKey.ApsBoostV5ConfirmedCapU, suggestion.confirmedCapU)
        resolve(DoubleKey.ApsBoostV5CommittedCapU, suggestion.committedCapU)
        // Cumulative cap from the FINAL operative per-shot caps (kept-or-derived), never the
        // derivation's own caps (cohort user E: budget sized from a derived confirmedCap 4.65 that
        // never applied while his operative cap was 2.0).
        resolve(
            DoubleKey.ApsBoostCumulativeSmbCap60Min,
            BoostV5AutoConfig.cumulativeCap60Min(
                operative.getValue(DoubleKey.ApsBoostV5ConfirmedCapU),
                operative.getValue(DoubleKey.ApsBoostV5CommittedCapU)
            )
        )
        resolve(DoubleKey.ApsBoostMaxIob, suggestion.maxIobU)
        resolve(DoubleKey.ApsBoostBolus, suggestion.bolusCapU)
        // 2026-07-20 V1-acceleration primer cap. NOT raise-guarded (see doseCapKeys): a hypo-prone user
        // must still be PROVISIONED a non-zero size, because their recommended delivery route — a
        // retractable temp basal — needs one. The routing is a recommendation the user may override; an
        // override is logged at the delivery seam (primerRoute) so it is visible in the data.
        resolve(DoubleKey.ApsBoostV5PrimerCapU, suggestion.primerCapU)
        return resolutions
    }

    /**
     * Auto-config persistence schema version — THE single hook future re-migrations plug into
     * (extend the `if (storedVersion < N)` chain in [runSchemaMigrations] and bump this).
     *
     * Why it exists (the promoted-APK-window incident, 2026-07-06): the per-knob resolution
     * (b2c0705e5e) shipped in the promoted APK `Boost-V6-experimental-promoted-2026-07-06.apk`
     * WITHOUT the historical-factory amendments in this file. That build's era-blind [isUserTuned]
     * classifies a stored OLD-era factory value (committedCap 0.25 / confirmedCap 1.0 /
     * cumulative 6.0) as "user-tuned" and persists the knob's resolved flag — terminally, since
     * resolved knobs are never revisited. Installing the amended build afterwards would NOT rescue
     * them without this: on startup, when the stored schema version is < 2, every resolved knob
     * whose stored value now classifies as at-factory (any era) has its resolved flag CLEARED so
     * the normal per-knob derivation picks it up next cycle; genuinely off-all-factories values
     * stay resolved. Then the current version is stamped. Idempotent; a fresh install just stamps.
     *
     * Versions: 0 = pre-versioning (everything up to and incl. the promoted 2026-07-06 APK);
     * 2 = historical-factory re-audit of persisted resolved flags. (1 is skipped so the version
     * mirrors the amendment generation; nothing ever stamped 1.)
     */
    const val AUTO_CONFIG_SCHEMA_VERSION = 2

    /**
     * Versioned re-migration of persisted per-knob resolution state (see
     * [AUTO_CONFIG_SCHEMA_VERSION] for the incident that motivated it). The b2c0705e5e-era
     * persistence shape stores ONLY a boolean resolved flag per knob
     * (`boost_v5_autoconfig_resolved_<prefKey>`) with no outcome detail, so applied and
     * kept-user-tuned are indistinguishable — the audit therefore re-runs the (now
     * historical-factory-aware) [isUserTuned] on every resolved knob's stored value and clears the
     * flag when the value is at ANY era's factory. A knob auto-APPLIED at a factory-coincident
     * value (e.g. Aggression 1.0) gets re-opened too, which is harmless: re-derivation is
     * suggestion-only and still respects tuned values.
     *
     * Runs at most once per schema bump: no-op (empty result, no version write) when the stored
     * version is current; otherwise clears + stamps [AUTO_CONFIG_SCHEMA_VERSION]. Returns the
     * re-opened keys for logging. Pure — the lambdas inject preference I/O.
     */
    fun runSchemaMigrations(
        storedVersion: Int,
        keys: List<DoubleKey>,
        isResolved: (DoubleKey) -> Boolean,
        storedValue: (DoubleKey) -> Double?,
        clearResolved: (DoubleKey) -> Unit,
        setVersion: (Int) -> Unit
    ): List<DoubleKey> {
        if (storedVersion >= AUTO_CONFIG_SCHEMA_VERSION) return emptyList()
        val cleared = mutableListOf<DoubleKey>()
        if (storedVersion < 2) {
            // v2: re-open knobs the era-blind isUserTuned mis-resolved at an old factory value.
            cleared += keys.filter { isResolved(it) && !isUserTuned(it, storedValue(it)) }
                .onEach(clearResolved)
        }
        // Future re-migrations: add `if (storedVersion < 3) { ... }` here and bump the constant.
        setVersion(AUTO_CONFIG_SCHEMA_VERSION)
        return cleared
    }

    /**
     * One-time migration from the legacy global "auto-config done" flag to per-key resolution.
     * Called when the legacy flag is found set: marks as resolved ONLY the keys whose stored value
     * differs from every factory default the key ever shipped with (they were plausibly applied by
     * the old run, or user-set — either way they must not be rewritten). Keys still AT a factory
     * default (current or any historical era) stay UNRESOLVED and become eligible for derivation
     * again — this is what rescues installs where the old presence-test (or a consumed flag)
     * wrongly skipped them; suggestion-only still holds because value == default means nobody
     * objected. Returns the keys marked resolved.
     */
    fun migrateLegacyDoneFlag(
        keys: List<DoubleKey>,
        storedValue: (DoubleKey) -> Double?,
        markResolved: (DoubleKey) -> Unit
    ): List<DoubleKey> =
        keys.filter { isUserTuned(it, storedValue(it)) }.onEach(markResolved)
}
