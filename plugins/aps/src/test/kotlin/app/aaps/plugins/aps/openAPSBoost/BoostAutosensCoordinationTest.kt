package app.aaps.plugins.aps.openAPSBoost

import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.selectSensitivityRatio
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-06-16 autosens / TDD-DynISF coordination. TDD-DynISF and traditional oref autosens are
 * ALTERNATIVE sensitivity-adaptation mechanisms — never both (would double-count). Pure-function
 * tests of the ratio-selection rule that feeds determine_basal's basal/target/CR scaling.
 *
 *   isfResultRatio    = TDD 24H/7D when TDD on; the DynISF-curve ratio when TDD off.
 *   orefAutosensRatio = real oref autosens ratio (1.0 when autosens disabled).
 */
class BoostAutosensCoordinationTest {

    private val tddRatio = 1.15      // would come from isfResult when useTdd
    private val curveRatio = 0.92    // would come from isfResult when !useTdd (sensNormalTarget/variableSens)
    private val orefRatio = 0.80     // real oref autosens (more sensitive today)

    @Test fun `TDD on - TDD ratio owns sensitivity, autosens ignored`() {
        val r = selectSensitivityRatio(useTdd = true, autosensWhenNoTdd = true, isfResultRatio = tddRatio, orefAutosensRatio = orefRatio)
        assertThat(r).isEqualTo(tddRatio)
    }

    @Test fun `TDD on - toggle off also yields TDD ratio (no effect when TDD on)`() {
        val r = selectSensitivityRatio(useTdd = true, autosensWhenNoTdd = false, isfResultRatio = tddRatio, orefAutosensRatio = orefRatio)
        assertThat(r).isEqualTo(tddRatio)
    }

    @Test fun `TDD off + toggle ON - traditional autosens drives basal (the fix)`() {
        val r = selectSensitivityRatio(useTdd = false, autosensWhenNoTdd = true, isfResultRatio = curveRatio, orefAutosensRatio = orefRatio)
        assertThat(r).isEqualTo(orefRatio)
    }

    @Test fun `TDD off + toggle OFF - legacy curve ratio scales basal (default, unchanged)`() {
        val r = selectSensitivityRatio(useTdd = false, autosensWhenNoTdd = false, isfResultRatio = curveRatio, orefAutosensRatio = orefRatio)
        assertThat(r).isEqualTo(curveRatio)
    }

    @Test fun `TDD off + toggle ON but autosens disabled - ratio is neutral 1,0 (no curve basal ramp)`() {
        // When ApsUseAutosens is off, orefAutosensRatio defaults to 1.0 → basal unscaled.
        val r = selectSensitivityRatio(useTdd = false, autosensWhenNoTdd = true, isfResultRatio = curveRatio, orefAutosensRatio = 1.0)
        assertThat(r).isEqualTo(1.0)
    }
}
