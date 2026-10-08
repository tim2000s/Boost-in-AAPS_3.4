package app.aaps.plugins.aps.openAPSBoostV5

import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min

/**
 * Splits the confirm commitment in two: part now, the rest ten minutes later if the rise continues.
 *
 * The confirm shot is currently the same size whether the excursion turns out to be 20 mg/dL or 100.
 * Measured over 140 episodes on the development participant, the median delivered at the confirming
 * cycle is 1.45 U for excursions under 30 mg/dL and 1.45 U for those over 75; the only component of
 * the response that scales with what actually happens is the committed holds that follow, and they
 * contribute a median of 0.00 U on the episodes that go nowhere. The confirm cycle carries 61.7 per
 * cent of the insulin delivered in the ninety minutes after a confirm.
 *
 * It cannot be sized correctly at the moment it fires. Separating the episodes that reach 75 mg/dL
 * from those that stay under 30, the trace gives 0.730 at the confirming cycle and 0.893 ten minutes
 * later, a paired gain of +0.162 [+0.066, +0.264]. The gain is front-loaded: one or two cycles are
 * worth more than everything from twenty minutes to forty-five combined. So the design does not need
 * to predict better, it needs to commit less until it knows more, and the knowing arrives fast.
 *
 * The release rule is a logistic on five quantities the loop already holds, derived over 764 confirm
 * episodes from eleven participants with participants held out as folds, so no score came from a
 * rule that had seen that person. It reaches 0.882 [0.849, 0.911] across the population and 0.798 to
 * 0.934 per participant, with no failure case. Coefficients live in
 * backtesting/scripts/2026-08-meal-size-readability/out/tranche_rule.json.
 *
 * Only the threshold is personal. Best values run 0.30 to 0.65 with a median of 0.48 and correlate
 * only -0.32 with a participant's own share of large excursions, so it cannot be inferred and is a
 * per-user knob for auto-config to derive. Raising it withholds more, which is a tightening, so the
 * existing raise-guard semantics already point the right way without modification.
 *
 * This can only deliver less than the engine would without it, never more. Over an episode the
 * immediate part plus any release is at most the confirm shot the engine sized, and a withheld
 * remainder that is never released is insulin not given; the committed cycles that follow are
 * unaffected and remain the size-responsive part of the response. On the cycle itself the release is
 * held to the bounds the rest of the V6 dose meets, through [onCycleBounded]: it is dropped unless the
 * engine is still in a meal state (CONFIRMED or COMMITTED), when a phase-3 hard gate fired, and inside
 * the post-rescue window, and what survives is clamped to the maxIOB headroom and the per-cycle cap the
 * confirm shot was held to. The release rule itself reads glucose shape only, which is why these
 * bounds sit outside it.
 */
class ConfirmTrancheController(
    // Settable rather than constructed, so changing the preference takes effect on the next cycle
    // instead of at the next restart. Auto-config owns the threshold in the shipping form.
    var immediateFraction: Double = 0.5,
    var releaseThreshold: Double = 0.48,
    private val holdMinutes: Double = 10.0,
    private val expiryMinutes: Double = 30.0,
) {

    // Fitted 2026-08-27, eleven participants, held out by participant. See the class KDoc.
    private companion object {
        const val B0 = 2.48631
        const val BG_CONFIRM = -0.014480
        const val RISE_SINCE = -0.003822
        const val MAX_RISE_SINCE = 0.138821
        const val SLOPE_NOW = 0.072499
        const val BG_NOW = -0.018302
        const val HOLD_SLACK_MIN = 2.5
        fun sigmoid(z: Double) = 1.0 / (1.0 + exp(-z))
    }

    data class Pending(
        val heldU: Double,
        val bgAtConfirm: Double,
        val confirmMs: Long,
        var maxBgSince: Double,
    )

    private var pending: Pending? = null
    private var lastBg: Double? = null

    /** What is currently held back, for logging. Zero when nothing is pending. */
    fun heldU(): Double = pending?.heldU ?: 0.0

    /**
     * Called on a confirming cycle. Returns what to deliver NOW; the rest is held.
     * A confirm arriving while something is already pending replaces it, since the older hold
     * belongs to a rise the engine has evidently stopped tracking.
     */
    fun onConfirm(nowMs: Long, bg: Double, sizedDose: Double): Double {
        if (sizedDose <= 0.0 || !bg.isFinite()) return sizedDose
        val f = immediateFraction.coerceIn(0.0, 1.0)
        val now = sizedDose * f
        val held = max(0.0, sizedDose - now)
        pending = if (held > 0.0) Pending(held, bg, nowMs, bg) else null
        lastBg = bg
        return now
    }

    /**
     * Called on every non-confirming cycle. Returns the remainder if the rule releases it, or zero.
     *
     * Returns zero and clears the hold once the window has passed, so a remainder is either released
     * on its cycle or not at all. Carrying it further would reintroduce the thing being removed, a
     * commitment made on evidence that has since gone stale.
     */
    fun onCycle(nowMs: Long, bg: Double?): Double {
        val p = pending ?: return 0.0
        if (bg == null || !bg.isFinite()) return 0.0
        p.maxBgSince = max(p.maxBgSince, bg)
        val prev = lastBg
        lastBg = bg
        val mins = (nowMs - p.confirmMs) / 60000.0
        // Half a cycle of slack. Cycles do not land on the boundary: the confirm at 14:52:11.459 on
        // 2026-08-27 was followed by a cycle at 15:02:10.934, which is 9.991 minutes, so an exact
        // comparison deferred the decision to the next cycle and released at 15:07 instead. With
        // five-minute cycles that misses roughly half the time, which is not a rare edge case but
        // the normal behaviour of the check.
        if (mins < holdMinutes - HOLD_SLACK_MIN) return 0.0
        if (mins > expiryMinutes) {
            pending = null
            return 0.0
        }
        val slope = if (prev != null) bg - prev else 0.0
        val z = B0 +
            BG_CONFIRM * p.bgAtConfirm +
            RISE_SINCE * (bg - p.bgAtConfirm) +
            MAX_RISE_SINCE * (p.maxBgSince - p.bgAtConfirm) +
            SLOPE_NOW * slope +
            BG_NOW * bg
        val prob = sigmoid(z)
        pending = null
        return if (prob > releaseThreshold) p.heldU else 0.0
    }

    /** The probability the rule would produce right now, for logging without acting. */
    fun probeProbability(bg: Double?): Double? {
        val p = pending ?: return null
        if (bg == null || !bg.isFinite()) return null
        val slope = lastBg?.let { bg - it } ?: 0.0
        return sigmoid(
            B0 + BG_CONFIRM * p.bgAtConfirm + RISE_SINCE * (bg - p.bgAtConfirm) +
                MAX_RISE_SINCE * (max(p.maxBgSince, bg) - p.bgAtConfirm) +
                SLOPE_NOW * slope + BG_NOW * bg
        )
    }

    /**
     * The bounds that apply to a release on this cycle, from outside the controller.
     * @param inMealState     V6's state is CONFIRMED or COMMITTED this cycle
     * @param hardGateFired   a V6 phase-3 hard gate zeroed the dose this cycle
     * @param postRescueWindow inside the post-rescue window (45-min low below the shared threshold)
     * @param ceilingU        the most the release may add this cycle (maxIOB headroom and state cap
     *                        left after the cycle's own dose)
     */
    data class ReleaseBounds(
        val inMealState: Boolean,
        val hardGateFired: Boolean,
        val postRescueWindow: Boolean,
        val ceilingU: Double,
    )

    /** A bounded release: the units to add and a short note for the reason line ("" when unbounded). */
    data class Release(val units: Double, val note: String)

    /**
     * [onCycle] under [bounds]. The hold is dropped, not deferred, when the state has left the meal
     * states, a hard gate fired or the post-rescue window is open: each is the engine deciding against
     * more insulin, and a hold carried past it would be released on evidence that predates it. A
     * release the rule grants is clamped to [ReleaseBounds.ceilingU].
     */
    fun onCycleBounded(nowMs: Long, bg: Double?, bounds: ReleaseBounds): Release {
        if (pending == null) return Release(0.0, "")
        val dropReason = when {
            !bounds.inMealState   -> "state"
            bounds.hardGateFired  -> "hard-gate"
            bounds.postRescueWindow -> "post-rescue"
            else                  -> null
        }
        if (dropReason != null) {
            val held = heldU()
            reset()
            return Release(0.0, "dropped:$dropReason,${roundMilli(held)}")
        }
        val granted = onCycle(nowMs, bg)
        if (granted <= 0.0) return Release(0.0, "")
        val ceiling = max(0.0, bounds.ceilingU)
        return if (granted > ceiling) Release(ceiling, "clamped:${roundMilli(granted)}->${roundMilli(ceiling)}")
        else Release(granted, "")
    }

    private fun roundMilli(x: Double): Double = Math.round(x * 1000.0) / 1000.0

    /** Drops any hold. Used when the engine leaves a meal state entirely. */
    fun reset() {
        pending = null
    }

    init {
        require(holdMinutes > 0 && expiryMinutes > holdMinutes) { "hold window must be positive and ordered" }
        require(min(immediateFraction, releaseThreshold) >= 0.0) { "fraction and threshold must be non-negative" }
    }
}
