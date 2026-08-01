package app.aaps.plugins.aps.openAPSBoostTwin

/**
 * Retractable anticipation arm — the generic state machine behind both anticipation levers
 * (exercise pre-reduce, meal move-earlier). SHADOW: it decides WHETHER it would arm / confirm /
 * back out; it never doses. This is the "retractability is the safety mechanism, not accuracy"
 * principle in one small, pure, testable unit (see ANTICIPATION_ARCHITECTURE_SPEC.md).
 *
 * IDLE → (armCond) → ARMED → { confirmCond → CONFIRMED(hold); vetoCond → back out; deadline → back
 * out }. `armCond` is the per-user predictor firing above threshold AND population/context-eligible;
 * `confirmCond` is the anticipated event actually appearing (exercise: activity shows; meal: BG
 * rises / Twin Ra rises); `vetoCond` is an early safety trip (e.g. already heading low, or in the
 * post-rescue window — the arming bug that over-fired the earlier shadow).
 */
class RetractableArm(private val deadlineMin: Double = 40.0) {

    enum class St { IDLE, ARMED }

    private var st = St.IDLE
    private var armedAtMs = 0L

    /** One cycle. Returns the compact outcome for this cycle (state + edge flags). */
    data class Out(val state: St, val armed: Int, val confirmed: Int, val backedOut: Int, val ageMin: Double)

    fun runCycle(nowMs: Long, armCond: Boolean, confirmCond: Boolean, vetoCond: Boolean): Out {
        var armed = 0; var confirmed = 0; var backedOut = 0
        when (st) {
            St.IDLE ->
                if (armCond && !vetoCond) { st = St.ARMED; armedAtMs = nowMs; armed = 1 }
            St.ARMED -> {
                val age = (nowMs - armedAtMs) / 60_000.0
                when {
                    confirmCond        -> { confirmed = 1; st = St.IDLE }   // event real → hold the action, hand off
                    vetoCond           -> { backedOut = 1; st = St.IDLE }   // early safety trip → unwind
                    age >= deadlineMin -> { backedOut = 1; st = St.IDLE }   // deadline without the event → unwind
                }
            }
        }
        val age = if (st == St.ARMED) (nowMs - armedAtMs) / 60_000.0 else 0.0
        return Out(st, armed, confirmed, backedOut, age)
    }

    val isArmed get() = st == St.ARMED
}
