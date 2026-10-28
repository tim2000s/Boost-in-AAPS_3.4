package app.aaps.core.data.model

/**
 * Compile-time SHIM of the AAPS HR type — just the fields SleepStateDetector reads (isValid, timestamp,
 * duration, beatsPerMinute). Lets the REAL SleepStateDetector.kt compile standalone in the harness; the HR
 * values come from the scenario JSON. NOT the real HR (that drags in IDs/room deps we don't need offline).
 */
data class HR(
    var duration: Long,
    var timestamp: Long,
    var beatsPerMinute: Double,
    var device: String = "harness",
    var isValid: Boolean = true,
)
