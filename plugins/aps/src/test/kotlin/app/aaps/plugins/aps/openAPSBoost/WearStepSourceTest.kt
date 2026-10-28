package app.aaps.plugins.aps.openAPSBoost

import app.aaps.core.data.model.SC
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-06-24 Wear step bridge: reconstruct today's cumulative from the rolling 5-min windows in the
 * stepsCount table without double-counting overlapping samples, and detect a live (worn) feed.
 */
class WearStepSourceTest {

    private val DAY = 86_400_000L
    private fun sc(ts: Long, s5: Int) = SC(duration = 300_000L, timestamp = ts, steps5min = s5,
        steps10min = 0, steps15min = 0, steps30min = 0, steps60min = 0, steps180min = 0, device = "wear")

    @Test fun `cumulative sums one sample per 5-min slot`() {
        val day0 = 100 * DAY
        // three 5-min slots with steps, plus an extra overlapping sample in the first slot (max wins)
        val list = listOf(
            sc(day0 + 60_000, 120),               // slot 0
            sc(day0 + 200_000, 140),              // slot 0 again (same 5-min) -> max 140, not 120+140
            sc(day0 + 360_000, 200),              // slot 1
            sc(day0 + 660_000, 90)                // slot 2
        )
        assertThat(WearStepSource.stepsToday(list, day0, day0 + 700_000)).isEqualTo(140 + 200 + 90)
    }

    @Test fun `freshness reflects a recent sample`() {
        val now = 100 * DAY
        assertThat(WearStepSource.isFresh(listOf(sc(now - 5 * 60_000, 50)), now)).isTrue()      // 5 min ago
        assertThat(WearStepSource.isFresh(listOf(sc(now - 30 * 60_000, 50)), now)).isFalse()    // 30 min ago
        assertThat(WearStepSource.isFresh(emptyList(), now)).isFalse()
    }

    @Test fun `resolution grace window keeps wear live through a short quiet spell`() {
        // 2026-07-07 anti-flap: strictly-stale-but-recent wear (e.g. 20 min quiet) must still
        // resolve as today's source — its reconstructed today-count is still valid — while a
        // genuinely-dead feed (> 30 min) is not.
        val now = 100 * DAY
        val quiet20m = listOf(sc(now - 20 * 60_000, 50))
        assertThat(WearStepSource.isFresh(quiet20m, now)).isFalse()          // strict freshness: stale
        assertThat(WearStepSource.isRecentlyFresh(quiet20m, now)).isTrue()   // resolution: still live
        assertThat(WearStepSource.isRecentlyFresh(listOf(sc(now - 31 * 60_000, 50)), now)).isFalse()
        assertThat(WearStepSource.isRecentlyFresh(emptyList(), now)).isFalse()
    }

    @Test fun `ignores samples outside the day window`() {
        val day0 = 100 * DAY
        val list = listOf(sc(day0 - 600_000, 999), sc(day0 + 120_000, 80))   // first is yesterday
        assertThat(WearStepSource.stepsToday(list, day0, day0 + 300_000)).isEqualTo(80)
    }
}
