package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.core.keys.DoubleKey
import app.aaps.core.keys.StringKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.plugins.aps.getBoostDosing
import org.json.JSONObject
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
        DoubleKey.ApsBoostV5PrimerCapU,  // NOT raise-guarded — safety is the locked TBR delivery, see doseCapKeys
        DoubleKey.ApsBoostV5TrancheThreshold   // its own rules, see resolveTrancheThreshold
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
        DoubleKey.ApsBoostV5PrimerCapU to s.primerCapU,  // 2026-07-20 V1-acceleration primer
        // NaN when the evidence fell short: there is no suggestion, and resolveTrancheThreshold then
        // writes nothing. The threshold never passes through resolve() or the movement tracker.
        DoubleKey.ApsBoostV5TrancheThreshold to (s.trancheThreshold ?: Double.NaN)
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
        RETIRED_USER_EDITED,      // the user has changed it since we wrote it — never revisit
        // confirm-tranche threshold outcomes (resolveTrancheThreshold)
        INSUFFICIENT_EVIDENCE,    // too few labelled confirm episodes; nothing written
        LOOSENING_HELD,           // a lower threshold was derived and the lowering guard held it
        AT_NEUTRAL_CEILING        // an aggression raise stopped at AGGRESSION_AUTO_CEILING
    }

    /**
     * The highest value re-derivation will raise aggression to. Onboarding never derives above
     * neutral (BoostV5AutoConfig.compute), and movement tracking could otherwise carry a user's
     * offset above 1.0 past it. A value above 1.0 set by hand is kept and may still be lowered.
     */
    const val AGGRESSION_AUTO_CEILING = 1.0

    /**
     * Labelled confirm episodes needed before a LOWER threshold may be written. Lowering releases
     * more of the held insulin, so it needs twice the evidence a suggestion needs at all
     * ([TrancheThresholdDeriver.MIN_LABELLED]).
     */
    const val TRANCHE_MIN_LABELLED_TO_LOWER = 30

    /**
     * Whether auto-config may lower the tranche threshold at all. False for now, because the
     * derivation is biased downwards once the tranche has been running: episodes in which the
     * tranche withheld insulin go on to peak higher, so more of them are labelled large and the
     * Youden-optimal threshold falls (self derived 0.35 with the tranche on, against 0.65 from the
     * episodes before it). Until the derivation corrects for the tranche's own effect, a lower
     * derived value is not evidence that releasing more is safe, so the threshold may only be
     * raised. The lowering path is kept and is exercised by tests through the `allowLowering`
     * parameter of [resolveTrancheThreshold].
     */
    const val TRANCHE_ALLOW_LOWERING = false

    /**
     * Resolves the confirm-tranche release threshold. Called on every onboarding and re-derivation
     * run, because confirm episodes accumulate only once the V6 override is active, so the evidence
     * usually arrives after onboarding has finished.
     *
     * The threshold is written as an absolute value rather than tracked by movement like the caps,
     * so auto-config has to know which value it wrote itself; [lastWritten] is that value. In order:
     *  - a stored value off the factory default that is not the value auto-config last wrote was set
     *    by hand, and is kept (KEPT_USER_TUNED). Setting it back to 0.48 hands it back.
     *  - no derived threshold (fewer than 15 labelled episodes, or fewer than five in a class):
     *    nothing is written (INSUFFICIENT_EVIDENCE) and the operative value stays.
     *  - derived above the operative value: withholds more, a tightening, written whatever the
     *    person's time below range.
     *  - derived below the operative value: releases more, insulin-adding. Held whenever
     *    `allowLowering` is false, the shipped setting ([TRANCHE_ALLOW_LOWERING]). With it true,
     *    written only when the profile is well controlled (TBR<70 under [BoostV5AutoConfig.WELL_CONTROLLED_MAX_TBR70] and
     *    time<54 under [BoostV5AutoConfig.WELL_CONTROLLED_MAX_SEV54], the cut the other
     *    insulin-adding switches use) and there are at least [TRANCHE_MIN_LABELLED_TO_LOWER] labelled
     *    episodes. Otherwise nothing is written (LOOSENING_HELD) and the operative value, the higher
     *    of the two, stays. This follows the dose-cap raise guard, which leaves the current value in
     *    place and reports the suggestion rather than writing a compromise value.
     *  - derived equal to the operative value: nothing to do (INSIDE_DEADBAND).
     * [writeOutcome] is APPLIED on the onboarding path and REDRIVEN on the re-derivation path, so
     * each caller's existing reporting picks a write up.
     */
    fun resolveTrancheThreshold(
        suggestion: BoostV5AutoConfig.V5Suggestion,
        tbrBelow70Pct: Double,
        timeBelow54Pct: Double,
        storedValue: Double?,
        lastWritten: Double?,
        put: (Double) -> Unit,
        recordWritten: (Double) -> Unit,
        writeOutcome: Outcome = Outcome.APPLIED,
        allowLowering: Boolean = TRANCHE_ALLOW_LOWERING
    ): Resolution {
        val key = DoubleKey.ApsBoostV5TrancheThreshold
        val current = storedValue ?: key.defaultValue
        val derived = suggestion.trancheThreshold
        val tr = suggestion.tranche
        val handSet = storedValue != null && isUserTuned(key, storedValue) &&
            (lastWritten == null || abs(storedValue - lastWritten) > DEFAULT_EPS)
        if (handSet)
            return Resolution(key, Outcome.KEPT_USER_TUNED, derived ?: Double.NaN, current,
                              "kept:user-set $current (derived ${derived ?: "-"})")
        if (derived == null)
            return Resolution(key, Outcome.INSUFFICIENT_EVIDENCE, Double.NaN, current,
                              "held:evidence ${tr?.nSmall ?: 0} small ${tr?.nLarge ?: 0} large; operative $current")
        val target = round2(derived.coerceIn(key.min, key.max))
        if (abs(target - current) <= DEFAULT_EPS)
            return Resolution(key, Outcome.INSIDE_DEADBAND, target, current, "unchanged $current")
        if (target < current) {
            val wellControlled = tbrBelow70Pct < BoostV5AutoConfig.WELL_CONTROLLED_MAX_TBR70 &&
                timeBelow54Pct < BoostV5AutoConfig.WELL_CONTROLLED_MAX_SEV54
            val why = buildList {
                if (!allowLowering) add("lowering-off")
                if (!wellControlled) add("not-well-controlled")
                if ((tr?.nLabelled ?: 0) < TRANCHE_MIN_LABELLED_TO_LOWER) add("n<$TRANCHE_MIN_LABELLED_TO_LOWER")
            }
            if (why.isNotEmpty())
                return Resolution(key, Outcome.LOOSENING_HELD, target, current,
                                  "held:${why.joinToString("+")} lowering $current to $target; " +
                                      "TBR<70=$tbrBelow70Pct% <54=$timeBelow54Pct%")
        }
        put(target)
        recordWritten(target)
        return Resolution(key, writeOutcome, target, target, "set $current to $target")
    }

    /**
     * Entry in the auto-config pending ledger holding the previous re-derivation window's
     * well-controlled verdict (1.0 or 0.0), for [resolvePrimerRoute]. Not a preference key.
     */
    const val PRIMER_ROUTE_PREV_WC_KEY = "primer_route_prev_well_controlled"

    /** Outcome of [resolvePrimerRoute]. [tbrFallback] is the operative routing after the run. */
    data class RouteResolution(val outcome: Outcome, val tbrFallback: Boolean, val reason: String)

    /**
     * Re-evaluates the primer delivery route (BooleanKey.ApsBoostV5PrimerTbrFallback) on a scheduled
     * re-derivation. Onboarding sets the route once from its 14-day window; without this a person
     * routed to the temp basal never returned to the bolus as their time below range fell, and a
     * bolus-routed person stayed on the bolus after becoming hypo-prone.
     *
     * [wellControlled] is the re-derivation window's own verdict, the same cut onboarding uses
     * (TBR<70 under 1.5% and time<54 under 0.3%). The two directions are treated differently because
     * one adds insulin and the other does not:
     *  - not well controlled while on the bolus: moves to the retractable temp basal at once, a
     *    tightening.
     *  - well controlled while on the temp basal: moves to the bolus only when the previous
     *    re-derivation window was well controlled as well ([previousWellControlled] true), since the
     *    bolus is the insulin-adding route. One window alone is AWAITING_CONFIRMATION.
     *  - a window with fewer than [BoostV5AutoConfig.MIN_BG_READINGS] readings changes nothing and
     *    breaks the run of consecutive windows.
     * A stored value that differs from the value auto-config last wrote ([lastWritten]) was set by
     * someone else and is kept. With no record of a write, the stored value is taken as auto-config's
     * own: the key has no preference-screen entry, so the onboarding derivation has been its only
     * writer. ApsBoostV5PrimerBolusMode, the user's override that forces the bolus, is not managed
     * here and still wins at the delivery seam.
     *
     * [recordWellControlled] persists this window's verdict for the next run (null clears it).
     */
    fun resolvePrimerRoute(
        wellControlled: Boolean,
        bgReadings: Int,
        previousWellControlled: Boolean?,
        stored: Boolean?,
        lastWritten: Boolean?,
        put: (Boolean) -> Unit,
        recordWritten: (Boolean) -> Unit,
        recordWellControlled: (Boolean?) -> Unit
    ): RouteResolution {
        val current = stored ?: false
        if (bgReadings < BoostV5AutoConfig.MIN_BG_READINGS) {
            recordWellControlled(null)
            return RouteResolution(Outcome.INSUFFICIENT_EVIDENCE, current, "held:evidence bg=$bgReadings")
        }
        recordWellControlled(wellControlled)
        if (stored != null && lastWritten != null && stored != lastWritten)
            return RouteResolution(Outcome.KEPT_USER_TUNED, current, "kept:user-set tbrFallback=$current")
        return when {
            !wellControlled && !current -> {
                put(true); recordWritten(true)
                RouteResolution(Outcome.REDRIVEN, true, "bolus to temp basal: window not well controlled")
            }
            wellControlled && current && previousWellControlled == true -> {
                put(false); recordWritten(false)
                RouteResolution(Outcome.REDRIVEN, false, "temp basal to bolus: two consecutive well-controlled windows")
            }
            wellControlled && current ->
                RouteResolution(Outcome.AWAITING_CONFIRMATION, true, "held:one-window temp basal kept until a second well-controlled window")
            else -> RouteResolution(Outcome.INSIDE_DEADBAND, current, "unchanged tbrFallback=$current")
        }
    }

    /**
     * Value in the written ledger recording that onboarding found a switch set by the user and kept
     * it. A switch so marked is never changed by re-derivation. 1.0 and 0.0 record auto-config's own
     * true and false.
     */
    const val SWITCH_USER_SET_MARK = -1.0

    /** Pending-ledger entry holding a switch's previous window verdict, for [resolveInsulinAddingSwitch]. */
    fun switchPreviousVerdictKey(prefKey: String) = "switch_prev_allows_$prefKey"

    /** Outcome of [resolveInsulinAddingSwitch]. [value] is the operative setting after the run. */
    data class SwitchResolution(val outcome: Outcome, val value: Boolean, val reason: String)

    /**
     * Re-evaluates an insulin-adding on/off switch on a scheduled re-derivation, by the rules the
     * primer route follows ([resolvePrimerRoute]). Used for ApsBoostV5AggressiveEarlyConfirm and
     * ApsBoostV5FastCarbConfirm, where ON adds insulin. Onboarding sets each once; without this a
     * switch turned on for a person who was well controlled then stayed on after they were not.
     *
     * [allowsOn] is this window's own derivation of the switch (the same rule onboarding applies:
     * the strict well-controlled cut for aggressive early confirm, not hypo-prone for fast-carb
     * confirm). In order:
     *  - a window under [BoostV5AutoConfig.MIN_BG_READINGS] readings changes nothing and breaks the
     *    run of consecutive windows;
     *  - a value the user set is kept: one that differs from auto-config's last write, or one
     *    onboarding marked as the user's ([userMarked]);
     *  - ON while the window does not allow it: switched OFF at once, a tightening;
     *  - OFF while the window allows it: switched ON only when the previous window allowed it too,
     *    and never while the TBR raise-guard is tripped ([raiseGuard]); one window alone is
     *    AWAITING_CONFIRMATION, and a window under the guard does not count towards the two.
     * With no record of a write (installs that onboarded before the written ledger), a stored value
     * at the factory default is auto-config's. A stored value off the default could be either, so
     * it is not overridden in the insulin-adding direction (switching ON is reported as kept) while
     * switching OFF still applies. The verdict is recorded through [recordVerdict] for the next run
     * (null clears it).
     */
    fun resolveInsulinAddingSwitch(
        allowsOn: Boolean,
        raiseGuard: Boolean,
        bgReadings: Int,
        previousAllowsOn: Boolean?,
        stored: Boolean?,
        defaultValue: Boolean,
        lastWritten: Boolean?,
        userMarked: Boolean,
        put: (Boolean) -> Unit,
        recordWritten: (Boolean) -> Unit,
        recordVerdict: (Boolean?) -> Unit
    ): SwitchResolution {
        val current = stored ?: defaultValue
        if (bgReadings < BoostV5AutoConfig.MIN_BG_READINGS) {
            recordVerdict(null)
            return SwitchResolution(Outcome.INSUFFICIENT_EVIDENCE, current, "held:evidence bg=$bgReadings")
        }
        val countsTowardOn = allowsOn && !raiseGuard
        recordVerdict(countsTowardOn)
        if (userMarked || (stored != null && lastWritten != null && stored != lastWritten))
            return SwitchResolution(Outcome.KEPT_USER_TUNED, current, "kept:user-set $current")
        val unrecordedNonDefault = lastWritten == null && stored != null && stored != defaultValue
        return when {
            !allowsOn && current -> {
                put(false); recordWritten(false)
                SwitchResolution(Outcome.REDRIVEN, false, "on to off: window does not allow it")
            }
            allowsOn && !current && raiseGuard ->
                SwitchResolution(Outcome.SUGGESTED_NOT_APPLIED_TBR, false, "held:tbr-guard off kept while time below range trips the guard")
            countsTowardOn && !current && previousAllowsOn == true ->
                if (unrecordedNonDefault)
                    SwitchResolution(Outcome.KEPT_USER_TUNED, false, "kept:unrecorded off is not switched on without a record that auto-config set it")
                else {
                    put(true); recordWritten(true)
                    SwitchResolution(Outcome.REDRIVEN, true, "off to on: two consecutive windows allow it")
                }
            countsTowardOn && !current ->
                SwitchResolution(Outcome.AWAITING_CONFIRMATION, false, "held:one-window off kept until a second window allows it")
            else -> SwitchResolution(Outcome.INSIDE_DEADBAND, current, "unchanged $current")
        }
    }

    /** Compact form of a [SwitchResolution] for the re-derivation breadcrumb (autordv=). */
    fun switchBreadcrumb(tag: String, r: SwitchResolution, allowsOn: Boolean): String {
        val why = r.reason.substringBefore(' ').takeIf { it.startsWith("held:") || it.startsWith("kept:") }
        return "$tag=${r.outcome}/v=${r.value}/ok=$allowsOn" + (if (why != null) "/$why" else "")
    }

    /** Compact form of a [RouteResolution] for the re-derivation breadcrumb (autordv=). */
    fun primerRouteBreadcrumb(r: RouteResolution, wellControlled: Boolean): String {
        val why = r.reason.substringBefore(' ').takeIf { it.startsWith("held:") || it.startsWith("kept:") }
        return "pr=${r.outcome}/tb=${r.tbrFallback}/wc=$wellControlled" + (if (why != null) "/$why" else "")
    }

    /**
     * Compact form of a threshold resolution for the auto-config breadcrumbs, which the engine
     * replays into the reason every cycle (autocfg= and autordv=). Carries no commas or semicolons,
     * since both separate fields there.
     */
    fun trancheBreadcrumb(r: Resolution, tr: TrancheThresholdDeriver.Derivation?): String {
        fun f(x: Double?) = if (x == null || x.isNaN()) "-" else round2(x).toString()
        val why = r.reason.substringBefore(' ').takeIf { it.startsWith("held:") || it.startsWith("kept:") }
        return "tr=${r.outcome}/d=${f(r.suggestedValue)}/op=${f(r.operativeValue)}" +
            "/s=${tr?.nSmall ?: 0}/l=${tr?.nLarge ?: 0}/J=${f(tr?.youdenJ)}" +
            (if (why != null) "/$why" else "")
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
     *    automatically. Because a recomputation overwrites, these two do need ownership: a value
     *    the user set (a lowered cumulative cap, a primer set to 0 to turn it off) is kept, by the
     *    rule in [computedKnobOwned], and a stored primer of 0 is never overwritten.
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
     * While the TBR raise-guard is tripped every insulin-adding move is held: a rise in either cap,
     * the cumulative cap, the primer or aggression, and a fall in hypoCaution. The primer differs
     * from onboarding here, where it is not raise-guarded so that a hypo-prone person is still
     * provisioned one for the temp-basal route; once provisioned, a larger primer waits like the
     * rest. Aggression is in addition never raised above [AGGRESSION_AUTO_CEILING].
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

    /** Smallest primer change re-derivation writes (U); below it a rewrite is rounding noise. */
    const val PRIMER_REWRITE_BAND = 0.056

    /** Every fraction of committedCap the derivation has sized the primer with since 2026-07-30. */
    val PRIMER_FRACTIONS: List<Double> = BoostV5AutoConfig.PRIMER_FRACTIONS

    /**
     * Whether a COMPUTED knob (the cumulative cap, the primer cap) is still auto-config's to
     * recompute, by the rule onboarding uses for every knob: a value nobody has set, or one still at
     * a factory default, is auto-config's ([isUserTuned]); so is the value auto-config last wrote
     * ([lastWritten], from the written ledger). Anything else was set by the user and is kept.
     *
     * Installs that ran re-derivation before the written ledger recorded these knobs have no
     * [lastWritten]. For them a stored value is taken as auto-config's only when it is one
     * auto-config would have left there: within [tolerance] of one of [autoValues], the values the
     * recomputation gives from the caps as they stood when this run began. Re-derivation has
     * recomputed both knobs on every run since 2026-08-03, so on such an install an auto-config
     * value sits at one of these, and a value elsewhere was set by hand. The one value this
     * misreads is a cumulative cap that an earlier run held below its recomputation under the TBR
     * guard: it is kept as though set by hand, which leaves the lower budget in place.
     */
    fun computedKnobOwned(
        key: DoubleKey,
        stored: Double?,
        lastWritten: Double?,
        autoValues: List<Double>,
        tolerance: Double
    ): Boolean = when {
        stored == null || !isUserTuned(key, stored) -> true
        lastWritten != null                         -> abs(stored - lastWritten) <= DEFAULT_EPS
        else                                        -> autoValues.any { abs(stored - it) <= tolerance + DEFAULT_EPS }
    }

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
        setPending: (DoubleKey, Double?) -> Unit,
        lastWritten: (DoubleKey) -> Double? = { null },
        recordWritten: (DoubleKey, Double) -> Unit = { _, _ -> }
    ): List<Resolution> {
        val out = mutableListOf<Resolution>()
        val raiseGuard = tbrBelow70Pct > TBR_RAISE_GUARD_PCT || timeBelow54Pct >= TBR54_RAISE_GUARD_PCT
        val derivedFor = managedDoubleKnobs(suggestion).toMap()
        val operative = mutableMapOf<DoubleKey, Double>()
        for (k in managedDoubleKeys) operative[k] = storedValue(k) ?: k.defaultValue
        val start = operative.toMap()   // as stored before this run moved anything

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
            var proposed = round2(bounded.coerceIn(key.min, key.max))
            // Aggression is never auto-raised above neutral. A raise stops at 1.0, and from a value
            // already at or above 1.0 (which only the user can have set) it does not move at all.
            // The baseline is not advanced, so the withheld movement stays available if the
            // derivation later falls back.
            if (key == DoubleKey.ApsBoostV5Aggression && proposed > current + DEFAULT_EPS) {
                val ceiling = maxOf(current, AGGRESSION_AUTO_CEILING)
                if (proposed > ceiling + DEFAULT_EPS) {
                    if (abs(ceiling - current) <= DEFAULT_EPS) {
                        setPending(key, null)
                        out += Resolution(key, Outcome.AT_NEUTRAL_CEILING, proposed, current,
                                          "held:neutral-ceiling raise $current → $proposed not written; " +
                                              "aggression is auto-raised no higher than $AGGRESSION_AUTO_CEILING")
                        continue
                    }
                    proposed = ceiling
                }
            }
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

            // Any insulin-adding move is held while the TBR guard is tripped: a cap or aggression
            // rising, or hypoCaution falling (hypoCaution RISING is the tightening). Checked before
            // the confirmation and noise filters so a held move is reported as held, and the
            // baseline is not advanced, so the movement accumulates until the guard clears.
            val loosening = if (key == DoubleKey.ApsBoostV5HypoCaution) delta < 0 else delta > 0
            if (loosening && raiseGuard) {
                setPending(key, null)
                out += Resolution(key, Outcome.SUGGESTED_NOT_APPLIED_TBR, proposed, current,
                                  "raise held: $current → $proposed; TBR<70=$tbrBelow70Pct% <54=$timeBelow54Pct%")
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

            put(key, proposed)
            recordWritten(key, proposed)
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

        // COMPUTED knobs follow the operative caps, exactly as the derivation computes them, but
        // only while auto-config still owns them (computedKnobOwned). A value the user set is kept.
        val cum = DoubleKey.ApsBoostCumulativeSmbCap60Min
        val curCum = operative.getValue(cum)
        val newCum = BoostV5AutoConfig.cumulativeCap60Min(
            operative.getValue(DoubleKey.ApsBoostV5ConfirmedCapU),
            operative.getValue(DoubleKey.ApsBoostV5CommittedCapU))
        val cumAtStart = BoostV5AutoConfig.cumulativeCap60Min(
            start.getValue(DoubleKey.ApsBoostV5ConfirmedCapU), start.getValue(DoubleKey.ApsBoostV5CommittedCapU))
        val cumStored = storedValue(cum)
        if (!computedKnobOwned(cum, cumStored, lastWritten(cum), listOf(cumAtStart), DEFAULT_EPS)) {
            out += Resolution(cum, Outcome.KEPT_USER_TUNED, newCum, curCum,
                              "kept:user-set $curCum (recomputed $newCum not written)")
        } else if (abs(newCum - curCum) > DEFAULT_EPS) {
            if (newCum > curCum && raiseGuard) {
                out += Resolution(cum, Outcome.SUGGESTED_NOT_APPLIED_TBR, newCum, curCum,
                                  "raise held: $curCum → $newCum; TBR<70=$tbrBelow70Pct% <54=$timeBelow54Pct%")
            } else {
                put(cum, newCum)
                recordWritten(cum, newCum)
                out += Resolution(cum, Outcome.REDRIVEN, newCum, newCum,
                                  "recomputed $curCum → $newCum from the operative caps")
            }
        } else if (cumStored != null && lastWritten(cum) == null) {
            // Owned, unchanged, and no record of a write yet: record it, so a later edit by the
            // user is recognised exactly rather than by the legacy heuristic.
            recordWritten(cum, cumStored)
        }
        // primerCap is a fraction of committedCap; take the fraction from the derivation so the
        // hypo-prone / well-controlled policy is never duplicated here.
        val primer = DoubleKey.ApsBoostV5PrimerCapU
        if (suggestion.committedCapU > 0.0) {
            val frac = suggestion.primerCapU / suggestion.committedCapU
            val curPrimer = operative.getValue(primer)
            val newPrimer = round2((operative.getValue(DoubleKey.ApsBoostV5CommittedCapU) * frac)
                                       .coerceIn(primer.min, primer.max))
            val primerStored = storedValue(primer)
            val primerAtStart = PRIMER_FRACTIONS.map { round2(start.getValue(DoubleKey.ApsBoostV5CommittedCapU) * it) }
            when {
                // A stored 0 is the primer's only off switch. Auto-config never writes 0 (the
                // derivation's smallest primer is 0.375 x a committed cap of at least 0.25), so a
                // stored 0 was set by the user and is never overwritten by a primer above 0.
                primerStored != null && abs(primerStored) <= DEFAULT_EPS ->
                    out += Resolution(primer, Outcome.KEPT_USER_TUNED, newPrimer, 0.0,
                                      "kept:user-set 0 (primer off; recomputed $newPrimer not written)")
                !computedKnobOwned(primer, primerStored, lastWritten(primer), primerAtStart, PRIMER_REWRITE_BAND) ->
                    out += Resolution(primer, Outcome.KEPT_USER_TUNED, newPrimer, curPrimer,
                                      "kept:user-set $curPrimer (recomputed $newPrimer not written)")
                abs(newPrimer - curPrimer) > PRIMER_REWRITE_BAND && newPrimer > curPrimer && raiseGuard ->
                    // Not raise-guarded at onboarding, where a hypo-prone person must still be
                    // provisioned a primer for the temp-basal route. Once provisioned, a larger
                    // primer is an insulin-adding move like any other and waits for the guard.
                    out += Resolution(primer, Outcome.SUGGESTED_NOT_APPLIED_TBR, newPrimer, curPrimer,
                                      "raise held: $curPrimer → $newPrimer; TBR<70=$tbrBelow70Pct% <54=$timeBelow54Pct%")
                abs(newPrimer - curPrimer) > PRIMER_REWRITE_BAND -> {
                    put(primer, newPrimer)
                    recordWritten(primer, newPrimer)
                    out += Resolution(primer, Outcome.REDRIVEN, newPrimer, newPrimer,
                                      "recomputed $curPrimer → $newPrimer from committedCap")
                }
                primerStored != null && lastWritten(primer) == null -> recordWritten(primer, primerStored)
            }
        }
        // Confirm-tranche threshold: re-derived from the person's own episodes on every run and
        // written as an absolute value under its own rules (resolveTrancheThreshold).
        val tk = DoubleKey.ApsBoostV5TrancheThreshold
        out += resolveTrancheThreshold(
            suggestion, tbrBelow70Pct, timeBelow54Pct,
            storedValue = storedValue(tk), lastWritten = lastWritten(tk),
            put = { put(tk, it) }, recordWritten = { recordWritten(tk, it) },
            writeOutcome = Outcome.REDRIVEN
        )
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
        markResolved: (DoubleKey) -> Unit,
        // What auto-config last wrote to a knob it sets absolutely (the tranche threshold), and the
        // setter for it. Defaults suit a store that has never had one written.
        lastWritten: (DoubleKey) -> Double? = { null },
        recordWritten: (DoubleKey, Double) -> Unit = { _, _ -> }
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
            recordWritten(key, derived)                     // lets re-derivation tell its own value from the user's
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
        // Confirm-tranche threshold, by its own rules. It resolves whatever the outcome, including
        // too little evidence, so that onboarding can finish; the weekly re-derivation evaluates it
        // again on every run, which is where the evidence normally arrives.
        val tk = DoubleKey.ApsBoostV5TrancheThreshold
        if (!isResolved(tk)) {
            resolutions += resolveTrancheThreshold(
                suggestion, tbrBelow70Pct, timeBelow54Pct,
                storedValue = storedValue(tk), lastWritten = lastWritten(tk),
                put = { put(tk, it) }, recordWritten = { recordWritten(tk, it) },
                writeOutcome = Outcome.APPLIED
            )
            markResolved(tk)
        }
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

/**
 * Auto-config's own string state: the JSON ledgers (re-derivation baselines, pending
 * confirmations, last-written values), the rolling history and the breadcrumbs the engine replays
 * into the reason.
 *
 * Every one of these StringKeys is declared `defaultedBySM = true`, so `Preferences.get` returns
 * the empty default while Simple Mode is on. Read that way, each weekly re-derivation saw no
 * baseline, recorded one, and changed nothing, indefinitely; the written ledger read empty, so a
 * value auto-config had written looked like the user's; and the autocfg= and autordv= breadcrumbs
 * vanished from the reason. All reads here go through [getBoostDosing], which reads the stored
 * value whatever the mode. Writes were never masked.
 */
internal object AutoConfigLedger {

    /** The ledger stored under [key] as prefKey to value; empty when unset or unparsable. */
    fun read(preferences: Preferences, key: StringKey): MutableMap<String, Double> {
        val raw = preferences.getBoostDosing(key)
        if (raw.isEmpty()) return mutableMapOf()
        return runCatching {
            val o = JSONObject(raw)
            o.keys().asSequence().associateWith { o.getDouble(it) }.toMutableMap()
        }.getOrElse { mutableMapOf() }
    }

    /** Sets (or, with a null [value], removes) one entry of the ledger under [key]. */
    fun put(preferences: Preferences, key: StringKey, prefKey: String, value: Double?) {
        val m = read(preferences, key)
        if (value == null) m.remove(prefKey) else m[prefKey] = value
        preferences.put(key, JSONObject(m as Map<*, *>).toString())
    }

    /** A stored string such as the redrive history, unmasked. */
    fun text(preferences: Preferences, key: StringKey): String = preferences.getBoostDosing(key)

    /**
     * The autocfg=, autordv= and histsync= breadcrumbs as the engine appends them to the reason,
     * each followed by "; ", or an empty string when none has been written.
     */
    fun reasonBreadcrumbs(preferences: Preferences): String = buildString {
        text(preferences, StringKey.ApsBoostV5AutoConfigSummary).let { if (it.isNotEmpty()) append("autocfg=$it; ") }
        text(preferences, StringKey.ApsBoostV5RedriveSummary).let { if (it.isNotEmpty()) append("autordv=$it; ") }
        text(preferences, StringKey.ApsBoostHistorySyncSummary).let { if (it.isNotEmpty()) append("histsync=$it; ") }
    }
}
