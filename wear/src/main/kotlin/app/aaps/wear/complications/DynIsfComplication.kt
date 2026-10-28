package app.aaps.wear.complications

import android.app.PendingIntent
import androidx.wear.watchface.complications.data.ComplicationData
import androidx.wear.watchface.complications.data.ComplicationType
import androidx.wear.watchface.complications.data.PlainComplicationText
import androidx.wear.watchface.complications.data.ShortTextComplicationData
import app.aaps.core.interfaces.logging.LTag
import dagger.android.AndroidInjection

/**
 * DynISF Complication
 *
 * Shows the current dynamic ISF / variable sensitivity (variable_sens from the last APS run),
 * formatted on the phone in the user's profile units (mg/dl/U or mmol/L/U). Display-only — this
 * value never influences dosing. Title is "ISF"; text is the value (or "--" when unavailable).
 * Tap opens the main menu.
 */
class DynIsfComplication : ModernBaseComplicationProviderService() {

    // Not derived from DaggerService, do injection here
    override fun onCreate() {
        AndroidInjection.inject(this)
        super.onCreate()
    }

    override fun buildComplicationData(
        type: ComplicationType,
        data: app.aaps.wear.data.ComplicationData,
        complicationPendingIntent: PendingIntent
    ): ComplicationData? {
        return when (type) {
            ComplicationType.SHORT_TEXT -> {
                val sens = data.statusData.variableSens.ifEmpty { "--" }
                ShortTextComplicationData.Builder(
                    text = PlainComplicationText.Builder(text = sens).build(),
                    contentDescription = PlainComplicationText.Builder(text = "DynISF $sens").build()
                )
                    .setTitle(PlainComplicationText.Builder(text = "ISF").build())
                    .setTapAction(complicationPendingIntent)
                    .build()
            }

            else                        -> {
                aapsLogger.warn(LTag.WEAR, "Unexpected complication type $type")
                null
            }
        }
    }

    override fun getProviderCanonicalName(): String = DynIsfComplication::class.java.canonicalName!!
    override fun getComplicationAction(): ComplicationAction = ComplicationAction.MENU
}
