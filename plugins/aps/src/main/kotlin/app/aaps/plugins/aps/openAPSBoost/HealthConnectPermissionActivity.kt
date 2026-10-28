package app.aaps.plugins.aps.openAPSBoost

import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.ActivityResultLauncher
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.StepsRecord

/**
 * HealthConnectPermissionActivity — single-purpose Activity that requests the
 * READ_HEART_RATE permission from Health Connect and finishes.
 *
 * Wired from a Boost Night Mode preference (see plugin addPreferenceScreen).
 *
 * Why an Activity rather than running from the preference fragment directly?
 * registerForActivityResult must be called BEFORE the host moves past
 * onStart, which is awkward to retrofit into AAPS's existing PluginBase
 * preference-injection pattern. This Activity exists solely to host the
 * launcher; it launches the request immediately in onCreate and finishes
 * once Android returns a result.
 *
 * If Health Connect isn't available on the device, the Activity shows a
 * toast explaining and finishes without launching anything.
 */
class HealthConnectPermissionActivity : ComponentActivity() {

    private lateinit var requestLauncher: ActivityResultLauncher<Set<String>>
    private val requiredPermissions = setOf(
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(StepsRecord::class)   // Boost activity-load shadow (2026-06-16)
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Register before onStart per ActivityResult API contract.
        requestLauncher = registerForActivityResult(
            PermissionController.createRequestPermissionResultContract()
        ) { granted ->
            val msg = if (granted.containsAll(requiredPermissions)) {
                "Health Connect: Read Heart Rate granted"
            } else {
                "Health Connect: permission denied — heart rate will not be ingested"
            }
            Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
            finish()
        }

        when (HealthConnectClient.getSdkStatus(this)) {
            HealthConnectClient.SDK_UNAVAILABLE -> {
                Toast.makeText(
                    this,
                    "Health Connect is not available on this device.",
                    Toast.LENGTH_LONG
                ).show()
                finish()
                return
            }
            HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> {
                Toast.makeText(
                    this,
                    "Install or update the Health Connect app to grant heart rate access.",
                    Toast.LENGTH_LONG
                ).show()
                finish()
                return
            }
        }

        try {
            requestLauncher.launch(requiredPermissions)
        } catch (t: Throwable) {
            Toast.makeText(
                this,
                "Could not open Health Connect permission screen: ${t.message}",
                Toast.LENGTH_LONG
            ).show()
            finish()
        }
    }
}
