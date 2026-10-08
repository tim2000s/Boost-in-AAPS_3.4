/**
 * Boost engine harness (2026-07-20) — drives the REAL shipping Kotlin engines from a JSON request so the
 * backtest and the APK run identical code ("build and test once"). Reads one request from stdin, runs the
 * requested engine over the cycle batch (state carried across cycles as on-device), writes JSON to stdout.
 * The engine .kt files are the ACTUAL sources under plugins/aps — compiled here, not copied. See HARNESS_SPEC.md.
 */
import app.aaps.plugins.aps.openAPSBoost.SleepStateDetector
import app.aaps.core.data.model.HR
import org.json.JSONArray
import org.json.JSONObject

private fun JSONObject.optDoubleOrNull(k: String): Double? = if (isNull(k) || !has(k)) null else getDouble(k)

fun main() {
    val req = JSONObject(System.`in`.readBytes().decodeToString())
    val engine = req.getString("engine")
    val cy = req.getJSONArray("cycles")
    val out = JSONArray()

    when (engine) {
        // ---- sleep state machine (real SleepStateDetector, via minimal shims for HR/AAPSLogger/LTag) ----
        "sleep" -> {
            var state = SleepStateDetector.State()
            for (i in 0 until cy.length()) {
                val c = cy.getJSONObject(i)
                val hrs = ArrayList<HR>()
                if (c.has("hr")) { val a = c.getJSONArray("hr"); for (j in 0 until a.length()) {
                    val h = a.getJSONObject(j)
                    hrs.add(HR(duration = h.optLong("duration", 300000L), timestamp = h.getLong("timestamp"),
                        beatsPerMinute = h.getDouble("bpm"), device = "harness")) } }
                val inp = SleepStateDetector.Inputs(
                    nowMs = c.getLong("nowMs"), minuteOfDay = c.getInt("minuteOfDay"),
                    hrReadings = hrs, hrResting = c.getInt("hrResting"),
                    stepsLast15Min = c.getInt("stepsLast15Min"), mlMealLikely = c.optDoubleOrNull("mlMealLikely"),
                    nightStartMin = c.getInt("nightStartMin"), nightEndMin = c.getInt("nightEndMin"),
                    stepsToday = c.optInt("stepsToday", -1), sleepInStepsThreshold = c.optInt("sleepInStepsThreshold", 0))
                val res = SleepStateDetector.evaluate(state, inp, null)
                state = res.newState
                out.put(JSONObject().put("i", i).put("state", res.newState.state.name)
                    .put("transitioned", res.transitioned).put("wakeReason", res.wakeReason ?: JSONObject.NULL))
            }
        }
        else -> { System.err.println("unknown engine: $engine"); kotlin.system.exitProcess(2) }
    }
    println(JSONObject().put("engine", engine).put("schema", 1).put("results", out))
}
