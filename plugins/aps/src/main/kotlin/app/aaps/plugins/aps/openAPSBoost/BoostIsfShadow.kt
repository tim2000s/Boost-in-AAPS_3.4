package app.aaps.plugins.aps.openAPSBoost

import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import app.aaps.core.keys.StringKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.plugins.aps.getBoostDosing
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min

/**
 * Silent shadow of V4.4.2's TDD-anchored EMA sensitivity ratio.
 *
 * V1's current behaviour: ratio = (tdd_24h / tdd_7d).coerceIn(autosensMin, autosensMax)
 * V4.4.2's behaviour:    ratio = EMA(τ=3h, raw_ratio), with 5-day cold-start blend toward 1.0
 *
 * The shadow computes V4.4.2's ratio in parallel with V1's calculation, persists the EMA
 * state across cycles via SharedPreferences, and produces a side-by-side comparison so the
 * EMA overlay's actual contribution can be quantified without changing dosing.
 *
 * State persisted (JSON in StringKey.ApsBoostIsfShadowState):
 *   - emaState:           Double — current EMA value
 *   - lastUpdateMs:       Long   — last EMA update timestamp
 *   - firstSeenMs:        Long   — earliest known TDD record timestamp (for warmup)
 *
 * Outputs (per cycle): TddSensShadowResult with the smoothed ratio, raw ratio, warmup
 * fraction, and a derived "what would V4.4.2's variable_sens have been if we substitute
 * the EMA ratio into V1's identical formula" — for direct comparison with V1's actual
 * variable_sens.
 *
 * Algorithm is a faithful port of OpenAPSBoostV3MLG3Plugin.computeTddSensitivity (commit
 * 1f81aa2834) with the only adaptation being SharedPreferences persistence so the EMA
 * survives restarts (V4.4.2's plugin instance keeps it in memory; for V1 we cross-cycle
 * via Preferences).
 */
@Singleton
class BoostIsfShadow @Inject constructor(
    private val preferences: Preferences,
    private val aapsLogger: AAPSLogger
) {

    private val tauMs: Long = 3L * 60 * 60 * 1000L         // 3-hour EMA
    private val coldStartDays: Double = 5.0
    private val coldStartMs: Long = (coldStartDays * 24 * 60 * 60 * 1000).toLong()

    // In-memory mirrors of the persisted state. Loaded lazily on first call so DI
    // doesn't trigger a SharedPreferences read at plugin-graph construction time.
    @Volatile private var loaded: Boolean = false
    @Volatile private var emaState: Double = 1.0
    @Volatile private var lastUpdateMs: Long = 0L
    @Volatile private var firstSeenMs: Long = 0L
    private val lock = Any()

    data class TddSensShadowResult(
        val ratio: Double,           // bounded EMA value (V4.4.2's final output)
        val raw: Double,             // raw tdd_24h / tdd_7d (V1's value — same input)
        val ema: Double,             // EMA pre-final-clamp
        val warmupFraction: Double,  // 0.0..1.0
        val debugLine: String
    )

    private fun ensureLoaded() {
        if (loaded) return
        synchronized(lock) {
            if (loaded) return
            try {
                val raw = preferences.getBoostDosing(StringKey.ApsBoostIsfShadowState)   // 2026-07-08: read raw so Simple Mode never wipes the shadow state blob
                if (raw.isNotBlank()) {
                    val j = JSONObject(raw)
                    emaState = j.optDouble("emaState", 1.0)
                    lastUpdateMs = j.optLong("lastUpdateMs", 0L)
                    firstSeenMs = j.optLong("firstSeenMs", 0L)
                }
            } catch (e: Exception) {
                aapsLogger.warn(LTag.APS, "BoostIsfShadow: state load failed (${e.message}); using defaults")
            }
            loaded = true
        }
    }

    private fun persist() {
        try {
            val j = JSONObject()
                .put("emaState", emaState)
                .put("lastUpdateMs", lastUpdateMs)
                .put("firstSeenMs", firstSeenMs)
            preferences.put(StringKey.ApsBoostIsfShadowState, j.toString())
        } catch (e: Exception) {
            aapsLogger.warn(LTag.APS, "BoostIsfShadow: state persist failed (${e.message})")
        }
    }

    /**
     * Compute the V4.4.2-style EMA-smoothed sensitivity ratio for the current cycle.
     *
     * Returns null if either TDD value is missing or non-positive — in which case the
     * V4.4.2 path would also have skipped this overlay and used the raw ratio (i.e. no
     * difference between V1 and V4.4.2 for the cycle).
     *
     * @param tddLast24H tdd_24h in U (must be > 0 to compute)
     * @param tdd7D      tdd_7d  in U (must be > 0 to compute)
     * @param autosensMin lower clamp from profile/settings (typically 0.5–0.7)
     * @param autosensMax upper clamp from profile/settings (typically 1.3–2.0)
     * @param nowMs      current time in ms since epoch
     */
    fun computeShadow(
        tddLast24H: Double?,
        tdd7D: Double?,
        autosensMin: Double,
        autosensMax: Double,
        nowMs: Long = System.currentTimeMillis()
    ): TddSensShadowResult? {
        if (tddLast24H == null || tdd7D == null || tddLast24H <= 0.0 || tdd7D <= 0.0) {
            return null
        }
        ensureLoaded()
        synchronized(lock) {
            // Seed firstSeenMs on the first ever call. We cannot query the TDD database
            // here (no DI to tddCalculator — keeping the shadow free of heavy deps), so
            // the conservative default is "now" → 5-day warmup begins at first call. On
            // an APK upgrade from V4.4.2 where the EMA state was already warm, the user
            // will see a brief 5-day re-blend before the shadow matches what V4.4.2
            // would have produced. Acceptable for a measurement-only shadow.
            if (firstSeenMs == 0L) firstSeenMs = nowMs

            val rawRatio = (tddLast24H / tdd7D).coerceIn(autosensMin, autosensMax)

            // Cold-start: linearly blend raw toward 1.0 over the first 5 days
            val daysSeen = (nowMs - firstSeenMs).toDouble() / (24.0 * 60.0 * 60.0 * 1000.0)
            val warmup = (daysSeen / coldStartDays).coerceIn(0.0, 1.0)
            val warmedRatio = 1.0 + (rawRatio - 1.0) * warmup

            // EMA update with elapsed-time-aware α
            val ema = if (lastUpdateMs == 0L) {
                emaState = warmedRatio
                warmedRatio
            } else {
                val dtMs = (nowMs - lastUpdateMs).coerceAtLeast(0L)
                val alpha = if (dtMs > 0L) 1.0 - exp(-dtMs.toDouble() / tauMs.toDouble()) else 0.0
                emaState += alpha * (warmedRatio - emaState)
                emaState
            }
            lastUpdateMs = nowMs

            // Final autosens clamp on the smoothed value
            val bounded = max(min(ema, autosensMax), autosensMin)

            persist()

            val debug = "IsfShadow: tdd24=${"%.1f".format(tddLast24H)}" +
                " tdd7=${"%.1f".format(tdd7D)}" +
                " | raw=${"%.3f".format(rawRatio)}" +
                " | warmup=${"%.2f".format(warmup)} (days=${"%.1f".format(daysSeen)}/$coldStartDays)" +
                " | warmed=${"%.3f".format(warmedRatio)}" +
                " | ema(τ=3h)=${"%.3f".format(ema)}" +
                " | bounded=${"%.3f".format(bounded)}"
            aapsLogger.debug(LTag.APS, debug)

            return TddSensShadowResult(
                ratio = bounded,
                raw = rawRatio,
                ema = ema,
                warmupFraction = warmup,
                debugLine = debug
            )
        }
    }

    /**
     * Reset the EMA state. Intended for debugging only; not exposed via UI.
     */
    fun reset() {
        synchronized(lock) {
            emaState = 1.0
            lastUpdateMs = 0L
            firstSeenMs = 0L
            persist()
            loaded = true
        }
    }

    fun snapshot(): Triple<Double, Long, Long> = Triple(emaState, lastUpdateMs, firstSeenMs)
}
