package app.aaps.core.interfaces.aps

import androidx.collection.LongSparseArray
import app.aaps.core.data.iob.InMemoryGlucoseValue
import app.aaps.core.data.model.GV
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.utils.DateUtil

interface AutosensDataStore {

    val dataLock: Any

    var bgReadings: List<GV>
    var autosensDataTable: LongSparseArray<AutosensData>
    var bucketedData: MutableList<InMemoryGlucoseValue>?

    /**
     * The same glucose at the sensor's OWN cadence, rather than resampled to five minutes.
     *
     * [bucketedData] is built by stepping back in fixed five-minute increments and interpolating,
     * so on a one-minute sensor four of every five readings are replaced by an interpolation of
     * their neighbours. That is deliberate for the sensitivity chain, which defines deviations
     * and carbohydrate impact per five-minute bucket and would be silently rescaled by a change
     * of interval. Consumers that work in elapsed time rather than sample counts, the smoother
     * and the delta calculation, can use this instead and see every reading.
     *
     * Identical to [bucketedData] on a five-minute feed. Null until [createBucketedData] runs.
     */
    var bucketedDataNative: MutableList<InMemoryGlucoseValue>?

    /** Median spacing of the raw readings in minutes, or null when it cannot be established. */
    var detectedCadenceMinutes: Double?

    var lastUsed5minCalculation: Boolean?

    /**
     * Return last valid (>39) InMemoryGlucoseValue from bucketed data or null if db is empty
     *
     * @return InMemoryGlucoseValue or null
     */
    fun lastBg(): InMemoryGlucoseValue?

    /**
     * Provide last bucketed InMemoryGlucoseValue or null if none exists within the last 9 minutes
     *
     * @return InMemoryGlucoseValue or null
     */
    fun actualBg(): InMemoryGlucoseValue?

    /**
     * Last NATIVE-cadence InMemoryGlucoseValue within the last 9 minutes, or null.
     *
     * [actualBg] reads the five-minute bucketed series, so on a faster sensor its timestamp only
     * advances every five minutes. That is what decides how often the loop runs: InvokeLoopWorker
     * skips a cycle whose glucose timestamp it has already looped on, so a one-minute feed still
     * produces a five-minute loop. This accessor exists so the loop can be driven at the sensor's
     * own cadence instead, and is used only where that is explicitly enabled.
     *
     * On a five-minute feed the native series IS the bucketed series, so this returns exactly what
     * [actualBg] does. (2026-08-09)
     */
    fun actualBgNative(): InMemoryGlucoseValue?
    fun lastDataTime(dateUtil: DateUtil): String
    fun clone(): AutosensDataStore
    fun getBgReadingsDataTableCopy(): List<GV>
    fun getLastAutosensData(reason: String, aapsLogger: AAPSLogger, dateUtil: DateUtil): AutosensData?
    fun getAutosensDataAtTime(fromTime: Long): AutosensData?
    fun getBucketedDataTableCopy(): MutableList<InMemoryGlucoseValue>?

    /**
     * Copy of [bucketedDataNative], falling back to [bucketedData] when no native series exists.
     * For consumers that work in elapsed time and want every reading the sensor produced.
     */
    fun getBucketedDataNativeTableCopy(): MutableList<InMemoryGlucoseValue>?
    fun createBucketedData(aapsLogger: AAPSLogger, dateUtil: DateUtil)
    fun slowAbsorptionPercentage(timeInMinutes: Int): Double
    fun newHistoryData(time: Long, aapsLogger: AAPSLogger, dateUtil: DateUtil)
    fun roundUpTime(time: Long): Long
    fun reset()
}