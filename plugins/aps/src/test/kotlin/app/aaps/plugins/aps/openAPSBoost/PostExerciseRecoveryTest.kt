package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.CsvSource

/**
 * Unit tests for the post-exercise recovery parameter calculation logic.
 *
 * The `when (lastExerciseStateAtTransition)` block in [OpenAPSBoostPlugin.invoke] is
 * extracted here as a pure function for isolated testing, mirroring the production logic
 * exactly.  No plugin instantiation is needed.
 *
 * Production code reference (OpenAPSBoostPlugin.kt ~line 756):
 *
 *   val (windowMultiplier, targetOffsetMgdl, scaleMultiplier) = when (lastExerciseStateAtTransition) {
 *       "VIGOROUS_AEROBIC" -> Triple(1.25, 0.0,  0.8)
 *       "RESISTANCE"       -> Triple(1.5,  10.0, 1.2)
 *       "LIGHT_AEROBIC"    -> Triple(0.5,  0.0,  1.4)
 *       else               -> Triple(1.0,  0.0,  1.0)
 *   }
 *   val recoveryMillis = (postExerciseRecoveryHours * 3600_000L * windowMultiplier).toLong()
 *   val recoveryTargetMgdl = postExerciseRecoveryTarget + targetOffsetMgdl
 *   activeRecoveryScale = (postExerciseRecoveryScale * scaleMultiplier).coerceIn(0.1, 1.0)
 */
class PostExerciseRecoveryTest {

    // ─── Mirror of the production `when` block ───────────────────────────────────

    data class RecoveryParams(
        val recoveryMillis: Long,
        val recoveryTargetMgdl: Double,
        val activeRecoveryScale: Double
    )

    private fun computeRecoveryParams(
        lastExerciseState: String,
        postExerciseRecoveryHours: Double,
        postExerciseRecoveryTarget: Double,
        postExerciseRecoveryScale: Double
    ): RecoveryParams {
        val (windowMultiplier, targetOffsetMgdl, scaleMultiplier) = when (lastExerciseState) {
            "VIGOROUS_AEROBIC" -> Triple(1.25, 0.0,  0.8)
            "RESISTANCE"       -> Triple(1.5,  10.0, 1.2)
            "LIGHT_AEROBIC"    -> Triple(0.5,  0.0,  1.4)
            else               -> Triple(1.0,  0.0,  1.0)
        }
        val recoveryMillis = (postExerciseRecoveryHours * 3600_000L * windowMultiplier).toLong()
        val recoveryTargetMgdl = postExerciseRecoveryTarget + targetOffsetMgdl
        val activeRecoveryScale = (postExerciseRecoveryScale * scaleMultiplier).coerceIn(0.1, 1.0)
        return RecoveryParams(recoveryMillis, recoveryTargetMgdl, activeRecoveryScale)
    }

    // ─── Recovery parameter tests ─────────────────────────────────────────────────

    // Baseline inputs used across all recovery parameter tests
    private val BASE_HOURS = 2.0
    private val BASE_TARGET = 144.0
    private val BASE_SCALE = 0.5

    @Test fun `VIGOROUS_AEROBIC - window 2 times 1_25 = 150 min, target unchanged, scale 0_4`() {
        val p = computeRecoveryParams("VIGOROUS_AEROBIC", BASE_HOURS, BASE_TARGET, BASE_SCALE)
        // 2.0 * 1.25 * 3600000 = 9000000 ms = 150 min
        assertThat(p.recoveryMillis).isEqualTo(9_000_000L)
        assertThat(p.recoveryTargetMgdl).isWithin(0.001).of(144.0)
        // (0.5 * 0.8).coerceIn(0.1, 1.0) = 0.4
        assertThat(p.activeRecoveryScale).isWithin(0.001).of(0.4)
    }

    @Test fun `RESISTANCE - window 2 times 1_5 = 180 min, target 144 + 10 = 154, scale 0_6`() {
        val p = computeRecoveryParams("RESISTANCE", BASE_HOURS, BASE_TARGET, BASE_SCALE)
        // 2.0 * 1.5 * 3600000 = 10800000 ms = 180 min
        assertThat(p.recoveryMillis).isEqualTo(10_800_000L)
        assertThat(p.recoveryTargetMgdl).isWithin(0.001).of(154.0)
        // (0.5 * 1.2).coerceIn(0.1, 1.0) = 0.6
        assertThat(p.activeRecoveryScale).isWithin(0.001).of(0.6)
    }

    @Test fun `LIGHT_AEROBIC - window 2 times 0_5 = 60 min, target unchanged, scale 0_7`() {
        val p = computeRecoveryParams("LIGHT_AEROBIC", BASE_HOURS, BASE_TARGET, BASE_SCALE)
        // 2.0 * 0.5 * 3600000 = 3600000 ms = 60 min
        assertThat(p.recoveryMillis).isEqualTo(3_600_000L)
        assertThat(p.recoveryTargetMgdl).isWithin(0.001).of(144.0)
        // (0.5 * 1.4).coerceIn(0.1, 1.0) = 0.7
        assertThat(p.activeRecoveryScale).isWithin(0.001).of(0.7)
    }

    @Test fun `ACTIVE else branch - window 2 times 1_0 = 120 min, target unchanged, scale 0_5`() {
        val p = computeRecoveryParams("ACTIVE", BASE_HOURS, BASE_TARGET, BASE_SCALE)
        // 2.0 * 1.0 * 3600000 = 7200000 ms = 120 min
        assertThat(p.recoveryMillis).isEqualTo(7_200_000L)
        assertThat(p.recoveryTargetMgdl).isWithin(0.001).of(144.0)
        assertThat(p.activeRecoveryScale).isWithin(0.001).of(0.5)
    }

    @Test fun `MODERATE_AEROBIC else branch - same as ACTIVE`() {
        val p = computeRecoveryParams("MODERATE_AEROBIC", BASE_HOURS, BASE_TARGET, BASE_SCALE)
        assertThat(p.recoveryMillis).isEqualTo(7_200_000L)
        assertThat(p.recoveryTargetMgdl).isWithin(0.001).of(144.0)
        assertThat(p.activeRecoveryScale).isWithin(0.001).of(0.5)
    }

    @Test fun `scale coerceIn ensures minimum of 0_1`() {
        // With a very small base scale, the result is coerced to at least 0.1
        val p = computeRecoveryParams("VIGOROUS_AEROBIC", BASE_HOURS, BASE_TARGET, postExerciseRecoveryScale = 0.05)
        // (0.05 * 0.8).coerceIn(0.1, 1.0) = 0.04.coerceIn(0.1,1.0) = 0.1
        assertThat(p.activeRecoveryScale).isWithin(0.001).of(0.1)
    }

    @Test fun `scale coerceIn ensures maximum of 1_0`() {
        // With a large base scale, the result is coerced to at most 1.0
        val p = computeRecoveryParams("RESISTANCE", BASE_HOURS, BASE_TARGET, postExerciseRecoveryScale = 1.0)
        // (1.0 * 1.2).coerceIn(0.1, 1.0) = 1.0
        assertThat(p.activeRecoveryScale).isWithin(0.001).of(1.0)
    }

    // ─── Exercise state set membership ───────────────────────────────────────────

    private val exerciseStateSet = setOf("ACTIVE", "VIGOROUS_AEROBIC", "MODERATE_AEROBIC", "LIGHT_AEROBIC", "RESISTANCE")

    @ParameterizedTest
    @CsvSource(
        "ACTIVE",
        "VIGOROUS_AEROBIC",
        "MODERATE_AEROBIC",
        "LIGHT_AEROBIC",
        "RESISTANCE"
    )
    fun `active states are in exerciseStateSet`(state: String) {
        assertThat(state in exerciseStateSet).isTrue()
    }

    @ParameterizedTest
    @CsvSource(
        "INACTIVE",
        "STRESS",
        "normal",
        "none"
    )
    fun `inactive states are not in exerciseStateSet`(state: String) {
        assertThat(state in exerciseStateSet).isFalse()
    }

    @Test fun `empty string is not in exerciseStateSet`() {
        assertThat("" in exerciseStateSet).isFalse()
    }

    // ─── Transition detection logic ───────────────────────────────────────────────

    /**
     * Pure function mirroring the transition detection block in [OpenAPSBoostPlugin.invoke].
     *
     * Returns a [TransitionResult] describing what the plugin would do at each transition.
     */
    data class TransitionResult(
        val exerciseStarted: Boolean,      // exerciseStartTime was set (false→true)
        val recoveryTriggered: Boolean,    // recovery window was opened (true→false with sufficient duration)
        val recoverySkipped: Boolean,      // exercise was too brief (true→false but duration < minDuration)
        val lastStateUpdated: Boolean      // lastExerciseStateAtTransition was updated (while active)
    )

    private fun simulateTransition(
        wasExerciseActive: Boolean,
        isCurrentlyActive: Boolean,
        exerciseStartTime: Long,
        now: Long,
        postExerciseMinDuration: Int = 10
    ): TransitionResult {
        val exerciseDurationMin = if (wasExerciseActive) (now - exerciseStartTime) / 60_000L else 0L

        val exerciseStarted = isCurrentlyActive && !wasExerciseActive
        val transitionToInactive = !isCurrentlyActive && wasExerciseActive
        val recoveryTriggered = transitionToInactive && exerciseDurationMin >= postExerciseMinDuration
        val recoverySkipped = transitionToInactive && exerciseDurationMin < postExerciseMinDuration
        val lastStateUpdated = isCurrentlyActive

        return TransitionResult(
            exerciseStarted = exerciseStarted,
            recoveryTriggered = recoveryTriggered,
            recoverySkipped = recoverySkipped,
            lastStateUpdated = lastStateUpdated
        )
    }

    private val BASE_NOW = 1_700_000_000_000L
    private val TEN_MINUTES_MS = 10 * 60_000L
    private val FIVE_MINUTES_MS = 5 * 60_000L

    @Test fun `false to true - exercise start sets exerciseStartTime`() {
        val result = simulateTransition(
            wasExerciseActive = false,
            isCurrentlyActive = true,
            exerciseStartTime = 0L,
            now = BASE_NOW
        )
        assertThat(result.exerciseStarted).isTrue()
        assertThat(result.recoveryTriggered).isFalse()
        assertThat(result.recoverySkipped).isFalse()
    }

    @Test fun `true to false with sufficient duration - recovery is triggered`() {
        val startTime = BASE_NOW - TEN_MINUTES_MS  // exactly 10 minutes ago
        val result = simulateTransition(
            wasExerciseActive = true,
            isCurrentlyActive = false,
            exerciseStartTime = startTime,
            now = BASE_NOW,
            postExerciseMinDuration = 10
        )
        assertThat(result.exerciseStarted).isFalse()
        assertThat(result.recoveryTriggered).isTrue()
        assertThat(result.recoverySkipped).isFalse()
    }

    @Test fun `true to false with insufficient duration - recovery is NOT triggered`() {
        val startTime = BASE_NOW - FIVE_MINUTES_MS  // only 5 minutes ago
        val result = simulateTransition(
            wasExerciseActive = true,
            isCurrentlyActive = false,
            exerciseStartTime = startTime,
            now = BASE_NOW,
            postExerciseMinDuration = 10
        )
        assertThat(result.exerciseStarted).isFalse()
        assertThat(result.recoveryTriggered).isFalse()
        assertThat(result.recoverySkipped).isTrue()
    }

    @Test fun `true to true - no transition lastExerciseStateAtTransition should update`() {
        val result = simulateTransition(
            wasExerciseActive = true,
            isCurrentlyActive = true,
            exerciseStartTime = BASE_NOW - TEN_MINUTES_MS,
            now = BASE_NOW
        )
        assertThat(result.exerciseStarted).isFalse()
        assertThat(result.recoveryTriggered).isFalse()
        assertThat(result.recoverySkipped).isFalse()
        assertThat(result.lastStateUpdated).isTrue()
    }

    @Test fun `false to false - no change`() {
        val result = simulateTransition(
            wasExerciseActive = false,
            isCurrentlyActive = false,
            exerciseStartTime = 0L,
            now = BASE_NOW
        )
        assertThat(result.exerciseStarted).isFalse()
        assertThat(result.recoveryTriggered).isFalse()
        assertThat(result.recoverySkipped).isFalse()
        assertThat(result.lastStateUpdated).isFalse()
    }

    @Test fun `boundary duration exactly at minimum triggers recovery`() {
        val startTime = BASE_NOW - TEN_MINUTES_MS  // exactly at minDuration=10
        val result = simulateTransition(
            wasExerciseActive = true,
            isCurrentlyActive = false,
            exerciseStartTime = startTime,
            now = BASE_NOW,
            postExerciseMinDuration = 10
        )
        assertThat(result.recoveryTriggered).isTrue()
    }

    @Test fun `duration one minute below minimum does NOT trigger recovery`() {
        val startTime = BASE_NOW - (TEN_MINUTES_MS - 60_000L)  // 9 minutes
        val result = simulateTransition(
            wasExerciseActive = true,
            isCurrentlyActive = false,
            exerciseStartTime = startTime,
            now = BASE_NOW,
            postExerciseMinDuration = 10
        )
        assertThat(result.recoveryTriggered).isFalse()
        assertThat(result.recoverySkipped).isTrue()
    }
}
