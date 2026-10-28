package app.aaps.plugins.aps.openAPSBoost

import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.autosensAdjustedIsf
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-09-24. On a static profile ISF the autosens ratio is folded into the ISF at target, the value
 * every sensitivity in the engine is built from, so it reaches the dosing sensitivity as it does in
 * stock oref. Field case: ratio 1.30 on an ISF of 68.4 must give 52.6 for the dose, which it did not.
 */
class BoostAutosensIsfTest {

    private fun isf(useTdd: Boolean = false, autosensWhenNoTdd: Boolean = true, tt: Double = 1.0, ratio: Double) =
        autosensAdjustedIsf(68.4, useTdd, autosensWhenNoTdd, tt, ratio)

    @Test fun `resistant ratio strengthens ISF at target`() {
        assertThat(isf(ratio = 1.3)).isWithin(0.05).of(52.6)
    }

    @Test fun `sensitive ratio weakens ISF at target`() {
        assertThat(isf(ratio = 0.8)).isWithin(0.05).of(85.5)
    }

    @Test fun `neutral ratio changes nothing`() {
        assertThat(isf(ratio = 1.0)).isEqualTo(68.4)
    }

    @Test fun `TDD-based ISF owns sensitivity, autosens not applied`() {
        assertThat(isf(useTdd = true, ratio = 1.3)).isEqualTo(68.4)
    }

    @Test fun `no-TDD autosens switch off, autosens not applied`() {
        assertThat(isf(autosensWhenNoTdd = false, ratio = 1.3)).isEqualTo(68.4)
    }

    @Test fun `a temp-target ratio is not stacked with autosens`() {
        assertThat(isf(tt = 0.7, ratio = 1.3)).isEqualTo(68.4)
    }

    @Test fun `a non-positive ratio falls back rather than dividing`() {
        assertThat(isf(ratio = 0.0)).isEqualTo(68.4)
        assertThat(isf(ratio = -1.0)).isEqualTo(68.4)
    }
}
