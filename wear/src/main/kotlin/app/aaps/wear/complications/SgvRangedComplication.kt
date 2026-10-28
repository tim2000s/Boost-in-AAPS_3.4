package app.aaps.wear.complications

import android.app.PendingIntent
import androidx.wear.watchface.complications.data.ComplicationData
import androidx.wear.watchface.complications.data.ComplicationType
import androidx.wear.watchface.complications.data.CountUpTimeReference
import androidx.wear.watchface.complications.data.PlainComplicationText
import androidx.wear.watchface.complications.data.RangedValueComplicationData
import androidx.wear.watchface.complications.data.ShortTextComplicationData
import androidx.wear.watchface.complications.data.TimeDifferenceComplicationText
import androidx.wear.watchface.complications.data.TimeDifferenceStyle
import app.aaps.core.interfaces.logging.LTag
import app.aaps.core.interfaces.sharedPreferences.SP
import app.aaps.wear.interaction.utils.SmallestDoubleString
import dagger.android.AndroidInjection
import java.time.Instant
import java.util.concurrent.TimeUnit
import javax.inject.Inject

/**
 * SGV (Sensor Glucose Value) — RANGED_VALUE variant.
 *
 * Identical data to [SgvComplication] but emits the BG as a numeric RANGED_VALUE (mg/dl, clamped
 * to [BG_MIN]..[BG_MAX]) alongside the display text (BG + arrow) and title (delta + auto-updating
 * time). The numeric value lets a Watch Face Format face threshold/colour by Time-In-Range and
 * draw a BG-proportional ring — neither of which is possible from a SHORT_TEXT-only complication.
 * Display-only; never affects dosing.
 */
class SgvRangedComplication : ModernBaseComplicationProviderService() {

    @Inject lateinit var sp: SP

    override fun onCreate() {
        AndroidInjection.inject(this)
        super.onCreate()
    }

    override fun buildComplicationData(
        type: ComplicationType,
        data: app.aaps.wear.data.ComplicationData,
        complicationPendingIntent: PendingIntent
    ): ComplicationData? {
        val bgData = data.bgData
        val mainText = bgData.sgvString + bgData.slopeArrow + "\uFE0E"
        val title = buildDeltaAndTimeTitle(bgData)

        return when (type) {
            ComplicationType.RANGED_VALUE -> {
                val value = bgData.sgv.toFloat().coerceIn(BG_MIN, BG_MAX)
                RangedValueComplicationData.Builder(
                    value = value,
                    min = BG_MIN,
                    max = BG_MAX,
                    contentDescription = PlainComplicationText.Builder(text = "Glucose $mainText").build()
                )
                    .setText(PlainComplicationText.Builder(text = mainText).build())
                    .setTitle(title)
                    .setTapAction(complicationPendingIntent)
                    .build()
            }

            ComplicationType.SHORT_TEXT   -> {
                ShortTextComplicationData.Builder(
                    text = PlainComplicationText.Builder(text = mainText).build(),
                    contentDescription = PlainComplicationText.Builder(text = "Glucose $mainText").build()
                )
                    .setTitle(title)
                    .setTapAction(complicationPendingIntent)
                    .build()
            }

            else                          -> {
                aapsLogger.warn(LTag.WEAR, "SgvRangedComplication unexpected type: $type")
                null
            }
        }
    }

    private fun buildDeltaAndTimeTitle(bgData: app.aaps.core.interfaces.rx.weardata.EventData.SingleBg): TimeDifferenceComplicationText {
        val rawDelta = if (sp.getBoolean(app.aaps.wear.R.string.key_show_detailed_delta, false)) bgData.deltaDetailed else bgData.delta
        val useUnicode = sp.getBoolean("complication_unicode", true)
        val deltaSymbol = if (useUnicode) "\u0394" else ""
        val deltaText = deltaSymbol + SmallestDoubleString(rawDelta).minimise(4)
        return TimeDifferenceComplicationText.Builder(
            style = TimeDifferenceStyle.SHORT_SINGLE_UNIT,
            countUpTimeReference = CountUpTimeReference(Instant.ofEpochMilli(bgData.timeStamp))
        )
            .setMinimumTimeUnit(TimeUnit.MINUTES)
            .setText("^1 $deltaText")
            .build()
    }

    override fun getProviderCanonicalName(): String = SgvRangedComplication::class.java.canonicalName!!

    companion object {
        // BG range the ring spans (mg/dl). Colour thresholds (TIR) are applied face-side on the value.
        const val BG_MIN = 40f
        const val BG_MAX = 350f
    }
}
