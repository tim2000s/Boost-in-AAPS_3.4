package app.aaps.plugins.aps.openAPSBoost

import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.util.Log

/**
 * Step counting service for Boost activity detection.
 *
 * Tracks steps in 5-minute buckets and provides aggregated counts
 * for 5, 10, 15, 30, and 60 minute windows. Used by OpenAPSBoostPlugin
 * to detect activity/inactivity and adjust profile percentage and targets.
 *
 * Must be registered as a SensorEventListener for Sensor.TYPE_STEP_COUNTER
 * in the application's main activity or service.
 */
object StepService : SensorEventListener {

    private const val TAG = "StepService"
    // Sensor callbacks (onSensorChanged) run on the app main thread while the APS loop reads steps
    // on an IO thread; all stepsMap access is @Synchronized on this object's monitor (same monitor
    // getStepsToday/seedTodayFromHc already use) to avoid ConcurrentModificationException / races.
    @Volatile private var previousStepCount = -1
    private val stepsMap = LinkedHashMap<Long, Int>()
    private const val FIVE_MINUTES_IN_MS = 300000
    private const val NUM_OF_5MIN_BLOCKS_TO_KEEP = 20

    // ── Feed-state visibility (F1, 2026-07-07) ──
    // TYPE_STEP_COUNTER never reports until the sensor delivers its first event after boot /
    // listener registration; until then every window reads 0 — indistinguishable from a genuinely
    // sedentary user. feedState() lets consumers (calculateBoostActivity's INACTIVE branch and the
    // sleep-in backstop) tell "no data" from "no steps" instead of dosing on a silent feed.
    /** Wall-clock ms of the last onSensorChanged callback (0 = none this process). */
    @Volatile var lastEventMs: Long = 0L
        private set

    enum class FeedState {
        /** The step sensor has never reported this boot (previousStepCount == -1): counts are unknowable, not zero. */
        NONE,
        /** The sensor has reported at least once this process — zero counts mean genuinely no steps. */
        LIVE
    }

    fun feedState(): FeedState = if (previousStepCount < 0) FeedState.NONE else FeedState.LIVE

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
        Log.i(TAG, "onAccuracyChanged: Sensor: $sensor; accuracy: $accuracy")
    }

    private fun currentTimeIn5Min(): Long {
        return System.currentTimeMillis() / FIVE_MINUTES_IN_MS
    }

    @Synchronized override fun onSensorChanged(sensorEvent: SensorEvent?) {
        sensorEvent ?: return
        lastEventMs = System.currentTimeMillis()

        val now = currentTimeIn5Min()
        val stepCount = sensorEvent.values[0].toInt()
        if (previousStepCount >= 0) {
            var recentStepCount = stepCount - previousStepCount
            if (stepsMap.contains(now)) {
                recentStepCount += stepsMap.getValue(now)
            }
            stepsMap[now] = recentStepCount
        }
        previousStepCount = stepCount

        if (stepsMap.size > NUM_OF_5MIN_BLOCKS_TO_KEEP) {
            val removeBefore = now - NUM_OF_5MIN_BLOCKS_TO_KEEP
            stepsMap.entries.removeIf { it.key < removeBefore }
        }
    }

    @Synchronized fun getRecentStepCount5Min(): Int {
        val now = currentTimeIn5Min() - 1
        return if (stepsMap.contains(now)) stepsMap.getValue(now) else 0
    }

    fun getRecentStepCount10Min(): Int = getStepsInLastXMin(3)

    fun getRecentStepCount15Min(): Int = getStepsInLastXMin(4)

    fun getRecentStepCount30Min(): Int {
        return getStepsInLastXMin(6)
    }

    fun getRecentStepCount60Min(): Int {
        return getStepsInLastXMin(12)
    }

    @Synchronized private fun getStepsInLastXMin(numberOf5MinIncrements: Int): Int {
        var stepCount = 0
        val now = currentTimeIn5Min()
        val cutoff = now - numberOf5MinIncrements
        for (entry in stepsMap.entries) {
            if (entry.key > cutoff && entry.key < now) {
                stepCount += entry.value
            }
        }
        return stepCount
    }

    // ── Cumulative steps-since-local-midnight (2026-06-19; reset-resilient 2026-06-24) ──
    // The phone is the authoritative step source (Garmin→HC is unreliable). The hardware
    // TYPE_STEP_COUNTER (previousStepCount) is cumulative-since-boot. Rather than a midnight-baseline
    // subtraction (which loses the whole day if the counter ever resets below the baseline), we
    // ACCUMULATE per-call deltas into todaySteps. A reset/reboot (cur < lastRaw) adds `cur` (the
    // post-reset steps) instead of zeroing. Survives reboots and sensor glitches; ~free per call.
    @Volatile private var dayKey = -1L
    @Volatile private var lastRaw = -1        // previous cumulative-since-boot reading
    @Volatile private var todaySteps = 0      // accumulated steps since local midnight

    private fun localDay(localOffsetMs: Long) = (System.currentTimeMillis() + localOffsetMs) / 86_400_000L

    /** Steps since local midnight from the phone pedometer. Accumulates; resilient to counter resets. */
    @Synchronized fun getStepsToday(localOffsetMs: Long): Int {
        val cur = previousStepCount
        val day = localDay(localOffsetMs)
        if (day != dayKey) {                  // local-day rollover → start the new day clean
            dayKey = day; todaySteps = 0; lastRaw = cur
            return 0
        }
        if (cur < 0) return todaySteps        // no sensor reading yet this boot
        if (lastRaw < 0) { lastRaw = cur; return todaySteps }
        todaySteps += stepDelta(cur, lastRaw)
        lastRaw = cur
        return todaySteps
    }

    /** Step increment between two cumulative-since-boot readings, resilient to a counter reset:
     *  forward → the delta; reset/reboot (cur < lastRaw) → `cur` (steps counted since the reset). */
    internal fun stepDelta(cur: Int, lastRaw: Int): Int = if (cur >= lastRaw) cur - lastRaw else cur

    /**
     * Reconcile with Health Connect's today total: only ever hold the HIGHER of the phone-accumulated
     * count and HC, never anchor downward. Lets a mid-day app start pick up earlier steps from HC,
     * and a post-restart phone count recover, without HC's lag ever pulling the live count backwards.
     */
    @Synchronized fun seedTodayFromHc(hcTodaySteps: Int, localOffsetMs: Long) {
        val day = localDay(localOffsetMs)
        if (day != dayKey) { dayKey = day; lastRaw = previousStepCount }
        if (hcTodaySteps > todaySteps) todaySteps = hcTodaySteps
        if (lastRaw < 0) lastRaw = previousStepCount
    }
}
