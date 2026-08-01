package app.aaps.plugins.aps.openAPSBoost

/**
 * The configured night window as a CLOCK FACT, separate from the night-mode POLICY.
 *
 * `ApsBoostNightModeEnabled` answers "should Boost dose overnight?", which is a choice. The
 * start/end times answer "when is this user overnight?", which is not. Until 2026-07-31 the two
 * were conflated: `isInNightSleepPeriod()` returns false on its first line when the flag is off,
 * so switching the policy off also made the system forget when night was. The INACTIVE branch
 * raises the profile — it ADDS insulin — and needs the fact, not the policy, so it reads this
 * window whatever the flag says.
 *
 * Times default to 22:00 and 07:00 and are whatever the user has configured.
 */
object NightWindow {

    private const val DAY_MS = 86_400_000L

    /**
     * True when [nowMs] falls inside the window, handling the usual wrap past midnight.
     *
     * Equal times are an EMPTY window, not a whole day. The wrap branch would otherwise union to
     * cover everything and make it permanently night, which in the 2026-07-02 incident meant
     * Boost silently never dosed. Callers that want sleep protection when the window is
     * misconfigured must get it from the detector, not from here.
     *
     * @param nowMs   the instant under test
     * @param startMs absolute start, i.e. local midnight plus the configured start offset
     * @param endMs   absolute end, same basis
     */
    fun contains(nowMs: Long, startMs: Long, endMs: Long): Boolean {
        if (startMs == endMs) return false
        return if (endMs > startMs) nowMs in startMs until endMs
        else nowMs in (startMs - DAY_MS) until endMs || nowMs in startMs until (endMs + DAY_MS)
    }
}
