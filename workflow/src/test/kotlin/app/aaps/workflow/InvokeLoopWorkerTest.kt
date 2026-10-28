package app.aaps.workflow

import app.aaps.core.data.time.T
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * The decision rate is a property of this class rather than of how glucose is bucketed, and these
 * tests are written against a sensor that jitters, because a real one does.
 */
class InvokeLoopWorkerTest {

    private val base = 1_700_000_000_000L
    private fun trigger(ts: Long, last: Long, native: Boolean) =
        InvokeLoopWorker.shouldTrigger(ts, last, native)

    /** Arm A and any ordinary install: one reading every five minutes, every one of them runs. */
    @Test
    fun aFiveMinuteFeedRunsOnEveryReadingWhateverThePhase() {
        // Sweep the offset of the whole series against the anchor. The failure this replaces showed
        // up only at particular phases, so a single starting point would not have caught it.
        for (offsetSec in 0 until 300 step 7) {
            var last = 0L
            var runs = 0
            var t = base + offsetSec * 1000L
            repeat(60) {
                if (trigger(t, last, false)) { last = t; runs++ }
                t += T.mins(5).msecs()
            }
            assertThat(runs).isEqualTo(60)
        }
    }

    /** The same, with the jitter a real sensor shows: never a clean 300000 ms. */
    @Test
    fun aJitteringFiveMinuteFeedStillRunsOnEveryReading() {
        val jitterSec = listOf(-4, +6, -1, +3, -6, +2, 0, +5, -3, +1)
        var last = 0L
        var runs = 0
        var t = base
        repeat(200) { i ->
            t += T.mins(5).msecs() + jitterSec[i % jitterSec.size] * 1000L
            if (trigger(t, last, false)) { last = t; runs++ }
        }
        assertThat(runs).isEqualTo(200)
    }

    /** Arm B: readings every minute, decisions every five. */
    @Test
    fun aOneMinuteFeedIsHeldToFiveMinuteDecisions() {
        var last = 0L
        val fired = mutableListOf<Long>()
        var t = base
        repeat(120) {
            if (trigger(t, last, false)) { last = t; fired += t }
            t += T.mins(1).msecs()
        }
        // 120 readings, two hours, so 24 decisions once the first has anchored the sequence.
        assertThat(fired.size).isEqualTo(24)
        val gaps = fired.zipWithNext { a, b -> (b - a) / 60000 }
        assertThat(gaps.all { it == 5L }).isTrue()
    }

    /** Arms C and D: readings every minute, decisions every minute. */
    @Test
    fun nativeCadenceRunsOnEveryReading() {
        var last = 0L
        var runs = 0
        var t = base
        repeat(120) {
            if (trigger(t, last, true)) { last = t; runs++ }
            t += T.mins(1).msecs()
        }
        assertThat(runs).isEqualTo(120)
    }

    /** The same value offered twice never runs twice, at either cadence. */
    @Test
    fun oneReadingRunsOnce() {
        assertThat(trigger(base, base, true)).isFalse()
        assertThat(trigger(base, base, false)).isFalse()
        assertThat(trigger(base - 1000, base, true)).isFalse()
    }

    /** A gap in the feed does not suppress the run that ends it. */
    @Test
    fun aGapInTheFeedRunsAsSoonAsGlucoseReturns() {
        assertThat(trigger(base + T.mins(40).msecs(), base, false)).isTrue()
    }

    /** The first ever run has nothing to space itself against. */
    @Test
    fun theFirstRunIsNotHeldBack() {
        assertThat(trigger(base, 0L, false)).isTrue()
    }
}
