import org.gradle.api.JavaVersion
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

@Suppress("ConstPropertyName")
object Versions {

    // On change edit aaps-ci.yml
    const val appVersion = "3.4.2.6"
    const val versionCode = 1500

    // Boost version, uploaded to Nightscout as apsConfiguration.boostVersion with the branch and
    // short hash appended at build time (e.g. 7.4.0+Boost-V7-shadow.9632514dfa). Numbering:
    // <engine>.<minor>.<patch>, engine 6 on dev/master (which share a number), 6.x.x.E on
    // Boost-endurance, 7 on the V7-shadow vehicle. Raise minor for any change to dosing behaviour,
    // patch for fixes and telemetry that leave dosing unchanged. Set by hand on each branch.
    const val boostVersion = "6.1.1.E"

    const val compileSdk = 36
    const val minSdk = 31
    const val targetSdk = 32
    const val wearMinSdk = 30
    const val wearTargetSdk = 30

    val javaVersion = JavaVersion.VERSION_21
    val jvmTarget = JvmTarget.JVM_21
    const val jacoco = "0.8.11"
}
