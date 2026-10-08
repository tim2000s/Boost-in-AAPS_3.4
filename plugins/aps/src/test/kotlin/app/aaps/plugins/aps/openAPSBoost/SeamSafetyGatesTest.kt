package app.aaps.plugins.aps.openAPSBoost

import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.PrimerTbrAction
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.boostGateOpen
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.boundaryExitHoldMin
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.effectiveBaseTempRate
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.mealSessionRecordable
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.preMealTargetBlock
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.primerTbrAction
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.sleepSignals
import app.aaps.plugins.aps.openAPSBoost.SleepStateDetector.SleepState
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/** Seam guards from the 2026-10-08 dose-path audit: #8 pre-meal target, #10 primer temp, #18 sleep boundary. */
class SeamSafetyGatesTest {

    // ── #8 pre-meal target ──

    @Test fun `pre-meal target - applies only outside the night, awake, no temp target, outside post-rescue`() {
        assertThat(preMealTargetBlock(false, SleepState.AWAKE, false, false)).isNull()
    }

    @Test fun `pre-meal target - blocked inside the night window, asleep, under a temp target and post-rescue`() {
        assertThat(preMealTargetBlock(true, SleepState.AWAKE, false, false)).isEqualTo("night window")
        assertThat(preMealTargetBlock(false, SleepState.SLEEPING, false, false)).isEqualTo("asleep")
        assertThat(preMealTargetBlock(false, SleepState.PRE_SLEEP, false, false)).isEqualTo("asleep")
        assertThat(preMealTargetBlock(false, SleepState.AWAKE, true, false)).isEqualTo("temp target")
        assertThat(preMealTargetBlock(false, SleepState.AWAKE, false, true)).isEqualTo("post-rescue")
    }

    @Test fun `meal-time learner - records only daytime sessions with the detector awake`() {
        assertThat(mealSessionRecordable(inNightWindow = false, sleepState = SleepState.AWAKE)).isTrue()
        assertThat(mealSessionRecordable(inNightWindow = true, sleepState = SleepState.AWAKE)).isFalse()
        assertThat(mealSessionRecordable(inNightWindow = false, sleepState = SleepState.SLEEPING)).isFalse()
        assertThat(mealSessionRecordable(inNightWindow = false, sleepState = SleepState.PRE_SLEEP)).isFalse()
    }

    // ── #10 primer temp basal ──

    @Test fun `primer - V1 kept a running zero temp with no rate returned - the protective temp wins`() {
        // "no temp required": rate null, a zero temp with 20 min left is running
        val base = effectiveBaseTempRate(baseRate = null, currentTempRate = 0.0, currentTempDurationMin = 20)
        assertThat(base).isEqualTo(0.0)
        assertThat(primerTbrAction(base, curBasal = 0.8, primerRate = 2.0)).isEqualTo(PrimerTbrAction.SKIP_PROTECTIVE)
    }

    @Test fun `primer - no temp running and no rate returned - the primer applies`() {
        // CurrentTemp reports rate 0.0 with duration 0 when nothing runs; that is not a zero temp
        val base = effectiveBaseTempRate(baseRate = null, currentTempRate = 0.0, currentTempDurationMin = 0)
        assertThat(base).isNull()
        assertThat(primerTbrAction(base, curBasal = 0.8, primerRate = 2.0)).isEqualTo(PrimerTbrAction.APPLY)
    }

    @Test fun `primer - a returned rate still decides as before`() {
        assertThat(primerTbrAction(effectiveBaseTempRate(0.3, 2.5, 20), 0.8, 2.0)).isEqualTo(PrimerTbrAction.SKIP_PROTECTIVE)
        assertThat(primerTbrAction(effectiveBaseTempRate(2.5, 0.0, 20), 0.8, 2.0)).isEqualTo(PrimerTbrAction.SUBSUMED)
        assertThat(primerTbrAction(effectiveBaseTempRate(1.0, 0.0, 20), 0.8, 2.0)).isEqualTo(PrimerTbrAction.APPLY)
    }

    @Test fun `primer - a running high temp at or above the primer is left alone`() {
        val base = effectiveBaseTempRate(baseRate = null, currentTempRate = 2.4, currentTempDurationMin = 15)
        assertThat(primerTbrAction(base, curBasal = 0.8, primerRate = 2.0)).isEqualTo(PrimerTbrAction.SUBSUMED)
    }

    // ── #18 sleep boundary exit ──

    private val min = 60_000L
    private val exitAt = 1_000_000_000L

    @Test fun `boundary exit - the next cycle is still treated as asleep, INACTIVE excluded`() {
        val s = sleepSignals(SleepState.AWAKE, nightSleepPeriodRaw = false, nightModeEnabled = true, autoBySleep = true,
            nowMs = exitAt + 5 * min, lastBoundaryExitMs = exitAt, holdMin = boundaryExitHoldMin(10))
        assertThat(s.boundaryHold).isTrue()
        assertThat(s.detectorAsleep).isTrue()
        assertThat(StepFeed.inactivityEligible(true, 100, 0, 400, sleepInActive = false, asleep = s.detectorAsleep, inNightWindow = false)).isFalse()
    }

    @Test fun `boundary exit - the gate stays closed for V1 with sleep-driven night mode, and for V6`() {
        val s = sleepSignals(SleepState.AWAKE, nightSleepPeriodRaw = false, nightModeEnabled = true, autoBySleep = true,
            nowMs = exitAt + 5 * min, lastBoundaryExitMs = exitAt, holdMin = boundaryExitHoldMin(10))
        assertThat(boostGateOpen(s.nightSleepPeriod, inNightWindow = false, v6Active = false, detectorSleeping = s.detectorSleeping)).isFalse()
        assertThat(boostGateOpen(s.nightSleepPeriod, inNightWindow = false, v6Active = true, detectorSleeping = s.detectorSleeping)).isFalse()
    }

    @Test fun `boundary exit - the hold lapses after the hysteresis plus one cycle`() {
        val s = sleepSignals(SleepState.AWAKE, false, true, true,
            nowMs = exitAt + 15 * min, lastBoundaryExitMs = exitAt, holdMin = boundaryExitHoldMin(10))
        assertThat(s.boundaryHold).isFalse()
        assertThat(s.detectorAsleep).isFalse()
        assertThat(s.nightSleepPeriod).isFalse()
    }

    @Test fun `boundary exit - V1 with night mode off keeps its toggle-governed gate`() {
        val s = sleepSignals(SleepState.AWAKE, nightSleepPeriodRaw = false, nightModeEnabled = false, autoBySleep = true,
            nowMs = exitAt + 5 * min, lastBoundaryExitMs = exitAt, holdMin = boundaryExitHoldMin(10))
        assertThat(s.nightSleepPeriod).isFalse()
        assertThat(s.detectorAsleep).isTrue()   // INACTIVE still excluded
    }

    @Test fun `no boundary exit recorded - signals are the detector's own`() {
        val s = sleepSignals(SleepState.AWAKE, false, true, true, nowMs = exitAt, lastBoundaryExitMs = null, holdMin = 15)
        assertThat(s.detectorSleeping).isFalse()
        assertThat(s.detectorAsleep).isFalse()
        val p = sleepSignals(SleepState.PRE_SLEEP, true, true, true, nowMs = exitAt, lastBoundaryExitMs = null, holdMin = 15)
        assertThat(p.detectorAsleep).isTrue()
        assertThat(p.detectorSleeping).isFalse()
        assertThat(p.nightSleepPeriod).isTrue()
    }
}
