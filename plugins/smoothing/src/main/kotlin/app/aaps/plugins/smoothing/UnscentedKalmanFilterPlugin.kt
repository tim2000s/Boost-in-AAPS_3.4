package app.aaps.plugins.smoothing

import app.aaps.core.data.iob.InMemoryGlucoseValue
import app.aaps.core.data.model.TE
import app.aaps.core.data.model.TrendArrow
import app.aaps.core.data.plugin.PluginType
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.iob.IobCobCalculator
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import app.aaps.core.interfaces.plugin.PluginBaseWithPreferences
import app.aaps.core.interfaces.plugin.PluginDescription
import app.aaps.core.interfaces.resources.ResourceHelper
import app.aaps.core.interfaces.smoothing.Smoothing
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.plugins.smoothing.keys.UkfDoubleNonKey
import app.aaps.plugins.smoothing.keys.UkfIntNonKey
import app.aaps.plugins.smoothing.keys.UkfLongNonKey
import dagger.Lazy
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/**
 * Adaptive Unscented Kalman Filter with RTS smoothing.
 *
 * KEY FEATURES:
 * - FIXED Q (process noise) tuned for realistic meal/insulin responses.
 * - ADAPTIVE R (measurement noise) adapting to changing sensor quality.
 * - Learned R parameter persists across function calls and app restarts.
 * - Chi-squared based outlier detection (99.99% confidence).
 * - Automatically resets learning on actual sensor changes (via EventTherapyEventChange).
 * - Outlier threshold scales with current uncertainty (P + R).
 * - Event-based reset (not time-based guessing).
 *
 * State vector: x = [G, Ġ]^T
 *   - G: glucose concentration (mg/dL)
 *   - Ġ: rate of glucose change (mg/dL/min)
 *
 * Process model: x_{t+1} = f(x_t) + w_t
 *   - f(x_t) = [G + Ġ·Δt, Ġ·damping]^T
 *   - w_t ~ N(0, Q) where Q is fixed based on realistic physiology.
 *
 * Measurement model: z_t = h(x_t) + v_t
 *   - h(x_t) = G
 *   - v_t ~ N(0, R) where R is adaptive based on sensor quality.
 */
@Singleton
class UnscentedKalmanFilterPlugin @Inject constructor(
    aapsLogger: AAPSLogger,
    rh: ResourceHelper,
    preferences: Preferences,
    private val persistenceLayer: PersistenceLayer,
    private val iobCobCalculator: Lazy<IobCobCalculator>
) : PluginBaseWithPreferences(
    pluginDescription = PluginDescription()
        .mainType(PluginType.SMOOTHING)
        .pluginIcon(app.aaps.core.ui.R.drawable.ic_timeline_24)
        .pluginName(R.string.UKF_name)
        .shortName(R.string.smoothing_shortname)
        .description(R.string.description_UKF),
    ownPreferences = listOf(UkfLongNonKey::class.java, UkfIntNonKey::class.java, UkfDoubleNonKey::class.java),
    aapsLogger, rh, preferences
), Smoothing {

    // ============================================================
    // UKF CONFIGURATION
    // ============================================================

    // State dimension.
    private val n = 2

    // UKF parameters (Merwe's scaled formulation).
    private val alpha = 0.1
    private val beta = 2.0
    private val kappa = 0.0

    // Derived parameters.
    private val lambda = alpha * alpha * (n + kappa) - n
    private val gamma = sqrt(n + lambda)

    // Sigma point weights.
    private val wm = DoubleArray(2 * n + 1)
    private val wc = DoubleArray(2 * n + 1)

    // FIXED process noise covariances - tuned for realistic glucose dynamics.
    // These values must accommodate meal responses (rapid rises) and insulin action (rapid falls).
    // Increased significantly from original to handle real-world glucose variability.
    private val q = doubleArrayOf(
        1.0, 0.0,     // Glucose process noise
        0.0, 0.35     // Rate process noise
    )

    // Initial measurement noise (conservative starting point).
    private val rInit = 25.0  // ~5 mg/dL std dev - assumes moderate sensor quality.

    // Adaptive R bounds (variance, mg/dL^2).
    private val rMin = 16.0   // ~4 mg/dL std dev - excellent sensor.
    private val rMax = 225.0  // ~15 mg/dL std dev - poor sensor.
    private val rEffMax = 400.0

    // R adaptation window for innovation statistics, expressed in MINUTES so that it means the
    // same thing at any cadence. It was 18 readings, whose own comment read "≈90 minutes at
    // 5-min intervals" — true only there, and 18 minutes on a one-minute feed. The reading count
    // is derived per call from the observed spacing and kept as a buffer bound. (2026-08-01)
    private val innovationWindowMinutes = 90.0
    private val innovationWindowMinReadings = 6
    private val innovationWindowMaxReadings = 120
    private var innovationWindow = 18

    // Chi-squared based outlier detection (99.99% confidence, 1 DOF).
    private val chiSquaredThreshold = 15.13  // Statistically rigorous.
    private val outlierAbsolute = 65.0        // Absolute safety limit (mg/dL).

    // --- IOB-gated compression-low damping (grafted from the tsunami compression guard) ---
    // A glucose-only filter cannot tell a compression low (lying on the sensor) from a real fast
    // hypo; both are sustained fast drops. IOB is the discriminator: a genuine fast low needs
    // insulin behind it. When a LOW reading falls well below the filter's own prediction with
    // little IOB on board, we treat it as a probable compression artefact and DOWN-WEIGHT it
    // (heavy R, no zero-lag Q) instead of tracking it to the floor. It is soft and bounded:
    // a sustained real low is still followed within a cycle, the hold is capped so it can never
    // mask a persistent low, highs/rises are never touched, and it fails safe (disabled) when
    // IOB is unavailable.
    private val compressionBgCeiling = 75.0      // only ever act on readings below this
    private val compressionIobMaxU = 2.0         // ...and only when IOB is under this
    private val compressionDropMgdl = 30.0       // ...and only if fallen >this from the recent baseline
    private val compressionWindow = 5            // baseline depth in READINGS (retained as a cap)
    /**
     * 2026-07-30: the compression baseline is a TIME window, not a reading count.
     *
     * [compressionWindow] is a count, and its own comment said "~25 min" — true only at a 5-minute
     * cadence. On a 1-minute feed the same 5 readings span 5 minutes, so the "fallen more than
     * [compressionDropMgdl] from the recent baseline" test is asked against a 5-minute baseline that
     * glucose almost never satisfies. Measured on 83,550 readings / 66 days of real 1-min data with
     * the shipped thresholds: 10 fires against 636 for the same glucose with a 25-minute window, i.e.
     * the damper was ~98% suppressed for that user. It is a SAFETY feature — it stops the loop
     * chasing a sensor artefact down into a real low — and 1-min feeds are exactly where fast falls
     * are seen soonest, so the cadence that benefits most was the one it was switched off for.
     *
     * The reading count is kept as an upper bound so a very high cadence cannot grow the buffer
     * without limit; the TIME bound is what decides membership.
     */
    private val compressionWindowMinutes = 25.0
    private val compressionWindowMaxReadings = 30
    private val compressionR = 900.0             // effective measurement variance for a suspect
    // After this long of continuous suspicion, follow the sensor even if it still looks like a
    // compression low. Expressed in minutes; it was a count of 3 whose comment read "≤15 min",
    // which is 3 minutes on a one-minute feed. (2026-08-01)
    private val maxCompressionMinutes = 15.0
    private var maxConsecutiveCompression = 3

    // Covariance limits (tighter for faster recovery).
    private val maxGlucoseVariance = 400.0  // Max 20 mg/dL std dev.
    private val maxRateVariance = 4.0       // Max 2 mg/dL/min std dev.

    // Innovation-based validation - detect parameter corruption.
    private val innovationResetThreshold = 12.0   // Reset if avg innovation > 12.
    private val innovationValidationSamples = 15  // Need 15 samples before validating.

    // Gap handling.
    /**
     * Smallest spacing treated as a valid step. Below this the samples are duplicates or clock
     * noise rather than a faster feed.
     *
     * This was 2.0, which silently made the filter a no-op on a one-minute sensor: every
     * consecutive pair failed the segment test below, so no segment ever reached the two-sample
     * minimum and [findValidSegments] returned an empty list. It never showed because the filter
     * is fed the five-minute bucketed series, where the spacing is always 5.0. It bites the
     * moment it is fed a native one-minute series. (2026-08-01)
     */
    private val minSampleSpacingMinutes = 0.5
    private val minorGapThreshold = 7.0       // Minutes - bridge with prediction.
    private val majorGapThreshold = 60.0      // Minutes - segment data.
    private val rateDecayTimeConstant = 30.0 // Minutes - physiological decay.

    // Hoisted constant for millis → minutes conversion to avoid repeated literal expressions.
    private val millisPerMinute = 1000.0 * 60.0

    private fun rateDamp(dt: Double): Double = exp(-dt / rateDecayTimeConstant)

    // ============================================================
    // DATA STRUCTURES
    // ============================================================

    /**
     * Represents a continuous segment of glucose data without major gaps.
     *
     * @property startIdx index of the newest point in the segment (inclusive).
     * @property endIdx index of the oldest point in the segment (inclusive).
     */
    private data class DataSegment(
        val startIdx: Int,
        val endIdx: Int
    )

    /**
     * Internal data class for storing filter state during the forward pass.
     * Used by the RTS smoother to perform backward smoothing.
     *
     * @property x state estimate before update [glucose, rate].
     * @property p state covariance before update (2x2 in row-major).
     * @property xPred predicted state [glucose, rate].
     * @property pPred predicted covariance (2x2 in row-major).
     * @property dt time step used for this prediction (minutes).
     */
    private data class FilterState(
        val x: DoubleArray,
        val p: DoubleArray,
        val xPred: DoubleArray,
        val pPred: DoubleArray,
        val dt: Double
    ) {

        override fun equals(other: Any?): Boolean {
            if (this === other) return true
            if (other !is FilterState) return false
            if (!x.contentEquals(other.x)) return false
            if (!p.contentEquals(other.p)) return false
            if (!xPred.contentEquals(other.xPred)) return false
            if (!pPred.contentEquals(other.pPred)) return false
            return dt == other.dt
        }

        override fun hashCode(): Int {
            var result = x.contentHashCode()
            result = 31 * result + p.contentHashCode()
            result = 31 * result + xPred.contentHashCode()
            result = 31 * result + pPred.contentHashCode()
            result = 31 * result + dt.hashCode()
            return result
        }
    }

    // ============================================================
    // PERSISTENT STATE
    // ============================================================

    // Learned measurement noise (variance).
    private var learnedR = rInit

    // Innovation tracking.
    // - innovations: normalized innovation squared ν² / (P[0] + R).
    // - rawInnovationVariance: raw innovation squared ν².
    // - predVarHistory: history of predicted variance P_pred[0].
    private val innovations = ArrayDeque<Double>(innovationWindow + 1)
    private val rawInnovationVariance = ArrayDeque<Double>(innovationWindow + 1)
    private val predVarHistory = ArrayDeque<Double>(innovationWindow + 1)

    // Session tracking.
    private var lastProcessedTimestamp: Long = 0
    private var lastSensorChangeTimestamp: Long = 0
    private var sensorSessionId: Int = 0
    private var sessionMeasurementCount: Long = 0
    private var sessionOutlierCount: Long = 0

    // Consecutive outlier counter (currently used only for diagnostics).
    private var consecutiveOutliers = 0

    // Event system.
    private val resetRequested = AtomicBoolean(false)
    private var scope: CoroutineScope? = null

    // ============================================================
    // INITIALIZATION
    // ============================================================

    init {
        // Initialize sigma point weights.
        wm[0] = lambda / (n + lambda)
        wc[0] = lambda / (n + lambda) + (1 - alpha * alpha + beta)
        val w = 1.0 / (2.0 * (n + lambda))
        for (i in 1 until 2 * n + 1) {
            wm[i] = w
            wc[i] = w
        }

        // Load persisted parameters.
        loadPersistedParameters()
    }

    override fun onStart() {
        super.onStart()
        val newScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
        scope = newScope

        // Load initial sensor state. (Upstream subscribes reactively to therapy-event
        // changes; this 3.4 codebase has no PersistenceLayer.observeChanges, so ongoing
        // sensor-change detection is polled once per cycle from smooth() instead.)
        newScope.launch {
            loadLastSensorChange()
        }
    }

    // ============================================================
    // PARAMETER PERSISTENCE
    // ============================================================

    /**
     * Load learned R parameter and session metadata from SharedPreferences.
     *
     * Q is never loaded; it is always the fixed physiological value defined in this class.
     */
    private fun loadPersistedParameters() {
        try {
            val lastSaved = preferences.get(UkfLongNonKey.LastSavedTimestamp)
            val savedSensorChange = preferences.get(UkfLongNonKey.LastSensorChangeTimestamp)

            if (lastSaved > 0) {
                lastSensorChangeTimestamp = savedSensorChange
                lastProcessedTimestamp = preferences.get(UkfLongNonKey.LastProcessedTimestamp)
                learnedR = preferences.get(UkfDoubleNonKey.LearnedR)
                sensorSessionId = preferences.get(UkfIntNonKey.SessionId)

                // Validate loaded R.
                if (learnedR !in rMin..rMax) {
                    aapsLogger.info(
                        LTag.GLUCOSE,
                        "UKF: Loaded R ($learnedR) out of bounds, resetting to R_INIT"
                    )
                    learnedR = rInit
                }

                aapsLogger.info(
                    LTag.GLUCOSE,
                    "UKF: Loaded session $sensorSessionId " +
                        "(R=${String.format(Locale.US, "%.1f", learnedR)}, " +
                        "Q_glucose=${String.format(Locale.US, "%.2f", q[0])} [FIXED], " +
                        "Q_rate=${String.format(Locale.US, "%.4f", q[3])} [FIXED])"
                )
            }
        } catch (e: Exception) {
            aapsLogger.error(LTag.GLUCOSE, "UKF: Failed to load persisted parameters", e)
            // Reset to defaults on error.
            learnedR = rInit
        }
    }

    /**
     * Save learned R parameter and session metadata to SharedPreferences.
     *
     * Called whenever new data has been processed.
     * Q is never saved; it is always the fixed physiological value defined in this class.
     */
    private fun savePersistedParameters() {
        try {
            preferences.put(UkfLongNonKey.LastSavedTimestamp, System.currentTimeMillis())
            preferences.put(UkfLongNonKey.LastSensorChangeTimestamp, lastSensorChangeTimestamp)
            preferences.put(UkfLongNonKey.LastProcessedTimestamp, lastProcessedTimestamp)
            preferences.put(UkfDoubleNonKey.LearnedR, learnedR)
            preferences.put(UkfIntNonKey.SessionId, sensorSessionId)

            aapsLogger.debug(
                LTag.GLUCOSE,
                "UKF: Saved learned R for session $sensorSessionId"
            )
        } catch (e: Exception) {
            aapsLogger.error(LTag.GLUCOSE, "UKF: Failed to save persisted parameters", e)
        }
    }

    // ============================================================
    // SENSOR CHANGE DETECTION
    // ============================================================

    /**
     * Load the most recent sensor change timestamp from the database.
     *
     * Called on plugin initialization and after therapy event changes.
     * Queries the last 30 days of therapy events for SENSOR_CHANGE entries.
     */
    private suspend fun loadLastSensorChange() {
        try {
            val therapyEvents = persistenceLayer.getTherapyEventDataFromTime(
                System.currentTimeMillis() - 30L * 24 * 60 * 60 * 1000,
                TE.Type.SENSOR_CHANGE,
                false
            )
            val latestSensorChange = therapyEvents
                .filter { it.type == TE.Type.SENSOR_CHANGE }
                .maxByOrNull { it.timestamp }

            latestSensorChange?.let { sensorChange ->
                if (sensorChange.timestamp > lastSensorChangeTimestamp) {
                    aapsLogger.info(
                        LTag.GLUCOSE,
                        "UKF: Detected sensor change at ${sensorChange.timestamp}"
                    )
                    lastSensorChangeTimestamp = sensorChange.timestamp

                    // If the sensor changed after the last processed reading, schedule a reset.
                    if (lastProcessedTimestamp > 0 &&
                        sensorChange.timestamp > lastProcessedTimestamp
                    ) {
                        aapsLogger.info(
                            LTag.GLUCOSE,
                            "UKF: Sensor changed after last processing, " +
                                "scheduling learning reset"
                        )
                        resetRequested.set(true)
                    }
                }
            }
        } catch (throwable: Throwable) {
            aapsLogger.error(
                LTag.GLUCOSE,
                "UKF: Error loading sensor change history",
                throwable
            )
        }
    }

    /**
     * Check for new sensor change events since the last known sensor change.
     *
     * Called when TE changes are observed to limit the query to
     * events after [lastSensorChangeTimestamp].
     */
    private fun checkForSensorChange() {
        scope?.launch {
            try {
                val therapyEvents = persistenceLayer.getTherapyEventDataFromTime(lastSensorChangeTimestamp, TE.Type.SENSOR_CHANGE, false)
                val newSensorChanges = therapyEvents.filter {
                    it.type == TE.Type.SENSOR_CHANGE &&
                        it.timestamp > lastSensorChangeTimestamp
                }

                if (newSensorChanges.isNotEmpty()) {
                    val latestChange = newSensorChanges.maxByOrNull { it.timestamp }!!
                    aapsLogger.info(
                        LTag.GLUCOSE,
                        "UKF: New sensor change at ${latestChange.timestamp}"
                    )
                    lastSensorChangeTimestamp = latestChange.timestamp
                    resetRequested.set(true)
                }
            } catch (throwable: Throwable) {
                aapsLogger.error(
                    LTag.GLUCOSE,
                    "UKF: Error checking for sensor changes",
                    throwable
                )
            }
        }
    }

    /**
     * Cleanup when the plugin stops.
     *
     * Called automatically by the plugin framework.
     */
    override fun onStop() {
        scope?.cancel()
        scope = null
        super.onStop()
    }

    // ============================================================
    // RESET LOGIC
    // ============================================================

    /**
     * Determine if learning should be reset.
     *
     * Uses actual sensor change events plus innovation-based validation.
     *
     * Reset conditions:
     * 1. Reset explicitly requested by the sensor change event listener.
     * 2. First ever call (lastProcessedTimestamp == 0).
     * 3. Timestamp corruption (time went backwards).
     * 4. Very large gaps (> 24 h) as a safety fallback for missed events.
     * 5. Severely corrupted R (detected via innovation statistics).
     *
     * @param currentTimestamp timestamp of the most recent glucose reading.
     * @return true if learning parameters should be reset to initial values.
     */
    private fun shouldResetLearning(currentTimestamp: Long): Boolean {
        if (resetRequested.getAndSet(false)) {
            aapsLogger.info(LTag.GLUCOSE, "UKF: Learning reset requested by sensor change event")
            return true
        }

        if (lastProcessedTimestamp == 0L) {
            aapsLogger.info(LTag.GLUCOSE, "UKF: First call, initializing learning")
            return true
        }

        val timeDiffMinutes = (currentTimestamp - lastProcessedTimestamp) / millisPerMinute

        if (timeDiffMinutes < 0) {
            aapsLogger.info(LTag.GLUCOSE, "UKF: Timestamp went backwards, resetting learning")
            return true
        }

        if (timeDiffMinutes > 1440.0) {
            aapsLogger.info(
                LTag.GLUCOSE,
                "UKF: Very large gap (${timeDiffMinutes.toInt()} min), resetting"
            )
            return true
        }

        // Check for severely mis-tuned R based on innovation statistics.
        if (innovations.size >= innovationValidationSamples) {
            val avgInnovation = innovations.average()
            if (avgInnovation > innovationResetThreshold) {
                aapsLogger.info(
                    LTag.GLUCOSE,
                    "UKF: Severely mis-tuned parameters " +
                        "(avg innovation: ${String.format(Locale.US, "%.1f", avgInnovation)}), " +
                        "resetting (R was ${String.format(Locale.US, "%.1f", learnedR)})"
                )
                return true
            }
        }

        return false
    }

    /**
     * Reset learned R parameter and session statistics to initial values.
     *
     * Called when the sensor changes or significant data anomalies are detected.
     * Clears innovation history and increments session ID; Q remains fixed.
     */
    private fun resetLearning() {
        learnedR = rInit
        innovations.clear()
        rawInnovationVariance.clear()
        predVarHistory.clear()
        sensorSessionId++
        sessionMeasurementCount = 0
        sessionOutlierCount = 0
        consecutiveOutliers = 0

        aapsLogger.info(
            LTag.GLUCOSE,
            "UKF: Learning reset complete (session $sensorSessionId, " +
                "R=${String.format(Locale.US, "%.1f", learnedR)}, " +
                "Q_glucose=${String.format(Locale.US, "%.2f", q[0])} [FIXED], " +
                "Q_rate=${String.format(Locale.US, "%.4f", q[3])} [FIXED])"
        )

        // Save the reset state.
        savePersistedParameters()
    }

    // ============================================================
    // MAIN FILTERING API
    // ============================================================


    /**
     * Median spacing of the supplied series, in minutes, or null when it cannot be established.
     * Median rather than mean so that a single gap does not move it.
     */
    internal fun medianSpacingMinutes(data: List<InMemoryGlucoseValue>): Double? {
        if (data.size < 3) return null
        val gaps = ArrayList<Double>(data.size - 1)
        for (i in 0 until data.size - 1) {
            // data is newest-first
            val d = (data[i].timestamp - data[i + 1].timestamp) / millisPerMinute
            if (d > 0 && d <= majorGapThreshold) gaps.add(d)
        }
        if (gaps.size < 2) return null
        gaps.sort()
        val m = gaps.size / 2
        return if (gaps.size % 2 == 0) (gaps[m - 1] + gaps[m]) / 2.0 else gaps[m]
    }

    /**
     * Convert the two duration-defined windows into reading counts for the cadence in hand.
     *
     * Both were fixed counts tuned at five minutes. On a one-minute feed the R adaptation window
     * shrank from 90 minutes to 18, and the compression follow-through from 15 minutes to 3.
     * Neither failure is visible in the output, which is why they survived until the cadence work
     * of 2026-07. Falls back to the five-minute counts when the spacing cannot be determined.
     */
    /** Test accessors for the two cadence-derived window sizes. */
    internal fun innovationWindowForTest(): Int = innovationWindow
    internal fun maxCompressionForTest(): Int = maxConsecutiveCompression

    internal fun adaptWindowsToCadence(data: List<InMemoryGlucoseValue>) {
        val spacing = medianSpacingMinutes(data) ?: 5.0
        val safe = spacing.coerceAtLeast(minSampleSpacingMinutes)
        innovationWindow = Math.round(innovationWindowMinutes / safe).toInt()
            .coerceIn(innovationWindowMinReadings, innovationWindowMaxReadings)
        maxConsecutiveCompression = Math.round(maxCompressionMinutes / safe).toInt()
            .coerceAtLeast(1)
    }

    override fun smooth(data: MutableList<InMemoryGlucoseValue>): MutableList<InMemoryGlucoseValue> {
        if (data.isEmpty()) return data

        // Poll for a sensor change each cycle (replaces the upstream reactive TE subscription,
        // unavailable in this 3.4 codebase). Async; the reset is consumed on the next reading.
        checkForSensorChange()

        // Size the reading-count windows from the cadence actually present, so that a window
        // meaning "90 minutes" or "15 minutes" means that at any sampling rate. (2026-08-01)
        adaptWindowsToCadence(data)

        try {
            return smoothInternal(data)
        } catch (e: Exception) {
            aapsLogger.error(
                LTag.GLUCOSE,
                "UKF: Error during smoothing, falling back to raw values",
                e
            )
            copyRawToSmoothed(data)
            return data
        }
    }

    /**
     * Split data into segments at major gaps (>60 min).
     *
     * Each segment is filtered and smoothed independently to avoid spanning
     * long gaps or invalid regions.
     */
    private fun findDataSegments(data: List<InMemoryGlucoseValue>): List<DataSegment> {
        if (data.size < 2) return emptyList()

        val segments = mutableListOf<DataSegment>()
        var segmentStart = 0

        for (i in 0 until data.size - 1) {
            val timeDiff = (data[i].timestamp - data[i + 1].timestamp) / millisPerMinute

            // Segment at major gaps (>60 min), invalid spacing, or error code.
            if (timeDiff !in minSampleSpacingMinutes..majorGapThreshold || data[i].value == 38.0) {
                // Close current segment if it has enough points.
                if (i - segmentStart >= 2) {
                    segments.add(DataSegment(segmentStart, i))
                }
                // Next segment starts after the gap.
                segmentStart = i + 1
            }
        }

        // Add final segment.
        if (data.size - segmentStart >= 2) {
            segments.add(DataSegment(segmentStart, data.size - 1))
        }

        return segments
    }

    /**
     * Total IOB (units) for the compression-damping gate. FAILS SAFE: on any error returns a high
     * value so the gate is disabled and a genuine drop is never masked.
     */
    private fun currentIobTotalU(): Double =
        try {
            val calc = iobCobCalculator.get()
            // Bolus IOB plus only POSITIVE basal IOB. Negative temp-basal IOB — the loop zero-/low-
            // temping during a genuine descent — must NOT shrink the total, or the gate is most-armed
            // exactly when the loop is already fighting a real insulin-driven low, damping the very
            // drop it should follow. Positive basal IOB still counts (it can drive a low). (2026-07-16)
            calc.calculateIobFromBolus().iob +
                max(0.0, calc.calculateIobFromTempBasalsIncludingConvertedExtended().iob)
        } catch (e: Exception) {
            aapsLogger.debug(LTag.GLUCOSE, "UKF: IOB unavailable, compression gate disabled")
            99.0
        }

    private fun smoothInternal(data: MutableList<InMemoryGlucoseValue>): MutableList<InMemoryGlucoseValue> {
        if (shouldResetLearning(data[0].timestamp)) {
            resetLearning()
        }

        // Current IOB for the compression-damping gate (same value for the window, as the
        // tsunami guard did; correct for the newest reading that feeds dosing).
        val iobTotal = currentIobTotalU()

        val segments = findDataSegments(data)

        if (segments.isEmpty()) {
            copyRawToSmoothed(data)
            return data
        }

        aapsLogger.debug(LTag.GLUCOSE, "UKF: Processing ${segments.size} data segments")

        // Track new measurements across all segments.
        val previousTimestamp = lastProcessedTimestamp
        lastProcessedTimestamp = data[0].timestamp

        // Process each segment independently.
        for ((idx, segment) in segments.withIndex()) {
            val segmentSize = segment.endIdx - segment.startIdx + 1
            aapsLogger.debug(
                LTag.GLUCOSE,
                "UKF: Segment $idx: $segmentSize points " +
                    "(idx ${segment.startIdx} to ${segment.endIdx})"
            )

            processSegment(data, segment.startIdx, segment.endIdx, previousTimestamp, iobTotal)
        }

        // Fill any unprocessed points with calibration-corrected raw values.
        for (i in data.indices) {
            if (data[i].smoothed == 0.0) {  // Not yet processed.
                data[i].smoothed = max(data[i].value, 39.0)
                data[i].trendArrow = TrendArrow.NONE
            }
        }

        // Periodic logging.
        if (sessionMeasurementCount % 100 == 0L && sessionMeasurementCount > 0) {
            val sessionOutlierRate =
                sessionOutlierCount.toDouble() / sessionMeasurementCount
            val avgInnovation =
                if (innovations.isNotEmpty()) innovations.average() else 0.0
            aapsLogger.info(
                LTag.GLUCOSE,
                "UKF: Session $sensorSessionId, $sessionMeasurementCount measurements, " +
                    "R=${String.format(Locale.US, "%.1f", learnedR)} [ADAPTIVE], " +
                    "Q_glucose=${String.format(Locale.US, "%.2f", q[0])} [FIXED], " +
                    "Q_rate=${String.format(Locale.US, "%.4f", q[3])} [FIXED], " +
                    "AvgInnovation=${String.format(Locale.US, "%.2f", avgInnovation)}, " +
                    "OutlierRate=${String.format(Locale.US, "%.1f%%", sessionOutlierRate * 100)}"
            )
        }

        // Save if we processed new data.
        val newDataProcessed = data.any { it.timestamp > previousTimestamp }
        if (newDataProcessed && sessionMeasurementCount > 0) {
            val diagnostics = mapOf(
                "session_id" to sensorSessionId,
                "measurements" to sessionMeasurementCount,
                "outliers" to sessionOutlierCount,
                "outlier_rate" to (sessionOutlierCount.toDouble() / sessionMeasurementCount),
                "R_learned" to learnedR,
                "R_stdev_equiv" to sqrt(learnedR),
                "avg_innovation" to if (innovations.isNotEmpty()) innovations.average() else 0.0,
                "innovation_count" to innovations.size,
                "consecutive_outliers" to consecutiveOutliers,
                "segments_processed" to segments.size
            )
            aapsLogger.debug(LTag.GLUCOSE, "UKF_DIAGNOSTICS: $diagnostics")
        }

        if (newDataProcessed) {
            savePersistedParameters()
        }

        return data
    }

    /**
     * Process a single continuous segment of data.
     *
     * Runs a forward UKF pass and backward RTS smoother over the segment only.
     */
    private fun processSegment(
        data: MutableList<InMemoryGlucoseValue>,
        startIdx: Int,           // Newest point in segment.
        endIdx: Int,             // Oldest point in segment.
        previousTimestamp: Long, // For tracking new measurements.
        iobTotal: Double         // Current IOB, for the compression-damping gate.
    ) {
        val segmentSize = endIdx - startIdx + 1
        if (segmentSize < 2) {
            data[startIdx].smoothed = max(data[startIdx].value, 39.0)
            data[startIdx].trendArrow = TrendArrow.NONE
            return
        }

        // Initialize state from the oldest point in the segment.
        val initialGlucose = data[endIdx].value
        var initialRate = 0.0

        if (endIdx > 0) {
            val dt = (data[endIdx - 1].timestamp - data[endIdx].timestamp) / millisPerMinute
            // Was 3.0..7.0, which no one-minute sample pair can satisfy, leaving the rate
            // unseeded and the filter to converge from zero. Accept any spacing that is a real
            // step and not a gap. (2026-08-01)
            if (dt in minSampleSpacingMinutes..minorGapThreshold) {
                initialRate = (data[endIdx - 1].value - data[endIdx].value) / dt
                initialRate = initialRate.coerceIn(-4.0, 4.0)
            }
        }

        val x = doubleArrayOf(initialGlucose, initialRate)
        val p = doubleArrayOf(16.0, 0.0, 0.0, 1.0)
        var r = learnedR

        val forwardStates = ArrayDeque<FilterState>(segmentSize)
        val forwardResults = DoubleArray(segmentSize)
        forwardResults[segmentSize - 1] = x[0]

        var segmentNewMeasurements = 0
        var segmentOutliers = 0

        // Local 2-of-3 same-sign gate for trend persistence (>2σ).
        val recentSigns = ArrayDeque<Int>(3)

        // Consecutive compression-suspect readings (bounds the damping hold; see below).
        var consecutiveCompression = 0
        // Recent RAW values (newest first) — baseline for the compression drop test. Uses raw,
        // not the filter level, so the filter's own rate-tracking can't hide a gradual drop.
        val recentRaw = ArrayDeque<Double>(compressionWindowMaxReadings + 1)
        // Timestamps parallel to [recentRaw], so the baseline window is bounded in MINUTES rather
        // than in samples (see compressionWindowMinutes).
        val recentRawTs = ArrayDeque<Long>(compressionWindowMaxReadings + 1)

        // === FORWARD PASS (within segment only) ===
        for (i in (endIdx - 1) downTo startIdx) {
            val dt = (data[i].timestamp - data[i + 1].timestamp) / millisPerMinute

            // Handle minor gaps within the segment.
            if (dt > minorGapThreshold && dt <= majorGapThreshold) {
                x[1] *= rateDamp(dt)
                aapsLogger.debug(
                    LTag.GLUCOSE,
                    "UKF: Bridging ${String.format(Locale.US, "%.1f", dt)} min gap within segment"
                )
            }

            // Covariance sanity checks.
            p[0] = p[0].coerceIn(0.1, maxGlucoseVariance)
            p[3] = p[3].coerceIn(0.001, maxRateVariance)

            // Use the real dt here; all process noise comes from predict().
            val dtUsed = dt

            // One-step prediction with fixed Q (base prediction).
            val (xPredBase, pPredBase) = predict(x, p, q, dtUsed)

            // Sentinel check (xDrip error code 38.0) must use raw .value, not calibrated;
            // the Kalman measurement itself uses .value.
            val rawValue = data[i].value
            val z = data[i].value

            // Skip only error code values (e.g., 38 mg/dL).
            if (rawValue <= 38.0) {
                // For smoothing, still record the pre-update state and prediction.
                val stateBefore = FilterState(
                    x.copyOf(),
                    p.copyOf(),
                    xPredBase.copyOf(),
                    pPredBase.copyOf(),
                    dtUsed
                )

                x[0] = xPredBase[0]
                x[1] = xPredBase[1]
                p[0] = pPredBase[0]
                p[1] = pPredBase[1]
                p[2] = pPredBase[2]
                p[3] = pPredBase[3]

                val resultIdx = i - startIdx
                forwardResults[resultIdx] = x[0]
                forwardStates.addFirst(stateBefore)
                continue
            }

            // --- Innovation stats (pre-inflation, for gating only) ---
            val innovation = z - xPredBase[0]
            val innovationVarianceRaw = pPredBase[0] + r
            val stdRaw = sqrt(innovationVarianceRaw)
            val normRaw = innovation / stdRaw
            val isNewData = data[i].timestamp > previousTimestamp

            // Maintain 2-of-3 same-sign gate for trend persistence at >2σ.
            val sign = when {
                normRaw > 0.0 -> 1
                normRaw < 0.0 -> -1
                else          -> 0
            }

            if (recentSigns.size == 3) recentSigns.removeLast()
            recentSigns.addFirst(if (abs(normRaw) > 2.0) sign else 0)
            val sameSignCount = if (sign == 0) 0 else recentSigns.count { it == sign }
            val qInflateAllowed = sameSignCount >= 2

            val absn = abs(normRaw)

            // --- IOB-gated compression-low suspicion ---
            // A LOW reading that has fallen well below its own recent RAW baseline, with little IOB
            // to explain a real crash → probable sensor compression. Raw-baseline (not prediction)
            // so the filter's rate-tracking can't hide a gradual dip; capped at
            // maxConsecutiveCompression so a persistent low is never masked for more than ~15 min.
            val recentMaxRaw = if (recentRaw.isEmpty()) z else recentRaw.max()
            // Pattern match is separate from the consecutive cap so we can distinguish "pattern
            // resolved" from "cap reached". compressionSuspect (which drives damping) additionally
            // requires being under the cap.
            val compressionPattern = z < compressionBgCeiling &&
                iobTotal < compressionIobMaxU &&
                (recentMaxRaw - z) > compressionDropMgdl
            val compressionSuspect = compressionPattern &&
                consecutiveCompression < maxConsecutiveCompression
            if (compressionSuspect) {
                consecutiveCompression++
                aapsLogger.debug(
                    LTag.GLUCOSE,
                    "UKF: Compression-suspect low z=${z.toInt()} " +
                        "(fell ${(recentMaxRaw - z).toInt()} from ${recentMaxRaw.toInt()}, " +
                        "IOB=${String.format(Locale.US, "%.1f", iobTotal)}) — damping"
                )
            } else if (!compressionPattern) {
                // Reset ONLY when the compression pattern has genuinely resolved (BG back above the
                // ceiling, drop closed, or IOB risen) — NOT merely because the consecutive cap tripped.
                // Resetting on a cap-trip let an ongoing low re-arm for another 3-reading burst every
                // cycle, defeating the ~15-min bound. Latching the counter while the pattern persists
                // means a sustained low is followed (undamped) after the cap and not re-damped until it
                // truly recovers. (2026-07-16 review)
                consecutiveCompression = 0
            }
            // else: pattern still present but cap reached → keep the counter latched (no damp, no reset).
            recentRaw.addFirst(z)
            recentRawTs.addFirst(data[i].timestamp)
            // Drop anything older than the time window, then apply the sample cap as a backstop.
            while (recentRawTs.isNotEmpty() &&
                (data[i].timestamp - recentRawTs.last()) / millisPerMinute > compressionWindowMinutes
            ) {
                recentRawTs.removeLast(); recentRaw.removeLast()
            }
            while (recentRaw.size > compressionWindowMaxReadings) {
                recentRaw.removeLast(); recentRawTs.removeLast()
            }

            // --- Measurement noise inflation (R_eff) ---
            // Huber-like per-sample R inflation with soft caps; a compression suspect is
            // down-weighted heavily instead (soft, not a hard mask — a sustained low is still
            // followed within a cycle, and the consecutive cap releases it after ~15 min).
            val rScale = 1.0 + max(0.0, absn - 2.0) // Grows linearly beyond 2σ.
            val rEff = if (compressionSuspect) compressionR
            else min(r * rScale, min(r + 100.0, rEffMax)) // Gentle ceiling.

            // --- Process noise inflation (Q) for real trends ---
            // Temporary Q inflation: prioritize rate agility, keep glucose bounded. Suppressed for
            // a compression suspect so the filter does NOT turn agile and chase the artefact down.
            val zScore = absn.coerceAtLeast(1.0)
            val qScale = if (qInflateAllowed && !compressionSuspect) zScore.coerceIn(1.0, 3.0) else 1.0
            val tempQ = if (qScale > 1.0) {
                q.copyOf().apply {
                    this[0] = q[0] * min(qScale, 2.0) // Modest glucose variance.
                    this[3] = q[3] * qScale          // Agile slope.
                }
            } else {
                q
            }

            // Re-predict if Q inflated, then update with R_eff.
            val (xPredEff, pPredEff) =
                if (qScale > 1.0) predict(x, p, tempQ, dtUsed) else Pair(xPredBase, pPredBase)

            // Store prediction for RTS smoothing (uses the effective prediction).
            val stateBefore = FilterState(
                x.copyOf(),
                p.copyOf(),
                xPredEff.copyOf(),
                pPredEff.copyOf(),
                dtUsed
            )

            // Effective innovation variance used by the filter (PPredEff + R_eff).
            val innovationVarianceEff = pPredEff[0] + rEff
            val mahalSqEff = (innovation * innovation) / innovationVarianceEff

            // Track predicted variance history for adaptive-R.
            predVarHistory.addFirst(pPredEff[0])
            if (predVarHistory.size > innovationWindow) predVarHistory.removeLast()

            // UKF update with effective parameters.
            update(xPredEff, pPredEff, z, rEff, x, p)

            // Track innovations for adaptive-R and reset logic using effecgtive variance.
            trackInnovation(innovation, innovationVarianceEff)

            // Pause R learning during real trend and on very large residuals.
            val skipRUpdate = qInflateAllowed || absn > 3.0
            if (!skipRUpdate) {
                r = adaptMeasurementNoise(r, innovations, rawInnovationVariance)
            }

            // Diagnostics on outliers, using effective covariance.
            if (mahalSqEff > chiSquaredThreshold || abs(innovation) > outlierAbsolute) {
                aapsLogger.debug(
                    LTag.GLUCOSE,
                    "UKF: Outlier detected - χ²=${String.format(Locale.US, "%.2f", mahalSqEff)}, " +
                        "innovation=${String.format(Locale.US, "%.1f", innovation)}, " +
                        "P[0]=${String.format(Locale.US, "%.1f", p[0])}"
                )
            }

            if (isNewData) {
                segmentNewMeasurements++
                sessionMeasurementCount++
                if (mahalSqEff > chiSquaredThreshold || abs(innovation) > outlierAbsolute) {
                    segmentOutliers++
                    sessionOutlierCount++
                }
            }

            // Logging with effective parameters (just switch to xPredEff for consistency).
            // DEBUG, not WARN: this is per-sample filter state, and the whole retained history is
            // reprocessed on every new reading. At warning level three glucose readings produced
            // 1,221 lines and filled a 5 MB log fragment in under fifteen minutes, so an exported
            // log covered a quarter of an hour and could not answer a question about anything
            // earlier. Genuine warnings in this file (singular innovation covariance, a
            // non-positive-definite covariance) stay at warn precisely so they remain visible.
            aapsLogger.debug(
                LTag.GLUCOSE,
                "UKF: live R=${String.format(Locale.US, "%.1f", r)}, " +
                    "R_eff=${String.format(Locale.US, "%.1f", rEff)}, " +
                    "BG=${String.format(Locale.US, "%.0f", z)}, " +
                    "predBG=${String.format(Locale.US, "%.0f", xPredEff[0])}, " +
                    "innov=${String.format(Locale.US, "%.1f", innovation)}, " +
                    "|ν|/σ=${String.format(Locale.US, "%.1f", absn)}, " +
                    "qScale=${String.format(Locale.US, "%.1f", qScale)}, " +
                    "P[0]=${String.format(Locale.US, "%.1f", p[0])}, " +
                    "P[3]=${String.format(Locale.US, "%.4f", p[3])}"
            )

            val resultIdx = i - startIdx
            forwardResults[resultIdx] = x[0]
            forwardStates.addFirst(stateBefore)
        }

        // Update learned R from the segment.
        learnedR = r

        // Log segment processing.
        if (segmentNewMeasurements > 0) {
            val segmentOutlierRate =
                segmentOutliers.toDouble() / segmentNewMeasurements
            aapsLogger.debug(
                LTag.GLUCOSE,
                "UKF: Segment processed $segmentNewMeasurements new measurements, " +
                    "$segmentOutliers outliers " +
                    "(${String.format(Locale.US, "%.1f%%", segmentOutlierRate * 100)})"
            )
        }

        // === BACKWARD SMOOTHING (RTS) - within segment only ===
        val smoothedResults = forwardResults.copyOf()
        if (segmentSize >= 3 && forwardStates.isNotEmpty()) {
            val maxSmoothSteps = min(segmentSize - 1, forwardStates.size)
            val xSmooth = doubleArrayOf(forwardResults[0], x[1])

            for (i in 1..maxSmoothSteps) {
                val state = forwardStates[i - 1]
                val c = computeSmootherGain(state.p, state.pPred, state.dt)
                val dx0 = xSmooth[0] - state.xPred[0]
                val dx1 = xSmooth[1] - state.xPred[1]
                xSmooth[0] = forwardResults[i] + c[0] * dx0 + c[1] * dx1
                xSmooth[1] = state.x[1] + c[2] * dx0 + c[3] * dx1
                smoothedResults[i] = xSmooth[0]
            }
        }

        // Apply results to this segment.
        for (i in startIdx..endIdx) {
            val resultIdx = i - startIdx
            data[i].smoothed = max(smoothedResults[resultIdx], 39.0)
            data[i].trendArrow =
                if (i == startIdx) computeTrendArrow(x[1]) else TrendArrow.NONE
        }
    }

    // ============================================================
    // ADAPTIVE R ESTIMATION
    // ============================================================

    /**
     * Track innovation statistics for adaptive R estimation.
     *
     * Stores both normalized innovation squared and raw innovation squared in
     * fixed-size windows for robust variance estimation.
     */
    private fun trackInnovation(innovation: Double, innovationVariance: Double) {
        val normalizedSq = (innovation * innovation) / innovationVariance
        val rawSq = innovation * innovation

        innovations.addFirst(normalizedSq)
        rawInnovationVariance.addFirst(rawSq)

        if (innovations.size > innovationWindow) {
            innovations.removeLast()
        }

        if (rawInnovationVariance.size > innovationWindow) {
            rawInnovationVariance.removeLast()
        }
    }

    /**
     * Adaptive measurement noise estimation.
     *
     * Uses innovation-based adaptive estimation (IAE) with robust trimmed-median
     * statistics on both innovation variance and predicted variance:
     *
     * - Computes a robust estimate of Var(ν) from recent raw innovations.
     * - Computes a robust estimate of P_pred[0] from recent predicted variances.
     * - Derives a target R̂ = Var(ν) - P_pred[0], clamped to [R_MIN, R_MAX].
     * - Updates currentR toward R̂ using asymmetric gains (faster when R must
     *   increase than when it should decrease) and per-step multiplicative caps
     *   to avoid large jumps.
     *
     * Under ideal tuning, E[ν²] ≈ P_pred[0] + R ⇒ E[normalized_innovation²] ≈ 1.0.
     */
    private fun adaptMeasurementNoise(
        currentR: Double,
        innovations: ArrayDeque<Double>,  // Stores ν²/(P[0] + R).
        rawSq: ArrayDeque<Double>         // Stores ν².
    ): Double {
        if (innovations.size < 12 || predVarHistory.isEmpty()) return currentR

        fun trimmedMean(v: List<Double>, trim: Double = 0.20): Double {
            if (v.isEmpty()) return 0.0
            val s = v.sorted()
            val k = (s.size * trim).toInt().coerceAtMost((s.size - 1) / 2)
            val core = s.subList(k, s.size - k)
            return core.average()
        }

        val nSize = innovations.size
        val mRaw = trimmedMean(rawSq.take(nSize))        // Robust Var(ν).
        val pyyMed = trimmedMean(predVarHistory.take(nSize)) // Robust P_pred[0].

        // Robust, decoupled target.
        val rHatRaw = (mRaw - pyyMed).coerceAtLeast(rMin) // Ensure positivity.
        val rHat = rHatRaw.coerceIn(rMin, rMax)

        // Asymmetric gains and gentle EMA step.
        val goingUp = rHat > currentR
        val kup = 0.18
        val kdn = 0.12 //MP increased from 0.10
        val k = if (goingUp) kup else kdn
        val step = currentR + k * (rHat - currentR)

        // Per-sample multiplicative clamp to avoid jumps.
        val upCap = if (goingUp) 1.20 else 1.00
        val dnCap = if (goingUp) 1.00 else 0.90
        val clamped = step
            .coerceIn(currentR * dnCap, currentR * upCap)
            .coerceIn(rMin, rMax)

        // Final smoothing to prevent ping-pong while keeping agility.
        val eta = 0.25
        return (1.0 - eta) * currentR + eta * clamped
    }

    // ============================================================
    // TREND ARROW COMPUTATION
    // ============================================================

    /**
     * Compute trend arrow from glucose rate of change.
     *
     * @param rate glucose rate in mg/dL/min.
     * @return corresponding trend arrow.
     */
    private fun computeTrendArrow(rate: Double): TrendArrow {
        return when {
            rate > 2.0  -> TrendArrow.DOUBLE_UP
            rate > 1.0  -> TrendArrow.SINGLE_UP
            rate > 0.5  -> TrendArrow.FORTY_FIVE_UP
            rate < -2.0 -> TrendArrow.DOUBLE_DOWN
            rate < -1.0 -> TrendArrow.SINGLE_DOWN
            rate < -0.5 -> TrendArrow.FORTY_FIVE_DOWN
            else        -> TrendArrow.FLAT
        }
    }

    // ============================================================
    // UKF CORE FUNCTIONS
    // ============================================================

    /**
     * Compute Rauch–Tung–Striebel (RTS) smoother gain.
     *
     * The smoother gain C maps forward-filtered estimates to backward-smoothed estimates:
     * C = P · Fᵀ · P_pred⁻¹
     *
     * Where F is the state transition Jacobian:
     * F = [[1, dt], [0, damping]]
     *
     * @param p forward-filtered covariance (2x2).
     * @param pPred one-step-ahead predicted covariance (2x2).
     * @param dt time step (minutes).
     * @return smoother gain matrix C (2x2 in row-major).
     */
    private fun computeSmootherGain(
        p: DoubleArray,
        pPred: DoubleArray,
        dt: Double
    ): DoubleArray {
        // F = [[1, dt],
        //      [0, exp(-dt/τ)]].
        val damp = rateDamp(dt)

        // Compute P · Fᵀ.
        val pfT00 = p[0] + p[1] * dt
        val pfT01 = p[1] * damp
        val pfT10 = p[2] + p[3] * dt
        val pfT11 = p[3] * damp

        // Invert PPred (2x2).
        val det = pPred[0] * pPred[3] - pPred[1] * pPred[2]
        if (abs(det) < 1e-10) return doubleArrayOf(0.0, 0.0, 0.0, 0.0)

        val inv00 = pPred[3] / det
        val inv01 = -pPred[1] / det
        val inv10 = -pPred[2] / det
        val inv11 = pPred[0] / det

        // C = P · Fᵀ · PPred^{-1}.
        return doubleArrayOf(
            pfT00 * inv00 + pfT01 * inv10,
            pfT00 * inv01 + pfT01 * inv11,
            pfT10 * inv00 + pfT11 * inv10,
            pfT10 * inv01 + pfT11 * inv11
        )
    }

    /**
     * UKF prediction step.
     *
     * Propagates state and covariance through the process model using the unscented transform:
     * 1. Generate sigma points from current state.
     * 2. Propagate each sigma point through process model f(x) = [G + Ġ·dt, Ġ·damping].
     * 3. Compute predicted mean and covariance from transformed sigma points.
     * 4. Add fixed process noise Q (scaled linearly with time).
     *
     * @param x current state [glucose, rate].
     * @param p current covariance (2x2 in row-major).
     * @param q fixed process noise covariance (2x2 in row-major).
     * @param dt time step in minutes.
     * @return pair of (predicted state, predicted covariance).
     */
    private fun predict(
        x: DoubleArray,
        p: DoubleArray,
        q: DoubleArray,
        dt: Double
    ): Pair<DoubleArray, DoubleArray> {
        // 1) Sigma points from current state.
        val sigmaPoints = generateSigmaPoints(x, p)

        // 2) Propagate through process model with dt-based rate damping.
        val sigmaPointsPred = Array(2 * n + 1) { DoubleArray(n) }
        val damp = rateDamp(dt)
        for (i in 0 until (2 * n + 1)) {
            // Glucose: G_{t+1} = G_t + Ġ_t · dt.
            sigmaPointsPred[i][0] = sigmaPoints[i][0] + sigmaPoints[i][1] * dt
            // Rate: Ġ_{t+1} = Ġ_t · exp(-dt/τ).
            sigmaPointsPred[i][1] = sigmaPoints[i][1] * damp
        }

        // 3) Predicted mean.
        val xPred = DoubleArray(n)
        for (i in 0 until (2 * n + 1)) {
            xPred[0] += wm[i] * sigmaPointsPred[i][0]
            xPred[1] += wm[i] * sigmaPointsPred[i][1]
        }

        // 4) Predicted covariance.
        val pPred = DoubleArray(4)
        for (i in 0 until (2 * n + 1)) {
            val dx0 = sigmaPointsPred[i][0] - xPred[0]
            val dx1 = sigmaPointsPred[i][1] - xPred[1]
            pPred[0] += wc[i] * dx0 * dx0
            pPred[1] += wc[i] * dx0 * dx1
            pPred[2] += wc[i] * dx1 * dx0
            pPred[3] += wc[i] * dx1 * dx1
        }

        // 5) Add process noise scaled linearly with time (as in original).
        val qScale = dt / 5.0
        pPred[0] += q[0] * qScale
        pPred[3] += q[3] * qScale

        // 6) Ensure positive definiteness.
        pPred[0] = max(pPred[0], 0.1)
        pPred[3] = max(pPred[3], 0.001)

        return Pair(xPred, pPred)
    }

    /**
     * UKF update step.
     *
     * Updates state and covariance using a new measurement:
     * 1. Generate sigma points from predicted state.
     * 2. Transform sigma points through measurement model h(x) = G.
     * 3. Compute innovation (measurement - prediction).
     * 4. Compute Kalman gain.
     * 5. Update state and covariance.
     *
     * @param xPred predicted state [glucose, rate].
     * @param pPred predicted covariance (2x2 in row-major).
     * @param z measurement (glucose reading in mg/dL).
     * @param r adaptive measurement noise variance.
     * @param x output: updated state (modified in place).
     * @param p output: updated covariance (modified in place).
     */
    private fun update(
        xPred: DoubleArray,
        pPred: DoubleArray,
        z: Double,
        r: Double,
        x: DoubleArray,
        p: DoubleArray
    ) {
        // Generate sigma points from predicted state.
        val sigmaPoints = generateSigmaPoints(xPred, pPred)
        val zSigma = DoubleArray(2 * n + 1)

        // Transform sigma points through measurement model (h(x) = glucose).
        for (i in 0 until 2 * n + 1) {
            zSigma[i] = sigmaPoints[i][0]
        }

        // Compute predicted measurement: z̄ = Σ W_i^(m) · Z_i.
        var zPred = 0.0
        for (i in 0 until 2 * n + 1) {
            zPred += wm[i] * zSigma[i]
        }

        // Compute innovation covariance: Pzz = Σ W_i^(c) · (Z_i - z̄)² + R.
        var pzz = 0.0
        for (i in 0 until 2 * n + 1) {
            val dz = zSigma[i] - zPred
            pzz += wc[i] * dz * dz
        }
        pzz += r

        // Safety check to prevent division by zero or numerical instability.
        if (pzz < 1e-6) {
            aapsLogger.warn(
                LTag.GLUCOSE,
                "UKF: Innovation covariance too small (Pzz=$pzz), skipping update"
            )
            x[0] = xPred[0]
            x[1] = xPred[1]
            p[0] = pPred[0]
            p[1] = pPred[1]
            p[2] = pPred[2]
            p[3] = pPred[3]
            return
        }

        // Compute cross-covariance: Pxz = Σ W_i^(c) · (χ_i - x̄)(Z_i - z̄).
        val pxz = DoubleArray(n)
        for (i in 0 until 2 * n + 1) {
            val dx0 = sigmaPoints[i][0] - xPred[0]
            val dx1 = sigmaPoints[i][1] - xPred[1]
            val dz = zSigma[i] - zPred
            pxz[0] += wc[i] * dx0 * dz
            pxz[1] += wc[i] * dx1 * dz
        }

        // Compute Kalman gain: K = Pxz / Pzz.
        val k = DoubleArray(n)
        k[0] = pxz[0] / pzz
        k[1] = pxz[1] / pzz

        // Update state: x = x̄ + K · (z - z̄).
        val innovation = z - zPred
        x[0] = xPred[0] + k[0] * innovation
        x[1] = xPred[1] + k[1] * innovation

        // Clamp rate to physiological range.
        x[1] = x[1].coerceIn(-4.0, 4.0)

        // Update covariance: P = P̄ - K · Pzz · Kᵀ.
        p[0] = pPred[0] - k[0] * pzz * k[0]
        p[1] = pPred[1] - k[0] * pzz * k[1]
        p[2] = pPred[2] - k[1] * pzz * k[0]
        p[3] = pPred[3] - k[1] * pzz * k[1]

        // Ensure positive definiteness.
        p[0] = max(p[0], 0.1)
        p[3] = max(p[3], 0.001)
    }

    /**
     * Generate sigma points using Merwe's scaled formulation.
     *
     * Creates 2n+1 sigma points around mean x with spread determined by covariance P:
     * - χ₀ = x (center point).
     * - χᵢ = x + γ·sqrt(P)_i for i = 1..n.
     * - χᵢ = x - γ·sqrt(P)_{i-n} for i = n+1..2n.
     *
     * Where γ = sqrt(n + λ) and λ is the scaling parameter.
     *
     * @param x mean state [glucose, rate].
     * @param p covariance (2x2 in row-major).
     * @return array of 2n+1 sigma points.
     */
    private fun generateSigmaPoints(
        x: DoubleArray,
        p: DoubleArray
    ): Array<DoubleArray> {
        val sigmaPoints = Array(2 * n + 1) { DoubleArray(n) }
        val sqrtP = matrixSqrt2x2(p)

        // Center sigma point.
        sigmaPoints[0][0] = x[0]
        sigmaPoints[0][1] = x[1]

        // Positive and negative perturbations.
        for (i in 0 until n) {
            sigmaPoints[i + 1][0] = x[0] + gamma * sqrtP[i * 2 + 0]
            sigmaPoints[i + 1][1] = x[1] + gamma * sqrtP[i * 2 + 1]

            sigmaPoints[i + 1 + n][0] = x[0] - gamma * sqrtP[i * 2 + 0]
            sigmaPoints[i + 1 + n][1] = x[1] - gamma * sqrtP[i * 2 + 1]
        }

        return sigmaPoints
    }

    /**
     * Compute matrix square root using Cholesky decomposition for a 2x2 SPD matrix.
     *
     * For a 2x2 symmetric positive definite matrix P, computes L such that L·Lᵀ = P.
     * Uses analytical Cholesky factorization:
     *
     * L = [[l11, 0],
     *      [l21, l22]]
     *
     * Where:
     * - l11 = sqrt(a)
     * - l21 = b / l11
     * - l22 = sqrt(d - l21²)
     *
     * Includes validation for numerical stability and non-positive-definite matrices.
     *
     * @param p covariance matrix [a, b, c, d] in row-major order.
     * @return lower-triangular Cholesky factor L in column-major order.
     */
    private fun matrixSqrt2x2(p: DoubleArray): DoubleArray {
        val a = p[0]
        val b = (p[1] + p[2]) / 2.0 // Enforce symmetry.
        val d = p[3]

        val l11 = sqrt(max(a, 1e-9))
        val l21 = b / l11
        val discriminant = d - l21 * l21
        if (discriminant < -1e-9) {
            aapsLogger.warn(
                LTag.GLUCOSE,
                "UKF: Non-positive-definite covariance, using fallback"
            )
            return doubleArrayOf(
                sqrt(max(a, 0.1)),
                0.0,
                0.0,
                sqrt(max(d, 0.01))
            )
        }

        val l22 = sqrt(max(discriminant, 1e-9))

        // Return in column-major order for easy extraction.
        return doubleArrayOf(l11, l21, 0.0, l22)
    }

    // ============================================================
    // UTILITY FUNCTIONS
    // ============================================================

    /**
     * Copy raw glucose values to the smoothed field (fallback).
     *
     * Used when insufficient data is available for filtering (< 2 readings) or
     * when the filter fails; ensures smoothed field is always populated.
     */
    private fun copyRawToSmoothed(data: MutableList<InMemoryGlucoseValue>) {
        for (reading in data) {
            reading.smoothed = max(reading.value, 39.0)
            reading.trendArrow = TrendArrow.NONE
        }
    }
}