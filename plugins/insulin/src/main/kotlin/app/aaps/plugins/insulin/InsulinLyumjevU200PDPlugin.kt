package app.aaps.plugins.insulin

import app.aaps.core.interfaces.configuration.Config
import app.aaps.core.interfaces.insulin.Insulin
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.profile.ProfileFunction
import app.aaps.core.interfaces.resources.ResourceHelper
import app.aaps.core.interfaces.rx.bus.RxBus
import app.aaps.core.interfaces.ui.UiInteraction
import app.aaps.core.interfaces.utils.HardLimits
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Glucodynamic model for Lyumjev U200 (2x concentrated).
 * Automatically adjusts DIA based on bolus size.
 * The peak-time dose is twice the bolus amount: with basals halved and ISFs doubled the amounts are
 * pump units of U200, and each carries two units of insulin.
 *
 * NOTE: You must halve your basals and double your ISFs before use with U200 insulin.
 */
@Singleton
class InsulinLyumjevU200PDPlugin @Inject constructor(
    rh: ResourceHelper,
    profileFunction: ProfileFunction,
    rxBus: RxBus,
    aapsLogger: AAPSLogger,
    config: Config,
    hardLimits: HardLimits,
    uiInteraction: UiInteraction
) : InsulinLyumjevPDBasePlugin(rh, profileFunction, rxBus, aapsLogger, config, hardLimits, uiInteraction) {

    override val id get(): Insulin.InsulinType = Insulin.InsulinType.OREF_LYUMJEV_U200_PD
    override val friendlyName get(): String = rh.gs(R.string.lyumjev_u200_pd)

    override fun configuration(): JSONObject = JSONObject()
    override fun applyConfiguration(configuration: JSONObject) {}

    override fun commentStandardText(): String = rh.gs(R.string.description_insulin_lyumjev_u200_pd)

    // U200: each pump unit carries two units of insulin, so the peak-time dose is twice the amount.
    override fun effectiveDose(bolusAmount: Double): Double = 2 * bolusAmount

    init {
        pluginDescription
            .pluginIcon(R.drawable.ic_insulin)
            .pluginName(R.string.lyumjev_u200_pd)
            .description(R.string.description_insulin_lyumjev_u200_pd)
    }
}
