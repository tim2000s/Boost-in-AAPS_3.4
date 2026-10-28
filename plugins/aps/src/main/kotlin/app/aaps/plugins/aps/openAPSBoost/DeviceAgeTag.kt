package app.aaps.plugins.aps.openAPSBoost

import java.util.Locale

/**
 * Infusion-site and reservoir age, logged in the reason string every cycle as
 * `siteAge=<h>; resAge=<h>; ` (hours to one decimal, `-` when no change is recorded) and parsed by
 * the extractor (2026-10-23). READ-ONLY: nothing reads either tag back.
 *
 * The site has a measurable life cycle in the developer's record (backtesting/scripts/
 * 2026-10-self-patterns/REPORT.md): a high in the first six hours, more lows to the end of the first
 * day, the best day second, insulin working less well from about 48 hours. The analysis had to
 * reconstruct site age from careportal records; this logs the age the loop itself saw, which any
 * later rule would act on, and lets the cycle be checked in other users' records
 * (SITE_CYCLE_ALGORITHM_OPTIONS.md, option A).
 *
 * The change times come from the therapy-event table, which a one-minute loop would otherwise query
 * every cycle, so they are cached for [REFRESH_MS]; a change logged since then appears within it.
 */
internal class DeviceAgeTag(private val lastChangeMs: (site: Boolean) -> Long?) {

    private var fetchedAtMs: Long? = null          // null until the first read; no sentinel to overflow
    private var siteMs: Long? = null
    private var reservoirMs: Long? = null

    fun tag(now: Long): String {
        val last = fetchedAtMs
        if (last == null || now - last >= REFRESH_MS || now < last) {
            siteMs = lastChangeMs(true)
            reservoirMs = lastChangeMs(false)
            fetchedAtMs = now
        }
        return "siteAge=${hours(siteMs, now)}; resAge=${hours(reservoirMs, now)}; "
    }

    companion object {
        const val REFRESH_MS = 10L * 60 * 1000

        /** Hours since [changeMs] to one decimal, or `-` when there is none or it lies in the future. */
        fun hours(changeMs: Long?, now: Long): String =
            if (changeMs == null || changeMs > now) "-"
            else String.format(Locale.ROOT, "%.1f", (now - changeMs) / 3_600_000.0)
    }
}
