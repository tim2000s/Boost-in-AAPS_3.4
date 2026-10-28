package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.plugins.aps.openAPSBoostV5.BoostV5AutoConfigApply.Outcome
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * The primer delivery route on scheduled re-derivation (BoostV5AutoConfigApply.resolvePrimerRoute).
 * Worse data moves the bolus route to the temp basal at once; better data must hold for two
 * consecutive windows before the temp basal returns to the bolus; a value auto-config did not write
 * is left alone; a thin window changes nothing.
 */
class PrimerRouteRedriveTest {

    private val ENOUGH = 6000
    private val THIN = BoostV5AutoConfig.MIN_BG_READINGS - 1

    /** The persisted state the plugin keeps between weekly runs. */
    private class State(var stored: Boolean? = null, var written: Boolean? = null, var prevWc: Boolean? = null) {
        val puts = mutableListOf<Boolean>()
        fun window(wellControlled: Boolean, bg: Int = 6000) = BoostV5AutoConfigApply.resolvePrimerRoute(
            wellControlled = wellControlled, bgReadings = bg, previousWellControlled = prevWc,
            stored = stored, lastWritten = written,
            put = { puts += it; stored = it }, recordWritten = { written = it }, recordWellControlled = { prevWc = it })
    }

    @Test fun `worsening data moves the bolus route to the temp basal on the first window`() {
        val s = State(stored = false, written = false, prevWc = true)
        val r = s.window(wellControlled = false)
        assertThat(r.outcome).isEqualTo(Outcome.REDRIVEN)
        assertThat(r.tbrFallback).isTrue()
        assertThat(s.stored).isTrue()
        assertThat(s.written).isTrue()
    }

    @Test fun `improving data needs two consecutive well-controlled windows`() {
        val s = State(stored = true, written = true, prevWc = false)
        val first = s.window(wellControlled = true)
        assertThat(first.outcome).isEqualTo(Outcome.AWAITING_CONFIRMATION)
        assertThat(first.tbrFallback).isTrue()
        assertThat(s.puts).isEmpty()
        val second = s.window(wellControlled = true)
        assertThat(second.outcome).isEqualTo(Outcome.REDRIVEN)
        assertThat(second.tbrFallback).isFalse()
        assertThat(s.stored).isFalse()
    }

    @Test fun `a single well-controlled window never moves the temp basal to the bolus`() {
        // Alternating windows: never two in a row, so the route never changes.
        val s = State(stored = true, written = true)
        repeat(4) {
            assertThat(s.window(wellControlled = true).tbrFallback).isTrue()
            assertThat(s.window(wellControlled = false).tbrFallback).isTrue()
        }
        assertThat(s.puts).isEmpty()
    }

    @Test fun `a well-controlled window with no previous verdict waits`() {
        val s = State(stored = true, written = true, prevWc = null)
        assertThat(s.window(wellControlled = true).outcome).isEqualTo(Outcome.AWAITING_CONFIRMATION)
        assertThat(s.stored).isTrue()
    }

    @Test fun `a value auto-config did not write is never overwritten`() {
        // Auto-config last wrote the temp basal; someone set the bolus since.
        val s = State(stored = false, written = true, prevWc = true)
        val r = s.window(wellControlled = false)
        assertThat(r.outcome).isEqualTo(Outcome.KEPT_USER_TUNED)
        assertThat(s.stored).isFalse()
        val t = State(stored = true, written = false, prevWc = true)
        assertThat(t.window(wellControlled = true).outcome).isEqualTo(Outcome.KEPT_USER_TUNED)
        assertThat(t.stored).isTrue()
        assertThat(s.puts + t.puts).isEmpty()
    }

    @Test fun `with no record of a write the stored value is auto-config's own`() {
        // Installs that onboarded before the written-value ledger existed.
        val s = State(stored = false, written = null, prevWc = null)
        assertThat(s.window(wellControlled = false).outcome).isEqualTo(Outcome.REDRIVEN)
        assertThat(s.stored).isTrue()
    }

    @Test fun `insufficient data changes nothing and breaks the run of windows`() {
        val s = State(stored = true, written = true, prevWc = true)
        val r = s.window(wellControlled = true, bg = THIN)
        assertThat(r.outcome).isEqualTo(Outcome.INSUFFICIENT_EVIDENCE)
        assertThat(s.puts).isEmpty()
        assertThat(s.prevWc).isNull()
        // The next adequate window is then only the first of two.
        assertThat(s.window(wellControlled = true, bg = ENOUGH).outcome).isEqualTo(Outcome.AWAITING_CONFIRMATION)
        val worse = State(stored = false, written = false)
        assertThat(worse.window(wellControlled = false, bg = THIN).outcome).isEqualTo(Outcome.INSUFFICIENT_EVIDENCE)
        assertThat(worse.stored).isFalse()
    }

    @Test fun `steady states change nothing`() {
        assertThat(State(stored = false, written = false).window(true).outcome).isEqualTo(Outcome.INSIDE_DEADBAND)
        assertThat(State(stored = true, written = true).window(false).outcome).isEqualTo(Outcome.INSIDE_DEADBAND)
    }

    @Test fun `breadcrumb names the outcome, the route and the window verdict`() {
        val s = State(stored = true, written = true, prevWc = false)
        val r = s.window(wellControlled = true)
        assertThat(BoostV5AutoConfigApply.primerRouteBreadcrumb(r, true))
            .isEqualTo("pr=AWAITING_CONFIRMATION/tb=true/wc=true/held:one-window")
    }
}
