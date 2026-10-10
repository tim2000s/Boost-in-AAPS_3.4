package app.aaps.plugins.aps.openAPSBoost

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.min

/**
 * MealTimeLearner — Boost V6.
 *
 * Learns a user's habitual meal times from the events V5 itself already calls meals (a fresh
 * CONFIRMED commit) and exposes a query the loop uses to fire an anticipatory low temp target
 * 45–60 min before a learned meal. Reuses [SleepHistoryTracker]'s `msToMinOfDay` / `circularMean`
 * so all time-of-day maths is midnight-wrap-safe and consistent with the sleep learner.
 *
 * **Why CONFIRMED events** (design decision, 2026-06-15): they are the real, already-computed
 * meal detector — no second detector to tune, and the histogram learns exactly what V5 treats
 * as a meal. The plugin records `decision.mealHypothesis == CONFIRMED && mealHypothesisAge == 0`.
 *
 * Storage shape (StringKey `ApsBoostMealTimeHistory`):
 *   { "events": [ <utcMs>, <utcMs>, ... ] }      // rolling [WINDOW_DAYS] days
 *
 * Clustering: events are projected to local minute-of-day and greedily grouped into *modes*.
 * A mode is emitted only when a cluster has ≥ [MIN_SESSIONS] events spread over ≥ [MIN_DISTINCT_DAYS]
 * distinct days within ±[CLUSTER_HALF_WIDTH_MIN] — so a one-off late dinner can't manufacture a
 * window. The mode centre is the circular mean of its members.
 *
 * Safety posture: empty / corrupt history → no modes → [preMealWindow] returns null → the feature
 * never fires. The learner has ZERO dosing impact on its own; the plugin gates the actual target
 * change behind a user toggle (shadow-first).
 */
object MealTimeLearner {

    private const val WINDOW_DAYS = 60L
    private const val WINDOW_MS = WINDOW_DAYS * 24L * 60L * 60L * 1000L

    /** A cluster must have at least this many events to be a trusted meal mode. */
    const val MIN_SESSIONS = 6

    /** …spread over at least this many distinct days (kills a single binge-day false mode). */
    const val MIN_DISTINCT_DAYS = 4

    /** Circular half-width (min) for grouping events into one mode (~07:50 ± 45 → breakfast). */
    const val CLUSTER_HALF_WIDTH_MIN = 45

    /** The pre-meal window always CLOSES this many minutes before the learned meal (45–60 prior, by design). */
    const val PRE_MEAL_LEAD_MIN_FLOOR = 45

    /** Guaranteed minimum window span (min), so a low leadMax setting can't yield a zero-width window. */
    const val PRE_MEAL_MIN_SPAN_MIN = 10

    private const val MINUTES_PER_DAY = 1440

    /** Rolling history of meal-commit timestamps (UTC ms). */
    data class History(var events: MutableList<Long> = mutableListOf()) {
        fun serialize(): String {
            val arr = JSONArray()
            for (e in events) arr.put(e)
            return JSONObject().put("events", arr).toString()
        }

        companion object {
            fun deserialize(raw: String): History {
                if (raw.isBlank()) return History()
                return try {
                    val arr = JSONObject(raw).optJSONArray("events") ?: JSONArray()
                    val list = mutableListOf<Long>()
                    for (i in 0 until arr.length()) list.add(arr.getLong(i))
                    History(list)
                } catch (e: Exception) {
                    History()
                }
            }
        }
    }

    /** A learned habitual meal time. */
    data class MealMode(
        /** Circular-mean clock minute-of-day [0..1439]. */
        val centreMin: Int,
        /** Number of events in the cluster. */
        val eventCount: Int,
        /** Number of distinct local days contributing (the trust signal). */
        val distinctDays: Int,
    )

    /** Result of a positive [preMealWindow] match. */
    data class PreMealHit(
        val mode: MealMode,
        /** How many minutes before the meal centre we currently are. */
        val minutesBeforeMeal: Int,
    )

    /**
     * Record a fresh meal-commit at [tsMs]. Appends and trims to the rolling window.
     * Returns the updated history (caller persists).
     */
    fun record(h: History, tsMs: Long): History {
        val newEvents = h.events.toMutableList()
        newEvents.add(tsMs)
        val cutoff = tsMs - WINDOW_MS
        newEvents.removeAll { it < cutoff }
        return History(newEvents)
    }

    /**
     * True when local [minOfDay] lies in the night window `[startMin, endMin)`. A window that wraps
     * midnight (start later than end, e.g. 22:00 to 07:00) is the union of `[start, 1440)` and
     * `[0, end)`, so 23:30 and 03:00 are both inside and 07:00 is not. Equal times are an empty window,
     * the same convention as [NightWindow.contains], so a misconfigured window drops nothing.
     */
    fun inNightMinutes(minOfDay: Int, startMin: Int, endMin: Int): Boolean = when {
        startMin == endMin -> false
        startMin < endMin  -> minOfDay in startMin until endMin
        else               -> minOfDay >= startMin || minOfDay < endMin
    }

    /**
     * [h] without the events whose local time falls inside the configured night window (2026-10-08).
     * Before the learner was gated on the night window and the sleep detector it recorded overnight
     * sessions, which in the field were rises with no logged carbs, mostly while the detector read
     * SLEEPING or PRE_SLEEP; enough of them form a mode and move the lowered pre-meal target into the
     * night. Local time uses [localOffsetMs] as [modes] does. Returns [h] itself when nothing is dropped.
     */
    fun withoutNightEvents(h: History, nightStartMin: Int, nightEndMin: Int, localOffsetMs: Long): History {
        val kept = h.events.filterNot {
            inNightMinutes(SleepHistoryTracker.msToMinOfDay(it, localOffsetMs), nightStartMin, nightEndMin)
        }
        return if (kept.size == h.events.size) h else History(kept.toMutableList())
    }

    /** Smaller of clockwise / anticlockwise distance between two minute-of-day values. */
    private fun circularDistance(a: Int, b: Int): Int {
        val d = abs(a - b)
        return min(d, MINUTES_PER_DAY - d)
    }

    /**
     * Greedily cluster the history's events into trusted meal modes (descending by size).
     * O(n²) over events, but n is tiny (≤ ~3 meals/day × 60 days).
     */
    fun modes(h: History, localOffsetMs: Long): List<MealMode> {
        if (h.events.size < MIN_SESSIONS) return emptyList()
        // (minuteOfDay, dayIndex) per event
        val pts = h.events.map { ms ->
            SleepHistoryTracker.msToMinOfDay(ms, localOffsetMs) to ((ms + localOffsetMs) / (24L * 60L * 60L * 1000L))
        }.toMutableList()

        val result = mutableListOf<MealMode>()
        while (pts.size >= MIN_SESSIONS) {
            // pick the event whose ±half-width neighbourhood holds the most events
            val best = pts.maxByOrNull { c -> pts.count { circularDistance(it.first, c.first) <= CLUSTER_HALF_WIDTH_MIN } }
                ?: break
            val cluster = pts.filter { circularDistance(it.first, best.first) <= CLUSTER_HALF_WIDTH_MIN }
            val distinctDays = cluster.map { it.second }.distinct().size
            if (cluster.size >= MIN_SESSIONS && distinctDays >= MIN_DISTINCT_DAYS) {
                val centre = SleepHistoryTracker.circularMean(cluster.map { it.first })
                if (centre != null) result.add(MealMode(centre, cluster.size, distinctDays))
                pts.removeAll(cluster.toSet())
            } else {
                // the densest remaining cluster isn't trustworthy → no further modes will be either
                break
            }
        }
        return result
    }

    /**
     * Is [nowMin] (local clock minute-of-day) inside the pre-meal lead window of any learned mode?
     *
     * The window for a mode centred at `c` is the arc `[c − openBefore, c − PRE_MEAL_LEAD_MIN_FLOOR]`
     * — it opens [openBefore] min before the meal and closes [PRE_MEAL_LEAD_MIN_FLOOR] min before
     * it (we stop adding pre-meal insulin once within the floor; V5's own detection takes the meal
     * from there). `openBefore` is the user's lead-minutes setting, but is held at least
     * [PRE_MEAL_MIN_SPAN_MIN] above the floor so a low setting can't collapse the window to nothing.
     * Returns the matched mode + how far before the meal we are, or null.
     *
     * @param leadMaxMin how far ahead the window opens (the user's "lead minutes" setting).
     */
    fun preMealWindow(
        h: History,
        nowMin: Int,
        localOffsetMs: Long,
        leadMaxMin: Int,
    ): PreMealHit? {
        val open = leadMaxMin.coerceAtLeast(PRE_MEAL_LEAD_MIN_FLOOR + PRE_MEAL_MIN_SPAN_MIN)
        for (mode in modes(h, localOffsetMs)) {
            // minutes from now forward to the meal centre, on the circle [0..1439]
            val ahead = ((mode.centreMin - nowMin) % MINUTES_PER_DAY + MINUTES_PER_DAY) % MINUTES_PER_DAY
            if (ahead in PRE_MEAL_LEAD_MIN_FLOOR..open) {
                return PreMealHit(mode, ahead)
            }
        }
        return null
    }
}
