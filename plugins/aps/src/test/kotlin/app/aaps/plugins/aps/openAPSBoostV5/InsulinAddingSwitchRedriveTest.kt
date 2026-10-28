package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.core.keys.BooleanKey
import app.aaps.plugins.aps.openAPSBoostV5.BoostV5AutoConfigApply.Outcome
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Dose-path audit item 16. Aggressive early confirm and fast-carb confirm add insulin when on, and
 * were set once at onboarding and never revisited. The weekly re-derivation now re-evaluates both by
 * the primer route's rules: off on the first window that does not allow them, on only after two
 * consecutive windows that do (and never under the TBR guard), never over a value the user set.
 */
class InsulinAddingSwitchRedriveTest {

    private val THIN = BoostV5AutoConfig.MIN_BG_READINGS - 1

    /** Persisted state between weekly runs for one switch. */
    private class Switch(
        val defaultValue: Boolean,
        var stored: Boolean? = null,
        var written: Boolean? = null,
        var userMarked: Boolean = false,
        var prev: Boolean? = null
    ) {
        val puts = mutableListOf<Boolean>()
        fun window(allowsOn: Boolean, guard: Boolean = false, bg: Int = 6000) =
            BoostV5AutoConfigApply.resolveInsulinAddingSwitch(
                allowsOn = allowsOn, raiseGuard = guard, bgReadings = bg, previousAllowsOn = prev,
                stored = stored, defaultValue = defaultValue, lastWritten = written, userMarked = userMarked,
                put = { puts += it; stored = it }, recordWritten = { written = it }, recordVerdict = { prev = it })
    }

    private fun aec(stored: Boolean? = null, written: Boolean? = null, prev: Boolean? = null) =
        Switch(BooleanKey.ApsBoostV5AggressiveEarlyConfirm.defaultValue, stored, written, prev = prev)
    private fun fcc(stored: Boolean? = null, written: Boolean? = null, prev: Boolean? = null) =
        Switch(BooleanKey.ApsBoostV5FastCarbConfirm.defaultValue, stored, written, prev = prev)

    @Test fun `factory defaults are the ones the rules assume`() {
        assertThat(BooleanKey.ApsBoostV5AggressiveEarlyConfirm.defaultValue).isFalse()
        assertThat(BooleanKey.ApsBoostV5FastCarbConfirm.defaultValue).isTrue()
    }

    @Test fun `a switch auto-config turned on goes off on the first window that does not allow it`() {
        for (s in listOf(aec(stored = true, written = true, prev = true), fcc(stored = true, written = true, prev = true))) {
            val r = s.window(allowsOn = false)
            assertThat(r.outcome).isEqualTo(Outcome.REDRIVEN)
            assertThat(s.stored).isFalse()
            assertThat(s.written).isFalse()
        }
    }

    @Test fun `switching on needs two consecutive windows`() {
        val s = aec(stored = false, written = false, prev = false)
        assertThat(s.window(allowsOn = true).outcome).isEqualTo(Outcome.AWAITING_CONFIRMATION)
        assertThat(s.stored).isFalse()
        assertThat(s.window(allowsOn = true).outcome).isEqualTo(Outcome.REDRIVEN)
        assertThat(s.stored).isTrue()
    }

    @Test fun `alternating windows never switch it on`() {
        val s = fcc(stored = false, written = false)
        repeat(4) {
            s.window(allowsOn = true)
            s.window(allowsOn = false)
        }
        assertThat(s.puts).isEmpty()
    }

    @Test fun `never switched on under the TBR guard, and a guarded window does not count`() {
        val s = fcc(stored = false, written = false, prev = true)
        val r = s.window(allowsOn = true, guard = true)
        assertThat(r.outcome).isEqualTo(Outcome.SUGGESTED_NOT_APPLIED_TBR)
        assertThat(s.stored).isFalse()
        assertThat(s.prev).isFalse()
        // The next clear window is only the first of two.
        assertThat(s.window(allowsOn = true).outcome).isEqualTo(Outcome.AWAITING_CONFIRMATION)
        assertThat(s.window(allowsOn = true).outcome).isEqualTo(Outcome.REDRIVEN)
    }

    @Test fun `a value the user changed after auto-config wrote is never overridden`() {
        val on = aec(stored = true, written = false, prev = false)       // user turned it on
        assertThat(on.window(allowsOn = false).outcome).isEqualTo(Outcome.KEPT_USER_TUNED)
        assertThat(on.stored).isTrue()
        val off = fcc(stored = false, written = true, prev = true)       // user turned it off
        assertThat(off.window(allowsOn = true).outcome).isEqualTo(Outcome.KEPT_USER_TUNED)
        assertThat(off.stored).isFalse()
        assertThat(on.puts + off.puts).isEmpty()
    }

    @Test fun `a value onboarding found set by the user is never overridden`() {
        val s = aec(stored = true).apply { userMarked = true }
        repeat(3) { assertThat(s.window(allowsOn = false).outcome).isEqualTo(Outcome.KEPT_USER_TUNED) }
        assertThat(s.stored).isTrue()
    }

    @Test fun `with no record a stored value at the factory default is auto-config's`() {
        // Aggressive early confirm defaults to off: a stored off is not the user's, so it can come on.
        val s = aec(stored = false, prev = true)
        assertThat(s.window(allowsOn = true).outcome).isEqualTo(Outcome.REDRIVEN)
        assertThat(s.stored).isTrue()
        // Fast-carb confirm defaults to on: a stored on goes off on a window that does not allow it.
        val f = fcc(stored = true)
        assertThat(f.window(allowsOn = false).outcome).isEqualTo(Outcome.REDRIVEN)
        assertThat(f.stored).isFalse()
    }

    @Test fun `with no record an off-default off is not switched on`() {
        // Fast-carb confirm stored off with no record: auto-config or the user, so it is not loosened.
        val f = fcc(stored = false, prev = true)
        assertThat(f.window(allowsOn = true).outcome).isEqualTo(Outcome.KEPT_USER_TUNED)
        assertThat(f.stored).isFalse()
    }

    @Test fun `with no record an off-default on is still switched off`() {
        val s = aec(stored = true)
        assertThat(s.window(allowsOn = false).outcome).isEqualTo(Outcome.REDRIVEN)
        assertThat(s.stored).isFalse()
        assertThat(s.written).isFalse()
    }

    @Test fun `a thin window changes nothing and breaks the run`() {
        val s = aec(stored = false, written = false, prev = true)
        assertThat(s.window(allowsOn = true, bg = THIN).outcome).isEqualTo(Outcome.INSUFFICIENT_EVIDENCE)
        assertThat(s.prev).isNull()
        assertThat(s.window(allowsOn = true).outcome).isEqualTo(Outcome.AWAITING_CONFIRMATION)
        val on = aec(stored = true, written = true)
        assertThat(on.window(allowsOn = false, bg = THIN).outcome).isEqualTo(Outcome.INSUFFICIENT_EVIDENCE)
        assertThat(on.stored).isTrue()
    }

    @Test fun `the window verdicts are the onboarding rules`() {
        fun s(tbr70: Double, sev54: Double) = BoostV5AutoConfig.compute(
            BoostV5AutoConfig.V1Profile(
                daysWithData = 28, bgReadingCount = 6000, tddMedianU = 40.0,
                manualBolusesU = List(20) { 4.0 }, smbAmountsU = List(200) { 0.3 },
                tbrBelow70Pct = tbr70, timeBelow54Pct = sev54, meanGlucoseMgdl = 130.0,
                currentMaxIobU = 6.0, currentMaxBolusU = 2.5))!!
        // Aggressive early confirm: the strict well-controlled cut.
        assertThat(s(1.0, 0.1).aggressiveEarlyConfirm).isTrue()
        assertThat(s(2.0, 0.1).aggressiveEarlyConfirm).isFalse()
        // Fast-carb confirm: not hypo-prone.
        assertThat(s(5.0, 1.0).fastCarbConfirm).isTrue()
        assertThat(s(7.0, 1.0).fastCarbConfirm).isFalse()
    }

    @Test fun `breadcrumb names the switch, the outcome, the value and the verdict`() {
        val s = aec(stored = false, written = false, prev = false)
        val r = s.window(allowsOn = true)
        assertThat(BoostV5AutoConfigApply.switchBreadcrumb("aec", r, true))
            .isEqualTo("aec=AWAITING_CONFIRMATION/v=false/ok=true/held:one-window")
    }
}
