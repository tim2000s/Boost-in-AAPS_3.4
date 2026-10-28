package app.aaps.plugins.insulin

import app.aaps.core.data.iob.Iob
import app.aaps.core.data.model.BS
import app.aaps.core.data.model.ICfg
import app.aaps.core.data.time.T
import app.aaps.core.interfaces.configuration.Config
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.profile.ProfileFunction
import app.aaps.core.interfaces.resources.ResourceHelper
import app.aaps.core.interfaces.rx.bus.RxBus
import app.aaps.core.interfaces.ui.UiInteraction
import app.aaps.core.interfaces.utils.HardLimits
import kotlin.math.exp
import kotlin.math.pow

/**
 * Glucodynamic (pharmacodynamic) base class for Lyumjev U100 and U200.
 *
 * Uses a Gaussian activity curve with dose-dependent peak time instead of
 * the standard oref biexponential model. The DIA is fixed at 8 hours as the
 * model automatically adjusts its duration based on bolus size.
 *
 * Peak time model: tp = (a0 + a1*X) / (1 + b1*X) where X = effective dose
 * Activity:  (2 * dose / tp_model) * t * exp(-t² / tp_model)
 * IOB:       dose * (exp(-t_lower² / tp_model) - exp(-t_upper² / tp_model))
 *
 * Based on the UAM Tsunami PD model from Boost 3.2.
 */
abstract class InsulinLyumjevPDBasePlugin(
    rh: ResourceHelper,
    profileFunction: ProfileFunction,
    rxBus: RxBus,
    aapsLogger: AAPSLogger,
    config: Config,
    hardLimits: HardLimits,
    uiInteraction: UiInteraction
) : InsulinOrefBasePlugin(rh, profileFunction, rxBus, aapsLogger, config, hardLimits, uiInteraction) {

    companion object {
        // Model constants for peak time estimation
        private const val A0 = 61.33    // minutes
        private const val A1 = 12.27
        private const val B1 = 0.05185
        private const val PD_DIA_HOURS = 8.0
        private const val PD_DIA_MINUTES = PD_DIA_HOURS * 60.0
    }

    /**
     * Returns the dose X, in units of insulin, that sets the peak time.
     * U100: the bolus amount, since one pump unit is one unit of insulin.
     * U200: twice the bolus amount, since the amounts are U200 pump units of two units of insulin each.
     *
     * The two were swapped from the model's first commit (44a0263099, May 2022): it doubled the dose
     * for insulin ID 6 under the comment "ID = 6 for Lyumjev U200", but ID 6 was the U100 plugin. So
     * U100 had four times U200's peak-time dose for the same insulin, where it should be the same.
     */
    abstract fun effectiveDose(bolusAmount: Double): Double

    override val peak = 45  // nominal peak for display; actual peak is dose-dependent

    /**
     * Fixed 8h DIA — the PD model auto-adjusts duration based on dose.
     */
    override val userDefinedDia: Double
        get() = PD_DIA_HOURS

    override val iCfg: ICfg
        get() = ICfg(friendlyName, (PD_DIA_HOURS * 1000.0 * 3600.0).toLong(), T.mins(peak.toLong()).msecs())

    override fun iobCalcForTreatment(bolus: BS, time: Long, dia: Double): Iob {
        val result = Iob()
        if (bolus.amount != 0.0) {
            val t = (time - bolus.timestamp) / 1000.0 / 60.0  // minutes since bolus

            if (t < PD_DIA_MINUTES) {
                // Dose-dependent peak time
                val effDose = effectiveDose(bolus.amount)
                val tp = (A0 + A1 * effDose) / (1 + B1 * effDose)
                val tpModel = tp.pow(2.0) * 2  // transform for model formula

                // Gaussian activity curve
                result.activityContrib = (2 * bolus.amount / tpModel) * t * exp(-t.pow(2.0) / tpModel)

                // Integrated IOB (closed-form of activity integral)
                val lowerLimit = t
                val upperLimit = PD_DIA_MINUTES
                result.iobContrib = bolus.amount * (exp(-lowerLimit.pow(2.0) / tpModel) - exp(-upperLimit.pow(2.0) / tpModel))
            }
        }
        return result
    }
}
