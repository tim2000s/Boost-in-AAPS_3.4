package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.core.keys.DoubleKey
import app.aaps.plugins.aps.openAPSBoostV5.BoostV5AutoConfigApply.Outcome
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Apply rules for the confirm-tranche threshold (BoostV5AutoConfigApply.resolveTrancheThreshold).
 * A higher threshold withholds more and applies on its own. A lower one releases more and, as
 * shipped, is never written (TRANCHE_ALLOW_LOWERING is false while the derivation is biased down by
 * the tranche's own effect); with lowering switched on it applies only for a well-controlled profile
 * with at least 30 labelled episodes. A value set by hand stays.
 */
class TrancheThresholdApplyTest {

    private val KEY = DoubleKey.ApsBoostV5TrancheThreshold
    private val WELL = 1.0 to 0.1          // TBR<70 %, time<54 %: inside the strict cut
    private val NOT_WELL = 2.0 to 0.1      // TBR<70 over 1.5 %

    private fun suggestion(threshold: Double?, nSmall: Int = 20, nLarge: Int = 20): BoostV5AutoConfig.V5Suggestion {
        val d = TrancheThresholdDeriver.Derivation(
            emptyList(), nSmall, nLarge, threshold, threshold?.let { 0.6 },
            if (threshold == null) TrancheThresholdDeriver.Shortfall.TOO_FEW_LABELLED else TrancheThresholdDeriver.Shortfall.NONE)
        return BoostV5AutoConfig.compute(
            BoostV5AutoConfig.V1Profile(
                daysWithData = 28, bgReadingCount = 6000, tddMedianU = 40.0,
                manualBolusesU = List(20) { 4.0 }, smbAmountsU = List(200) { 0.3 },
                tbrBelow70Pct = 1.0, timeBelow54Pct = 0.1, meanGlucoseMgdl = 130.0,
                currentMaxIobU = 6.0, currentMaxBolusU = 2.5, tranche = d
            )
        )!!
    }

    private class Box(var stored: Double? = null, var written: Double? = null) {
        val puts = mutableListOf<Double>()
        fun run(s: BoostV5AutoConfig.V5Suggestion, tbr: Pair<Double, Double>, allowLowering: Boolean = BoostV5AutoConfigApply.TRANCHE_ALLOW_LOWERING) =
            BoostV5AutoConfigApply.resolveTrancheThreshold(
                s, tbr.first, tbr.second, stored, written,
                put = { puts += it; stored = it }, recordWritten = { written = it }, allowLowering = allowLowering)
    }

    @Test fun `a higher threshold applies even when the profile is not well controlled`() {
        val b = Box()
        val r = b.run(suggestion(0.65, nSmall = 8, nLarge = 8), NOT_WELL)
        assertThat(r.outcome).isEqualTo(Outcome.APPLIED)
        assertThat(b.stored).isEqualTo(0.65)
        assertThat(b.written).isEqualTo(0.65)
    }

    @Test fun `a lower threshold is held when the profile is not well controlled`() {
        val b = Box()
        val r = b.run(suggestion(0.30, nSmall = 30, nLarge = 30), NOT_WELL, allowLowering = true)
        assertThat(r.outcome).isEqualTo(Outcome.LOOSENING_HELD)
        assertThat(r.operativeValue).isEqualTo(KEY.defaultValue)
        assertThat(r.reason).contains("not-well-controlled")
        assertThat(b.puts).isEmpty()
    }

    @Test fun `a lower threshold is held on severe time below range alone`() {
        val b = Box()
        val r = b.run(suggestion(0.30, nSmall = 30, nLarge = 30), 1.0 to 0.3, allowLowering = true)    // <54 at the cut, not under it
        assertThat(r.outcome).isEqualTo(Outcome.LOOSENING_HELD)
        assertThat(b.puts).isEmpty()
    }

    @Test fun `a lower threshold is held with fewer than 30 labelled episodes`() {
        val b = Box()
        val r = b.run(suggestion(0.30, nSmall = 15, nLarge = 14), WELL, allowLowering = true)
        assertThat(r.outcome).isEqualTo(Outcome.LOOSENING_HELD)
        assertThat(r.reason).contains("n<30")
        assertThat(b.puts).isEmpty()
    }

    @Test fun `a lower threshold applies when well controlled with at least 30 labelled episodes`() {
        val b = Box()
        val r = b.run(suggestion(0.30, nSmall = 15, nLarge = 15), WELL, allowLowering = true)
        assertThat(r.outcome).isEqualTo(Outcome.APPLIED)
        assertThat(b.stored).isEqualTo(0.30)
    }

    @Test fun `a lowering from a value auto-config raised earlier is held in the same way`() {
        val b = Box(stored = 0.65, written = 0.65)
        val r = b.run(suggestion(0.50, nSmall = 10, nLarge = 10), WELL, allowLowering = true)
        assertThat(r.outcome).isEqualTo(Outcome.LOOSENING_HELD)
        assertThat(b.stored).isEqualTo(0.65)
    }

    @Test fun `a value set by hand is kept in both directions`() {
        for (derived in listOf(0.30, 0.75)) {
            val b = Box(stored = 0.65, written = null)            // never written by auto-config
            val r = b.run(suggestion(derived, nSmall = 40, nLarge = 40), WELL)
            assertThat(r.outcome).isEqualTo(Outcome.KEPT_USER_TUNED)
            assertThat(b.puts).isEmpty()
        }
        val edited = Box(stored = 0.55, written = 0.60)           // auto-config wrote 0.60, user moved it
        assertThat(edited.run(suggestion(0.75), WELL).outcome).isEqualTo(Outcome.KEPT_USER_TUNED)
        assertThat(edited.stored).isEqualTo(0.55)
    }

    @Test fun `a value auto-config wrote itself stays under auto-config`() {
        val b = Box(stored = 0.60, written = 0.60)
        val r = b.run(suggestion(0.70), NOT_WELL)
        assertThat(r.outcome).isEqualTo(Outcome.APPLIED)
        assertThat(b.stored).isEqualTo(0.70)
    }

    @Test fun `no derivation writes nothing`() {
        val b = Box()
        val r = b.run(suggestion(null, nSmall = 3, nLarge = 2), WELL)
        assertThat(r.outcome).isEqualTo(Outcome.INSUFFICIENT_EVIDENCE)
        assertThat(r.operativeValue).isEqualTo(KEY.defaultValue)
        assertThat(b.puts).isEmpty()
    }

    @Test fun `the written value stays inside the preference bounds`() {
        val hi = Box()
        hi.run(suggestion(0.95), NOT_WELL)
        assertThat(hi.stored).isEqualTo(KEY.max)
        val lo = Box()
        lo.run(suggestion(0.05, nSmall = 40, nLarge = 40), WELL, allowLowering = true)
        assertThat(lo.stored).isEqualTo(KEY.min)
        assertThat(KEY.min).isEqualTo(0.20)
        assertThat(KEY.max).isEqualTo(0.80)
    }

    @Test fun `equal to the operative value changes nothing`() {
        val b = Box()
        assertThat(b.run(suggestion(0.48), WELL).outcome).isEqualTo(Outcome.INSIDE_DEADBAND)
        assertThat(b.puts).isEmpty()
    }

    @Test fun `onboarding resolves the threshold even without evidence and re-derivation keeps evaluating it`() {
        val store = mutableMapOf<DoubleKey, Double>()
        val resolved = mutableSetOf<DoubleKey>()
        val res = BoostV5AutoConfigApply.applyAutoConfig(
            suggestion(null, nSmall = 2, nLarge = 1), tbrBelow70Pct = 1.0, timeBelow54Pct = 0.1,
            isResolved = { it in resolved }, storedValue = { store[it] },
            put = { k, v -> store[k] = v }, markResolved = { resolved += it })
        assertThat(res.single { it.key == KEY }.outcome).isEqualTo(Outcome.INSUFFICIENT_EVIDENCE)
        assertThat(resolved).contains(KEY)
        assertThat(store).doesNotContainKey(KEY)

        val written = mutableMapOf<DoubleKey, Double>()
        val rd = BoostV5AutoConfigApply.redrive(
            suggestion(0.60), 1.0, 0.1,
            storedValue = { store[it] }, baselineValue = { null }, pendingValue = { null },
            put = { k, v -> store[k] = v }, setBaseline = { _, _ -> }, setPending = { _, _ -> },
            lastWritten = { written[it] }, recordWritten = { k, v -> written[k] = v })
        assertThat(rd.single { it.key == KEY }.outcome).isEqualTo(Outcome.REDRIVEN)
        assertThat(store[KEY]).isEqualTo(0.60)
        assertThat(written[KEY]).isEqualTo(0.60)
    }

    @Test fun `breadcrumb carries the counts and the hold reason without separators`() {
        val s = suggestion(0.30, nSmall = 12, nLarge = 9)
        val r = Box().run(s, NOT_WELL, allowLowering = true)
        val crumb = BoostV5AutoConfigApply.trancheBreadcrumb(r, s.tranche)
        assertThat(crumb).isEqualTo("tr=LOOSENING_HELD/d=0.3/op=0.48/s=12/l=9/J=0.6/held:not-well-controlled+n<30")
        assertThat(crumb).doesNotContain(",")
        assertThat(crumb).doesNotContain(";")
    }

    // ── lowering switched off (the shipped setting) ────────────────────────────────────────────
    @Test fun `as shipped, auto-config may not lower the threshold`() {
        assertThat(BoostV5AutoConfigApply.TRANCHE_ALLOW_LOWERING).isFalse()
    }

    @Test fun `with lowering off a lower threshold is held even when well controlled with ample evidence`() {
        // Every other condition for a lowering is met: strict well-controlled cut, 80 labelled episodes.
        val b = Box()
        val r = b.run(suggestion(0.30, nSmall = 40, nLarge = 40), WELL)
        assertThat(r.outcome).isEqualTo(Outcome.LOOSENING_HELD)
        assertThat(r.operativeValue).isEqualTo(KEY.defaultValue)
        assertThat(r.reason).contains("lowering-off")
        assertThat(b.puts).isEmpty()
        assertThat(BoostV5AutoConfigApply.trancheBreadcrumb(r, null)).endsWith("/held:lowering-off")
    }

    @Test fun `with lowering off the threshold still rises, and a later lower derivation leaves it there`() {
        val b = Box()
        b.run(suggestion(0.65, nSmall = 40, nLarge = 40), WELL)
        assertThat(b.stored).isEqualTo(0.65)
        val r = b.run(suggestion(0.35, nSmall = 40, nLarge = 40), WELL)
        assertThat(r.outcome).isEqualTo(Outcome.LOOSENING_HELD)
        assertThat(b.stored).isEqualTo(0.65)
        assertThat(b.puts).containsExactly(0.65)
    }

    @Test fun `with lowering off neither onboarding nor re-derivation writes a lower threshold`() {
        val s = suggestion(0.30, nSmall = 40, nLarge = 40)
        val store = mutableMapOf<DoubleKey, Double>()
        val resolved = mutableSetOf<DoubleKey>()
        val onboarding = BoostV5AutoConfigApply.applyAutoConfig(
            s, tbrBelow70Pct = 1.0, timeBelow54Pct = 0.1,
            isResolved = { it in resolved }, storedValue = { store[it] },
            put = { k, v -> store[k] = v }, markResolved = { resolved += it })
        assertThat(onboarding.single { it.key == KEY }.outcome).isEqualTo(Outcome.LOOSENING_HELD)
        val rd = BoostV5AutoConfigApply.redrive(
            s, 1.0, 0.1,
            storedValue = { store[it] }, baselineValue = { null }, pendingValue = { null },
            put = { k, v -> store[k] = v }, setBaseline = { _, _ -> }, setPending = { _, _ -> })
        assertThat(rd.single { it.key == KEY }.outcome).isEqualTo(Outcome.LOOSENING_HELD)
        assertThat(store).doesNotContainKey(KEY)
    }
}
