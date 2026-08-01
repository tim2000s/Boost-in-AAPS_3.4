package app.aaps.plugins.sync.garmin

import androidx.annotation.VisibleForTesting
import app.aaps.core.data.model.GV
import app.aaps.core.data.model.GlucoseUnit
import app.aaps.core.data.model.HR
import app.aaps.core.data.model.RM
import app.aaps.core.data.model.SC
import app.aaps.core.data.model.TE
import app.aaps.core.data.ue.Action
import app.aaps.core.data.ue.Sources
import app.aaps.core.data.ue.ValueWithUnit
import app.aaps.core.interfaces.aps.Loop
import app.aaps.core.interfaces.constraints.ConstraintsChecker
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.db.ProcessedTbrEbData
import app.aaps.core.interfaces.iob.IobCobCalculator
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import app.aaps.core.interfaces.logging.UserEntryLogger
import app.aaps.core.interfaces.profile.Profile
import app.aaps.core.interfaces.profile.ProfileFunction
import app.aaps.core.interfaces.profile.ProfileUtil
import app.aaps.core.interfaces.pump.DetailedBolusInfo
import app.aaps.core.interfaces.queue.CommandQueue
import app.aaps.core.keys.StringKey
import app.aaps.core.keys.UnitDoubleKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.core.objects.extensions.convertedToPercent
import io.reactivex.rxjava3.disposables.CompositeDisposable
import io.reactivex.rxjava3.kotlin.plusAssign
import java.time.Clock
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Interface to the functionality of the looping algorithm and storage systems.
 */
@Singleton
class LoopHubImpl @Inject constructor(
    private val aapsLogger: AAPSLogger,
    private val commandQueue: CommandQueue,
    private val constraintChecker: ConstraintsChecker,
    private val iobCobCalculator: IobCobCalculator,
    private val loop: Loop,
    private val profileFunction: ProfileFunction,
    private val profileUtil: ProfileUtil,
    private val persistenceLayer: PersistenceLayer,
    private val userEntryLogger: UserEntryLogger,
    private val preferences: Preferences,
    private val processedTbrEbData: ProcessedTbrEbData
) : LoopHub {

    val disposable = CompositeDisposable()

    @VisibleForTesting
    var clock: Clock = Clock.systemUTC()

    /** Returns the active insulin profile. */
    override val currentProfile: Profile? get() = profileFunction.getProfile()

    /** Returns the name of the active insulin profile. */
    override val currentProfileName: String
        get() = profileFunction.getProfileName()

    /** Returns the glucose unit (mg/dl or mmol/l) as selected by the user. */
    override val glucoseUnit: GlucoseUnit
        get() = GlucoseUnit.fromText(preferences.get(StringKey.GeneralUnits))

    /** Returns the remaining bolus insulin on board. */
    override val insulinOnboard: Double
        get() = iobCobCalculator.calculateIobFromBolus().iob

    /** Returns the remaining bolus and basal insulin on board. */
    override val insulinBasalOnboard: Double
        get() = iobCobCalculator.calculateIobFromTempBasalsIncludingConvertedExtended().basaliob

    /** Returns the remaining carbs on board. */
    override val carbsOnboard: Double?
        get() = iobCobCalculator.getCobInfo("LoopHubImpl").displayCob

    /** Returns true if the pump is connected. */
    override val isConnected: Boolean get() = loop.runningMode != RM.Mode.DISCONNECTED_PUMP

    /** Short loop status for the watch face. */
    override val loopStatus: String
        get() = when (loop.runningMode) {
            RM.Mode.CLOSED_LOOP       -> "CLOSED"
            RM.Mode.CLOSED_LOOP_LGS   -> "LGS"
            RM.Mode.OPEN_LOOP         -> "OPEN"
            RM.Mode.DISABLED_LOOP     -> "DISABLED"
            RM.Mode.SUPER_BOLUS       -> "SUPERBOLUS"
            RM.Mode.DISCONNECTED_PUMP -> "DISCONN"
            RM.Mode.SUSPENDED_BY_PUMP,
            RM.Mode.SUSPENDED_BY_USER,
            RM.Mode.SUSPENDED_BY_DST  -> "SUSPEND"
            else                      -> "LOOP"   // RESUME / any transient or future mode
        }

    /** Epoch-ms of the last APS run (loop freshness), or null if it has never run. */
    override val lastLoopEpochMs: Long?
        get() = loop.lastRun?.lastAPSRun

    /** Current DynISF / variable sensitivity in the user's glucose units. Prefer the live APS
     *  variable_sens; fall back to the profile ISF; null if neither is available. */
    override val variableSensInUnits: Double?
        get() {
            val mgdl = loop.lastRun?.constraintsProcessed?.variableSens
                ?: currentProfile?.getIsfMgdl("GarminLoopHub")
                ?: return null
            return profileUtil.fromMgdlToUnits(mgdl, glucoseUnit)
        }

    /** Returns true if the current profile is set of a limited amount of time. */
    override val isTemporaryProfile: Boolean
        get() {
            val ps = persistenceLayer.getEffectiveProfileSwitchActiveAt(clock.millis())
            return ps != null && ps.originalDuration > 0
        }

    /** Returns the factor by which the basal rate is currently raised (> 1) or lowered (< 1). */
    override val temporaryBasal: Double
        get() {
            return currentProfile?.let {
                val tb = processedTbrEbData.getTempBasalIncludingConvertedExtended(clock.millis())
                tb?.convertedToPercent(clock.millis(), it)?.div(100.0)
            } ?: Double.NaN
        }

    override val lowGlucoseMark
        get() = profileUtil.convertToMgdl(
            preferences.get(UnitDoubleKey.OverviewLowMark), glucoseUnit
        )

    override val highGlucoseMark
        get() = profileUtil.convertToMgdl(
            preferences.get(UnitDoubleKey.OverviewHighMark), glucoseUnit
        )

    /** Tells the loop algorithm that the pump is physically connected. */
    override fun connectPump() {
        disposable += persistenceLayer.cancelCurrentRunningMode(clock.millis(), Action.RECONNECT, Sources.Garmin).subscribe()
        commandQueue.cancelTempBasal(enforceNew = true, callback = null)
    }

    /** Tells the loop algorithm that the pump will be physically disconnected
     *  for the given number of minutes. */
    override fun disconnectPump(minutes: Int) {
        currentProfile?.let { p ->
            loop.handleRunningModeChange(
                durationInMinutes = minutes,
                profile = p,
                newRM = RM.Mode.DISCONNECTED_PUMP,
                action = Action.DISCONNECT,
                source = Sources.Garmin,
                listValues = listOf(ValueWithUnit.Minute(minutes))
            )
        }
    }

    /** Retrieves the glucose values starting at from. */
    override fun getGlucoseValues(from: Instant, ascending: Boolean): List<GV> {
        return persistenceLayer.getBgReadingsDataFromTime(from.toEpochMilli(), ascending)
            .blockingGet()
    }

    /** Notifies the system that carbs were eaten and stores the value. */
    override fun postCarbs(carbohydrates: Int) {
        aapsLogger.info(LTag.GARMIN, "post $carbohydrates g carbohydrates")
        val carbsAfterConstraints =
            carbohydrates.coerceAtMost(constraintChecker.getMaxCarbsAllowed().value())
        userEntryLogger.log(
            action = Action.CARBS,
            source = Sources.Garmin,
            note = null,
            listValues = listOf(ValueWithUnit.Gram(carbsAfterConstraints))
        )
        val detailedBolusInfo = DetailedBolusInfo().apply {
            eventType = TE.Type.CARBS_CORRECTION
            carbs = carbsAfterConstraints.toDouble()
        }
        commandQueue.bolus(detailedBolusInfo, null)
    }

    /** Stores hear rate readings that a taken and averaged of the given interval. */
    override fun storeHeartRate(
        samplingStart: Instant, samplingEnd: Instant,
        avgHeartRate: Int,
        device: String?
    ) {
        val hr = HR(
            timestamp = samplingStart.toEpochMilli(),
            duration = samplingEnd.toEpochMilli() - samplingStart.toEpochMilli(),
            dateCreated = clock.millis(),
            beatsPerMinute = avgHeartRate.toDouble(),
            device = device ?: "Garmin",
        )
        disposable += persistenceLayer.insertOrUpdateHeartRate(hr).subscribe()
    }

    override fun storeSteps(
        timestampMs: Long,
        steps5min: Int, steps10min: Int, steps15min: Int,
        steps30min: Int, steps60min: Int, steps180min: Int,
        device: String?
    ) {
        if (timestampMs <= 0L) return
        val sc = SC(
            duration = 300_000L,          // 5-min snapshot (mirrors the wear cadence)
            timestamp = timestampMs,
            steps5min = steps5min, steps10min = steps10min, steps15min = steps15min,
            steps30min = steps30min, steps60min = steps60min, steps180min = steps180min,
            device = device ?: "Garmin",
            dateCreated = clock.millis(),
        )
        disposable += persistenceLayer.insertOrUpdateStepsCount(sc).subscribe()
    }

    override fun storeHeartRates(samples: List<Pair<Long, Int>>, device: String?) {
        // Correct HR-model convention: timestamp = END of the minute, duration = 60 000 (matches
        // HealthConnectHrIngest so overlapping rows dedupe by minute bucket). insertOrUpdate is
        // idempotent, so a backfill batch on BT reconnect is safe to replay.
        val dev = device ?: "Garmin"
        for ((endMs, bpm) in samples) {
            if (bpm <= 10 || endMs <= 0L) continue
            val hr = HR(
                timestamp = endMs,
                duration = 60_000L,
                dateCreated = clock.millis(),
                beatsPerMinute = bpm.toDouble(),
                device = dev,
            )
            disposable += persistenceLayer.insertOrUpdateHeartRate(hr).subscribe()
        }
    }
}
