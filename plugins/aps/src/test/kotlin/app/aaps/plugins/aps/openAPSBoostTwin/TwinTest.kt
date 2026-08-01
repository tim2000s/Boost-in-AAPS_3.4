package app.aaps.plugins.aps.openAPSBoostTwin

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * KAIROS Twin (2026-07-18) — the physiological core, the ensemble filter, and the shadow orchestrator.
 * These pin the physiology (insulin lowers glucose, CGM lags blood, appearance decays), the filter
 * (tracks CGM, discovers meals as latent appearance, forecasts a calibrated band), and the shadow
 * contract (deterministic, doses nothing, fails safe). Faithful to the validated Python.
 */
class TwinTest {

    private val p = TwinParams()

    // ── physiological model ─────────────────────────────────────────────────────────────────────

    @Test fun `a bolus enters the SC depot and lowers glucose over time (insulin action)`() {
        // Fasting-ish at 150, deliver 2U, then coast: glucose must fall as insulin action builds.
        var x = doubleArrayOf(0.0, 0.0, 0.0, 0.0, 150.0, 150.0)
        x = twinStep5(x, 2.0, p)                       // the bolus cycle
        assertThat(x[TW_ISC1]).isGreaterThan(0.0)      // depot filled
        val g0 = x[TW_G]
        repeat(24) { x = twinStep5(x, 0.0, p) }        // coast ~2h
        assertThat(x[TW_X]).isGreaterThan(0.0)         // insulin action present
        assertThat(x[TW_G]).isLessThan(g0)             // glucose came down
    }

    @Test fun `CGM compartment lags blood glucose`() {
        // Blood glucose jumps; interstitial Gi should trail it, not equal it, after one step.
        var x = doubleArrayOf(0.0, 0.0, 0.0, 0.0, 200.0, 120.0)
        x = twinStep5(x, 0.0, p)
        assertThat(x[TW_GI]).isGreaterThan(120.0)      // moving toward G
        assertThat(x[TW_GI]).isLessThan(x[TW_G])       // but lagging
    }

    @Test fun `latent appearance decays toward zero with no input`() {
        var x = doubleArrayOf(0.0, 0.0, 0.0, 3.0, 120.0, 120.0)
        val ra0 = x[TW_RA]
        repeat(10) { x = twinStep5(x, 0.0, p) }
        assertThat(x[TW_RA]).isLessThan(ra0)
        assertThat(x[TW_RA]).isGreaterThan(0.0)
    }

    @Test fun `glucose never goes non-physical`() {
        // Absurd inputs must not produce a negative / silly glucose (floored at 10).
        var x = doubleArrayOf(0.0, 0.0, 0.0, 0.0, 40.0, 40.0)
        repeat(50) { x = twinStep5(x, 5.0, p) }        // hammer insulin
        assertThat(x[TW_G]).isAtLeast(10.0)
        assertThat(x[TW_GI]).isAtLeast(10.0)
    }

    // ── ensemble filter ─────────────────────────────────────────────────────────────────────────

    @Test fun `filter tracks a steady CGM and forecasts near it`() {
        val f = TwinEnkf(p, seed = 1L); f.init(120.0)
        repeat(48) { f.predict(0.05); f.update(120.0) }   // 4h of steady 120 under trickle basal
        assertThat(f.meanState()[TW_GI]).isWithin(6.0).of(120.0)
        val (mean, lo, hi) = f.forecast(12, 0.05)
        assertThat(mean).isWithin(15.0).of(120.0)
        assertThat(lo).isLessThan(mean); assertThat(hi).isGreaterThan(mean)   // a real band
    }

    @Test fun `filter discovers a meal as positive latent appearance`() {
        val f = TwinEnkf(p, seed = 1L); f.init(110.0)
        repeat(12) { f.predict(0.05); f.update(110.0) }   // settle
        // a brisk rise with no matching insulin ⇒ the only explanation the model has is appearance
        for (g in listOf(120.0, 135.0, 155.0, 175.0, 190.0)) { f.predict(0.05); f.update(g) }
        assertThat(f.meanState()[TW_RA]).isGreaterThan(0.5)
    }

    @Test fun `forecast band widens with horizon (unseen meals)`() {
        val f = TwinEnkf(p, seed = 1L); f.init(120.0)
        repeat(24) { f.predict(0.05); f.update(120.0) }
        val (_, lo30, hi30) = f.forecast(6, 0.05)
        val (_, lo60, hi60) = f.forecast(12, 0.05)
        assertThat(hi60 - lo60).isGreaterThan(hi30 - lo30)   // more uncertainty further out
    }

    // ── shadow orchestrator ─────────────────────────────────────────────────────────────────────

    @Test fun `cold start returns null until the first CGM`() {
        val t = TwinShadow(p, seed = 1L)
        assertThat(t.runCycle(cgmMgdl = null, insulinThisCycleU = 0.1, expectedBasalPerCycleU = 0.05)).isNull()
        assertThat(t.runCycle(cgmMgdl = 120.0, insulinThisCycleU = 0.1, expectedBasalPerCycleU = 0.05)).isNotNull()
    }

    @Test fun `orchestrator is deterministic given the seed`() {
        fun run(): TwinForecast? {
            val t = TwinShadow(p, seed = 7L); var r: TwinForecast? = null
            for (g in listOf(120.0, 122.0, 130.0, 145.0, 150.0, 148.0)) r = t.runCycle(g, 0.1, 0.05)
            return r
        }
        assertThat(run()).isEqualTo(run())
    }

    @Test fun `forecast is a valid ordered band and doses nothing (no dose field exists)`() {
        val t = TwinShadow(p, seed = 1L); var r: TwinForecast? = null
        for (g in listOf(120.0, 125.0, 135.0, 150.0, 165.0)) r = t.runCycle(g, 0.1, 0.05)
        assertThat(r).isNotNull()
        assertThat(r!!.lo60).isAtMost(r.fc60); assertThat(r.fc60).isAtMost(r.hi60)
        // TwinForecast structurally carries only a forecast — there is no dose to deliver.
        assertThat(TwinForecast::class.java.declaredFields.map { it.name })
            .containsNoneOf("dose", "units", "insulin", "smb")
    }
}
