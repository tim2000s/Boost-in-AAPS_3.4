package app.aaps.plugins.aps.openAPSBoostTwin

import org.json.JSONArray
import org.json.JSONObject

/**
 * Persisted rolling history of onset timestamps for the anticipation shadow (2026-07-27).
 * Two independent streams — exercise-bout onsets and meal (V5 CONFIRMED) onsets — each a rolling,
 * capped, recency-windowed list of epoch-seconds. This is the substrate the per-user
 * [AnticipationHabitModel] is refit from (~nightly). READ-ONLY to dosing; it only records.
 *
 * Persistence follows the V7ResidualTracker idiom: a single JSON blob in a StringKey, timestamps in
 * seconds to keep it compact, tolerant deserialize (blank/corrupt → empty, fails safe to the prior).
 */
class AnticipationOnsetStore {

    enum class Kind { EXERCISE, MEAL }

    companion object {
        const val WINDOW_MS = 56L * 86_400_000L        // ~8 weeks of history feeds the fit
        const val MAX_PER_KIND = 1500                  // hard cap on the persisted list
        private const val SERIAL_VERSION = 1

        fun deserialize(raw: String?): AnticipationOnsetStore {
            val s = AnticipationOnsetStore()
            if (raw.isNullOrBlank()) return s
            try {
                val j = JSONObject(raw)
                if (j.optInt("v") != SERIAL_VERSION) return AnticipationOnsetStore()
                loadList(j.optJSONArray("ex"), s.exercise)
                loadList(j.optJSONArray("meal"), s.meal)
            } catch (_: Throwable) {
                return AnticipationOnsetStore()
            }
            return s
        }

        private fun loadList(arr: JSONArray?, into: ArrayDeque<Long>) {
            if (arr == null) return
            for (i in 0 until arr.length()) into.addLast(arr.getLong(i) * 1000L)
        }
    }

    private val exercise = ArrayDeque<Long>()
    private val meal = ArrayDeque<Long>()

    private fun list(kind: Kind) = if (kind == Kind.EXERCISE) exercise else meal

    /** Record an onset (idempotent within a 5-min bucket — a re-invoke in the same cycle won't dup). */
    fun record(kind: Kind, tsMs: Long) {
        val l = list(kind)
        val last = l.lastOrNull()
        if (last != null && tsMs / 300_000L == last / 300_000L) return
        l.addLast(tsMs)
    }

    /** Drop entries older than the window or over the cap (oldest first). */
    fun evict(nowMs: Long) {
        val cutoff = nowMs - WINDOW_MS
        for (l in listOf(exercise, meal)) {
            while (l.isNotEmpty() && (l.first() < cutoff || l.size > MAX_PER_KIND)) l.removeFirst()
        }
    }

    fun count(kind: Kind): Int = list(kind).size

    /** Minutes since the most recent onset of [kind] (999.0 if none). */
    fun minsSinceLast(kind: Kind, nowMs: Long): Double {
        val last = list(kind).lastOrNull() ?: return 999.0
        return ((nowMs - last).coerceAtLeast(0L)) / 60_000.0
    }

    /** Raw onset epochs (ms), oldest first — the caller converts to week-minutes + ages for the fit. */
    fun epochsMs(kind: Kind): LongArray = list(kind).toLongArray()

    fun serialize(): String {
        val j = JSONObject().put("v", SERIAL_VERSION)
        j.put("ex", JSONArray().apply { exercise.forEach { put(it / 1000L) } })
        j.put("meal", JSONArray().apply { meal.forEach { put(it / 1000L) } })
        return j.toString()
    }
}
