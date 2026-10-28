package app.aaps.plugins.main.general.overview.boost

import java.util.Locale

/**
 * Chooses what the Boost V2 overview shows for the pump battery and, in AAPSClient, for the main
 * phone's (uploader's) battery. Pure: every input is passed in, so the choice can be unit tested
 * without a pump driver, Nightscout or a fragment.
 *
 * The full app reads the local pump driver. Several drivers have no usable level (Omnipod Dash and
 * Medtrum return null, the Combo only reports a three-state flag and declares
 * `supportBatteryLevel = false`, Dana returns null or 0 before the first connection), so it falls
 * back to the age of the last pump battery change, as the stock status lights do, and hides the
 * row for patch pumps whose battery lives and dies with the patch.
 *
 * AAPSClient has no pump of its own: its active pump is the virtual pump, whose `batteryLevel` is a
 * constant 50. Its values therefore come from the Nightscout device status uploaded by the main
 * phone, and a status older than [staleAfterMs] is treated as absent rather than shown.
 */
object BoostBatteryDisplay {

    const val PLACEHOLDER = "---"

    enum class Kind { PERCENT, VOLTAGE, AGE, UNAVAILABLE, HIDDEN }

    /** [text] goes on screen, [spoken] into the TalkBack description, [percent] drives the warning colour. */
    data class Reading(val kind: Kind, val text: String, val spoken: String, val percent: Int? = null) {

        val visible: Boolean get() = kind != Kind.HIDDEN
    }

    /** What the local pump driver reports (full app). */
    data class LocalPump(
        val level: Int?,
        /** `pump.model().supportBatteryLevel`, or an Eros with a RileyLink-compatible link that reports one. */
        val supportsLevel: Boolean,
        /** `isBatteryReplaceable || isBatteryChangeLoggingEnabled()`: the stock rule for showing battery age. */
        val batteryAgeApplies: Boolean,
        /** Patch pump with no hardware link: the stock overview hides the battery row for these. */
        val patchWithoutLink: Boolean
    )

    /** The pump section of the newest Nightscout device status (AAPSClient). */
    data class NsPump(val clock: Long, val percent: Int?, val voltage: Double?)

    /** One uploader entry from the Nightscout device status (AAPSClient). */
    data class NsUploader(val clock: Long, val battery: Int, val isCharging: Boolean?)

    fun pumpBattery(
        isClient: Boolean,
        local: LocalPump?,
        ns: NsPump?,
        batteryChangeTimestamp: Long?,
        now: Long,
        staleAfterMs: Long
    ): Reading {
        if (isClient) {
            val fresh = ns != null && now - ns.clock <= staleAfterMs
            if (fresh) {
                val pct = ns!!.percent
                if (pct != null && pct > 0) return percent(pct)
                val v = ns.voltage
                if (v != null && v > 0.0) {
                    val txt = String.format(Locale.US, "%.2fV", v)
                    return Reading(Kind.VOLTAGE, txt, String.format(Locale.US, "%.2f volts", v))
                }
            }
            age(batteryChangeTimestamp, now)?.let { return it }
            return when {
                ns == null -> Reading(Kind.UNAVAILABLE, PLACEHOLDER, "no pump status from the main phone")
                !fresh     -> Reading(Kind.UNAVAILABLE, PLACEHOLDER, "no recent pump status from the main phone")
                else       -> Reading(Kind.UNAVAILABLE, PLACEHOLDER, "not reported by the pump")
            }
        }

        val pump = local ?: return Reading(Kind.UNAVAILABLE, PLACEHOLDER, "unknown")
        val lvl = pump.level
        if (pump.supportsLevel && lvl != null && lvl > 0) return percent(lvl)
        if (pump.batteryAgeApplies) age(batteryChangeTimestamp, now)?.let { return it }
        if (pump.patchWithoutLink) return Reading(Kind.HIDDEN, "", "")
        return Reading(Kind.UNAVAILABLE, PLACEHOLDER, "unknown")
    }

    /**
     * The main phone's battery in AAPSClient: the lowest fresh uploader level, as the stock client
     * overview takes the minimum across uploaders. Hidden outside client mode, where the phone's own
     * battery is in the system status bar.
     */
    fun uploaderBattery(isClient: Boolean, uploaders: Collection<NsUploader>, now: Long, staleAfterMs: Long): Reading {
        if (!isClient) return Reading(Kind.HIDDEN, "", "")
        if (uploaders.isEmpty()) return Reading(Kind.UNAVAILABLE, PLACEHOLDER, "no status from the main phone")
        val lowest = uploaders.filter { now - it.clock <= staleAfterMs && it.battery > 0 }.minByOrNull { it.battery }
            ?: return Reading(Kind.UNAVAILABLE, PLACEHOLDER, "no recent status from the main phone")
        val charging = lowest.isCharging == true
        val text = if (charging) "ᴪ ${lowest.battery}%" else "${lowest.battery}%"
        val spoken = if (charging) "${lowest.battery} percent, charging" else "${lowest.battery} percent"
        return Reading(Kind.PERCENT, text, spoken, lowest.battery)
    }

    fun formatAge(ms: Long): String {
        val totalHours = ms.coerceAtLeast(0) / 3_600_000L
        return "${totalHours / 24}d ${totalHours % 24}h"
    }

    private fun percent(p: Int) = Reading(Kind.PERCENT, "$p%", "$p percent", p)

    private fun age(changed: Long?, now: Long): Reading? {
        changed ?: return null
        val ms = (now - changed).coerceAtLeast(0)
        val totalHours = ms / 3_600_000L
        return Reading(Kind.AGE, formatAge(ms), "changed ${totalHours / 24} days ${totalHours % 24} hours ago")
    }
}
