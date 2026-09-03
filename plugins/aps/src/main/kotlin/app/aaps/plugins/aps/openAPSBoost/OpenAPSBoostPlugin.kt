package app.aaps.plugins.aps.openAPSBoost

import android.content.Context
import android.content.Intent
import androidx.core.net.toUri
import androidx.preference.PreferenceCategory
import androidx.preference.PreferenceGroup
import androidx.preference.PreferenceFragmentCompat
import androidx.preference.PreferenceManager
import androidx.preference.PreferenceScreen
import androidx.preference.SwitchPreference
import app.aaps.core.data.aps.SMBDefaults
import app.aaps.core.data.configuration.Constants
import app.aaps.core.data.model.BS
import app.aaps.core.data.model.GlucoseUnit
import app.aaps.core.data.model.TT
import app.aaps.core.data.plugin.PluginType
import app.aaps.core.data.time.T
import app.aaps.core.data.ue.Action
import app.aaps.core.data.ue.Sources
import app.aaps.core.data.ue.ValueWithUnit
import app.aaps.core.interfaces.aps.APS
import app.aaps.core.interfaces.aps.APSResult
import app.aaps.core.interfaces.aps.AutosensResult
import app.aaps.core.interfaces.aps.CurrentTemp
import app.aaps.core.interfaces.aps.OapsProfileBoost
import app.aaps.core.interfaces.bgQualityCheck.BgQualityCheck
import app.aaps.core.interfaces.configuration.Config
import app.aaps.core.interfaces.constraints.Constraint
import app.aaps.core.interfaces.constraints.ConstraintsChecker
import app.aaps.core.interfaces.constraints.PluginConstraints
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.db.ProcessedTbrEbData
import app.aaps.plugins.aps.openAPSSMB.GlucoseStatusCalculatorSMB
import app.aaps.core.interfaces.iob.IobCobCalculator
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import app.aaps.core.interfaces.notifications.Notification
import app.aaps.core.interfaces.plugin.ActivePlugin
import app.aaps.core.interfaces.plugin.PluginBase
import app.aaps.core.interfaces.plugin.PluginDescription
import app.aaps.core.interfaces.profile.Profile
import app.aaps.core.interfaces.profile.ProfileFunction
import app.aaps.core.interfaces.profile.ProfileUtil
import app.aaps.core.interfaces.profiling.Profiler
import app.aaps.core.interfaces.resources.ResourceHelper
import app.aaps.core.interfaces.rx.AapsSchedulers
import app.aaps.core.interfaces.rx.bus.RxBus
import app.aaps.core.interfaces.rx.events.EventAPSCalculationFinished
import app.aaps.core.interfaces.rx.events.EventCalibrationDetected
import io.reactivex.rxjava3.disposables.CompositeDisposable
import io.reactivex.rxjava3.kotlin.plusAssign
import app.aaps.core.interfaces.stats.TddCalculator
import app.aaps.core.interfaces.ui.UiInteraction
import app.aaps.core.interfaces.utils.DateUtil
import app.aaps.core.interfaces.utils.HardLimits
import app.aaps.core.interfaces.utils.Round
import app.aaps.core.keys.BooleanKey
import app.aaps.core.keys.DoubleKey
import app.aaps.core.keys.IntKey
import app.aaps.core.keys.IntentKey
import app.aaps.core.keys.StringKey
import app.aaps.core.keys.UnitDoubleKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.plugins.aps.getBoostDosing
import app.aaps.core.objects.constraints.ConstraintObject
import app.aaps.core.objects.extensions.convertedToAbsolute
import app.aaps.core.objects.extensions.getPassedDurationToTimeInMinutes
import app.aaps.core.objects.extensions.plannedRemainingMinutes
import app.aaps.core.objects.extensions.put
import app.aaps.core.objects.extensions.store
import app.aaps.core.objects.extensions.target
import app.aaps.core.objects.profile.ProfileSealed
import app.aaps.core.utils.MidnightUtils
import app.aaps.core.validators.preferences.AdaptiveDoublePreference
import app.aaps.core.validators.preferences.AdaptiveIntPreference
import app.aaps.core.validators.preferences.AdaptiveIntentPreference
import app.aaps.core.validators.preferences.AdaptiveStringPreference
import app.aaps.core.validators.preferences.AdaptiveSwitchPreference
import app.aaps.core.validators.preferences.AdaptiveUnitPreference
import app.aaps.plugins.aps.OpenAPSFragment
import app.aaps.plugins.aps.R
import app.aaps.plugins.aps.events.EventOpenAPSUpdateGui
import app.aaps.plugins.aps.events.EventResetOpenAPSGui
import org.json.JSONObject
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Provider
import javax.inject.Singleton
import kotlin.math.abs
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import app.aaps.plugins.aps.openAPSBoostV5.MealHypothesis

/**
 * 2026-07-30 implausible-TDD guard for dynamic ISF. Minimum blended TDD, as a fraction of the TDD the
 * user's own profile ISF implies via the 1800 rule (profileISF ~= 1800/TDD). Below this the insulin
 * history is treated as incomplete and dynamic ISF is NOT derived — the profile ISF is used instead.
 *
 * 0.35 is deliberately liberal. The fallback direction is safe (profileSens is the user's configured
 * value), so a false positive costs one cycle of dynamic responsiveness and nothing else, whereas a
 * false NEGATIVE paralyses dosing: the field case that motivated this had TDD at 0.22 of implied and
 * ran ~88x profile ISF, delivering nothing for 3.5 h. Every activation is logged (LTag.APS) and lands
 * in consoleError, so the true false-positive rate is auditable across the cohort before tightening.
 */
private const val DYNISF_MIN_TDD_FRACTION = 0.35

/**
 * True when [tdd] is too low to be believed given what [profileSens] implies, so dynamic ISF must NOT
 * be derived from it. Extracted as a pure function so the guard is unit-testable independently of the
 * plugin's DI graph. Returns false when [profileSens] is non-positive (no reference to judge against —
 * fail OPEN there, because the existing `tdd > 0` check still applies downstream).
 */
internal fun tddImplausibleForProfile(tdd: Double, profileSens: Double): Boolean {
    if (profileSens <= 0.0) return false
    val impliedTdd = 1800.0 / profileSens
    return tdd < impliedTdd * DYNISF_MIN_TDD_FRACTION
}

// @Singleton MUST stay adjacent to this declaration. 2026-07-30..08-04: a KDoc, a constant and a
// helper function were inserted between the two, which silently moved the annotation onto the
// constant and left the engine UNSCOPED. OpenAPSBoostV5Plugin injects it and reads lastAPSResult
// back through the same reference, so every cycle built its result on one instance and the loop
// read null from another — "NO APS SELECTED OR PROVIDED RESULT", nothing enacted, for five days.
// Verified in the generated component: the binding had no DoubleCheck wrapper.
@Singleton
open class OpenAPSBoostPlugin @Inject constructor(
    aapsLogger: AAPSLogger,
    private val aapsSchedulers: AapsSchedulers,
    private val rxBus: RxBus,
    private val constraintsChecker: ConstraintsChecker,
    rh: ResourceHelper,
    private val profileFunction: ProfileFunction,
    private val profileUtil: ProfileUtil,
    private val config: Config,
    private val activePlugin: ActivePlugin,
    private val iobCobCalculator: IobCobCalculator,
    private val hardLimits: HardLimits,
    private val preferences: Preferences,
    protected val dateUtil: DateUtil,
    private val processedTbrEbData: ProcessedTbrEbData,
    private val persistenceLayer: PersistenceLayer,
    private val glucoseStatusCalculatorSMB: GlucoseStatusCalculatorSMB,
    private val bgQualityCheck: BgQualityCheck,
    private val uiInteraction: UiInteraction,
    private val tddCalculator: TddCalculator,
    private val determineBasalBoost: DetermineBasalBoost,
    // Layer A ML retrofit — both models are @Singleton, lazy-loaded from APK
    // assets on first inference. Safe to inject unconditionally; absence of the
    // asset is handled inside the model classes (returns null score).
    private val boostRiskModel: BoostRiskModel,
    private val boostMealModel: BoostMealModel,
    // ISF shadow — V4.4.2-style EMA(τ=3h) TDD-anchored sensitivity ratio computed
    // in parallel with V1's instantaneous ratio. Singleton with SharedPreferences-backed
    // EMA state, so the ratio survives plugin restarts.
    private val boostIsfShadow: BoostIsfShadow,
    private val fallConsequenceShadow: FallConsequenceShadow,
    private val profiler: Profiler,
    private val apsResultProvider: Provider<APSResult>,
    // V5 silent shadow — V1 hands the cycle's RT + inputs to V5 after determine_basal
    // returns so V5 can compute a parallel decision against the same data. V5 itself
    // is hidden from the plugin list and not user-selectable; this callback is the
    // only way V5 sees a cycle's data. Provider<> avoids a hard DI cycle.
    private val boostV5Plugin: Provider<app.aaps.plugins.aps.openAPSBoostV5.OpenAPSBoostV5Plugin>,
    // Health Connect HR ingest — bridges Garmin Connect / Wear OS HR streams via Android
    // Health Connect into AAPS's local HR table. Pulled each Boost cycle (throttled internally).
    private val healthConnectHrIngest: HealthConnectHrIngest,
    // Activity-load SHADOW (2026-06-16) — HC steps → single-source daily totals for the step baseline.
    private val healthConnectStepsIngest: HealthConnectStepsIngest
) : PluginBase(
    PluginDescription()
        .mainType(PluginType.APS)
        .fragmentClass(OpenAPSFragment::class.java.name)
        .pluginIcon(app.aaps.core.ui.R.drawable.ic_generic_icon)
        .pluginName(R.string.openaps_boost)
        .shortName(R.string.boost_shortname)
        .preferencesId(PluginDescription.PREFERENCE_SCREEN)
        .preferencesVisibleInSimpleMode(false)
        .showInList { config.APS }
        .description(R.string.description_boost),
    aapsLogger, rh
), APS, PluginConstraints {


    /** The volume-weighted dose shadow, held on preferences as the other shadows are. It logs
     *  an alternative blend and reaches nothing on the dose path. */
    private val vwaTddShadow by lazy {
        BoostVwaTddShadow(
            loadState = { preferences.getBoostDosing(StringKey.ApsBoostVwaTddShadowState) },
            saveState = { preferences.put(StringKey.ApsBoostVwaTddShadowState, it) },
            logInfo = { aapsLogger.debug(LTag.APS, it) },
        )
    }

    companion object {
        /**
         * Picks the sensitivity ratio that scales basal / targets / CR in determine_basal.
         * TDD-DynISF and traditional oref autosens are alternative adaptation mechanisms — never both:
         *  - useTdd ON  → the TDD model (isfResultRatio = 24H/7D) owns sensitivity.
         *  - useTdd OFF + autosensWhenNoTdd → traditional oref autosens drives it (the fix).
         *  - useTdd OFF + !autosensWhenNoTdd → legacy: the DynISF-curve ratio (in isfResultRatio).
         * variable_sens (the curve ISF) is a separate lever and is unaffected by this choice.
         */
        internal fun selectSensitivityRatio(
            useTdd: Boolean,
            autosensWhenNoTdd: Boolean,
            isfResultRatio: Double,
            orefAutosensRatio: Double
        ): Double = when {
            useTdd            -> isfResultRatio
            autosensWhenNoTdd -> orefAutosensRatio
            else              -> isfResultRatio
        }

        /** Outcome of the V6-override dose caps: the dose to deliver plus the reason-line breadcrumb ("" when uncapped). */
        internal data class V6OverrideCaps(val dose: Double, val capNote: String)

        /**
         * V6-override dose caps (pure — unit-tested directly):
         *  - non-meal-state cap (2026-07-02): in IDLE/OBSERVING/RECOVERING V6 never out-doses V1;
         *  - post-rescue meal-state cap (2026-07-04): inside the post-rescue window
         *    (recentLowBG45Min < [DetermineBasalBoost.POST_RESCUE_LOW_THRESHOLD_MGDL]) the meal-state
         *    exemption is suppressed, so CONFIRMED/COMMITTED are ALSO capped at V1's would-dose.
         *
         * Incident 2026-07-03 19:47 BST: severe hypo (nadir 40) → unannounced rescue carbs → violent
         * rebound. V6 CONFIRMED at BG 119 delivered 2.7U while V1's 45-min post-rescue tier guard had
         * restrained the base engine to 1.05U — the meal-state exemption discarded that restraint. BG
         * then ran 181 → nadir 81 with zero margin, and the 2.7U tripped the 2.5U cumulative cap,
         * silencing V6 for the following hour.
         *
         * DB backtest (2026-07-04): 20.4% of meal-state cycles are post-rescue; 27% of the insulin this
         * cap removes sits directly ahead of a second low < 70 (vs 14-19% for every other lever
         * evaluated). Cost side: 10% genuine post-hypo meals, median 0.15U under-delivery, zero
         * double-dips. Verdict SHIP.
         *
         * WHY inherit V1 (alignment is load-bearing): the 75 mg/dL / 45-min window is deliberately the
         * SAME constant + source value as V1's post-rescue tier guard (DetermineBasalBoost Fix A v2),
         * so whenever this cap binds, v1WouldDose is by construction the hypo-restrained dose — the cap
         * inherits V1's restraint instead of inventing a second, divergent notion of "post-rescue".
         */
        internal fun applyV6OverrideCaps(
            inMealState: Boolean,
            inPostRescueWindow: Boolean,
            v5FinalDose: Double,
            v1WouldDose: Double,
            recentLowBG45Min: Double
        ): V6OverrideCaps {
            val dose = if (inMealState && !inPostRescueWindow) v5FinalDose else minOf(v5FinalDose, v1WouldDose)
            val capNote = when {
                dose >= v5FinalDose -> ""
                inMealState         -> ", post-rescue capped from ${Round.roundTo(v5FinalDose, 0.001)}U to V1's ${Round.roundTo(v1WouldDose, 0.001)}U (45-min low ${Round.roundTo(recentLowBG45Min, 1.0)})"
                else                -> ", non-meal-capped from ${Round.roundTo(v5FinalDose, 0.001)}U"
            }
            return V6OverrideCaps(dose, capNote)
        }
    }

    // last values
    override var lastAPSRun: Long = 0
    override val algorithm = APSResult.Algorithm.BOOST
    override var lastAPSResult: APSResult? = null

    // ---- Calibration SMB block ----
    private val disposable = CompositeDisposable()
    @Volatile private var calibrationBlockedUntil: Long = 0L

    override fun onStart() {
        super.onStart()
        disposable += rxBus
            .toObservable(EventCalibrationDetected::class.java)
            .observeOn(aapsSchedulers.io)
            .subscribe({
                calibrationBlockedUntil = dateUtil.now() + 15 * 60_000L
                aapsLogger.debug(LTag.APS, "Boost SMB block set: calibration detected, blocked until ${dateUtil.dateAndTimeString(calibrationBlockedUntil)}")
            }, { aapsLogger.error(LTag.APS, "EventCalibrationDetected error", it) })
    }

    override fun onStop() {
        disposable.clear()
        super.onStop()
    }

    // ---- Boost-specific preference getters ----

    // Dynamic ISF
    // NOTE: all these Boost getters use preferences.getBoostDosing(...) (not .get) so Simple Mode
    // does NOT mask the user's / auto-config's stored dosing settings to factory defaults. The keys
    // keep defaultedBySM = true (they stay HIDDEN in Simple Mode); only the doser's read is unmasked.
    // See BoostDosingPreferences.kt + 2026-07_maxiob_consistency_REPORT.md.
    private val dynIsfNormalTarget; get() = profileUtil.convertToMgdlDetect(preferences.getBoostDosing(UnitDoubleKey.ApsBoostDynIsfNormalTarget, profileUtil))
    private val dynIsfVelocity; get() = preferences.getBoostDosing(DoubleKey.ApsBoostDynIsfVelocity) / 100.0
    private val dynIsfBgCap; get() = profileUtil.convertToMgdlDetect(preferences.getBoostDosing(UnitDoubleKey.ApsBoostDynIsfBgCap, profileUtil))

    // Boost SMB
    private val boostBolus; get() = preferences.getBoostDosing(DoubleKey.ApsBoostBolus)
    private val boostMaxIob; get() = preferences.getBoostDosing(DoubleKey.ApsBoostMaxIob)
    private val boostInsulinReqPct; get() = preferences.getBoostDosing(DoubleKey.ApsBoostInsulinReqPct)
    private val boostScale; get() = preferences.getBoostDosing(DoubleKey.ApsBoostScale)
    private val boostPercentScale; get() = preferences.getBoostDosing(DoubleKey.ApsBoostPercentScale)
    private val enableBoostPercentScale; get() = preferences.getBoostDosing(BooleanKey.ApsBoostEnablePercentScale)
    private val enableCircadianIsf; get() = preferences.getBoostDosing(BooleanKey.ApsBoostEnableCircadianIsf)
    private val allowBoostWithHighTt; get() = preferences.getBoostDosing(BooleanKey.ApsBoostAllowWithHighTt)
    // ApsBoostV5ActiveDosing retired 2026-06-15: V5 is now a selectable plugin (Boost V5), so the
    // engine's V5 override is gated by runEngine(v5Active=…) — set true only when the V5 plugin
    // drives the engine. The key is kept in BooleanKey for back-compat but no longer read here.

    // Boost time window retired 2026-07-02 — boostActive now derives from the night-mode period
    // (isInNightSleepPeriod). ApsBoostStartTime/EndTime are no longer read.
    private val sleepInHours; get() = preferences.getBoostDosing(DoubleKey.ApsBoostSleepInHours)

    // Step counting thresholds
    private val inactivitySteps; get() = preferences.getBoostDosing(IntKey.ApsBoostInactivitySteps)
    private val inactivityPct; get() = preferences.getBoostDosing(DoubleKey.ApsBoostInactivityPct)
    private val sleepInSteps; get() = preferences.getBoostDosing(IntKey.ApsBoostSleepInSteps)
    private val activitySteps5; get() = preferences.getBoostDosing(IntKey.ApsBoostActivitySteps5)
    private val activitySteps15; get() = preferences.getBoostDosing(IntKey.ApsBoostActivitySteps15)
    private val activitySteps30; get() = preferences.getBoostDosing(IntKey.ApsBoostActivitySteps30)
    private val activitySteps60; get() = preferences.getBoostDosing(IntKey.ApsBoostActivitySteps60)
    private val activityPct; get() = preferences.getBoostDosing(DoubleKey.ApsBoostActivityPct)

    // Heart rate integration
    private val hrIntegrationEnabled; get() = preferences.getBoostDosing(BooleanKey.ApsBoostHrIntegrationEnabled)
    private val hrMaxBpm; get() = preferences.getBoostDosing(IntKey.ApsBoostHrMaxBpm)
    private val hrRestingBpm; get() = preferences.getBoostDosing(IntKey.ApsBoostHrRestingBpm)
    private val hrWindowMinutes; get() = preferences.getBoostDosing(IntKey.ApsBoostHrWindowMinutes)
    private val hrStressDetection; get() = preferences.getBoostDosing(BooleanKey.ApsBoostHrStressDetection)

    // Post-exercise recovery
    private val postExerciseRecoveryEnabled; get() = preferences.getBoostDosing(BooleanKey.ApsBoostPostExerciseRecoveryEnabled)
    private val postExerciseRecoveryHours; get() = preferences.getBoostDosing(DoubleKey.ApsBoostPostExerciseRecoveryHours)
    private val postExerciseRecoveryTarget; get() = profileUtil.convertToMgdlDetect(preferences.getBoostDosing(UnitDoubleKey.ApsBoostPostExerciseRecoveryTarget, profileUtil))
    private val postExerciseRecoveryScale; get() = preferences.getBoostDosing(DoubleKey.ApsBoostPostExerciseRecoveryScale)
    private val postExerciseMinDuration; get() = preferences.getBoostDosing(IntKey.ApsBoostPostExerciseMinDuration)

    // ---- Feed-health edge detection (F4/F6, 2026-07-07) ----
    // HR: fresh→dark transitions + one waking-hours notification per dark episode.
    private val hrFeedDarkTracker = HrFeedDarkTracker()
    // Steps: boostSteps_feed transitions, reason-line only (no notification).
    @Volatile private var lastStepsFeed: String? = null

    // ---- V7 shadow (2026-07) ----
    // Read-only per-cycle V7 would-dose instrument (see openAPSBoostV7/V7_SHADOW.md). Constructed
    // lazily with lambda seams (no DI module change); persistence = StringKey JSON blob, the
    // V5StateStore idiom. Invoked at the seam below runShadow, wrapped in runCatching there.
    private val v7Shadow by lazy {
        app.aaps.plugins.aps.openAPSBoostV7.V7Shadow(
            loadState = { preferences.get(StringKey.ApsBoostV7ResidualPools) },
            saveState = { preferences.put(StringKey.ApsBoostV7ResidualPools, it) },
            logInfo = { msg -> aapsLogger.info(LTag.APS, msg) },
            logError = { msg, t -> aapsLogger.error(LTag.APS, msg, t) },
        )
    }

    // KAIROS Twin — physiological EnKF forecaster, held in memory across cycles (re-converges in
    // ~30 min after a restart; fail-safe). READ-ONLY telemetry; never touches the dose path. Uses the
    // validated default per-person parameters. (2026-07-18)
    private val twinShadow by lazy { app.aaps.plugins.aps.openAPSBoostTwin.TwinShadow() }
    // Anticipatory back-out controller SHADOW (2026-07-20): retractable-anticipation state machine, held
    // in memory across cycles. READ-ONLY — logs antBackout=...; delivers nothing. See BACKOUT_CONTROLLER_SPEC.
    private val backoutShadow by lazy { app.aaps.plugins.aps.openAPSBoostTwin.AnticipationBackoutShadow() }
    private val consequenceShadow by lazy { app.aaps.plugins.aps.openAPSBoostV5.ConsequencePriorShadow() }
    private val confirmTranche by lazy { app.aaps.plugins.aps.openAPSBoostV5.ConfirmTrancheController() }
    // Per-user ANTICIPATION shadow (2026-07-27): refits per-user exercise/meal onset-hazard models
    // offline, predicts p(onset) at 45-min lead, runs the two retractable arms in shadow. READ-ONLY —
    // logs anticip=...; delivers nothing. Onset history persists as a StringKey JSON blob (V7 idiom).
    // See openAPSBoostTwin/ANTICIPATION_ARCHITECTURE_SPEC.md (Phase 1+2). Runs in the shared engine, so
    // it covers plain Boost, V5/V6, and the V7-shadow line identically.
    private val anticipShadow by lazy {
        app.aaps.plugins.aps.openAPSBoostTwin.AnticipationShadow(
            loadState = { preferences.get(StringKey.ApsBoostAnticipHistory) },
            saveState = { preferences.put(StringKey.ApsBoostAnticipHistory, it) },
            logError = { msg, t -> aapsLogger.error(LTag.APS, msg, t) },
            weekMinuteOf = { ms ->
                val z = java.time.Instant.ofEpochMilli(ms).atZone(java.time.ZoneId.systemDefault())
                app.aaps.plugins.aps.openAPSBoostTwin.AnticipationHabitModel.weekMinute(
                    z.dayOfWeek.value - 1, z.hour * 60 + z.minute
                )
            },
        )
    }

    // ---- Post-exercise recovery state ----
    @Volatile private var recoveryWindowEnd: Long = 0L
    @Volatile private var wasExerciseActive: Boolean = false
    @Volatile private var exerciseStartTime: Long = 0L
    @Volatile private var lastExerciseStateAtTransition: String = "ACTIVE"
    @Volatile private var activeRecoveryScale: Double = 0.5
    @Volatile private var activeRecoveryTargetOffset: Double = 0.0

    // ---- Lifecycle ----

    override fun specialEnableCondition(): Boolean {
        return try {
            activePlugin.activePump.pumpDescription.isTempBasalCapable
        } catch (_: Exception) {
            true
        }
    }

    override fun specialShowInListCondition(): Boolean {
        return try {
            activePlugin.activePump.pumpDescription.isTempBasalCapable
        } catch (_: Exception) {
            true
        }
    }

    /**
     * True when THIS engine should run/constrain: either plain "Boost" (V1) is the selected APS,
     * OR the selectable "Boost V5" plugin is (it delegates to [runEngine]). Without this, when V5
     * is the active APS, V1's own isEnabled() is false → runEngine's guard would post "disabled"
     * and the maxIOB/maxBasal constraint methods would silently stop applying. (2026-06-15.)
     */
    private fun engineActive(): Boolean =
        isEnabled() || runCatching { boostV5Plugin.get().isEnabled() }.getOrDefault(false)

    override fun supportsDynamicIsf() = true

    override fun getIsfMgdl(profile: Profile, caller: String): Double? {
        // Boost computes ISF dynamically inside determine_basal via getIsfByProfile()
        // Return null to fall back to profile ISF for external callers
        return null
    }

    override fun getAverageIsfMgdl(timestamp: Long, caller: String): Double? = null

    override fun getSensitivityOverviewString(): String? = null

    override fun preprocessPreferences(preferenceFragment: PreferenceFragmentCompat) {
        super.preprocessPreferences(preferenceFragment)
        val smbAlwaysEnabled = preferences.get(BooleanKey.ApsUseSmbAlways)
        val allowAllBgSources = true // Boost: always allow all BG sources (forced on; user toggle removed)
        val advancedFiltering = allowAllBgSources || activePlugin.activeBgSource.advancedFilteringSupported()
        preferenceFragment.findPreference<SwitchPreference>(BooleanKey.ApsUseSmbWithCob.key)?.isVisible = !smbAlwaysEnabled || !advancedFiltering
        preferenceFragment.findPreference<SwitchPreference>(BooleanKey.ApsUseSmbWithLowTt.key)?.isVisible = !smbAlwaysEnabled || !advancedFiltering
        preferenceFragment.findPreference<SwitchPreference>(BooleanKey.ApsUseSmbAfterCarbs.key)?.isVisible = !smbAlwaysEnabled || !advancedFiltering
    }

    // ---- ISF Pre-calculation ----
    // Mirrors the IsfCalculatorImpl from 3.2, computing sensNormalTarget and variable_sens
    // These are then passed to DetermineBasalBoost which uses them in getIsfByProfile()

    data class BoostIsfResult(
        val sensNormalTarget: Double,
        val variableSens: Double,
        val bgCapped: Double,
        val insulinDivisor: Int,
        val dynIsfVelocity: Double,
        val ratio: Double,
        val tdd: Double,
        val isfDebug: String = "",
        // ISF shadow — V4.4.2-style EMA(τ=3h) sensitivity ratio computed in parallel for
        // comparison. Null when TDD inputs unavailable. Does not influence dosing.
        val tddSensShadow: BoostIsfShadow.TddSensShadowResult? = null,
        val vwaTddShadow: BoostVwaTddShadow.Result? = null
    )

    private fun calculateBoostIsf(
        profileSens: Double,
        profilePercent: Int,
        targetBg: Double,
        insulinDivisor: Int,
        glucoseValue: Double,
        isTempTarget: Boolean
    ): BoostIsfResult {
        val autosensMax = preferences.get(DoubleKey.AutosensMax)
        val autosensMin = preferences.get(DoubleKey.AutosensMin)
        val velocity = dynIsfVelocity
        val bgCap = dynIsfBgCap
        val bgNormalTarget = dynIsfNormalTarget
        val highTtRaisesSens = preferences.get(BooleanKey.ApsAutoIsfHighTtRaisesSens)
        val lowTtLowersSens = preferences.get(BooleanKey.ApsAutoIsfLowTtLowersSens)
        val halfBasalTarget = SMBDefaults.half_basal_exercise_target

        val globalScale = 100.0 / profilePercent.toDouble()

        var sensNormalTarget = profileSens
        var ratio = 1.0
        // ISF shadow accumulator — populated when V4.4.2-style EMA ratio is computed below.
        var isfShadowResult: BoostIsfShadow.TddSensShadowResult? = null
        var vwaShadowResult: BoostVwaTddShadow.Result? = null
        var tdd = 0.0
        val bgCurrent = if (glucoseValue > bgCap) bgCap + ((glucoseValue - bgCap) / 3.0) else glucoseValue

        val debug = StringBuilder()

        // TDD-based ISF calculation
        val useTdd = preferences.getBoostDosing(BooleanKey.ApsBoostUseTdd)
        val adjustSens = preferences.getBoostDosing(BooleanKey.ApsBoostAdjustSensitivity)

        if (useTdd) {
            // Fetch all TDD components — use allowMissingDays=true so partial data still works
            val tdd7D = tddCalculator.averageTDD(tddCalculator.calculate(7, allowMissingDays = true))?.data?.totalAmount
            val tdd1D = tddCalculator.averageTDD(tddCalculator.calculate(1, allowMissingDays = true))?.data?.totalAmount
            val tddLast24H = tddCalculator.calculateDaily(-24, 0)?.totalAmount
            val tddLast4H = tddCalculator.calculateDaily(-4, 0)?.totalAmount
            val tddLast8to4H = tddCalculator.calculateDaily(-8, -4)?.totalAmount

            debug.append("TDD data: 7D=${tdd7D?.let { Round.roundTo(it, 0.1) } ?: "null"}")
            debug.append(" | 1D=${tdd1D?.let { Round.roundTo(it, 0.1) } ?: "null"}")
            debug.append(" | 24H=${tddLast24H?.let { Round.roundTo(it, 0.1) } ?: "null"}")
            debug.append(" | 4H=${tddLast4H?.let { Round.roundTo(it, 0.1) } ?: "null"}")
            debug.append(" | 8-4H=${tddLast8to4H?.let { Round.roundTo(it, 0.1) } ?: "null"}")

            // Require ALL critical components — same safety gate as standard DynISF
            if (tdd7D != null && tdd1D != null && tddLast24H != null && tddLast4H != null && tddLast8to4H != null && tdd7D > 0) {
                val tddWeightedFromLast8H = ((1.4 * tddLast4H) + (0.6 * tddLast8to4H)) * 3
                debug.append("\nWeighted8H=${Round.roundTo(tddWeightedFromLast8H, 0.1)} (4H×1.4 + 8-4H×0.6)×3")

                if (tddWeightedFromLast8H < (0.75 * tdd7D)) {
                    // Recent insulin usage significantly below 7D average —
                    // pull the 7D average down toward recent reality before blending
                    val adjusted7D = tddWeightedFromLast8H + ((tddWeightedFromLast8H / tdd7D) * (tdd7D - tddWeightedFromLast8H))
                    tdd = (adjusted7D * 0.34) + (tdd1D * 0.33) + (tddWeightedFromLast8H * 0.33)
                    debug.append("\nW8H < 75% of 7D → adjusted7D=${Round.roundTo(adjusted7D, 0.1)} (7D ${Round.roundTo(tdd7D, 0.1)} pulled toward W8H)")
                } else {
                    // Standard blend
                    tdd = (tddWeightedFromLast8H * 0.33) + (tdd7D * 0.34) + (tdd1D * 0.33)
                    debug.append("\nStandard blend (W8H×.33 + 7D×.34 + 1D×.33)")
                }
                debug.append("\nBlended TDD=${Round.roundTo(tdd, 0.1)}")

                // Adjustment factor from Boost DynISF preferences (default 100%)
                val dynIsfAdjust = preferences.get(IntKey.ApsBoostDynIsfAdjustmentFactor).toDouble().coerceIn(1.0, 300.0)
                tdd *= dynIsfAdjust / 100.0
                debug.append("\nFinal TDD=${Round.roundTo(tdd, 0.1)} (adj factor ${dynIsfAdjust.toInt()}%)")

                // Safety: TDD must be positive and produce a sane ISF
                val logTerm = ln((bgNormalTarget / insulinDivisor) + 1.0)
                // 2026-07-30 IMPLAUSIBLE-TDD GUARD. The old condition was `tdd > 0` only, and the
                // comment above claimed it ensured "a sane ISF" — it did not. A TDD of 0.1 U/day
                // passes, and 1800/(tdd × logTerm) then explodes. Observed in the field on a
                // cross-fork migration: a fresh AAPS database reported TDD 3.1–4.1 U/day against a
                // true ~20, dynamic ISF reached 5550–8944 mg/dL/U against a profile ISF of 100
                // (~88×), insulinReq computed at or below zero, and the loop delivered NOTHING for
                // 3.5 h while BG climbed to 276 — 19 consecutive zero temp basals, no lows, no alarm.
                //
                // The floor is anchored on the profile's OWN implied TDD via the 1800 rule
                // (profileISF ≈ 1800/TDD), so it is self-scaling per user and needs no magic ISF
                // multiplier: a U200 user, a child and a high-TDD adult are all handled by their own
                // profile. Falling back is SAFE-SIGNED — profileSens is the value the user/clinician
                // configured, so a false positive costs dynamic responsiveness for that cycle and
                // nothing else, which is why the fraction is set liberally rather than tightly.
                val impliedTdd = if (profileSens > 0) 1800.0 / profileSens else 0.0
                val tddImplausible = tddImplausibleForProfile(tdd, profileSens)
                if (tddImplausible) {
                    // Leave sensNormalTarget at profileSens (its initial value) — do NOT derive.
                    debug.append(
                        "\n⚠ dynISF=PROFILE-FALLBACK: TDD ${Round.roundTo(tdd, 0.1)} U/day is below " +
                            "${Round.roundTo(impliedTdd * DYNISF_MIN_TDD_FRACTION, 0.1)} " +
                            "(${(DYNISF_MIN_TDD_FRACTION * 100).toInt()}% of the ${Round.roundTo(impliedTdd, 0.1)} " +
                            "implied by profile ISF ${Round.roundTo(profileSens, 0.1)}) — insulin history looks " +
                            "incomplete; using profile ISF instead of a derived one this cycle"
                    )
                    aapsLogger.info(
                        LTag.APS,
                        "Boost dynISF profile-fallback: tdd=${Round.roundTo(tdd, 0.1)} < " +
                            "${Round.roundTo(impliedTdd * DYNISF_MIN_TDD_FRACTION, 0.1)} implied-floor; using profileSens=$profileSens"
                    )
                }
                if (tdd > 0 && logTerm > 0 && !tddImplausible) {
                    sensNormalTarget = 1800.0 / (tdd * logTerm)
                    sensNormalTarget *= globalScale
                    debug.append("\nTDD ISF at target: ${Round.roundTo(sensNormalTarget, 0.1)} mg/dl/U (profile was ${Round.roundTo(profileSens, 0.1)})")

                    if (adjustSens && tddLast24H > 0) {
                        ratio = max(min(tddLast24H / tdd7D, autosensMax), autosensMin)
                        sensNormalTarget /= ratio
                        debug.append("\nSens ratio: ${Round.roundTo(ratio, 0.01)} (24H/7D = ${Round.roundTo(tddLast24H, 0.1)}/${Round.roundTo(tdd7D, 0.1)}) → ISF=${Round.roundTo(sensNormalTarget, 0.1)}")
                    }

                    // ISF shadow — compute the V4.4.2-style EMA(τ=3h) sensitivity ratio
                    // in parallel. Does not modify sensNormalTarget; result is returned
                    // alongside the real BoostIsfResult for direct comparison.
                    isfShadowResult = boostIsfShadow.computeShadow(
                        tddLast24H = tddLast24H,
                        tdd7D = tdd7D,
                        autosensMin = autosensMin,
                        autosensMax = autosensMax
                    )
                    if (isfShadowResult != null) {
                        debug.append("\n${isfShadowResult.debugLine}")
                    }

                    // Volume-weighted dose shadow. Computes an alternative blend from the
                    // insulin delivered so far today against the participant's own delivery
                    // curve, and logs it. It does not touch tdd, sensNormalTarget or anything
                    // downstream: the candidate failed one of the four pre-registered targets
                    // it was judged on, and the only route from here to dosing is a
                    // pre-registered within-person trial.
                    val nowForVwa = System.currentTimeMillis()
                    val sinceAnchorH = ((nowForVwa - vwaTddShadow.dayAnchorMs(nowForVwa))
                        / 3_600_000L).coerceIn(0L, 24L)
                    val deliveredToday = if (sinceAnchorH > 0L)
                        tddCalculator.calculateDaily(-sinceAnchorH, 0L)?.totalAmount else 0.0
                    // Read one day of stored history per cycle until the curve stands on the
                    // participant rather than on the population. Costs 48 window totals on a
                    // cycle and stops after seven days.
                    vwaTddShadow.warmFromHistory(nowForVwa) { startH, endH ->
                        tddCalculator.calculateDaily(startH, endH)?.totalAmount
                    }
                    vwaShadowResult = vwaTddShadow.compute(
                        nowMs = nowForVwa,
                        deliveredSinceDayStart = deliveredToday,
                        tdd7D = tdd7D
                    )
                    if (vwaShadowResult != null) {
                        debug.append("\n${vwaShadowResult.debugLine}")
                    }
                } else {
                    debug.append("\n⚠ TDD calculation produced invalid values (tdd=$tdd, logTerm=$logTerm) — using profile ISF")
                    aapsLogger.warn(LTag.APS, "Boost TDD ISF: invalid tdd=$tdd or logTerm=$logTerm, falling back to profile ISF")
                }
            } else {
                debug.append("\n⚠ TDD data incomplete — using profile ISF")
                aapsLogger.debug(LTag.APS, "Boost: TDD parts missing (7D=$tdd7D 1D=$tdd1D 24H=$tddLast24H 4H=$tddLast4H 8-4H=$tddLast8to4H)")
            }
        } else {
            debug.append("TDD-based ISF: disabled (using profile ISF ${Round.roundTo(profileSens, 0.1)})")
        }

        // Temp target sensitivity adjustment
        if (isTempTarget && ((highTtRaisesSens && targetBg > bgNormalTarget) || (lowTtLowersSens && targetBg < bgNormalTarget))) {
            val c = (halfBasalTarget - bgNormalTarget).toDouble()
            if (c * (c + targetBg - bgNormalTarget) > 0.0) {
                ratio = c / (c + targetBg - bgNormalTarget)
                ratio = max(min(ratio, autosensMax), autosensMin)
                sensNormalTarget /= ratio
                debug.append("\nTT adjustment: ratio=${Round.roundTo(ratio, 0.01)} → ISF=${Round.roundTo(sensNormalTarget, 0.1)}")
                aapsLogger.debug(LTag.APS, "Boost ISF adjusted by ${1.0 / ratio} due to TT of ${targetBg.toInt()}")
            }
        }

        // Calculate variable_sens using log formula
        val sbg = ln((bgCurrent / insulinDivisor) + 1.0)
        val scaler = ln((bgNormalTarget / insulinDivisor) + 1.0) / sbg
        val variableSens = sensNormalTarget * (1 - (1 - scaler) * velocity)

        if (ratio == 1.0 && adjustSens && !useTdd) {
            ratio = sensNormalTarget / variableSens
        }

        debug.append("\nVariable ISF at BG ${Round.roundTo(glucoseValue, 1.0)}: ${Round.roundTo(variableSens, 0.1)} (velocity=${Round.roundTo(velocity * 100, 1.0)}%)")

        aapsLogger.debug(LTag.APS, "Boost ISF: $debug")

        return BoostIsfResult(
            sensNormalTarget = Round.roundTo(sensNormalTarget, 0.1),
            variableSens = Round.roundTo(variableSens, 0.1),
            bgCapped = bgCurrent,
            insulinDivisor = insulinDivisor,
            dynIsfVelocity = velocity,
            ratio = Round.roundTo(ratio, 0.01),
            tdd = tdd,
            isfDebug = debug.toString(),
            tddSensShadow = isfShadowResult,
            vwaTddShadow = vwaShadowResult
        )
    }

    // ---- Boost Time Window & Activity Detection ----
    // Mirrors logic from DetermineBasalAdapterBoostJS.setData()

    data class BoostActivityResult(
        val boostActive: Boolean,
        val profileSwitch: Int,
        val minBg: Double,
        val maxBg: Double,
        val targetBg: Double,
        val activityState: String = "none",
        val debugReason: String = "",
        // True when the step-based sleep-in (lie-in) gate is suppressing Boost this cycle. Cached by
        // the caller so isNightModeActiveImpl() applies night-mode SMB rules during a lie-in. (2026-07-02)
        val sleepInActive: Boolean = false,
        // Which step feeds are live this cycle (F1, 2026-07-07): "phone+wear" | "phone" | "wear" |
        // "none" — written to RT.boostSteps_feed every cycle so a dark feed is visible in NS.
        val stepsFeed: String = "none"
    )

    private fun calculateBoostActivity(
        now: Long,
        tempTargetSet: Boolean,
        targetBg: Double,
        minBg: Double,
        maxBg: Double,
        profilePercent: Int
    ): BoostActivityResult {
        val debug = StringBuilder()
        val midnight = now - MidnightUtils.milliSecFromMidnight(now)
        val sleepInMillis = (3600000.0 * sleepInHours).toLong()

        // Boost is active whenever the user is NOT in their night/sleep period. The night/sleep period
        // is the HR/step-aware night-mode state — enabled && (night time window OR sleep detection) —
        // EXCLUDING night mode's BG gate: a nocturnal high (incl. a sensor spike) must NOT re-enable
        // Boost, or a full V6 meal-amplified SMB could fire while asleep (the 2026-07-01 incident).
        // Replaces the old fixed Boost time window; the Boost window now tracks night mode, so
        // "Boost active" == "not night". `ApsBoostStartTime`/`ApsBoostEndTime` are retired. (2026-07-02)
        val nightEndMs = midnight + parseTimeToMillisOrDefault(preferences.getBoostDosing(StringKey.ApsBoostNightModeEnd), "07:00")

        var boostActive = !isInNightSleepPeriod()
        var disableReason = ""
        if (!boostActive) disableReason = "Night/sleep period (night mode active by time or HR/steps)"

        val nowTime = java.time.Instant.ofEpochMilli(now).atZone(java.time.ZoneId.systemDefault()).toLocalTime()
        debug.append("Boost gate: night/sleep=${!boostActive} | Now: ${nowTime.format(DateTimeFormatter.ofPattern("HH:mm"))}")

        // Disable boost if high temp target and not allowed
        if (boostActive && tempTargetSet && !allowBoostWithHighTt && targetBg > dynIsfNormalTarget) {
            boostActive = false
            disableReason = "High temp target ($targetBg > ${dynIsfNormalTarget})"
            aapsLogger.debug(LTag.APS, "Boost disabled due to high temptarget of $targetBg")
        }

        var recentSteps5Min = StepService.getRecentStepCount5Min()
        var recentSteps15Min = StepService.getRecentStepCount15Min()
        var recentSteps30Min = StepService.getRecentStepCount30Min()
        var recentSteps60Min = StepService.getRecentStepCount60Min()
        // F3 fix (2026-07-08): the live exercise classifier read PHONE StepService ONLY, so watch
        // steps (wear AND Garmin, which land in the SC table) never influenced exercise state — a
        // pre-existing gap that Garmin workstream B forced into the open. Blend the freshest watch
        // SC row's trailing windows in ADDITIVELY (max): can only ADD activity detection, never
        // remove protection. NOTE: this is a dosing-behaviour change (exercise state → activity
        // target/gating) — backtest before relying on it beyond on-device validation.
        run {
            val recentSc = try {
                persistenceLayer.getStepsCountFromTimeToTime(dateUtil.now() - 15 * 60_000L, dateUtil.now())
            } catch (t: Throwable) { emptyList() }
            recentSc.maxByOrNull { it.timestamp }?.let { sc ->
                recentSteps5Min = maxOf(recentSteps5Min, sc.steps5min)
                recentSteps15Min = maxOf(recentSteps15Min, sc.steps15min)
                recentSteps30Min = maxOf(recentSteps30Min, sc.steps30min)
                recentSteps60Min = maxOf(recentSteps60Min, sc.steps60min)
            }
        }

        debug.append("\nSteps: 5m=$recentSteps5Min 15m=$recentSteps15Min 30m=$recentSteps30Min 60m=$recentSteps60Min")

        // ── Step-source availability guard (F1, 2026-07-07) ──
        // 0 steps from a feed that never reported is NOT sedentary — it's unknown. Available =
        // phone pedometer LIVE this boot OR a wear SC row within the WearStepSource freshness
        // window. When unavailable: no INACTIVE profile drop, no steps-based sleep-in, and the
        // outage is breadcrumbed (debugReason + boostSteps_feed RT). See StepFeed KDoc.
        val wearScRecent = try {
            persistenceLayer.getStepsCountFromTimeToTime(now - WearStepSource.FRESH_MS, now)
        } catch (t: Throwable) {
            emptyList()
        }
        val stepFeed = StepFeed.State(
            phoneLive = StepService.feedState() == StepService.FeedState.LIVE,
            wearAgeMs = WearStepSource.latest(wearScRecent)?.let { now - it.timestamp }
        )
        val stepsAvailable = stepFeed.available
        if (!stepsAvailable) debug.append("\n${stepFeed.unavailableNote()}")

        // Steps-based sleep-in (lie-in). 2026-07-08 MERGE folded this into SleepStateDetector — when
        // night-mode-auto-by-sleep is ON, the detector HOLDS SLEEPING through the lie-in window
        // (nightEnd → nightEnd+sleepInHours) and releases on the SAME sleepInSteps threshold. This
        // standalone gate is the FAILSAFE. It engages unless the detector is ACTIVELY holding sleep
        // (auto-by-sleep ON *and* state == SLEEPING) — so it also covers the detector's documented
        // false-AWAKE mode during the lie-in (previously the gate stood down for the whole window
        // whenever auto-by-sleep was on, leaving a dawn false-AWAKE unprotected). sleepStateCached is
        // last cycle's state (this cycle's is evaluated later); one-cycle (~5 min) lag is acceptable
        // for a lie-in backstop.
        val sleepInActive = StepFeed.sleepInActive(stepsAvailable, now, nightEndMs, sleepInMillis, recentSteps60Min, sleepInSteps)
        val autoBySleepActive = preferences.get(BooleanKey.ApsBoostNightModeAutoBySleep)
        val nightModeEnabled = preferences.getBoostDosing(BooleanKey.ApsBoostNightModeEnabled)
        val detectorSleeping = sleepStateCached.state == SleepStateDetector.SleepState.SLEEPING
        // Sleep as the INACTIVE branch must see it. SLEEPING is confirmed sleep; PRE_SLEEP is the
        // wind-down before it, and the user is in bed for both. This covers the CORE NIGHT, which
        // sleepInActive cannot reach — that window opens AT night end, so at 06:09 with a 07:00 end
        // it is false by construction, which is why the original report fired before dawn.
        val detectorAsleep = sleepStateCached.state == SleepStateDetector.SleepState.SLEEPING ||
            sleepStateCached.state == SleepStateDetector.SleepState.PRE_SLEEP
        // The configured night window as a clock fact, read WHATEVER ApsBoostNightModeEnabled says.
        // This is what makes "INACTIVE never fires overnight" hold by default instead of depending
        // on the user having enabled night mode, and it needs no HR, no steps and no detector.
        val nightStartMs = midnight + parseTimeToMillisOrDefault(preferences.getBoostDosing(StringKey.ApsBoostNightModeStart), "22:00")
        val inNightWindow = NightWindow.contains(now, nightStartMs, nightEndMs)
        // Audit trail for the 2026-07-31 fix: record when the step test alone WOULD have raised the
        // profile but sleep blocked it, so the suppression is visible in NS rather than silent.
        if (StepFeed.inactivityStepsMet(stepsAvailable, profilePercent, recentSteps60Min, inactivitySteps) &&
            (sleepInActive || detectorAsleep || inNightWindow)
        ) {
            debug.append("\nInactivity SUPPRESSED by sleep (60m steps $recentSteps60Min < $inactivitySteps; " +
                "nightWindow=$inNightWindow sleepIn=$sleepInActive detector=${sleepStateCached.state}) → profile held at 100%")
        }
        if (boostActive && StepFeed.lieInFailsafeEngages(sleepInActive, nightModeEnabled, autoBySleepActive, detectorSleeping)) {
            boostActive = false
            disableReason = "Sleep-in failsafe (60m steps $recentSteps60Min < threshold $sleepInSteps, within ${sleepInHours}h of night end; auto-by-sleep=$autoBySleepActive detector=${sleepStateCached.state})"
            aapsLogger.debug(LTag.APS, "Boost disabled due to lie-in (failsafe; auto-by-sleep=$autoBySleepActive detector=${sleepStateCached.state})")
        }

        var activityMinBg = minBg
        var activityMaxBg = maxBg
        var activityTargetBg = targetBg
        var currentProfileSwitch = profilePercent
        var activityState = "none"

        if (boostActive) {
            val activityBgTarget = 150.0
            val isActive = (activitySteps5  > 0 && recentSteps5Min  > activitySteps5)
                || (activitySteps15 > 0 && recentSteps15Min > activitySteps15)
                || (activitySteps30 > 0 && recentSteps30Min > activitySteps30)
                || (activitySteps60 > 0 && recentSteps60Min > activitySteps60)

            // ---- HR-augmented classification (opt-in, additive only) ----
            val hrClassification: HrActivityCalculator.HrClassificationResult? =
                if (hrIntegrationEnabled) {
                    val windowMs = hrWindowMinutes * 60_000L
                    val hrReadings = persistenceLayer.getHeartRatesFromTime(now - windowMs)
                    HrActivityCalculator.classify(
                        hrReadings = hrReadings,
                        nowMillis = now,
                        hrWindowMinutes = hrWindowMinutes,
                        hrMax = hrMaxBpm,
                        // Use learned daytime baseline if banked (≥7 nights); fallback to configured.
                        // This gives a more accurate Karvonen HRR for exercise classification.
                        hrResting = hrLearnedDaytimeBpmCached ?: hrRestingBpm,
                        stepsLast15Min = recentSteps15Min,
                        stressDetection = hrStressDetection,
                        aapsLogger = aapsLogger,
                    ).takeIf { it.hrZone != HrActivityCalculator.HrZone.NONE } // null if no HR data
                } else null

            if (hrClassification != null) {
                debug.append("\nHR: ${hrClassification.debugInfo}")
            }

            if (isActive) {
                // Step-only path detected activity; use HR to refine classification
                when (hrClassification?.exerciseState) {
                    HrActivityCalculator.ExerciseState.VIGOROUS_AEROBIC -> {
                        // High intensity aerobic: reduce profile more aggressively, raise target
                        activityState = "VIGOROUS_AEROBIC"
                        if (currentProfileSwitch == 100) {
                            // Use a more conservative profile reduction (cap at activityPct - 10, min 50%)
                            currentProfileSwitch = (activityPct - 10.0).coerceAtLeast(50.0).toInt()
                            aapsLogger.debug(LTag.APS, "Profile changed to $currentProfileSwitch% due to vigorous aerobic (HR z${hrClassification.hrZone.label})")
                        }
                        if (!tempTargetSet) {
                            activityMinBg = activityBgTarget
                            activityMaxBg = activityBgTarget
                            activityTargetBg = activityBgTarget
                        }
                        debug.append("\nVigorous aerobic (HR ${String.format("%.0f", hrClassification.averageHrBpm)} bpm, ${hrClassification.hrZone.label}) → profile ${currentProfileSwitch}%, target $activityTargetBg")
                    }
                    HrActivityCalculator.ExerciseState.RESISTANCE -> {
                        // Resistance exercise: raise target BG but do NOT reduce profile
                        // (acute BG rise; delayed hypo risk — don't increase insulin aggressiveness now)
                        activityState = "RESISTANCE"
                        val resistanceBgTarget = 160.0
                        if (!tempTargetSet) {
                            activityMinBg = resistanceBgTarget
                            activityMaxBg = resistanceBgTarget
                            activityTargetBg = resistanceBgTarget
                        }
                        aapsLogger.debug(LTag.APS, "Resistance exercise detected via HR (${hrClassification.hrZone.label}): raising target, not reducing profile")
                        debug.append("\nResistance exercise (HR ${String.format("%.0f", hrClassification.averageHrBpm)} bpm, ${hrClassification.hrZone.label}) → profile unchanged at ${currentProfileSwitch}%, target $activityTargetBg")
                    }
                    null, HrActivityCalculator.ExerciseState.MODERATE_AEROBIC,
                    HrActivityCalculator.ExerciseState.LIGHT_AEROBIC -> {
                        // Default step-only ACTIVE behaviour
                        activityState = "ACTIVE"
                        if (currentProfileSwitch == 100) {
                            currentProfileSwitch = activityPct.toInt()
                            aapsLogger.debug(LTag.APS, "Profile changed to $activityPct% due to activity")
                        }
                        if (!tempTargetSet) {
                            activityMinBg = activityBgTarget
                            activityMaxBg = activityBgTarget
                            activityTargetBg = activityBgTarget
                            aapsLogger.debug(LTag.APS, "TargetBG changed to $activityBgTarget due to activity")
                        }
                        debug.append("\nActivity detected → profile ${currentProfileSwitch}%, target ${activityTargetBg}")
                    }
                    else -> {
                        // HR signal contradicts steps (LOW confidence) — fall back to step-only ACTIVE
                        activityState = "ACTIVE"
                        if (currentProfileSwitch == 100) {
                            currentProfileSwitch = activityPct.toInt()
                            aapsLogger.debug(LTag.APS, "Profile changed to $activityPct% due to activity (HR inconclusive)")
                        }
                        if (!tempTargetSet) {
                            activityMinBg = activityBgTarget
                            activityMaxBg = activityBgTarget
                            activityTargetBg = activityBgTarget
                        }
                        debug.append("\nActivity detected (HR inconclusive: ${hrClassification.exerciseState}) → profile ${currentProfileSwitch}%, target $activityTargetBg")
                    }
                }
            } else if (StepFeed.inactivityEligible(
                    stepsAvailable, currentProfileSwitch, recentSteps60Min, inactivitySteps,
                    sleepInActive = sleepInActive, asleep = detectorAsleep,
                    inNightWindow = inNightWindow
                )) {
                // Inactivity confirmed on a LIVE feed — check HR for stress. (F1 2026-07-07: a dark
                // feed can no longer reach this branch — "no steps" must not mean "sedentary".)
                if (hrIntegrationEnabled && HrActivityCalculator.inactivitySuppressedByElevatedHr(hrClassification)) {
                    // 2026-07-21 CRITICAL SAFETY: an elevated HR (zone ≥ 3) with a low step count is
                    // probable NON-STEP exercise (cycling, rowing, resistance). The inactivity branch
                    // adds insulin (profile → inactivityPct); a real incident raised profile 130% at
                    // zone3 while BG fell 12 mg/dL per 5 min because 64 steps landed in the classifier
                    // dead zone and came back RESTING. Keying on the HR ZONE directly (not the fused
                    // state), suppress the profile-raise entirely and raise the target instead.
                    activityState = "RESISTANCE"
                    val elevatedHrTarget = 160.0
                    if (!tempTargetSet) {
                        activityMinBg = elevatedHrTarget
                        activityMaxBg = elevatedHrTarget
                        activityTargetBg = elevatedHrTarget
                    }
                    aapsLogger.debug(LTag.APS, "Inactivity SUPPRESSED — HR elevated (${hrClassification?.hrZone?.label}, ${String.format("%.0f", hrClassification?.averageHrBpm ?: 0.0)} bpm) with low steps → non-step exercise; raising target to $elevatedHrTarget, profile UNCHANGED (NOT adding insulin)")
                    debug.append("\nInactivity SUPPRESSED (HR ${hrClassification?.hrZone?.label} elevated, 60m steps $recentSteps60Min) → target $activityTargetBg, profile unchanged")
                } else if (hrStressDetection &&
                    hrClassification?.exerciseState == HrActivityCalculator.ExerciseState.STRESS &&
                    hrClassification.confidence != HrActivityCalculator.Confidence.LOW
                ) {
                    // Stress detected: raise target BG without changing profile
                    activityState = "STRESS"
                    val stressBgTarget = 160.0
                    if (!tempTargetSet) {
                        activityMinBg = stressBgTarget
                        activityMaxBg = stressBgTarget
                        activityTargetBg = stressBgTarget
                    }
                    aapsLogger.debug(LTag.APS, "Stress/illness detected (HR ${String.format("%.0f", hrClassification.averageHrBpm)} bpm, no steps): raising target to $stressBgTarget, profile unchanged")
                    debug.append("\nStress/illness (HR ${String.format("%.0f", hrClassification.averageHrBpm)} bpm, ${hrClassification.hrZone.label}, no movement) → target $activityTargetBg, profile unchanged")
                } else {
                    activityState = "INACTIVE"
                    currentProfileSwitch = inactivityPct.toInt()
                    debug.append("\nInactivity detected (60m steps $recentSteps60Min < $inactivitySteps) → profile ${currentProfileSwitch}%")
                    aapsLogger.debug(LTag.APS, "Profile changed to $inactivityPct% due to inactivity")
                }
            } else if (!isActive &&
                hrIntegrationEnabled &&
                hrClassification?.exerciseState == HrActivityCalculator.ExerciseState.RESISTANCE &&
                hrClassification.confidence != HrActivityCalculator.Confidence.LOW
            ) {
                // HR-only resistance detection (steps don't detect this)
                activityState = "RESISTANCE"
                val resistanceBgTarget = 160.0
                if (!tempTargetSet) {
                    activityMinBg = resistanceBgTarget
                    activityMaxBg = resistanceBgTarget
                    activityTargetBg = resistanceBgTarget
                }
                aapsLogger.debug(LTag.APS, "Resistance exercise detected via HR only (${hrClassification.hrZone.label}): raising target")
                debug.append("\nResistance (HR-only, ${hrClassification.hrZone.label}) → target $activityTargetBg, profile unchanged")
            } else if (!isActive &&
                hrStressDetection &&
                hrClassification?.exerciseState == HrActivityCalculator.ExerciseState.STRESS &&
                hrClassification.confidence != HrActivityCalculator.Confidence.LOW
            ) {
                activityState = "STRESS"
                val stressBgTarget = 160.0
                if (!tempTargetSet) {
                    activityMinBg = stressBgTarget
                    activityMaxBg = stressBgTarget
                    activityTargetBg = stressBgTarget
                }
                aapsLogger.debug(LTag.APS, "Stress detected via HR (${hrClassification.hrZone.label}): raising target")
                debug.append("\nStress (HR-only, ${hrClassification.hrZone.label}) → target $activityTargetBg, profile unchanged")
            } else if (!stepsAvailable) {
                // F1 (2026-07-07): feed dark and no HR-only classification fired — profile stays
                // 100%, no target change. isActive is necessarily false here (no step data), so
                // this is exactly the cycle set that previously mis-read as INACTIVE.
                activityState = "steps-unknown"
                debug.append("\nActivity: steps-unknown (feed unavailable — no INACTIVE, profile unchanged)")
            } else {
                activityState = "normal"
                debug.append("\nActivity: normal (no adjustment)")
            }
        }

        if (boostActive) {
            debug.append("\n✓ BOOST ACTIVE ($activityState)")
        } else {
            debug.append("\n✗ BOOST INACTIVE: $disableReason")
        }

        return BoostActivityResult(
            boostActive = boostActive,
            profileSwitch = currentProfileSwitch,
            minBg = activityMinBg,
            maxBg = activityMaxBg,
            targetBg = activityTargetBg,
            activityState = activityState,
            debugReason = debug.toString(),
            sleepInActive = sleepInActive,
            stepsFeed = stepFeed.label
        )
    }

    private fun parseTimeToMillis(timeStr: String): Long {
        return try {
            val time = LocalTime.parse(timeStr, DateTimeFormatter.ofPattern("H:mm"))
            (time.hour * 3600000L) + (time.minute * 60000L)
        } catch (_: DateTimeParseException) {
            try {
                val time = LocalTime.parse(timeStr, DateTimeFormatter.ofPattern("HH:mm"))
                (time.hour * 3600000L) + (time.minute * 60000L)
            } catch (_: DateTimeParseException) {
                aapsLogger.error(LTag.APS, "Failed to parse time: $timeStr, defaulting to 0")
                0L
            }
        }
    }

    /** [parseTimeToMillis] but falling back to [defaultStr] — NOT silently to midnight — on a
     *  malformed pref. Midnight-on-typo moved the whole night window (night "ending" at 00:00 put
     *  the sleep-in anchor at midnight and Boost fully active from 00:00 while asleep). (2026-07-02) */
    private fun parseTimeToMillisOrDefault(timeStr: String, defaultStr: String): Long {
        return try {
            val time = LocalTime.parse(timeStr, DateTimeFormatter.ofPattern("H:mm"))
            (time.hour * 3600000L) + (time.minute * 60000L)
        } catch (_: DateTimeParseException) {
            try {
                val time = LocalTime.parse(timeStr, DateTimeFormatter.ofPattern("HH:mm"))
                (time.hour * 3600000L) + (time.minute * 60000L)
            } catch (_: DateTimeParseException) {
                aapsLogger.error(LTag.APS, "Malformed night-mode time '$timeStr' — using default $defaultStr")
                parseTimeToMillis(defaultStr)
            }
        }
    }

    /** Returns minute-of-day [0..1439] for a "HH:mm" or "H:mm" string. Defaults to 0 on parse error. */
    private fun parseTimeToMinutesOfDay(timeStr: String): Int =
        (parseTimeToMillis(timeStr) / 60_000L).toInt()

    /**
     * Clamp a learned minute-of-day to within ±[bandMin] of the configured minute-of-day, on the
     * 24h circle. Returns [configured] when [learned] is null (no/insufficient learned data). This
     * caps how far the learned sleep window can drift from the user's configured times — the safety
     * bound that, with the genuine-wake-only training in SleepHistoryTracker, stops the night-window
     * collapse (each night ratcheting the wake earlier).
     */
    /** Max minutes the learned sleep window may move from the configured night start/end. */
    private val LEARNED_WINDOW_BAND_MIN = 90

    private fun clampToConfiguredBand(learned: Int?, configured: Int, bandMin: Int, allowEarlier: Boolean = true): Int {
        if (learned == null) return configured
        // signed circular delta in [-720, 719] (positive = learned is LATER than configured)
        val delta = ((learned - configured + 1440 + 720) % 1440) - 720
        // allowEarlier=false makes the nudge one-sided: learning may only move the bound LATER than the
        // configured time, never earlier. Used for night-END (wake), where moving earlier would lift
        // sleep protection before the user's own setting — the unsafe direction — and is a poor fit for a
        // highly-variable waker (learned point-mean sits early; real-time detection catches genuine early
        // wakes anyway). Night-START keeps the symmetric band (later-to-bed drift is expected + safe).
        val loBand = if (allowEarlier) -bandMin else 0
        val clamped = delta.coerceIn(loBand, bandMin)
        return ((configured + clamped) % 1440 + 1440) % 1440
    }

    /** Format a minute-of-day [0..1439] as "HH:mm" for telemetry. */
    private fun formatClockMin(min: Int): String {
        val m = ((min % 1440) + 1440) % 1440
        return "%02d:%02d".format(m / 60, m % 60)
    }

    // ---- Main invoke ----

    override fun invoke(initiator: String, tempBasalFallback: Boolean) =
        runEngine(initiator, tempBasalFallback, v5Active = false)

    /**
     * Shared Boost dosing engine. Computes the full V1 decision and, when [v5Active], lets V5's
     * observe-confirm-commit decision override the SMB. The selectable "Boost V5" plugin calls
     * this with v5Active=true; pure "Boost" (V1) calls it with false (its own [invoke]).
     * `runShadow()` runs either way, so V5 shadow telemetry is logged under V1 as well — only the
     * dose override is gated by [v5Active].
     */
    fun runEngine(initiator: String, tempBasalFallback: Boolean, v5Active: Boolean) {
        aapsLogger.debug(LTag.APS, "runEngine from $initiator tempBasalFallback: $tempBasalFallback v5Active: $v5Active")
        // 2026-06-03: Trigger Health Connect HR ingest. Throttled internally; no-op if disabled.
        healthConnectHrIngest.syncIfDue()
        // 2026-06-16: Health Connect STEPS ingest (activity-load shadow). Throttled internally.
        healthConnectStepsIngest.syncIfDue()
        lastAPSResult = null
        val glucoseStatus = glucoseStatusCalculatorSMB.glucoseStatusData
        val profile = profileFunction.getProfile()
        val pump = activePlugin.activePump
        if (profile == null) {
            rxBus.send(EventResetOpenAPSGui(rh.gs(app.aaps.core.ui.R.string.no_profile_set)))
            aapsLogger.debug(LTag.APS, rh.gs(app.aaps.core.ui.R.string.no_profile_set))
            return
        }
        if (!engineActive()) {
            rxBus.send(EventResetOpenAPSGui(rh.gs(R.string.openapsma_disabled)))
            aapsLogger.debug(LTag.APS, rh.gs(R.string.openapsma_disabled))
            return
        }
        if (glucoseStatus == null) {
            rxBus.send(EventResetOpenAPSGui(rh.gs(R.string.openapsma_no_glucose_data)))
            aapsLogger.debug(LTag.APS, rh.gs(R.string.openapsma_no_glucose_data))
            return
        }

        val inputConstraints = ConstraintObject(0.0, aapsLogger)

        if (!hardLimits.checkHardLimits(profile.dia, app.aaps.core.ui.R.string.profile_dia, hardLimits.minDia(), hardLimits.maxDia())) return
        if (!hardLimits.checkHardLimits(
                profile.getIcTimeFromMidnight(MidnightUtils.secondsFromMidnight()),
                app.aaps.core.ui.R.string.profile_carbs_ratio_value,
                hardLimits.minIC(),
                hardLimits.maxIC()
            )
        ) return
        if (!hardLimits.checkHardLimits(profile.getIsfMgdl("OpenAPSBoostPlugin"), app.aaps.core.ui.R.string.profile_sensitivity_value, HardLimits.MIN_ISF, HardLimits.MAX_ISF)) return
        if (!hardLimits.checkHardLimits(profile.getMaxDailyBasal(), app.aaps.core.ui.R.string.profile_max_daily_basal_value, 0.02, hardLimits.maxBasal())) return
        if (!hardLimits.checkHardLimits(pump.baseBasalRate, app.aaps.core.ui.R.string.current_basal_value, 0.01, hardLimits.maxBasal())) return

        // End of checks, start gathering data

        val smbEnabled = preferences.get(BooleanKey.ApsUseSmb)
        val allowAllBgSources = true // Boost: always allow all BG sources (forced on; user toggle removed)
        val advancedFiltering = allowAllBgSources || constraintsChecker.isAdvancedFilteringEnabled().also { inputConstraints.copyReasons(it) }.value()
        val now = dateUtil.now()

        val tb = processedTbrEbData.getTempBasalIncludingConvertedExtended(now)
        val currentTemp = CurrentTemp(
            duration = tb?.plannedRemainingMinutes ?: 0,
            rate = tb?.convertedToAbsolute(now, profile) ?: 0.0,
            minutesrunning = tb?.getPassedDurationToTimeInMinutes(now)
        )

        var minBg = hardLimits.verifyHardLimits(Round.roundTo(profile.getTargetLowMgdl(), 0.1), app.aaps.core.ui.R.string.profile_low_target, HardLimits.LIMIT_MIN_BG[0], HardLimits.LIMIT_MIN_BG[1])
        var maxBg = hardLimits.verifyHardLimits(Round.roundTo(profile.getTargetHighMgdl(), 0.1), app.aaps.core.ui.R.string.profile_high_target, HardLimits.LIMIT_MAX_BG[0], HardLimits.LIMIT_MAX_BG[1])
        var targetBg = hardLimits.verifyHardLimits(profile.getTargetMgdl(), app.aaps.core.ui.R.string.temp_target_value, HardLimits.LIMIT_TARGET_BG[0], HardLimits.LIMIT_TARGET_BG[1])
        var isTempTarget = false
        persistenceLayer.getTemporaryTargetActiveAt(dateUtil.now())?.let { tempTarget ->
            isTempTarget = true
            minBg = hardLimits.verifyHardLimits(tempTarget.lowTarget, app.aaps.core.ui.R.string.temp_target_low_target, HardLimits.LIMIT_TEMP_MIN_BG[0], HardLimits.LIMIT_TEMP_MIN_BG[1])
            maxBg = hardLimits.verifyHardLimits(tempTarget.highTarget, app.aaps.core.ui.R.string.temp_target_high_target, HardLimits.LIMIT_TEMP_MAX_BG[0], HardLimits.LIMIT_TEMP_MAX_BG[1])
            targetBg = hardLimits.verifyHardLimits(tempTarget.target(), app.aaps.core.ui.R.string.temp_target_value, HardLimits.LIMIT_TEMP_TARGET_BG[0], HardLimits.LIMIT_TEMP_TARGET_BG[1])
        }

        var autosensResult = AutosensResult()
        if (constraintsChecker.isAutosensModeEnabled().value()) {
            val autosensData = iobCobCalculator.getLastAutosensDataWithWaitForCalculationFinish("OpenAPSBoostPlugin")
            if (autosensData == null) {
                rxBus.send(EventResetOpenAPSGui(rh.gs(R.string.openaps_no_as_data)))
                return
            }
            autosensResult = autosensData.autosensResult
        } else autosensResult.sensResult = "autosens disabled"

        val iobArray = iobCobCalculator.calculateIobArrayForSMB(autosensResult, SMBDefaults.exercise_mode, SMBDefaults.half_basal_exercise_target, isTempTarget)
        val mealData = iobCobCalculator.getMealDataWithWaitingForCalculationFinish()
        val profilePercent = if (profile is ProfileSealed.EPS) profile.value.originalPercentage else 100
        val microBolusAllowedByConstraints = constraintsChecker.isSMBModeEnabled(ConstraintObject(tempBasalFallback.not(), aapsLogger)).also { inputConstraints.copyReasons(it) }.value()
        val microBolusAllowed = if (dateUtil.now() < calibrationBlockedUntil) {
            val remainingMin = (calibrationBlockedUntil - dateUtil.now()) / 60_000
            aapsLogger.debug(LTag.APS, "Boost SMB blocked: calibration detected ${remainingMin}min ago, ${15 - remainingMin}min elapsed of 15")
            false
        } else microBolusAllowedByConstraints
        val flatBGsDetected = bgQualityCheck.state == BgQualityCheck.State.FLAT

        // ---- Boost-specific calculations ----

        // 1. Activity detection & boost time window
        val activityResult = calculateBoostActivity(now, isTempTarget, targetBg, minBg, maxBg, profilePercent)
        // Publish the step-based sleep-in state for next cycle's night-mode evaluation. (2026-07-02)
        sleepInActiveCached = activityResult.sleepInActive

        // 1b. Post-exercise recovery transition detection
        // HR-aware: all exercise states (aerobic, resistance) trigger recovery, not just "ACTIVE".
        // Recovery window duration, target BG, and SMB scale are adjusted per exercise type.
        if (postExerciseRecoveryEnabled) {
            val exerciseStateSet = setOf("ACTIVE", "VIGOROUS_AEROBIC", "MODERATE_AEROBIC", "LIGHT_AEROBIC", "RESISTANCE")
            val isCurrentlyActive = activityResult.activityState in exerciseStateSet
            if (isCurrentlyActive && !wasExerciseActive) {
                exerciseStartTime = now
                aapsLogger.debug(LTag.APS, "Boost post-exercise: exercise started (${activityResult.activityState}) at ${dateUtil.dateAndTimeString(exerciseStartTime)}")
            } else if (!isCurrentlyActive && wasExerciseActive) {
                val exerciseDurationMin = (now - exerciseStartTime) / 60_000L
                aapsLogger.debug(LTag.APS, "Boost post-exercise: exercise ended (was $lastExerciseStateAtTransition) after ${exerciseDurationMin}min")
                if (exerciseDurationMin >= postExerciseMinDuration) {
                    // Adjust recovery parameters based on exercise type (HR-classified or step-only).
                    // Multipliers are evidence-based relative to the user's configured baseline:
                    //   VIGOROUS_AEROBIC  — high immediate hypo risk: longer window, more SMB suppression
                    //   RESISTANCE        — delayed hypo risk + acute BG rise: longest window, less SMB
                    //                       suppression (BG runs high initially), slightly higher target
                    //   LIGHT_AEROBIC     — minimal glycogen depletion: shorter window, less suppression
                    //   ACTIVE/MODERATE   — baseline (no multiplier)
                    val (windowMultiplier, targetOffsetMgdl, scaleMultiplier) = when (lastExerciseStateAtTransition) {
                        "VIGOROUS_AEROBIC" -> Triple(1.25, 0.0,  0.8)
                        "RESISTANCE"       -> Triple(1.5,  10.0, 1.2)
                        "LIGHT_AEROBIC"    -> Triple(0.5,  0.0,  1.4)
                        else               -> Triple(1.0,  0.0,  1.0)
                    }
                    val recoveryMillis = (postExerciseRecoveryHours * 3600_000L * windowMultiplier).toLong()
                    val recoveryTargetMgdl = postExerciseRecoveryTarget + targetOffsetMgdl
                    activeRecoveryScale = (postExerciseRecoveryScale * scaleMultiplier).coerceIn(0.1, 1.0)
                    activeRecoveryTargetOffset = targetOffsetMgdl
                    recoveryWindowEnd = now + recoveryMillis
                    aapsLogger.debug(LTag.APS, "Boost post-exercise [$lastExerciseStateAtTransition]: window=${recoveryMillis / 60_000}min target=${recoveryTargetMgdl.toInt()}mg/dL SMBscale=$activeRecoveryScale")
                    if (persistenceLayer.getTemporaryTargetActiveAt(now) == null) {
                        val tt = TT(
                            timestamp = now,
                            duration = recoveryMillis,
                            reason = TT.Reason.ACTIVITY,
                            lowTarget = recoveryTargetMgdl,
                            highTarget = recoveryTargetMgdl
                        )
                        disposable += persistenceLayer.insertAndCancelCurrentTemporaryTarget(
                            temporaryTarget = tt,
                            action = Action.TT,
                            source = Sources.Aaps,
                            note = rh.gs(R.string.boost_post_exercise_recovery_title),
                            listValues = listOf(
                                ValueWithUnit.TETTReason(TT.Reason.ACTIVITY),
                                ValueWithUnit.Mgdl(recoveryTargetMgdl),
                                ValueWithUnit.Minute(TimeUnit.MILLISECONDS.toMinutes(recoveryMillis).toInt())
                            )
                        ).subscribe(
                            { aapsLogger.debug(LTag.APS, "Boost post-exercise: TempTarget inserted (${recoveryTargetMgdl.toInt()} mg/dL for ${TimeUnit.MILLISECONDS.toMinutes(recoveryMillis)}min)") },
                            { aapsLogger.error(LTag.APS, "Boost post-exercise: failed to insert TempTarget", it) }
                        )
                    } else {
                        aapsLogger.debug(LTag.APS, "Boost post-exercise: TempTarget already active — skipping insert")
                    }
                } else {
                    aapsLogger.debug(LTag.APS, "Boost post-exercise: exercise too brief (${exerciseDurationMin}min < ${postExerciseMinDuration}min) — no recovery")
                }
            }
            if (isCurrentlyActive) lastExerciseStateAtTransition = activityResult.activityState
            wasExerciseActive = isCurrentlyActive
        }

        // 2. Insulin peak / divisor calculation
        val insulin = activePlugin.activeInsulin
        val insulinPeak = insulin.peak.coerceIn(30, 75)
        val insulinDivisor = if (insulinPeak < 60) (90 - insulinPeak) + 30 else (90 - insulinPeak) + 40

        // 3. ISF pre-calculation
        // Profile switch inversely scales ISF: 80% profile → 125% ISF (more sensitive),
        // 120% profile → 83% ISF (more resistant).
        val profileScale = activityResult.profileSwitch.toDouble() / 100.0
        val scaledProfileSens = profile.getIsfMgdl("OpenAPSBoostPlugin") / profileScale
        val isfResult = calculateBoostIsf(
            profileSens = scaledProfileSens,
            profilePercent = activityResult.profileSwitch,
            targetBg = targetBg,
            insulinDivisor = insulinDivisor,
            glucoseValue = glucoseStatus.glucose,
            isTempTarget = isTempTarget
        )

        // 4. Sensitivity ratio that drives basal / target / CR scaling in determine_basal.
        //    Two DISTINCT levers feed DetermineBasalBoost:
        //      • variable_sens (ISF, from isfResult) — the DynISF curve; always carries BG/velocity
        //        sensitivity and is used as `sens` directly (no autosens division — dynISF mode).
        //      • autosensResult.ratio — scales basal (`current_basal * sensitivityRatio`), shifts
        //        targets, and adjusts remainingCATime/CR (DetermineBasalBoost ~383-400, 601).
        //    TDD-DynISF and traditional oref autosens are ALTERNATIVE adaptation mechanisms — never
        //    stack both (would double-count sensitivity). So:
        //      • useTdd ON  → the TDD model (24H/7D, in isfResult.ratio) owns sensitivity; autosens off.
        //      • useTdd OFF → ISF is the profile-anchored curve; traditional oref autosens (already in
        //        autosensResult.ratio, computed above and gated by ApsUseAutosens) should drive
        //        basal/target/CR. Mirrors reference DynISF SMB (sens=variable_sens; autosens scales
        //        basal only). Gated by ApsBoostAutosensWhenNoTdd — default OFF (legacy: the curve
        //        ratio scales basal) until validated on the oref-vs-curve shadow telemetry logged below.
        val orefAutosensRatio = autosensResult.ratio     // real oref autosens (1.0 when autosens disabled)
        val useTdd = preferences.getBoostDosing(BooleanKey.ApsBoostUseTdd)
        val autosensWhenNoTdd = preferences.getBoostDosing(BooleanKey.ApsBoostAutosensWhenNoTdd)
        autosensResult.ratio = selectSensitivityRatio(useTdd, autosensWhenNoTdd, isfResult.ratio, orefAutosensRatio)

        // 5. Adjust basal if profile switch from activity
        val currentBasal = if (activityResult.profileSwitch != 100) {
            val adjusted = pump.baseBasalRate * profileScale
            aapsLogger.debug(LTag.APS, "Basal adjusted to $adjusted")
            adjusted
        } else pump.baseBasalRate

        // 6. Recent BG nadir + braking signal (for fast-carb detection)
        val now60MinAgo = System.currentTimeMillis() - 60 * 60 * 1000L
        val now45MinAgo = System.currentTimeMillis() - 45 * 60 * 1000L
        val recentBgReadings = persistenceLayer.getBgReadingsDataFromTimeToTime(now60MinAgo, System.currentTimeMillis(), true)
        val recentLowBG = recentBgReadings.minOfOrNull { it.value }?.toDouble() ?: 999.0
        // v4.4.4 hotfix Fix A v2 (ported to V1 2026-06-01): 45-min rolling minimum used only by
        // Fix A post-rescue tier gating. See V3MLG3 plugin/determine_basal for backtest rationale.
        val recentLowBG45Min = recentBgReadings.filter { it.timestamp >= now45MinAgo }.minOfOrNull { it.value }?.toDouble() ?: 999.0
        // Braking product: max(|delta2| × (delta2 - delta1)) across consecutive triplets
        // where delta2 < 0 (still falling) and delta2 > delta1 (deceleration).
        // High values indicate rapid carb absorption arresting a fall — fast-carb signal
        // even when BG never went below the low threshold.
        val recentBrakingProduct = recentBgReadings.windowed(3).mapNotNull { w ->
            val delta1 = w[1].value - w[0].value
            val delta2 = w[2].value - w[1].value
            val improvement = delta2 - delta1
            if (delta2 < 0 && improvement > 0) Math.abs(delta2) * improvement else null
        }.maxOrNull()?.toDouble() ?: 0.0

        // 6b. Auto-cancel recovery TempTarget during hypo rescue rebound
        // When a hypo has occurred (recentLowBG < 100) and BG is now rising above it,
        // a post-exercise recovery TempTarget is counterproductive — it suppresses Boost
        // via the high-TT check, preventing the algorithm from responding to the carb overshoot.
        // Cancel the recovery TT and reset target to profile so Boost can re-engage.
        if (recentLowBG < 100.0 && glucoseStatus.glucose > recentLowBG + 20) {
            val activeTt = persistenceLayer.getTemporaryTargetActiveAt(now)
            if (activeTt != null && activeTt.reason == TT.Reason.ACTIVITY) {
                aapsLogger.debug(LTag.APS, "Boost: cancelling recovery TempTarget — hypo rebound detected (recentLow=${recentLowBG.toInt()}, BG now ${glucoseStatus.glucose.toInt()})")
                disposable += persistenceLayer.cancelCurrentTemporaryTargetIfAny(
                    timestamp = now,
                    action = Action.TT_REMOVED,
                    source = Sources.Aaps,
                    note = "Auto-cancelled: hypo rebound (low ${recentLowBG.toInt()} mg/dL)",
                    listValues = listOf(ValueWithUnit.TETTReason(TT.Reason.ACTIVITY))
                ).subscribe()
                // Also clear the recovery window so SMB reduction doesn't persist
                recoveryWindowEnd = 0L
                // Reset targets back to profile values
                isTempTarget = false
                minBg = hardLimits.verifyHardLimits(Round.roundTo(profile.getTargetLowMgdl(), 0.1), app.aaps.core.ui.R.string.profile_low_target, HardLimits.LIMIT_MIN_BG[0], HardLimits.LIMIT_MIN_BG[1])
                maxBg = hardLimits.verifyHardLimits(Round.roundTo(profile.getTargetHighMgdl(), 0.1), app.aaps.core.ui.R.string.profile_high_target, HardLimits.LIMIT_MAX_BG[0], HardLimits.LIMIT_MAX_BG[1])
                targetBg = hardLimits.verifyHardLimits(profile.getTargetMgdl(), app.aaps.core.ui.R.string.temp_target_value, HardLimits.LIMIT_TARGET_BG[0], HardLimits.LIMIT_TARGET_BG[1])
            }
        }

        // 7. Step counts
        val recentSteps5Min = StepService.getRecentStepCount5Min()
        val recentSteps15Min = StepService.getRecentStepCount15Min()
        val recentSteps30Min = StepService.getRecentStepCount30Min()
        val recentSteps60Min = StepService.getRecentStepCount60Min()

        // 7b. V6 anticipatory pre-meal low target (shadow-first).
        // Learned habitual meal times (from V5 CONFIRMED commits) lower the target ~45-60 min
        // before a meal so insulinReq is already elevated when carbs land. Exercise and
        // post-exercise recovery OVERRIDE this (activity raises the target; we only fire when not
        // active and not recovering). LOWER-ONLY: never raises a target. Shadow gate — when
        // ApsBoostV6PreMealTarget is OFF we only log "WOULD apply" for NS validation, no change.
        var v6MinBg = activityResult.minBg
        var v6MaxBg = activityResult.maxBg
        var v6TargetBg = activityResult.targetBg
        var v6PreMealReason: String? = null
        run {
            val nowLocal = java.time.LocalTime.now()
            val nowMin = nowLocal.hour * 60 + nowLocal.minute
            val offsetMs = java.time.ZoneId.systemDefault().rules.getOffset(java.time.Instant.now()).totalSeconds * 1000L
            val leadMaxMin = preferences.getBoostDosing(DoubleKey.ApsBoostV6PreMealLeadMin).toInt()
            val hit = MealTimeLearner.preMealWindow(mealTimeHistoryCached, nowMin, offsetMs, leadMaxMin) ?: return@run
            val exerciseNow = activityResult.activityState in setOf("ACTIVE", "VIGOROUS_AEROBIC", "MODERATE_AEROBIC", "LIGHT_AEROBIC", "RESISTANCE", "STRESS")
            val inRecovery = postExerciseRecoveryEnabled && now < recoveryWindowEnd
            if (exerciseNow || inRecovery) {
                v6PreMealReason = "V6 pre-meal SUPPRESSED (${if (exerciseNow) "exercise" else "recovery"}); "
                return@run
            }
            val preMealTarget = preferences.getBoostDosing(DoubleKey.ApsBoostV6PreMealTargetMgdl)
            val mealClock = formatClockMin(hit.mode.centreMin)
            v6PreMealReason = if (preferences.getBoostDosing(BooleanKey.ApsBoostV6PreMealTarget)) {
                if (preMealTarget < v6TargetBg) {   // lower-only
                    v6MinBg = minOf(v6MinBg, preMealTarget)
                    v6MaxBg = minOf(v6MaxBg, preMealTarget)
                    v6TargetBg = preMealTarget
                    "V6 pre-meal ACTIVE target=${preMealTarget.toInt()} (learned ~$mealClock, ${hit.minutesBeforeMeal}min before, ${hit.mode.distinctDays}d); "
                } else {
                    "V6 pre-meal skipped (target ${preMealTarget.toInt()} ≥ current ${v6TargetBg.toInt()}); "
                }
            } else {
                "V6 pre-meal WOULD apply ${preMealTarget.toInt()} (learned ~$mealClock, ${hit.minutesBeforeMeal}min before, ${hit.mode.distinctDays}d); "
            }
        }

        // ---- Build the OapsProfileBoost ----

        val oapsProfile = OapsProfileBoost(
            // Standard oref1 fields
            dia = 0.0,
            min_5m_carbimpact = 0.0,
            max_iob = constraintsChecker.getMaxIOBAllowed().also { inputConstraints.copyReasons(it) }.value(),
            max_daily_basal = profile.getMaxDailyBasal(),
            max_basal = constraintsChecker.getMaxBasalAllowed(profile).also { inputConstraints.copyReasons(it) }.value(),
            min_bg = v6MinBg,
            max_bg = v6MaxBg,
            target_bg = v6TargetBg,
            carb_ratio = profile.getIc(),
            sens = profile.getIsfMgdl("OpenAPSBoostPlugin"),
            autosens_adjust_targets = false,
            max_daily_safety_multiplier = preferences.get(DoubleKey.ApsMaxDailyMultiplier),
            current_basal_safety_multiplier = preferences.get(DoubleKey.ApsMaxCurrentBasalMultiplier),
            lgsThreshold = profileUtil.convertToMgdlDetect(preferences.get(UnitDoubleKey.ApsLgsThreshold)).toInt(),
            high_temptarget_raises_sensitivity = preferences.get(BooleanKey.ApsAutoIsfHighTtRaisesSens),
            low_temptarget_lowers_sensitivity = preferences.get(BooleanKey.ApsAutoIsfLowTtLowersSens),
            sensitivity_raises_target = true,
            resistance_lowers_target = true,
            adv_target_adjustments = true,
            exercise_mode = SMBDefaults.exercise_mode,
            half_basal_exercise_target = SMBDefaults.half_basal_exercise_target,
            maxCOB = SMBDefaults.maxCOB,
            skip_neutral_temps = pump.setNeutralTempAtFullHour(),
            remainingCarbsCap = SMBDefaults.remainingCarbsCap,
            enableUAM = constraintsChecker.isUAMEnabled().also { inputConstraints.copyReasons(it) }.value(),
            A52_risk_enable = SMBDefaults.A52_risk_enable,
            SMBInterval = preferences.get(IntKey.ApsMaxSmbFrequency),
            enableSMB_with_COB = smbEnabled && preferences.get(BooleanKey.ApsUseSmbWithCob),
            enableSMB_with_temptarget = smbEnabled && preferences.get(BooleanKey.ApsUseSmbWithLowTt),
            allowSMB_with_high_temptarget = smbEnabled && preferences.get(BooleanKey.ApsUseSmbWithHighTt),
            enableSMB_always = smbEnabled && preferences.get(BooleanKey.ApsUseSmbAlways) && advancedFiltering,
            enableSMB_after_carbs = smbEnabled && preferences.get(BooleanKey.ApsUseSmbAfterCarbs) && advancedFiltering,
            maxSMBBasalMinutes = preferences.get(IntKey.ApsMaxMinutesOfBasalToLimitSmb),
            maxUAMSMBBasalMinutes = preferences.get(IntKey.ApsUamMaxMinutesOfBasalToLimitSmb),
            bolus_increment = pump.pumpDescription.bolusStep,
            carbsReqThreshold = preferences.get(IntKey.ApsCarbsRequestThreshold),
            current_basal = currentBasal,
            temptargetSet = isTempTarget,
            autosens_max = preferences.get(DoubleKey.AutosensMax),
            out_units = if (profileFunction.getUnits() == GlucoseUnit.MMOL) "mmol/L" else "mg/dl",

            // Dynamic ISF fields
            dynISFBgCap = dynIsfBgCap,
            dynISFBgCapped = isfResult.bgCapped,
            sensNormalTarget = isfResult.sensNormalTarget,
            normalTarget = dynIsfNormalTarget,
            dynISFvelocity = isfResult.dynIsfVelocity,
            insulinPeak = insulinPeak,
            variable_sens = isfResult.variableSens,
            insulinDivisor = insulinDivisor,
            TDD = isfResult.tdd,

            // Boost SMB fields
            boostActive = activityResult.boostActive,
            profileSwitch = activityResult.profileSwitch,
            boost_bolus = if (postExerciseRecoveryEnabled && now < recoveryWindowEnd) {
                val scaled = boostBolus * activeRecoveryScale
                aapsLogger.debug(LTag.APS, "Boost post-exercise recovery [$lastExerciseStateAtTransition]: boost_bolus $boostBolus → $scaled (scale=$activeRecoveryScale)")
                scaled
            } else boostBolus,
            boost_maxIOB = boostMaxIob,
            Boost_InsulinReq = boostInsulinReqPct,
            boost_scale = if (postExerciseRecoveryEnabled && now < recoveryWindowEnd) {
                val scaled = boostScale * activeRecoveryScale
                aapsLogger.debug(LTag.APS, "Boost post-exercise recovery [$lastExerciseStateAtTransition]: boost_scale $boostScale → $scaled (scale=$activeRecoveryScale)")
                scaled
            } else boostScale,
            boost_percent_scale = boostPercentScale,
            enableBoostPercentScale = enableBoostPercentScale,
            enableCircadianISF = enableCircadianIsf,
            allowBoost_with_high_temptarget = allowBoostWithHighTt,

            // Step counter data
            recentSteps5Minutes = recentSteps5Min,
            recentSteps15Minutes = recentSteps15Min,
            recentSteps30Minutes = recentSteps30Min,
            recentSteps60Minutes = recentSteps60Min,

            // Fast-carb rebound detection
            recentLowBG = recentLowBG,
            recentBrakingProduct = recentBrakingProduct,

            // Debug context
            boostDebugReason = activityResult.debugReason,
            isfDebugReason = isfResult.isfDebug,

            // V5/V6 exercise inputs (F2, 2026-07-07) — fill so OpenAPSBoostV5Plugin's decide() sees
            // the live activity state. These fields were DEAD on the live path since the V6 plugin
            // split: only the retired OpenAPSBoostV3MLG3Plugin ever set them, so V6's meal-score
            // exercise damping (MealSignalScore.notExercisingTerm), the fastConfirm !exercising gate
            // (MealHypothesis.step), and the AggressionBudget post-exercise damper had NEVER engaged
            // live — the exercise-into-correction hypo class this batch targets. Mapping mirrors
            // V3MLG3's exact block (OpenAPSBoostV3MLG3Plugin, v5_* assignments) via the shared
            // helpers below ([v5ExerciseActive]/[v5InPostExerciseWindow]).
            v5_exerciseActive = v5ExerciseActive(activityResult.activityState),
            v5_inPostExerciseWindow = v5InPostExerciseWindow(postExerciseRecoveryEnabled, now, recoveryWindowEnd),
            v5_exerciseSubclass = activityResult.activityState,
        )

        aapsLogger.debug(LTag.APS, ">>> Invoking determine_basal Boost <<<")
        aapsLogger.debug(LTag.APS, "Glucose status:     $glucoseStatus")
        aapsLogger.debug(LTag.APS, "Current temp:       $currentTemp")
        aapsLogger.debug(LTag.APS, "IOB data:           ${iobArray.joinToString()}")
        aapsLogger.debug(LTag.APS, "Profile:            $oapsProfile")
        aapsLogger.debug(LTag.APS, "Autosens data:      $autosensResult")
        aapsLogger.debug(LTag.APS, "Meal data:          $mealData")
        aapsLogger.debug(LTag.APS, "MicroBolusAllowed:  $microBolusAllowed")
        aapsLogger.debug(LTag.APS, "flatBGsDetected:    $flatBGsDetected")
        aapsLogger.debug(LTag.APS, "BoostActive:        ${activityResult.boostActive}")

        // v4.4.3 hotfix Fix B (ported to V1 2026-06-01): compute cumulative SMB volume delivered
        // in the last 60 min. Pulled from PersistenceLayer rather than synthesised from IOB —
        // IOB is decay-adjusted, but the rolling-window cap wants raw delivered amounts.
        // Filters to BS.Type.SMB so manual user boluses don't contribute.
        val cumulativeSmbCap60Min = preferences.getBoostDosing(DoubleKey.ApsBoostCumulativeSmbCap60Min)
        // v12 ML uses both the 60-min volume (already used by the cap) and the
        // minutes-since-last-SMB. Query a wider 12-hr window once and derive both.
        val (recentSmbVolume60Min, timeSinceLastSmbMin) = try {
            val twelveHrAgo = now - 12 * 60 * 60 * 1000L
            val smbs = persistenceLayer.getBolusesFromTimeToTime(twelveHrAgo, now, ascending = false)
                .filter { it.type == BS.Type.SMB && it.isValid }
            val sixtyMinAgo = now - 60 * 60 * 1000L
            val sum60 = smbs.filter { it.timestamp >= sixtyMinAgo }.sumOf { it.amount }
            val tSince = smbs.firstOrNull()?.let {
                kotlin.math.min(720.0, (now - it.timestamp) / 60_000.0)
            } ?: 720.0
            Pair(sum60, tSince)
        } catch (e: Exception) {
            // FAIL CLOSED (2026-07-02): a DB failure must not disarm the anti-stacking cap — treat the
            // 60-min volume as AT the cap so both V1's internal cap and the V5-override re-check
            // suppress SMB this cycle (basal control continues; SMBs resume when the query recovers).
            // Previously fell open to 0.0 ("cap will not engage this cycle") — the backstop vanished
            // exactly when state was already degraded. tSince stays 720 (neutral ML feature).
            aapsLogger.error(LTag.APS, "Boost V1 recent SMB volume query failed (${e.message}) — FAIL CLOSED: treating 60-min volume as at-cap; SMB suspended this cycle")
            Pair(if (cumulativeSmbCap60Min > 0.0) cumulativeSmbCap60Min else 0.0, 720.0)
        }
        aapsLogger.debug(LTag.APS, "Boost V1 cumulative SMB last 60min: ${recentSmbVolume60Min}U / cap ${cumulativeSmbCap60Min}U | minutes-since-last-SMB: ${timeSinceLastSmbMin}")

        // v12 ML lookback ring buffer — restore from storage once per process so the
        // lag0..lag5 windowed features survive an AAPS restart instead of cold-starting
        // (zero-imputed) for the first ~6 cycles. No-op after the first cycle.
        determineBasalBoost.loadMlRingBufferOnce(preferences.getBoostDosing(StringKey.ApsBoostMlRingBuffer))

        // ── Post-rescue TIGHT-RAMP trial arm (2026-08-03, pre-registered crossover) ──
        // Enrolment is an explicit per-user preference; the arm is a pure function of a
        // once-generated install seed and the LOCAL day index, so the offline analysis can
        // reproduce every day's assignment from the seed alone. Treatment days cap the
        // post-rescue scale at 0.60 and apply it across the whole window; control days run the
        // shipped guard untouched. Neither arm can dose above today's behaviour.
        val tightRampCap: Double? = if (preferences.getBoostDosing(BooleanKey.ApsBoostPostRescueTightRampTrial)) {
            var seed = preferences.getBoostDosing(StringKey.ApsBoostTrialSeed)
            if (seed.isEmpty()) {                       // first cycle after enrolment
                seed = java.util.UUID.randomUUID().toString()
                preferences.put(StringKey.ApsBoostTrialSeed, seed)
                aapsLogger.info(LTag.APS, "Post-rescue tight-ramp trial: seed generated, enrolled")
            }
            val dayIndex = java.time.Instant.ofEpochMilli(now)
                .atZone(java.time.ZoneId.systemDefault()).toLocalDate().toEpochDay()
            if (DetermineBasalBoost.tightRampArm(seed, dayIndex)) DetermineBasalBoost.TIGHT_RAMP_CAP else null
        } else null

        determineBasalBoost.determine_basal(
            glucose_status = glucoseStatus,
            currenttemp = currentTemp,
            iob_data_array = iobArray,
            profile = oapsProfile,
            autosens_data = autosensResult,
            meal_data = mealData,
            microBolusAllowed = microBolusAllowed,
            currentTime = now,
            flatBGsDetected = flatBGsDetected,
            // Layer A ML retrofit — models compute scores that are emitted to NS
            // via RT.mlHypoRisk / RT.mlMealLikely. Dosing behaviour unchanged.
            riskModel = boostRiskModel,
            mealModel = boostMealModel,
            recentSmbVolume60Min = recentSmbVolume60Min,
            cumulativeSmbCap60Min = cumulativeSmbCap60Min,
            recentLowBG45Min = recentLowBG45Min,
            timeSinceLastSmbMin = timeSinceLastSmbMin,
            postRescueTightRampCap = tightRampCap
        ).also {
            // Trial arm tag, every cycle (not only when the guard fires), so the analysis can
            // count exposure on days the guard never engaged. enrolled,arm,cap.
            it.reason.append(
                "prTrial=${if (preferences.getBoostDosing(BooleanKey.ApsBoostPostRescueTightRampTrial)) 1 else 0}," +
                    "${if (tightRampCap != null) "tight" else "control"},${tightRampCap ?: 0.0}; ")
            // ISF shadow telemetry — V1's actual variable_sens used the instantaneous
            // ratio = tdd24/tdd7; V4.4.2 would use an EMA(τ=3h) of the same. Compute
            // the implied shadow values for direct comparison:
            //   variable_sens_v442 = variable_sens_v1 × (ratio_v1 / ratio_ema)
            //   insulinReq_v442    = insulinReq_v1    × (ratio_ema / ratio_v1)
            //   microBolus_v442    ≈ microBolus_v1   × (ratio_ema / ratio_v1)
            // (microBolus is exact for T1/T2/T5/T8 which compute it as insulinReq/X;
            // approximate but directionally right for T3/T4/T6/T7 which use scaled
            // boostInsulinReq paths.)
            val shadow = isfResult.tddSensShadow
            if (shadow != null && isfResult.ratio > 0.0 && shadow.ratio > 0.0) {
                val scale = isfResult.ratio / shadow.ratio
                it.isfShadow_ratioRaw = Round.roundTo(shadow.raw, 0.001)
                it.isfShadow_ratioEma = Round.roundTo(shadow.ratio, 0.001)
                it.isfShadow_warmup = Round.roundTo(shadow.warmupFraction, 0.01)
                it.isfShadow_variableSens = Round.roundTo(isfResult.variableSens * scale, 0.1)
                it.isfShadow_deltaPct = Round.roundTo((scale - 1.0) * 100.0, 0.01)
                it.insulinReq?.let { ir ->
                    it.isfShadow_insulinReq = Round.roundTo(ir / scale, 0.001)
                }
                it.units?.let { u ->
                    it.isfShadow_microBolus = Round.roundTo(u / scale, 0.001)
                }
            }

            // Volume-weighted dose shadow. Read-only: the blend it proposes and the working
            // behind it, so the paired estimates accumulate from the first cycle.
            isfResult.vwaTddShadow?.let { v ->
                it.boostVwa_blend = Round.roundTo(v.vwaBlend, 0.01)
                it.boostVwa_projection = Round.roundTo(v.projection, 0.01)
                it.boostVwa_expected = Round.roundTo(v.expectedToday, 0.01)
                it.boostVwa_delivered = Round.roundTo(v.deliveredToday, 0.01)
                it.boostVwa_dayFraction = Round.roundTo(v.dayFraction, 0.001)
                it.boostVwa_calibratedTdd = Round.roundTo(v.calibratedTdd, 0.01)
                it.boostVwa_curveDays = v.curveDays
                it.boostVwa_usedPrevDay = v.usedPreviousDay
            }
            // Persist the v12 ML lookback ring buffer (updated in-place during this
            // cycle's inference) so the lag features survive a process restart.
            preferences.put(StringKey.ApsBoostMlRingBuffer, determineBasalBoost.serializeMlRingBuffer())
            // V5 — runs BEFORE EventAPSCalculationFinished. In SHADOW mode (toggle off) V5 only
            // attaches boostV5_* telemetry. In ACTIVE mode (ApsBoostV5ActiveDosing) V5's finalDose
            // REPLACES V1's SMB on cycles V1 permits one (microBolusAllowed) — V1 still owns basal,
            // predictions and every safety gate; the overridden rT.units flows through downstream
            // pump/bolus constraints unchanged. runShadow returns null on internal error → V1's
            // dose is left intact. V5 can never raise the dose above its own caps + maxIOB clamp.
            // Prior-cycle sleep state (updated end-of-invoke). Passed into V5 so the fast-carb
            // fast-path is gated OFF overnight, and reused below for the dose-level sleep gate.
            val v5Asleep = sleepStateCached.state == SleepStateDetector.SleepState.SLEEPING
            // Post-rescue window (2026-07-04; hoisted above runShadow 2026-07-06 so V5's composed-floor
            // shadow can read it) — the SAME source value (recentLowBG45Min, computed once in step 6
            // above and passed into determine_basal) and the SAME shared threshold as V1's Fix A v2
            // post-rescue tier guard, so this flag is true exactly when V1's own dose is the
            // hypo-restrained one. Logged every cycle as boostV5_postRescueWindow (shadow and active)
            // so the 2026-07-10 live review can audit windows without CGM reconstruction.
            val inPostRescueWindow = recentLowBG45Min < DetermineBasalBoost.POST_RESCUE_LOW_THRESHOLD_MGDL
            it.boostV5_postRescueWindow = inPostRescueWindow
            // Cumulative-cap telemetry (2026-07-06): the rolling-60-min anti-stacking cap and the
            // volume it compares against were previously invisible in NS — a cap suppression looked
            // identical to a zero-dose decision (2026-07-06 forensic). Written EVERY Boost cycle
            // (shadow + active); the same recentSmbVolume60Min already computed above (fail-closed
            // to at-cap on DB error, so the telemetry mirrors the operative value exactly).
            it.boostV5_cumulativeCapU = cumulativeSmbCap60Min
            it.boostV5_smbVol60Min = recentSmbVolume60Min
            val v5decision = try {
                boostV5Plugin.get().runShadow(
                    rT = it,
                    glucoseStatus = glucoseStatus,
                    iobArray = iobArray,
                    oapsProfile = oapsProfile,
                    pumpBolusStep = activePlugin.activePump.pumpDescription.bolusStep,
                    activeMode = v5Active,
                    microBolusAllowed = microBolusAllowed,
                    flatBGsDetected = flatBGsDetected,
                    asleep = v5Asleep,
                    postRescueWindow = inPostRescueWindow
                )
            } catch (t: Throwable) {
                aapsLogger.error(LTag.APS, "V5 shadow invocation failed", t)
                null
            }
            // ── V7 SHADOW (2026-07) — read-only instrument for the REVISED distributional-sizing
            // formulation after the offline NO-GO (backtesting/reports/2026-07_v7_foundation_REPORT.md;
            // see openAPSBoostV7/V7_SHADOW.md for the two acceptance criteria it instruments).
            // Placement is load-bearing: AFTER V5's runShadow (so the V5 state/budget this cycle are
            // available) and BEFORE the V6 override seam below (so it.units here is STILL V1's
            // would-dose — the sizer's non-meal/post-rescue v1-bound). Writes ONLY boostV7_* telemetry
            // + a reason breadcrumb when the R-doses differ; delivered dosing is bit-identical with or
            // without it. Failure-swallowed twice (V7Shadow's own runCatching + this belt-and-braces
            // one) — the shadow can NEVER break a loop cycle.
            runCatching {
                v7Shadow.runCycle(
                    rT = it,
                    bg = glucoseStatus.glucose,
                    delta = glucoseStatus.delta,
                    shortAvgDelta = glucoseStatus.shortAvgDelta,
                    iobActivity = iobArray.firstOrNull()?.activity ?: 0.0,
                    variableSens = it.variable_sens,
                    profileSens = oapsProfile.sens,
                    v5State = v5decision?.mealHypothesis,
                    v5BudgetU = v5decision?.aggressionBudget?.budget,
                    v1WouldDoseU = it.units,
                    committedCapU = preferences.get(DoubleKey.ApsBoostV5CommittedCapU),
                    confirmedCapU = preferences.get(DoubleKey.ApsBoostV5ConfirmedCapU),
                    postRescueWindow = inPostRescueWindow,
                    cumulativeCapU = cumulativeSmbCap60Min,
                    smbVol60MinU = recentSmbVolume60Min,
                    nowMs = now,
                    hour = java.time.Instant.ofEpochMilli(now).atZone(java.time.ZoneId.systemDefault()).hour,
                )
            }.onFailure { t -> aapsLogger.error(LTag.APS, "V7 shadow invocation failed (swallowed)", t) }
            // KAIROS Twin shadow (2026-07-18): assimilate this cycle's CGM + insulin into the
            // physiological EnKF and log a calibrated 30/60-min forecast + the inferred glucose
            // appearance. READ-ONLY — writes only boostTwin_* telemetry; the delivered dose is
            // untouched. Insulin this cycle = boluses(last 5 min) + basal (temp-adjusted). Belt-and-
            // braces runCatching on top of TwinShadow's own — the shadow can NEVER break a cycle.
            runCatching {
                val fiveMinAgo = now - 5L * 60 * 1000
                val bolusU = persistenceLayer.getBolusesFromTimeToTime(fiveMinAgo, now, true).sumOf { b -> b.amount }
                val tb = persistenceLayer.getTemporaryBasalActiveAt(now)
                val basalRate = when {
                    tb == null    -> oapsProfile.current_basal
                    tb.isAbsolute -> tb.rate
                    else          -> oapsProfile.current_basal * tb.rate / 100.0
                }
                val basalU = basalRate * 5.0 / 60.0
                // Assimilate what WAS delivered this cycle (bolus + active basal), but forecast under
                // the SCHEDULED (profile) basal, not the currently-active temp: a transient correction
                // temp must not be projected forward for the whole 30–60 min horizon (that ran the
                // open-loop forecast cold/warm and mis-fired the lo30 floor). Fidelity fix 2026-07-18;
                // second-order in practice (basal dosed now barely acts within the horizon, and the
                // off-policy test found the Twin's insulin gain is weak/unidentified — see
                // backtesting/2026-07-kairos-twin/TWIN_OFFPOLICY.md).
                val scheduledBasalU = oapsProfile.current_basal * 5.0 / 60.0
                val fc = twinShadow.runCycle(glucoseStatus.glucose, bolusU + basalU, scheduledBasalU)
                if (fc != null) {
                    // Ride in the reason string, NOT a new RT field (see RT KDoc — the legacy V3MLG3
                    // ART verifier limit). The extractor parses "twin=...;" back into DB columns.
                    // idea-4 shadow (2026-07-18): lo30 (30-min forecast FLOOR) is the actionable hypo
                    // signal — validated to catch real lows at ⅓–½ the false-alarm rate of oref's
                    // minGuardBG/minPredBG (backtesting/2026-07-kairos-twin/TWIN_HYPO_LEAD.md). floorbreach
                    // = the would-withhold-this-cycle trigger (lo30 < 70 mg/dL). LOGGED, NOT APPLIED —
                    // pure telemetry; the withdrawal ACTION is the policy leg (shadow-first, auto-config-
                    // managed when built). lo60 is NOT actionable (band too wide — cries wolf, FA 0.56).
                    val floorBreach = if (fc.lo30 < 70.0) 1 else 0
                    it.reason.append("twin=${fc.fc30},${fc.fc60},${fc.lo60},${fc.hi60},${fc.raMean},${fc.filteredGi}," +
                        "${Round.roundTo(bolusU + basalU, 0.001)},${fc.lo30},$floorBreach; ")
                    // Anticipatory back-out shadow: run the retractable-anticipation state machine off the
                    // Twin's Ra + BG. ARM on the accelMeal onset detector (the best onset cue from signal
                    // digging) with mlMealLikely retained as a secondary OR-trigger; armSrc is logged so the
                    // two are compared on banked data (2026-07-20 ACCELMEAL_ARM_SPEC.md). READ-ONLY. The arm
                    // computation duplicates the accelMeal block below by design, to keep the two shadows'
                    // failure isolation independent — a fault here degrades to no-arm, never breaks a cycle.
                    val accelArm = runCatching {
                        val accel = glucoseStatus.shortAvgDelta - glucoseStatus.longAvgDelta
                        val rising = glucoseStatus.delta > 0.0 || glucoseStatus.shortAvgDelta > 0.0
                        val preConfirm = v5decision?.mealHypothesis == null ||
                            v5decision.mealHypothesis == MealHypothesis.IDLE ||
                            v5decision.mealHypothesis == MealHypothesis.OBSERVING
                        accel > 2.0 && rising && preConfirm
                    }.getOrDefault(false)
                    runCatching {
                        backoutShadow.runCycle(now, glucoseStatus.glucose, fc.raMean, fc.lo30, it.mlMealLikely, accelArm)
                            ?.let { p -> it.reason.append("antBackout=$p; ") }
                    }.onFailure { t -> aapsLogger.error(LTag.APS, "Back-out shadow failed (swallowed — dosing untouched)", t) }
                }
            }.onFailure { t -> aapsLogger.error(LTag.APS, "KAIROS Twin shadow failed (swallowed — dosing untouched)", t) }
            // Acceleration-based early-meal-detection SHADOW (2026-07-20). Signal digging over all Boost
            // data found BG ACCELERATION (curvature) is the one signal worth adding: it detects an
            // unannounced meal ~5 min before the delta-based confirm (and improves the forecaster). accel =
            // shortAvgDelta − longAvgDelta (>0 = the rise is accelerating). Flags a would-be EARLIER
            // meal-confirm when acceleration + a rise are present but the state has not CONFIRMED yet.
            // READ-ONLY — logs accelMeal=; delivers NOTHING (shadow-first; a live earlier-confirm is a
            // dosing change → two-test bar). Banks the on-device lead + false-alarm to price it.
            runCatching {
                val accel = glucoseStatus.shortAvgDelta - glucoseStatus.longAvgDelta
                val rising = glucoseStatus.delta > 0.0 || glucoseStatus.shortAvgDelta > 0.0
                val preConfirm = v5decision?.mealHypothesis == null ||
                    v5decision.mealHypothesis == MealHypothesis.IDLE ||
                    v5decision.mealHypothesis == MealHypothesis.OBSERVING
                val trig = if (accel > 2.0 && rising && preConfirm) 1 else 0
                it.reason.append("accelMeal=$trig,${Round.roundTo(accel, 0.1)},${Round.roundTo(glucoseStatus.shortAvgDelta, 0.1)}," +
                    "${Round.roundTo(glucoseStatus.longAvgDelta, 0.1)},${glucoseStatus.glucose.toInt()},${v5decision?.mealHypothesis ?: "?"}; ")
            }.onFailure { t -> aapsLogger.error(LTag.APS, "Accel-meal shadow failed (swallowed — dosing untouched)", t) }
            // Consequence prior SHADOW (2026-08-26). Logs a probability that this rise ends
            // somewhere that matters, from glucose at the onset and the local hour. READ-ONLY.
            // Included because the engine's own projection is at chance on that question (0.527
            // against a 0.398 base rate on 27,619 onsets) while these two numbers reach 0.763, and
            // adding the whole engine record to them is worth +0.001. Delivers NOTHING; a dose
            // sized on this is a dosing change and goes to the two-test bar.
            runCatching {
                consequenceShadow.runCycle(now, glucoseStatus.glucose)
                    ?.let { p -> it.reason.append("conseq=$p; ") }
            }.onFailure { t -> aapsLogger.error(LTag.APS, "Consequence-prior shadow failed (swallowed — dosing untouched)", t) }
            // Fall-consequence SHADOW (2026-09-03). Twenty minutes into a fall, is this one
            // reaching 70 mg/dL within two hours? Offline it reaches AUC 0.780 on the sixteen Boost
            // participants, none of whom contributed a training row, against 0.746 for glucose at
            // onset plus the clock, and it is better for all sixteen. Restricted to onsets still
            // above 70 at the moment of scoring, which is where a controller could still act, it is
            // 0.760 against 0.723.
            //
            // The onset rule here is STRICTER than the one that built the training anchors: those
            // allowed the 25 mg/dL drop to arrive within thirty minutes, which is only knowable
            // thirty minutes late. This wants it within twenty, so every onset found here would
            // also have been an anchor offline while some anchors will be missed. Measuring that
            // shortfall is the shadow's first job, which is why the tag carries the onset age and
            // the fall size rather than the score alone.
            //
            // Rides in [reason] rather than on RT: one more field on that class costs one register
            // in every determine_basal and the V3MLG3 one has none left. Delivers NOTHING.
            runCatching {
                val since = now - 70 * 60 * 1000L
                val rows = persistenceLayer.getBgReadingsDataFromTimeToTime(since, now, true)
                if (rows.size >= 4) {
                    val times = LongArray(rows.size) { rows[it].timestamp }
                    val values = DoubleArray(rows.size) { rows[it].value }
                    fallConsequenceShadow.evaluate(times, values) { tsMs ->
                        val z = java.time.ZonedDateTime.ofInstant(
                            java.time.Instant.ofEpochMilli(tsMs), java.time.ZoneId.systemDefault())
                        z.hour + z.minute / 60.0 + z.second / 3600.0
                    }?.let { r ->
                        it.reason.append(
                            "fallcon=${Round.roundTo(r.score, 0.001)},${r.onsetAgeMin}," +
                                "${Round.roundTo(r.onsetBg, 0.1)},${Round.roundTo(r.fall, 0.1)}," +
                                "${if (r.stillFalling) 1 else 0}; "
                        )
                    }
                    // A shadow that never fires looks exactly like a quiet day, and did for two
                    // days. On the cycles that produce no score, say which test rejected it.
                    if (fallConsequenceShadow.lastSkip != "ok") {
                        it.reason.append("fallconskip=${fallConsequenceShadow.lastSkip},${rows.size}; ")
                    }
                } else {
                    it.reason.append("fallconskip=norows,${rows.size}; ")
                }
            }.onFailure { t -> aapsLogger.error(LTag.APS, "Fall-consequence shadow failed (swallowed — dosing untouched)", t) }
            // Sleep gate (2026-06-14): do NOT let V5 drive the SMB while SLEEPING — fall back to V1's
            // (oref1/Boost) SMB, which already respects night mode. V5 still computes its shadow
            // telemetry above (runShadow ran), so the V5-vs-V1 comparison continues overnight; only
            // the dose override is suppressed. Robust to overnight CGM artifacts tripping V5.
            // Anti-stacking hard gate: the rolling-60-min cumulative SMB cap is enforced inside V1
            // (DetermineBasalBoost), but the V5 override below replaces it.units AFTER determine_basal
            // returns — so re-check the SAME cap here (same prior-volume semantics as V1) or V5 could
            // deliver on a cycle V1 suspended for cumulative volume. (Review 2026-06-26, MEDIUM.)
            val cumulativeCapReached = cumulativeSmbCap60Min > 0.0 && recentSmbVolume60Min >= cumulativeSmbCap60Min
            // Boost-inactive gate (2026-07-02): the V6/V5 override may replace the SMB ONLY when Boost
            // is active this cycle. When boostActive is false — night/sleep period, high temp target, or
            // the step-based sleep-in has fired — fall back to V1's base oref1 SMB (which respects night
            // mode + its own hypo/minGuard gates) instead of the amplified V5 dose. Without this, a
            // genuinely-asleep, zero-step cycle could still receive a full V5 meal-amplified bolus,
            // because v5Asleep reflects ONLY the HR sleep-state machine, never the boost-window gate.
            if (v5Active && microBolusAllowed && v5decision != null && !v5Asleep && !cumulativeCapReached && activityResult.boostActive) {
                val v1WouldDose = it.units ?: 0.0
                // Non-meal-state cap (2026-07-02): V6 may only OUT-dose V1 when it holds a meal
                // hypothesis (CONFIRMED/COMMITTED). In IDLE/OBSERVING/RECOVERING the V5 state caps
                // don't apply (applyStateDoseCap passes them through) and IDLE's 1.0× multiplier can
                // front a multi-unit correction that bypasses V1's per-SMB sizing — 5-month cohort
                // shadow data: ~1,430U cumulative IDLE excess over V1, worst 3.7U vs 0.45U at BG 210,
                // incl. 2.0U at 05:02 where V1 dosed 0. Capping at V1's would-dose makes IDLE match
                // its own spec ("standard oref dose; no meal hypothesis"); genuine meal rises still
                // get full V6 dosing via OBSERVING→CONFIRMED.
                // 2026-07-17 velocity-budget floor exemption: when the ACTIVE velocity-budget floor
                // lifted this cycle's dose (velocityBudgetExempt), treat it as a meal state so the
                // floored hold can out-dose V1 on the budget≈0 high tail (V1 doses ~0 there). Safe by
                // construction: the exempt dose is committedCap + maxIOB bounded, the floor requires
                // !postRescueWindow, and the cumulative-60min / boost-active / sleep gates all still run.
                // 2026-07-20 V1-acceleration primer (bolus mode): the OBSERVING primer is already folded
                // into finalDose and floored/netted in-engine, so exempt it from the non-meal v1-cap
                // (it must out-dose V1's OBSERVING dose — that IS the reclaimed early insulin). The
                // primer's own floors (recentLow≥80, !postRescue, awake, !exercise, maxIOB) ran in-engine;
                // the cumulative-60min/sleep/boost-active seam guards above still apply.
                val inMealState = v5decision.mealHypothesis == MealHypothesis.CONFIRMED ||
                    v5decision.mealHypothesis == MealHypothesis.COMMITTED ||
                    v5decision.velocityBudgetExempt ||
                    (v5decision.primerBolusU > 0.0 && !v5decision.primerUseTempBasal)
                // Post-rescue meal-state cap (2026-07-04): inside the post-rescue window the meal-state
                // exemption is suppressed and CONFIRMED/COMMITTED are ALSO capped at V1's would-dose —
                // which is hypo-restrained by V1's aligned tier guard (same value, same threshold; see
                // applyV6OverrideCaps KDoc for the 2026-07-03 nadir-40 incident + backtest evidence:
                // 27% of the removed insulin sits ahead of a second low <70 vs 14-19% for other levers;
                // cost 10% genuine post-hypo meals at 0.15U median under-delivery).
                val caps = applyV6OverrideCaps(inMealState, inPostRescueWindow, v5decision.finalDose, v1WouldDose, recentLowBG45Min)
                var overrideDose = caps.dose
                // 2026-08-27 confirm tranche. Split the confirm commitment: part now, the rest ten
                // minutes later only if the rise continues. The confirm shot is currently the same
                // size whether the excursion reaches 20 mg/dL or 100, and the trace separates those
                // two ends at 0.730 at the confirming cycle against 0.893 ten minutes on, a paired
                // gain of +0.162 [+0.066, +0.264]. Bounded: this can only deliver LESS than the
                // engine would without it.
                //
                // The release is evaluated inside this same block deliberately. Ten minutes after a
                // confirm the block runs on 76.4% of cycles, and the 23.6% where it does not divide
                // into exactly two causes, the rolling cumulative SMB cap and the sleep gate, both
                // of which are states in which the engine has already decided against a micro bolus.
                // A release that cannot land is that machinery agreeing with the withhold.
                if (preferences.getBoostDosing(BooleanKey.ApsBoostV5ConfirmTranche)) {
                    confirmTranche.immediateFraction = preferences.getBoostDosing(DoubleKey.ApsBoostV5TrancheFraction)
                    confirmTranche.releaseThreshold = preferences.getBoostDosing(DoubleKey.ApsBoostV5TrancheThreshold)
                    val before = overrideDose
                    overrideDose = if (v5decision.mealHypothesis == MealHypothesis.CONFIRMED) {
                        confirmTranche.onConfirm(now, glucoseStatus.glucose, before)
                    } else {
                        before + confirmTranche.onCycle(now, glucoseStatus.glucose)
                    }
                    it.reason.append("tranche=${Round.roundTo(before, 0.001)},"
                        + "${Round.roundTo(overrideDose, 0.001)},"
                        + "${Round.roundTo(confirmTranche.heldU(), 0.001)},"
                        + "${confirmTranche.probeProbability(glucoseStatus.glucose)?.let { p -> Round.roundTo(p, 0.001) } ?: "-"},"
                        + "${v5decision.mealHypothesis}; ")
                }
                it.units = overrideDose
                it.reason.append("V6-ACTIVE drove SMB ${Round.roundTo(overrideDose, 0.001)}U (base would=${Round.roundTo(v1WouldDose, 0.001)}U, state=${v5decision.mealHypothesis}${caps.capNote}); ")
                aapsLogger.info(LTag.APS, "V6-ACTIVE override: SMB ${v1WouldDose} → ${overrideDose} state=${v5decision.mealHypothesis}${caps.capNote}")
                // 2026-07 composed brake-floor breadcrumb: when the Advanced toggle is ON,
                // decision.floorWouldAdd carries the uplift the floor actually APPLIED (active
                // semantics — see V5Decision KDoc). Log the un-floored→floored delivery so a
                // floored cycle is auditable straight from the reason line. Whenever the uplift
                // is > 0 the floored dose is inside every seam cap by construction (RECOVERING
                // v1-bound + !postRescueWindow are conditions of the floor itself), so
                // overrideDose == v5decision.finalDose here and X→Y is the delivered truth.
                val floorUplift = if (preferences.getBoostDosing(BooleanKey.ApsBoostV5ComposedFloorActive)) v5decision.floorWouldAdd ?: 0.0 else 0.0
                if (floorUplift > 0.0) {
                    it.reason.append("brake-floor applied: ${Round.roundTo(v5decision.finalDose - floorUplift, 0.001)}→${Round.roundTo(v5decision.finalDose, 0.001)} U; ")
                    aapsLogger.info(LTag.APS, "V6 brake-floor applied: ${Round.roundTo(v5decision.finalDose - floorUplift, 0.001)}→${Round.roundTo(v5decision.finalDose, 0.001)} U")
                }
                // 2026-07-17 velocity-budget floor breadcrumb: when ON, decision.velocityBudgetWouldAdd
                // carries the uplift actually APPLIED (out-dosing V1 on the budget≈0 tail via the
                // non-meal-cap exemption). overrideDose == v5decision.finalDose here (the exemption made
                // inMealState true), so X→Y is the delivered truth.
                val vbUplift = if (preferences.getBoostDosing(BooleanKey.ApsBoostV5VelocityBudgetActive)) v5decision.velocityBudgetWouldAdd ?: 0.0 else 0.0
                if (vbUplift > 0.0) {
                    it.reason.append("velocity-budget floor applied: ${Round.roundTo(v5decision.finalDose - vbUplift, 0.001)}→${Round.roundTo(v5decision.finalDose, 0.001)} U (base insulinReq≈0); ")
                    aapsLogger.info(LTag.APS, "V6 velocity-budget floor applied: ${Round.roundTo(v5decision.finalDose - vbUplift, 0.001)}→${Round.roundTo(v5decision.finalDose, 0.001)} U")
                }
                // ===== 2026-07-20 V1-acceleration early primer delivery + breadcrumb =====
                if (v5decision.primerBolusU > 0.0) {
                    if (v5decision.primerUseTempBasal) {
                        // RETRACTABLE temp-basal fallback (hypo-prone routing): deliver ~primerBolusU over
                        // a short window as a raise ABOVE scheduled basal — additive-only. NEVER fires when
                        // the base engine is suspending/reducing (it.rate < current_basal): a protective
                        // low/zero temp always wins. Never lowers what the base engine already planned
                        // (max), and never shortens its duration. Expires (retracts) if the meal fades.
                        val primerTbrDurationMin = 30
                        val curBasal = oapsProfile.current_basal
                        val baseRate = it.rate
                        val extraRate = v5decision.primerBolusU * (60.0 / primerTbrDurationMin)
                        val primerRate = curBasal + extraRate
                        when {
                            // Base engine suspending/reducing — a protective low/zero temp always wins.
                            baseRate != null && baseRate < curBasal ->
                                it.reason.append("primer=tbr-skipped(base-temp ${Round.roundTo(baseRate, 0.001)}<basal ${Round.roundTo(curBasal, 0.001)}); ")
                            // Base engine already delivering ≥ the primer rate — primer adds nothing; do
                            // NOT touch its rate/duration (extending a high base temp would over-deliver).
                            baseRate != null && baseRate >= primerRate ->
                                it.reason.append("primer=tbr-subsumed(base ${Round.roundTo(baseRate, 0.001)}≥primer ${Round.roundTo(primerRate, 0.001)}U/h); ")
                            // Primer genuinely raises above the base plan → apply the retractable temp.
                            else -> {
                                it.rate = primerRate
                                it.duration = kotlin.math.max(it.duration ?: 0, primerTbrDurationMin)
                                it.reason.append("primer=tbr,${Round.roundTo(v5decision.primerBolusU, 0.001)}U→${Round.roundTo(primerRate, 0.001)}U/h×${it.duration}m; ")
                                aapsLogger.info(LTag.APS, "V6 primer (temp-basal): ${v5decision.primerBolusU}U → ${primerRate}U/h x ${it.duration}min")
                            }
                        }
                    } else {
                        // Bolus mode: already folded into the SMB above (finalDose) + exempted from the
                        // non-meal cap. Just log the reclaimed early insulin.
                        // 2026-07-30: if auto-config RECOMMENDED the retractable temp-basal route and the
                        // user has overridden it to a bolus, say so in the reason. The override is always
                        // honoured — auto-config never makes a setting unreachable — but an overridden
                        // routing must be VISIBLE in the data, because it is the difference between a
                        // primer the loop can unwind and one it cannot. Both live primer users had
                        // silently overridden, which is why the 2026-07-29 incident could not be undone.
                        val routeOverridden = preferences.getBoostDosing(BooleanKey.ApsBoostV5PrimerTbrFallback) &&
                            preferences.getBoostDosing(BooleanKey.ApsBoostV5PrimerBolusMode)
                        it.reason.append("primer=bolus,${Round.roundTo(v5decision.primerBolusU, 0.001)}U" +
                            (if (routeOverridden) ";primerRoute=bolus-USER-OVERRIDE(recommended=tbr)" else "") + "; ")
                        aapsLogger.info(LTag.APS, "V6 primer (bolus): ${v5decision.primerBolusU}U folded into SMB" +
                            if (routeOverridden) " [user override of recommended temp-basal routing]" else "")
                    }
                }
                // 2026-07-30 primer sizing telemetry. Emitted whenever the primer GATE opened — including
                // when the state factors sized it to nothing and it rounded to 0U (primerBolusU == 0, so
                // the block above is skipped). Without this the shadow cannot tell "gate never opened"
                // from "gate opened, correctly sized to zero", which is the whole point of the rework.
                if (v5decision.primerScaleDebug.isNotEmpty()) {
                    it.reason.append("primerScale=${v5decision.primerScaleDebug}" +
                        (if (v5decision.primerBolusU <= 0.0) ",ROUNDED_TO_ZERO" else "") + "; ")
                }
            } else if (v5Active && v5decision != null && cumulativeCapReached) {
                it.units = 0.0
                it.reason.append("V6 suppressed (cumulative SMB cap ${Round.roundTo(recentSmbVolume60Min, 0.01)}U/${Round.roundTo(cumulativeSmbCap60Min, 0.01)}U reached); ")
                aapsLogger.info(LTag.APS, "V6-ACTIVE cumulative SMB cap reached (${recentSmbVolume60Min}/${cumulativeSmbCap60Min}U) — SMB suspended")
            } else if (v5Active && v5Asleep && v5decision != null) {
                it.reason.append("V6 suppressed (SLEEPING) — base SMB ${Round.roundTo(it.units ?: 0.0, 0.001)}U; ")
            } else if (v5Active && v5decision != null && !activityResult.boostActive) {
                it.reason.append("V6 override skipped (Boost inactive) — base SMB ${Round.roundTo(it.units ?: 0.0, 0.001)}U; ")
                aapsLogger.info(LTag.APS, "V6-ACTIVE override skipped — Boost inactive; base oref1 SMB ${it.units ?: 0.0}U retained")
            }

            // Post-meal PLATEAU-NUDGE shadow (2026-07-19) — READ-ONLY, delivers NOTHING.
            // Finding: V6 under-recovers — it parks post-meal glucose at ~145-150 for hours
            // (backtesting/2026-07-descent ff1). The per-cycle plateau low is UNFORECASTABLE (dr3:
            // no signal — Twin forecast/floor/slope, oref minGuard/minPred, BG/IOB/trend — clears
            // chance out-of-sample, best OOS AUC 0.55). So the lever is a base-rate + small-dose +
            // hard-floor rule, per-user auto-config-gated in the active version (see
            // backtesting/scripts/2026-07-v6-descent/PLATEAU_NUDGE_SPEC.md). This SHADOW logs the
            // would-nudge + trigger/floor state via a `plateau=` reason tag so it can be banked +
            // priced on-device before it ever doses. Belt-and-braces runCatching — never breaks a cycle.
            runCatching {
                val plateauNudgeU = 0.10
                // Lower bound on "flat or falling". Set at -3 mg/dL/5min: the sticky-plateau
                // episodes this targets ran -0.6 to -2.9 (live, 2026-08-02 14:36-15:31 at BG
                // 226-249), while the descents to exclude ran -6 to -25. Provisional — the band
                // should be re-derived from banked data once that data is trustworthy again.
                val PLATEAU_MIN_TREND = -3.0
                val bgMgdl = glucoseStatus.glucose
                val trend = glucoseStatus.shortAvgDelta                       // mg/dL per 5 min
                val iobNow = iobArray.firstOrNull()?.iob ?: 0.0
                val committedCap = preferences.get(DoubleKey.ApsBoostV5CommittedCapU)
                val maxIob = oapsProfile.max_iob
                // oref1's forward-low guard. Read the TYPED value the engine already publishes
                // (DetermineBasalBoost sets rT.minGuardBG in mg/dL) rather than scraping the
                // formatted reason string.
                //
                // 2026-08-04 defect: the previous `Regex("minGuardBG ([0-9.]+)")` could not match a
                // NEGATIVE value — the character class has no minus sign — so on a deep forward-low
                // forecast the match failed, minGuardMgdl was null, and the veto below
                // short-circuited to false. The floor whose entire job is "never nudge into a low"
                // failed OPEN exactly when the forecast was worst. Verified on 4 live cycles
                // (2026-08-02 16:26-16:41, minGuardBG -25.1..-18.6 mmol, the live path HARD-blocking
                // on min_guard_bg while this shadow reported floor="ok"); that descent ended at
                // 55 mg/dL. The magnitude-based mmol heuristic it used is gone with it: it would
                // have multiplied a genuine sub-30 mg/dL value by 18.
                val minGuardMgdl = it.minGuardBG
                // trigger: post-meal plateau — above tight range, flat/falling, insulin on board.
                // SHADOW band widened past the spec's 200 ceiling (2026-07-25): a live stuck-high at
                // 219-247 with IOB ~2 showed insulinReq≈0 above 200 too (eventualBG≈target — the
                // efficacy deficit is invisible to IOB), so bank those episodes as well. The tag
                // records BG, so [145,200) vs [200,250) price separately; the ACTIVE nudge spec
                // band stays [145,200) until the upper band earns its own verdict.
                val inPlateau = bgMgdl in 145.0..249.9 && trend <= 1.7 && iobNow > 0.5
                val nudgeRaw = minOf(plateauNudgeU, committedCap, maxOf(0.0, maxIob - iobNow))
                // hard floors (can only tighten) — never nudge into a low
                val floor = when {
                    !inPlateau                                    -> "n/a"
                    recentLowBG45Min < 75.0                       -> "recent-low"
                    inPostRescueWindow                            -> "post-rescue"
                    cumulativeCapReached                          -> "cum-cap"
                    // FAIL CLOSED: an absent forecast vetoes. A floor that only vetoes when it can
                    // read a value is not a floor.
                    minGuardMgdl == null                          -> "minguard-unknown"
                    minGuardMgdl < 85.0                           -> "minguard"
                    // A steep descent is not a plateau. The trigger's `trend <= 1.7` is unbounded
                    // below, so a -25 mg/dL/5min freefall satisfied it; 8 of 26 live triggers in a
                    // 36-hour sample were on trends steeper than -5, five of them inside the descent
                    // that ended at 55 mg/dL.
                    trend < PLATEAU_MIN_TREND                     -> "falling"
                    v5Asleep || !activityResult.boostActive       -> "not-active"
                    nudgeRaw <= 0.0                               -> "no-headroom"
                    else                                          -> "ok"
                }
                val wouldNudge = if (floor == "ok") nudgeRaw else 0.0
                it.reason.append("plateau=${if (floor == "ok") 1 else 0},${Round.roundTo(wouldNudge, 0.001)}," +
                    "${bgMgdl.toInt()},${Round.roundTo(trend, 0.1)},${Round.roundTo(iobNow, 0.01)}," +
                    "${v5decision?.mealHypothesis ?: "?"},$floor; ")
            }.onFailure { t -> aapsLogger.error(LTag.APS, "Plateau-nudge shadow failed (swallowed — dosing untouched)", t) }

            // Per-user ANTICIPATION shadow (2026-07-27) — READ-ONLY, delivers NOTHING. Records this
            // cycle's exercise/meal onset, refits the per-user habit models offline, predicts p(onset)
            // at a 45-min lead, and runs the two retractable arms in shadow. Appends anticip=... .
            // Belt-and-braces on top of the shadow's own try/catch — can never break a cycle.
            runCatching {
                anticipShadow.runCycle(
                    reason = it.reason,
                    nowMs = now,
                    steps5Min = recentSteps5Min,
                    mealStateName = v5decision?.mealHypothesis?.name,
                    bg = glucoseStatus.glucose,
                    delta = glucoseStatus.delta,
                    inPostRescueWindow = inPostRescueWindow,
                )
            }.onFailure { t -> aapsLogger.error(LTag.APS, "Anticipation shadow invocation failed (swallowed)", t) }

            // V6: surface the anticipatory pre-meal target decision computed earlier this cycle.
            v6PreMealReason?.let { r -> it.reason.append(r) }
            // V6 meal-time learner: record a FRESH CONFIRMED commit (the event V5 treats as a meal)
            // so the pre-meal window learns this user's habitual meal times. Persist only on change.
            if (v5decision != null && v5decision.mealHypothesis == MealHypothesis.CONFIRMED && v5decision.mealHypothesisAge == 0) {
                mealTimeHistoryCached = MealTimeLearner.record(mealTimeHistoryCached, now)
                preferences.put(StringKey.ApsBoostMealTimeHistory, mealTimeHistoryCached.serialize())
                aapsLogger.debug(LTag.APS, "V6 meal-time learner: recorded CONFIRMED @ ${dateUtil.dateAndTimeString(now)} (${mealTimeHistoryCached.events.size} events)")
            }

            // Step-feed availability telemetry (F1, 2026-07-07) — written EVERY cycle so a dark
            // feed is visible in NS ("none" = INACTIVE + sleep-in suppressed this cycle).
            it.boostSteps_feed = activityResult.stepsFeed
            // F6 (2026-07-07): step-feed edge detection — reason-line only (steps degrade
            // gracefully via F1's guard, so no notification; the transition just needs to be
            // findable in NS next to the cycles it affected).
            val prevStepsFeed = lastStepsFeed
            if (prevStepsFeed != null && prevStepsFeed != activityResult.stepsFeed) {
                it.reason.append("stepsFeed: $prevStepsFeed→${activityResult.stepsFeed}; ")
                aapsLogger.info(LTag.APS, "Boost step feed changed: $prevStepsFeed → ${activityResult.stepsFeed}")
            }
            lastStepsFeed = activityResult.stepsFeed

            // 2026-06-02: Sleep state evaluation. Runs at end of invoke so we have
            // mlMealLikely from this cycle. State persists across plugin restarts via
            // StringKey.ApsBoostSleepState. Updates sleepStateCached so the next
            // isNightModeActive() call sees the fresh state.
            try {
                val configuredNightStartMin = parseTimeToMinutesOfDay(preferences.getBoostDosing(StringKey.ApsBoostNightModeStart))
                val configuredNightEndMin = parseTimeToMinutesOfDay(preferences.getBoostDosing(StringKey.ApsBoostNightModeEnd))
                val nowLocal = java.time.LocalTime.now()
                val minOfDay = nowLocal.hour * 60 + nowLocal.minute

                // Auto-tune from learned 28-day history if ≥7 sessions exist; otherwise fall back
                // to configured nightStart / nightEnd.
                val localOffsetMs = java.time.ZoneId.systemDefault().rules.getOffset(java.time.Instant.now()).totalSeconds * 1000L
                val agg = SleepHistoryTracker.aggregate(sleepHistoryCached, localOffsetMs)
                // The learned window may only nudge the configured night window by ±BAND, and the
                // wake side trains on genuine wakes only (see SleepHistoryTracker). Together these
                // anchor the hard sleep/wake bounds to the user's configured times and cap how far
                // learning can move them — preventing the self-reinforcing earlier-every-night
                // collapse seen when the hard-exit fed its own learned wake. No/insufficient data
                // → effective == configured.
                val effectiveNightStartMin = clampToConfiguredBand(agg.sleepStartMinAvg, configuredNightStartMin, LEARNED_WINDOW_BAND_MIN)
                // wake side: one-sided — learning may only push the night-end LATER than configured, never
                // earlier (never lift protection before the user's set wake). See clampToConfiguredBand.
                val effectiveNightEndMin = clampToConfiguredBand(agg.wakeMinAvg, configuredNightEndMin, LEARNED_WINDOW_BAND_MIN, allowEarlier = false)
                // Learned resting HR (sleep p10 median, ≥7 sessions) overrides the configured static value
                // for sleep state evaluation; fallback is the existing user-set hrRestingBpm.
                val effectiveHrResting = agg.restingHrBpm ?: hrRestingBpm

                // 30-min window for HR — sufficient for both 5-min and 15-min avgs and sleep eval.
                val hrReadingsForSleep = persistenceLayer.getHeartRatesFromTime(now - 30 * 60_000L)
                // Lump-tolerant wake evidence (2026-07-03): the detector needs today's CUMULATIVE
                // steps (max of wear-reconstructed and phone) — wear-bridge steps arrive in batches
                // the phone's 15-min bucket never sees (the phone sits on the nightstand overnight),
                // which is why the 06:00 wake was missed and every wake was boundary-forced.
                val sleepTodayIdx = DailyStepHistoryTracker.dayIndex(now, localOffsetMs)
                val sleepDayStartMs = sleepTodayIdx * 86_400_000L - localOffsetMs
                val scTodayForSleep = try { persistenceLayer.getStepsCountFromTimeToTime(sleepDayStartMs, now) } catch (t: Throwable) { emptyList() }
                val stepsTodayForSleep = maxOf(
                    WearStepSource.stepsToday(scTodayForSleep, sleepDayStartMs, now),
                    StepService.getStepsToday(localOffsetMs)
                )
                val sleepResult = SleepStateDetector.evaluate(
                    prev = sleepStateCached,
                    inputs = SleepStateDetector.Inputs(
                        nowMs = now,
                        minuteOfDay = minOfDay,
                        hrReadings = hrReadingsForSleep,
                        hrWindowMinutes = 5,
                        hrResting = effectiveHrResting,
                        stepsLast15Min = recentSteps15Min,
                        mlMealLikely = it.mlMealLikely,
                        nightStartMin = effectiveNightStartMin,
                        nightEndMin = effectiveNightEndMin,
                        preSleepLeadMin = preferences.getBoostDosing(IntKey.ApsBoostPreSleepLeadMin),
                        minSleepHysteresisMin = preferences.getBoostDosing(IntKey.ApsBoostSleepHysteresisMin),
                        wakeHrHysteresisMin = preferences.getBoostDosing(IntKey.ApsBoostWakeHrHysteresisMin),
                        stepsToday = stepsTodayForSleep,
                        // 2026-07-08 sleep-in merge (v7-shadow): fold the lie-in backstop into the state machine.
                        sleepInStepsThreshold = sleepInSteps,
                        sleepInWindowMin = (sleepInHours * 60.0).toInt(),
                        cycleSpacingMinutes = iobCobCalculator.ads.detectedCadenceMinutes
                    ),
                    aapsLogger = aapsLogger
                )
                val prevSleepState = sleepStateCached.state
                sleepStateCached = sleepResult.newState
                if (sleepResult.transitioned) {
                    preferences.put(StringKey.ApsBoostSleepState, sleepResult.newState.serialize())
                    aapsLogger.debug(LTag.APS, "Sleep state transitioned → ${sleepResult.newState.state} (${sleepResult.debug})")

                    // Update sleep history on the actual sleep/wake transitions only
                    val newState = sleepResult.newState.state
                    val historyChanged = when {
                        prevSleepState != SleepStateDetector.SleepState.SLEEPING &&
                            newState == SleepStateDetector.SleepState.SLEEPING -> {
                            sleepHistoryCached = SleepHistoryTracker.onSleepStart(sleepHistoryCached, now)
                            true
                        }
                        prevSleepState == SleepStateDetector.SleepState.SLEEPING &&
                            newState != SleepStateDetector.SleepState.SLEEPING -> {
                            // Fetch HR over the just-ended sleep period for restingHrP10
                            val sleepStartMs = sleepHistoryCached.openSleepStartMs ?: 0L
                            val sleepHrSamples = if (sleepStartMs > 0) {
                                persistenceLayer.getHeartRatesFromTimeToTime(sleepStartMs, now)
                                    .filter { hr -> hr.isValid && hr.beatsPerMinute > 0 }
                                    .map { hr -> hr.beatsPerMinute }
                            } else emptyList()
                            // Fetch HR over the awake period preceding this sleep for daytimeHrP10
                            val priorWakeMs = SleepHistoryTracker.lastWakeMs(sleepHistoryCached)
                            val daytimeHrSamples = if (priorWakeMs != null && sleepStartMs > priorWakeMs) {
                                persistenceLayer.getHeartRatesFromTimeToTime(priorWakeMs, sleepStartMs)
                                    .filter { hr -> hr.isValid && hr.beatsPerMinute > 0 }
                                    .map { hr -> hr.beatsPerMinute }
                            } else emptyList()
                            sleepHistoryCached = SleepHistoryTracker.onWake(
                                sleepHistoryCached, now,
                                sleepHrBpms = sleepHrSamples,
                                daytimeHrBpms = daytimeHrSamples,
                                wakeReason = sleepResult.wakeReason
                            )
                            true
                        }
                        else -> false
                    }
                    if (historyChanged) {
                        preferences.put(StringKey.ApsBoostSleepHistory, sleepHistoryCached.serialize())
                    }
                }

                // ── NS upload: HR + sleep + learned-schedule telemetry ─────────
                it.sleepState = sleepResult.newState.state.name
                it.sleepStateEnteredAtMs = sleepResult.newState.enteredAtMs.takeIf { v -> v > 0 }
                it.sleepEntryReason = sleepResult.newState.sleepEntryReason
                it.sleepLearnedStartMin = agg.sleepStartMinAvg
                it.sleepLearnedWakeMin = agg.wakeMinAvg
                it.sleepLearnedDurationMin = agg.sleepDurationMinAvg
                it.sleepLearnedSessionCount = agg.sessionCount
                it.hrLearnedRestingBpm = agg.restingHrBpm
                it.hrLearnedDaytimeBpm = agg.daytimeHrBpm
                // Update cache for next cycle's HrActivityCalculator.classify call
                hrLearnedDaytimeBpmCached = agg.daytimeHrBpm
                val latestHr = hrReadingsForSleep.maxByOrNull { hr -> hr.timestamp }
                if (latestHr != null && latestHr.isValid) {
                    it.hrBpmLatest = Round.roundTo(latestHr.beatsPerMinute, 0.1)
                }
                val avg5 = SleepStateDetector.averageHr(hrReadingsForSleep, now, 5)
                val avg15 = SleepStateDetector.averageHr(hrReadingsForSleep, now, 15)
                if (avg5 != null) it.hrBpmAvg5m = Round.roundTo(avg5, 0.1)
                if (avg15 != null) it.hrBpmAvg15m = Round.roundTo(avg15, 0.1)
                // F5 (2026-07-07) transient visibility: 15-min averaging blunts hypo-tachycardia
                // (+1.5 vs +13.6 bpm, 2026-07-06 analysis) — emit the 5-min extremes of the 1-min
                // rows so the transient survives into NS for retrospective modelling.
                val hrRows5m = hrReadingsForSleep.filter { hr -> hr.isValid && hr.timestamp > now - 5 * 60_000L }
                if (hrRows5m.isNotEmpty()) {
                    it.hrBpmMax5m = Round.roundTo(hrRows5m.maxOf { hr -> hr.beatsPerMinute }, 0.1)
                    it.hrBpmMin5m = Round.roundTo(hrRows5m.minOf { hr -> hr.beatsPerMinute }, 0.1)
                }
                it.hrReadingsCount15m = hrReadingsForSleep.count { hr ->
                    hr.isValid && hr.timestamp > now - 15 * 60_000L
                }
                // HR source visibility (2026-06-28): which device feeds HR + silent-death detection.
                // Consumers stay source-agnostic; this is telemetry only.
                val hrRes = HrSourceResolver.resolve(
                    hrReadingsForSleep.filter { it.isValid }.map { HrSourceResolver.Reading(it.device, it.timestamp) }, now
                )
                it.hrSource_resolved = hrRes.active
                it.hrSource_states = hrRes.note
                // F4 phone side (2026-07-07): edge-detect the whole feed going dark (anyFresh
                // true→false) — one reason-line note naming the last device + age — and after 60
                // consecutive dark minutes during 08:00-22:00 local, one low-priority notification
                // per dark episode (the wear watchdog re-registers the sensor; this covers every
                // other silent-death mode: BT drop, Garmin app dead, watch off wrist).
                val darkEvent = hrFeedDarkTracker.onCycle(hrRes, now, java.time.LocalTime.now().hour)
                darkEvent.wentDarkNote?.let { note ->
                    aapsLogger.warn(LTag.APS, note)
                    it.reason.append("$note; ")
                }
                if (darkEvent.raiseNotification) {
                    uiInteraction.addNotification(
                        Notification.USER_MESSAGE,
                        "Boost: heart-rate feed has been dark for ${darkEvent.darkMinutes} min — check the watch/Garmin connection",
                        Notification.LOW
                    )
                }

                // 2026-07-30 auto-config breadcrumb, replayed EVERY cycle so it reaches Nightscout and
                // boost_decisions.reason_text. Written by the V5 onboarding path (see
                // StringKey.ApsBoostV5AutoConfigSummary); read-only here. Empty = the onboarding path has
                // not reached a decision yet on this install. Display-only, never consulted for dosing.
                preferences.get(StringKey.ApsBoostV5AutoConfigSummary).let { acs ->
                    if (acs.isNotEmpty()) it.reason.append("autocfg=$acs; ")
                }
                // 2026-08-03 periodic re-derivation breadcrumb, same contract: replayed EVERY cycle
                // so Nightscout and boost_decisions always show the CURRENT auto-config state, not
                // just the one cycle in seven when the re-derivation actually ran. Written by
                // OpenAPSBoostV5Plugin.maybeRedrive; display-only, never consulted for dosing.
                preferences.get(StringKey.ApsBoostV5RedriveSummary).let { rds ->
                    if (rds.isNotEmpty()) it.reason.append("autordv=$rds; ")
                }
                // 2026-07-30 install-time history-gap breadcrumb, same contract (see BoostHistorySync).
                // Empty = adequate local history, so nothing to say — the common case writes nothing.
                preferences.get(StringKey.ApsBoostHistorySyncSummary).let { hss ->
                    if (hss.isNotEmpty()) it.reason.append("histsync=$hss; ")
                }
                it.reason.append("sleep=${sleepResult.newState.state}")
                if (agg.sleepStartMinAvg != null) {
                    it.reason.append(" learned=${formatClockMin(agg.sleepStartMinAvg!!)}→${formatClockMin(agg.wakeMinAvg ?: 0)}/${agg.sessionCount}d")
                }
                it.reason.append("; ")
            } catch (t: Throwable) {
                aapsLogger.error(LTag.APS, "Sleep state evaluation failed", t)
            }

            // ── Activity-load SHADOW (2026-06-16): learn the personal step baseline + compute what
            // an activity/inactivity ISF modifier WOULD do, and LOG it. Never applied to dosing. ──
            if (preferences.getBoostDosing(BooleanKey.ApsBoostActivityShadowEnabled)) {   // 2026-07-08: raw read (Simple-Mode mask bypass)
                try {
                    val offsetMs = java.time.ZoneId.systemDefault().rules.getOffset(java.time.Instant.now()).totalSeconds * 1000L
                    val todayIdx = DailyStepHistoryTracker.dayIndex(now, offsetMs)
                    val dayStartMs = todayIdx * 86_400_000L - offsetMs
                    var multi = multiStepHistoryCached

                    // ── Assemble per-source completed-day history from whatever the user has ──
                    // Health Connect: EVERY dataOrigin (Garmin, Google Fit, …) — instant backfill, and
                    // one source dying no longer starves the baseline (the 2026-06-27 failure).
                    for ((rawSrc, totals) in healthConnectStepsIngest.allSourceDailyTotals)
                        multi = DailyStepHistoryTracker.mergeSource(multi, rawSrc, totals, todayIdx)
                    // Backfill the PHONE anchor from HC's phone-sensor (device.type==PHONE) history so the
                    // phone-anchored baseline is full-window at once, not accrued one day per midnight.
                    val hcPhone = healthConnectStepsIngest.phoneDailyTotals
                    if (hcPhone.isNotEmpty()) multi = DailyStepHistoryTracker.mergeSource(multi, StepSourceResolver.PHONE, hcPhone, todayIdx)
                    // Wear: derive completed-day totals from the SC table (throttled — daily totals are
                    // stable within an hour, and a 28-day SC read is heavy at the 5-min cycle cadence).
                    if (now - lastWearDailyMs >= 60 * 60_000L) {
                        lastWearDailyMs = now
                        val windowStartMs = (todayIdx - DailyStepHistoryTracker.WINDOW_DAYS) * 86_400_000L - offsetMs
                        val wearHist = try { persistenceLayer.getStepsCountFromTimeToTime(windowStartMs, now) } catch (t: Throwable) { emptyList() }
                        val wearDaily = WearStepSource.dailyTotals(wearHist, todayIdx, offsetMs)
                        if (wearDaily.isNotEmpty()) multi = DailyStepHistoryTracker.mergeSource(multi, StepSourceResolver.WEAR, wearDaily, todayIdx)
                    }

                    // ── Today-so-far per candidate source ──
                    // Reconcile the phone counter with HC's today total (hold the HIGHER, never anchor
                    // down), only when HC's value is for the CURRENT local day (no cross-midnight bleed).
                    if (healthConnectStepsIngest.todayStepsDay == todayIdx)
                        StepService.seedTodayFromHc(healthConnectStepsIngest.todayStepsSoFar, offsetMs)
                    val todaySc = try { persistenceLayer.getStepsCountFromTimeToTime(dayStartMs, now) } catch (t: Throwable) { emptyList() }
                    val wearToday = WearStepSource.stepsToday(todaySc, dayStartMs, now)
                    val phoneToday = StepService.getStepsToday(offsetMs)

                    // ── Intraday running-max BANK (2026-07-07) — day-close never reads live counts.
                    // The 07-06 recurrence (despite hold-higher): wear peaked 4142 at 22:58 BST,
                    // the wear counter reset at DEVICE midnight 23:04, and the day closed at 739
                    // (phone) — wear's candidate was already 0 at the moment of resolution. Bank
                    // per-source maxima every cycle (wear/phone native units; HC sources only when
                    // HC's today value is for the CURRENT local day); on rollover the completed
                    // day is merged from the BANK. Persisted so an app restart keeps the peak.
                    // Replaces the old phone-only in-memory ledger (phoneDayCached/phoneMaxCached).
                    val bankCounts = LinkedHashMap<String, Int>()
                    bankCounts[StepSourceResolver.WEAR] = wearToday
                    bankCounts[StepSourceResolver.PHONE] = phoneToday
                    if (healthConnectStepsIngest.todayStepsDay == todayIdx)
                        for ((rawSrc, t) in healthConnectStepsIngest.todayStepsBySource) {
                            val c = StepSourceResolver.canonical(rawSrc)
                            if (c == StepSourceResolver.WEAR || c == StepSourceResolver.PHONE) continue
                            bankCounts[c] = maxOf(bankCounts[c] ?: 0, t)
                        }
                    val banked = DailyStepHistoryTracker.bankCycle(stepBankCached, todayIdx, bankCounts)
                    stepBankCached = banked.bank
                    val bankSerialized = banked.bank.serialize()
                    if (bankSerialized != lastStepBankSerialized) {
                        preferences.put(StringKey.ApsBoostIntradayStepBank, bankSerialized)
                        lastStepBankSerialized = bankSerialized
                    }
                    if (banked.closedDayTotals.isNotEmpty()) {
                        for (t in banked.closedDayTotals)
                            multi = DailyStepHistoryTracker.mergeSource(multi, t.source, listOf(t), todayIdx)
                        // Breadcrumb AT the rollover cycle (the 07-06 close was silent): what each
                        // source banked. The held-X-over-Y resolution line follows from
                        // phoneAnchoredWindow below on this same cycle, now with banked values.
                        it.reason.append("stepHistory: day-close banked ${banked.closedDayTotals.joinToString(", ") { t -> "${t.source} ${t.steps}" }}; ")
                        aapsLogger.info(LTag.APS, "Boost step day-close (banked): ${banked.closedDayTotals.joinToString(", ") { t -> "${t.source} ${t.steps}" }}")
                    }

                    if (multi.sources != multiStepHistoryCached.sources) {
                        multiStepHistoryCached = multi
                        preferences.put(StringKey.ApsBoostDailyStepHistory, multi.serialize())
                    }

                    // ── Auto-resolve today's active source (no UI) ──
                    // Wear "fresh" uses the RESOLUTION grace window (2026-07-07): strict 12-min
                    // freshness flapped today's count wear↔phone every 2-3 cycles overnight (the
                    // resolver prefers the highest-trust FRESH source, so each brief wear-quiet
                    // spell handed the count to the live-but-tiny phone: 349↔32 in the 07-06/07
                    // telemetry). The wear today-count is rebuilt from the day's SC rows, so it
                    // stays valid across a short quiet spell. Phone "fresh" = the pedometer has
                    // actually reported this boot (F9, 2026-07-07) — `phoneToday > 0` conflated
                    // "no data" with "no steps yet today" (false at midnight, false after reboot
                    // until the user moves, and never true on a phone whose sensor is dead).
                    val states = mutableListOf<StepSourceResolver.SourceState>()
                    states += StepSourceResolver.SourceState(StepSourceResolver.WEAR, WearStepSource.isRecentlyFresh(todaySc, now), multi.sources[StepSourceResolver.WEAR]?.days?.size ?: 0, wearToday)
                    states += StepSourceResolver.SourceState(StepSourceResolver.PHONE, StepService.feedState() == StepService.FeedState.LIVE, multi.sources[StepSourceResolver.PHONE]?.days?.size ?: 0, phoneToday)
                    for ((rawSrc, t) in healthConnectStepsIngest.todayStepsBySource) {
                        val c = StepSourceResolver.canonical(rawSrc)
                        if (c == StepSourceResolver.WEAR || c == StepSourceResolver.PHONE) continue
                        states += StepSourceResolver.SourceState(c, false, multi.sources[c]?.days?.size ?: 0, t)   // HC is hourly/laggy → not "fresh"
                    }
                    val res = StepSourceResolver.resolve(states)

                    // ── Baseline from the PHONE-ANCHORED rolling window. The phone is the one source
                    //    that runs continuously across watch SWAPS (one watch ceases as the next
                    //    starts → they never overlap), so it is the calibration frame; worn sources
                    //    are scaled into phone units. (Replaces watch-to-watch bridging, which could
                    //    never calibrate a swap.) ──
                    val bridged = DailyStepHistoryTracker.phoneAnchoredWindow(multi, todayIdx)
                    val sf = DailyStepHistoryTracker.shadowFactors(bridged.history, todayIdx)
                    it.boostActivityLoad_baselineSteps = sf.baselineSteps
                    it.boostActivityLoad_lastDaySteps = sf.lastDaySteps
                    it.boostActivityLoad_ratio = sf.ratio?.let { r -> Round.roundTo(r, 0.01) }
                    it.boostActivityLoad_wouldDeltaIsfPct = Round.roundTo(sf.wouldDeltaIsfPct, 0.1)
                    it.boostActivityLoad_source = res.active
                    it.boostActivitySource_resolved = res.active
                    it.boostActivitySource_states = res.note
                    it.boostActivitySource_bridge = if (bridged.donorsUsed.isEmpty()) "phone"
                        else "phone<-" + bridged.donorsUsed.joinToString("+") + if (bridged.calibrated) "" else "(raw)"
                    // Hold-higher reconcile breadcrumb (2026-07-03): make the yesterday-total
                    // resolution visible in NS — the 07-02 undercount (wear 6224 recorded as 2227)
                    // was invisible because nothing logged which source's count won the day.
                    bridged.heldNote?.let { hn -> it.reason.append("stepHistory: $hn; ") }
                    if (sf.baselineSteps != null && sf.ratio != null) {
                        val sign = if (sf.wouldDeltaIsfPct >= 0) "+" else ""
                        it.reason.append("activityLoad: ${res.active ?: "none"} base ${sf.baselineSteps} last ${sf.lastDaySteps} (${Round.roundTo(sf.ratio!!, 0.01)}x) wouldΔISF $sign${Round.roundTo(sf.wouldDeltaIsfPct, 0.1)}% [${sf.note}] bridge[${it.boostActivitySource_bridge}]; ")
                    } else {
                        it.reason.append("activityLoad: no baseline (src[${res.note}]); ")
                    }

                    // ── Intraday "running hot?" — today's count converted to PHONE units so it matches
                    //    the phone-anchored baseline (worn-source today × phone/worn calibration). ──
                    val intraHour = java.time.LocalTime.now().hour
                    val stepsTodayPhone = DailyStepHistoryTracker.toPhoneUnits(res.stepsToday, res.active, multi)
                    val intra = DailyStepHistoryTracker.intradayFactor(stepsTodayPhone, sf.baselineSteps, intraHour)
                    it.boostActivityLoad_stepsToday = res.stepsToday
                    it.boostActivityLoad_stepsSource = res.active
                    it.boostActivityLoad_intradayRatio = intra.ratio?.let { r -> Round.roundTo(r, 0.01) }
                    it.boostActivityLoad_intradayDeltaIsfPct = Round.roundTo(intra.wouldDeltaIsfPct, 0.1)
                    if (intra.ratio != null) {
                        it.reason.append("activityIntraday: today ${res.stepsToday} vs exp ${intra.expectedByNow} (${Round.roundTo(intra.ratio!!, 0.01)}x) wouldΔISF +${Round.roundTo(intra.wouldDeltaIsfPct, 0.1)}%; ")
                    }
                } catch (t: Throwable) {
                    aapsLogger.error(LTag.APS, "Activity-load shadow failed", t)
                }
            }

            // ── Autosens / TDD-DynISF coordination telemetry (2026-06-16). Always logs which
            // mechanism drives basal + the would-be alternative, so ApsBoostAutosensWhenNoTdd can be
            // validated on real data before being enabled. SHADOW only when the toggle is OFF — the
            // applied ratio (boostAutosens_appliedRatio) is whatever determine_basal actually used. ──
            it.boostAutosens_mode = if (useTdd) "tdd" else if (autosensWhenNoTdd) "autosens" else "curve"
            it.boostAutosens_orefRatio = Round.roundTo(orefAutosensRatio, 0.001)
            it.boostAutosens_curveRatio = Round.roundTo(isfResult.ratio, 0.001)
            it.boostAutosens_appliedRatio = Round.roundTo(autosensResult.ratio, 0.001)
            if (!useTdd) {
                it.reason.append("autosensCoord[${it.boostAutosens_mode}]: oref=${Round.roundTo(orefAutosensRatio, 0.01)} curve=${Round.roundTo(isfResult.ratio, 0.01)} applied=${Round.roundTo(autosensResult.ratio, 0.01)}; ")
            }

            val determineBasalResult = apsResultProvider.get().with(it)
            determineBasalResult.inputConstraints = inputConstraints
            determineBasalResult.autosensResult = autosensResult
            determineBasalResult.iobData = iobArray
            determineBasalResult.glucoseStatus = glucoseStatus
            determineBasalResult.currentTemp = currentTemp
            determineBasalResult.oapsProfileBoost = oapsProfile
            determineBasalResult.mealData = mealData
            lastAPSResult = determineBasalResult
            lastAPSRun = now
            aapsLogger.debug(LTag.APS, "Result: $it")
            rxBus.send(EventAPSCalculationFinished())
        }

        rxBus.send(EventOpenAPSUpdateGui())
    }

    // ---- Glucose status ----

    override fun getGlucoseStatusData(allowOldData: Boolean) = glucoseStatusCalculatorSMB.getGlucoseStatusData(allowOldData)

    // ---- Constraints ----

    override fun isSuperBolusEnabled(value: Constraint<Boolean>): Constraint<Boolean> {
        value.set(false)
        return value
    }

    override fun applyMaxIOBConstraints(maxIob: Constraint<Double>): Constraint<Double> {
        if (engineActive()) {
            val maxIobPref = preferences.get(DoubleKey.ApsSmbMaxIob)
            maxIob.setIfSmaller(maxIobPref, rh.gs(R.string.limiting_iob, maxIobPref, rh.gs(R.string.maxvalueinpreferences)), this)
            maxIob.setIfSmaller(hardLimits.maxIobSMB(), rh.gs(R.string.limiting_iob, hardLimits.maxIobSMB(), rh.gs(R.string.hardlimit)), this)
        }
        return maxIob
    }

    override fun applyBasalConstraints(absoluteRate: Constraint<Double>, profile: Profile): Constraint<Double> {
        if (engineActive()) {
            var maxBasal = preferences.get(DoubleKey.ApsMaxBasal)
            if (maxBasal < profile.getMaxDailyBasal()) {
                maxBasal = profile.getMaxDailyBasal()
                absoluteRate.addReason(rh.gs(R.string.increasing_max_basal), this)
            }
            absoluteRate.setIfSmaller(maxBasal, rh.gs(app.aaps.core.ui.R.string.limitingbasalratio, maxBasal, rh.gs(R.string.maxvalueinpreferences)), this)

            val maxBasalMultiplier = preferences.get(DoubleKey.ApsMaxCurrentBasalMultiplier)
            val maxFromBasalMultiplier = floor(maxBasalMultiplier * profile.getBasal() * 100) / 100
            absoluteRate.setIfSmaller(
                maxFromBasalMultiplier,
                rh.gs(app.aaps.core.ui.R.string.limitingbasalratio, maxFromBasalMultiplier, rh.gs(R.string.max_basal_multiplier)),
                this
            )
            val maxBasalFromDaily = preferences.get(DoubleKey.ApsMaxDailyMultiplier)
            val maxFromDaily = floor(profile.getMaxDailyBasal() * maxBasalFromDaily * 100) / 100
            absoluteRate.setIfSmaller(maxFromDaily, rh.gs(app.aaps.core.ui.R.string.limitingbasalratio, maxFromDaily, rh.gs(R.string.max_daily_basal_multiplier)), this)
        }
        return absoluteRate
    }

    override fun isSMBModeEnabled(value: Constraint<Boolean>): Constraint<Boolean> {
        val enabled = preferences.get(BooleanKey.ApsUseSmb)
        if (!enabled) value.set(false, rh.gs(R.string.smb_disabled_in_preferences), this)
        else if (isNightModeActive()) value.set(false, rh.gs(R.string.boost_night_mode_smb_disabled), this)
        return value
    }

    // ---- Night Mode ----

    // @Volatile (2026-07-02): read from the constraint path (isSMBModeEnabled) on non-loop threads;
    // without a happens-before edge a racing reader could pair a fresh timestamp with a stale result
    // and return "not night" on a night cycle (SMB let through). Benign worst case now: recompute.
    @Volatile private var lastNightModeRun: Long = 0
    @Volatile private var lastNightModeResult: Boolean = false

    // ---- Sleep state (2026-06-02) ----
    // Updated at end of invoke() once HR + steps + mlMealLikely are known. Read by
    // isNightModeActiveImpl() when ApsBoostNightModeAutoBySleep is enabled.
    @Volatile private var sleepStateCached: SleepStateDetector.State =
        SleepStateDetector.State.deserialize(preferences.getBoostDosing(StringKey.ApsBoostSleepState))
    @Volatile private var sleepHistoryCached: SleepHistoryTracker.History =
        SleepHistoryTracker.History.deserialize(preferences.getBoostDosing(StringKey.ApsBoostSleepHistory))
    // V6 meal-time learner — rolling 60-day history of V5-CONFIRMED meal commits. Loaded once at
    // construction; updated at end of invoke() when a fresh CONFIRMED fires, persisted on change.
    @Volatile private var mealTimeHistoryCached: MealTimeLearner.History =
        MealTimeLearner.History.deserialize(preferences.getBoostDosing(StringKey.ApsBoostMealTimeHistory))
    // Activity-load SHADOW — rolling 28-day PER-SOURCE daily-step history (multi-source abstraction
    // 2026-06-28; deserialize auto-migrates the old single-source blob). Persisted under the same key.
    @Volatile private var multiStepHistoryCached: DailyStepHistoryTracker.MultiSourceHistory =
        DailyStepHistoryTracker.MultiSourceHistory.deserialize(preferences.getBoostDosing(StringKey.ApsBoostDailyStepHistory))
    @Volatile private var lastWearDailyMs = 0L          // throttle the 28-day Wear SC read to hourly
    // Intraday step bank (2026-07-07): per-source running max of today's counts, persisted so a
    // mid-evening app restart keeps the day's peak. Day-close resolves from THIS, never from
    // post-reset live reads (the 07-06 device-midnight wear reset undercount).
    @Volatile private var stepBankCached: DailyStepHistoryTracker.IntradayStepBank =
        DailyStepHistoryTracker.IntradayStepBank.deserialize(preferences.getBoostDosing(StringKey.ApsBoostIntradayStepBank))
    @Volatile private var lastStepBankSerialized: String? = null   // write-avoidance cache
    // Cached learned daytime baseline (used by HrActivityCalculator in current cycle from prior
    // cycle's aggregate computation — 5-min lag is acceptable, baseline changes slowly).
    @Volatile private var hrLearnedDaytimeBpmCached: Int? = null

    // Step-based sleep-in (lie-in) state from the most recent calculateBoostActivity() (2026-07-02).
    // Read by isNightModeActiveImpl() so a lie-in applies the user's night-mode SMB rules. The SMB
    // constraint is evaluated earlier in invoke() than calculateBoostActivity() runs, so this holds
    // the PREVIOUS cycle's value — a one-cycle (~5 min) lag that is safe: it errs toward keeping night
    // mode on one extra cycle when waking, and the boostActive override gate already blocks the
    // amplified V5 dose on the entering cycle regardless.
    @Volatile private var sleepInActiveCached: Boolean = false

    /**
     * Pre-BG-gate "user is in their night/sleep period" — the night time window OR HR/step sleep
     * detection, gated by the night-mode master toggle. This is the sleep-aware signal that gates the
     * Boost window (boostActive = !this). It deliberately EXCLUDES the BG / COB / low-TT gates that
     * [isNightModeActiveImpl] layers on for the SMB-suppression decision: those must NOT influence the
     * Boost window, or a nocturnal high would flip Boost back on and re-fire a V6 dose while asleep.
     * (2026-07-02)
     */
    private fun isInNightSleepPeriod(): Boolean {
        if (!preferences.getBoostDosing(BooleanKey.ApsBoostNightModeEnabled)) return false
        val now = System.currentTimeMillis()
        val midnight = now - MidnightUtils.milliSecFromMidnight(now)
        val start = midnight + parseTimeToMillisOrDefault(preferences.getBoostDosing(StringKey.ApsBoostNightModeStart), "22:00")
        val end = midnight + parseTimeToMillisOrDefault(preferences.getBoostDosing(StringKey.ApsBoostNightModeEnd), "07:00")
        // Equal-times guard (2026-07-02): with start==end the wrap-branch union covers the whole
        // day → always-night → Boost/V6 silently never doses. Treat as an EMPTY time window
        // (mathematically a zero-length interval); HR/step sleep detection + the steps lie-in
        // backstop still protect the night.
        if (start == end) {
            aapsLogger.error(LTag.APS, "Night-mode start == end — treating time window as empty (sleep detection still active)")
            return preferences.getBoostDosing(BooleanKey.ApsBoostNightModeAutoBySleep) &&
                sleepStateCached.state != SleepStateDetector.SleepState.AWAKE
        }
        val active = NightWindow.contains(now, start, end)
        val autoBySleep = preferences.getBoostDosing(BooleanKey.ApsBoostNightModeAutoBySleep)
        val sleepActive = autoBySleep && sleepStateCached.state != SleepStateDetector.SleepState.AWAKE
        return active || sleepActive
    }

    private fun isNightModeActive(): Boolean {
        val currentTimeMillis = System.currentTimeMillis()
        val timeAligned = currentTimeMillis - (currentTimeMillis % 1000)
        if (lastNightModeRun >= timeAligned) return lastNightModeResult
        lastNightModeResult = isNightModeActiveImpl()
        lastNightModeRun = timeAligned
        return lastNightModeResult
    }

    private fun isNightModeActiveImpl(): Boolean {
        if (!preferences.getBoostDosing(BooleanKey.ApsBoostNightModeEnabled)) return false

        val bgCurrent = glucoseStatusCalculatorSMB.getGlucoseStatusData(true)?.glucose ?: return false

        // Night by time window OR HR/step sleep detection (isInNightSleepPeriod, which also honours
        // ApsBoostNightModeAutoBySleep — extending past nightEnd while still SLEEPING and enabling early
        // on PRE_SLEEP), OR the step-based lie-in surfaced from calculateBoostActivity so night-mode SMB
        // rules also apply during a morning lie-in. (sleepInActiveCached lags one cycle; see its
        // declaration.) (2026-07-02)
        if (!isInNightSleepPeriod() && !sleepInActiveCached) return false

        // Disable night mode when COB > 0
        if (preferences.getBoostDosing(BooleanKey.ApsBoostNightModeDisableWithCob)) {
            val mealData = iobCobCalculator.getMealDataWithWaitingForCalculationFinish()
            if (mealData.mealCOB > 0) return false
        }

        // Disable night mode with low temp target
        if (preferences.getBoostDosing(BooleanKey.ApsBoostNightModeDisableWithLowTt)) {
            val profile = profileFunction.getProfile() ?: return false
            val profileTarget = profile.getTargetMgdl()
            persistenceLayer.getTemporaryTargetActiveAt(dateUtil.now())?.let { tempTarget ->
                val targetBg = hardLimits.verifyHardLimits(
                    tempTarget.target(), app.aaps.core.ui.R.string.temp_target_value,
                    HardLimits.LIMIT_TEMP_TARGET_BG[0], HardLimits.LIMIT_TEMP_TARGET_BG[1]
                )
                if (targetBg < profileTarget) return false
            }
        }

        // Check BG vs profile target + offset
        val profile = profileFunction.getProfile() ?: return false
        val profileTarget = profile.getTargetMgdl()
        val bgOffset = profileUtil.convertToMgdl(preferences.getBoostDosing(UnitDoubleKey.ApsBoostNightModeBgOffset, profileUtil), profileUtil.units)
        return bgCurrent < profileTarget + bgOffset
    }

    override fun isUAMEnabled(value: Constraint<Boolean>): Constraint<Boolean> {
        val enabled = preferences.get(BooleanKey.ApsUseUam)
        if (!enabled) value.set(false, rh.gs(R.string.uam_disabled_in_preferences), this)
        return value
    }

    override fun isAutosensModeEnabled(value: Constraint<Boolean>): Constraint<Boolean> {
        val enabled = preferences.get(BooleanKey.ApsUseAutosens)
        if (!enabled) value.set(false, rh.gs(R.string.autosens_disabled_in_preferences), this)
        return value
    }

    override fun configuration(): JSONObject =
        JSONObject()
            .put(BooleanKey.ApsBoostEnablePercentScale, preferences)
            .put(BooleanKey.ApsBoostEnableCircadianIsf, preferences)

    override fun applyConfiguration(configuration: JSONObject) {
        configuration
            .store(BooleanKey.ApsBoostEnablePercentScale, preferences)
            .store(BooleanKey.ApsBoostEnableCircadianIsf, preferences)
    }

    // ---- Preferences screen ----

    override fun addPreferenceScreen(preferenceManager: PreferenceManager, parent: PreferenceScreen, context: Context, requiredKey: String?) {
        if (requiredKey != null &&
            requiredKey != "absorption_smb_advanced" &&
            requiredKey != "boost_default_aaps_settings" &&
            requiredKey != "boost_dynisf_settings" &&
            requiredKey != "boost_exercise_settings" &&
            requiredKey != "boost_stepcount_settings" &&
            requiredKey != "boost_hr_integration_settings" &&
            requiredKey != "boost_post_exercise_recovery_settings" &&
            requiredKey != "boost_night_mode_settings" &&
            requiredKey != "boost_v1_smb_sizing" &&
            requiredKey != "boost_safety_settings"
        ) return
        val category = PreferenceCategory(context)
        parent.addPreference(category)
        category.apply {
            key = "openapsboost_settings"
            title = rh.gs(R.string.openaps_boost)
            initialExpandedChildrenCount = 0
        }
        // V1-only SMB sizing — these size V1's own SMB tiers, which "Boost V5" replaces, so they
        // are NOT shown on the V5 screen.
        category.addPreference(preferenceManager.createPreferenceScreen(context).apply {
            key = "boost_v1_smb_sizing"
            title = rh.gs(R.string.boost_v1_smb_sizing_title)
            addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostInsulinReqPct, dialogMessage = R.string.boost_insulin_req_summary, title = R.string.boost_insulin_req_title))
            addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostBolus, dialogMessage = R.string.boost_bolus_summary, title = R.string.boost_bolus_title))
            addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostPercentScale, dialogMessage = R.string.boost_percent_scale_summary, title = R.string.boost_percent_scale_title))
            addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostScale, dialogMessage = R.string.boost_scale_summary, title = R.string.boost_scale_title))
            // Boost start/end time retired 2026-07-02 — the Boost window now tracks the night-mode
            // period (see calculateBoostActivity / isInNightSleepPeriod). Keys kept for back-compat.
            addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostEnablePercentScale, summary = R.string.boost_enable_percent_scale_summary, title = R.string.boost_enable_percent_scale_title))
        })
        addBoostEngineCategories(preferenceManager, category, context)
    }

    /**
     * Shared Boost ENGINE preference categories — everything both "Boost" (V1) and the selectable
     * "Boost V5" need: basal/IOB, Boost controls, DynISF, activity/HR, post-exercise, night mode,
     * SMB safety, advanced. Built into the caller's root [category]. V5's [OpenAPSBoostV5Plugin]
     * calls this too, then appends its own V5/V6 knob category — so engine settings live in ONE
     * place and stay reachable under whichever Boost plugin is the active APS. Contains NO V5/V6
     * controls (those belong to the V5 plugin).
     */
    fun addBoostEngineCategories(preferenceManager: PreferenceManager, category: PreferenceGroup, context: Context, includeEngineEssentials: Boolean = true) {
        category.apply {
            // ── 1. Default AAPS Settings ────────────────────────────────
            addPreference(preferenceManager.createPreferenceScreen(context).apply {
                key = "boost_default_aaps_settings"
                title = rh.gs(R.string.boost_settings_default_aaps)
                if (includeEngineEssentials) addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsMaxBasal, dialogMessage = R.string.openapsma_max_basal_summary, title = R.string.openapsma_max_basal_title))
                addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsSmbMaxIob, dialogMessage = R.string.openapssmb_max_iob_summary, title = R.string.openapssmb_max_iob_title))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseAutosens, title = R.string.openapsama_use_autosens))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsAutoIsfHighTtRaisesSens, summary = R.string.high_temptarget_raises_sensitivity_summary, title = R.string.high_temptarget_raises_sensitivity_title))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsAutoIsfLowTtLowersSens, summary = R.string.low_temptarget_lowers_sensitivity_summary, title = R.string.low_temptarget_lowers_sensitivity_title))
            })

            // ── 2. Shared Boost engine controls (live under V5 too) ─────
            // maxIOB clamps V5's dose; circadian ISF + allow-with-high-TT shape sens/insulinReq
            // which V5 inherits as baseInsulinReq. The V1 SMB-SIZING controls (bolus cap, scale,
            // percent-scale, insulinReq%, boost time window) are NOT here — V5 replaces V1's SMB, so
            // they're inert under V5; they live in V1's screen only. EXCEPTION: the cumulative-60min
            // SMB cap ALSO bounds V5/V6 (re-checked at the V6 override), so it lives in the shared
            // Safety category below — see §6.
            if (includeEngineEssentials) addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostMaxIob, dialogMessage = R.string.boost_max_iob_summary, title = R.string.boost_max_iob_title))
            addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostEnableCircadianIsf, summary = R.string.boost_enable_circadian_isf_summary, title = R.string.boost_enable_circadian_isf_title))
            addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostAllowWithHighTt, summary = R.string.boost_allow_high_tt_summary, title = R.string.boost_allow_high_tt_title))

            // ── 3. Dynamic ISF Controls ──────────────────────────────────
            addPreference(preferenceManager.createPreferenceScreen(context).apply {
                key = "boost_dynisf_settings"
                title = rh.gs(R.string.boost_dynisf_title)
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostUseTdd, summary = R.string.boost_use_tdd_summary, title = R.string.boost_use_tdd_title))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostAdjustSensitivity, summary = R.string.boost_adjust_sensitivity_summary, title = R.string.boost_adjust_sensitivity_title))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostAutosensWhenNoTdd, summary = R.string.boost_autosens_when_no_tdd_summary, title = R.string.boost_autosens_when_no_tdd_title))
                addPreference(AdaptiveUnitPreference(ctx = context, unitKey = UnitDoubleKey.ApsBoostDynIsfNormalTarget, dialogMessage = R.string.boost_dynisf_normal_target_summary, title = R.string.boost_dynisf_normal_target_title))
                addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostDynIsfVelocity, dialogMessage = R.string.boost_dynisf_velocity_summary, title = R.string.boost_dynisf_velocity_title))
                addPreference(AdaptiveUnitPreference(ctx = context, unitKey = UnitDoubleKey.ApsBoostDynIsfBgCap, dialogMessage = R.string.boost_dynisf_bg_cap_summary, title = R.string.boost_dynisf_bg_cap_title))
                addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostDynIsfAdjustmentFactor, dialogMessage = R.string.boost_dynisf_adjust_factor_summary, title = R.string.boost_dynisf_adjust_factor_title))
            })

            // ── 4. Exercise Settings (parent with nested sub-screens) ────
            addPreference(preferenceManager.createPreferenceScreen(context).apply {
                key = "boost_exercise_settings"
                title = rh.gs(R.string.boost_settings_exercise)

                // 4a. Step Count Settings
                addPreference(preferenceManager.createPreferenceScreen(context).apply {
                    key = "boost_stepcount_settings"
                    title = rh.gs(R.string.boost_stepcount_settings_title)
                    summary = rh.gs(R.string.boost_stepcount_settings_summary)
                    addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostInactivitySteps, dialogMessage = R.string.boost_inactivity_steps_summary, title = R.string.boost_inactivity_steps_title))
                    addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostInactivityPct, dialogMessage = R.string.boost_inactivity_pct_summary, title = R.string.boost_inactivity_pct_title))
                    addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostSleepInHours, dialogMessage = R.string.boost_sleep_in_hrs_summary, title = R.string.boost_sleep_in_hrs_title))
                    addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostSleepInSteps, dialogMessage = R.string.boost_sleep_in_steps_summary, title = R.string.boost_sleep_in_steps_title))
                    addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostActivitySteps5, dialogMessage = R.string.boost_activity_steps_5_summary, title = R.string.boost_activity_steps_5_title))
                    addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostActivitySteps15, dialogMessage = R.string.boost_activity_steps_15_summary, title = R.string.boost_activity_steps_15_title))
                    addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostActivitySteps30, dialogMessage = R.string.boost_activity_steps_30_summary, title = R.string.boost_activity_steps_30_title))
                    addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostActivitySteps60, dialogMessage = R.string.boost_activity_steps_60_summary, title = R.string.boost_activity_steps_60_title))
                    addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostActivityPct, dialogMessage = R.string.boost_activity_pct_summary, title = R.string.boost_activity_pct_title))
                })

                // 4b. Heart Rate Integration
                addPreference(preferenceManager.createPreferenceScreen(context).apply {
                    key = "boost_hr_integration_settings"
                    title = rh.gs(R.string.boost_hr_integration_title)
                    summary = rh.gs(R.string.boost_hr_integration_summary)
                    addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostHrIntegrationEnabled, summary = R.string.boost_hr_integration_enabled_summary, title = R.string.boost_hr_integration_enabled_title))
                    addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostHrMaxBpm, dialogMessage = R.string.boost_hr_max_bpm_summary, title = R.string.boost_hr_max_bpm_title))
                    addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostHrRestingBpm, dialogMessage = R.string.boost_hr_resting_bpm_summary, title = R.string.boost_hr_resting_bpm_title))
                    addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostHrWindowMinutes, dialogMessage = R.string.boost_hr_window_minutes_summary, title = R.string.boost_hr_window_minutes_title))
                    addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostHrStressDetection, summary = R.string.boost_hr_stress_detection_summary, title = R.string.boost_hr_stress_detection_title))
                })

                // 4c. Post-Exercise Recovery
                addPreference(preferenceManager.createPreferenceScreen(context).apply {
                    key = "boost_post_exercise_recovery_settings"
                    title = rh.gs(R.string.boost_post_exercise_recovery_title)
                    addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostPostExerciseRecoveryEnabled, summary = R.string.boost_post_exercise_recovery_enabled_summary, title = R.string.boost_post_exercise_recovery_enabled_title))
                    addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostPostExerciseRecoveryHours, dialogMessage = R.string.boost_post_exercise_recovery_hours_summary, title = R.string.boost_post_exercise_recovery_hours_title))
                    addPreference(AdaptiveUnitPreference(ctx = context, unitKey = UnitDoubleKey.ApsBoostPostExerciseRecoveryTarget, dialogMessage = R.string.boost_post_exercise_recovery_target_summary, title = R.string.boost_post_exercise_recovery_target_title))
                    addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostPostExerciseRecoveryScale, dialogMessage = R.string.boost_post_exercise_recovery_scale_summary, title = R.string.boost_post_exercise_recovery_scale_title))
                    addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostPostExerciseMinDuration, dialogMessage = R.string.boost_post_exercise_min_duration_summary, title = R.string.boost_post_exercise_min_duration_title))
                })
            })

            // ── 5. Night Mode ────────────────────────────────────────────
            addPreference(preferenceManager.createPreferenceScreen(context).apply {
                key = "boost_night_mode_settings"
                title = rh.gs(R.string.boost_night_mode_title)
                if (includeEngineEssentials) addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostNightModeEnabled, summary = R.string.boost_night_mode_enabled_summary, title = R.string.boost_night_mode_enabled_title))
                addPreference(AdaptiveStringPreference(ctx = context, stringKey = StringKey.ApsBoostNightModeStart, dialogMessage = R.string.boost_night_mode_start_summary, title = R.string.boost_night_mode_start_title))
                addPreference(AdaptiveStringPreference(ctx = context, stringKey = StringKey.ApsBoostNightModeEnd, dialogMessage = R.string.boost_night_mode_end_summary, title = R.string.boost_night_mode_end_title))
                if (includeEngineEssentials) addPreference(AdaptiveUnitPreference(ctx = context, unitKey = UnitDoubleKey.ApsBoostNightModeBgOffset, dialogMessage = R.string.boost_night_mode_bg_offset_summary, title = R.string.boost_night_mode_bg_offset_title))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostNightModeDisableWithCob, summary = R.string.boost_night_mode_disable_with_cob_summary, title = R.string.boost_night_mode_disable_with_cob_title))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostNightModeDisableWithLowTt, summary = R.string.boost_night_mode_disable_with_low_tt_summary, title = R.string.boost_night_mode_disable_with_low_tt_title))
                // 2026-06-02: HR-based sleep detection (opt-in)
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostNightModeAutoBySleep, summary = R.string.boost_night_mode_auto_by_sleep_summary, title = R.string.boost_night_mode_auto_by_sleep_title))
                addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostPreSleepLeadMin, dialogMessage = R.string.boost_pre_sleep_lead_min_summary, title = R.string.boost_pre_sleep_lead_min_title))
                addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostSleepHysteresisMin, dialogMessage = R.string.boost_sleep_hysteresis_min_summary, title = R.string.boost_sleep_hysteresis_min_title))
                addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostWakeHrHysteresisMin, dialogMessage = R.string.boost_wake_hr_hysteresis_min_summary, title = R.string.boost_wake_hr_hysteresis_min_title))
                // 2026-06-03: Health Connect HR ingest
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostHealthConnectHrEnabled, summary = R.string.boost_hc_hr_summary, title = R.string.boost_hc_hr_title))
                addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsBoostHealthConnectPollMin, dialogMessage = R.string.boost_hc_poll_summary, title = R.string.boost_hc_poll_title))
                // 2026-06-16: Activity-load SHADOW (HC steps → step baseline; logs would-do ISF, never doses)
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostActivityShadowEnabled, summary = R.string.boost_activity_shadow_summary, title = R.string.boost_activity_shadow_title))
                addPreference(androidx.preference.Preference(context).apply {
                    key = "boost_hc_grant_permission_v1"
                    title = context.getString(R.string.boost_hc_grant_title)
                    summary = context.getString(R.string.boost_hc_grant_summary)
                    setOnPreferenceClickListener {
                        val intent = android.content.Intent(context, app.aaps.plugins.aps.openAPSBoost.HealthConnectPermissionActivity::class.java)
                            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                        context.startActivity(intent)
                        true
                    }
                })
            })

            // ── 6. Safety Settings ───────────────────────────────────────
            addPreference(preferenceManager.createPreferenceScreen(context).apply {
                key = "boost_safety_settings"
                title = rh.gs(R.string.boost_settings_safety)
                if (includeEngineEssentials) addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseSmb, summary = R.string.enable_smb_summary, title = R.string.enable_smb))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseSmbWithHighTt, summary = R.string.enable_smb_with_high_temp_target_summary, title = R.string.enable_smb_with_high_temp_target))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseSmbAlways, summary = R.string.enable_smb_always_summary, title = R.string.enable_smb_always))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseSmbWithCob, summary = R.string.enable_smb_with_cob_summary, title = R.string.enable_smb_with_cob))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseSmbWithLowTt, summary = R.string.enable_smb_with_temp_target_summary, title = R.string.enable_smb_with_temp_target))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseSmbAfterCarbs, summary = R.string.enable_smb_after_carbs_summary, title = R.string.enable_smb_after_carbs))
                if (includeEngineEssentials) addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseUam, summary = R.string.enable_uam_summary, title = R.string.enable_uam))
                addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsMaxSmbFrequency, title = R.string.smb_interval_summary))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsLoopAtNativeCadence, summary = R.string.loop_native_cadence_summary, title = R.string.loop_native_cadence_title))
                addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsMaxMinutesOfBasalToLimitSmb, title = R.string.smb_max_minutes_summary))
                addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsUamMaxMinutesOfBasalToLimitSmb, dialogMessage = R.string.uam_smb_max_minutes, title = R.string.uam_smb_max_minutes_summary))
                addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsCarbsRequestThreshold, dialogMessage = R.string.carbs_req_threshold_summary, title = R.string.carbs_req_threshold))
                // Cumulative 60-min SMB volume cap — a hard anti-stacking gate that ALSO bounds V5/V6
                // (re-checked at the V6 override in OpenAPSBoostPlugin), so it lives in the shared
                // engine Safety category — NOT just V1's SMB-sizing screen. 0 disables; auto-config
                // sets it per user (up to ~confirmedCap, so the key's max must cover the cohort).
                addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostCumulativeSmbCap60Min, dialogMessage = R.string.boost_cumulative_smb_cap_summary, title = R.string.boost_cumulative_smb_cap_title))
                // allow-all-BG-sources + bypass-version-check toggles removed 2026-06-27 —
                // both are now forced always-on in code (no longer user-facing levers).
                // V5/V6 controls intentionally NOT here — they live in the selectable "Boost V5"
                // plugin's screen (OpenAPSBoostV5Plugin.addPreferenceScreen). V1 is V5-free.
            })

            // ── 7. Advanced Settings ─────────────────────────────────────
            addPreference(preferenceManager.createPreferenceScreen(context).apply {
                key = "absorption_smb_advanced"
                title = rh.gs(app.aaps.core.ui.R.string.advanced_settings_title)
                addPreference(
                    AdaptiveIntentPreference(
                        ctx = context,
                        intentKey = IntentKey.ApsLinkToDocs,
                        intent = Intent().apply { action = Intent.ACTION_VIEW; data = rh.gs(R.string.openapsama_link_to_preference_json_doc).toUri() },
                        summary = R.string.openapsama_link_to_preference_json_doc_txt
                    )
                )
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsAlwaysUseShortDeltas, summary = R.string.always_use_short_avg_summary, title = R.string.always_use_short_avg))
                addPreference(
                    AdaptiveSwitchPreference(
                        ctx = context,
                        booleanKey = BooleanKey.ApsBoostPostRescueTightRampTrial,
                        summary = R.string.boost_postrescue_tight_ramp_trial_summary,
                        title = R.string.boost_postrescue_tight_ramp_trial
                    )
                )
                addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsMaxDailyMultiplier, dialogMessage = R.string.openapsama_max_daily_safety_multiplier_summary, title = R.string.openapsama_max_daily_safety_multiplier))
                addPreference(
                    AdaptiveDoublePreference(
                        ctx = context,
                        doubleKey = DoubleKey.ApsMaxCurrentBasalMultiplier,
                        dialogMessage = R.string.openapsama_current_basal_safety_multiplier_summary,
                        title = R.string.openapsama_current_basal_safety_multiplier
                    )
                )
            })
        }
    }
}

// ── V5/V6 exercise-input mapping (F2, 2026-07-07) ───────────────────────────────────────────────
// Pure top-level helpers so the live profile build's mapping is unit-testable. They MUST stay
// bit-identical to the retired V3MLG3 block (OpenAPSBoostV3MLG3Plugin.kt, `v5_exerciseActive =
// activityResult.activityState in setOf(...)` / `v5_inPostExerciseWindow =
// postExerciseRecoveryEnabled && now < recoveryWindowEnd`) — V5's consumers were calibrated
// against that mapping while V5 shadowed V4.4.1.

/**
 * Activity states that count as "exercising" for V5/V6 ([OapsProfileBoost.v5_exerciseActive]).
 * Consumed by MealSignalScore's notExercisingTerm and MealHypothesis' fastConfirm !exercising gate.
 * NOTE: includes "STRESS" (as V3MLG3 did) — a high-HR no-steps state should damp meal confirmation
 * just like exercise. Distinct from the plugin's post-exercise `exerciseStateSet`, which
 * deliberately EXCLUDES "STRESS" (stress shouldn't start a recovery window).
 */
internal val V5_EXERCISE_STATES = setOf(
    "ACTIVE", "VIGOROUS_AEROBIC", "MODERATE_AEROBIC", "LIGHT_AEROBIC", "RESISTANCE", "STRESS"
)

/** [OapsProfileBoost.v5_exerciseActive] from V1's activity classification. */
internal fun v5ExerciseActive(activityState: String): Boolean = activityState in V5_EXERCISE_STATES

/**
 * [OapsProfileBoost.v5_inPostExerciseWindow] — true while the post-exercise recovery window is
 * open. Feeds V5's AggressionBudget post-exercise damper (postExerciseRecoveryModifier).
 */
internal fun v5InPostExerciseWindow(postExerciseRecoveryEnabled: Boolean, nowMs: Long, recoveryWindowEndMs: Long): Boolean =
    postExerciseRecoveryEnabled && nowMs < recoveryWindowEndMs
