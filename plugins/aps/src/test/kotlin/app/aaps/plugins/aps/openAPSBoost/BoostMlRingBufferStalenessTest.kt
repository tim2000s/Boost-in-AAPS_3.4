package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * The ring buffer feeding the 53-feature hypo model is persisted across process restarts and is
 * trimmed by age as well as by length. Without the age check a break in the decision series leaves
 * pre-break snapshots in place, and the model is handed a trajectory hours old as though it were
 * the preceding five cycles.
 */
class BoostMlRingBufferStalenessTest {

    private val minute = 60_000L

    private fun snap(ts: Long, bg: Double) = BoostMlFeatureBuilder.CycleSnapshot(
        ts = ts, cgmMgdl = bg, iobIob = 0.0, iobActivity = 0.0,
        sugEventualBG = bg, recentSmbUnits60m = 0.0, sugMinDelta = 0.0
    )

    @Test fun contiguousCyclesAreAllRetained() {
        val b = BoostMlFeatureBuilder.RingBuffer()
        for (i in 0 until BoostMlFeatureBuilder.LOOKBACK) b.push(snap(i * 5 * minute, 100.0 + i))
        assertThat(b.snapshots).hasSize(BoostMlFeatureBuilder.LOOKBACK)
        assertThat(b.lagged(BoostMlFeatureBuilder.LOOKBACK - 1)?.cgmMgdl).isEqualTo(100.0)
    }

    @Test fun aBreakInTheSeriesDiscardsTheHistoryItInterrupts() {
        val b = BoostMlFeatureBuilder.RingBuffer()
        for (i in 0 until BoostMlFeatureBuilder.LOOKBACK) b.push(snap(i * 5 * minute, 100.0 + i))
        // two hours later the loop resumes; nothing before the break describes the preceding cycles
        b.push(snap(2 * 60 * minute, 200.0))
        assertThat(b.snapshots).hasSize(1)
        assertThat(b.lagged(0)?.cgmMgdl).isEqualTo(200.0)
        assertThat(b.lagged(1)).isNull()
    }

    @Test fun aShortDelayKeepsHistoryWithinTheWindow() {
        val b = BoostMlFeatureBuilder.RingBuffer()
        b.push(snap(0, 100.0))
        b.push(snap(20 * minute, 110.0))          // 20 min on, still inside the window
        assertThat(b.snapshots).hasSize(2)
        assertThat(b.lagged(1)?.cgmMgdl).isEqualTo(100.0)
    }

    @Test fun theBoundaryIsThirtyFiveMinutes() {
        val b = BoostMlFeatureBuilder.RingBuffer()
        b.push(snap(0, 100.0))
        b.push(snap(34 * minute, 110.0))
        assertThat(b.snapshots).hasSize(2)
        val c = BoostMlFeatureBuilder.RingBuffer()
        c.push(snap(0, 100.0))
        c.push(snap(36 * minute, 110.0))
        assertThat(c.snapshots).hasSize(1)
    }

    @Test fun aStaleBufferReloadedFromPreferencesIsDiscardedOnTheNextPush() {
        // what happens after an app restart: the buffer is deserialised, then a cycle arrives
        val restored = BoostMlFeatureBuilder.deserializeBuffer(
            BoostMlFeatureBuilder.serializeBuffer(
                BoostMlFeatureBuilder.RingBuffer(
                    mutableListOf(snap(0, 90.0), snap(5 * minute, 92.0))
                )
            )
        )
        assertThat(restored.snapshots).hasSize(2)
        restored.push(snap(6 * 60 * minute, 150.0))
        assertThat(restored.snapshots).hasSize(1)
        assertThat(restored.lagged(0)?.cgmMgdl).isEqualTo(150.0)
    }

    @Test fun theBuiltVectorFallsBackToTheCurrentCycleRatherThanStaleHistory() {
        val names = listOf("cgm_mgdl", "cgm_mgdl_lag1", "cgm_mgdl_lag2")
        val b = BoostMlFeatureBuilder.RingBuffer()
        for (i in 0 until BoostMlFeatureBuilder.LOOKBACK) b.push(snap(i * 5 * minute, 60.0))
        val current = snap(3 * 60 * minute, 180.0)
        b.push(current)
        val v = BoostMlFeatureBuilder.build(names, current, b, mapOf("cgm_mgdl" to 180.0))
        // every lag resolves to the current cycle; none of them reports the pre-break 60 mg/dL
        assertThat(v[0]).isEqualTo(180.0)
        assertThat(v[1]).isEqualTo(180.0)
        assertThat(v[2]).isEqualTo(180.0)
    }
}
