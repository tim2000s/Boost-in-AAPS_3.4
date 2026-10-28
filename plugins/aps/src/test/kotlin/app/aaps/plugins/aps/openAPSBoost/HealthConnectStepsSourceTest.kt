package app.aaps.plugins.aps.openAPSBoost

import app.aaps.plugins.aps.openAPSBoost.HealthConnectStepsIngest.Companion.chooseSourceByCoverage
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-06-18 step-source selection: pick the source with the most DAILY COVERAGE (continuous feed),
 * not the most total steps. A constant on-body source (phone pedometer) should beat an app that
 * only holds a couple of days, even if that app reports more total steps.
 */
class HealthConnectStepsSourceTest {

    private fun days(vararg pairs: Pair<Long, Long>) = HashMap<Long, Long>().apply { putAll(pairs) }

    @Test fun `prefers the source with more days of coverage even if fewer total steps`() {
        val m = mapOf(
            "com.google.android.apps.fitness" to days(100L to 30000L, 101L to 20000L),          // 2 days, big total
            "com.oplus.health" to days(80L to 8000L, 81L to 9000L, 82L to 7000L, 83L to 8000L,
                84L to 9000L, 85L to 8000L, 86L to 7000L, 87L to 8000L)                          // 8 days, smaller total
        )
        assertThat(chooseSourceByCoverage(m)).isEqualTo("com.oplus.health")
    }

    @Test fun `total steps breaks a coverage tie`() {
        val m = mapOf(
            "a" to days(1L to 1000L, 2L to 1000L),
            "b" to days(1L to 5000L, 2L to 5000L)
        )
        assertThat(chooseSourceByCoverage(m)).isEqualTo("b")
    }

    @Test fun `ignores sources whose days are all zero`() {
        val m = mapOf(
            "empty" to days(1L to 0L, 2L to 0L, 3L to 0L, 4L to 0L),
            "real" to days(1L to 6000L)
        )
        assertThat(chooseSourceByCoverage(m)).isEqualTo("real")
    }

    @Test fun `null when nothing has data`() {
        assertThat(chooseSourceByCoverage(emptyMap())).isNull()
        assertThat(chooseSourceByCoverage(mapOf("x" to days(1L to 0L)))).isNull()
    }
}
