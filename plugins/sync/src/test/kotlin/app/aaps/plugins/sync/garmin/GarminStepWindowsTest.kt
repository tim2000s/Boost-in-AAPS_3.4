package app.aaps.plugins.sync.garmin

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

class GarminStepWindowsTest {

    @Test fun `the reported Venu 3 fault is bounded`() {
        // 2026-08-27: all six windows arrived as the day's cumulative total.
        val w = GarminStepWindows.sanitise(1919, 1919, 1919, 1919, 1919, 1919)
        assertThat(w.s5).isEqualTo(1000)      // 5 min at 200/min
        assertThat(w.s15).isEqualTo(1919)     // 15 min ceiling is 3000, so 1919 passes
        assertThat(w.s5).isLessThan(1919)
    }

    @Test fun `a five minute window cannot exceed a sprint cadence`() {
        assertThat(GarminStepWindows.sanitise(5000, 0, 0, 0, 0, 0).s5).isEqualTo(1000)
    }

    @Test fun `ordinary counts pass through untouched`() {
        val w = GarminStepWindows.sanitise(120, 260, 380, 700, 1200, 3000)
        assertThat(listOf(w.s5, w.s10, w.s15, w.s30, w.s60, w.s180))
            .containsExactly(120, 260, 380, 700, 1200, 3000).inOrder()
    }

    @Test fun `a burst confined to the last five minutes stays equal across windows`() {
        val w = GarminStepWindows.sanitise(600, 600, 600, 600, 600, 600)
        assertThat(listOf(w.s5, w.s10, w.s15, w.s30, w.s60, w.s180))
            .containsExactly(600, 600, 600, 600, 600, 600).inOrder()
    }

    @Test fun `a wider window is never smaller than a narrower one`() {
        val w = GarminStepWindows.sanitise(900, 100, 50, 20, 10, 0)
        assertThat(w.s10).isAtLeast(w.s5)
        assertThat(w.s15).isAtLeast(w.s10)
        assertThat(w.s180).isAtLeast(w.s60)
    }

    @Test fun `negative counts floor at zero`() {
        val w = GarminStepWindows.sanitise(-50, -10, 0, 0, 0, 0)
        assertThat(w.s5).isEqualTo(0)
        assertThat(w.s180).isEqualTo(0)
    }
}
