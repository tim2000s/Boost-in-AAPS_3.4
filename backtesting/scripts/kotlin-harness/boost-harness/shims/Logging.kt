package app.aaps.core.interfaces.logging

/**
 * Compile-time SHIMS of the AAPS logging types — only the surface SleepStateDetector references
 * (aapsLogger?.debug(LTag.APS, msg)). The harness passes a null logger, so debug is never called; these
 * exist only so the REAL SleepStateDetector.kt compiles standalone.
 */
enum class LTag { APS }

interface AAPSLogger {
    fun debug(tag: LTag, message: String)
}
