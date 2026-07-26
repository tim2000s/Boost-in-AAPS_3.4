package app.aaps.plugins.aps.openAPSBoostV5

import kotlin.math.max
import kotlin.math.min

// Scenario driver for the REAL MealHypothesis state machine (compiled from plugins/aps source).
// Question: after CONFIRMED, if deltas keep ACCELERATING, does the engine issue a second confirm?
// We drive step() cycle-by-cycle over a synthetic "accelerating straight through the confirm" meal.

data class Cycle(
    val bg: Int, val delta: Double, val accl: Double, val score: Double,
    val eventualBg: Double, val target: Double = 100.0
)

fun run(name: String, cycles: List<Cycle>, fastEnabled: Boolean = false) {
    println("\n=== $name ===")
    println("min | BG  | delta | accl  | score | evBG | -> STATE (age, committedInSession)  [confirm-fires]")
    var st = MealHypothesisState()
    val deltaHist = mutableListOf<Double>()
    var prevScore = 0.0
    var t = 0
    var confirmCount = 0
    for (c in cycles) {
        deltaHist.add(c.delta)
        val declining = deltaDeclining(deltaHist, 2)
        val scoreReadyStreak = prevScore >= CONFIRM_SCORE
        val before = st.state
        st = step(
            current = st, score = c.score, eventualBg = c.eventualBg, targetBg = c.target,
            delta = c.delta, deltaAccl = c.accl, deltaDeclining = declining,
            asleep = false, exerciseActive = false, fastConfirmEnabled = fastEnabled,
            confirmDoseAdequate = true, scoreReadyStreak = scoreReadyStreak,
            aggressiveEarlyConfirm = false,
        )
        val fired = if (st.state == MealHypothesis.CONFIRMED && before != MealHypothesis.CONFIRMED) {
            confirmCount++; "  <-- CONFIRM #$confirmCount FIRES"
        } else ""
        println("%3d | %3d | %+5.1f | %+5.1f | %.2f  | %4.0f | -> %-10s (age=%d, cis=%s)%s".format(
            t, c.bg, c.delta, c.accl, c.score, c.eventualBg,
            st.state, st.ageCycles, st.committedInSession, fired))
        prevScore = c.score
        t += 5
    }
    println("TOTAL confirm-shots fired: $confirmCount")
}

fun main() {
    // Scenario A: a meal that CONFIRMS, then keeps ACCELERATING hard (delta & accl both rising)
    // straight through — never decelerates. This is Tim's exact case.
    run("A: accelerate straight through the confirm (delta & accl keep climbing)", listOf(
        Cycle(105,  2.0,  1.0, 0.30, 120.0),  // IDLE->OBSERVING (score>0.44? no, 0.30 -> stays IDLE)
        Cycle(110,  5.0,  8.0, 0.50, 135.0),  // enter OBSERVING
        Cycle(118,  8.0, 12.0, 0.60, 155.0),  // OBSERVING age1
        Cycle(128, 10.0, 14.0, 0.66, 175.0),  // OBSERVING age2 -> eligible -> CONFIRMED
        Cycle(140, 12.0, 16.0, 0.68, 195.0),  // CONFIRMED -> COMMITTED (still accelerating)
        Cycle(154, 14.0, 18.0, 0.70, 215.0),  // COMMITTED, accl still climbing
        Cycle(170, 16.0, 20.0, 0.72, 235.0),  // COMMITTED, accl still climbing
        Cycle(188, 18.0, 22.0, 0.74, 255.0),  // COMMITTED, accl still climbing
    ))

    // Scenario B: two-phase meal (rise -> decel -> RE-accelerate) — the Fix-7 re-engage case,
    // to contrast: here the re-escalation IS allowed, but as COMMITTED (1.0x), not a 2nd CONFIRMED.
    run("B: rise -> decelerate -> re-accelerate (two-phase / Fix-7)", listOf(
        Cycle(110,  5.0,  8.0, 0.50, 135.0),  // OBSERVING
        Cycle(118,  8.0, 12.0, 0.60, 155.0),
        Cycle(128, 10.0, 14.0, 0.66, 175.0),  // CONFIRMED
        Cycle(138, 10.0,  2.0, 0.66, 190.0),  // COMMITTED
        Cycle(143,  5.0, -8.0, 0.55, 185.0),  // decel -> RECOVERING (accl<-5 & declining)
        Cycle(145,  2.0, -6.0, 0.45, 178.0),  // RECOVERING
        Cycle(152,  7.0, 14.0, 0.55, 195.0),  // RE-accelerate -> re-engage COMMITTED (not CONFIRMED)
        Cycle(162, 10.0, 16.0, 0.58, 210.0),
    ))
}
