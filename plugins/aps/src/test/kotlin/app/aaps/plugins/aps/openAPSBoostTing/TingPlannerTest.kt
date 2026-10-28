package app.aaps.plugins.aps.openAPSBoostTing

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * TING engine core (2026-07-18) — the planner is a SMOOTHER, not an amplifier. These tests pin the
 * two things that make it a TING lever rather than a hypo generator: it never chases glucose down
 * or breaches the low-tail (safety), and it nudges rather than slams (smoothness). Pure-function.
 */
class TingPlannerTest {

    // A benign baseline: forecast drifting up out of the band, plenty of floor headroom.
    private fun base() = TingInputs(
        bg = 150.0, forecastBg = 165.0, minGuardBg = 120.0, minGuardThreshold = 80.0,
        isf = 40.0, iob = 1.0, maxIob = 8.0, lastDoseU = 0.20, roundSmbTo = 0.05,
    )

    // ── Safety: the floor is sacred ─────────────────────────────────────────────────────────────

    @Test fun `imminent low - doses zero regardless of forecast`() {
        val d = tingPlan(base().copy(minGuardBg = 78.0))   // ≤ threshold 80
        assertThat(d.wouldDoseU).isEqualTo(0.0)
        assertThat(d.floorClipped).isTrue()
    }

    @Test fun `floor-clip keeps the worst-case low above threshold plus margin`() {
        // minGuard 92, threshold 80, margin 8 → headroom 4 mg/dL; perU = 40*0.35 = 14 → cap ≈ 0.285U.
        val d = tingPlan(base().copy(minGuardBg = 92.0, forecastBg = 260.0, lastDoseU = 1.0))
        assertThat(d.floorClipped).isTrue()
        // predicted worst-case low after dosing must not fall below threshold+margin (88)
        val worstCaseLowAfter = 92.0 - d.wouldDoseU * (40.0 * TING_HORIZON_ACTIVITY)
        assertThat(worstCaseLowAfter).isAtLeast(80.0 + TING_FLOOR_MARGIN_MGDL - 1e-6)
    }

    @Test fun `never chases glucose down - forecast in or under the band holds`() {
        assertThat(tingPlan(base().copy(forecastBg = 112.0)).wouldDoseU).isEqualTo(0.0)   // at aim
        assertThat(tingPlan(base().copy(forecastBg = 95.0)).wouldDoseU).isEqualTo(0.0)    // in band
        assertThat(tingPlan(base().copy(forecastBg = 70.0)).wouldDoseU).isEqualTo(0.0)    // low-normal
    }

    @Test fun `maxIOB headroom caps the dose`() {
        val d = tingPlan(base().copy(forecastBg = 300.0, iob = 7.95, maxIob = 8.0, lastDoseU = 5.0, minGuardBg = 200.0))
        assertThat(d.wouldDoseU).isAtMost(8.0 - 7.95 + 1e-9)
    }

    // ── Smoothness: nudge, don't slam ───────────────────────────────────────────────────────────

    @Test fun `rate-limits the increase over the last dose (anti-ringing)`() {
        // Huge forecast would want a big dose; the step-up limit holds it near lastDose + step.
        val d = tingPlan(base().copy(forecastBg = 400.0, lastDoseU = 0.10, minGuardBg = 250.0))
        assertThat(d.wouldDoseU).isAtMost(0.10 + TING_MAX_STEP_UP_U + 1e-9)
    }

    @Test fun `low-gain proportional nudge - closes only part of the gap`() {
        // gap = 165 - 112 = 53; perU = 14; gain 0.5 → raw ≈ 1.89U, but step-up from 0.20 caps at 0.40.
        val d = tingPlan(base())
        assertThat(d.wouldDoseU).isGreaterThan(0.0)
        assertThat(d.wouldDoseU).isAtMost(base().lastDoseU + TING_MAX_STEP_UP_U + 1e-9)
        // projected BG moves toward the band but does NOT overshoot below the aim (no manufactured low)
        assertThat(d.projectedBg).isGreaterThan(TING_AIM)
    }

    @Test fun `a dose never drives the projected horizon below the aim (no overshoot into lows)`() {
        // Across a sweep of forecasts, the projected post-dose BG stays at or above the aim.
        for (f in listOf(145.0, 160.0, 180.0, 210.0, 250.0, 300.0)) {
            val d = tingPlan(base().copy(forecastBg = f, minGuardBg = f - 20.0, lastDoseU = 2.0))
            assertThat(d.projectedBg).isAtLeast(TING_AIM - 1e-6)
        }
    }

    @Test fun `holds at zero when already smooth and in band - the glide state`() {
        // Forecast at aim, small last dose → nothing to do; this is the steady state the planner seeks.
        val d = tingPlan(base().copy(forecastBg = 108.0, lastDoseU = 0.05))
        assertThat(d.wouldDoseU).isEqualTo(0.0)
        assertThat(d.reason).contains("hold")
    }
}
