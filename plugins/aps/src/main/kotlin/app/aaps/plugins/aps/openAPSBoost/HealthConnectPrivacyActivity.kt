package app.aaps.plugins.aps.openAPSBoost

import android.app.Activity
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * HealthConnectPrivacyActivity — required by Health Connect's permission flow.
 *
 * Health Connect refuses to surface the permission request UI unless the app
 * declares an Activity it can deep-link into for "Why does this app want this
 * data?". Two intent filters route here, one for Android 14+ and one for older
 * Android versions (see plugins/aps/src/main/AndroidManifest.xml).
 *
 * The Activity itself just renders a plain-text explanation of why AAPS reads
 * heart rate. No outbound network call, no analytics, no data leaves the device.
 */
class HealthConnectPrivacyActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        title = "AndroidAPS — Heart rate use"

        val padding = (resources.displayMetrics.density * 20).toInt()
        val text = TextView(this).apply {
            setPadding(padding, padding, padding, padding)
            textSize = 16f
            text = """
                Why AndroidAPS reads heart rate

                AndroidAPS uses heart rate data to:

                • Detect when you are asleep, so it can engage Night Mode and
                  suppress unsafe SMBs overnight without relying purely on a
                  configured clock window.

                • Detect activity / exercise patterns alongside step counts,
                  so the algorithm can reduce dosing during workouts and
                  raise the target during resistance training.

                • Learn your resting heart rate over a rolling 28-day window
                  for more accurate sleep-state detection and Karvonen heart
                  rate reserve calculations for exercise classification.

                What happens to the data

                • Heart rate samples stay on this device.
                • Nothing is uploaded anywhere by this part of AndroidAPS,
                  beyond what you already share via your existing Nightscout
                  configuration (if any).
                • You can revoke this permission at any time from the
                  Health Connect app.
            """.trimIndent()
        }

        val scroll = ScrollView(this).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            addView(text)
        }

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.TOP
            addView(scroll)
        }

        setContentView(root)
    }
}
