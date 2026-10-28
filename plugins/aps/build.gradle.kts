plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.ksp)
    id("kotlin-android")
    id("android-module-dependencies")
    id("test-module-dependencies")
    id("jacoco-module-dependencies")
}

fun gitOutput(vararg args: String): String = try {
    val p = ProcessBuilder("git", *args).redirectErrorStream(true).start()
    p.inputStream.bufferedReader().readText().trim().also { p.waitFor() }
} catch (_: Exception) {
    "nogit"
}

android {
    namespace = "app.aaps.plugins.aps"
    buildFeatures { buildConfig = true }
    defaultConfig {
        // Boost version plus the branch and commit it was built from, so a build seen in Nightscout
        // can be traced even when its hash is later rewritten (see Versions.boostVersion).
        buildConfigField(
            "String", "BOOST_VERSION",
            "\"${Versions.boostVersion}+${gitOutput("rev-parse", "--abbrev-ref", "HEAD")}.${gitOutput("rev-parse", "--short=10", "HEAD")}\""
        )
    }
}

dependencies {
    implementation(project(":core:data"))
    implementation(project(":core:interfaces"))
    implementation(project(":core:keys"))
    implementation(project(":core:nssdk"))
    implementation(project(":core:objects"))
    implementation(project(":core:utils"))
    implementation(project(":core:ui"))
    implementation(project(":core:validators"))

    testImplementation(project(":pump:virtual"))
    testImplementation(project(":shared:tests"))

    api(libs.androidx.appcompat)
    api(libs.androidx.swiperefreshlayout)
    api(libs.androidx.gridlayout)
    api(kotlin("reflect"))

    // APS (it should be androidTestImplementation but it doesn't work)
    api(libs.org.mozilla.rhino)

    //Logger
    api(libs.org.slf4j.api)

    // Health Connect — for HR ingest path (2026-06-03)
    implementation(libs.androidx.health.connect.client)

    ksp(libs.com.google.dagger.android.processor)
}