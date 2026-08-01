package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

class NightWindowTest {

    private val midnight = 1_784_505_600_000L      // an arbitrary local midnight
    private fun at(h: Int, m: Int = 0) = midnight + ((h * 60 + m) * 60_000L)

    @Test
    fun `default window 2200 to 0700 wraps midnight`() {
        val start = at(22); val end = at(7)
        assertThat(NightWindow.contains(at(23), start, end)).isTrue()
        assertThat(NightWindow.contains(at(2), start, end)).isTrue()
        assertThat(NightWindow.contains(at(6, 9), start, end)).isTrue()   // the reported incident
        assertThat(NightWindow.contains(at(7), start, end)).isFalse()     // end is exclusive
        assertThat(NightWindow.contains(at(12), start, end)).isFalse()
        assertThat(NightWindow.contains(at(21, 59), start, end)).isFalse()
    }

    @Test
    fun `a window that does not wrap behaves normally`() {
        val start = at(1); val end = at(5)
        assertThat(NightWindow.contains(at(3), start, end)).isTrue()
        assertThat(NightWindow.contains(at(0, 30), start, end)).isFalse()
        assertThat(NightWindow.contains(at(6), start, end)).isFalse()
    }

    @Test
    fun `equal times are an empty window, never a whole day`() {
        // The wrap branch would otherwise union to cover everything, making it permanently night.
        // In the 2026-07-02 incident that silently stopped Boost dosing altogether.
        val t = at(7)
        assertThat(NightWindow.contains(at(3), t, t)).isFalse()
        assertThat(NightWindow.contains(at(7), t, t)).isFalse()
        assertThat(NightWindow.contains(at(15), t, t)).isFalse()
    }

    @Test
    fun `start is inclusive and end is exclusive`() {
        val start = at(22); val end = at(7)
        assertThat(NightWindow.contains(at(22), start, end)).isTrue()
        assertThat(NightWindow.contains(at(6, 59), start, end)).isTrue()
    }
}
