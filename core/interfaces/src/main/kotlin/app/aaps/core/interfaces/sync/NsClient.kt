package app.aaps.core.interfaces.sync

import app.aaps.core.interfaces.nsclient.NSAlarm
import app.aaps.core.interfaces.profile.Profile
import app.aaps.core.interfaces.rx.events.EventNSClientNewLog

/**
 * Plugin providing communication with Nightscout server
 */
interface NsClient : Sync {

    /**
     * NS URL
     */
    val address: String

    /**
     * Set plugin in paused state
     */
    fun pause(newState: Boolean)

    /**
     * Initiate new round of upload/download
     *
     * @param reason identification of caller
     */
    fun resend(reason: String)

    /**
     * List of log messages for fragment
     */
    val listLog: MutableList<EventNSClientNewLog>

    /**
     * Used data sync selector
     */
    val dataSyncSelector: DataSyncSelector

    /**
     * Version of NS server
     * @return Returns detected version of NS server
     */
    fun detectedNsVersion(): String?

    enum class Collection { ENTRIES, TREATMENTS, FOODS, PROFILE }

    /**
     * NSC v3 does first load of all data
     * next loads are using srvModified property for sync
     * not used for NSCv1
     *
     * @return true if inside first load of NSCv3, true for NSCv1
     */
    fun isFirstLoad(collection: Collection): Boolean = true

    /**
     * Update newest loaded timestamp for entries collection (first load or NSCv1)
     * Update newest srvModified (sync loads)
     *
     * @param latestReceived timestamp
     *
     */
    fun updateLatestBgReceivedIfNewer(latestReceived: Long)

    /**
     * Update newest loaded timestamp for treatments collection (first load or NSCv1)
     * Update newest srvModified (sync loads)
     *
     * @param latestReceived timestamp
     *
     */
    fun updateLatestTreatmentReceivedIfNewer(latestReceived: Long)

    /**
     * Send alarm confirmation to NS
     *
     * @param originalAlarm alarm to be cleared
     * @param silenceTimeInMilliseconds silence alarm for specified duration
     */
    fun handleClearAlarm(originalAlarm: NSAlarm, silenceTimeInMilliseconds: Long)

    /**
     * Clear synchronization status
     *
     * Next synchronization will start from scratch
     */
    fun resetToFullSync()

    /**
     * Request a BOUNDED re-download of history from Nightscout, starting at [fromTimestamp].
     *
     * Added 2026-07-30 for the install-time history gap: a user migrating onto a fresh AAPS database
     * has a local history far shorter than their Nightscout site's, which silently corrupts every
     * history-derived quantity (TDD, and hence dynamic ISF; the Boost auto-config window).
     * [resetToFullSync] already exists for this shape of problem but it is a MANUAL, unbounded
     * (100-day) action that also resets the UPLOAD cursors and re-pushes everything to the server.
     * This is the download-only, time-bounded sibling:
     *  - the download cursors are rewound to [fromTimestamp] and no further;
     *  - the upload sync state is left completely untouched;
     *  - nothing blocks — the request only arms the existing NSClient worker chain, which performs
     *    the fetch on its own thread. Implementations must not do network I/O on the calling thread.
     *
     * Storage goes through the normal NS sync transactions, which deduplicate on
     * nightscoutId / pumpId / timestamp, so the call is idempotent and safe to repeat.
     *
     * @param fromTimestamp epoch ms; the oldest record to fetch. Implementations may clamp it to
     *                      their own maximum age.
     * @return true if the request was armed, false if this client cannot service it (disabled,
     *         paused, not configured, or not supported by this NSClient version).
     */
    fun requestHistoryBackfill(fromTimestamp: Long): Boolean = false

    /**
     * Upload new record to NS
     *
     * @param collection target ns collection
     * @param dataPair data to upload (data.first) and id of changed record (data.second)
     * @param progress progress of sync in format "number/number". Only for display in fragment
     * @return true for successful upload
     */
    suspend fun nsAdd(collection: String, dataPair: DataSyncSelector.DataPair, progress: String, profile: Profile? = null): Boolean

    /**
     * Upload updated record to NS
     *
     * @param collection target ns collection
     * @param dataPair data to upload (data.first) and id of changed record (data.second)
     * @param progress progress of sync in format "number/number". Only for display in fragment
     * @return true for successful upload
     */
    suspend fun nsUpdate(collection: String, dataPair: DataSyncSelector.DataPair, progress: String, profile: Profile? = null): Boolean
}