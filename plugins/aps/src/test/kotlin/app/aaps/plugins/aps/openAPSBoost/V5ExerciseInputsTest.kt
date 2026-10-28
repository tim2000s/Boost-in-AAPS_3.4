package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * F2 (2026-07-07) — exercise inputs to V6 on the LIVE path.
 *
 * The `v5_exerciseActive` / `v5_inPostExerciseWindow` / `v5_exerciseSubclass` fields on
 * OapsProfileBoost were only ever filled by the retired OpenAPSBoostV3MLG3Plugin; the live
 * OpenAPSBoostPlugin profile build omitted them, so V6's exercise damping never engaged live.
 * These tests lock the now-shared mapping helpers the live profile build uses
 * ([v5ExerciseActive]/[v5InPostExerciseWindow]) to V3MLG3's exact semantics.
 */
class V5ExerciseInputsTest {

    @Test fun `every exercise state maps to exerciseActive true`() {
        listOf("ACTIVE", "VIGOROUS_AEROBIC", "MODERATE_AEROBIC", "LIGHT_AEROBIC", "RESISTANCE", "STRESS")
            .forEach { assertThat(v5ExerciseActive(it)).isTrue() }
    }

    @Test fun `non-exercise states map to exerciseActive false`() {
        // Every non-exercise activityState calculateBoostActivity can produce (incl. the F1
        // "steps-unknown" state added in this batch).
        listOf("none", "normal", "INACTIVE", "steps-unknown", "")
            .forEach { assertThat(v5ExerciseActive(it)).isFalse() }
    }

    @Test fun `set matches the V3MLG3 mapping verbatim`() {
        // The V5 consumers were calibrated against V3MLG3's shadow-era mapping — the live set
        // must be exactly that set (no drift when someone edits one list but not the other).
        assertThat(V5_EXERCISE_STATES).containsExactly(
            "ACTIVE", "VIGOROUS_AEROBIC", "MODERATE_AEROBIC", "LIGHT_AEROBIC", "RESISTANCE", "STRESS"
        )
    }

    @Test fun `inside the recovery window - inPostExerciseWindow true`() {
        val now = 1_000_000L
        assertThat(v5InPostExerciseWindow(postExerciseRecoveryEnabled = true, nowMs = now, recoveryWindowEndMs = now + 1)).isTrue()
    }

    @Test fun `window expired or feature disabled - inPostExerciseWindow false`() {
        val now = 1_000_000L
        // window end == now → closed (strict <, same as V3MLG3)
        assertThat(v5InPostExerciseWindow(true, now, now)).isFalse()
        assertThat(v5InPostExerciseWindow(true, now, now - 1)).isFalse()
        // pref off → never in window, regardless of the timestamp
        assertThat(v5InPostExerciseWindow(false, now, now + 60_000L)).isFalse()
        // never-exercised default (recoveryWindowEnd = 0)
        assertThat(v5InPostExerciseWindow(true, now, 0L)).isFalse()
    }
}
