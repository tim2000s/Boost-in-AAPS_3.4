package app.aaps.plugins.smoothing

import app.aaps.core.data.iob.InMemoryGlucoseValue
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.iob.IobCobCalculator
import dagger.Lazy
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.resources.ResourceHelper
import app.aaps.core.keys.interfaces.Preferences
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test
import app.aaps.core.interfaces.aps.IobTotal
import org.mockito.kotlin.doReturn
import org.mockito.kotlin.mock

/**
 * Behavioural tests for the Unscented Kalman Filter smoother. `smooth()` is pure JVM math (no Android runtime),
 * so a plain JUnit5 test with mocked collaborators exercises the whole forward-UKF + backward-RTS pipeline,
 * segmentation, outlier rejection and the raw-copy fallbacks.
 *
 * Each plugin is freshly constructed so its learned state starts from defaults: `preferences.get(LastSaved…)`
 * returns the Mockito default 0, which makes `loadPersistedParameters()` take the "nothing persisted" path.
 */
internal class UnscentedKalmanFilterPluginTest {

    private val aapsLogger = mock<AAPSLogger>()
    private val rh = mock<ResourceHelper>()
    private val preferences = mock<Preferences>()
    private val persistenceLayer = mock<PersistenceLayer>()

    // Guard-disabled by default (IOB unavailable → compression gate off), so the existing tests
    // exercise the unchanged UKF. A compression test supplies a stubbed low-IOB Lazy.
    private fun plugin(
        iobLazy: Lazy<IobCobCalculator> = Lazy { throw IllegalStateException("no IOB in unit test") }
    ) = UnscentedKalmanFilterPlugin(aapsLogger, rh, preferences, persistenceLayer, iobLazy)

    /** Newest-first series (data[0] = most recent) at [stepMin]-minute spacing, timestamps descending. */
    private fun series(vararg values: Double, stepMin: Long = 5): MutableList<InMemoryGlucoseValue> {
        val base = 1_700_000_000_000L
        return values.mapIndexed { i, v ->
            InMemoryGlucoseValue(timestamp = base - i * stepMin * 60_000L, value = v)
        }.toMutableList()
    }

    @Test fun `empty input returns the same empty list`() {
        val data = mutableListOf<InMemoryGlucoseValue>()
        val out = plugin().smooth(data)
        assertThat(out).isSameInstanceAs(data)
        assertThat(out).isEmpty()
    }

    @Test fun `a single value is copied to smoothed, floored at 39`() {
        assertThat(plugin().smooth(series(100.0))[0].smoothed).isEqualTo(100.0)
        assertThat(plugin().smooth(series(20.0))[0].smoothed).isEqualTo(39.0)
    }

    @Test fun `error-code (38) values collapse to the 39 floor with no valid segment`() {
        val out = plugin().smooth(series(38.0, 38.0, 38.0))
        assertThat(out.map { it.smoothed }).containsExactly(39.0, 39.0, 39.0)
    }

    @Test fun `a clean series smooths every point to a sane value`() {
        val out = plugin().smooth(series(101.0, 99.0, 100.0, 102.0, 98.0, 100.0, 101.0, 99.0, 100.0, 100.0))
        assertThat(out).hasSize(10)
        out.forEach {
            assertThat(it.smoothed).isNotNull()
            assertThat(it.smoothed!!).isAtLeast(39.0)
            assertThat(it.smoothed!!).isWithin(30.0).of(100.0)
        }
    }

    @Test fun `a rising series produces a rising smoothed trend`() {
        // newest-first: data[0] is the most recent (highest) value, data.last() the oldest (lowest)
        val out = plugin().smooth(series(150.0, 140.0, 130.0, 120.0, 110.0, 100.0, 90.0, 80.0))
        assertThat(out.first().smoothed!!).isGreaterThan(out.last().smoothed!!)
    }

    @Test fun `an isolated spike is dampened toward the surrounding level`() {
        // stable 100s with one 300 spike — outlier handling must pull the smoothed spike far below the raw 300
        val out = plugin().smooth(series(100.0, 100.0, 100.0, 300.0, 100.0, 100.0, 100.0, 100.0))
        val spike = out[3]
        assertThat(spike.value).isEqualTo(300.0)
        assertThat(spike.smoothed!!).isLessThan(200.0)
    }

    @Test fun `data spanning a major gap is split into segments and both clusters are smoothed`() {
        val base = 1_700_000_000_000L
        val clusterA = listOf(100.0, 101.0, 99.0).mapIndexed { i, v -> InMemoryGlucoseValue(timestamp = base - i * 5 * 60_000L, value = v) }
        val gapBase = base - (3 * 5 + 120) * 60_000L // 120-minute (major) gap after cluster A
        val clusterB = listOf(120.0, 119.0, 121.0).mapIndexed { i, v -> InMemoryGlucoseValue(timestamp = gapBase - i * 5 * 60_000L, value = v) }
        val out = plugin().smooth((clusterA + clusterB).toMutableList())
        assertThat(out.count { it.smoothed != null }).isAtLeast(4)
    }

    @Test fun `smoothing is deterministic across fresh instances`() {
        val a = plugin().smooth(series(120.0, 118.0, 122.0, 119.0, 121.0, 120.0, 118.0))
        val b = plugin().smooth(series(120.0, 118.0, 122.0, 119.0, 121.0, 120.0, 118.0))
        a.indices.forEach { assertThat(b[it].smoothed!!).isWithin(1e-9).of(a[it].smoothed!!) }
    }

    private fun iobLazy(totalU: Double) = Lazy<IobCobCalculator> {
        mock {
            on { calculateIobFromBolus() } doReturn IobTotal(0L, iob = totalU)
            on { calculateIobFromTempBasalsIncludingConvertedExtended() } doReturn IobTotal(0L, iob = 0.0)
        }
    }

    @Test fun `a compression low with near-zero IOB is damped, not tracked to the floor`() {
        // newest-first: steady ~100 then a steep fall toward 40 (a compression dip).
        val vals = doubleArrayOf(40.0, 44.0, 60.0, 82.0, 100.0, 100.0, 100.0, 100.0)
        val damped = plugin(iobLazy(0.1)).smooth(series(*vals))[0].smoothed!!
        // With real insulin on board (guard disabled) the same fall IS followed down.
        val followed = plugin(iobLazy(3.0)).smooth(series(*vals))[0].smoothed!!
        assertThat(damped).isGreaterThan(52.0)            // held well above the 40 floor
        assertThat(damped).isGreaterThan(followed + 5.0)  // and clearly higher than the un-gated case
    }

    @Test fun `negative basal IOB does not arm the compression gate`() {
        // Bolus IOB 3.0U (real insulin on board) but basal IOB -5.0U (loop zero-temping a descent).
        // Summed naively that is -2.0U (< 2 → the gate would DAMP a genuine insulin-driven low). The
        // fix counts only POSITIVE basal, so total = 3.0U and the fall is FOLLOWED, not masked.
        val iob = Lazy<IobCobCalculator> {
            mock {
                on { calculateIobFromBolus() } doReturn IobTotal(0L, iob = 3.0)
                on { calculateIobFromTempBasalsIncludingConvertedExtended() } doReturn IobTotal(0L, iob = -5.0)
            }
        }
        val vals = doubleArrayOf(40.0, 44.0, 60.0, 82.0, 100.0, 100.0, 100.0, 100.0)
        val followed = plugin(iob).smooth(series(*vals))[0].smoothed!!
        val damped = plugin(iobLazy(0.1)).smooth(series(*vals))[0].smoothed!!
        assertThat(followed).isLessThan(damped - 5.0)     // followed down, NOT held up by the gate
    }

    // ── One-minute cadence (2026-08-01) ─────────────────────────────────────────────────────
    // The filter is fed the five-minute bucketed series today, so every spacing it has ever seen
    // is 5.0. Routing it to a native one-minute series exposed three assumptions tuned there.

    @Test fun `a one-minute series is actually smoothed, not passed through`() {
        // Before the fix the segment test required spacing in 2.0..60.0, so every consecutive
        // pair broke a segment, none reached the two-sample minimum, and findValidSegments
        // returned empty. The filter then fell back to copying raw values and did nothing at all.
        val noisy = series(120.0, 118.0, 123.0, 119.0, 124.0, 120.0, 125.0, 121.0,
                           126.0, 122.0, 127.0, 123.0, stepMin = 1)
        val out = plugin().smooth(noisy)
        val changed = out.count { it.smoothed != it.value }
        assertThat(changed).isGreaterThan(0)
    }

    @Test fun `the same series at five minutes is smoothed too, so the fix is not cadence-specific`() {
        val noisy = series(120.0, 118.0, 123.0, 119.0, 124.0, 120.0, 125.0, 121.0,
                           126.0, 122.0, 127.0, 123.0, stepMin = 5)
        val out = plugin().smooth(noisy)
        assertThat(out.count { it.smoothed != it.value }).isGreaterThan(0)
    }

    @Test fun `median spacing is read from the data`() {
        val p = plugin()
        assertThat(p.medianSpacingMinutes(series(100.0, 101.0, 102.0, 103.0, stepMin = 1))).isEqualTo(1.0)
        assertThat(p.medianSpacingMinutes(series(100.0, 101.0, 102.0, 103.0, stepMin = 5))).isEqualTo(5.0)
        assertThat(p.medianSpacingMinutes(series(100.0))).isNull()
    }

    @Test fun `duration-defined windows resize with cadence`() {
        // R adaptation is meant to be 90 minutes and compression follow-through 15 minutes.
        // Both were fixed reading counts tuned at five-minute spacing.
        val atFive = plugin().apply { adaptWindowsToCadence(series(100.0, 101.0, 102.0, 103.0, stepMin = 5)) }
        val atOne = plugin().apply { adaptWindowsToCadence(series(100.0, 101.0, 102.0, 103.0, stepMin = 1)) }
        assertThat(atFive.innovationWindowForTest()).isEqualTo(18)   // 90 / 5
        assertThat(atOne.innovationWindowForTest()).isEqualTo(90)    // 90 / 1, not 18
        assertThat(atFive.maxCompressionForTest()).isEqualTo(3)      // 15 / 5
        assertThat(atOne.maxCompressionForTest()).isEqualTo(15)      // 15 / 1, not 3
    }

    @Test fun `an unreadable spacing falls back to the five-minute counts`() {
        val p = plugin().apply { adaptWindowsToCadence(series(100.0)) }
        assertThat(p.innovationWindowForTest()).isEqualTo(18)
        assertThat(p.maxCompressionForTest()).isEqualTo(3)
    }
}
