package app.aaps.plugins.aps.openAPSBoost

import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.applyV6OverrideCaps
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-07-04 post-rescue meal-state cap — pure-function tests of the V6-override dose caps
 * (OpenAPSBoostPlugin.applyV6OverrideCaps).
 *
 * Incident 2026-07-03 19:47 BST: severe hypo (nadir 40) → unannounced rescue carbs → rebound.
 * V6 CONFIRMED at BG 119 delivered 2.7U while V1's 45-min post-rescue tier guard had restrained
 * the base engine to 1.05U; the meal-state exemption discarded that restraint. Inside the
 * post-rescue window (recentLowBG45Min < 75, SAME value + threshold as V1's tier guard) the
 * exemption is now suppressed, so CONFIRMED/COMMITTED inherit V1's hypo-restrained dose.
 * DB backtest 2026-07-04: 27% of removed insulin sits ahead of a second low <70 (vs 14-19%
 * for other levers); cost 10% genuine post-hypo meals at 0.15U median under-delivery.
 */
class PostRescueMealStateCapTest {

    // The 2026-07-03 incident numbers: V6 wanted 2.7U, hypo-restrained V1 would give 1.05U, nadir 40.
    private val v5Dose = 2.7
    private val v1Dose = 1.05

    @Test fun `meal state inside window - capped at V1 dose with post-rescue breadcrumb`() {
        val r = applyV6OverrideCaps(inMealState = true, inPostRescueWindow = true, v5FinalDose = v5Dose, v1WouldDose = v1Dose, recentLowBG45Min = 40.0)
        assertThat(r.dose).isEqualTo(v1Dose)
        assertThat(r.capNote).contains("post-rescue capped from 2.7U to V1's 1.05U")
        assertThat(r.capNote).contains("45-min low 40")
    }

    @Test fun `meal state inside window but V5 already below V1 - V5 dose kept, no breadcrumb`() {
        val r = applyV6OverrideCaps(inMealState = true, inPostRescueWindow = true, v5FinalDose = 0.4, v1WouldDose = v1Dose, recentLowBG45Min = 68.0)
        assertThat(r.dose).isEqualTo(0.4)
        assertThat(r.capNote).isEmpty()
    }

    @Test fun `meal state outside window - exemption intact, V6 may out-dose V1`() {
        val r = applyV6OverrideCaps(inMealState = true, inPostRescueWindow = false, v5FinalDose = v5Dose, v1WouldDose = v1Dose, recentLowBG45Min = 110.0)
        assertThat(r.dose).isEqualTo(v5Dose)
        assertThat(r.capNote).isEmpty()
    }

    @Test fun `non-meal state outside window - non-meal cap unchanged`() {
        val r = applyV6OverrideCaps(inMealState = false, inPostRescueWindow = false, v5FinalDose = v5Dose, v1WouldDose = v1Dose, recentLowBG45Min = 110.0)
        assertThat(r.dose).isEqualTo(v1Dose)
        assertThat(r.capNote).contains("non-meal-capped from 2.7U")
        assertThat(r.capNote).doesNotContain("post-rescue")
    }

    @Test fun `non-meal state inside window - still the non-meal cap (window adds nothing new)`() {
        val r = applyV6OverrideCaps(inMealState = false, inPostRescueWindow = true, v5FinalDose = v5Dose, v1WouldDose = v1Dose, recentLowBG45Min = 40.0)
        assertThat(r.dose).isEqualTo(v1Dose)
        assertThat(r.capNote).contains("non-meal-capped from 2.7U")
    }

    @Test fun `non-meal state with V5 below V1 - V5 dose kept, no breadcrumb`() {
        val r = applyV6OverrideCaps(inMealState = false, inPostRescueWindow = false, v5FinalDose = 0.3, v1WouldDose = v1Dose, recentLowBG45Min = 110.0)
        assertThat(r.dose).isEqualTo(0.3)
        assertThat(r.capNote).isEmpty()
    }

    @Test fun `shared threshold stays aligned with V1's tier guard at 75`() {
        // Alignment is load-bearing: the plugin's window predicate and V1's Fix A v2 tier block
        // both read this constant, so the V6 cap engages exactly when V1's dose is restrained.
        assertThat(DetermineBasalBoost.POST_RESCUE_LOW_THRESHOLD_MGDL).isEqualTo(75.0)
    }
}
