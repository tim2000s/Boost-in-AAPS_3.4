package app.aaps.plugins.aps.openAPSBoost

import app.aaps.core.data.model.HR
import com.google.common.truth.Truth.assertThat
import org.json.JSONObject
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.TestFactory
import java.io.File

/**
 * Data-driven regression tests for the exercise detection features.
 *
 * Each scenario is defined in a JSON file under
 * `plugins/aps/src/test/resources/exercise_scenarios/`.
 *
 * Two types of scenario are supported:
 *  - `hr_classification`  — tests [HrActivityCalculator.classify] fusion logic
 *  - `recovery_parameters` — tests the recovery `when` block parameter selection
 *
 * Note: Scenario files are read via the filesystem path `src/test/resources/exercise_scenarios/`
 * relative to the module root (same pattern as autotune tests in this module).
 */
class ExerciseRegressionTest {

    private val SCENARIO_DIR = "src/test/resources/exercise_scenarios"
    private val NOW = 1_700_000_000_000L
    private val WINDOW_MIN = 15

    // ─── JSON scenario loading ────────────────────────────────────────────────────

    private fun loadScenarios(type: String): List<Pair<String, JSONObject>> {
        val dir = File(SCENARIO_DIR)
        if (!dir.exists()) return emptyList()
        return dir.listFiles { f -> f.extension == "json" }
            ?.sorted()
            ?.mapNotNull { file ->
                val json = JSONObject(file.readText())
                if (json.getString("type") == type) Pair(file.name, json) else null
            }
            ?: emptyList()
    }

    // ─── HR zone label lookup ─────────────────────────────────────────────────────

    private fun hrZoneLabel(zone: HrActivityCalculator.HrZone): String = zone.label

    // ─── HR Classification scenarios ─────────────────────────────────────────────

    @TestFactory
    fun `HR classification scenarios`(): List<DynamicTest> {
        return loadScenarios("hr_classification").map { (fileName, json) ->
            val scenarioName = json.getString("scenario")
            val description = json.optString("description", scenarioName)

            DynamicTest.dynamicTest("[$scenarioName] $description") {
                val input = json.getJSONObject("input")
                val expected = json.getJSONObject("expected")

                val avgBpm: Double? = if (input.isNull("avgBpm")) null else input.getDouble("avgBpm")
                val hrMax = input.getInt("hrMax")
                val hrResting = input.getInt("hrResting")
                val stepsLast15Min = input.getInt("stepsLast15Min")
                val stressDetection = input.getBoolean("stressDetection")

                // Build HR readings: one reading 60s before NOW with the given BPM
                val hrReadings: List<HR> = if (avgBpm != null) {
                    listOf(
                        HR(
                            duration = 60_000L,
                            timestamp = NOW - 60_000L,
                            beatsPerMinute = avgBpm,
                            device = "regression_test",
                            isValid = true
                        )
                    )
                } else {
                    emptyList()
                }

                val result = HrActivityCalculator.classify(
                    hrReadings = hrReadings,
                    nowMillis = NOW,
                    hrWindowMinutes = WINDOW_MIN,
                    hrMax = hrMax,
                    hrResting = hrResting,
                    stepsLast15Min = stepsLast15Min,
                    stressDetection = stressDetection
                )

                val expectedState = expected.getString("exerciseState")
                val expectedZone = expected.getString("hrZone")
                val expectedConfidence = expected.getString("confidence")

                assertThat(result.exerciseState.name)
                    .isEqualTo(expectedState)
                assertThat(hrZoneLabel(result.hrZone))
                    .isEqualTo(expectedZone)
                assertThat(result.confidence.name)
                    .isEqualTo(expectedConfidence)
            }
        }
    }

    // ─── Recovery parameter scenarios ────────────────────────────────────────────

    private fun computeRecoveryParams(
        lastExerciseState: String,
        postExerciseRecoveryHours: Double,
        postExerciseRecoveryTarget: Double,
        postExerciseRecoveryScale: Double
    ): Triple<Long, Double, Double> {
        val (windowMultiplier, targetOffsetMgdl, scaleMultiplier) = when (lastExerciseState) {
            "VIGOROUS_AEROBIC" -> Triple(1.25, 0.0,  0.8)
            "RESISTANCE"       -> Triple(1.5,  10.0, 1.2)
            "LIGHT_AEROBIC"    -> Triple(0.5,  0.0,  1.4)
            else               -> Triple(1.0,  0.0,  1.0)
        }
        val recoveryMillis = (postExerciseRecoveryHours * 3_600_000L * windowMultiplier).toLong()
        val recoveryTargetMgdl = postExerciseRecoveryTarget + targetOffsetMgdl
        val activeRecoveryScale = (postExerciseRecoveryScale * scaleMultiplier).coerceIn(0.1, 1.0)
        return Triple(recoveryMillis, recoveryTargetMgdl, activeRecoveryScale)
    }

    @TestFactory
    fun `recovery parameter scenarios`(): List<DynamicTest> {
        return loadScenarios("recovery_parameters").map { (fileName, json) ->
            val scenarioName = json.getString("scenario")
            val description = json.optString("description", scenarioName)

            DynamicTest.dynamicTest("[$scenarioName] $description") {
                val input = json.getJSONObject("input")
                val expected = json.getJSONObject("expected")

                val exerciseState = input.getString("exerciseState")
                val baseHours = input.getDouble("baseRecoveryHours")
                val baseTarget = input.getDouble("baseTargetMgdl")
                val baseScale = input.getDouble("baseScale")

                val expectedWindowMin = expected.getInt("windowMinutes")
                val expectedTargetMgdl = expected.getDouble("targetMgdl")
                val expectedScale = expected.getDouble("scale")

                val (recoveryMillis, recoveryTargetMgdl, activeRecoveryScale) =
                    computeRecoveryParams(exerciseState, baseHours, baseTarget, baseScale)

                val actualWindowMin = recoveryMillis / 60_000L
                assertThat(actualWindowMin).isEqualTo(expectedWindowMin.toLong())
                assertThat(recoveryTargetMgdl).isWithin(0.001).of(expectedTargetMgdl)
                assertThat(activeRecoveryScale).isWithin(0.001).of(expectedScale)
            }
        }
    }
}
