package app.aaps.wear.complications

import android.app.PendingIntent
import androidx.wear.watchface.complications.data.ComplicationData
import androidx.wear.watchface.complications.data.ComplicationType
import androidx.wear.watchface.complications.data.PlainComplicationText
import androidx.wear.watchface.complications.data.WeightedElementsComplicationData
import app.aaps.core.interfaces.logging.LTag
import dagger.android.AndroidInjection

/**
 * TIR (Time-In-Range) Complication — WEIGHTED_ELEMENTS.
 *
 * Renders the last-24h Time-In-Range distribution as a proportional, multi-colour pie/donut ring.
 * The 5 percentages arrive from the phone via [app.aaps.core.interfaces.rx.weardata.EventData.Status.tirWeights]
 * ("vlow,low,inrange,high,vhigh"); each becomes a weighted element with its fixed band colour.
 * Display-only; never affects dosing.
 */
class TirWeightedComplication : ModernBaseComplicationProviderService() {

    override fun onCreate() {
        AndroidInjection.inject(this)
        super.onCreate()
    }

    override fun buildComplicationData(
        type: ComplicationType,
        data: app.aaps.wear.data.ComplicationData,
        complicationPendingIntent: PendingIntent
    ): ComplicationData? {
        if (type != ComplicationType.WEIGHTED_ELEMENTS) {
            aapsLogger.warn(LTag.WEAR, "TirWeightedComplication unexpected type: $type")
            return null
        }

        val weights = parseWeights(data.statusData.tirWeights)
        val elements = if (weights != null && weights.any { it > 0f }) {
            BAND_COLORS.indices.map { i ->
                WeightedElementsComplicationData.Element(weight = weights.getOrElse(i) { 0f }, color = BAND_COLORS[i])
            }
        } else {
            // no data yet → single neutral-grey ring so the slot is visibly populated
            listOf(WeightedElementsComplicationData.Element(weight = 1f, color = 0xFF455A64.toInt()))
        }

        val inRangePct = weights?.getOrNull(2)?.let { "${it.toInt()}%" } ?: "--"
        return WeightedElementsComplicationData.Builder(
            elements = elements,
            contentDescription = PlainComplicationText.Builder(text = "Time in range $inRangePct").build()
        )
            .setText(PlainComplicationText.Builder(text = inRangePct).build())
            .setTitle(PlainComplicationText.Builder(text = "TIR").build())
            .setTapAction(complicationPendingIntent)
            .build()
    }

    private fun parseWeights(raw: String): List<Float>? {
        if (raw.isBlank()) return null
        val parts = raw.split(",").mapNotNull { it.trim().toFloatOrNull() }
        return if (parts.size == BAND_COLORS.size) parts else null
    }

    override fun getProviderCanonicalName(): String = TirWeightedComplication::class.java.canonicalName!!

    companion object {
        // vLow, low, inRange, high, vHigh — must match the TIR colour scheme on the faces.
        private val BAND_COLORS = intArrayOf(
            0xFFC62828.toInt(), // very low  (dark red)
            0xFFFF9F45.toInt(), // low       (orange)
            0xFF41C97B.toInt(), // in range  (green)
            0xFFFFC233.toInt(), // high      (amber)
            0xFFFF5252.toInt()  // very high (red)
        )
    }
}
