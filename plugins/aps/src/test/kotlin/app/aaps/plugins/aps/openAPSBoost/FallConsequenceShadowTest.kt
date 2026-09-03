package app.aaps.plugins.aps.openAPSBoost

import android.content.Context
import app.aaps.core.interfaces.logging.AAPSLogger
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test
import org.mockito.Mockito.mock

/**
 * Pins the Kotlin feature builder against values computed by the training pipeline on the same
 * series, in `backtesting/scripts/2026-09-ml-features/out/c2_golden_fixture.json`.
 *
 * The point is train/serve skew. Every threshold in the shipped trees was placed on quantities the
 * Python produced, so a curvature computed a different way, or an area under the curve integrated
 * on a different grid, moves rows across splits while every unit test that only checks for a
 * plausible number still passes. These expectations are the Python's own output.
 */
class FallConsequenceShadowTest {

    // The feature builder touches neither collaborator; the mocks exist only to construct it.
    private val shadow = FallConsequenceShadow(mock(Context::class.java), mock(AAPSLogger::class.java))

    // 5-minute spacing, onset at index 3 where glucose is 142 and above the 70 floor.
    private val ts = longArrayOf(
        1788399100_000, 1788399400_000, 1788399700_000, 1788400000_000, 1788400300_000,
        1788400600_000, 1788400900_000, 1788401200_000, 1788401500_000, 1788401800_000,
        1788402100_000, 1788402400_000, 1788402700_000, 1788403000_000
    )
    private val bg = doubleArrayOf(
        150.0, 148.0, 145.0, 142.0, 136.0, 128.0, 121.0, 113.0, 106.0, 99.0, 94.0, 90.0, 88.0, 86.0
    )
    private val hour = 1.7777777777777777

    @Test fun featureVectorMatchesTheTrainingPipeline() {
        val f = shadow.features(ts, bg, 3, hour)!!
        assertThat(f.size).isEqualTo(14)
        assertThat(f[0]).isWithin(1e-9).of(29.0)                    // fall
        assertThat(f[1]).isWithin(1e-9).of(1.45)                    // fall_rate
        assertThat(f[2]).isWithin(1e-9).of(29.0)                    // nadir, a depth not a level
        assertThat(f[3]).isWithin(1e-6).of(277.5)                   // auc
        assertThat(f[4]).isWithin(1e-9).of(8.0)                     // dec_max
        assertThat(f[5]).isWithin(1e-9).of(8.0)                     // dec_last
        assertThat(f[6]).isWithin(1e-9).of(7.25)                    // dec_mean
        assertThat(f[7]).isWithin(1e-9).of(2.0)                     // accel
        assertThat(f[8]).isWithin(1e-9).of(-0.008571428571429309)   // curv
        assertThat(f[9]).isWithin(1e-9).of(-0.5333333333333333)     // pre_slope
        assertThat(f[10]).isWithin(1e-9).of(1.0)                    // still_falling
        assertThat(f[11]).isWithin(1e-9).of(142.0)                  // base
        assertThat(f[12]).isWithin(1e-9).of(0.44879918020046217)    // tod_sin
        assertThat(f[13]).isWithin(1e-9).of(0.8936326403234123)     // tod_cos
    }

    @Test fun quadraticCoefficientMatchesPolyfit() {
        // y = 3t^2 - 2t + 5 recovered exactly
        val t = doubleArrayOf(0.0, 1.0, 2.0, 3.0, 4.0)
        val y = DoubleArray(5) { 3.0 * t[it] * t[it] - 2.0 * t[it] + 5.0 }
        assertThat(shadow.quadCoefficient(t, y)).isWithin(1e-9).of(3.0)
    }

    @Test fun tooFewPointsReturnsNullRatherThanASubstitutedDefault() {
        assertThat(shadow.features(longArrayOf(0, 60_000), doubleArrayOf(120.0, 118.0), 0, 0.0))
            .isNull()
    }
}
