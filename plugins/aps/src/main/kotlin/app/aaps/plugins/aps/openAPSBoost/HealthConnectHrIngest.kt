package app.aaps.plugins.aps.openAPSBoost

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import app.aaps.core.data.model.HR
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import app.aaps.core.keys.BooleanKey
import app.aaps.core.keys.IntKey
import app.aaps.core.keys.LongNonKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.plugins.aps.getBoostDosing
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

/**
 * HealthConnectHrIngest — reads HeartRateRecord from Android Health Connect on a polling
 * cadence and persists into AAPS's HR table via PersistenceLayer.insertOrUpdateHeartRate.
 *
 * Designed to bridge the Garmin overnight gap: Garmin Connect on the phone keeps syncing
 * HR to Health Connect even when the watch's Connect IQ data field isn't actively
 * pulling glucose. This service taps that stream so Boost sleep detection sees continuous
 * HR throughout the night.
 *
 * Polling strategy:
 *   - Caller invokes [syncIfDue] every Boost cycle (~5 min)
 *   - Internal throttle skips runs within [pollIntervalMin] (default 5 min, settable
 *     via IntKey.ApsBoostHealthConnectPollMin) of the last successful sync
 *   - Each run requests records from [lastSyncedMs] onwards, dedupes against existing
 *     timestamps (PersistenceLayer's insertOrUpdate is idempotent on (timestamp,device)
 *     in practice — we set a stable timestamp + duration from the HC record)
 *
 * Failsafe behaviour:
 *   - If Health Connect SDK isn't available on this device, [isAvailable] is false and
 *     [syncIfDue] is a no-op
 *   - If the user has not granted READ_HEART_RATE, reads return empty silently — logged
 *     once per app start
 *   - Coroutine errors are caught, logged, and never propagate to the calling plugin cycle
 */
@Singleton
class HealthConnectHrIngest @Inject constructor(
    private val context: Context,
    private val persistenceLayer: PersistenceLayer,
    private val preferences: Preferences,
    private val aapsLogger: AAPSLogger
) {

    private val scope = CoroutineScope(Dispatchers.IO)

    @Volatile private var client: HealthConnectClient? = null
    private val inFlight = java.util.concurrent.atomic.AtomicBoolean(false)
    @Volatile private var lastSyncRunMs: Long = 0L
    @Volatile private var permissionWarned = false

    // 2026-06-14: lookback re-sweep window (covers a full night + margin) and an in-memory dedupe
    // set of already-ingested sample timestamps. Lets each poll re-read the window to catch Garmin's
    // backdated morning-batch writes without re-persisting samples. Empty on process restart (the
    // first post-restart poll re-reads the window once; insertOrUpdate is idempotent so it's safe).
    private val lookbackMs = 18 * 60 * 60_000L
    private val ingestedSampleMs = java.util.concurrent.ConcurrentHashMap.newKeySet<Long>()

    val isAvailable: Boolean
        get() = try {
            HealthConnectClient.getSdkStatus(context) == HealthConnectClient.SDK_AVAILABLE
        } catch (t: Throwable) {
            false   // getSdkStatus can throw on some OEM/HC states; never let it bubble into the loop
        }

    private fun getOrInitClient(): HealthConnectClient? {
        client?.let { return it }
        if (!isAvailable) return null
        return try {
            val c = HealthConnectClient.getOrCreate(context)
            client = c
            c
        } catch (t: Throwable) {
            aapsLogger.error(LTag.APS, "HealthConnectHrIngest: client init failed: ${t.message}")
            null
        }
    }

    /**
     * Invoke from the Boost plugin's invoke() each cycle. Cheap when not due; spawns an
     * async sync when due. Never throws.
     */
    fun syncIfDue() {
        // 2026-07-08: raw reads — Simple Mode must NOT mask HC-HR enable back to its `false` default
        // (that silently starves HR ingest — another overnight-HR-loss vector) nor reset the poll interval.
        if (!preferences.getBoostDosing(BooleanKey.ApsBoostHealthConnectHrEnabled)) return
        val intervalMs = preferences.getBoostDosing(IntKey.ApsBoostHealthConnectPollMin).coerceAtLeast(1) * 60_000L
        val now = System.currentTimeMillis()
        if (now - lastSyncRunMs < intervalMs) return
        if (!inFlight.compareAndSet(false, true)) return   // atomic guard — no check-then-act race
        val hc = getOrInitClient()
        if (hc == null) { inFlight.set(false); return }
        lastSyncRunMs = now
        scope.launch {
            try {
                syncOnce(hc, now)
            } catch (t: Throwable) {
                aapsLogger.error(LTag.APS, "HealthConnectHrIngest: sync failed: ${t.message}")
            } finally {
                inFlight.set(false)
            }
        }
    }

    /**
     * Re-sweep the last [lookbackMs] of HeartRateRecord samples each poll, persisting any not yet
     * ingested this session (deduped via [ingestedSampleMs]). Lookback (NOT forward-only) so Garmin's
     * backdated overnight morning-batch writes are caught rather than skipped.
     */
    private suspend fun syncOnce(hc: HealthConnectClient, nowMs: Long) {
        // Check permission once and remember the answer for this session
        val granted = try {
            val grantedPerms = hc.permissionController.getGrantedPermissions()
            HealthPermission.getReadPermission(HeartRateRecord::class) in grantedPerms
        } catch (t: Throwable) {
            aapsLogger.error(LTag.APS, "HealthConnectHrIngest: permission check failed: ${t.message}")
            false
        }
        if (!granted) {
            if (!permissionWarned) {
                aapsLogger.warn(LTag.APS, "HealthConnectHrIngest: READ_HEART_RATE not granted — open AAPS settings → Boost → HR sources → Health Connect to grant.")
                permissionWarned = true
            }
            return
        }

        // 2026-06-14 fix: re-sweep a LOOKBACK WINDOW each poll and dedupe in-memory, instead of
        // reading forward-only from a persisted high-water mark. Garmin writes overnight HR into
        // Health Connect as a BACKDATED MORNING BATCH; the old forward-only reader advanced its
        // marker to "now" on each empty overnight poll, so when the batch landed (timestamps in the
        // past) it fell before the marker and was permanently skipped — ~0 overnight HR despite HC
        // holding the data. A lookback re-sweep catches backdated inserts; ingestedSampleMs ensures
        // each sample is persisted once (insertOrUpdateHeartRate is idempotent regardless).
        val sinceMs = nowMs - lookbackMs

        val request = ReadRecordsRequest(
            recordType = HeartRateRecord::class,
            timeRangeFilter = TimeRangeFilter.between(
                Instant.ofEpochMilli(sinceMs),
                Instant.ofEpochMilli(nowMs)
            )
        )
        val resp = hc.readRecords(request)
        // Gap-filler dedup (2026-06-24): the Garmin Connect IQ side-channel writes realtime HR
        // whenever the watch is awake. HC must only BACKFILL the gaps it leaves (overnight, or when
        // the watch wasn't polling) — not duplicate the live feed. Load the HR already in the window
        // once, bucket existing readings to the minute, and skip any HC sample whose minute already
        // has a reading. One DB read per poll, then O(1) membership checks.
        val existingMinutes = HashSet<Long>()
        try {
            for (h in persistenceLayer.getHeartRatesFromTimeToTime(sinceMs, nowMs))
                existingMinutes.add(h.timestamp / 60_000L)
        } catch (t: Throwable) {
            aapsLogger.warn(LTag.APS, "HealthConnectHrIngest: could not load existing HR for dedup: ${t.message}")
        }
        var inserted = 0; var skippedCovered = 0
        // HeartRateRecord groups multiple samples per record (a "session" of HR ticks).
        for (record in resp.records) {
            val device = record.metadata.device?.let { d ->
                listOfNotNull(d.manufacturer, d.model).joinToString(" ").trim().ifEmpty { "HealthConnect" }
            } ?: "HealthConnect"
            for (sample in record.samples) {
                val sampleMs = sample.time.toEpochMilli()
                if (sampleMs < sinceMs) continue
                if (!ingestedSampleMs.add(sampleMs)) continue   // already persisted this session
                if (sampleMs / 60_000L in existingMinutes) { skippedCovered++; continue }  // live feed already covered this minute
                val hr = HR(
                    timestamp = sampleMs,
                    duration = 60_000L,                       // HC samples are point-in-time; treat as 1-min weight
                    beatsPerMinute = sample.beatsPerMinute.toDouble(),
                    device = device,
                    isValid = true
                )
                // Fire-and-forget one-shot insert; not retained (was leaking into a never-cleared
                // CompositeDisposable). insertOrUpdate is idempotent and self-disposes on completion.
                persistenceLayer.insertOrUpdateHeartRate(hr).subscribe(
                    { inserted++ },
                    { e -> aapsLogger.warn(LTag.APS, "HealthConnectHrIngest: persist failed: ${e.message}") }
                )
            }
        }
        ingestedSampleMs.removeIf { it < sinceMs }   // prune dedupe set to the lookback window
        preferences.put(LongNonKey.ApsBoostHealthConnectLastSyncMs, nowMs)   // diagnostics only
        aapsLogger.info(LTag.APS, "HealthConnectHrIngest: window [${sinceMs}..${nowMs}] records=${resp.records.size} backfilled=$inserted skipped-live=$skippedCovered set=${ingestedSampleMs.size}")
    }

    /** Force a sync regardless of throttle — e.g. from a settings "test now" button. Returns immediately; result via logs. */
    fun forceSync() {
        lastSyncRunMs = 0L
        syncIfDue()
    }

    /** Synchronous one-shot check primarily for diagnostics. */
    fun isPermissionGranted(): Boolean = try {
        val hc = getOrInitClient() ?: return false
        runBlocking {
            val grantedPerms = hc.permissionController.getGrantedPermissions()
            HealthPermission.getReadPermission(HeartRateRecord::class) in grantedPerms
        }
    } catch (t: Throwable) { false }
}
