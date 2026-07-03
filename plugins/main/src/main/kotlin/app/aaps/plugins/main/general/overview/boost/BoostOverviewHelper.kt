package app.aaps.plugins.main.general.overview.boost

import app.aaps.core.interfaces.aps.Loop
import app.aaps.core.interfaces.aps.RT
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.iob.IobCobCalculator
import app.aaps.core.interfaces.nsclient.ProcessedDeviceStatusData
import app.aaps.core.interfaces.stats.TddCalculator
import app.aaps.core.interfaces.utils.DateUtil
import app.aaps.core.data.model.TE
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Extracts Boost-specific algorithm data from the last APS run result.
 * Parses APSResult JSON for decision tier, DynISF, TDD, activity mode.
 *
 * Uses a time-based cache (30s expiry) to avoid repeated heavy DB queries
 * (TDD calculations, therapy record lookups) on every UI event.
 */
@Singleton
class BoostOverviewHelper @Inject constructor(
    private val loop: Loop,
    private val processedDeviceStatusData: ProcessedDeviceStatusData,
    private val iobCobCalculator: IobCobCalculator,
    private val tddCalculator: TddCalculator,
    private val persistenceLayer: PersistenceLayer,
    private val dateUtil: DateUtil
) {

    // Cache to avoid recalculating TDD and querying DB on every UI event
    @Volatile private var cachedStatus: BoostStatus? = null
    @Volatile private var cachedAt: Long = 0L

    data class BoostStatus(
        val tier: BoostTier = BoostTier.INACTIVE,
        val tierLabel: String = "Inactive",
        val tierReason: String = "",
        val dynIsfValue: Double = 0.0,
        val tdd7d: Double = 0.0,
        val tdd24h: Double = 0.0,
        val tddWeighted: Double = 0.0,
        val tddFromDebug: Double = 0.0,
        val insulinDivisor: Int = 0,
        val lastBg: Double = 0.0,
        val activityMode: ActivityMode = ActivityMode.NORMAL,
        val activityDetail: String = "Normal",
        val targetBgMgdl: Double = 0.0,
        val autosensRatio: Double = 1.0,
        val profilePercentage: Int = 100,
        val deltaAccl: Double = 0.0,
        val variableSens: Double = 0.0,
        val scriptDebugText: String = "",
        val cannulaAgeDays: Double = -1.0,
        val sensorAgeDays: Double = -1.0,
        val fastCarbProtection: Boolean = false,
    )

    enum class BoostTier(val label: String, val colorHex: Long) {
        BOOST_BOLUS("Boost Bolus", 0xFFE040FB),
        HIGH_BOOST("High Boost", 0xFFFF5252),
        PERCENT_SCALE("Percent Scale", 0xFFFF9800),
        UAM_BOOST("UAM Boost", 0xFFFFC107),
        ACCELERATION("Acceleration", 0xFFFFAB40),
        ENHANCED_OREF1("Enhanced oref1", 0xFF42A5F5),
        REGULAR_OREF1("Regular oref1", 0xFF66BB6A),
        INACTIVE("Inactive", 0xFF78909C);

        companion object {
            fun fromLabel(text: String): BoostTier {
                val t = text.lowercase()
                return when {
                    t.contains("boost bolus") && !t.contains("high")       -> BOOST_BOLUS
                    t.contains("high boost")                               -> HIGH_BOOST
                    t.contains("percent scale") || t.contains("pctscale") -> PERCENT_SCALE
                    t.contains("uam boost")                                -> UAM_BOOST
                    t.contains("acceleration bolus") || t.contains("acceleration") -> ACCELERATION
                    t.contains("enhanced oref1")                           -> ENHANCED_OREF1
                    t.contains("regular oref1") || t.contains("oref1 smb") -> REGULAR_OREF1
                    t.contains("outside boost") || t.contains("sleep-in") -> INACTIVE
                    else                                                   -> REGULAR_OREF1
                }
            }
        }
    }

    enum class ActivityMode(val label: String) {
        NORMAL("Normal"),
        ACTIVE("Active"),
        INACTIVE("Inactive"),
        SLEEP_IN("Sleep-in"),
        BOOST_OFF("Boost off")
    }

    /**
     * Returns cached status if less than CACHE_TTL_MS old, otherwise recalculates.
     * Call invalidate() when you know the underlying data has changed (e.g. new loop run).
     */
    fun getBoostStatus(): BoostStatus {
        val now = System.currentTimeMillis()
        cachedStatus?.let { cached ->
            if (now - cachedAt < CACHE_TTL_MS) return cached
        }
        val status = computeBoostStatus()
        cachedStatus = status
        cachedAt = now
        return status
    }

    /** Force next getBoostStatus() call to recalculate. */
    fun invalidate() {
        cachedAt = 0L
    }

    private fun computeBoostStatus(): BoostStatus {
        val request = loop.lastRun?.request
        // AAPSClient fallback: when Loop isn't running locally, read the RT
        // object received from Nightscout via ProcessedDeviceStatusData
        val rt: RT? = (request as? RT) ?: processedDeviceStatusData.openAPSData.suggested
        val json = try { request?.json() } catch (_: Exception) { null }
        val reason = request?.reason ?: rt?.reason?.toString() ?: ""
        val scriptDebug = request?.scriptDebug ?: rt?.consoleLog ?: emptyList()
        val debugText = scriptDebug.joinToString("\n")
        // Combine all text sources for parsing — scriptDebug, reason, and JSON reason field
        val allText = "$debugText\n$reason"

        // Parse tier from all available text (e.g. "Tier 5 - Percent Scale")
        val tierResult = parseTierFromText(allText) ?: Pair(BoostTier.REGULAR_OREF1, BoostTier.REGULAR_OREF1.label)
        val tier = tierResult.first
        val tierLabel = tierResult.second

        val deltaAccl = json?.optDouble("delta_accl", 0.0) ?: rt?.deltaAcceleration ?: 0.0

        // Parse activity/exercise mode from all text (e.g. "Inactive - 140% profile")
        val activityResult = parseActivityFromText(allText)
        val activityMode = activityResult.first
        val activityDetail = activityResult.second

        val profilePct = json?.optInt("current_profile_percentage", 0) ?: rt?.boostProfileSwitch ?: 0
        // Parse profile % from scriptDebug header: "Boost V2 (...) | Profile: 140%"
        val profileFromDebug = PROFILE_HEADER_REGEX.find(debugText)
            ?.groupValues?.get(1)?.toIntOrNull() ?: 0
        val effectiveProfilePct = when {
            profilePct > 0    -> profilePct
            profileFromDebug > 0 -> profileFromDebug
            else              -> 100
        }

        val tdds7d = tddCalculator.calculate(7, allowMissingDays = true)
        val avg7d = tddCalculator.averageTDD(tdds7d)
        val tdd7d = avg7d?.data?.totalAmount ?: 0.0
        val tdd24h = tddCalculator.calculateDaily(-24, 0)?.totalAmount ?: 0.0

        val lastBg = iobCobCalculator.ads.actualBg()?.recalculated ?: 0.0

        // Use actual DynISF values from the running APS algorithm, with NS RT fallback
        val oapsProfile = request?.oapsProfile
        val variableSens = request?.variableSens ?: rt?.variable_sens ?: 0.0
        val apsTdd = oapsProfile?.TDD ?: rt?.tdd ?: 0.0
        val apsInsulinDivisor = oapsProfile?.insulinDivisor ?: 0

        // Use the algorithm's actual target
        val targetBgMgdl = request?.targetBG ?: rt?.targetBG ?: 0.0

        // Autosens ratio
        val autosensRatio = request?.autosensResult?.ratio ?: rt?.sensitivityRatio ?: 1.0

        // Fast-carb protection state
        val fastCarbProtection = rt?.fastCarbProtection ?: false

        // Try to parse TDD from scriptDebug (Boost may write "TDD: 48.3" or similar)
        val tddFromDebug = parseTddFromText(allText)

        return BoostStatus(
            tier = tier, tierLabel = tierLabel, tierReason = reason,
            dynIsfValue = variableSens,
            tdd7d = tdd7d, tdd24h = tdd24h,
            tddWeighted = apsTdd,
            tddFromDebug = tddFromDebug,
            insulinDivisor = apsInsulinDivisor,
            lastBg = lastBg,
            targetBgMgdl = targetBgMgdl,
            autosensRatio = autosensRatio,
            activityMode = activityMode, activityDetail = activityDetail,
            profilePercentage = effectiveProfilePct,
            deltaAccl = deltaAccl, variableSens = variableSens,
            scriptDebugText = debugText,
            cannulaAgeDays = getAgeDays(TE.Type.CANNULA_CHANGE),
            sensorAgeDays = getAgeDays(TE.Type.SENSOR_CHANGE),
            fastCarbProtection = fastCarbProtection,
        )
    }

    /** Parse "Tier N - Label" from combined text. Returns (BoostTier, display label) or null. */
    private fun parseTierFromText(text: String): Pair<BoostTier, String>? {
        val match = TIER_REGEX.find(text) ?: return null
        val tierNum = match.groupValues[1]
        val tierName = match.groupValues[2].trim()
        // Trim at sentence boundary if reason has extra text after tier label
        val cleanName = tierName.split(TIER_NAME_SPLIT_REGEX).firstOrNull()?.trim()
            ?.trimEnd('<', '>', ' ') ?: tierName
        val label = "Tier $tierNum - $cleanName"
        val tier = BoostTier.fromLabel(cleanName)
        return Pair(tier, label)
    }

    /** Parse activity/exercise mode from Boost scriptDebug.
     *  Formats:
     *    "✓ BOOST ACTIVE (INACTIVE)"  → Boost running, exercise=inactive, profile adjusted
     *    "✓ BOOST ACTIVE (ACTIVE)"    → Boost running, exercise=active
     *    "✗ BOOST INACTIVE: Outside boost time window" → Boost off
     *    "✗ BOOST INACTIVE: Sleep-in (...)" → Sleep-in mode */
    private fun parseActivityFromText(text: String): Pair<ActivityMode, String> {
        // Case 1: "BOOST ACTIVE (INACTIVE)" or "BOOST ACTIVE (ACTIVE)" etc.
        val activeMatch = BOOST_ACTIVE_REGEX.find(text)
        if (activeMatch != null) {
            val modeName = activeMatch.groupValues[1].trim()
            // Extract profile percentage from "→ profile 140%"
            val pct = PROFILE_PCT_REGEX.find(text)?.groupValues?.get(1) ?: ""
            val mode = when (modeName.uppercase()) {
                "INACTIVE"             -> ActivityMode.INACTIVE
                "ACTIVE"               -> ActivityMode.ACTIVE
                "SLEEP-IN", "SLEEP IN" -> ActivityMode.SLEEP_IN
                else                   -> ActivityMode.NORMAL
            }
            val detail = if (pct.isNotEmpty()) "$modeName - $pct%" else modeName
            return Pair(mode, detail)
        }

        // Case 2: "BOOST INACTIVE: Sleep-in (...)"
        if (SLEEP_IN_REGEX.containsMatchIn(text)) {
            return Pair(ActivityMode.SLEEP_IN, "Sleep-in")
        }

        // Case 3: "BOOST INACTIVE: Outside boost time window"
        if (OUTSIDE_WINDOW_REGEX.containsMatchIn(text)) {
            return Pair(ActivityMode.BOOST_OFF, "Outside window")
        }

        // Case 4: Any other "BOOST INACTIVE: <reason>"
        val inactiveMatch = BOOST_INACTIVE_REGEX.find(text)
        if (inactiveMatch != null) {
            val reason = inactiveMatch.groupValues[1].trim().split("\n").first().trim()
            return Pair(ActivityMode.BOOST_OFF, reason)
        }

        return Pair(ActivityMode.NORMAL, "Normal")
    }

    /** Parse TDD from Boost scriptDebug.
     *  Priority: "Final TDD=31.5" > "Blended TDD=31.5" > "TDD: 31.5" */
    private fun parseTddFromText(text: String): Double {
        // Most specific: "Final TDD=31.5"
        FINAL_TDD_REGEX.find(text)?.groupValues?.get(1)?.toDoubleOrNull()?.let { return it }

        // Next: "Blended TDD=31.5"
        BLENDED_TDD_REGEX.find(text)?.groupValues?.get(1)?.toDoubleOrNull()?.let { return it }

        // Fallback: first "TDD: 31.5" (the algorithm's working TDD line)
        TDD_COLON_REGEX.find(text)?.groupValues?.get(1)?.toDoubleOrNull()?.let { return it }

        return 0.0
    }

    private fun getAgeDays(type: TE.Type): Double {
        val event = persistenceLayer.getLastTherapyRecordUpToNow(type)
        return if (event != null) (dateUtil.now() - event.timestamp) / (24.0 * 60 * 60 * 1000) else -1.0
    }

    companion object {
        /** Cache TTL — getBoostStatus() returns cached result within this window */
        private const val CACHE_TTL_MS = 30_000L  // 30 seconds

        // Pre-compiled regexes (avoid recompilation on every getBoostStatus() call)
        private val TIER_REGEX = Regex("""tier\s+(\d+)\s*[-:]\s*(.+)""", RegexOption.IGNORE_CASE)
        private val BOOST_ACTIVE_REGEX = Regex("""BOOST\s+ACTIVE\s*\((\w[\w\s-]*)\)""", RegexOption.IGNORE_CASE)
        private val PROFILE_PCT_REGEX = Regex("""(?:→\s*)?profile\s+(\d+)%""", RegexOption.IGNORE_CASE)
        private val SLEEP_IN_REGEX = Regex("""BOOST\s+INACTIVE\s*:\s*Sleep-?in""", RegexOption.IGNORE_CASE)
        private val OUTSIDE_WINDOW_REGEX = Regex("""BOOST\s+INACTIVE\s*:\s*Outside\s+boost\s+time\s+window""", RegexOption.IGNORE_CASE)
        private val BOOST_INACTIVE_REGEX = Regex("""BOOST\s+INACTIVE\s*:\s*(.+)""", RegexOption.IGNORE_CASE)
        private val FINAL_TDD_REGEX = Regex("""Final\s+TDD\s*=\s*([\d.]+)""", RegexOption.IGNORE_CASE)
        private val BLENDED_TDD_REGEX = Regex("""Blended\s+TDD\s*=\s*([\d.]+)""", RegexOption.IGNORE_CASE)
        private val TDD_COLON_REGEX = Regex("""(?i)\bTDD\b\s*:\s*([\d.]+)""")
        private val TIER_NAME_SPLIT_REGEX = Regex("""[.;,\n]""")
        private val PROFILE_HEADER_REGEX = Regex("""Profile:\s*(\d+)%""")
    }
}
