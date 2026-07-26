package app.aaps.plugins.aps.openAPSBoost

import app.aaps.plugins.aps.openAPSBoost.DetermineBasalBoost.Companion.postRescueReboundScale
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-07-23 composed post-rescue rebound guard — pure-function tests of the shared
 * graduated scale (DetermineBasalBoost.postRescueReboundScale).
 *
 * Incident 2026-07-23 (user H): low 67 mg/dL → unannounced rescue carbs → rebound. The
 * post-rescue tier block demoted T3/T5 to T7 (Enhanced oref1), but T7/T8 apply no
 * fast-carb scaling, so a delta-inflated insulinReq delivered 3.55U at BG 97, 25 min
 * after the low. Second hypo followed; the engine repeated the pattern on the second
 * rescue and the user set the loop offline. The guard now applies this scale to the
 * final microBolus whenever the post-rescue window is active, independent of tier.
 * DB pricing 2026-07-23: 34% [32,37] of removed insulin sits ahead of a second low <70.
 */
class PostRescueReboundScaleTest {

    @Test fun `strong suppression below 120`() {
        assertThat(postRescueReboundScale(70.0)).isEqualTo(0.3)
        assertThat(postRescueReboundScale(97.0)).isEqualTo(0.3)   // the 3.55U incident cycle → 1.06U
        assertThat(postRescueReboundScale(119.9)).isEqualTo(0.3)
    }

    @Test fun `linear ramp 120 to 170`() {
        assertThat(postRescueReboundScale(120.0)).isWithin(1e-9).of(0.3)
        assertThat(postRescueReboundScale(145.0)).isWithin(1e-9).of(0.65)
        assertThat(postRescueReboundScale(169.9)).isWithin(1e-3).of(0.9986)
    }

    @Test fun `no suppression at and above 170`() {
        assertThat(postRescueReboundScale(170.0)).isEqualTo(1.0)
        assertThat(postRescueReboundScale(250.0)).isEqualTo(1.0)
    }
}
