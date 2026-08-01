package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.keys.StringKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.plugins.aps.getBoostDosing
import org.json.JSONObject
import java.util.Locale
import kotlin.math.round

/**
 * V5 persisted-state store.
 *
 * V5 needs to remember `mealHypothesis`, `mealHypothesisAge`, and `mlMealLikelyNullStreak`
 * across cycles — without persistence, every plugin invocation would start from IDLE and the
 * state machine couldn't function. We use AAPS's Preferences-backed StringKey
 * (`StringKey.ApsBoostV5State`) holding a small JSON blob.
 *
 * Why a StringKey JSON blob and not three separate keys: state values must be read/written
 * atomically — partial updates would let mealHypothesis advance while age stays stale, which
 * would silently break hysteresis. JSON in one key keeps writes atomic.
 *
 * RT NS fields are written separately (to ProcessedDeviceStatusData via the existing pipeline)
 * for observability — see [v5DecisionToRtJson].
 *
 * ## 2026-05-26 Fix 6 — in-memory cache for atomic persistence across rapid invokes
 *
 * Diagnosed 2026-05-26 from the 2026-05-25 evening meal trace: V5 fired CONFIRMED 4 times in
 * 20 min during a single meal climb. Root cause: AAPS invokes the V4.4.2 plugin (which calls
 * `runShadow()` → V5StateStore) MULTIPLE times per 5-min cycle during SMB delivery (every
 * 1-3 min, not every 5). AAPS `Preferences.put()` writes asynchronously, so a second invoke
 * arriving within milliseconds of the first reads stale state — including blank — and the
 * fallback drops V5 back to IDLE, restarting the state machine mid-meal.
 *
 * Fix: maintain a `@Volatile` in-memory cache of the most recent persisted state. Load
 * returns the cache first (always-current within process), falling back to SharedPreferences
 * only on cold start (cache=null). Save updates both the cache (synchronous) and
 * SharedPreferences (async-flushed via the preferences interface, for restart-recovery).
 *
 * This eliminates the race entirely — every load within the same process sees what the most
 * recent save wrote, regardless of whether SharedPreferences has flushed yet.
 *
 * See `boost_v5_multi_confirmed_investigation.md` for the full diagnosis and trace.
 */
class V5StateStore(private val preferences: Preferences, private val aapsLogger: AAPSLogger? = null) {

    /**
     * Most recent persisted state, held in memory for synchronous read consistency.
     * Initialised to null (cold-start sentinel — first load() falls through to SharedPreferences).
     * Updated on every save(). Read by load() ahead of the SharedPreferences path.
     */
    @Volatile private var cached: V5PersistedState? = null

    fun load(): V5PersistedState {
        // 2026-05-26 Fix 6: prefer in-memory cache; SharedPreferences only on cold start.
        cached?.let { return it }

        // getBoostDosing (not get): Simple Mode masks defaultedBySM StringKeys to their "" default,
        // which would discard the persisted V5 state-machine on cold start (post app-restart) and
        // reset OBSERVING→CONFIRMED progress. See BoostDosingPreferences.kt.
        val raw = preferences.getBoostDosing(StringKey.ApsBoostV5State)
        if (raw.isBlank()) {
            // Cold start with no persisted state: seed cache with default IDLE so subsequent
            // reads in the same process are consistent.
            val fresh = V5PersistedState()
            cached = fresh
            return fresh
        }
        val loaded = try {
            val json = JSONObject(raw)
            val state = MealHypothesisState(
                state = MealHypothesis.valueOf(json.getString("mealHypothesis")),
                ageCycles = json.getInt("mealHypothesisAge"),
                // 2026-05-15: peak score added to state. Missing in pre-fix state → default 0.0
                // (next OBSERVING cycle will populate it from the entry score).
                maxScoreInObserving = json.optDouble("maxScoreInObserving", 0.0),
                // 2026-05-22 Fix 5: peak eventualBG-target offset. Missing in pre-Fix-5 state →
                // default 0.0 (next OBSERVING cycle will populate it from the entry-cycle offset).
                maxEventualBgOffsetInObserving = json.optDouble("maxEventualBgOffsetInObserving", 0.0),
                // 2026-05-26 Fix 6: single-CONFIRMED-per-session guard. Missing in pre-Fix-6
                // state → default false (next session entry will reset it explicitly).
                committedInSession = json.optBoolean("committedInSession", false),
            )
            V5PersistedState(
                mealHypothesis = state,
                mlMealLikelyNullStreak = json.optInt("mlMealLikelyNullStreak", 0),
                // 2026-07-20 primer session accumulators: survive a mid-meal restart. Missing in
                // pre-primer state → default 0.0 (safe: no primer credited, no netting owed).
                primerAppliedU = json.optDouble("primerAppliedU", 0.0),
                primerNettingResidualU = json.optDouble("primerNettingResidualU", 0.0),
                primerIobU = json.optDouble("primerIobU", 0.0),                              // 2026-07-21 cross-session accumulator
                primerIobUpdatedMs = json.optLong("primerIobUpdatedMs", 0L),
                // lastCycleScore is deliberately NOT in the JSON blob (see V5PersistedState KDoc) —
                // it lives only in the in-memory cache. Cold start → null → scoreReadyStreak=false
                // → legacy confirm timing for the first cycle. (2026-07-03)
            )
        } catch (e: Exception) {
            // Corrupt or stale state — fall back to IDLE (safer than carrying forward unknown state),
            // LOG it, and clear the blob so it doesn't silently re-parse-and-fail on every cold start.
            aapsLogger?.error(app.aaps.core.interfaces.logging.LTag.APS, "V5StateStore: corrupt persisted state — resetting to IDLE (${e.javaClass.simpleName}: ${e.message})")
            preferences.put(StringKey.ApsBoostV5State, "")
            V5PersistedState()
        }
        cached = loaded
        return loaded
    }

    fun save(state: V5PersistedState) {
        // 2026-05-26 Fix 6: update in-memory cache synchronously BEFORE the async SharedPreferences
        // write, so any subsequent load() in the same process sees the new state immediately.
        cached = state

        // NOTE: lastCycleScore is intentionally NOT serialized — cache-only cross-cycle input for
        // the sustained-score early confirm; losing it on restart fails safe. (2026-07-03)
        val json = JSONObject()
            .put("mealHypothesis", state.mealHypothesis.state.name)
            .put("mealHypothesisAge", state.mealHypothesis.ageCycles)
            .put("maxScoreInObserving", state.mealHypothesis.maxScoreInObserving)
            .put("maxEventualBgOffsetInObserving", state.mealHypothesis.maxEventualBgOffsetInObserving)
            .put("committedInSession", state.mealHypothesis.committedInSession)
            .put("mlMealLikelyNullStreak", state.mlMealLikelyNullStreak)
            .put("primerAppliedU", state.primerAppliedU)                     // 2026-07-20 primer session state
            .put("primerNettingResidualU", state.primerNettingResidualU)
            .put("primerIobU", state.primerIobU)                            // 2026-07-21 cross-session accumulator
            .put("primerIobUpdatedMs", state.primerIobUpdatedMs)
        preferences.put(StringKey.ApsBoostV5State, json.toString())
    }

    /** Force IDLE. Called on user-initiated reset (e.g., from a settings action). */
    fun clear() {
        cached = null
        preferences.put(StringKey.ApsBoostV5State, "")
    }
}

/**
 * Names of the core NS RT fields emitted via [v5DecisionToRtJson]. The plugin additionally sets
 * `boostV5_finalDose`, `boostV5_active`, `boostV5_committedCap`, `boostV5_confirmedCap`, and (from
 * 2026-07-03) `boostV5_confirmGate`, `boostV5_prospectiveShot`, `boostV5_aggressionKnob` directly
 * on RT (see OpenAPSBoostV5Plugin.runShadow) — 13 fields total as of 2026-07-03. These core six
 * plus per-cycle inputs reconstruct any V5 decision (per `boost_v5_test_plan.md`).
 */
object V5RTFields {
    const val MEAL_SIGNAL_SCORE = "boostV5_score"
    const val MEAL_HYPOTHESIS = "boostV5_state"
    const val MEAL_HYPOTHESIS_AGE = "boostV5_age"
    const val AGGRESSION_BUDGET = "boostV5_budget"
    const val ACTION_MULTIPLIER = "boostV5_actionMult"
    const val GATE_REDUCTION = "boostV5_gateReduction"   // comma-joined gate tags (not a percentage)
}

/**
 * THE single formatter for the compact gate-reduction summary. Used by the rT field, the plugin's
 * log line, and [v5DecisionToRtJson] — one implementation so the three can never diverge. (2026-07-02)
 */
fun formatGateReduction(r: GateReductions): String = listOfNotNull(
    r.iobHeadroomBrake.takeIf { it < 1.0 }?.let { "iobHeadroom:${formatScale(it)}" },
    r.postActionRiskCheck.takeIf { it < 1.0 }?.let { "postAction:${formatScale(it)}" },
    r.decelerationBrake.takeIf { it < 1.0 }?.let { "decel:${formatScale(it)}" },
    r.sensorQualityCheck.takeIf { it < 1.0 }?.let { "sensor:${formatScale(it)}" },
    r.hardGateFired?.let { "HARD:$it" },
    if (r.maxIobClampApplied) "maxIOB" else null,
    if (r.dynamicSpikeCapped) "spike" else null,
).joinToString(",").ifEmpty { "none" }

/** Build a JSON blob suitable for embedding in NS deviceStatus from a [V5Decision]. */
fun v5DecisionToRtJson(decision: V5Decision): JSONObject {
    val gateReduction = formatGateReduction(decision.phase3.reductions)

    return JSONObject()
        .put(V5RTFields.MEAL_SIGNAL_SCORE, round4(decision.score))
        .put(V5RTFields.MEAL_HYPOTHESIS, decision.mealHypothesis.name)
        .put(V5RTFields.MEAL_HYPOTHESIS_AGE, decision.mealHypothesisAge)
        .put(V5RTFields.AGGRESSION_BUDGET, round4(decision.aggressionBudget.budget))
        .put(V5RTFields.ACTION_MULTIPLIER, round4(decision.actionMultiplier))
        .put(V5RTFields.GATE_REDUCTION, gateReduction)
}

/** Numeric rounding to 4 decimals — locale-independent (don't use String.format default locale). */
private fun round4(v: Double): Double = round(v * 10000.0) / 10000.0

/** Compact 2-decimal scale formatter — locale-pinned to US so a comma-decimal device doesn't break parsing. */
private fun formatScale(v: Double): String = String.format(Locale.US, "%.2f", v)
