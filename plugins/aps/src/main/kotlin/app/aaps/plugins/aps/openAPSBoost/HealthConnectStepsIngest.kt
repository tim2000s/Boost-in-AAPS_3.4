package app.aaps.plugins.aps.openAPSBoost

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.metadata.Device
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import app.aaps.core.keys.BooleanKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.plugins.aps.getBoostDosing
import app.aaps.plugins.aps.openAPSBoost.DailyStepHistoryTracker.DailyTotal
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId
import javax.inject.Inject
import javax.inject.Singleton

/**
 * HealthConnectStepsIngest — Boost activity-load SHADOW (2026-06-16). Mirrors [HealthConnectHrIngest].
 *
 * Reads StepsRecord from Health Connect, filters to a **single source** (the dominant `dataOrigin`
 * over the window — HC aggregates steps from every app that writes them and double-counts; for a
 * deviation-from-baseline metric, single-source CONSISTENCY beats blended accuracy), buckets into
 * per-LOCAL-day totals, and exposes them for the plugin to fold into [DailyStepHistoryTracker].
 *
 * Reads a full [DailyStepHistoryTracker.WINDOW_DAYS] window each poll, so the baseline is
 * **backfilled from HC history immediately** (no cold start). Hourly throttle (daily totals don't
 * need 5-min cadence). SHADOW — produces data only; nothing here touches dosing.
 */
@Singleton
class HealthConnectStepsIngest @Inject constructor(
    private val context: Context,
    private val preferences: Preferences,
    private val aapsLogger: AAPSLogger
) {
    private val scope = CoroutineScope(Dispatchers.IO)
    @Volatile private var client: HealthConnectClient? = null
    private val inFlight = java.util.concurrent.atomic.AtomicBoolean(false)
    @Volatile private var lastSyncRunMs = 0L
    @Volatile private var permissionWarned = false

    private val windowMs = DailyStepHistoryTracker.WINDOW_DAYS * 24L * 60L * 60_000L
    private val pollIntervalMs = 60 * 60_000L   // hourly is ample for daily totals

    /** Single-source per-completed-day totals from the most recent sync (empty until first sync). */
    @Volatile var latestDailyTotals: List<DailyTotal> = emptyList()
        private set
    /** EVERY dataOrigin's per-day totals (raw package-name keys), for the multi-source step abstraction
     *  — so Garmin AND Google Fit etc. are all retained and one source dying can't starve the baseline. */
    @Volatile var allSourceDailyTotals: Map<String, List<DailyTotal>> = emptyMap()
        private set
    /** Each dataOrigin's step total for the CURRENT (partial) local day. */
    @Volatile var todayStepsBySource: Map<String, Int> = emptyMap()
        private set
    /** Per-completed-day totals from records the device auto-recorded as a PHONE (device.type ==
     *  TYPE_PHONE), regardless of which app wrote them. This is the phone pedometer's OWN history —
     *  used to backfill the phone anchor of the phone-anchored baseline so it is full-window
     *  immediately instead of accruing one day per midnight. Empty if the phone doesn't write
     *  sensor steps to HC (then the forward StepService ledger is the only phone history). */
    @Volatile var phoneDailyTotals: List<DailyTotal> = emptyList()
        private set
    @Volatile var chosenSource: String? = null
        private set
    /** Per-source coverage seen in the last window, "shortname:daysWithSteps/totalSteps", for NS visibility. */
    @Volatile var availableSources: List<String> = emptyList()
        private set
    /** Chosen source's step total for the CURRENT (partial) local day — used to anchor the phone
     *  pedometer's intraday counter. -1 until the first sync produces a value. */
    @Volatile var todayStepsSoFar: Int = -1
        private set
    /** Local day-index that [todayStepsSoFar] was computed for. Lets callers ignore a value that's
     *  gone stale across local midnight (HC re-syncs only hourly), avoiding yesterday bleeding in. */
    @Volatile var todayStepsDay: Long = -1L
        private set

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
            HealthConnectClient.getOrCreate(context).also { client = it }
        } catch (t: Throwable) {
            aapsLogger.error(LTag.APS, "HealthConnectStepsIngest: client init failed: ${t.message}")
            null
        }
    }

    /** Call each Boost cycle. Cheap when not due; spawns an async sync when due. Never throws. */
    fun syncIfDue() {
        if (!preferences.getBoostDosing(BooleanKey.ApsBoostActivityShadowEnabled)) return   // 2026-07-08: raw read (Simple-Mode mask bypass — don't starve step ingest)
        val now = System.currentTimeMillis()
        if (now - lastSyncRunMs < pollIntervalMs) return
        if (!inFlight.compareAndSet(false, true)) return   // atomic guard — no check-then-act race
        val hc = getOrInitClient()
        if (hc == null) { inFlight.set(false); return }
        lastSyncRunMs = now
        scope.launch {
            try {
                syncOnce(hc, now)
            } catch (t: Throwable) {
                aapsLogger.error(LTag.APS, "HealthConnectStepsIngest: sync failed: ${t.message}")
            } finally {
                inFlight.set(false)
            }
        }
    }

    private suspend fun syncOnce(hc: HealthConnectClient, nowMs: Long) {
        val granted = try {
            HealthPermission.getReadPermission(StepsRecord::class) in hc.permissionController.getGrantedPermissions()
        } catch (t: Throwable) {
            aapsLogger.error(LTag.APS, "HealthConnectStepsIngest: permission check failed: ${t.message}")
            false
        }
        if (!granted) {
            if (!permissionWarned) {
                aapsLogger.warn(LTag.APS, "HealthConnectStepsIngest: READ_STEPS not granted — grant Health Connect step access (Boost → HC) for the activity shadow.")
                permissionWarned = true
            }
            return
        }
        val sinceMs = nowMs - windowMs
        val offsetMs = ZoneId.systemDefault().rules.getOffset(Instant.now()).totalSeconds * 1000L
        // Paginate — a single readRecords() returns only the first page (~1000 records, oldest
        // first), which would truncate a full 28-day history from a continuous source. Loop on
        // pageToken so we see every source's complete coverage.
        val perSourceDay = HashMap<String, HashMap<Long, Long>>()
        val phoneDay = HashMap<Long, Long>()   // device.type == PHONE — the phone pedometer's own history
        var pageToken: String? = null
        do {
            val resp = hc.readRecords(
                ReadRecordsRequest(
                    recordType = StepsRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(Instant.ofEpochMilli(sinceMs), Instant.ofEpochMilli(nowMs)),
                    pageToken = pageToken
                )
            )
            for (r in resp.records) {
                val src = r.metadata.dataOrigin.packageName.ifBlank { "unknown" }
                val day = DailyStepHistoryTracker.dayIndex(r.startTime.toEpochMilli(), offsetMs)
                perSourceDay.getOrPut(src) { HashMap() }.merge(day, r.count) { a, b -> a + b }
                if (r.metadata.device?.type == Device.TYPE_PHONE)
                    phoneDay.merge(day, r.count) { a, b -> a + b }
            }
            pageToken = resp.pageToken
        } while (pageToken != null)
        // Phone-sensor history for the anchor (completed days are filtered downstream by the merge).
        phoneDailyTotals = phoneDay.map { (day, steps) -> DailyTotal(day, steps.toInt(), StepSourceResolver.PHONE) }
            .sortedBy { it.dayIndex }

        // Diagnostics: every source's coverage (days-with-steps / total), best-covered first.
        availableSources = perSourceDay.entries
            .sortedByDescending { e -> e.value.count { it.value > 0 } }
            .map { e -> "${e.key.substringAfterLast('.')}:${e.value.count { it.value > 0 }}/${e.value.values.sum()}" }

        // Expose EVERY source (not just the dominant one) for the multi-source step abstraction.
        val todayIdx = DailyStepHistoryTracker.dayIndex(nowMs, offsetMs)
        allSourceDailyTotals = perSourceDay.mapValues { (src, days) ->
            days.map { (day, steps) -> DailyTotal(day, steps.toInt(), src) }.sortedBy { it.dayIndex }
        }
        todayStepsBySource = perSourceDay.mapValues { (_, days) -> days[todayIdx]?.toInt() ?: 0 }

        val chosen = chooseSourceByCoverage(perSourceDay)
        if (chosen == null) {
            latestDailyTotals = emptyList()
            chosenSource = null
            aapsLogger.info(LTag.APS, "HealthConnectStepsIngest: no step records in window")
            return
        }
        latestDailyTotals = perSourceDay[chosen]!!
            .map { (day, steps) -> DailyTotal(day, steps.toInt(), chosen) }
            .sortedBy { it.dayIndex }
        chosenSource = chosen
        todayStepsSoFar = perSourceDay[chosen]?.get(todayIdx)?.toInt() ?: 0
        todayStepsDay = todayIdx
        aapsLogger.info(LTag.APS, "HealthConnectStepsIngest: coverage=$availableSources chose=$chosen days=${latestDailyTotals.size}")
    }

    companion object {
        /**
         * Pick the step source with the most **daily coverage** — the count of distinct local days
         * that have real step data — with total steps as a tiebreaker. A continuous on-body source
         * (the phone's own pedometer) therefore wins over an app/aggregator that holds only sparse
         * or no daily history. "Most total steps" got this wrong: it picked a high-count source with
         * no usable per-day history, so the baseline never formed. Coverage is what the
         * deviation-from-baseline metric actually needs.
         */
        internal fun chooseSourceByCoverage(perSourceDay: Map<String, HashMap<Long, Long>>): String? {
            val withData = perSourceDay.filterValues { days -> days.values.any { it > 0 } }
            if (withData.isEmpty()) return null
            return withData.maxWith(
                compareBy<Map.Entry<String, HashMap<Long, Long>>> { it.value.count { d -> d.value > 0 } }
                    .thenBy { it.value.values.sum() }
            ).key
        }
    }

    /** Force a sync regardless of throttle — e.g. a settings "test now" button. */
    fun forceSync() {
        lastSyncRunMs = 0L
        syncIfDue()
    }
}
