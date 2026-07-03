package app.aaps.plugins.aps.openAPSBoost

import android.content.Context
import android.content.Intent
import androidx.core.net.toUri
import androidx.preference.PreferenceCategory
import androidx.preference.PreferenceFragmentCompat
import androidx.preference.PreferenceManager
import androidx.preference.PreferenceScreen
import androidx.preference.SwitchPreference
import app.aaps.core.data.aps.SMBDefaults
import app.aaps.core.data.configuration.Constants
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
    private val profiler: Profiler,
    private val apsResultProvider: Provider<APSResult>
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
    private val dynIsfNormalTarget; get() = profileUtil.convertToMgdlDetect(preferences.get(UnitDoubleKey.ApsBoostDynIsfNormalTarget))
    private val dynIsfVelocity; get() = preferences.get(DoubleKey.ApsBoostDynIsfVelocity) / 100.0
    private val dynIsfBgCap; get() = profileUtil.convertToMgdlDetect(preferences.get(UnitDoubleKey.ApsBoostDynIsfBgCap))

    // Boost SMB
    private val boostBolus; get() = preferences.get(DoubleKey.ApsBoostBolus)
    private val boostMaxIob; get() = preferences.get(DoubleKey.ApsBoostMaxIob)
    private val boostInsulinReqPct; get() = preferences.get(DoubleKey.ApsBoostInsulinReqPct)
    private val boostScale; get() = preferences.get(DoubleKey.ApsBoostScale)
    private val boostPercentScale; get() = preferences.get(DoubleKey.ApsBoostPercentScale)
    private val enableBoostPercentScale; get() = preferences.get(BooleanKey.ApsBoostEnablePercentScale)
    private val enableCircadianIsf; get() = preferences.get(BooleanKey.ApsBoostEnableCircadianIsf)
    private val allowBoostWithHighTt; get() = preferences.get(BooleanKey.ApsBoostAllowWithHighTt)

    // Boost time window
    private val boostStartTime; get() = preferences.get(StringKey.ApsBoostStartTime)
    private val boostEndTime; get() = preferences.get(StringKey.ApsBoostEndTime)
    private val sleepInHours; get() = preferences.get(DoubleKey.ApsBoostSleepInHours)

    // Step counting thresholds
    private val inactivitySteps; get() = preferences.get(IntKey.ApsBoostInactivitySteps)
    private val inactivityPct; get() = preferences.get(DoubleKey.ApsBoostInactivityPct)
    private val sleepInSteps; get() = preferences.get(IntKey.ApsBoostSleepInSteps)
    private val activitySteps5; get() = preferences.get(IntKey.ApsBoostActivitySteps5)
    private val activitySteps15; get() = preferences.get(IntKey.ApsBoostActivitySteps15)
    private val activitySteps30; get() = preferences.get(IntKey.ApsBoostActivitySteps30)
    private val activitySteps60; get() = preferences.get(IntKey.ApsBoostActivitySteps60)
    private val activityPct; get() = preferences.get(DoubleKey.ApsBoostActivityPct)

    // Heart rate integration
    private val hrIntegrationEnabled; get() = preferences.get(BooleanKey.ApsBoostHrIntegrationEnabled)
    private val hrMaxBpm; get() = preferences.get(IntKey.ApsBoostHrMaxBpm)
    private val hrRestingBpm; get() = preferences.get(IntKey.ApsBoostHrRestingBpm)
    private val hrWindowMinutes; get() = preferences.get(IntKey.ApsBoostHrWindowMinutes)
    private val hrStressDetection; get() = preferences.get(BooleanKey.ApsBoostHrStressDetection)

    // Post-exercise recovery
    private val postExerciseRecoveryEnabled; get() = preferences.get(BooleanKey.ApsBoostPostExerciseRecoveryEnabled)
    private val postExerciseRecoveryHours; get() = preferences.get(DoubleKey.ApsBoostPostExerciseRecoveryHours)
    private val postExerciseRecoveryTarget; get() = profileUtil.convertToMgdlDetect(preferences.get(UnitDoubleKey.ApsBoostPostExerciseRecoveryTarget))
    private val postExerciseRecoveryScale; get() = preferences.get(DoubleKey.ApsBoostPostExerciseRecoveryScale)
    private val postExerciseMinDuration; get() = preferences.get(IntKey.ApsBoostPostExerciseMinDuration)

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
        val allowAllBgSources = preferences.get(BooleanKey.ApsBoostAllowAllBgSources)
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
        val isfDebug: String = ""
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
        var tdd = 0.0
        val bgCurrent = if (glucoseValue > bgCap) bgCap + ((glucoseValue - bgCap) / 3.0) else glucoseValue

        val debug = StringBuilder()

        // TDD-based ISF calculation
        val useTdd = preferences.get(BooleanKey.ApsBoostUseTdd)
        val adjustSens = preferences.get(BooleanKey.ApsBoostAdjustSensitivity)

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
                if (tdd > 0 && logTerm > 0) {
                    sensNormalTarget = 1800.0 / (tdd * logTerm)
                    sensNormalTarget *= globalScale
                    debug.append("\nTDD ISF at target: ${Round.roundTo(sensNormalTarget, 0.1)} mg/dl/U (profile was ${Round.roundTo(profileSens, 0.1)})")

                    if (adjustSens && tddLast24H > 0) {
                        ratio = max(min(tddLast24H / tdd7D, autosensMax), autosensMin)
                        sensNormalTarget /= ratio
                        debug.append("\nSens ratio: ${Round.roundTo(ratio, 0.01)} (24H/7D = ${Round.roundTo(tddLast24H, 0.1)}/${Round.roundTo(tdd7D, 0.1)}) → ISF=${Round.roundTo(sensNormalTarget, 0.1)}")
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
            isfDebug = debug.toString()
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
        val debugReason: String = ""
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

        var boostStart = midnight + parseTimeToMillis(boostStartTime)
        var boostEnd = midnight + parseTimeToMillis(boostEndTime)

        val nowTime = java.time.Instant.ofEpochMilli(now).atZone(java.time.ZoneId.systemDefault()).toLocalTime()
        debug.append("Boost window: $boostStartTime–$boostEndTime | Now: ${nowTime.format(DateTimeFormatter.ofPattern("HH:mm"))}")

        if (boostStart > boostEnd) {
            if (now > boostEnd) boostEnd += 86400000L
            else boostStart -= 86400000L
            debug.append(" (overnight wrap)")
        }

        var boostActive = now in boostStart until boostEnd
        var disableReason = ""

        if (!boostActive) {
            disableReason = "Outside boost time window"
        }

        // Disable boost if high temp target and not allowed
        if (boostActive && tempTargetSet && !allowBoostWithHighTt && targetBg > dynIsfNormalTarget) {
            boostActive = false
            disableReason = "High temp target ($targetBg > ${dynIsfNormalTarget})"
            aapsLogger.debug(LTag.APS, "Boost disabled due to high temptarget of $targetBg")
        }

        val recentSteps5Min = StepService.getRecentStepCount5Min()
        val recentSteps15Min = StepService.getRecentStepCount15Min()
        val recentSteps30Min = StepService.getRecentStepCount30Min()
        val recentSteps60Min = StepService.getRecentStepCount60Min()

        debug.append("\nSteps: 5m=$recentSteps5Min 15m=$recentSteps15Min 30m=$recentSteps30Min 60m=$recentSteps60Min")

        // Sleep-in detection
        val inSleepInWindow = now in boostStart until (boostStart + sleepInMillis)
        if (boostActive && inSleepInWindow && recentSteps60Min < sleepInSteps) {
            boostActive = false
            disableReason = "Sleep-in (60m steps $recentSteps60Min < threshold $sleepInSteps, within ${sleepInHours}h of start)"
            aapsLogger.debug(LTag.APS, "Boost disabled due to lie-in")
        } else if (inSleepInWindow && boostActive) {
            debug.append("\nSleep-in window active but overridden (steps $recentSteps60Min >= $sleepInSteps)")
        }

        var activityMinBg = minBg
        var activityMaxBg = maxBg
        var activityTargetBg = targetBg
        var currentProfileSwitch = profilePercent
        var activityState = "none"

        if (boostActive) {
            val activityBgTarget = 150.0
            val isActive = recentSteps5Min > activitySteps5
                || recentSteps15Min > activitySteps15
                || recentSteps30Min > activitySteps30
                || recentSteps60Min > activitySteps60

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
                        hrResting = hrRestingBpm,
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
            } else if (currentProfileSwitch == 100 && recentSteps60Min < inactivitySteps) {
                // Inactivity confirmed or no steps — check HR for stress
                if (hrStressDetection &&
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
            debugReason = debug.toString()
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

    // ---- Main invoke ----

    override fun invoke(initiator: String, tempBasalFallback: Boolean) {
        aapsLogger.debug(LTag.APS, "invoke from $initiator tempBasalFallback: $tempBasalFallback")
        lastAPSResult = null
        val glucoseStatus = glucoseStatusCalculatorSMB.glucoseStatusData
        val profile = profileFunction.getProfile()
        val pump = activePlugin.activePump
        if (profile == null) {
            rxBus.send(EventResetOpenAPSGui(rh.gs(app.aaps.core.ui.R.string.no_profile_set)))
            aapsLogger.debug(LTag.APS, rh.gs(app.aaps.core.ui.R.string.no_profile_set))
            return
        }
        if (!isEnabled()) {
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
        val allowAllBgSources = preferences.get(BooleanKey.ApsBoostAllowAllBgSources)
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

        // 4. Adjust autosens ratio from ISF calculation
        autosensResult.ratio = isfResult.ratio

        // 5. Adjust basal if profile switch from activity
        val currentBasal = if (activityResult.profileSwitch != 100) {
            val adjusted = pump.baseBasalRate * profileScale
            aapsLogger.debug(LTag.APS, "Basal adjusted to $adjusted")
            adjusted
        } else pump.baseBasalRate

        // 6. Recent BG nadir + braking signal (for fast-carb detection)
        val now60MinAgo = System.currentTimeMillis() - 60 * 60 * 1000L
        val recentBgReadings = persistenceLayer.getBgReadingsDataFromTimeToTime(now60MinAgo, System.currentTimeMillis(), true)
        val recentLowBG = recentBgReadings.minOfOrNull { it.value }?.toDouble() ?: 999.0
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

        // ---- Build the OapsProfileBoost ----

        val oapsProfile = OapsProfileBoost(
            // Standard oref1 fields
            dia = 0.0,
            min_5m_carbimpact = 0.0,
            max_iob = constraintsChecker.getMaxIOBAllowed().also { inputConstraints.copyReasons(it) }.value(),
            max_daily_basal = profile.getMaxDailyBasal(),
            max_basal = constraintsChecker.getMaxBasalAllowed(profile).also { inputConstraints.copyReasons(it) }.value(),
            min_bg = activityResult.minBg,
            max_bg = activityResult.maxBg,
            target_bg = activityResult.targetBg,
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
            isfDebugReason = isfResult.isfDebug
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

        determineBasalBoost.determine_basal(
            glucose_status = glucoseStatus,
            currenttemp = currentTemp,
            iob_data_array = iobArray,
            profile = oapsProfile,
            autosens_data = autosensResult,
            meal_data = mealData,
            microBolusAllowed = microBolusAllowed,
            currentTime = now,
            flatBGsDetected = flatBGsDetected
        ).also {
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
        if (isEnabled()) {
            val maxIobPref = preferences.get(DoubleKey.ApsSmbMaxIob)
            maxIob.setIfSmaller(maxIobPref, rh.gs(R.string.limiting_iob, maxIobPref, rh.gs(R.string.maxvalueinpreferences)), this)
            maxIob.setIfSmaller(hardLimits.maxIobSMB(), rh.gs(R.string.limiting_iob, hardLimits.maxIobSMB(), rh.gs(R.string.hardlimit)), this)
        }
        return maxIob
    }

    override fun applyBasalConstraints(absoluteRate: Constraint<Double>, profile: Profile): Constraint<Double> {
        if (isEnabled()) {
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

    private var lastNightModeRun: Long = 0
    private var lastNightModeResult: Boolean = false

    private fun isNightModeActive(): Boolean {
        val currentTimeMillis = System.currentTimeMillis()
        val timeAligned = currentTimeMillis - (currentTimeMillis % 1000)
        if (lastNightModeRun >= timeAligned) return lastNightModeResult
        lastNightModeResult = isNightModeActiveImpl()
        lastNightModeRun = timeAligned
        return lastNightModeResult
    }

    private fun isNightModeActiveImpl(): Boolean {
        if (!preferences.get(BooleanKey.ApsBoostNightModeEnabled)) return false

        val bgCurrent = glucoseStatusCalculatorSMB.getGlucoseStatusData(true)?.glucose ?: return false

        val now = System.currentTimeMillis()
        val midnight = now - MidnightUtils.milliSecFromMidnight(now)
        val startStr = preferences.get(StringKey.ApsBoostNightModeStart)
        val endStr = preferences.get(StringKey.ApsBoostNightModeEnd)
        val start = midnight + parseTimeToMillis(startStr)
        val end = midnight + parseTimeToMillis(endStr)
        val active = if (end > start) now in start until end
        else (now in (start - 86400000) until end || now in start until (end + 86400000))

        if (!active) return false

        // Disable night mode when COB > 0
        if (preferences.get(BooleanKey.ApsBoostNightModeDisableWithCob)) {
            val mealData = iobCobCalculator.getMealDataWithWaitingForCalculationFinish()
            if (mealData.mealCOB > 0) return false
        }

        // Disable night mode with low temp target
        if (preferences.get(BooleanKey.ApsBoostNightModeDisableWithLowTt)) {
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
        val bgOffset = profileUtil.convertToMgdl(preferences.get(UnitDoubleKey.ApsBoostNightModeBgOffset), profileUtil.units)
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
            requiredKey != "boost_safety_settings"
        ) return
        val category = PreferenceCategory(context)
        parent.addPreference(category)
        category.apply {
            key = "openapsboost_settings"
            title = rh.gs(R.string.openaps_boost)
            initialExpandedChildrenCount = 0

            // ── 1. Default AAPS Settings ────────────────────────────────
            addPreference(preferenceManager.createPreferenceScreen(context).apply {
                key = "boost_default_aaps_settings"
                title = rh.gs(R.string.boost_settings_default_aaps)
                addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsMaxBasal, dialogMessage = R.string.openapsma_max_basal_summary, title = R.string.openapsma_max_basal_title))
                addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsSmbMaxIob, dialogMessage = R.string.openapssmb_max_iob_summary, title = R.string.openapssmb_max_iob_title))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseAutosens, title = R.string.openapsama_use_autosens))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsAutoIsfHighTtRaisesSens, summary = R.string.high_temptarget_raises_sensitivity_summary, title = R.string.high_temptarget_raises_sensitivity_title))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsAutoIsfLowTtLowersSens, summary = R.string.low_temptarget_lowers_sensitivity_summary, title = R.string.low_temptarget_lowers_sensitivity_title))
            })

            // ── 2. Boost Controls (flat, not in a sub-menu) ─────────────
            addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostInsulinReqPct, dialogMessage = R.string.boost_insulin_req_summary, title = R.string.boost_insulin_req_title))
            addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostBolus, dialogMessage = R.string.boost_bolus_summary, title = R.string.boost_bolus_title))
            addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostPercentScale, dialogMessage = R.string.boost_percent_scale_summary, title = R.string.boost_percent_scale_title))
            addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostScale, dialogMessage = R.string.boost_scale_summary, title = R.string.boost_scale_title))
            addPreference(AdaptiveDoublePreference(ctx = context, doubleKey = DoubleKey.ApsBoostMaxIob, dialogMessage = R.string.boost_max_iob_summary, title = R.string.boost_max_iob_title))
            addPreference(AdaptiveStringPreference(ctx = context, stringKey = StringKey.ApsBoostStartTime, dialogMessage = R.string.boost_start_summary, title = R.string.boost_start_title))
            addPreference(AdaptiveStringPreference(ctx = context, stringKey = StringKey.ApsBoostEndTime, dialogMessage = R.string.boost_end_summary, title = R.string.boost_end_title))
            addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostEnablePercentScale, summary = R.string.boost_enable_percent_scale_summary, title = R.string.boost_enable_percent_scale_title))
            addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostEnableCircadianIsf, summary = R.string.boost_enable_circadian_isf_summary, title = R.string.boost_enable_circadian_isf_title))
            addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostAllowWithHighTt, summary = R.string.boost_allow_high_tt_summary, title = R.string.boost_allow_high_tt_title))

            // ── 3. Dynamic ISF Controls ──────────────────────────────────
            addPreference(preferenceManager.createPreferenceScreen(context).apply {
                key = "boost_dynisf_settings"
                title = rh.gs(R.string.boost_dynisf_title)
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostUseTdd, summary = R.string.boost_use_tdd_summary, title = R.string.boost_use_tdd_title))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostAdjustSensitivity, summary = R.string.boost_adjust_sensitivity_summary, title = R.string.boost_adjust_sensitivity_title))
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
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostNightModeEnabled, summary = R.string.boost_night_mode_enabled_summary, title = R.string.boost_night_mode_enabled_title))
                addPreference(AdaptiveStringPreference(ctx = context, stringKey = StringKey.ApsBoostNightModeStart, dialogMessage = R.string.boost_night_mode_start_summary, title = R.string.boost_night_mode_start_title))
                addPreference(AdaptiveStringPreference(ctx = context, stringKey = StringKey.ApsBoostNightModeEnd, dialogMessage = R.string.boost_night_mode_end_summary, title = R.string.boost_night_mode_end_title))
                addPreference(AdaptiveUnitPreference(ctx = context, unitKey = UnitDoubleKey.ApsBoostNightModeBgOffset, dialogMessage = R.string.boost_night_mode_bg_offset_summary, title = R.string.boost_night_mode_bg_offset_title))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostNightModeDisableWithCob, summary = R.string.boost_night_mode_disable_with_cob_summary, title = R.string.boost_night_mode_disable_with_cob_title))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostNightModeDisableWithLowTt, summary = R.string.boost_night_mode_disable_with_low_tt_summary, title = R.string.boost_night_mode_disable_with_low_tt_title))
            })

            // ── 6. Safety Settings ───────────────────────────────────────
            addPreference(preferenceManager.createPreferenceScreen(context).apply {
                key = "boost_safety_settings"
                title = rh.gs(R.string.boost_settings_safety)
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseSmb, summary = R.string.enable_smb_summary, title = R.string.enable_smb))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseSmbWithHighTt, summary = R.string.enable_smb_with_high_temp_target_summary, title = R.string.enable_smb_with_high_temp_target))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseSmbAlways, summary = R.string.enable_smb_always_summary, title = R.string.enable_smb_always))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseSmbWithCob, summary = R.string.enable_smb_with_cob_summary, title = R.string.enable_smb_with_cob))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseSmbWithLowTt, summary = R.string.enable_smb_with_temp_target_summary, title = R.string.enable_smb_with_temp_target))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseSmbAfterCarbs, summary = R.string.enable_smb_after_carbs_summary, title = R.string.enable_smb_after_carbs))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsUseUam, summary = R.string.enable_uam_summary, title = R.string.enable_uam))
                addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsMaxSmbFrequency, title = R.string.smb_interval_summary))
                addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsMaxMinutesOfBasalToLimitSmb, title = R.string.smb_max_minutes_summary))
                addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsUamMaxMinutesOfBasalToLimitSmb, dialogMessage = R.string.uam_smb_max_minutes, title = R.string.uam_smb_max_minutes_summary))
                addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.ApsCarbsRequestThreshold, dialogMessage = R.string.carbs_req_threshold_summary, title = R.string.carbs_req_threshold))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostAllowAllBgSources, summary = R.string.boost_allow_all_bg_sources_summary, title = R.string.boost_allow_all_bg_sources_title))
                addPreference(AdaptiveSwitchPreference(ctx = context, booleanKey = BooleanKey.ApsBoostBypassVersionCheck, summary = R.string.boost_bypass_version_check_summary, title = R.string.boost_bypass_version_check_title))
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
