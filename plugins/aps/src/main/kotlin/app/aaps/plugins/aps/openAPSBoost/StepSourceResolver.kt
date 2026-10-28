package app.aaps.plugins.aps.openAPSBoost

/**
 * StepSourceResolver — Boost activity-load source abstraction (2026-06-28).
 *
 * Picks ONE active step source per cycle from whatever the user actually has — a worn AAPS Wear
 * watch, Garmin, another Health-Connect writer, or the phone pedometer — with NO user-facing knob
 * (the minimal-settings tenet: resolution is fully automatic). Replaces the old split where the
 * 24–48h baseline read Health Connect ONLY (and silently starved when Garmin stopped syncing to HC)
 * while intraday read Wear-or-phone — two pipelines that could disagree about reality.
 *
 * Two SEPARATE concerns (so a device switch never drops the user into a 7-day warmup):
 *   - SELECTION (here): which source owns TODAY's cumulative count. Highest-trust source with a
 *     live feed wins.
 *   - COVERAGE (the bridging layer in [DailyStepHistoryTracker]): the rolling baseline window is
 *     filled from the active source's days where it has them, and BRIDGED with the previous
 *     source's historic days where it doesn't — so changing watches keeps rolling-7-day coverage
 *     instead of resetting the baseline to zero. Cross-source absolute-count differences are
 *     reconciled there, not here.
 *
 * Trust ranking (best first): a worn watch beats an aggregator — Wear (on-body, continuous,
 * independent of HC) > Garmin > other Health-Connect writer > phone pedometer (only counts when
 * carried). Active source = the highest-trust source whose feed is fresh; if none is fresh, the
 * highest-trust source that has ANY recent data (so today's count is still reported); else none.
 *
 * Pure / no I/O — the caller assembles [SourceState]s from the adapters and persists nothing here.
 */
object StepSourceResolver {

    /** Canonical source ids, best-trust first. Raw ids are mapped to these by [canonical]. */
    const val WEAR = "wear"
    const val GARMIN = "garmin"
    const val PHONE = "phone"
    /** Any other Health-Connect writer (Google Fit, Samsung Health, …) → "hc:<shortname>". */
    const val HC_PREFIX = "hc:"

    private const val GARMIN_PKG = "com.garmin.android.apps.connectmobile"

    /**
     * Map a raw source id to its canonical id. [raw] is either an adapter tag already in canonical
     * form ("wear"/"phone") or a Health-Connect `dataOrigin` package name.
     */
    fun canonical(raw: String): String = when {
        raw == WEAR || raw == PHONE -> raw
        raw == GARMIN || raw == GARMIN_PKG -> GARMIN
        raw.startsWith(HC_PREFIX) -> raw
        else -> HC_PREFIX + raw.substringAfterLast('.')   // a bare HC package name
    }

    /** Trust tier (lower = better). Unknown → after phone. */
    fun tier(canonicalSource: String): Int = when {
        canonicalSource == WEAR -> 0
        canonicalSource == GARMIN -> 1
        canonicalSource.startsWith(HC_PREFIX) -> 2
        canonicalSource == PHONE -> 3
        else -> 4
    }

    /**
     * One candidate source's current state.
     * @param source       canonical id (see [canonical]).
     * @param fresh        intraday feed produced data recently (else its today total may be stale).
     * @param coverageDays distinct completed days with steps in THIS source's own history.
     * @param stepsToday   today's cumulative steps as reported by this source.
     */
    data class SourceState(
        val source: String,
        val fresh: Boolean,
        val coverageDays: Int,
        val stepsToday: Int
    )

    data class Resolution(
        /** Source that owns today's cumulative count; null only when no source has any data. */
        val active: String?,
        /** Today's cumulative from [active] (0 when null). */
        val stepsToday: Int,
        /** [active]'s feed is currently fresh (else today's count may be laggy, e.g. HC hourly). */
        val activeFresh: Boolean,
        /** Compact per-source diagnostics for NS, best-trust first: "src(fresh,covDays)". */
        val note: String
    )

    /**
     * Pick today's active source. [states] need not be pre-sorted; ids need not be canonical (we
     * canonicalise and sort by trust here). Selection does NOT gate on history — coverage is the
     * bridging layer's job. Never throws; empty input → active=null.
     */
    fun resolve(states: List<SourceState>): Resolution {
        val ranked = states
            .map { it.copy(source = canonical(it.source)) }
            .sortedBy { tier(it.source) }

        // Highest-trust fresh source; else highest-trust source with any recent data.
        val chosen = ranked.firstOrNull { it.fresh }
            ?: ranked.firstOrNull { it.coverageDays > 0 || it.stepsToday > 0 }

        val note = ranked.joinToString(" ") {
            "${it.source}(${if (it.fresh) "f" else "-"},${it.coverageDays}d)"
        }.ifEmpty { "none" }

        return Resolution(
            active = chosen?.source,
            stepsToday = chosen?.stepsToday ?: 0,
            activeFresh = chosen?.fresh ?: false,
            note = if (chosen == null) "none[$note]" else note
        )
    }
}
