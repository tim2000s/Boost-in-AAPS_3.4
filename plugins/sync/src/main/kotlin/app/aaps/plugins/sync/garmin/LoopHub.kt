package app.aaps.plugins.sync.garmin

import app.aaps.core.data.model.GV
import app.aaps.core.data.model.GlucoseUnit
import app.aaps.core.interfaces.profile.Profile
import java.time.Instant

/** Abstraction from all the functionality we need from the AAPS app. */
interface LoopHub {

    /** Returns the active insulin profile. */
    val currentProfile: Profile?

    /** Returns the name of the active insulin profile. */
    val currentProfileName: String

    /** Returns the glucose unit (mg/dl or mmol/l) as selected by the user. */
    val glucoseUnit: GlucoseUnit

    /** Returns the remaining bolus insulin on board. */
    val insulinOnboard: Double

    /** Returns the basal insulin on board. */
    val insulinBasalOnboard: Double

    /** Returns the remaining carbs on board. */
    val carbsOnboard: Double?

    /** Returns true if the pump is connected. */
    val isConnected: Boolean

    /** Returns true if the current profile is set of a limited amount of time. */
    val isTemporaryProfile: Boolean

    /** Returns the factor by which the basal rate is currently raised (> 1) or lowered (< 1). */
    val temporaryBasal: Double

    /** Short loop status for the watch: CLOSED / LGS / OPEN / SUSPEND / DISCONN / DISABLED / SUPERBOLUS. */
    val loopStatus: String

    /** Epoch-ms of the last APS run (loop "freshness"), or null if the loop has never run. */
    val lastLoopEpochMs: Long?

    /** Current DynISF / variable sensitivity in the user's glucose units (mg/dL·U or mmol/L·U), or
     *  null if unavailable. Falls back to the profile ISF when the APS hasn't produced a value. */
    val variableSensInUnits: Double?

    /** Returns the lower bound of the target glucose range. */
    val lowGlucoseMark: Double

    /** Returns the upper bound of the target glucose range. */
    val highGlucoseMark: Double

    /** Tells the loop algorithm that the pump is physically connected. */
    fun connectPump()

    /** Tells the loop algorithm that the pump will be physically disconnected
     *  for the given number of minutes. */
    fun disconnectPump(minutes: Int)

    /** Retrieves the glucose values starting at from. */
    fun getGlucoseValues(from: Instant, ascending: Boolean): List<GV>

    /** Notifies the system that carbs were eaten and stores the value. */
    fun postCarbs(carbohydrates: Int)

    /** Stores hear rate readings that a taken and averaged of the given interval. */
    fun storeHeartRate(
        samplingStart: Instant, samplingEnd: Instant,
        avgHeartRate: Int,
        device: String?
    )

    /** Stores a batch of fine-grained (≈1-min) HR samples. Each pair is (endOfMinuteEpochMs, bpm);
     *  stored with the HR-model convention timestamp = END of a 60 000 ms window, matching the
     *  Health Connect ingest so per-minute buckets dedupe. Peak preservation is downstream:
     *  Boost's hrBpmMax5m/Min5m take max/min over these 1-min rows. (2026-07-08, Garmin workstream B.) */
    fun storeHeartRates(samples: List<Pair<Long, Int>>, device: String?)

    /** Stores a Garmin step-count snapshot as an SC row (the same shape wear uses), so Boost's
     *  step subsystem (WearStepSource / IntradayStepBank / activity classifier) can consume it via
     *  the GARMIN source. [timestampMs] = end of the sampling; the six trailing-window counts are
     *  computed device-side from the cumulative counter. (2026-07-08, Garmin workstream B.) */
    fun storeSteps(
        timestampMs: Long,
        steps5min: Int, steps10min: Int, steps15min: Int,
        steps30min: Int, steps60min: Int, steps180min: Int,
        device: String?
    )
}
