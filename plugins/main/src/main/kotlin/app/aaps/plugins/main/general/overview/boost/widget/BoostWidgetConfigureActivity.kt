package app.aaps.plugins.main.general.overview.boost.widget

import android.appwidget.AppWidgetManager
import android.content.Intent
import android.os.Bundle
import android.widget.SeekBar
import app.aaps.core.keys.BooleanComposedKey
import app.aaps.core.keys.IntComposedKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.plugins.main.databinding.BoostWidgetConfigureBinding
import dagger.android.DaggerActivity
import javax.inject.Inject

/**
 * Configuration screen for the [BoostWidget].
 */
class BoostWidgetConfigureActivity : DaggerActivity() {

    @Inject lateinit var preferences: Preferences

    private var appWidgetId = AppWidgetManager.INVALID_APPWIDGET_ID
    private lateinit var binding: BoostWidgetConfigureBinding

    public override fun onCreate(icicle: Bundle?) {
        super.onCreate(icicle)

        setResult(RESULT_CANCELED)

        binding = BoostWidgetConfigureBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.seekBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onStopTrackingTouch(seekBar: SeekBar) {}
            override fun onStartTrackingTouch(seekBar: SeekBar) {}
            override fun onProgressChanged(seekBar: SeekBar, progress: Int, fromUser: Boolean) {
                preferences.put(IntComposedKey.WidgetOpacity, appWidgetId, value = progress)
                BoostWidget.updateWidget(this@BoostWidgetConfigureActivity, "BoostWidgetConfigure")
            }
        })

        binding.closeLayout.close.setOnClickListener {
            val resultValue = Intent()
            resultValue.putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
            setResult(RESULT_OK, resultValue)
            finish()
        }

        binding.useBlack.setOnCheckedChangeListener { _, value ->
            preferences.put(BooleanComposedKey.WidgetUseBlack, appWidgetId, value = value)
            BoostWidget.updateWidget(this@BoostWidgetConfigureActivity, "BoostWidgetConfigure")
        }

        appWidgetId = intent.extras?.getInt(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID) ?: AppWidgetManager.INVALID_APPWIDGET_ID

        if (appWidgetId == AppWidgetManager.INVALID_APPWIDGET_ID) {
            finish()
            return
        }

        binding.seekBar.progress = preferences.get(IntComposedKey.WidgetOpacity, appWidgetId)
        binding.useBlack.isChecked = preferences.get(BooleanComposedKey.WidgetUseBlack, appWidgetId)
    }

    override fun onDestroy() {
        super.onDestroy()
        binding.seekBar.setOnSeekBarChangeListener(null)
        binding.closeLayout.close.setOnClickListener(null)
        binding.useBlack.setOnCheckedChangeListener(null)
    }
}
