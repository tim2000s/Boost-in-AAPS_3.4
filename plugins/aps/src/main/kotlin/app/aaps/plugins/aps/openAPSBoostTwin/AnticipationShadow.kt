package app.aaps.plugins.aps.openAPSBoostTwin

import app.aaps.plugins.aps.openAPSBoostTwin.AnticipationHabitModel.Companion.defaultExercisePrior
import app.aaps.plugins.aps.openAPSBoostTwin.AnticipationHabitModel.Companion.defaultMealPrior

/**
 * KAIROS — per-user anticipation SHADOW orchestrator (2026-07-27). READ-ONLY: it records onsets,
 * refits the per-user habit models offline (~6-hourly), predicts p(exercise)/p(meal) at a 45-min
 * lead, and runs the two retractable arms in shadow. It appends an `anticip=` reason tag and
 * DELIVERS NOTHING. Lives in the shared Boost engine (OpenAPSBoostPlugin.runEngine), so it runs
 * identically for plain Boost, V5/V6, and the V7-shadow line — one instrument, both engines.
 *
 * Phase 1+2 of ANTICIPATION_ARCHITECTURE_SPEC.md: the predictor + arming, banking the data the
 * per-user pricing (Phase 3) and the within-user trial (Phase 4) will need. Population gating
 * (Component C) and live action (Component D) are deliberately NOT enforced here — the tag logs
 * the raw material so eligibility is decided offline against real outcomes.
 *
 * @param weekMinuteOf converts an epoch (ms) to a LOCAL week-minute (Mon 00:00 = 0). Injected so the
 *   habit model stays pure and timezone-free; the plugin supplies a java.time systemDefault mapper.
 */
class AnticipationShadow(
    private val loadState: () -> String,
    private val saveState: (String) -> Unit,
    private val logError: (String, Throwable) -> Unit,
    private val weekMinuteOf: (Long) -> Int,
) {

    companion object {
        const val REFIT_INTERVAL_MS = 6L * 3_600_000L   // refit the tables ~4×/day (offline-style)
        const val STEP_ONSET_5MIN = 150                 // steps/5min that counts as a bout (edge-detected)
        const val ARM_THRESHOLD_EX = 0.35               // shadow arm thresholds — generous, tuned offline
        const val ARM_THRESHOLD_MEAL = 0.35
    }

    private val exModel = AnticipationHabitModel()
    private val mealModel = AnticipationHabitModel()
    private val exArm = RetractableArm()
    private val mealArm = RetractableArm()
    private val exPrior = defaultExercisePrior()
    private val mealPrior = defaultMealPrior()

    @Volatile private var store: AnticipationOnsetStore? = null
    @Volatile private var exFit: AnticipationHabitModel.Fitted? = null
    @Volatile private var mealFit: AnticipationHabitModel.Fitted? = null
    private var lastFitMs = 0L
    private var wasExercising = false
    private var prevMealState: String? = null

    /**
     * One engine cycle. Records onsets, refits when due, predicts, runs the shadow arms, and
     * appends `anticip=...;`. Belt-and-braces: never throws (mirrors the other shadows).
     */
    fun runCycle(
        reason: StringBuilder,
        nowMs: Long,
        steps5Min: Int,
        mealStateName: String?,
        bg: Double,
        delta: Double,
        inPostRescueWindow: Boolean,
    ) {
        try {
            val st = store ?: AnticipationOnsetStore.deserialize(runCatching { loadState() }.getOrNull())
                .also { store = it }

            // 1. Onset detection (in-memory edge; a missed onset across a restart is harmless).
            val exercisingNow = steps5Min > STEP_ONSET_5MIN
            if (exercisingNow && !wasExercising) st.record(AnticipationOnsetStore.Kind.EXERCISE, nowMs)
            wasExercising = exercisingNow
            val mealConfirmNow = mealStateName == "CONFIRMED"
            if (mealConfirmNow && prevMealState != "CONFIRMED") st.record(AnticipationOnsetStore.Kind.MEAL, nowMs)
            prevMealState = mealStateName
            st.evict(nowMs)
            runCatching { saveState(st.serialize()) }.onFailure { t -> logError("Anticip persist failed", t) }

            // 2. Refit the per-user tables when due (or on first cycle / after restart).
            if (exFit == null || mealFit == null || nowMs - lastFitMs >= REFIT_INTERVAL_MS) {
                exFit = fitFrom(st, AnticipationOnsetStore.Kind.EXERCISE, nowMs, exPrior, exModel)
                mealFit = fitFrom(st, AnticipationOnsetStore.Kind.MEAL, nowMs, mealPrior, mealModel)
                lastFitMs = nowMs
            }

            // 3. Predict at a 45-min lead.
            val wmNow = weekMinuteOf(nowMs)
            val pEx = exModel.predict(exFit, wmNow, st.minsSinceLast(AnticipationOnsetStore.Kind.EXERCISE, nowMs))
            val pMeal = mealModel.predict(mealFit, wmNow, st.minsSinceLast(AnticipationOnsetStore.Kind.MEAL, nowMs))

            // 4. Shadow arms. Context gates: never arm inside the post-rescue window (the earlier
            //    shadow's over-arm bug). Exercise confirm = activity appears; meal confirm = a rise.
            val exOut = exArm.runCycle(
                nowMs,
                armCond = (pEx ?: 0.0) >= ARM_THRESHOLD_EX && !inPostRescueWindow,
                confirmCond = exercisingNow,
                vetoCond = inPostRescueWindow,
            )
            val mealOut = mealArm.runCycle(
                nowMs,
                armCond = (pMeal ?: 0.0) >= ARM_THRESHOLD_MEAL && !inPostRescueWindow && prevMealState != "CONFIRMED",
                confirmCond = mealConfirmNow || delta > 5.0,
                vetoCond = inPostRescueWindow,
            )

            // 5. Emit. Fields: pEx,pMeal,srcEx,srcMeal | exArm,exConf,exBO | mealArm,mealConf,mealBO |
            //    minsSinceEx,minsSinceMeal,nEx,nMeal
            reason.append(
                "anticip=${f(pEx)},${f(pMeal)},${exFit?.source ?: "-"},${mealFit?.source ?: "-"}," +
                    "${exOut.armed},${exOut.confirmed},${exOut.backedOut}," +
                    "${mealOut.armed},${mealOut.confirmed},${mealOut.backedOut}," +
                    "${st.minsSinceLast(AnticipationOnsetStore.Kind.EXERCISE, nowMs).toInt()}," +
                    "${st.minsSinceLast(AnticipationOnsetStore.Kind.MEAL, nowMs).toInt()}," +
                    "${st.count(AnticipationOnsetStore.Kind.EXERCISE)},${st.count(AnticipationOnsetStore.Kind.MEAL)}; "
            )
        } catch (t: Throwable) {
            logError("Anticipation shadow failed (swallowed — dosing untouched)", t)
        }
    }

    private fun fitFrom(
        st: AnticipationOnsetStore, kind: AnticipationOnsetStore.Kind, nowMs: Long,
        prior: DoubleArray, model: AnticipationHabitModel,
    ): AnticipationHabitModel.Fitted {
        val epochs = st.epochsMs(kind)
        val wm = IntArray(epochs.size) { weekMinuteOf(epochs[it]) }
        val ages = DoubleArray(epochs.size) { (nowMs - epochs[it]).coerceAtLeast(0L) / 86_400_000.0 }
        val historyDays = if (epochs.isEmpty()) 1.0 else ((nowMs - epochs.first()).coerceAtLeast(0L) / 86_400_000.0).coerceAtLeast(1.0)
        return model.fit(wm, ages, historyDays, prior)
    }

    private fun f(v: Double?) = if (v == null) "-" else (Math.round(v * 1000.0) / 1000.0).toString()
}
