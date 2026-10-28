package app.aaps.plugins.aps.glucagon

import android.content.Context
import androidx.preference.PreferenceCategory
import androidx.preference.PreferenceManager
import androidx.preference.PreferenceScreen
import app.aaps.core.data.model.BS
import app.aaps.core.data.plugin.PluginType
import app.aaps.core.data.time.T
import app.aaps.core.interfaces.aps.APS
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import app.aaps.core.interfaces.plugin.ActivePlugin
import app.aaps.core.interfaces.plugin.PluginBase
import app.aaps.core.interfaces.plugin.PluginDescription
import app.aaps.core.interfaces.profile.ProfileFunction
import app.aaps.core.interfaces.pump.GlucagonPump
import app.aaps.core.interfaces.resources.ResourceHelper
import app.aaps.core.interfaces.rx.AapsSchedulers
import app.aaps.core.interfaces.rx.bus.RxBus
import app.aaps.core.interfaces.rx.events.EventAPSCalculationFinished
import app.aaps.core.interfaces.rx.events.EventGlucagonDoseDelivered
import app.aaps.core.interfaces.utils.DateUtil
import app.aaps.core.keys.BooleanKey
import app.aaps.core.keys.IntKey
import app.aaps.core.keys.StringKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.core.objects.glucagon.GlucagonFormulation
import app.aaps.core.objects.glucagon.GobCalculator
import app.aaps.core.validators.preferences.AdaptiveIntPreference
import app.aaps.core.validators.preferences.AdaptiveListPreference
import app.aaps.core.validators.preferences.AdaptiveSwitchPreference
import app.aaps.plugins.aps.R
import io.reactivex.rxjava3.disposables.CompositeDisposable
import io.reactivex.rxjava3.kotlin.plusAssign
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Glucagon dosing algorithm plugin.
 *
 * Listens for [EventAPSCalculationFinished] and, when all 8 trigger conditions are met,
 * delivers a glucagon microdose via the active [GlucagonPump] implementation.
 *
 * Fully independent of the insulin loop — no changes to LoopPlugin, CommandQueue, or activePump.
 *
 * **Safety:**
 * - Disabled by default (GlucagonEnabled = false)
 * - GLUCAGON records are excluded from IOB calculations in BolusExtension.iobCalc
 * - All 8 conditions must pass simultaneously before any dose is issued
 * - Daily hard cap (GlucagonMaxDailyMcg) blocks further dosing when reached
 */
@Singleton
class GlucagonAlgorithmPlugin @Inject constructor(
    aapsLogger: AAPSLogger,
    rh: ResourceHelper,
    private val rxBus: RxBus,
    private val aapsSchedulers: AapsSchedulers,
    private val preferences: Preferences,
    private val activePlugin: ActivePlugin,
    private val profileFunction: ProfileFunction,
    private val persistenceLayer: PersistenceLayer,
    private val dateUtil: DateUtil
) : PluginBase(
    PluginDescription()
        .mainType(PluginType.GENERAL)
        .pluginIcon(app.aaps.core.ui.R.drawable.ic_generic_icon)
        .pluginName(R.string.glucagon_plugin_name)
        .shortName(R.string.glucagon_plugin_short_name)
        .description(R.string.glucagon_plugin_description)
        .preferencesId(PluginDescription.PREFERENCE_SCREEN),
    aapsLogger, rh
) {

    private val disposable = CompositeDisposable()
    private val gobCalculator by lazy { GobCalculator(persistenceLayer, dateUtil) }

    override fun onStart() {
        super.onStart()
        disposable += rxBus
            .toObservable(EventAPSCalculationFinished::class.java)
            .observeOn(aapsSchedulers.io)
            .subscribe({ evaluateAndDose() }, { aapsLogger.error(LTag.APS, "Glucagon event error", it) })
    }

    /** Exposed for unit tests — do not call from production code. */
    internal fun evaluateAndDoseForTest() = evaluateAndDose()

    override fun onStop() {
        disposable.clear()
        super.onStop()
    }

    // -------------------------------------------------------------------------
    // Main evaluation — called on every APS calculation
    // -------------------------------------------------------------------------

    private fun evaluateAndDose() {
        // Condition 1: feature enabled
        if (!preferences.get(BooleanKey.GlucagonEnabled)) return

        val aps: APS = activePlugin.activeAPS
        val apsResult = aps.lastAPSResult ?: return

        // Condition 2: carbsReq signals upcoming low
        if (!apsResult.isCarbsRequired) return

        val glucoseStatus = apsResult.glucoseStatus ?: return
        val currentBgMgdl = glucoseStatus.glucose

        // Condition 3: current BG <= threshold
        val minBg = preferences.get(IntKey.GlucagonMinBgMgdl)
        if (currentBgMgdl > minBg) return

        // Condition 4: BG falling or short-average delta indicates downward trend
        val trendDown = glucoseStatus.delta <= 0.0 || glucoseStatus.shortAvgDelta <= 0.0
        if (!trendDown) return

        // Condition 5: current GOB < max
        val formulation = GlucagonFormulation.fromKey(preferences.get(StringKey.GlucagonFormulation))
        val maxGob = preferences.get(IntKey.GlucagonMaxGobMcg)
        val currentGob = gobCalculator.currentGob(formulation)
        if (currentGob >= maxGob) {
            aapsLogger.debug(LTag.APS, "Glucagon blocked: GOB ${"%.1f".format(currentGob)} mcg >= max $maxGob mcg")
            return
        }

        // Condition 6: min interval since last dose
        val minInterval = preferences.get(IntKey.GlucagonMinIntervalMinutes)
        val now = dateUtil.now()
        val lastDose = lastGlucagonTimestamp(now)
        val minutesSinceLast = (now - lastDose) / 60_000.0
        if (lastDose > 0 && minutesSinceLast < minInterval) {
            aapsLogger.debug(LTag.APS, "Glucagon blocked: only ${"%.1f".format(minutesSinceLast)} min since last dose (min: $minInterval)")
            return
        }

        // Condition 7: daily total < hard cap
        val maxDaily = preferences.get(IntKey.GlucagonMaxDailyMcg)
        val dailyTotal = dailyGlucagonMcg(now)
        if (dailyTotal >= maxDaily) {
            aapsLogger.warn(LTag.APS, "Glucagon blocked: daily total ${"%.0f".format(dailyTotal)} mcg >= hard cap $maxDaily mcg")
            return
        }

        // Condition 8: glucagon pump ready
        val glucagonPump = activeGlucagonPump() ?: run {
            aapsLogger.debug(LTag.APS, "Glucagon blocked: no active glucagon pump")
            return
        }
        if (!glucagonPump.isGlucagonPumpReady()) {
            aapsLogger.debug(LTag.APS, "Glucagon blocked: pump not ready")
            return
        }

        // ---- Dose calculation ----
        val profile = profileFunction.getProfile() ?: return
        val basalRateUh = profile.getBasal()
        // iobData[0] is current IOB; index 0 = now in the array
        val currentIob = apsResult.iobData?.firstOrNull()?.iob ?: 0.0
        val iobRatio = if (basalRateUh > 0.0) currentIob / basalRateUh else 0.0
        val iobPenalty = if (iobRatio > 1.5) 0.5 else 1.0

        val carbsReq = apsResult.carbsReq
        val maxSingle = preferences.get(IntKey.GlucagonMaxSingleDoseMcg)
        val baseDose = carbsReq * 5.0 * formulation.doseFactor
        val clampedBase = baseDose.coerceIn(25.0, maxSingle.toDouble())
        val raw = clampedBase * iobPenalty
        // Round to nearest 25 mcg step, minimum 25 mcg
        val roundedDose = (Math.round(raw / 25.0) * 25.0).coerceAtLeast(25.0)
        // Trim to the daily headroom in whole 25 mcg steps so this dose cannot carry the total past the cap
        val dailyHeadroom = Math.floor((maxDaily - dailyTotal) / 25.0) * 25.0
        if (dailyHeadroom < 25.0) {
            aapsLogger.warn(LTag.APS, "Glucagon blocked: daily headroom ${"%.0f".format(maxDaily - dailyTotal)} mcg below the 25 mcg minimum dose")
            return
        }
        val finalDoseMcg = minOf(roundedDose, dailyHeadroom)

        // Warn if approaching daily cap
        if (dailyTotal + finalDoseMcg > 600) {
            aapsLogger.warn(LTag.APS, "Glucagon warning: daily total will exceed 600 mcg after this dose (total: ${"%.0f".format(dailyTotal + finalDoseMcg)} mcg)")
        }

        aapsLogger.debug(
            LTag.APS,
            "Glucagon dose: carbsReq=$carbsReq iobRatio=${"%.2f".format(iobRatio)} " +
                "iobPenalty=$iobPenalty formulation=$formulation baseDose=${"%.0f".format(baseDose)} finalDose=${"%.0f".format(finalDoseMcg)} mcg " +
                "gob=${"%.1f".format(currentGob)} dailyTotal=${"%.0f".format(dailyTotal)}"
        )

        val success = glucagonPump.deliverGlucagon(finalDoseMcg)
        rxBus.send(EventGlucagonDoseDelivered(doseMcg = finalDoseMcg, success = success))

        if (!success) {
            aapsLogger.error(LTag.APS, "Glucagon delivery failed for dose ${"%.0f".format(finalDoseMcg)} mcg")
        }
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    private fun activeGlucagonPump(): GlucagonPump? =
        activePlugin
            .getSpecificPluginsListByInterface(GlucagonPump::class.java)
            .firstOrNull { it.isEnabled() } as? GlucagonPump

    private fun lastGlucagonTimestamp(now: Long): Long {
        val since = now - T.hours(3).msecs()
        return persistenceLayer
            .getBolusesFromTimeToTime(since, now, ascending = false)
            .filter { it.isValid && it.type == BS.Type.GLUCAGON }
            .maxOfOrNull { it.timestamp }
            ?: 0L
    }

    private fun dailyGlucagonMcg(now: Long): Double {
        val since = now - T.hours(24).msecs()
        return persistenceLayer
            .getBolusesFromTimeToTime(since, now, ascending = true)
            .filter { it.isValid && it.type == BS.Type.GLUCAGON }
            .sumOf { it.amount * 1000.0 }   // mg → mcg
    }

    // -------------------------------------------------------------------------
    // Preference screen
    // -------------------------------------------------------------------------

    override fun addPreferenceScreen(preferenceManager: PreferenceManager, parent: PreferenceScreen, context: Context, requiredKey: String?) {
        if (requiredKey != null && requiredKey != "glucagon_settings") return
        val category = PreferenceCategory(context)
        parent.addPreference(category)
        category.apply {
            key = "glucagon_settings"
            title = rh.gs(R.string.glucagon_settings_category)
            initialExpandedChildrenCount = 0
            addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.GlucagonEnabled, title = R.string.glucagon_enabled_title, summary = R.string.glucagon_enabled_summary))
            addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.GlucagonMinBgMgdl, dialogMessage = R.string.glucagon_min_bg_summary, title = R.string.glucagon_min_bg_title))
            addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.GlucagonMaxSingleDoseMcg, dialogMessage = R.string.glucagon_max_single_dose_summary, title = R.string.glucagon_max_single_dose_title))
            addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.GlucagonMinIntervalMinutes, dialogMessage = R.string.glucagon_min_interval_summary, title = R.string.glucagon_min_interval_title))
            addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.GlucagonMaxDailyMcg, dialogMessage = R.string.glucagon_max_daily_summary, title = R.string.glucagon_max_daily_title))
            addPreference(
                AdaptiveListPreference(
                    ctx = context, stringKey = StringKey.GlucagonFormulation, title = R.string.glucagon_formulation_title,
                    summary = R.string.glucagon_formulation_summary,
                    entries = arrayOf<CharSequence>(rh.gs(R.string.glucagon_formulation_glucagen), rh.gs(R.string.glucagon_formulation_gvoke), rh.gs(R.string.glucagon_formulation_dasiglucagon)),
                    entryValues = GlucagonFormulation.entries.map<GlucagonFormulation, CharSequence> { it.name }.toTypedArray()
                )
            )
            addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.GlucagonMaxGobMcg, dialogMessage = R.string.glucagon_max_gob_summary, title = R.string.glucagon_max_gob_title))
        }
    }
}
