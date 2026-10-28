package app.aaps.workflow

import android.content.Context
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import app.aaps.core.data.time.T
import app.aaps.core.interfaces.aps.Loop
import app.aaps.core.interfaces.iob.IobCobCalculator
import app.aaps.core.interfaces.rx.events.Event
import app.aaps.core.interfaces.rx.events.EventNewBG
import app.aaps.core.keys.BooleanKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.core.objects.workflow.LoggingWorker
import app.aaps.core.utils.receivers.DataWorkerStorage
import kotlinx.coroutines.Dispatchers
import javax.inject.Inject

class InvokeLoopWorker(
    context: Context,
    params: WorkerParameters
) : LoggingWorker(context, params, Dispatchers.Default) {

    @Inject lateinit var dataWorkerStorage: DataWorkerStorage
    @Inject lateinit var iobCobCalculator: IobCobCalculator
    @Inject lateinit var loop: Loop
    @Inject lateinit var preferences: Preferences

    class InvokeLoopData(
        val cause: Event?
    )

    /*
     This method is triggered once autosens calculation has completed, so the LoopPlugin
     has current data to work with. However, autosens calculation can be triggered by multiple
     sources and currently only a new BG should trigger a loop run. Hence we return early if
     the event causing the calculation is not EventNewBG.
     <p>
    */
    override suspend fun doWorkAndLog(): Result {

        val data = dataWorkerStorage.pickupObject(inputData.getLong(DataWorkerStorage.STORE_KEY, -1)) as InvokeLoopData?
            ?: return Result.failure(workDataOf("Error" to "missing input data"))

        if (data.cause !is EventNewBG) return Result.success(workDataOf("Result" to "no calculation needed"))
        val nativeCadence = preferences.get(BooleanKey.ApsLoopAtNativeCadence)
        val glucoseValue = (
            if (nativeCadence) iobCobCalculator.ads.actualBgNative()
            else iobCobCalculator.ads.actualBg()
            ) ?: return Result.success(workDataOf("Result" to "bg outdated"))
        if (!shouldTrigger(glucoseValue.timestamp, loop.lastBgTriggeredRun, nativeCadence))
            return Result.success(workDataOf("Result" to "already looped with that value"))
        loop.lastBgTriggeredRun = glucoseValue.timestamp
        loop.invoke("Calculation for $glucoseValue", true)
        return Result.success()
    }

    companion object {

        /**
         * Shortest advance in glucose time that starts another five-minute cycle. A sensor does not
         * deliver on exact multiples of five minutes, so requiring a full five would reject a
         * reading arriving a second early and push that cycle out to ten. Half a step of tolerance
         * is the same allowance the bucketing uses when it decides which grid point a reading
         * belongs to.
         */
        val MIN_FIVE_MINUTE_ADVANCE: Long = T.mins(4).plus(T.secs(30)).msecs()

        /**
         * Whether a new glucose value should start a loop run.
         *
         * Two conditions, and the second is the one worth explaining. The value has to be newer
         * than the one already acted on, which is the long-standing guard against running twice on
         * one reading. Beyond that, a loop that is not following the sensor has to hold the
         * five-minute interval itself.
         *
         * It cannot delegate that to the bucketing. The bucketed series is built on a grid anchored
         * to a reference time that upstream deliberately re-establishes from the newest reading
         * whenever the store is rebuilt, so the grid follows the sensor rather than standing still.
         * On a five-minute feed that is invisible and harmless. On a faster one it means the
         * bucketed timestamp advances once per reading, and a trigger relying on the grid to space
         * out the cycles gets no spacing at all. Holding the interval here makes the decision rate a
         * property of this decision rather than a side effect of how glucose happens to be stored.
         *
         * @param glucoseTimestamp   timestamp of the value being offered
         * @param lastTriggeredRun   timestamp of the value the loop last ran on, 0 if never
         * @param nativeCadence      true to run once per reading, false to hold five minutes
         */
        fun shouldTrigger(glucoseTimestamp: Long, lastTriggeredRun: Long, nativeCadence: Boolean): Boolean {
            if (glucoseTimestamp <= lastTriggeredRun) return false
            if (nativeCadence || lastTriggeredRun == 0L) return true
            return glucoseTimestamp - lastTriggeredRun >= MIN_FIVE_MINUTE_ADVANCE
        }
    }
}