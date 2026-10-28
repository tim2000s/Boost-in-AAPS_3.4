package app.aaps.plugins.aps.glucagon

import android.content.Context
import androidx.preference.PreferenceCategory
import androidx.preference.PreferenceManager
import androidx.preference.PreferenceScreen
import app.aaps.core.data.model.GlucoseUnit
import app.aaps.core.data.model.TE
import app.aaps.core.data.plugin.PluginType
import app.aaps.core.data.time.T
import app.aaps.core.interfaces.aps.APS
import app.aaps.core.interfaces.aps.GlucoseStatus
import app.aaps.core.interfaces.constraints.Constraint
import app.aaps.core.interfaces.constraints.PluginConstraints
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import app.aaps.core.interfaces.notifications.Notification
import app.aaps.core.interfaces.plugin.ActivePlugin
import app.aaps.core.interfaces.plugin.PluginBase
import app.aaps.core.interfaces.plugin.PluginDescription
import app.aaps.core.interfaces.profile.Profile
import app.aaps.core.interfaces.profile.ProfileFunction
import app.aaps.core.interfaces.profile.ProfileUtil
import app.aaps.core.interfaces.pump.GlucagonPump
import app.aaps.core.interfaces.resources.ResourceHelper
import app.aaps.core.interfaces.rx.AapsSchedulers
import app.aaps.core.interfaces.rx.bus.RxBus
import app.aaps.core.interfaces.rx.events.EventAPSCalculationFinished
import app.aaps.core.interfaces.ui.UiInteraction
import app.aaps.core.interfaces.utils.DateUtil
import app.aaps.core.keys.BooleanKey
import app.aaps.core.keys.IntKey
import app.aaps.core.keys.StringKey
import app.aaps.core.keys.UnitDoubleKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.core.objects.glucagon.GlucagonFormulation
import app.aaps.core.objects.glucagon.GobCalculator
import app.aaps.core.validators.preferences.AdaptiveIntPreference
import app.aaps.core.validators.preferences.AdaptiveListPreference
import app.aaps.core.validators.preferences.AdaptiveSwitchPreference
import app.aaps.core.validators.preferences.AdaptiveUnitPreference
import app.aaps.plugins.aps.R
import io.reactivex.rxjava3.disposables.CompositeDisposable
import io.reactivex.rxjava3.kotlin.plusAssign
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Glucagon dosing algorithm plugin.
 *
 * Listens for [EventAPSCalculationFinished] and, when every trigger condition is met,
 * delivers a glucagon microdose via the active [GlucagonPump] implementation.
 *
 * Doses only while the loop is closed (or LGS), since open loop asks the user to confirm, and only
 * on a fresh glucose reading and APS result. As a [PluginConstraints] it tells the insulin loop
 * about glucagon: while glucagon is on board, SMBs are off and temp basals are capped at the
 * profile rate, so insulin is not added into a rise glucagon caused. Each cycle it also checks
 * whether the last dose is working and alarms when it is not.
 *
 * Safety: disabled by default (GlucagonEnabled = false); GLUCAGON records are excluded from IOB
 * and the last-bolus time; every condition must pass before a dose is issued; the dose never
 * exceeds the max single dose, the daily headroom or the reservoir.
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
    private val dateUtil: DateUtil,
    private val uiInteraction: UiInteraction,
    private val profileUtil: ProfileUtil
) : PluginBase(
    PluginDescription()
        .mainType(PluginType.GENERAL)
        .pluginIcon(app.aaps.core.ui.R.drawable.ic_generic_icon)
        .pluginName(R.string.glucagon_plugin_name)
        .shortName(R.string.glucagon_plugin_short_name)
        .description(R.string.glucagon_plugin_description)
        .preferencesId(PluginDescription.PREFERENCE_SCREEN),
    aapsLogger, rh
), PluginConstraints {

    private val disposable = CompositeDisposable()
    private val gobCalculator by lazy { GobCalculator(persistenceLayer, dateUtil) }

    private val formulation get() = GlucagonFormulation.fromKey(preferences.get(StringKey.GlucagonFormulation))

    override fun onStart() {
        super.onStart()
        disposable += rxBus
            .toObservable(EventAPSCalculationFinished::class.java)
            .observeOn(aapsSchedulers.io)
            .subscribe({ evaluateAndDose() }, { aapsLogger.error(LTag.APS, "Glucagon event error", it) })
    }

    /** Exposed for unit tests; not for production code. */
    internal fun evaluateAndDoseForTest() = evaluateAndDose()

    override fun onStop() {
        disposable.clear()
        super.onStop()
    }

    // -------------------------------------------------------------------------
    // Insulin loop constraints
    // -------------------------------------------------------------------------

    /** Glucagon is still acting: at least one minimum dose on board. */
    private fun glucagonActive(): Boolean =
        preferences.get(BooleanKey.GlucagonEnabled) &&
            runCatching { gobCalculator.currentGob(formulation) >= INSULIN_HOLD_GOB_MCG }.getOrDefault(false)

    override fun isSMBModeEnabled(value: Constraint<Boolean>): Constraint<Boolean> {
        if (glucagonActive()) value.set(false, rh.gs(R.string.glucagon_insulin_hold), this)
        return value
    }

    override fun applyBasalConstraints(absoluteRate: Constraint<Double>, profile: Profile): Constraint<Double> {
        if (glucagonActive()) absoluteRate.setIfSmaller(profile.getBasal(), rh.gs(R.string.glucagon_insulin_hold), this)
        return absoluteRate
    }

    override fun applyBasalPercentConstraints(percentRate: Constraint<Int>, profile: Profile): Constraint<Int> {
        if (glucagonActive()) percentRate.setIfSmaller(100, rh.gs(R.string.glucagon_insulin_hold), this)
        return percentRate
    }

    // -------------------------------------------------------------------------
    // Main evaluation, called on every APS calculation
    // -------------------------------------------------------------------------

    private fun evaluateAndDose() {
        // Condition 1: feature enabled
        if (!preferences.get(BooleanKey.GlucagonEnabled)) return

        // Open loop needs the user to confirm each action; suspended and disabled modes stop the loop
        val now = dateUtil.now()
        val mode = runCatching { persistenceLayer.getRunningModeActiveAt(now).mode }.getOrNull()
        if (mode?.isClosedLoopOrLgs() != true) {
            aapsLogger.debug(LTag.APS, "Glucagon blocked: running mode $mode")
            return
        }

        checkReservoir()

        val aps: APS = activePlugin.activeAPS
        val apsResult = aps.lastAPSResult ?: return
        val glucoseStatus = apsResult.glucoseStatus ?: return

        // A calculation started from the screen can reuse an old reading or result
        if (now - glucoseStatus.date > STALE_MS || now - apsResult.date > STALE_MS) {
            aapsLogger.debug(LTag.APS, "Glucagon blocked: glucose ${(now - glucoseStatus.date) / 60_000} min, result ${(now - apsResult.date) / 60_000} min old")
            return
        }

        checkEffectiveness(glucoseStatus, now)

        // Condition 2: carbsReq signals upcoming low
        if (!apsResult.isCarbsRequired) return

        // Condition 3: current BG <= threshold (stored in mg/dL, read in the user's units)
        val minBgMgdl = profileUtil.convertToMgdlDetect(preferences.get(UnitDoubleKey.GlucagonMinBg))
        if (glucoseStatus.glucose > minBgMgdl) return

        // Condition 4: BG not rising now; a falling short average alone would dose into a recovery
        if (glucoseStatus.delta > 0.0) return

        // Condition 5: current GOB < max
        val formulation = formulation
        val maxGob = preferences.get(IntKey.GlucagonMaxGobMcg)
        val currentGob = gobCalculator.currentGob(formulation)
        if (currentGob >= maxGob) {
            aapsLogger.debug(LTag.APS, "Glucagon blocked: GOB ${"%.1f".format(currentGob)} mcg >= max $maxGob mcg")
            return
        }

        // Condition 6: min interval since last dose
        val minInterval = preferences.get(IntKey.GlucagonMinIntervalMinutes)
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
        // From here a dose is wanted, so a pump that cannot give one raises the alarm
        val glucagonPump = activeGlucagonPump() ?: run {
            alarmUnavailable(rh.gs(R.string.glucagon_unavailable_no_pump))
            return
        }
        if (!glucagonPump.isGlucagonPumpReady()) {
            alarmUnavailable(rh.gs(R.string.glucagon_unavailable_not_ready))
            return
        }

        // ---- Dose calculation ----
        val profile = profileFunction.getProfile() ?: return
        val basalRateUh = profile.getBasal()
        // iobData[0] is current IOB; index 0 = now in the array
        val currentIob = apsResult.iobData?.firstOrNull()?.iob ?: 0.0
        val iobRatio = if (basalRateUh > 0.0) currentIob / basalRateUh else 0.0

        val carbsReq = apsResult.carbsReq
        val maxSingle = preferences.get(IntKey.GlucagonMaxSingleDoseMcg)
        val baseDose = carbsReq * 5.0 * formulation.doseFactor
        // Rounding first, then the cap in whole 25 mcg steps, so rounding cannot lift the dose over it
        val maxSingleStep = Math.floor(maxSingle / 25.0) * 25.0
        val roundedDose = (Math.round(baseDose / 25.0) * 25.0).coerceIn(25.0, maxSingleStep)
        // Trim to the daily headroom in whole 25 mcg steps so this dose cannot carry the total past the cap
        val dailyHeadroom = Math.floor((maxDaily - dailyTotal) / 25.0) * 25.0
        if (dailyHeadroom < 25.0) {
            aapsLogger.warn(LTag.APS, "Glucagon blocked: daily headroom ${"%.0f".format(maxDaily - dailyTotal)} mcg below the 25 mcg minimum dose")
            return
        }
        val reservoirStep = Math.floor(glucagonPump.glucagonReservoirMcg / 25.0) * 25.0
        val finalDoseMcg = minOf(roundedDose, dailyHeadroom, reservoirStep)
        if (finalDoseMcg < 25.0) {
            alarmUnavailable(rh.gs(R.string.glucagon_unavailable_reservoir, glucagonPump.glucagonReservoirMcg))
            return
        }

        aapsLogger.debug(
            LTag.APS,
            "Glucagon dose: carbsReq=$carbsReq iobRatio=${"%.2f".format(iobRatio)} " +
                "formulation=$formulation baseDose=${"%.0f".format(baseDose)} finalDose=${"%.0f".format(finalDoseMcg)} mcg " +
                "gob=${"%.1f".format(currentGob)} dailyTotal=${"%.0f".format(dailyTotal)}"
        )

        if (glucagonPump.deliverGlucagon(finalDoseMcg)) {
            uiInteraction.dismissNotification(Notification.GLUCAGON_UNAVAILABLE)
            recordForNightscout(now, finalDoseMcg, formulation)
            checkReservoir()
            // Above 1.5x basal IOB one dose has not been enough to stop a fall (n=1); warn rather than dose more
            if (iobRatio > INSUFFICIENT_IOB_RATIO)
                uiInteraction.addNotificationWithSound(
                    Notification.GLUCAGON_INSUFFICIENT, rh.gs(R.string.glucagon_insufficient, iobRatio), Notification.URGENT, app.aaps.core.ui.R.raw.alarm
                )
        } else {
            aapsLogger.error(LTag.APS, "Glucagon delivery failed for dose ${"%.0f".format(finalDoseMcg)} mcg")
            alarmUnavailable(rh.gs(R.string.glucagon_unavailable_delivery_failed, finalDoseMcg))
        }
    }

    /**
     * A dose has had time to act (onset 10 to 15 min) and glucose is still at or below where it was
     * given, and not rising: glucagon is not working (alcohol, depleted glycogen, high insulin).
     */
    private fun checkEffectiveness(glucoseStatus: GlucoseStatus, now: Long) {
        val lastDose = lastGlucagonTimestamp(now)
        if (lastDose == 0L) return
        val minutes = (now - lastDose) / 60_000.0
        if (minutes < EFFECT_CHECK_FROM_MIN || minutes > EFFECT_CHECK_TO_MIN) return
        val bgAtDose = persistenceLayer.getBgReadingsDataFromTimeToTime(lastDose - T.mins(10).msecs(), lastDose, false).firstOrNull()?.value ?: return
        if (glucoseStatus.glucose <= bgAtDose && glucoseStatus.delta <= 0.0)
            uiInteraction.addNotificationWithSound(
                Notification.GLUCAGON_NOT_WORKING,
                rh.gs(R.string.glucagon_not_working, minutes, profileUtil.fromMgdlToStringInUnits(bgAtDose), profileUtil.fromMgdlToStringInUnits(glucoseStatus.glucose)),
                Notification.URGENT, app.aaps.core.ui.R.raw.alarm
            )
        else if (glucoseStatus.glucose > bgAtDose) {
            uiInteraction.dismissNotification(Notification.GLUCAGON_NOT_WORKING)
            uiInteraction.dismissNotification(Notification.GLUCAGON_INSUFFICIENT)
        }
    }

    /** Glucagon is wanted and cannot be given. Re-raising the same id while it is shown does not re-sound it. */
    private fun alarmUnavailable(reason: String) {
        aapsLogger.warn(LTag.APS, "Glucagon blocked: $reason")
        uiInteraction.addNotificationWithSound(Notification.GLUCAGON_UNAVAILABLE, rh.gs(R.string.glucagon_unavailable, reason), Notification.URGENT, app.aaps.core.ui.R.raw.alarm)
    }

    /**
     * Warn while the reservoir holds less than one maximum single dose, and when it has been in the pump
     * longer than the formulation allows; clear each once it no longer applies.
     */
    private fun checkReservoir() {
        val pump = activeGlucagonPump() ?: return
        val left = pump.glucagonReservoirMcg
        if (left < preferences.get(IntKey.GlucagonMaxSingleDoseMcg))
            uiInteraction.addNotification(Notification.GLUCAGON_RESERVOIR_LOW, rh.gs(R.string.glucagon_reservoir_low, left), Notification.NORMAL)
        else
            uiInteraction.dismissNotification(Notification.GLUCAGON_RESERVOIR_LOW)

        val maxHours = formulation.maxReservoirHours
        val filledAt = pump.glucagonReservoirFilledAt
        val ageHours = (dateUtil.now() - filledAt) / 3_600_000.0
        if (maxHours != null && filledAt > 0 && ageHours > maxHours)
            uiInteraction.addNotification(Notification.GLUCAGON_RESERVOIR_OLD, rh.gs(R.string.glucagon_reservoir_old, ageHours, maxHours), Notification.NORMAL)
        else
            uiInteraction.dismissNotification(Notification.GLUCAGON_RESERVOIR_OLD)
    }

    /**
     * Glucagon never leaves the device as a bolus. A note carries it to Nightscout so followers see it
     * and the analysis extractor can find it ("Glucagon <n> mcg (<formulation>)").
     */
    private fun recordForNightscout(now: Long, doseMcg: Double, formulation: GlucagonFormulation) {
        val note = "Glucagon ${doseMcg.toInt()} mcg (${formulation.displayName})"
        runCatching {
            persistenceLayer.insertOrUpdateTherapyEvent(TE(timestamp = now, type = TE.Type.NOTE, note = note, enteredBy = "AAPS", glucoseUnit = GlucoseUnit.MGDL)).blockingGet()
        }.onFailure { aapsLogger.error(LTag.APS, "Glucagon note not stored", it) }
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
            .getGlucagonDosesFromTime(since, includeInvalid = false)
            .blockingGet()
            .maxOfOrNull { it.timestamp }
            ?: 0L
    }

    private fun dailyGlucagonMcg(now: Long): Double {
        val since = now - T.hours(24).msecs()
        return persistenceLayer
            .getGlucagonDosesFromTime(since, includeInvalid = false)
            .blockingGet()
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
            addPreference(AdaptiveUnitPreference(ctx = context, unitKey = UnitDoubleKey.GlucagonMinBg, dialogMessage = R.string.glucagon_min_bg_summary, title = R.string.glucagon_min_bg_title))
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

    private companion object {
        const val STALE_MS = 7 * 60_000L                  // more than one missed 5-minute reading
        const val INSULIN_HOLD_GOB_MCG = 25.0             // one minimum dose
        const val INSUFFICIENT_IOB_RATIO = 1.5            // diabettech.com Glucagon & Me part 2
        const val EFFECT_CHECK_FROM_MIN = 20.0            // onset 10 to 15 min (GlucaGen label; Laugesen 2022 +20 mg/dL by 15 min)
        const val EFFECT_CHECK_TO_MIN = 60.0
    }
}
