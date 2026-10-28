package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * The shadow must never reach the dose, must survive a broken persistence layer, and must not
 * assert a projection it cannot support. These are the invariants that make it safe to flash
 * beside a live loop rather than the ones that make it correct.
 */
class BoostVwaTddShadowTest {

    private val hour = 60L * 60 * 1000
    private val day = 24 * hour
    private val anchor = 3 * hour                       // the default quiet hour

    private class Store(var blob: String = "") {

        var loadThrows = false
        var saveThrows = false
        fun shadow() = BoostVwaTddShadow(
            loadState = { if (loadThrows) throw RuntimeException("read boom") else blob },
            saveState = { if (saveThrows) throw RuntimeException("write boom") else blob = it },
        )
    }

    /** An instant a given number of hours after the anchor of an arbitrary day. */
    private fun at(hoursAfterAnchor: Double) = 1000L * day + anchor +
        (hoursAfterAnchor * hour).toLong()

    @Test fun `missing or impossible inputs produce no estimate rather than a substituted one`() {
        assertThat(Store().shadow().compute(at(12.0), null, 30.0)).isNull()
        assertThat(Store().shadow().compute(at(12.0), 10.0, null)).isNull()
        assertThat(Store().shadow().compute(at(12.0), 10.0, 0.0)).isNull()
        assertThat(Store().shadow().compute(at(12.0), -1.0, 30.0)).isNull()
    }

    @Test fun `the blend sits half way between the seven-day term and the bounded projection`() {
        val s = Store().shadow()
        // Twelve hours in, the population curve puts about 0.47 of the day behind us, so 14 U
        // delivered projects to roughly 30 and the blend should sit between that and the 20 U
        // seven-day term rather than at either end.
        val r = s.compute(at(12.0), 14.0, 20.0)!!
        assertThat(r.dayFraction).isGreaterThan(0.4)
        assertThat(r.projection).isGreaterThan(20.0)
        assertThat(r.vwaBlend).isGreaterThan(20.0)
        assertThat(r.vwaBlend).isLessThan(r.projection)
        assertThat(r.vwaBlend).isWithin(1e-9).of(0.5 * 20.0 + 0.5 * minOf(r.projection, 40.0))
    }

    @Test fun `a projection is never allowed beyond half to twice the seven-day term`() {
        val s = Store().shadow()
        val wild = s.compute(at(12.0), 200.0, 20.0)!!    // an implausible morning
        assertThat(wild.projection).isGreaterThan(40.0)
        assertThat(wild.vwaBlend).isAtMost(0.5 * 20.0 + 0.5 * 40.0)
        val none = s.compute(at(12.0), 0.0, 20.0)!!
        assertThat(none.vwaBlend).isAtLeast(0.5 * 20.0 + 0.5 * 10.0)
    }

    @Test fun `too early in the day the estimate abstains from dividing by a small fraction`() {
        val s = Store().shadow()
        val r = s.compute(at(0.5), 0.4, 20.0)!!
        assertThat(r.dayFraction).isLessThan(BoostVwaTddShadow.FRACTION_FLOOR)
        assertThat(r.usedPreviousDay).isTrue()
        // With no previous day yet, it falls back to the seven-day term and moves nothing.
        assertThat(r.vwaBlend).isWithin(1e-9).of(20.0)
    }

    @Test fun `the previous day carries the estimate across the anchor once one exists`() {
        val st = Store()
        val s = st.shadow()
        // Run a full day that delivers 30 U, then step past the anchor into the next.
        for (h in 0..23) s.compute(at(h.toDouble()), 30.0 * (h + 1) / 24.0, 20.0)
        val next = s.compute(at(24.5), 0.5, 20.0)!!
        assertThat(next.usedPreviousDay).isTrue()
        assertThat(next.projection).isWithin(0.5).of(30.0)
        assertThat(next.vwaBlend).isGreaterThan(20.0)   // yesterday ran heavy, so today starts high
    }

    @Test fun `the curve learns the participant and stays a cumulative fraction`() {
        val st = Store()
        val s = st.shadow()
        val before = s.curveSnapshot()
        for (d in 0..2) for (h in 0..23) {
            s.compute(at(d * 24.0 + h), 24.0 * (h + 1) / 24.0, 20.0)
        }
        s.compute(at(3 * 24.0 + 1), 1.0, 20.0)
        val after = s.curveSnapshot()
        assertThat(after.size).isEqualTo(BoostVwaTddShadow.BUCKETS)
        assertThat(after.first()).isAtLeast(0.0)
        assertThat(after.last()).isWithin(1e-9).of(1.0)
        for (i in 1 until after.size) assertThat(after[i]).isAtLeast(after[i - 1])
        assertThat(after.toList()).isNotEqualTo(before.toList())
    }

    @Test fun `a throwing persistence layer never propagates`() {
        val st = Store()
        st.loadThrows = true
        assertThat(st.shadow().compute(at(12.0), 10.0, 20.0)).isNotNull()
        val st2 = Store()
        st2.saveThrows = true
        assertThat(st2.shadow().compute(at(12.0), 10.0, 20.0)).isNotNull()
    }

    @Test fun `a corrupt blob falls back to the population curve rather than failing`() {
        val st = Store(blob = "{not json at all")
        val r = st.shadow().compute(at(12.0), 10.0, 20.0)
        assertThat(r).isNotNull()
        assertThat(r!!.curveDays).isEqualTo(0)
    }

    @Test fun `state survives a restart`() {
        val st = Store()
        val first = st.shadow()
        for (h in 0..23) first.compute(at(h.toDouble()), 30.0 * (h + 1) / 24.0, 20.0)
        first.compute(at(25.0), 1.0, 20.0)
        val reloaded = st.shadow().compute(at(25.5), 1.2, 20.0)!!
        assertThat(reloaded.curveDays).isAtLeast(1)
    }

    @Test fun `history warming folds one day per call and then stops`() {
        val st = Store()
        val s = st.shadow()
        // a flat day: every half hour delivers the same, so the curve it implies is a ramp
        val flat = { _: Long, _: Long -> 30.0 / BoostVwaTddShadow.WARM_SLICES }
        repeat(BoostVwaTddShadow.WARM_DAYS + 3) { s.warmFromHistory(at(12.0), flat) }
        val r = s.compute(at(12.0), 10.0, 20.0)!!
        assertThat(r.curveDays).isAtMost(BoostVwaTddShadow.WARM_DAYS)
        assertThat(r.curveDays).isAtLeast(1)
    }

    @Test fun `warming stops rather than inventing where the phone cannot answer`() {
        val st = Store()
        val s = st.shadow()
        s.warmFromHistory(at(12.0)) { _, _ -> null }
        val r = s.compute(at(12.0), 10.0, 20.0)!!
        assertThat(r.curveDays).isEqualTo(0)
    }

    @Test fun `a flat history produces a curve close to a straight ramp`() {
        val st = Store()
        val s = st.shadow()
        val flat = { _: Long, _: Long -> 24.0 / BoostVwaTddShadow.WARM_SLICES }
        repeat(BoostVwaTddShadow.WARM_DAYS) { s.warmFromHistory(at(12.0), flat) }
        val c = s.curveSnapshot()
        // a ramp puts about half the day behind you at the halfway point; the population seed
        // it started from is shrunk toward that as the days accumulate
        assertThat(c[c.size / 2]).isGreaterThan(0.30)
        assertThat(c[c.size / 2]).isLessThan(0.70)
        assertThat(c.last()).isWithin(1e-9).of(1.0)
    }
}
