package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Fix (2026-06-14) — V1-anchored decelerationBrake: ease off as delta_accl crosses below zero
 * (first sign insulin is biting), unless still climbing fast (delta > 8, V1 T4 velocity fallback).
 * Graduated 1.0 @ accl=0 → 0.30 @ accl ≤ −15. Pure function, tested directly.
 */
class SafetyGatesDecelBrakeTest {

    @Test fun `still accelerating - no brake`() {
        assertThat(decelerationBrake(deltaAccl = 5.0, delta = 4.0)).isEqualTo(1.0)
        assertThat(decelerationBrake(deltaAccl = 0.0, delta = 4.0)).isEqualTo(1.0)
    }

    @Test fun `still climbing fast - velocity fallback exempts even when decelerating`() {
        assertThat(decelerationBrake(deltaAccl = -20.0, delta = 12.0)).isEqualTo(1.0)
        assertThat(decelerationBrake(deltaAccl = -2.3, delta = 19.0)).isEqualTo(1.0)
    }

    @Test fun `decelerating and not climbing fast - graduated ease-off`() {
        // accl=-7.5, delta<8 → 0.30 + 0.70*(7.5/15) = 0.65
        assertThat(decelerationBrake(deltaAccl = -7.5, delta = 2.0)).isWithin(1e-9).of(0.65)
    }

    @Test fun `full brake at or below floor accl`() {
        assertThat(decelerationBrake(deltaAccl = -15.0, delta = 2.0)).isWithin(1e-9).of(0.30)
        assertThat(decelerationBrake(deltaAccl = -25.0, delta = 2.0)).isWithin(1e-9).of(0.30)
    }

    @Test fun `mild deceleration - near full dose`() {
        // accl=-1, delta<8 → 0.30 + 0.70*(14/15) ≈ 0.953
        assertThat(decelerationBrake(deltaAccl = -1.0, delta = 0.0)).isWithin(1e-3).of(0.953)
    }
}
