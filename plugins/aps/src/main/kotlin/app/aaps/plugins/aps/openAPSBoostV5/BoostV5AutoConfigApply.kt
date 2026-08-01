package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.core.keys.DoubleKey
import kotlin.math.abs

/**
 * Pure helpers for applying a [BoostV5AutoConfig.V5Suggestion] to preferences while respecting any
 * value the user — or a preset (e.g. a pre-seeded keystore/import) — has ALREADY set.
 *
 * Separated from [OpenAPSBoostV5Plugin]'s preference I/O so the invariants Tim cares about are
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
        DoubleKey.ApsBoostV5PrimerCapU   // 2026-07-20 — NOT in doseCapKeys (routing is the safety, see BoostV5AutoConfig)
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
    enum class Outcome { APPLIED, KEPT_USER_TUNED, SUGGESTED_NOT_APPLIED_TBR }

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
        // 2026-07-20 V1-acceleration primer cap. NOT in doseCapKeys, so the raise-guard does not block
        // it — the bolus-vs-temp-basal routing is the safety differentiator, and a tbr-routed
        // (non-well-controlled) user still needs a non-zero cap to size the retractable temp-basal.
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
