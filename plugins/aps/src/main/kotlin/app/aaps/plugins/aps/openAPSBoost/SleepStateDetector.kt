package app.aaps.plugins.aps.openAPSBoost

import app.aaps.core.data.model.HR
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import org.json.JSONArray
import org.json.JSONObject

/**
 * SleepStateDetector — HR + step + clock-driven sleep state estimator for Boost night mode.
 *
 * Three-state machine: AWAKE → PRE_SLEEP → SLEEPING → AWAKE.
 *
 * Design (2026-06-02):
 *
 * Enter PRE_SLEEP (from AWAKE) when:
 *   - clock-of-day ∈ [nightStart − preSleepLeadMin, nightStart)
 *
 *   PRE_SLEEP is a *proactive* state: it engages Boost night-mode SMB suppression BEFORE
 *   the user falls asleep, so they're not carrying excess IOB into the night. No HR or
 *   step gating — this is a time-only pre-warm window.
 *
 * Enter SLEEPING (from PRE_SLEEP or AWAKE, in the ±[SLEEP_SCHEDULE_TOLERANCE_MIN]-early candidate
 * window through nightEnd) when a qualifier holds for ≥ minSleepHysteresisMin — EITHER:
 *   (a) HR-corroborated: avgHr ≤ hrRest × 1.15, stepsLast15Min < 50, mlMealLikely < 0.30/null
 *       (reason "hr"), OR
 *   (b) HR-unreliable fallback: the HR feed is dead OR intermittent (fresh samples < [HR_RELIABLE_MIN_SAMPLES])
 *       and drought is established (≥ droughtThresholdMin, stray samples don't reset it), with the same
 *       step + meal gates — so a degraded overnight feed still reaches SLEEPING on the clock
 *       (reason "drought" if fully dead, "time" if intermittent). 2026-07-08: fixes the stuck-in-PRE_SLEEP
 *       nights where ~1 stray HR sample/15-20min defeated both the old avgHr==null gate and the HR qualifier.
 *
 * Exit SLEEPING (to AWAKE) — BG trend alone NEVER wakes. Any of:
 *   1. Gentle (HR + steps), trusted only within [SLEEP_SCHEDULE_TOLERANCE_MIN] of scheduled wake:
 *      avgHr > hrRest × 1.25 for ≥ [WAKE_HR_SUSTAIN_CYCLES] cycles (REM-proof), AND step evidence
 *      (stepsLast15Min ≥ 100 OR stepsToday growth over [WAKE_STEP_LOOKBACK_MIN] ≥ [WAKE_STEP_THRESHOLD]),
 *      sustained ≥ wakeHrHysteresisMin (reason "hr_steps").
 *   2. Strong steps-alone, ONLY when HR is unreliable (dead/intermittent) so it can't corroborate:
 *      stepsToday growth ≥ [WAKE_STEP_STRONG_THRESHOLD], sustained (reason "steps"). When HR is live,
 *      the gentle rule governs and steps-alone does NOT wake — preserves the both-required guard.
 *   3. clock-of-day exits nightEnd  (hard morning boundary — reason "boundary", excluded from learning).
 *
 * 2026-07-03 incident (why the step evidence is lump-tolerant): the wear step bridge delivers
 * steps in LUMPS, not smooth 15-min increments — the developer was demonstrably awake ~06:00
 * (hrAvg5m 90.2 @05:52, 82–86 through 06:30; wear stepsToday jumped 0 → 1326 by 06:02) yet the
 * detector held SLEEPING until the 07:00 boundary, because the lump predated/straddled the single
 * 15-min bucket and "steps≥100/15min AND HR rise in the same window" never co-fired. Consequences:
 * a 06:02 BG rise to 164 got night-capped dosing for ~1h, and sleepLearnedWakeMin was still NULL
 * after 48 sessions — every wake was boundary-forced, so the wake learner (genuine wakes only, by
 * design) never received a sample. BG alone still NEVER wakes the detector.
 *
 * PRE_SLEEP → AWAKE when clock-of-day exits nightEnd (morning).
 *
 * Failsafes:
 *   - If avgHr is null (no HR data in window), the detector cannot CONFIRM sleep; state
 *     stays AWAKE (or PRE_SLEEP if in time window). Callers should fall back to legacy
 *     time-based night mode.
 *   - State machine is monotonic per-cycle; hysteresis counters carried across calls
 *     via the caller's persistent state struct (see [State]).
 */
object SleepStateDetector {

    /**
     * Discrete sleep state. Persisted across plugin restarts via [serialize]/[deserialize].
     */
    enum class SleepState {
        AWAKE,        // Default state; no sleep behaviour applied
        PRE_SLEEP,    // Within pre-sleep lead window; night-mode SMB rules apply
        SLEEPING      // Sleep confirmed by HR + steps + time + meal-likely gate
    }

    // ── Lump-tolerant genuine-wake constants (2026-07-03 incident — see class KDoc) ──

    /**
     * Trailing lookback (minutes) over which cumulative stepsToday growth counts as wake evidence.
     * Wear-bridge steps arrive in batches that predate/straddle any single 15-min bucket (0 → 1326
     * by 06:02 on 2026-07-03), so the wake test compares stepsToday deltas across a longer window
     * instead of one bucket.
     */
    const val WAKE_STEP_LOOKBACK_MIN = 60

    /**
     * Cumulative stepsToday growth over [WAKE_STEP_LOOKBACK_MIN] required as step evidence for a
     * genuine wake. Must clear nocturnal fidgeting/turn-overs accumulated over the full lookback;
     * validated against 6 nights of the developer's NS telemetry (no false wakes 01:00–05:00).
     */
    const val WAKE_STEP_THRESHOLD = 100

    /**
     * Consecutive evaluate() cycles with avgHr above the wake floor required before wake candidacy
     * may start. A single elevated sample must never count — REM lifts HR without wakefulness.
     */
    const val WAKE_HR_SUSTAIN_CYCLES = 2

    /**
     * Minimum FRESH HR samples within the fresh window for the feed to count as a reliable live
     * transmission. Below this the feed is UNRELIABLE — dead OR intermittent. 2026-07-08 failure:
     * ~1 stray sample per 15-20 min defeated BOTH the HR-value qualifier (avgHr flickered null↔value
     * so the sleep-candidate hysteresis kept resetting) AND the old avgHr==null drought gate (each
     * stray reset the drought clock below threshold), so the detector never reached SLEEPING and sat
     * in PRE_SLEEP to the night-window boundary three nights running. A feed below this floor is
     * treated as drought, and stray samples below it do NOT reset the drought clock.
     */
    const val HR_RELIABLE_MIN_SAMPLES = 3

    /**
     * Cumulative stepsToday growth over [WAKE_STEP_LOOKBACK_MIN] that wakes on STEPS ALONE (no HR
     * corroboration), sustained across wakeHrHysteresisMin. Deliberately HIGH — clear, sustained
     * getting-up movement, not a bathroom trip or nocturnal fidget ([WAKE_STEP_THRESHOLD] is the
     * lower, HR-corroborated bar). 2026-07-08 spec: "steps show clear movement above the sleep
     * threshold" wakes regardless of HR. This is the safety net that catches genuine early rising
     * when the gentle HR+steps rule is time-gated away (and covers the 2026-07-03 over-sleep: the
     * 0→1326 morning step lump clears this easily).
     */
    const val WAKE_STEP_STRONG_THRESHOLD = 250

    /**
     * ±tolerance (minutes) around the scheduled night window for schedule-anchored rules: sleep
     * candidacy may begin up to this long BEFORE nightStart, and the gentle HR+steps wake is trusted
     * only within this long of nightEnd (earlier genuine rising is caught by [WAKE_STEP_STRONG_THRESHOLD]).
     */
    const val SLEEP_SCHEDULE_TOLERANCE_MIN = 90

    /** One (timestamp, cumulative stepsToday) observation for the trailing wake-evidence window. */
    data class StepSample(val tMs: Long, val steps: Int)

    /**
     * Carrier for hysteresis counters and state. Caller stores one instance across cycles
     * and passes it back to [evaluate]. Persist via [serialize] across app restarts.
     *
     * @param state                  Current state
     * @param sleepCandidateSinceMs  When the current PRE_SLEEP→SLEEPING qualification window started
     *                               (null = no current candidacy in progress)
     * @param wakeCandidateSinceMs   When the current SLEEPING→AWAKE qualification window started
     *                               (null = no current wake-candidacy)
     * @param enteredAtMs            When the current state was entered (for telemetry)
     */
    data class State(
        var state: SleepState = SleepState.AWAKE,
        var sleepCandidateSinceMs: Long? = null,
        var wakeCandidateSinceMs: Long? = null,
        var enteredAtMs: Long = 0L,
        // 2026-06-05: drought-based sleep detection for batched-HR platforms (Garmin etc.).
        // Tracks the most recent fresh HR-sample timestamp the detector has observed.
        // Non-zero only after the first fresh sample is seen; persists across cycles so
        // drought duration survives gaps between evaluate() calls.
        var lastFreshHrSampleMs: Long = 0L,
        // 2026-06-06: records which qualifier promoted the current SLEEPING entry.
        // Values: "hr" (HR-value qualifier — avgHr ≤ resting × 1.15), "drought" (no live
        // HR for ≥droughtThresholdMin), null when not in SLEEPING. Emitted to NS for
        // validation that the watch-side sleep-window narrowing is actually working
        // (expect "hr" entries when bookend HR transmission is live; "drought" as fallback).
        var sleepEntryReason: String? = null,
        // 2026-07-03: lump-tolerant wake evidence. Trailing (timestamp, stepsToday) samples over
        // the last WAKE_STEP_LOOKBACK_MIN (+1 anchor just older, so the first in-window increment
        // counts), and the count of consecutive cycles with avgHr above the wake floor.
        var stepSamples: MutableList<StepSample> = mutableListOf(),
        var hrHighStreak: Int = 0
    ) {
        fun serialize(): String =
            JSONObject()
                .put("state", state.name)
                .put("sleepCandidateSinceMs", sleepCandidateSinceMs ?: JSONObject.NULL)
                .put("wakeCandidateSinceMs", wakeCandidateSinceMs ?: JSONObject.NULL)
                .put("enteredAtMs", enteredAtMs)
                .put("lastFreshHrSampleMs", lastFreshHrSampleMs)
                .put("sleepEntryReason", sleepEntryReason ?: JSONObject.NULL)
                .put("stepSamples", JSONArray().also { arr ->
                    for (s in stepSamples) arr.put(JSONArray().put(s.tMs).put(s.steps))
                })
                .put("hrHighStreak", hrHighStreak)
                .toString()

        companion object {
            fun deserialize(raw: String): State {
                if (raw.isBlank()) return State()
                return try {
                    val j = JSONObject(raw)
                    val samples = mutableListOf<StepSample>()
                    j.optJSONArray("stepSamples")?.let { arr ->
                        for (i in 0 until arr.length()) {
                            val p = arr.getJSONArray(i)
                            samples.add(StepSample(p.getLong(0), p.getInt(1)))
                        }
                    }
                    State(
                        state = SleepState.valueOf(j.optString("state", "AWAKE")),
                        sleepCandidateSinceMs = j.optLong("sleepCandidateSinceMs", -1L).takeIf { it > 0 },
                        wakeCandidateSinceMs = j.optLong("wakeCandidateSinceMs", -1L).takeIf { it > 0 },
                        enteredAtMs = j.optLong("enteredAtMs", 0L),
                        lastFreshHrSampleMs = j.optLong("lastFreshHrSampleMs", 0L),
                        sleepEntryReason = j.optString("sleepEntryReason", "").takeIf { it.isNotEmpty() },
                        stepSamples = samples,
                        hrHighStreak = j.optInt("hrHighStreak", 0)
                    )
                } catch (e: Exception) {
                    State()
                }
            }
        }
    }

    /**
     * Result of one evaluation cycle. The returned [newState] should be persisted by the
     * caller and passed back next cycle.
     */
    data class Result(
        val newState: State,
        val transitioned: Boolean,
        val debug: String,
        // Why a SLEEPING→AWAKE transition happened this cycle, else null. Lets the learner train
        // its wake time ONLY on genuine wakes ("hr_steps", "resume") and ignore "boundary" (the
        // hard morning-exit at the night-window end) — otherwise the exit feeds its own learned
        // wake and the window ratchets earlier every night (the 2026-06-25 collapse).
        val wakeReason: String? = null
    )

    /**
     * Inputs from the host plugin. All time-of-day values are minutes-since-midnight (0–1439).
     *
     * @param nowMs                 Current system time in ms (UTC epoch)
     * @param minuteOfDay           Minute-of-day in local time (0..1439)
     * @param hrReadings            Recent HR records (caller fetches; detector filters by window)
     * @param hrWindowMinutes       Minutes of HR history to average for state evaluation (default 5)
     * @param hrResting             User's resting HR (from ApsBoostHrRestingBpm)
     * @param stepsLast15Min        Steps in last 15 min (from StepService)
     * @param mlMealLikely          Optional meal-likelihood score (null if model unavailable)
     * @param nightStartMin         Minute-of-day for night-mode start (e.g. 22:00 → 1320)
     * @param nightEndMin           Minute-of-day for night-mode end (e.g. 07:00 → 420)
     * @param preSleepLeadMin       How early before nightStart to enter PRE_SLEEP (default 60)
     * @param minSleepHysteresisMin Minutes the sleep conditions must hold before SLEEPING (default 10)
     * @param wakeHrHysteresisMin   Minutes HR > 1.25× resting must hold before AWAKE (default 5)
     * @param droughtThresholdMin   Minutes without a fresh HR sample before drought-based sleep
     *                              qualification applies (default 30). When platforms like Garmin
     *                              stop transmitting HR overnight, this lets the detector promote
     *                              PRE_SLEEP → SLEEPING without HR-value confirmation. Set very
     *                              high (e.g. 1440) to disable drought-based promotion.
     * @param freshHrWindowMin      How recent an HR sample's timestamp must be (relative to nowMs)
     *                              to count as "fresh" / live transmission rather than backfilled
     *                              catch-up sync data (default 10).
     * @param stepsToday            Today's CUMULATIVE steps from the best available source (max of
     *                              wear-reconstructed and phone; resets at local midnight). Feeds
     *                              the lump-tolerant trailing wake-evidence window (2026-07-03) —
     *                              the wear bridge delivers steps in batches invisible to the
     *                              phone-bucket [stepsLast15Min]. -1 = unavailable (legacy
     *                              15-min-bucket evidence only).
     */
    data class Inputs(
        val nowMs: Long,
        val minuteOfDay: Int,
        val hrReadings: List<HR>,
        val hrWindowMinutes: Int = 5,
        val hrResting: Int,
        val stepsLast15Min: Int,
        val mlMealLikely: Double?,
        val nightStartMin: Int,
        val nightEndMin: Int,
        val preSleepLeadMin: Int = 60,
        val minSleepHysteresisMin: Int = 10,
        val wakeHrHysteresisMin: Int = 5,
        val droughtThresholdMin: Int = 30,
        val freshHrWindowMin: Int = 10,
        val stepsToday: Int = -1,
        // 2026-07-08 sleep-in merge: the unified lie-in threshold + window that folds the former
        // standalone StepFeed.sleepInActive backstop INTO this state machine. When sleepInWindowMin > 0,
        // SLEEPING is held past nightEnd for this many minutes as a "lie-in" and released early once
        // stepsToday growth over the wake lookback clears sleepInStepsThreshold (the user's
        // ApsBoostSleepInSteps). 0 = disabled (legacy nightEnd hard-exit; strong-steps uses the constant).
        val sleepInStepsThreshold: Int = 0,
        val sleepInWindowMin: Int = 0
    )

    /**
     * Evaluate the state machine for the current cycle. Pure function over [prev] and [inputs].
     * Caller persists [Result.newState] and passes it as [prev] next cycle.
     */
    fun evaluate(prev: State, inputs: Inputs, aapsLogger: AAPSLogger? = null): Result {
        val debug = StringBuilder()
        val avgHr = averageHr(inputs.hrReadings, inputs.nowMs, inputs.hrWindowMinutes)
        val sleepCap = inputs.hrResting * 1.15
        val wakeFloor = inputs.hrResting * 1.25
        val inOuterWindow = minuteInWrappedRange(inputs.minuteOfDay, inputs.nightStartMin, inputs.nightEndMin)
        val preSleepStart = (inputs.nightStartMin - inputs.preSleepLeadMin + 1440) % 1440
        val inPreSleep = minuteInWrappedRange(inputs.minuteOfDay, preSleepStart, inputs.nightStartMin)
        // 2026-07-08 spec: sleep candidacy is allowed ±SLEEP_SCHEDULE_TOLERANCE_MIN early (before
        // nightStart) through nightEnd — an unusually-early onset up to 90 min pre-nightStart is
        // detected promptly regardless of the (SMB-pre-warm) preSleepLead. And the gentle HR+steps
        // wake is trusted only within SLEEP_SCHEDULE_TOLERANCE_MIN of nightEnd.
        val sleepCandStart = (inputs.nightStartMin - SLEEP_SCHEDULE_TOLERANCE_MIN + 1440) % 1440
        val inSleepCandidateWindow = minuteInWrappedRange(inputs.minuteOfDay, sleepCandStart, inputs.nightEndMin)
        val wakeGraceStart = (inputs.nightEndMin - SLEEP_SCHEDULE_TOLERANCE_MIN + 1440) % 1440
        val nearScheduledWake = minuteInWrappedRange(inputs.minuteOfDay, wakeGraceStart, inputs.nightEndMin)
        // 2026-07-08 sleep-in merge: SLEEPING is HELD past nightEnd through the lie-in window
        // [nightEnd, nightEnd + sleepInWindowMin] (the merged StepFeed.sleepInActive), so the hard
        // boundary exit moves from nightEnd to lieInEnd. Sleep candidacy still anchors to nightEnd
        // (never START a new sleep during the morning lie-in).
        val lieInEnd = if (inputs.sleepInWindowMin > 0)
            (inputs.nightEndMin + inputs.sleepInWindowMin) % 1440 else inputs.nightEndMin
        val inHoldWindow = minuteInWrappedRange(inputs.minuteOfDay, inputs.nightStartMin, lieInEnd)
        val inLieIn = inputs.sleepInWindowMin > 0 &&
            minuteInWrappedRange(inputs.minuteOfDay, inputs.nightEndMin, lieInEnd)

        // deep-copy the step-sample list so evaluate() stays pure over prev (data-class copy is shallow)
        var newState = prev.copy(stepSamples = prev.stepSamples.toMutableList())
        var transitioned = false
        var wakeReason: String? = null

        // 2026-06-05: drought-based sleep + transmission-resumed wake signals.
        // Compute the most recent fresh HR sample (timestamp within last freshHrWindowMin
        // of nowMs — distinguishes live transmission from backfilled catch-up sync data),
        // then derive drought duration and a count of fresh samples for wake detection.
        val freshCutoff = inputs.nowMs - inputs.freshHrWindowMin * 60_000L
        val fifteenMinCutoff = inputs.nowMs - 15 * 60_000L
        val freshInWindow = inputs.hrReadings.filter {
            it.isValid && it.timestamp in (freshCutoff + 1)..inputs.nowMs
        }
        val mostRecentFreshTs = freshInWindow.maxOfOrNull { it.timestamp } ?: 0L
        val freshSamplesInLast15Min = freshInWindow.count { it.timestamp >= fifteenMinCutoff }
        // 2026-07-08: only a RELIABLE live feed (≥HR_RELIABLE_MIN_SAMPLES fresh) resets the drought
        // clock. A lone stray sample every 15-20 min must NOT reset it — that intermittency is what
        // kept droughtMinutes below threshold all night and left the detector stuck in PRE_SLEEP.
        val hrTransmitting = freshSamplesInLast15Min >= HR_RELIABLE_MIN_SAMPLES
        if (mostRecentFreshTs > newState.lastFreshHrSampleMs && hrTransmitting) {
            newState.lastFreshHrSampleMs = mostRecentFreshTs
        }
        val droughtMinutes = if (newState.lastFreshHrSampleMs > 0)
            ((inputs.nowMs - newState.lastFreshHrSampleMs) / 60_000L).toInt()
        else
            Int.MAX_VALUE  // never seen a fresh sample → treat as fully in drought
        val droughtEstablished = droughtMinutes >= inputs.droughtThresholdMin

        // 2026-07-03 lump-tolerant wake evidence: record (nowMs, stepsToday) each cycle and derive
        // cumulative growth over the trailing lookback (sum of positive inter-sample increments, so
        // the local-midnight stepsToday reset never yields negative/false deltas). HR sustain streak:
        // consecutive cycles with avgHr above the wake floor; any miss (null or low) resets it.
        if (inputs.stepsToday >= 0) recordStepSample(newState.stepSamples, inputs.nowMs, inputs.stepsToday)
        val stepsInLookback = stepGrowth(newState.stepSamples, inputs.nowMs, WAKE_STEP_LOOKBACK_MIN)
        // Unified strong-steps wake threshold (the user's ApsBoostSleepInSteps; constant fallback when the
        // merge is off). Hoisted here so BOTH the PRE_SLEEP activity-escape and the SLEEPING steps-alone
        // wake read the one value.
        val strongStepsThreshold =
            if (inputs.sleepInStepsThreshold > 0) inputs.sleepInStepsThreshold else WAKE_STEP_STRONG_THRESHOLD
        newState.hrHighStreak = if (avgHr != null && avgHr > wakeFloor) newState.hrHighStreak + 1 else 0

        debug.append("avgHr=${avgHr?.let { String.format("%.1f", it) } ?: "null"}")
            .append(" sleepCap=${String.format("%.1f", sleepCap)}")
            .append(" wakeFloor=${String.format("%.1f", wakeFloor)}")
            .append(" steps15=${inputs.stepsLast15Min}")
            .append(" mealLikely=${inputs.mlMealLikely?.let { String.format("%.2f", it) } ?: "null"}")
            .append(" minOfDay=${inputs.minuteOfDay}")
            .append(" inOuter=$inOuterWindow inPreSleep=$inPreSleep")
            .append(" drought=${if (droughtMinutes == Int.MAX_VALUE) "∞" else "${droughtMinutes}m"}")
            .append(" freshN15=$freshSamplesInLast15Min")
            .append(" stepsLB=$stepsInLookback hrStreak=${newState.hrHighStreak}")

        // 2026-06-05 / 2026-07-08: drought-qualified candidacy. When the HR feed is UNRELIABLE
        // (dead OR intermittent — freshSamplesInLast15Min below the reliable floor) AND drought is
        // established AND steps + meal gates pass, treat as a sleep candidate. Lets the detector
        // reach SLEEPING on batched-HR platforms (Garmin) where the watch stops transmitting
        // overnight — and on a degraded Wear feed that dribbles one stray sample every 15-20 min
        // (the 2026-07-08 stuck-in-PRE_SLEEP failure: the old avgHr==null gate never fired because
        // the stray samples kept avgHr non-null and reset the drought clock).
        val hrUnreliable = freshSamplesInLast15Min < HR_RELIABLE_MIN_SAMPLES
        val droughtQualifies = hrUnreliable && droughtEstablished &&
            inputs.stepsLast15Min < 50 &&
            (inputs.mlMealLikely == null || inputs.mlMealLikely < 0.30)
        val hrQualifies = qualifiesAsSleepCandidate(avgHr, sleepCap, inputs.stepsLast15Min, inputs.mlMealLikely)
        val anyQualifies = hrQualifies || droughtQualifies

        // Transmission-resume wake: was in drought before this cycle, now a burst of
        // fresh samples just arrived. Distinguishes "user picked up phone / watch synced"
        // from a single stray sample mid-night. Requires the burst to follow an actual
        // drought (priorDroughtMinutes >= threshold), preventing false wakes from
        // ordinary daytime intermittency.
        val priorDroughtMinutes = if (prev.lastFreshHrSampleMs > 0)
            ((inputs.nowMs - prev.lastFreshHrSampleMs) / 60_000L).toInt()
        else
            Int.MAX_VALUE
        val transmissionResumeWake = freshSamplesInLast15Min >= 3 &&
            priorDroughtMinutes >= inputs.droughtThresholdMin

        when (prev.state) {
            SleepState.AWAKE -> {
                // Sleep candidacy check — possible from AWAKE anywhere in the ±90-early candidate
                // window (so an unusually-early sleep onset up to SLEEP_SCHEDULE_TOLERANCE_MIN before
                // nightStart is detected promptly, independent of the PRE_SLEEP SMB-pre-warm lead).
                if (inSleepCandidateWindow && anyQualifies) {
                    if (newState.sleepCandidateSinceMs == null) {
                        newState.sleepCandidateSinceMs = inputs.nowMs
                        debug.append(" | sleep-candidate-started${if (droughtQualifies && !hrQualifies) " (drought)" else ""}")
                    } else {
                        val heldMin = ((inputs.nowMs - newState.sleepCandidateSinceMs!!) / 60_000L).toInt()
                        if (heldMin >= inputs.minSleepHysteresisMin) {
                            newState = State(state = SleepState.SLEEPING, enteredAtMs = inputs.nowMs,
                                             lastFreshHrSampleMs = newState.lastFreshHrSampleMs,
                                             sleepEntryReason = when { hrQualifies -> "hr"; avgHr == null -> "drought"; else -> "time" },
                                             stepSamples = newState.stepSamples, hrHighStreak = newState.hrHighStreak)
                            transitioned = true
                            debug.append(" | →SLEEPING (held ${heldMin}m${if (droughtQualifies && !hrQualifies) " — drought" else ""})")
                        } else {
                            debug.append(" | sleep-candidate-held=${heldMin}m")
                        }
                    }
                } else {
                    if (newState.sleepCandidateSinceMs != null) debug.append(" | sleep-candidate-reset")
                    newState.sleepCandidateSinceMs = null
                }

                if (!transitioned && inPreSleep) {
                    newState = State(state = SleepState.PRE_SLEEP, enteredAtMs = inputs.nowMs,
                                     lastFreshHrSampleMs = newState.lastFreshHrSampleMs,
                                     stepSamples = newState.stepSamples, hrHighStreak = newState.hrHighStreak)
                    transitioned = true
                    debug.append(" | →PRE_SLEEP (time)")
                }
            }

            SleepState.PRE_SLEEP -> {
                // Clear sustained activity releases PRE_SLEEP → AWAKE immediately, ANY time of night —
                // never suppress dosing while the user is demonstrably up. Uses the same 60-min cumulative
                // step growth vs the user's ApsBoostSleepInSteps threshold as the SLEEPING steps-alone wake,
                // but UNGATED by clock/drought (PRE_SLEEP is not confirmed sleep, so activity is decisive).
                // Fixes the 05:00 "up + BG rising but stuck PRE_SLEEP to the boundary" trap. NOT a genuine
                // sleep→wake, so wakeReason stays null (does not train the wake learner).
                if (stepsInLookback >= strongStepsThreshold) {
                    newState = State(state = SleepState.AWAKE, enteredAtMs = inputs.nowMs,
                                     lastFreshHrSampleMs = newState.lastFreshHrSampleMs,
                                     stepSamples = newState.stepSamples, hrHighStreak = newState.hrHighStreak)
                    transitioned = true
                    debug.append(" | →AWAKE (activity ${stepsInLookback} steps/${WAKE_STEP_LOOKBACK_MIN}m ≥ $strongStepsThreshold)")
                }
                // Exit PRE_SLEEP if we've left the outer night window (morning exit before ever sleeping)
                else if (!inOuterWindow && !inPreSleep) {
                    newState = State(state = SleepState.AWAKE, enteredAtMs = inputs.nowMs,
                                     lastFreshHrSampleMs = newState.lastFreshHrSampleMs,
                                     stepSamples = newState.stepSamples, hrHighStreak = newState.hrHighStreak)
                    transitioned = true
                    debug.append(" | →AWAKE (left window without sleeping)")
                } else if (anyQualifies) {
                    if (newState.sleepCandidateSinceMs == null) {
                        newState.sleepCandidateSinceMs = inputs.nowMs
                        debug.append(" | sleep-candidate-started${if (droughtQualifies && !hrQualifies) " (drought)" else ""}")
                    } else {
                        val heldMin = ((inputs.nowMs - newState.sleepCandidateSinceMs!!) / 60_000L).toInt()
                        if (heldMin >= inputs.minSleepHysteresisMin) {
                            newState = State(state = SleepState.SLEEPING, enteredAtMs = inputs.nowMs,
                                             lastFreshHrSampleMs = newState.lastFreshHrSampleMs,
                                             sleepEntryReason = when { hrQualifies -> "hr"; avgHr == null -> "drought"; else -> "time" },
                                             stepSamples = newState.stepSamples, hrHighStreak = newState.hrHighStreak)
                            transitioned = true
                            debug.append(" | →SLEEPING (held ${heldMin}m${if (droughtQualifies && !hrQualifies) " — drought" else ""})")
                        } else {
                            debug.append(" | sleep-candidate-held=${heldMin}m")
                        }
                    }
                } else {
                    if (newState.sleepCandidateSinceMs != null) debug.append(" | sleep-candidate-reset")
                    newState.sleepCandidateSinceMs = null
                }
            }

            SleepState.SLEEPING -> {
                // Hard morning exit — at the END of the lie-in hold window (nightEnd + sleepInWindowMin;
                // == nightEnd when the sleep-in merge is disabled). The lie-in keeps SLEEPING past the
                // scheduled wake until steps confirm the user is genuinely up (see strongStepsWake).
                if (!inHoldWindow) {
                    newState = State(state = SleepState.AWAKE, enteredAtMs = inputs.nowMs,
                                     lastFreshHrSampleMs = newState.lastFreshHrSampleMs,
                                     stepSamples = newState.stepSamples, hrHighStreak = newState.hrHighStreak)
                    transitioned = true
                    wakeReason = "boundary"   // hard night-window exit — NOT a genuine wake; excluded from learning
                    debug.append(" | →AWAKE (outer window exit)")
                } else if (transmissionResumeWake) {
                    // Sync burst arrived after drought → user just resumed phone interaction.
                    // No hysteresis: the burst itself contains multiple samples in one cycle
                    // and is strongly correlated with wake on batched-HR platforms.
                    newState = State(state = SleepState.AWAKE, enteredAtMs = inputs.nowMs,
                                     lastFreshHrSampleMs = newState.lastFreshHrSampleMs,
                                     stepSamples = newState.stepSamples, hrHighStreak = newState.hrHighStreak)
                    transitioned = true
                    wakeReason = "resume"   // genuine wake signal
                    debug.append(" | →AWAKE (transmission resumed — ${freshSamplesInLast15Min} fresh after ${priorDroughtMinutes}m drought)")
                } else {
                    // Two wake rules (2026-07-08 spec), both lump-tolerant + hysteresis-sustained;
                    // BG trend alone still NEVER wakes.
                    //  Rule 1 (gentle): HR-rise + steps, trusted ONLY within SLEEP_SCHEDULE_TOLERANCE_MIN
                    //    of scheduled wake. HR evidence is SUSTAINED (≥WAKE_HR_SUSTAIN_CYCLES cycles above
                    //    the wake floor — a single sample never counts, REM lifts HR). Earlier HR rises
                    //    are REM/restlessness, so the gentle rule is time-gated near nightEnd.
                    //  Rule 2 (strong steps-alone): clear sustained getting-up movement wakes WITHOUT HR,
                    //    at the UNIFIED sleep-in threshold (sleepInStepsThreshold — the user's
                    //    ApsBoostSleepInSteps; falls back to WAKE_STEP_STRONG_THRESHOLD when the merge is
                    //    off). It fires EITHER when HR can't corroborate (drought established — dead/
                    //    intermittent, any time in the night) OR anywhere in the lie-in past nightEnd
                    //    (the merged sleep-in release: past the alarm, movement means up regardless of HR).
                    //    When HR is live and it is still the core night, the gentle rule governs and
                    //    steps-alone does NOT wake (preserves the both-required guard).
                    val stepsConfirmWake = inputs.stepsLast15Min >= 100 || stepsInLookback >= WAKE_STEP_THRESHOLD
                    val hrAboveWakeFloor = avgHr != null && avgHr > wakeFloor &&
                        newState.hrHighStreak >= WAKE_HR_SUSTAIN_CYCLES
                    val gentleWake = stepsConfirmWake && hrAboveWakeFloor && nearScheduledWake
                    val strongStepsWake = stepsInLookback >= strongStepsThreshold && (droughtEstablished || inLieIn)
                    if (gentleWake || strongStepsWake) {
                        if (newState.wakeCandidateSinceMs == null) {
                            newState.wakeCandidateSinceMs = inputs.nowMs
                            debug.append(" | wake-candidate-started")
                        } else {
                            val heldMin = ((inputs.nowMs - newState.wakeCandidateSinceMs!!) / 60_000L).toInt()
                            if (heldMin >= inputs.wakeHrHysteresisMin) {
                                newState = State(state = SleepState.AWAKE, enteredAtMs = inputs.nowMs,
                                                 lastFreshHrSampleMs = newState.lastFreshHrSampleMs)
                                transitioned = true
                                wakeReason = if (gentleWake) "hr_steps" else "steps"   // both genuine wakes
                                debug.append(" | →AWAKE (held ${heldMin}m — ${if (gentleWake) "HR+steps" else "steps-only (HR unreliable)"})")
                            } else {
                                debug.append(" | wake-candidate-held=${heldMin}m")
                            }
                        }
                    } else {
                        if (newState.wakeCandidateSinceMs != null) debug.append(" | wake-candidate-reset")
                        newState.wakeCandidateSinceMs = null
                    }
                }
            }
        }

        aapsLogger?.debug(LTag.APS, "SleepStateDetector: ${newState.state} ${if (transitioned) "[T]" else "" } $debug")
        return Result(newState, transitioned, debug.toString(), wakeReason)
    }

    /**
     * Append the current cumulative-stepsToday observation and prune samples older than
     * [WAKE_STEP_LOOKBACK_MIN], keeping ONE just-older anchor so the first in-window increment
     * still counts. Bounded to ~lookback/cycle-interval entries.
     */
    private fun recordStepSample(samples: MutableList<StepSample>, nowMs: Long, stepsToday: Int) {
        samples.add(StepSample(nowMs, stepsToday))
        val cutoff = nowMs - WAKE_STEP_LOOKBACK_MIN * 60_000L
        while (samples.size >= 2 && samples[1].tMs <= cutoff) samples.removeAt(0)
    }

    /**
     * Cumulative POSITIVE stepsToday growth across the trailing [lookbackMin]: sum of positive
     * increments between consecutive samples ending inside the window. Negative jumps (the local-
     * midnight stepsToday reset, a step-source switch) contribute 0 — they are not movement.
     */
    internal fun stepGrowth(samples: List<StepSample>, nowMs: Long, lookbackMin: Int): Int {
        val cutoff = nowMs - lookbackMin * 60_000L
        var sum = 0
        for (i in 1 until samples.size) {
            if (samples[i].tMs <= cutoff) continue
            sum += (samples[i].steps - samples[i - 1].steps).coerceAtLeast(0)
        }
        return sum
    }

    /** Duration-weighted average HR over a window. null if no readings. */
    fun averageHr(readings: List<HR>, nowMs: Long, windowMinutes: Int): Double? {
        val cutoff = nowMs - windowMinutes * 60_000L
        val inWindow = readings.filter { it.isValid && it.timestamp in (cutoff + 1)..nowMs }
        if (inWindow.isEmpty()) return null
        val totalDur = inWindow.sumOf { it.duration.toDouble() }
        if (totalDur <= 0.0) return null
        return inWindow.sumOf { it.beatsPerMinute * it.duration } / totalDur
    }

    /**
     * Returns true if `minute` lies within the [start, end] window on a 24-hour clock,
     * handling wrap-around (e.g. start=1320 (22:00), end=420 (07:00)).
     */
    private fun minuteInWrappedRange(minute: Int, start: Int, end: Int): Boolean {
        if (start == end) return false
        return if (end > start) minute in start until end
        else minute >= start || minute < end
    }

    private fun qualifiesAsSleepCandidate(
        avgHr: Double?,
        sleepCap: Double,
        stepsLast15Min: Int,
        mlMealLikely: Double?
    ): Boolean {
        if (avgHr == null) return false                              // no HR → can't confirm
        if (avgHr > sleepCap) return false                           // HR too high
        if (stepsLast15Min >= 50) return false                       // recent activity
        if (mlMealLikely != null && mlMealLikely >= 0.30) return false  // about to eat
        return true
    }
}
