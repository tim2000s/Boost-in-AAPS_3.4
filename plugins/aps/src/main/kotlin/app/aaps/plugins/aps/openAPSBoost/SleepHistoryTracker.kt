package app.aaps.plugins.aps.openAPSBoost

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin

/**
 * SleepHistoryTracker — rolling 28-day record of sleep onset and wake times, with
 * circular-mean aggregation so PRE_SLEEP can fire `preSleepLeadMin` before the user's
 * *learned* habitual sleep onset (not just the configured nightStart fallback).
 *
 * Two events drive the record:
 *   AWAKE → SLEEPING       → record `sleepStartMs` (the current "session")
 *   SLEEPING → AWAKE       → record `wakeMs`, close the session, persist
 *
 * Storage shape (StringKey `ApsBoostSleepHistory`):
 *   {
 *     "sessions": [
 *       { "sleepStartMs": ..., "wakeMs": ... }, ...
 *     ],
 *     "openSleepStartMs": <ms or null>     // current session that hasn't woken yet
 *   }
 *
 * Trim policy: keep only sessions whose `sleepStartMs` is within the last 28 days.
 *
 * Aggregation:
 *   - Convert sleepStartMs and wakeMs to local clock-minute-of-day [0..1439]
 *   - Compute *circular* mean (vector sum on unit circle, atan2 back) to handle
 *     wrap-around correctly: avg of (22:00, 02:00) = 00:00, not 12:00
 *   - Return null if fewer than [minSessionsForLearned] sessions present
 */
object SleepHistoryTracker {

    private const val WINDOW_DAYS = 28L
    private const val WINDOW_MS = WINDOW_DAYS * 24L * 60L * 60L * 1000L
    private const val MIN_SESSIONS_FOR_LEARNED = 7

    /**
     * A closed sleep session.
     *
     * @param sleepHrP10      p10 of HR samples during the sleep period (null if insufficient data) —
     *                        approximates true resting HR (deep sleep floor)
     * @param daytimeHrP10    p10 of HR samples during the preceding awake period (null if no
     *                        previous session or insufficient data) — active baseline used for
     *                        exercise classification
     */
    data class Session(
        val sleepStartMs: Long,
        val wakeMs: Long,
        val sleepHrP10: Int? = null,
        val daytimeHrP10: Int? = null,
        // Why the session ended: "hr_steps"/"resume" = genuine wake (trains the learned wake time);
        // "boundary" = hard night-window exit (excluded from wake learning); null = legacy/unknown
        // (also excluded, so the pre-fix collapsed history is discarded rather than re-learned).
        val wakeReason: String? = null
    )

    /**
     * Carrier struct persisted to SharedPreferences.
     *
     * @param sessions          Closed sessions within rolling window
     * @param openSleepStartMs  The current session (entered SLEEPING but not yet woken). Null when no session in progress.
     */
    data class History(
        var sessions: MutableList<Session> = mutableListOf(),
        var openSleepStartMs: Long? = null
    ) {
        fun serialize(): String {
            val arr = JSONArray()
            for (s in sessions) {
                val o = JSONObject()
                    .put("sleepStartMs", s.sleepStartMs)
                    .put("wakeMs", s.wakeMs)
                if (s.sleepHrP10 != null) o.put("sleepHrP10", s.sleepHrP10)
                if (s.daytimeHrP10 != null) o.put("daytimeHrP10", s.daytimeHrP10)
                if (s.wakeReason != null) o.put("wakeReason", s.wakeReason)
                arr.put(o)
            }
            return JSONObject()
                .put("sessions", arr)
                .put("openSleepStartMs", openSleepStartMs ?: JSONObject.NULL)
                .toString()
        }

        companion object {
            fun deserialize(raw: String): History {
                if (raw.isBlank()) return History()
                return try {
                    val j = JSONObject(raw)
                    val arr = j.optJSONArray("sessions") ?: JSONArray()
                    val list = mutableListOf<Session>()
                    for (i in 0 until arr.length()) {
                        val o = arr.getJSONObject(i)
                        list.add(Session(
                            sleepStartMs = o.getLong("sleepStartMs"),
                            wakeMs = o.getLong("wakeMs"),
                            sleepHrP10 = if (o.has("sleepHrP10")) o.getInt("sleepHrP10") else null,
                            daytimeHrP10 = if (o.has("daytimeHrP10")) o.getInt("daytimeHrP10") else null,
                            wakeReason = if (o.has("wakeReason")) o.getString("wakeReason") else null
                        ))
                    }
                    val openVal = j.opt("openSleepStartMs")
                    val open = if (openVal == null || openVal == JSONObject.NULL) null else (openVal as Number).toLong()
                    History(list, open)
                } catch (e: Exception) {
                    History()
                }
            }
        }
    }

    /**
     * Aggregate metrics from the rolling history.
     *
     * @param sleepStartMinAvg      Circular-mean clock-minute of sleep onset (0..1439), null if insufficient data
     * @param wakeMinAvg            Circular-mean clock-minute of wake (0..1439), null if insufficient data
     * @param sleepDurationMinAvg   Mean sleep duration in minutes, null if insufficient data
     * @param sessionCount          Number of closed sessions inside the 28-day window
     * @param restingHrBpm          Median of per-session sleepHrP10 — true resting HR. null if insufficient data.
     * @param daytimeHrBpm          Median of per-session daytimeHrP10 — active baseline (for exercise calcs). null if insufficient data.
     * @param restingHrSampleCount  Number of sessions contributing non-null sleepHrP10
     * @param daytimeHrSampleCount  Number of sessions contributing non-null daytimeHrP10
     */
    data class Aggregate(
        val sleepStartMinAvg: Int?,
        val wakeMinAvg: Int?,
        val sleepDurationMinAvg: Int?,
        val sessionCount: Int,
        val restingHrBpm: Int? = null,
        val daytimeHrBpm: Int? = null,
        val restingHrSampleCount: Int = 0,
        val daytimeHrSampleCount: Int = 0
    )

    /** Called by the plugin when SleepStateDetector transitions AWAKE→SLEEPING. */
    fun onSleepStart(h: History, sleepStartMs: Long): History {
        return h.copy(openSleepStartMs = sleepStartMs)
    }

    /**
     * Called by the plugin when SleepStateDetector transitions SLEEPING→AWAKE. Closes the
     * open session, appends to history, and trims old sessions outside the rolling window.
     *
     * @param sleepHrBpms     HR samples (BPM) collected during the just-ended sleep period.
     *                        Used to compute sleepHrP10. Pass empty list if unavailable.
     * @param daytimeHrBpms   HR samples (BPM) collected during the awake period BEFORE this
     *                        sleep (since the previous session's wakeMs). Used to compute
     *                        daytimeHrP10. Pass empty list if no prior session.
     *
     * Returns the updated history (caller persists).
     */
    fun onWake(
        h: History,
        wakeMs: Long,
        sleepHrBpms: List<Double> = emptyList(),
        daytimeHrBpms: List<Double> = emptyList(),
        wakeReason: String? = null
    ): History {
        val open = h.openSleepStartMs ?: return h.copy()      // no open session; nothing to do
        val newSessions = h.sessions.toMutableList()
        newSessions.add(
            Session(
                sleepStartMs = open,
                wakeMs = wakeMs,
                sleepHrP10 = p10(sleepHrBpms),
                daytimeHrP10 = p10(daytimeHrBpms),
                wakeReason = wakeReason
            )
        )
        // Trim sessions whose start is older than the rolling window
        val cutoff = wakeMs - WINDOW_MS
        newSessions.removeAll { it.sleepStartMs < cutoff }
        return History(newSessions, openSleepStartMs = null)
    }

    /** Returns wakeMs of the latest closed session, or null if none. Plugin uses this to bound the daytime window. */
    fun lastWakeMs(h: History): Long? = h.sessions.maxByOrNull { it.wakeMs }?.wakeMs

    /** Compute aggregates over the rolling window. */
    fun aggregate(h: History, localOffsetMs: Long): Aggregate {
        val restingHrSamples = h.sessions.mapNotNull { it.sleepHrP10 }
        val daytimeHrSamples = h.sessions.mapNotNull { it.daytimeHrP10 }
        val restingHr = if (restingHrSamples.size >= MIN_SESSIONS_FOR_LEARNED) median(restingHrSamples) else null
        val daytimeHr = if (daytimeHrSamples.size >= MIN_SESSIONS_FOR_LEARNED) median(daytimeHrSamples) else null

        // Learned WAKE time is trained ONLY on genuine wakes ("hr_steps"/"resume"/"steps"); "boundary"
        // hard-exit wakes (and legacy null) are excluded, with its own session-count gate. This
        // breaks the hard-exit→learned-wake feedback loop: without a genuine wake signal (e.g. a
        // sparse-HR night) wakeMinAvg stays null and the caller falls back to the configured wake.
        // "steps" (2026-07-08): steps-only wake when HR is unreliable — genuine, so it trains too.
        val genuineWakeMins = h.sessions
            .filter { it.wakeReason == "hr_steps" || it.wakeReason == "resume" || it.wakeReason == "steps" }
            .map { msToMinOfDay(it.wakeMs, localOffsetMs) }
        val wakeAvg = if (genuineWakeMins.size >= MIN_SESSIONS_FOR_LEARNED) circularMean(genuineWakeMins) else null

        if (h.sessions.size < MIN_SESSIONS_FOR_LEARNED) {
            return Aggregate(
                sleepStartMinAvg = null, wakeMinAvg = wakeAvg,
                sleepDurationMinAvg = null, sessionCount = h.sessions.size,
                restingHrBpm = restingHr, daytimeHrBpm = daytimeHr,
                restingHrSampleCount = restingHrSamples.size,
                daytimeHrSampleCount = daytimeHrSamples.size
            )
        }
        val sleepStartMin = h.sessions.map { msToMinOfDay(it.sleepStartMs, localOffsetMs) }
        val durations = h.sessions.map { ((it.wakeMs - it.sleepStartMs) / 60_000L).toInt() }
        return Aggregate(
            sleepStartMinAvg = circularMean(sleepStartMin),
            wakeMinAvg = wakeAvg,
            sleepDurationMinAvg = if (durations.isNotEmpty()) durations.sum() / durations.size else null,
            sessionCount = h.sessions.size,
            restingHrBpm = restingHr,
            daytimeHrBpm = daytimeHr,
            restingHrSampleCount = restingHrSamples.size,
            daytimeHrSampleCount = daytimeHrSamples.size
        )
    }

    /**
     * Compute the p10 (10th percentile) of a list of HR values (BPM). Returns null when the
     * sample is too small to be representative (< [minSamples]).
     *
     * Used at session-close time to summarise a sleep period's "deep-sleep floor" or an
     * awake period's "active baseline" in a single robust statistic.
     */
    fun p10(values: List<Double>, minSamples: Int = 30): Int? {
        val valid = values.filter { it.isFinite() && it > 0 }
        if (valid.size < minSamples) return null
        val sorted = valid.sorted()
        val idx = ((sorted.size - 1) * 0.10).toInt().coerceIn(0, sorted.size - 1)
        return sorted[idx].toInt()
    }

    /** Integer median (lower of two middles for even-count). */
    private fun median(values: List<Int>): Int? {
        if (values.isEmpty()) return null
        val sorted = values.sorted()
        return sorted[sorted.size / 2]
    }

    /**
     * Convert an absolute UTC millis instant to local clock minute-of-day [0..1439].
     *
     * @param utcMs        UTC instant
     * @param localOffsetMs  Local-time offset from UTC in ms (e.g. BST = +1h = 3,600,000)
     */
    fun msToMinOfDay(utcMs: Long, localOffsetMs: Long): Int {
        val localMs = utcMs + localOffsetMs
        val msPerDay = 24L * 60L * 60L * 1000L
        val msIntoDay = ((localMs % msPerDay) + msPerDay) % msPerDay
        return (msIntoDay / 60_000L).toInt()
    }

    /**
     * Circular mean of a list of minute-of-day values, handling wrap-around correctly.
     * Returns the mean clock-minute (0..1439). Each value is mapped to an angle on the
     * unit circle, vectors summed, and the resulting angle converted back to a minute.
     *
     * Example: circularMean([1320, 1410, 60, 120]) ≈ 0 (≈ midnight), NOT 727 (12:07).
     */
    fun circularMean(minutes: List<Int>): Int? {
        if (minutes.isEmpty()) return null
        var sx = 0.0
        var sy = 0.0
        for (m in minutes) {
            val angle = 2.0 * Math.PI * m / 1440.0
            sx += cos(angle)
            sy += sin(angle)
        }
        val mean = atan2(sy, sx)
        val normalized = (mean + 2.0 * Math.PI) % (2.0 * Math.PI)
        return ((normalized / (2.0 * Math.PI)) * 1440.0).toInt() % 1440
    }
}
