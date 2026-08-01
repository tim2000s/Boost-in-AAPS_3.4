package app.aaps.plugins.aps.openAPSBoostTwin

/**
 * KAIROS Twin — shadow orchestrator (2026-07-18). Holds the physiological EnKF across cycles,
 * assimilates each cycle's CGM + insulin, and returns a calibrated forecast. READ-ONLY: it produces
 * a forecast for telemetry and (eventually) to feed the TING planner's counterfactual; it never
 * touches a dose. Mirrors the openAPSBoostV7 V7Shadow pattern — self-contained, error-swallowing,
 * ready to wire into runShadow with a single call.
 *
 * Validated as a forecaster (backtesting/scripts/2026-07-kairos-twin): out-of-sample RMSE ≈ half of
 * oref's at 30/60 min, beats persistence at 60 min, 60-min 90%-band coverage ~87%.
 */
class TwinShadow(
    params: TwinParams = TwinParams(),
    seed: Long = 1L,
) {
    private val enkf = TwinEnkf(params, seed = seed)

    /**
     * Run one cycle. [cgmMgdl] this cycle's CGM (null = missing → predict only); [insulinThisCycleU]
     * the insulin actually delivered in the last 5 min (SMB + basal, U); [expectedBasalPerCycleU] the
     * insulin to assume for each FUTURE cycle in the forecast (open-loop, e.g. the current basal rate).
     * Returns the forecast, or null on cold start (no CGM yet) / any error — never throws.
     */
    fun runCycle(cgmMgdl: Double?, insulinThisCycleU: Double, expectedBasalPerCycleU: Double): TwinForecast? =
        runCatching {
            if (!enkf.initialised) {
                if (cgmMgdl == null) return null
                enkf.init(cgmMgdl)
            }
            enkf.predict(insulinThisCycleU)                       // step to now under known insulin
            if (cgmMgdl != null) enkf.update(cgmMgdl)             // assimilate the reading
            val f30 = enkf.forecast(6, expectedBasalPerCycleU)    // 30 min
            val f60 = enkf.forecast(12, expectedBasalPerCycleU)   // 60 min
            val s = enkf.meanState()
            TwinForecast(
                fc30 = round1(f30.first), lo30 = round1(f30.second), hi30 = round1(f30.third),
                fc60 = round1(f60.first), lo60 = round1(f60.second), hi60 = round1(f60.third),
                raMean = round3(s[TW_RA]), filteredGi = round1(s[TW_GI]),
            )
        }.getOrNull()

    private fun round1(v: Double) = kotlin.math.round(v * 10.0) / 10.0
    private fun round3(v: Double) = kotlin.math.round(v * 1000.0) / 1000.0
}

/**
 * The Twin's read-only per-cycle output.
 * - [fc30]/[fc60] : forecast CGM (mg/dL) at 30 / 60 min, with [lo*]/[hi*] the 90% band.
 * - [raMean]      : inferred glucose appearance (mg/dL/min) — a meal signal discovered from CGM alone.
 * - [filteredGi]  : the Twin's current filtered glucose (mg/dL).
 */
data class TwinForecast(
    val fc30: Double, val lo30: Double, val hi30: Double,
    val fc60: Double, val lo60: Double, val hi60: Double,
    val raMean: Double,
    val filteredGi: Double,
)
