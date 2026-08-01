package app.aaps.plugins.aps.openAPSBoostV7

import app.aaps.core.interfaces.aps.Predictions
import app.aaps.core.interfaces.aps.RT
import app.aaps.plugins.aps.openAPSBoostV5.DetermineBasalBoostV5
import app.aaps.plugins.aps.openAPSBoostV5.MealHypothesis
import app.aaps.plugins.aps.openAPSBoostV5.MealHypothesisState
import app.aaps.plugins.aps.openAPSBoostV5.V5Inputs
import app.aaps.plugins.aps.openAPSBoostV5.V5PersistedState
import com.google.common.truth.Truth.assertThat
import org.json.JSONArray
import org.json.JSONObject
import org.junit.jupiter.api.Test

/**
 * V7Shadow safety invariants — the reason this branch may be flashed:
 *
 *  1. **Dosing-path bit-identity**: every dose-relevant RT field and every V5/V6 decision output
 *     is IDENTICAL with the shadow enabled vs a control without it (the shadow is read-only;
 *     only `boostV7_*` telemetry + the reason breadcrumb are written).
 *  2. **Failure-swallowing**: a throwing persistence layer or a corrupt blob never propagates —
 *     the loop cycle proceeds untouched (the V5-inside-V1 shadow pattern).
 *  3. **Cold-start abstention**: empty pools log "warming" and the sizer stays null.
 *  4. The reason breadcrumb appears ONLY when the R-doses differ (the criterion-(a) event).
 */
class V7ShadowSafetyTest {

    private val now = 1_000_000_000_000L

    private class FakeStore(var blob: String = "") {

        var loadThrows = false
        var saveThrows = false
        fun shadow() = V7Shadow(
            loadState = { if (loadThrows) throw RuntimeException("prefs read boom") else blob },
            saveState = { if (saveThrows) throw RuntimeException("prefs write boom") else blob = it },
            logInfo = {},
            logError = { _, _ -> },
        )
    }

    /** A warm persisted blob: MEAL pools at h=30/60/90 with 160 samples equally cycling the
     *  given five values → the tracker's 5/25/50/75/95 quantiles land EXACTLY on those values. */
    private fun warmMealBlob(values: DoubleArray): String {
        val pools = JSONObject()
        for (h in intArrayOf(30, 60, 90)) {
            val flat = JSONArray()
            for (i in 0 until 160) {
                flat.put((now - i * 300_000L) / 1000L)
                flat.put(values[i % values.size])
            }
            pools.put("MEAL:$h", flat)
        }
        return JSONObject().put("v", 2).put("pend", JSONArray()).put("pools", pools).toString()
    }

    /** Debiased pool → sizer doses 1.65/1.60/1.40 (pinned in V7SizerTest) → breadcrumb fires. */
    private val debiased = doubleArrayOf(-80.0, -20.0, 0.0, 30.0, 90.0)

    private fun rt(reason: String = "base; ") = RT(runningDynamicIsf = true).apply {
        bg = 200.0
        eventualBG = 240.0
        insulinReq = 0.9
        units = 0.45          // V1's would-dose at the seam
        rate = 1.2
        duration = 30
        variable_sens = 80.0
        // Flat undosed IOB curve at bg=200 → base60/base90 = 200, matching the old
        // bgi5=0 constant-hold arithmetic the pinned sizer expectations were built on.
        predBGs = Predictions(IOB = List(19) { 200 })
        this.reason = StringBuilder(reason)
    }

    /** Run one warm MEAL cycle through the shadow (CONFIRMED, budget 2.0 → sizing computes). */
    private fun runWarmCycle(store: FakeStore, rT: RT, bg: Double = 200.0, sens: Double = 80.0) = store.shadow().runCycle(
        rT = rT, bg = bg, delta = 5.0, shortAvgDelta = 5.0, iobActivity = 0.0,
        variableSens = sens, profileSens = 50.0,
        v5State = MealHypothesis.CONFIRMED, v5BudgetU = 2.0, v1WouldDoseU = rT.units,
        committedCapU = 0.5, confirmedCapU = 3.0, postRescueWindow = false,
        cumulativeCapU = 0.0, smbVol60MinU = 0.0, nowMs = now, hour = 12,
    )

    // ── 1. Dosing-path bit-identity ─────────────────────────────────────────────────────────────

    @Test fun `every dose-relevant RT field is bit-identical with the shadow enabled vs the control`() {
        val control = rt()                              // shadow never ran
        val shadowed = rt()
        runWarmCycle(FakeStore(warmMealBlob(debiased)), shadowed)

        // The shadow computed (all three doses present, breadcrumb fired)…
        assertThat(shadowed.boostV7_wouldDoseR4).isEqualTo(1.65)
        assertThat(shadowed.boostV7_wouldDoseR7).isEqualTo(1.6)
        assertThat(shadowed.boostV7_wouldDoseR10).isEqualTo(1.4)
        // …and the dose path is untouched — bit-identical to the control:
        assertThat(shadowed.units).isEqualTo(control.units)
        assertThat(shadowed.rate).isEqualTo(control.rate)
        assertThat(shadowed.duration).isEqualTo(control.duration)
        assertThat(shadowed.insulinReq).isEqualTo(control.insulinReq)
        assertThat(shadowed.eventualBG).isEqualTo(control.eventualBG)
        assertThat(shadowed.variable_sens).isEqualTo(control.variable_sens)
        assertThat(shadowed.carbsReq).isEqualTo(control.carbsReq)
        assertThat(shadowed.deliverAt).isEqualTo(control.deliverAt)
    }

    @Test fun `V5 decision outputs are identical with the shadow running between decide() calls`() {
        // The Episode-B-like fixture from ComposedFloorShadowTest — an existing dosing fixture.
        val inputs = V5Inputs(
            delta = 2.0, shortAvgDelta = 2.0, deltaAccl = -15.0, bg = 270.0, eventualBg = 280.0,
            targetBg = 100.0, maxDelta = 2.0, minGuardBg = 150.0, minGuardThreshold = 80.0,
            deltaHistory = listOf(2.0, 2.0, 2.0), iob = 8.5, maxIob = 10.0, baseInsulinReq = 0.5,
            roundSmbTo = 0.05, enableSmbPreChecks = true, mlHypoRisk = null, mlMealLikely = 0.5,
            recentLowBg = 120.0, cumulativeRise30min = 12.0, hour = 12, exerciseActive = false,
            inPostExerciseWindow = false, asleep = false, committedCapU = 0.5, confirmedCapU = 2.5,
            postRescueWindow = false, v1WouldDoseU = null,
        )
        val persisted = V5PersistedState(
            mealHypothesis = MealHypothesisState(MealHypothesis.COMMITTED, ageCycles = 1, committedInSession = true)
        )
        val determineBasal = DetermineBasalBoostV5()

        val before = determineBasal.decide(inputs, persisted)
        runWarmCycle(FakeStore(warmMealBlob(debiased)), rt())   // shadow runs a full sizing cycle
        val after = determineBasal.decide(inputs, persisted)

        assertThat(after.finalDose).isEqualTo(before.finalDose)
        assertThat(after.insulinToDeliver).isEqualTo(before.insulinToDeliver)
        assertThat(after.mealHypothesis).isEqualTo(before.mealHypothesis)
        assertThat(after.aggressionBudget.budget).isEqualTo(before.aggressionBudget.budget)
        assertThat(after.actionMultiplier).isEqualTo(before.actionMultiplier)
        assertThat(after.floorWouldAdd).isEqualTo(before.floorWouldAdd)
    }

    // ── 2. Failure-swallowing ───────────────────────────────────────────────────────────────────

    @Test fun `a throwing persistence READ is swallowed - the cycle proceeds on a cold tracker`() {
        val store = FakeStore(warmMealBlob(debiased)).apply { loadThrows = true }
        val rT = rt()
        runWarmCycle(store, rT)   // must not throw
        assertThat(rT.units).isEqualTo(0.45)                       // dose path untouched
        assertThat(rT.boostV7_pool).isEqualTo("meal(warming n=0)") // fell back to cold start
        assertThat(rT.boostV7_wouldDoseR4).isNull()                // sizer abstained
    }

    @Test fun `a throwing persistence WRITE is swallowed - telemetry still lands`() {
        val store = FakeStore(warmMealBlob(debiased)).apply { saveThrows = true }
        val rT = rt()
        runWarmCycle(store, rT)   // must not throw
        assertThat(rT.units).isEqualTo(0.45)
        assertThat(rT.boostV7_pool).isEqualTo("meal(n=160)")
        assertThat(rT.boostV7_wouldDoseR7).isEqualTo(1.6)
    }

    @Test fun `a corrupt persisted blob cold-starts instead of breaking the cycle`() {
        val store = FakeStore("definitely { not json")
        val rT = rt()
        runWarmCycle(store, rT)   // must not throw
        assertThat(rT.units).isEqualTo(0.45)
        assertThat(rT.boostV7_pool).isEqualTo("meal(warming n=0)")
        assertThat(rT.boostV7_wouldDoseR4).isNull()
    }

    // ── 3. Cold-start abstention + 4. breadcrumb semantics ──────────────────────────────────────

    @Test fun `cold start logs warming, abstains from sizing, and leaves the reason untouched`() {
        val rT = rt("base; ")
        val store = FakeStore("")
        store.shadow().runCycle(
            rT = rT, bg = 120.0, delta = 0.5, shortAvgDelta = 0.0, iobActivity = 0.01,
            variableSens = 60.0, profileSens = 50.0,
            v5State = MealHypothesis.IDLE, v5BudgetU = 0.5, v1WouldDoseU = 0.1,
            committedCapU = 0.5, confirmedCapU = 2.5, postRescueWindow = false,
            cumulativeCapU = 2.5, smbVol60MinU = 0.0, nowMs = now, hour = 12,
        )
        assertThat(rT.boostV7_pool).isEqualTo("quiet_flat(warming n=0)")
        assertThat(rT.boostV7_wouldDoseR4).isNull()
        assertThat(rT.boostV7_wouldDoseR7).isNull()
        assertThat(rT.boostV7_wouldDoseR10).isNull()
        assertThat(rT.boostV7_q50Drift).isNull()
        assertThat(rT.boostV7_pLow90).isNull()
        assertThat(rT.reason.toString()).isEqualTo("base; ")       // no breadcrumb without doses
        assertThat(rT.boostV7_innovSensFrozen).isNotNull()         // innovation accrues from cycle 1
        assertThat(store.blob).isNotEmpty()                        // pools persisted for next cycle
    }

    @Test fun `reason breadcrumb fires ONLY when the R-doses differ`() {
        // Debiased pool → doses differ → breadcrumb (the interesting criterion-(a) event).
        val differing = rt("base; ")
        runWarmCycle(FakeStore(warmMealBlob(debiased)), differing)
        assertThat(differing.reason.toString()).isEqualTo("base; v7: R4=1.65 R7=1.60 R10=1.40; ")

        // Biased pool (the offline pathology) at the sizer test's bg 160 / sens 50: the q5
        // shoulder never projects <70 inside the grid → doses identical → NO breadcrumb.
        val biased = doubleArrayOf(-15.0, 9.0, 31.0, 63.0, 122.0)
        val identical = rt("base; ")
        runWarmCycle(FakeStore(warmMealBlob(biased)), identical, bg = 160.0, sens = 50.0)
        assertThat(identical.boostV7_wouldDoseR4).isEqualTo(3.0)
        assertThat(identical.boostV7_wouldDoseR4).isEqualTo(identical.boostV7_wouldDoseR10)
        assertThat(identical.reason.toString()).isEqualTo("base; ")
    }

    @Test fun `excluded cycles log excluded and compute nothing but the innovation`() {
        val rT = rt("base; ")
        FakeStore(warmMealBlob(debiased)).shadow().runCycle(
            rT = rT, bg = 150.0, delta = 6.0, shortAvgDelta = 5.0, iobActivity = 0.01,
            variableSens = 60.0, profileSens = 50.0,
            v5State = MealHypothesis.IDLE, v5BudgetU = 0.5, v1WouldDoseU = 0.1,   // rising non-meal daytime
            committedCapU = 0.5, confirmedCapU = 2.5, postRescueWindow = false,
            cumulativeCapU = 2.5, smbVol60MinU = 0.0, nowMs = now, hour = 12,
        )
        assertThat(rT.boostV7_pool).isEqualTo("excluded")
        assertThat(rT.boostV7_wouldDoseR4).isNull()
        assertThat(rT.boostV7_q50Drift).isNull()
        assertThat(rT.boostV7_innovSensFrozen).isNotNull()
        assertThat(rT.reason.toString()).isEqualTo("base; ")
        assertThat(rT.units).isEqualTo(0.45)
    }
}
