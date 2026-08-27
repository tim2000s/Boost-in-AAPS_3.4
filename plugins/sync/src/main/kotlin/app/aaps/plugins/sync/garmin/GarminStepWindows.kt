package app.aaps.plugins.sync.garmin

/**
 * Bounds the six trailing step-window counts a watch reports, before they reach the database.
 *
 * A window count has a physical ceiling. Nobody sustains more than about 200 steps a minute, and a
 * sprint is under it, so a larger number is a counter rather than a window. On 2026-08-27 a Venu 3
 * sent 1919 in all six windows at once, which is the day's cumulative total: its reset handling
 * returned the whole counter whenever it saw a negative delta, and every window took that branch on
 * the same wake. The activity classifier calls 300 steps in fifteen minutes a brisk walk, so 1919
 * reads as six times that and the loop would have treated it as continuous exercise and raised the
 * target on it.
 *
 * The watch-side fault is fixed separately. This exists because a watch in the field is not easily
 * updated, and a value that steers dosing should not rest on one guard in one place.
 *
 * Clamping rather than rejecting: a clamped value is still wrong but it is bounded, and it keeps a
 * genuine burst where dropping the record would lose the cycle. The wider windows are additionally
 * raised to at least the narrower ones, since a three-hour count cannot be smaller than the
 * five-minute count contained in it.
 */
object GarminStepWindows {

    /** Above a sprint cadence; anything higher is a counter, not a window. */
    const val MAX_STEPS_PER_MINUTE = 200

    data class Windows(
        val s5: Int, val s10: Int, val s15: Int,
        val s30: Int, val s60: Int, val s180: Int,
    )

    /** Steps in a window of [minutes], bounded by what a person can physically do. */
    fun clamp(steps: Int, minutes: Int): Int = steps.coerceIn(0, minutes * MAX_STEPS_PER_MINUTE)

    fun sanitise(s5: Int, s10: Int, s15: Int, s30: Int, s60: Int, s180: Int): Windows {
        val c5 = clamp(s5, 5)
        val c10 = maxOf(clamp(s10, 10), c5)
        val c15 = maxOf(clamp(s15, 15), c10)
        val c30 = maxOf(clamp(s30, 30), c15)
        val c60 = maxOf(clamp(s60, 60), c30)
        val c180 = maxOf(clamp(s180, 180), c60)
        return Windows(c5, c10, c15, c30, c60, c180)
    }
}
