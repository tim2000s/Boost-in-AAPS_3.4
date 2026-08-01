package app.aaps.plugins.aps.openAPSBoostV7

import app.aaps.core.interfaces.aps.RT
import app.aaps.plugins.aps.openAPSBoostV5.MealHypothesis
import java.util.Locale
import kotlin.math.round

/**
 * V7Shadow — per-cycle orchestrator for the V7 shadow computation.
 *
 * READ-ONLY BY CONSTRUCTION: invoked by the V1 engine right after V5's runShadow (same inputs)
 * and BEFORE the V6 override seam, so `rT.units` is still V1's would-dose (the non-meal
 * v1-bound input). It writes ONLY the `boostV7_*` RT telemetry fields plus a reason breadcrumb
 * when the R-doses differ (the interesting criterion-(a) event); it never reads back into any
 * dosing decision. Everything runs inside [runCatching] — a shadow failure is logged and
 * swallowed, the loop cycle proceeds untouched (the V5-inside-V1 shadow pattern).
 *
 * Composition:
 *  1. [V7ResidualTracker] — regime-conditioned residual pools (substrate; criterion (b)).
 *  2. [V7Sizer] — revised distributional sizing at R = 4/7/10 (criterion (a)).
 *  3. [V7InnovationTracker] — sens-frozen efficacy innovation (Backtest-2 follow-up, log-only).
 *
 * Persistence follows the V5StateStore idiom: `@Volatile` in-memory tracker (rapid multi-invokes
 * always see the latest state) + a StringKey JSON blob (StringKey.ApsBoostV7ResidualPools) for
 * restart recovery, written through the injected [saveState]. The load/save/log seams are
 * injected as lambdas so the orchestrator is unit-testable without Android preferences.
 *
 * See V7_SHADOW.md in this package for what is computed and the NO-GO lineage.
 */
class V7Shadow(
    private val loadState: () -> String,
    private val saveState: (String) -> Unit,
    private val logInfo: (String) -> Unit,
    private val logError: (String, Throwable) -> Unit,
) {

    @Volatile private var tracker: V7ResidualTracker? = null
    private val innovation = V7InnovationTracker()

    /**
     * Run the V7 shadow for one engine cycle. Never throws; never mutates anything except
     * `rT.boostV7_*` (+ the reason breadcrumb on differing R-doses).
     *
     * @param v1WouldDoseU rT.units at the seam — V1's would-dose, BEFORE the V6 override.
     * @param variableSens the adapted variable_sens (mg/dL/U) this cycle (rT.variable_sens).
     * @param profileSens the STATIC profile ISF (mg/dL/U) — the sens-frozen innovation's sens.
     */
    fun runCycle(
        rT: RT,
        bg: Double,
        delta: Double,
        shortAvgDelta: Double,
        iobActivity: Double,
        variableSens: Double?,
        profileSens: Double,
        v5State: MealHypothesis?,
        v5BudgetU: Double?,
        v1WouldDoseU: Double?,
        committedCapU: Double,
        confirmedCapU: Double,
        postRescueWindow: Boolean,
        cumulativeCapU: Double,
        smbVol60MinU: Double,
        nowMs: Long,
        hour: Int,
    ) {
        runCatching {
            runCycleInner(
                rT, bg, delta, shortAvgDelta, iobActivity, variableSens, profileSens, v5State, v5BudgetU,
                v1WouldDoseU, committedCapU, confirmedCapU, postRescueWindow, cumulativeCapU, smbVol60MinU, nowMs, hour
            )
        }.onFailure { t ->
            // The shadow can NEVER break a loop cycle — log + swallow; telemetry stays null.
            logError("V7 shadow cycle failed (swallowed — dosing path untouched)", t)
        }
    }

    private fun runCycleInner(
        rT: RT,
        bg: Double,
        delta: Double,
        shortAvgDelta: Double,
        iobActivity: Double,
        variableSens: Double?,
        profileSens: Double,
        v5State: MealHypothesis?,
        v5BudgetU: Double?,
        v1WouldDoseU: Double?,
        committedCapU: Double,
        confirmedCapU: Double,
        postRescueWindow: Boolean,
        cumulativeCapU: Double,
        smbVol60MinU: Double,
        nowMs: Long,
        hour: Int,
    ) {
        if (bg <= 0.0) return  // no usable CGM this cycle — leave every boostV7_* field null

        val tracker = this.tracker ?: V7ResidualTracker.deserialize(runCatching { loadState() }.getOrNull())
            .also { this.tracker = it }

        // 1. Substrate — record this cycle's IOB-only projection + mature due horizons.
        // 2026-07-27: the projection is oref's decaying-activity IOB prediction curve
        // (rT.predBGs.IOB, the purple line — trailing-flat values are truncated by oref, so
        // clamp to the last element). The previous constant-BGI5 hold overstated the 90-min
        // fall in proportion to IOB (field calibration: high-IOB tertile predicted 36% low
        // vs 14% realised; QUIET_FLAT median residual +15 instead of ≈0).
        val iobCurve = rT.predBGs?.IOB
        val bases: DoubleArray? = if (iobCurve != null && iobCurve.size >= 2)
            DoubleArray(V7ResidualTracker.HORIZONS_MIN.size) { i ->
                iobCurve[minOf(V7ResidualTracker.HORIZONS_MIN[i] / 5, iobCurve.size - 1)].toDouble()
            } else null
        val regime = classifyV7Regime(v5State, delta, shortAvgDelta, hour)
        tracker.onCycle(nowMs, bg, bases, regime)
        runCatching { saveState(tracker.serialize()) }
            .onFailure { t -> logError("V7 shadow persist failed (state kept in memory)", t) }

        // 2. Telemetry — pool identity + the two acceptance-criteria instruments.
        if (regime == null) {
            rT.boostV7_pool = "excluded"
            // No active pool → no drift/pLow/doses this cycle; innovation still accrues below.
        } else {
            val n60 = tracker.count(regime, 60)
            val q60 = tracker.quantiles(regime, 60)
            rT.boostV7_pool =
                if (q60 != null) "${regime.name.lowercase(Locale.US)}(n=$n60)"
                else "${regime.name.lowercase(Locale.US)}(warming n=$n60)"

            // Criterion (b) instrument: the active pool's 30-min median residual — quiet-flat
            // cycles must read ≈0 once the regime conditioning has debiased the substrate.
            rT.boostV7_q50Drift = tracker.median(regime, 30)?.let { round1(it) }

            // Criterion (a) instrument: the sizing rule at R = 4/7/10 — warm pools only.
            if (q60 != null && bases != null && variableSens != null && variableSens > 0.0) {
                val result = V7Sizer.size(
                    V7Sizer.Inputs(
                        bg = bg, base60 = bases[1], sens = variableSens,
                        state = v5State, budgetU = v5BudgetU,
                        committedCapU = committedCapU, confirmedCapU = confirmedCapU,
                        v1WouldDoseU = v1WouldDoseU, postRescueWindow = postRescueWindow,
                        cumulativeCapU = cumulativeCapU, smbVol60MinU = smbVol60MinU,
                        residualQuantiles = q60,
                    )
                )
                if (result != null) {
                    rT.boostV7_wouldDoseR4 = round3(result.doseR4)
                    rT.boostV7_wouldDoseR7 = round3(result.doseR7)
                    rT.boostV7_wouldDoseR10 = round3(result.doseR10)
                    if (result.dosesDiffer) {
                        // The interesting event — cost-ratio sensitivity APPEARED in the field.
                        val line = "v7: R4=${fmt(result.doseR4)} R7=${fmt(result.doseR7)} R10=${fmt(result.doseR10)}"
                        rT.reason.append("$line; ")
                        logInfo("V7 shadow $line (env=${fmt(result.envelopeU)}U pool=${rT.boostV7_pool})")
                    }
                }
            }

            // Display-only left-shoulder p(BG<70 within 90 min) — never permission.
            val q90 = tracker.quantiles(regime, 90)
            if (q90 != null && bases != null) {
                rT.boostV7_pLow90 = V7Sizer.pLow(bases[2], q90)?.let { round3(it) }
            }
        }

        // 3. Sens-frozen efficacy innovation (log-only follow-up to Backtest 2's no-teeth verdict).
        rT.boostV7_innovSensFrozen = innovation.onCycle(nowMs, delta, iobActivity, profileSens)?.let { round1(it) }
    }

    private fun round1(v: Double) = round(v * 10.0) / 10.0
    private fun round3(v: Double) = round(v * 1000.0) / 1000.0
    private fun fmt(v: Double) = String.format(Locale.US, "%.2f", v)
}
