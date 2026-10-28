package app.aaps.pump.glucagon

import android.content.Context
import androidx.preference.Preference
import androidx.preference.PreferenceCategory
import androidx.preference.PreferenceManager
import androidx.preference.PreferenceScreen
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
import app.aaps.core.keys.IntKey
import app.aaps.core.keys.IntNonKey
import app.aaps.core.keys.LongNonKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.core.validators.preferences.AdaptiveIntPreference
import java.util.TimeZone
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Virtual glucagon pump for testing the bihormonal closed-loop without physical hardware.
 *
 * Implements [GlucagonPump], and is found by [GlucagonAlgorithmPlugin] through
 * `activePlugin.getSpecificPluginsListByInterface(GlucagonPump::class.java)`.
 *
 * The reservoir level and fill time are kept in preferences so a restart does not refill it; the
 * settings screen sets the fill amount and refills. Delivered doses are stored as BS(type=GLUCAGON)
 * records so GOB can be calculated. Delivery is synchronous; a real driver would go through a
 * command queue and confirm each dose from pump history.
 *
 * Amount encoding: BS.amount is stored in mg (1.0 = 1 mg = 1000 mcg).
 */
@Singleton
class VirtualGlucagonPump @Inject constructor(
    aapsLogger: AAPSLogger,
    rh: ResourceHelper,
    private val rxBus: RxBus,
    private val persistenceLayer: PersistenceLayer,
    private val dateUtil: DateUtil,
    private val preferences: Preferences
) : PluginBase(
    PluginDescription()
        .mainType(PluginType.GENERAL)
        .pluginIcon(app.aaps.core.ui.R.drawable.ic_generic_icon)
        .pluginName(R.string.virtual_glucagon_pump_name)
        .shortName(R.string.virtual_glucagon_pump_short_name)
        .description(R.string.virtual_glucagon_pump_description)
        .preferencesId(PluginDescription.PREFERENCE_SCREEN),
    aapsLogger, rh
), GlucagonPump {

    override fun onStart() {
        super.onStart()
        // An install that never refilled has no fill time; count from now so the age reminder can run
        if (preferences.get(LongNonKey.GlucagonReservoirFilledAt) == 0L) preferences.put(LongNonKey.GlucagonReservoirFilledAt, dateUtil.now())
    }

    override val glucagonReservoirMcg: Double get() = preferences.get(IntNonKey.GlucagonReservoirMcg).toDouble()
    override val glucagonReservoirFilledAt: Long get() = preferences.get(LongNonKey.GlucagonReservoirFilledAt)

    override fun isGlucagonPumpReady(): Boolean = isEnabled() && glucagonReservoirMcg >= MIN_DOSE_MCG

    override fun deliverGlucagon(doseMcg: Double): Boolean {
        if (!isEnabled()) {
            aapsLogger.warn(LTag.PUMP, "VirtualGlucagonPump: deliverGlucagon called but plugin is disabled")
            return false
        }
        if (doseMcg <= 0.0) {
            aapsLogger.warn(LTag.PUMP, "VirtualGlucagonPump: invalid dose $doseMcg mcg")
            return false
        }
        val reservoirMcg = glucagonReservoirMcg
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
                preferences.put(IntNonKey.GlucagonReservoirMcg, (reservoirMcg - doseMcg).toInt())
                aapsLogger.debug(LTag.PUMP, "VirtualGlucagonPump: delivered ${"%.0f".format(doseMcg)} mcg, reservoir=${"%.0f".format(glucagonReservoirMcg)} mcg")
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

    /** Fill the reservoir to the configured amount and record the fill time. */
    fun refillReservoir() {
        preferences.put(IntNonKey.GlucagonReservoirMcg, preferences.get(IntKey.GlucagonReservoirFillMcg))
        preferences.put(LongNonKey.GlucagonReservoirFilledAt, dateUtil.now())
        aapsLogger.debug(LTag.PUMP, "VirtualGlucagonPump: refilled to ${glucagonReservoirMcg.toInt()} mcg")
    }

    override fun addPreferenceScreen(preferenceManager: PreferenceManager, parent: PreferenceScreen, context: Context, requiredKey: String?) {
        if (requiredKey != null && requiredKey != "virtual_glucagon_pump_settings") return
        val category = PreferenceCategory(context)
        parent.addPreference(category)
        category.apply {
            key = "virtual_glucagon_pump_settings"
            title = rh.gs(R.string.virtual_glucagon_pump_name)
            initialExpandedChildrenCount = 0
            addPreference(AdaptiveIntPreference(ctx = context, intKey = IntKey.GlucagonReservoirFillMcg, dialogMessage = R.string.virtual_glucagon_fill_summary, title = R.string.virtual_glucagon_fill_title))
            addPreference(Preference(context).apply {
                key = "virtual_glucagon_refill"
                title = rh.gs(R.string.virtual_glucagon_refill_title)
                summary = rh.gs(R.string.virtual_glucagon_refill_summary, glucagonReservoirMcg)
                setOnPreferenceClickListener {
                    refillReservoir()
                    summary = rh.gs(R.string.virtual_glucagon_refill_summary, glucagonReservoirMcg)
                    true
                }
            })
        }
    }

    companion object {
        const val MIN_DOSE_MCG = 25.0
    }
}
