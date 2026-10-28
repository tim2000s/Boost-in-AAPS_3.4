package app.aaps.plugins.main.general.overview.boost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows

/** Row sizes for the overview action-button grid, which wraps at three buttons per row. */
class ButtonGridTest {

    @Test fun `one to eight visible buttons wrap at three`() {
        val expected = mapOf(
            1 to listOf(1),
            2 to listOf(2),
            3 to listOf(3),
            4 to listOf(3, 1),
            5 to listOf(3, 2),
            6 to listOf(3, 3),
            7 to listOf(3, 3, 1),
            8 to listOf(3, 3, 2)
        )
        for ((count, rows) in expected) assertThat(ButtonGrid.rowSizes(count)).isEqualTo(rows)
    }

    @Test fun `no visible buttons gives no rows`() {
        assertThat(ButtonGrid.rowSizes(0)).isEmpty()
        assertThat(ButtonGrid.rowSizes(-1)).isEmpty()
    }

    @Test fun `row sizes always sum to the count and never exceed the maximum`() {
        for (max in 1..5) for (count in 0..20) {
            val rows = ButtonGrid.rowSizes(count, max)
            assertThat(rows.sum()).isEqualTo(count)
            assertThat(rows.all { it in 1..max }).isTrue()
        }
    }

    @Test fun `non-positive maximum is rejected`() {
        assertThrows<IllegalArgumentException> { ButtonGrid.rowSizes(3, 0) }
    }
}
