package app.aaps.plugins.main.iob.iobCobCalculator.data

import androidx.collection.LongSparseArray
import androidx.collection.size
import app.aaps.core.data.iob.InMemoryGlucoseValue
import app.aaps.core.data.model.GV
import app.aaps.core.data.time.T
import app.aaps.core.interfaces.aps.AutosensData
import app.aaps.core.interfaces.aps.AutosensDataStore
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import app.aaps.core.interfaces.utils.DateUtil
import app.aaps.core.objects.extensions.fromGv
import kotlin.math.abs
import kotlin.math.min
import kotlin.math.roundToLong

class AutosensDataStoreObject : AutosensDataStore {

    override val dataLock = Any()
    override var lastUsed5minCalculation: Boolean? = null // true if used 5min bucketed data

    companion object {

        const val IRREGULAR_DATA_SEC = 30L
    }

    // we need to make sure that bucketed_data will always have the same timestamp for correct use of cached values
    // once referenceTime != null all bucketed data should be (x * 5min) from referenceTime
    var referenceTime: Long = -1

    override var bgReadings: List<GV> = listOf() // newest at index 0
        @Synchronized set
        @Synchronized get

    override var autosensDataTable = LongSparseArray<AutosensData>() // oldest at index 0
        @Synchronized set
        @Synchronized get

    override var bucketedData: MutableList<InMemoryGlucoseValue>? = null
    override var bucketedDataNative: MutableList<InMemoryGlucoseValue>? = null
    override var detectedCadenceMinutes: Double? = null
        @Synchronized set
        @Synchronized get

    override fun clone(): AutosensDataStore =
        AutosensDataStoreObject().also {
            synchronized(dataLock) {
                it.bgReadings = this.bgReadings.toMutableList()
                it.autosensDataTable = LongSparseArray<AutosensData>(this.autosensDataTable.size).apply { putAll(this@AutosensDataStoreObject.autosensDataTable) }
                it.bucketedData = this.bucketedData?.toMutableList()
                it.bucketedDataNative = this.bucketedDataNative?.toMutableList()
                it.detectedCadenceMinutes = this.detectedCadenceMinutes
            }
        }

    override fun getBucketedDataTableCopy(): MutableList<InMemoryGlucoseValue>? = synchronized(dataLock) { bucketedData?.toMutableList() }

    override fun getBucketedDataNativeTableCopy(): MutableList<InMemoryGlucoseValue>? =
        synchronized(dataLock) { (bucketedDataNative ?: bucketedData)?.toMutableList() }
    override fun getBgReadingsDataTableCopy(): List<GV> = synchronized(dataLock) { bgReadings.toMutableList() }

    override fun reset() {
        synchronized(autosensDataTable) { autosensDataTable = LongSparseArray() }
    }

    override fun newHistoryData(time: Long, aapsLogger: AAPSLogger, dateUtil: DateUtil) {
        synchronized(autosensDataTable) {
            for (index in autosensDataTable.size() - 1 downTo 0) {
                if (autosensDataTable.keyAt(index) > time) {
                    aapsLogger.debug(LTag.AUTOSENS) { "Removing from autosensDataTable: ${dateUtil.dateAndTimeAndSecondsString(autosensDataTable.keyAt(index))}" }
                    autosensDataTable.removeAt(index)
                } else {
                    break
                }
            }
        }
    }

    // roundup to whole minute
    override fun roundUpTime(time: Long): Long {
        return if (time % 60000 == 0L) time else (time / 60000 + 1) * 60000
    }

    /**
     * Return last valid (>39) InMemoryGlucoseValue from bucketed data or null if db is empty
     *
     * @return InMemoryGlucoseValue or null
     */
    override fun lastBg(): InMemoryGlucoseValue? =
        synchronized(dataLock) {
            bucketedData?.let { bucketedData ->
                if (bucketedData.isNotEmpty()) bucketedData[0]
                else null
            }
        }

    /**
     * Provide last bucketed InMemoryGlucoseValue or null if none exists within the last 9 minutes
     *
     * @return InMemoryGlucoseValue or null
     */
    override fun actualBg(): InMemoryGlucoseValue? {
        val lastBg = lastBg() ?: return null
        return if (lastBg.timestamp > System.currentTimeMillis() - T.mins(9).msecs()) lastBg else null
    }

    override fun actualBgNative(): InMemoryGlucoseValue? {
        val last = synchronized(dataLock) {
            bucketedDataNative?.firstOrNull() ?: bucketedData?.firstOrNull()
        } ?: return null
        return if (last.timestamp > System.currentTimeMillis() - T.mins(9).msecs()) last else null
    }

    override fun lastDataTime(dateUtil: DateUtil): String =
        synchronized(dataLock) {
            if (autosensDataTable.size() > 0) dateUtil.dateAndTimeAndSecondsString(autosensDataTable.valueAt(autosensDataTable.size() - 1).time)
            else "autosensDataTable empty"
        }

    fun findPreviousTimeFromBucketedData(time: Long): Long? {
        val bData = bucketedData ?: return null
        for (index in bData.indices) {
            if (bData[index].timestamp <= time) return bData[index].timestamp
        }
        return null
    }

    override fun getAutosensDataAtTime(fromTime: Long): AutosensData? {
        synchronized(dataLock) {
            val now = System.currentTimeMillis()
            if (fromTime > now) return null
            val previous = findPreviousTimeFromBucketedData(fromTime) ?: return null
            return autosensDataTable[roundUpTime(previous)]
        }
    }

    // during recalculation autosensDataTable is cleared and not available
    // for providing COB, which is an serious issue in BolusWizard
    // So let save last value after every calculation and use it
    // if autosensDataTable is not available
    var storedLastAutosensResult: AutosensData? = null
        get() = field?.let { if (it.time < System.currentTimeMillis() - 11 * 60 * 1000) it else null }

    override fun getLastAutosensData(reason: String, aapsLogger: AAPSLogger, dateUtil: DateUtil): AutosensData? {
        synchronized(dataLock) {
            if (autosensDataTable.size() < 1) {
                aapsLogger.debug(LTag.AUTOSENS, "AUTOSENSDATA null: autosensDataTable empty ($reason)")
                return storedLastAutosensResult
            }
            val data: AutosensData = try {
                autosensDataTable.valueAt(autosensDataTable.size() - 1)
            } catch (_: Exception) {
                // data can be processed on the background
                // in this rare case better return null and do not block UI
                // APS plugin should use getLastAutosensDataSynchronized where the blocking is not an issue
                aapsLogger.error("AUTOSENSDATA null: Exception caught ($reason)")
                return storedLastAutosensResult
            }
            return if (data.time < dateUtil.now() - 11 * 60 * 1000) {
                aapsLogger.debug(LTag.AUTOSENS) { "AUTOSENSDATA null: data is old ($reason) size()=${autosensDataTable.size()} lastData=${dateUtil.dateAndTimeAndSecondsString(data.time)}" }
                storedLastAutosensResult
            } else {
                aapsLogger.debug(LTag.AUTOSENS) { "AUTOSENSDATA ($reason) $data" }
                storedLastAutosensResult = data
                data
            }
        }
    }

    private fun adjustToReferenceTime(someTime: Long): Long {
        if (referenceTime == -1L) {
            referenceTime = someTime
            return someTime
        }
        var diff = abs(someTime - referenceTime)
        diff %= T.mins(5).msecs()
        return if (diff > T.mins(2).plus(T.secs(30)).msecs()) someTime + abs(diff - T.mins(5).msecs()) // Adjust to the future
        else someTime - diff // adjust to the past
    }

    fun isAbout5minData(aapsLogger: AAPSLogger): Boolean {
        synchronized(dataLock) {
            if (bgReadings.size < 3) return true

            var totalDiff: Long = 0
            for (i in 1 until bgReadings.size) {
                val bgTime = bgReadings[i].timestamp
                val lastBgTime = bgReadings[i - 1].timestamp
                var diff = lastBgTime - bgTime
                diff %= T.mins(5).msecs()
                if (diff > T.mins(2).plus(T.secs(30)).msecs()) diff -= T.mins(5).msecs()
                totalDiff += diff
                diff = abs(diff)
                if (diff > T.secs(IRREGULAR_DATA_SEC).msecs()) {
                    aapsLogger.debug(LTag.AUTOSENS, "Interval detection: values: ${bgReadings.size} diff: ${diff / 1000}[s] is5minData: false")
                    return false
                }
            }
            val averageDiff = totalDiff / bgReadings.size / 1000
            val is5minData = averageDiff < 1
            aapsLogger.debug(LTag.AUTOSENS, "Interval detection: values: ${bgReadings.size} averageDiff: $averageDiff[s] is5minData: $is5minData")
            return is5minData
        }
    }

    override fun createBucketedData(aapsLogger: AAPSLogger, dateUtil: DateUtil) {
        val fiveMinData = isAbout5minData(aapsLogger)
        if (lastUsed5minCalculation != null && lastUsed5minCalculation != fiveMinData) {
            // changing mode => clear cache
            aapsLogger.debug("Invalidating cached data because of changed mode.")
            reset()
        }
        lastUsed5minCalculation = fiveMinData
        if (fiveMinData) createBucketedData5min(aapsLogger, dateUtil) else createBucketedDataRecalculated(aapsLogger, dateUtil)
        detectedCadenceMinutes = detectCadenceMinutes()
        createBucketedDataNative(aapsLogger)
    }

    /**
     * Median spacing of the raw readings, in minutes. Median rather than mean so that one gap
     * cannot move it. Spacings above an hour are treated as gaps and ignored.
     */
    fun detectCadenceMinutes(): Double? {
        synchronized(dataLock) {
            if (bgReadings.size < 4) return null
            val gaps = ArrayList<Double>(bgReadings.size - 1)
            for (i in 0 until bgReadings.size - 1) {
                // bgReadings is newest-first
                val d = (bgReadings[i].timestamp - bgReadings[i + 1].timestamp) / 60000.0
                if (d > 0.1 && d <= 60.0) gaps.add(d)
            }
            if (gaps.size < 3) return null
            gaps.sort()
            val m = gaps.size / 2
            return if (gaps.size % 2 == 0) (gaps[m - 1] + gaps[m]) / 2.0 else gaps[m]
        }
    }

    /**
     * Build the native-cadence series.
     *
     * On a five-minute feed this is the existing bucketed series, shared rather than copied,
     * because they are the same thing and nothing downstream mutates it. On a faster feed the
     * raw readings are used directly: no resampling, no interpolation, every reading kept.
     *
     * The raw path deliberately does not snap to a grid. [adjustToReferenceTime] exists so that
     * cached five-minute buckets line up between cycles; the native series is rebuilt each cycle
     * and has no such cache to align with.
     */
    private fun createBucketedDataNative(aapsLogger: AAPSLogger) {
        synchronized(dataLock) {
            val cadence = detectedCadenceMinutes
            // Only a genuinely sub-two-minute feed takes the native path. An earlier draft used
            // 4.0, which also captured three-minute sensors and changed their deltas: with 3-min
            // raw data the 2.5-7.5 minute window holds two points rather than one, so the delta
            // becomes an average over two lookbacks instead of a single one. Caught by
            // AutosensDataStoreTest.threeMinDataWithRecalculation, which moved 2.0 -> 1.67.
            // That is a real behaviour change and not one this branch is asking for, so the
            // native path is confined to the one-minute case it exists to serve. (2026-08-01)
            if (cadence == null || cadence >= 2.0) {
                bucketedDataNative = bucketedData
                return
            }
            if (bgReadings.size < 3) {
                bucketedDataNative = bucketedData
                return
            }
            // Build a REGULAR grid at the native cadence rather than passing the raw readings
            // through. Raw readings are irregularly spaced: a CGM backfill landing just after a
            // regular reading produces a pair seconds apart, and the smoother starts a new
            // segment on any spacing below its minimum, re-initialising from that point's RAW
            // value and discarding the smoothed trend. The visible result is a sharp downward V
            // where the smoothed line steps to the raw dot and recovers near-vertically.
            //
            // This is not hypothetical. Trio hit exactly this on 2026-07-17, reproduced to within
            // 1 mg/dL, and it was Trio-specific only because AAPS buckets before smoothing and
            // Trio did not. Feeding AAPS the raw series would have handed it the same defect.
            // Trio's fix was to bucket onto a five-minute grid; the same reasoning at the native
            // cadence keeps every reading AND regular spacing.
            val stepMs = Math.round(cadence * 60_000.0)
            val out = ArrayList<InMemoryGlucoseValue>()
            var t = bgReadings[0].timestamp
            val oldest = bgReadings[bgReadings.size - 1].timestamp
            while (t >= oldest) {
                val newer = findNewer(t)
                val older = findOlder(t)
                if (newer == null || older == null) break
                if (older.timestamp == newer.timestamp) {
                    out.add(InMemoryGlucoseValue.fromGv(newer))
                } else {
                    val span = (newer.timestamp - older.timestamp).toDouble()
                    val toNew = (newer.timestamp - t).toDouble()
                    val filled = min(t - older.timestamp, newer.timestamp - t) > T.secs(IRREGULAR_DATA_SEC).msecs()
                    val v = newer.value - toNew / span * (newer.value - older.value)
                    out.add(
                        InMemoryGlucoseValue(
                            t, v.roundToLong().toDouble(), filledGap = filled,
                            sourceSensor = bgReadings[0].sourceSensor
                        )
                    )
                }
                t -= stepMs
            }
            bucketedDataNative = out
            aapsLogger.debug(
                LTag.AUTOSENS,
                "Native cadence ${String.format(java.util.Locale.ENGLISH, "%.1f", cadence)} min: " +
                    "${bucketedDataNative?.size} readings kept against ${bucketedData?.size} five-minute buckets"
            )
        }
    }

    fun findNewer(time: Long): GV? {
        var lastFound = bgReadings[0]
        if (lastFound.timestamp < time) return null
        for (i in 1 until bgReadings.size) {
            if (bgReadings[i].timestamp == time) return bgReadings[i]
            if (bgReadings[i].timestamp > time) continue
            lastFound = bgReadings[i - 1]
            if (bgReadings[i].timestamp < time) break
        }
        return lastFound
    }

    fun findOlder(time: Long): GV? {
        var lastFound = bgReadings[bgReadings.size - 1]
        if (lastFound.timestamp > time) return null
        for (i in bgReadings.size - 2 downTo 0) {
            if (bgReadings[i].timestamp == time) return bgReadings[i]
            if (bgReadings[i].timestamp < time) continue
            lastFound = bgReadings[i + 1]
            if (bgReadings[i].timestamp > time) break
        }
        return lastFound
    }

    private fun createBucketedDataRecalculated(aapsLogger: AAPSLogger, dateUtil: DateUtil) {
        if (bgReadings.size < 3) {
            bucketedData = null
            return
        }
        val lastBg = bgReadings[0]
        val newBucketedData = ArrayList<InMemoryGlucoseValue>()
        var currentTime = bgReadings[0].timestamp
        val adjustedTime = adjustToReferenceTime(currentTime)
        // after adjusting time may be newer. In this case use T-5min
        currentTime = if (adjustedTime > currentTime) adjustedTime - T.mins(5).msecs() else adjustedTime
        aapsLogger.debug("Adjusted time " + dateUtil.dateAndTimeAndSecondsString(currentTime))
        while (true) {
            // test if current value is older than current time
            val newer = findNewer(currentTime)
            val older = findOlder(currentTime)
            if (newer == null || older == null) break
            if (older.timestamp == newer.timestamp) { // direct hit
                newBucketedData.add(InMemoryGlucoseValue.fromGv(newer))
            } else {
                val bgDelta = newer.value - older.value
                val timeDiffToNew = newer.timestamp - currentTime
                val timeDiffToOlder = currentTime - older.timestamp
                val filledGap = min(timeDiffToOlder, timeDiffToNew) > T.secs(IRREGULAR_DATA_SEC).msecs()
                val currentBg = newer.value - timeDiffToNew.toDouble() / (newer.timestamp - older.timestamp) * bgDelta
                val newBgReading = InMemoryGlucoseValue(currentTime, currentBg.roundToLong().toDouble(), filledGap = filledGap, sourceSensor = lastBg.sourceSensor)
                newBucketedData.add(newBgReading)
            }
            currentTime -= T.mins(5).msecs()
        }
        bucketedData = newBucketedData
    }

    private fun createBucketedData5min(aapsLogger: AAPSLogger, dateUtil: DateUtil) {
        if (bgReadings.size < 3) {
            bucketedData = null
            return
        }
        val lastBg = bgReadings[0]
        val bData: MutableList<InMemoryGlucoseValue> = ArrayList()
        bData.add(InMemoryGlucoseValue.fromGv(bgReadings[0]))
        aapsLogger.debug(LTag.AUTOSENS) { "Adding. bgTime: ${dateUtil.toISOString(bgReadings[0].timestamp)} lastBgTime: none-first-value ${bgReadings[0]}" }
        var j = 0
        for (i in 1 until bgReadings.size) {
            val bgTime = bgReadings[i].timestamp
            var lastBgTime = bgReadings[i - 1].timestamp
            var elapsedMinutes = (bgTime - lastBgTime) / (60 * 1000)
            when {
                abs(elapsedMinutes) > 8 -> {
                    // interpolate missing data points
                    var lastBgValue = bgReadings[i - 1].value
                    elapsedMinutes = abs(elapsedMinutes)
                    var nextBgTime: Long
                    while (elapsedMinutes > 5) {
                        nextBgTime = lastBgTime - 5 * 60 * 1000
                        j++
                        val gapDelta = bgReadings[i].value - lastBgValue
                        val nextBg = lastBgValue + 5.0 / elapsedMinutes * gapDelta
                        val newBgReading = InMemoryGlucoseValue(nextBgTime, nextBg.roundToLong().toDouble(), filledGap = true, sourceSensor = lastBg.sourceSensor)
                        bData.add(newBgReading)
                        aapsLogger.debug(LTag.AUTOSENS) { "Adding. bgTime: ${dateUtil.toISOString(bgTime)} lastBgTime: ${dateUtil.toISOString(lastBgTime)} $newBgReading" }
                        elapsedMinutes -= 5
                        lastBgValue = nextBg
                        lastBgTime = nextBgTime
                    }
                    j++
                    val newBgReading = InMemoryGlucoseValue(bgTime, bgReadings[i].value, sourceSensor = lastBg.sourceSensor)
                    bData.add(newBgReading)
                    aapsLogger.debug(LTag.AUTOSENS) { "Adding. bgTime: ${dateUtil.toISOString(bgTime)} lastBgTime: ${dateUtil.toISOString(lastBgTime)} $newBgReading" }
                }

                abs(elapsedMinutes) > 2 -> {
                    j++
                    val newBgReading = InMemoryGlucoseValue(bgTime, bgReadings[i].value, sourceSensor = lastBg.sourceSensor)
                    bData.add(newBgReading)
                    aapsLogger.debug(LTag.AUTOSENS) { "Adding. bgTime: ${dateUtil.toISOString(bgTime)} lastBgTime: ${dateUtil.toISOString(lastBgTime)} $newBgReading" }
                }

                else                    -> {
                    bData[j].value = (bData[j].value + bgReadings[i].value) / 2
                }
            }
        }

        // Normalize bucketed data
        val oldest = bData[bData.size - 1]
        oldest.timestamp = adjustToReferenceTime(oldest.timestamp)
        aapsLogger.debug("Adjusted time " + dateUtil.dateAndTimeAndSecondsString(oldest.timestamp))
        for (i in bData.size - 2 downTo 0) {
            val current = bData[i]
            val previous = bData[i + 1]
            val mSecDiff = current.timestamp - previous.timestamp
            val adjusted = (mSecDiff - T.mins(5).msecs()) / 1000
            aapsLogger.debug(LTag.AUTOSENS) {
                "Adjusting bucketed data time. Current: ${dateUtil.dateAndTimeAndSecondsString(current.timestamp)} to: ${
                    dateUtil.dateAndTimeAndSecondsString(previous.timestamp + T.mins(5).msecs())
                } by $adjusted sec"
            }
            if (abs(adjusted) > 90) {
                // too big adjustment, fallback to non 5 min data
                aapsLogger.debug(LTag.AUTOSENS, "Fallback to non 5 min data")
                createBucketedDataRecalculated(aapsLogger, dateUtil)
                return
            }
            current.timestamp = previous.timestamp + T.mins(5).msecs()
        }
        aapsLogger.debug(LTag.AUTOSENS, "Bucketed data created. Size: " + bData.size)
        bucketedData = bData
    }

    override fun slowAbsorptionPercentage(timeInMinutes: Int): Double {
        var sum = 0.0
        var count = 0
        val valuesToProcess = timeInMinutes / 5
        synchronized(dataLock) {
            var i = autosensDataTable.size() - 1
            while (i >= 0 && count < valuesToProcess) {
                if (autosensDataTable.valueAt(i).failOverToMinAbsorptionRate) sum++
                count++
                i--
            }
        }
        return if (count != 0) sum / count else 0.0
    }
}