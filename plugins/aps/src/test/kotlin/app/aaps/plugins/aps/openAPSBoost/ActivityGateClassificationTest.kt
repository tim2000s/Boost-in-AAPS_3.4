package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-10-08, audit #11 and #12.
 *
 * #11: the overnight gate fix closed the Boost gate across the night window, and the whole activity
 * classification sat inside `if (boostActive)`, so an exercise session inside the window lost its
 * reduced profile and raised target (38 decisions over 60 days in the field), and an evening session
 * was cut off at night start. Classification now runs whatever the gate says; only the INACTIVE raise,
 * which adds insulin, still needs the gate open.
 *
 * #12: with HR integration on, a missing or stuck heart rate (classification null) let the INACTIVE
 * +30% raise through. It now needs positive HR evidence of rest.
 */
class ActivityGateClassificationTest {

    private fun inputs(
        raiseGateOpen: Boolean,
        isActive: Boolean = false,
        hr: HrActivityCalculator.HrClassificationResult? = null,
        hrIntegrationEnabled: Boolean = false,
        inactivityEligible: Boolean = false,
        tempTargetSet: Boolean = false,
    ) = BoostActivityInputs(
        raiseGateOpen = raiseGateOpen,
        isActive = isActive,
        hr = hr,
        hrIntegrationEnabled = hrIntegrationEnabled,
        hrStressDetection = false,
        inactivityEligible = inactivityEligible,
        stepsAvailable = true,
        tempTargetSet = tempTargetSet,
        profilePercent = 100,
        activityPct = 80.0,
        inactivityPct = 130.0,
        minBg = 100.0,
        maxBg = 100.0,
        targetBg = 100.0,
        recentSteps60Min = 40,
        inactivitySteps = 400,
    )

    private fun hrResult(zone: HrActivityCalculator.HrZone, state: HrActivityCalculator.ExerciseState) =
        HrActivityCalculator.HrClassificationResult(
            exerciseState = state, hrZone = zone, averageHrBpm = 70.0, hrrPercent = 10.0,
            confidence = HrActivityCalculator.Confidence.HIGH, debugInfo = "test"
        )

    // ── #11 ──

    @Test fun `gate closed - exercise inside the night window keeps the reduced profile and raised target`() {
        val r = classifyBoostActivity(inputs(raiseGateOpen = false, isActive = true))
        assertThat(r.state).isEqualTo("ACTIVE")
        assertThat(r.profileSwitch).isEqualTo(80)
        assertThat(r.targetBg).isEqualTo(150.0)
    }

    @Test fun `gate closed - vigorous aerobic still reduces the profile further`() {
        val hr = hrResult(HrActivityCalculator.HrZone.ZONE_4_HARD, HrActivityCalculator.ExerciseState.VIGOROUS_AEROBIC)
        val r = classifyBoostActivity(inputs(raiseGateOpen = false, isActive = true, hr = hr, hrIntegrationEnabled = true))
        assertThat(r.state).isEqualTo("VIGOROUS_AEROBIC")
        assertThat(r.profileSwitch).isEqualTo(70)
    }

    @Test fun `gate closed - the INACTIVE raise stays withheld`() {
        val r = classifyBoostActivity(inputs(raiseGateOpen = false, inactivityEligible = true))
        assertThat(r.state).isNotEqualTo("INACTIVE")
        assertThat(r.profileSwitch).isEqualTo(100)
    }

    @Test fun `gate open - the INACTIVE raise is unchanged for step-only users`() {
        val r = classifyBoostActivity(inputs(raiseGateOpen = true, inactivityEligible = true))
        assertThat(r.state).isEqualTo("INACTIVE")
        assertThat(r.profileSwitch).isEqualTo(130)
    }

    @Test fun `a user temp target is never overridden by the activity target`() {
        val r = classifyBoostActivity(inputs(raiseGateOpen = false, isActive = true, tempTargetSet = true))
        assertThat(r.targetBg).isEqualTo(100.0)
        assertThat(r.profileSwitch).isEqualTo(80)
    }

    // ── #12 ──

    @Test fun `HR integration on, no usable HR - INACTIVE raise withheld`() {
        val r = classifyBoostActivity(inputs(raiseGateOpen = true, inactivityEligible = true, hrIntegrationEnabled = true, hr = null))
        assertThat(r.state).isEqualTo("HR_UNAVAILABLE")
        assertThat(r.profileSwitch).isEqualTo(100)
    }

    @Test fun `HR integration on, resting zone 1 - INACTIVE raise allowed`() {
        val hr = hrResult(HrActivityCalculator.HrZone.ZONE_1_VERY_LIGHT, HrActivityCalculator.ExerciseState.INACTIVE)
        val r = classifyBoostActivity(inputs(raiseGateOpen = true, inactivityEligible = true, hrIntegrationEnabled = true, hr = hr))
        assertThat(r.state).isEqualTo("INACTIVE")
        assertThat(r.profileSwitch).isEqualTo(130)
    }
}
