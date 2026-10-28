package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.plugins.aps.openAPSBoostV5.InsulinNeedWatch.Day
import app.aaps.plugins.aps.openAPSBoostV5.InsulinNeedWatch.Status
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * The insulin-need watch. The developer's own October 2026 days (insulin a day, units of insulin,
 * from backtesting/scripts/2026-10-insulin-need-alerts/daily.csv) pin the case the rule was chosen on;
 * the rest pin the gap, profile-change and cooldown behaviour a notification depends on.
 */
class InsulinNeedWatchTest {

    private val dayMs = 24L * 60 * 60 * 1000
    private val t0 = 1_788_652_800_000L      // a midnight; only differences matter

    /** 6 September to 13 October 2026. */
    private val october = listOf(
        31.6, 39.0, 31.2, 28.8, 27.2, 43.5, 42.4, 37.7, 36.9, 26.3, 32.3, 30.8, 40.0, 32.1, 33.8, 41.7, 32.3, 37.7, 38.9,
        25.3, 31.5, 35.6, 36.1, 36.1, 36.3, 29.6, 39.2, 35.3, 32.8, 39.2, 38.5, 29.3, 38.6, 52.7, 36.5, 48.2, 44.8, 34.9
    )

    private fun days(tdds: List<Double>, basal: (Int) -> Double? = { 8.0 }) =
        tdds.mapIndexed { i, x -> Day(t0 + i * dayMs, x, basal(i)) }

    @Test fun `the developer's October rise is flagged on 11 October and not on 8 October`() {
        // index 35 is 11 October, index 32 is 8 October
        val on11 = InsulinNeedWatch.evaluate(days(october.take(36)))
        assertThat(on11.status).isEqualTo(Status.ABOVE)
        assertThat(on11.recentMeanU).isWithin(0.05).of((52.7 + 36.5 + 48.2) / 3)
        assertThat(on11.baselineDays).isEqualTo(30)
        assertThat(on11.z).isGreaterThan(2.0)
        assertThat(InsulinNeedWatch.evaluate(days(october.take(33))).status).isEqualTo(Status.WITHIN)
    }

    @Test fun `a steady month is within and a sustained fall is below`() {
        val steady = List(33) { 30.0 + (it % 5) - 2 }
        assertThat(InsulinNeedWatch.evaluate(days(steady)).status).isEqualTo(Status.WITHIN)
        val falling = steady.dropLast(3) + listOf(22.0, 21.0, 23.0)
        assertThat(InsulinNeedWatch.evaluate(days(falling)).status).isEqualTo(Status.BELOW)
    }

    @Test fun `too short a month gives no verdict`() {
        val r = InsulinNeedWatch.evaluate(days(List(15) { 30.0 + (it % 3) }))
        assertThat(r.status).isEqualTo(Status.FEW_DAYS)
    }

    @Test fun `a near-empty day is a gap in the record, not a dose`() {
        val base = List(30) { 30.0 + (it % 5) - 2 }
        // a gap in the window leaves two usable days: no verdict rather than a BELOW
        assertThat(InsulinNeedWatch.evaluate(days(base + listOf(30.0, 2.0, 31.0))).status).isEqualTo(Status.FEW_DAYS)
        // a gap in the month is left out, so it does not widen the spread and hide a real rise
        val withGap = base.toMutableList().also { it[10] = 1.5 } + listOf(40.0, 41.0, 42.0)
        val r = InsulinNeedWatch.evaluate(days(withGap))
        assertThat(r.baselineDays).isEqualTo(29)
        assertThat(r.status).isEqualTo(Status.ABOVE)
    }

    @Test fun `a profile change is reported as that, not as a change in need`() {
        // undiluted U200 halves the pump units of the profile and of every dose
        val tdds = List(30) { 30.0 + (it % 5) - 2 } + listOf(16.0, 15.0, 15.5)
        val r = InsulinNeedWatch.evaluate(days(tdds) { i -> if (i < 30) 16.0 else 8.0 })
        assertThat(r.status).isEqualTo(Status.PROFILE_CHANGED)
        // the same days with an unchanged profile would have been read as a fall
        assertThat(InsulinNeedWatch.evaluate(days(tdds)).status).isEqualTo(Status.BELOW)
        // a missing profile does not count as a change
        assertThat(InsulinNeedWatch.evaluate(days(tdds) { null }).status).isEqualTo(Status.BELOW)
    }

    @Test fun `a missing yesterday leaves the window short instead of moving it back`() {
        val d = days(october.take(36))
        val yesterday = d.last().startMs
        // drop 11 October: the window is still 9 to 11 October, now with two days, so no verdict
        assertThat(InsulinNeedWatch.evaluate(d.dropLast(1), yesterday).status).isEqualTo(Status.FEW_DAYS)
        assertThat(InsulinNeedWatch.evaluate(d, yesterday).status).isEqualTo(Status.ABOVE)
    }

    @Test fun `a temporary percentage switch is divided out, a permanent one is kept`() {
        // 16 U a day profile under a 70% exercise switch stores 11.2 U
        assertThat(InsulinNeedWatch.profileDailyBasal(11.2, 70, 2 * 60 * 60 * 1000L)).isWithin(1e-9).of(16.0)
        assertThat(InsulinNeedWatch.profileDailyBasal(19.2, 120, 0L)).isWithin(1e-9).of(19.2)
    }

    @Test fun `a direction is not repeated within 14 days, the other direction is`() {
        val above = InsulinNeedWatch.evaluate(days(october.take(36)))
        val now = t0 + 40 * dayMs
        assertThat(InsulinNeedWatch.shouldNotify(above, 0L, 0L, now)).isTrue()
        assertThat(InsulinNeedWatch.shouldNotify(above, now - 13 * dayMs, 0L, now)).isFalse()
        assertThat(InsulinNeedWatch.shouldNotify(above, now - 14 * dayMs, 0L, now)).isTrue()
        assertThat(InsulinNeedWatch.shouldNotify(above, 0L, now - dayMs, now)).isTrue()
        val within = InsulinNeedWatch.evaluate(days(october.take(33)))
        assertThat(InsulinNeedWatch.shouldNotify(within, 0L, 0L, now)).isFalse()
    }

    @Test fun `the breadcrumb token carries the verdict`() {
        assertThat(InsulinNeedWatch.evaluate(days(october.take(36))).token()).matches("ndw=ABOVE/z=\\d\\.\\d/p=\\+\\d+/n=30")
        assertThat(InsulinNeedWatch.evaluate(days(List(10) { 30.0 })).token()).startsWith("ndw=FEW_DAYS")
    }
}
