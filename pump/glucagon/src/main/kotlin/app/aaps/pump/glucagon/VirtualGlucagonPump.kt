package app.aaps.pump.glucagon

import app.aaps.core.data.model.BS
import app.aaps.core.data.plugin.PluginType
import app.aaps.core.data.ue.Action
import app.aaps.core.data.ue.Sources
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import app.aaps.core.interfaces.plugin.PluginBase
import app.aaps.core.interfaces.plugin.PluginDescription
import app.aaps.core.interfaces.pump.GlucagonPump
import app.aaps.core.interfaces.resources.ResourceHelper
import app.aaps.core.interfaces.rx.bus.RxBus
import app.aaps.core.interfaces.rx.events.EventNewHistoryData
import app.aaps.core.interfaces.utils.DateUtil
import java.util.TimeZone
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Virtual glucagon pump for testing the bihormonal closed-loop without physical hardware.
 *
 * Implements [GlucagonPump], and is found by [GlucagonAlgorithmPlugin] through
 * `activePlugin.getSpecificPluginsListByInterface(GlucagonPump::class.java)`.
 *
 * Simulates a pump loaded with glucagon. Reservoir defaults to 1000 mcg (1 mg, about a day's supply).
 * Stores delivered doses as BS(type=GLUCAGON) records so GOB can be calculated; they are not uploaded.
 *
 * Amount encoding: BS.amount is stored in mg (1.0 = 1 mg = 1000 mcg).
 */
@Singleton
class VirtualGlucagonPump @Inject constructor(
    aapsLogger: AAPSLogger,
    rh: ResourceHelper,
    private val rxBus: RxBus,
    private val persistenceLayer: PersistenceLayer,
    private val dateUtil: DateUtil
) : PluginBase(
    PluginDescription()
        .mainType(PluginType.GENERAL)
        .pluginIcon(app.aaps.core.ui.R.drawable.ic_generic_icon)
        .pluginName(R.string.virtual_glucagon_pump_name)
        .shortName(R.string.virtual_glucagon_pump_short_name)
        .description(R.string.virtual_glucagon_pump_description),
    aapsLogger, rh
), GlucagonPump {

    // Simulated reservoir, 1000 mcg by default
    private var reservoirMcg: Double = DEFAULT_RESERVOIR_MCG
    private var lastDeliveryTs: Long = 0L

    override val glucagonReservoirMcg: Double get() = reservoirMcg
    override val lastGlucagonDeliveryTimestamp: Long get() = lastDeliveryTs

    override fun isGlucagonPumpReady(): Boolean = isEnabled() && reservoirMcg >= MIN_DOSE_MCG

    override fun deliverGlucagon(doseMcg: Double): Boolean {
        if (!isEnabled()) {
            aapsLogger.warn(LTag.PUMP, "VirtualGlucagonPump: deliverGlucagon called but plugin is disabled")
            return false
        }
        if (doseMcg <= 0.0) {
            aapsLogger.warn(LTag.PUMP, "VirtualGlucagonPump: invalid dose $doseMcg mcg")
            return false
        }
        if (reservoirMcg < doseMcg) {
            aapsLogger.warn(LTag.PUMP, "VirtualGlucagonPump: insufficient reservoir (${"%.0f".format(reservoirMcg)} mcg) for dose ${"%.0f".format(doseMcg)} mcg")
            return false
        }

        val now = dateUtil.now()
        val bolus = BS(
            timestamp = now,
            utcOffset = TimeZone.getDefault().getOffset(now).toLong(),
            amount = doseMcg / 1000.0,   // mcg → mg
            type = BS.Type.GLUCAGON,
            isValid = true
        )

        return try {
            val result = persistenceLayer
                .insertOrUpdateBolus(bolus, Action.GLUCAGON_DOSE, Sources.GlucagonPump)
                .blockingGet()
            if (result.inserted.isNotEmpty()) {
                reservoirMcg -= doseMcg
                lastDeliveryTs = now
                aapsLogger.debug(LTag.PUMP, "VirtualGlucagonPump: delivered ${"%.0f".format(doseMcg)} mcg, reservoir=${"%.0f".format(reservoirMcg)} mcg")
                rxBus.send(EventNewHistoryData(now, false))
                true
            } else {
                aapsLogger.error(LTag.PUMP, "VirtualGlucagonPump: DB insert returned no inserted records")
                false
            }
        } catch (e: Exception) {
            aapsLogger.error(LTag.PUMP, "VirtualGlucagonPump: DB insert failed", e)
            false
        }
    }

    /** Refill simulator reservoir (for testing). */
    fun refillReservoir(mcg: Double) {
        reservoirMcg = mcg.coerceAtLeast(0.0)
    }

    companion object {
        const val DEFAULT_RESERVOIR_MCG = 1000.0   // 1 mg glucagon
        const val MIN_DOSE_MCG = 25.0
    }
}
