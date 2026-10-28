package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.core.keys.DoubleKey
import app.aaps.plugins.aps.openAPSBoostV5.BoostV5AutoConfigApply.Outcome
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Dose-path audit item 22. While the TBR raise-guard is tripped (TBR<70 over 4% or time<54 at or
 * over 1%) the weekly re-derivation holds every insulin-adding move, not only the three caps: a
 * fall in hypoCaution, a rise in aggression and a larger primer are held as well. Aggression is
 * never auto-raised above neutral (1.0); a value above 1.0 set by hand is kept and may be lowered.
 */
class RedriveLooseningGuardTest {

    private val AGG = DoubleKey.ApsBoostV5Aggression
    private val HC = DoubleKey.ApsBoostV5HypoCaution
    private val CCAP = DoubleKey.ApsBoostV5CommittedCapU
    private val PRIMER = DoubleKey.ApsBoostV5PrimerCapU

    private fun suggestion(tbr70: Double, sev54: Double, tdd: Double = 40.0) =
        BoostV5AutoConfig.compute(
            BoostV5AutoConfig.V1Profile(
                daysWithData = 28, bgReadingCount = 6000, tddMedianU = tdd,
                manualBolusesU = List(20) { 4.0 }, smbAmountsU = List(200) { 0.3 },
                tbrBelow70Pct = tbr70, timeBelow54Pct = sev54, meanGlucoseMgdl = 130.0,
                currentMaxIobU = 6.0, currentMaxBolusU = 2.5
            )
        )!!

    private class Store(vararg initial: Pair<DoubleKey, Double>) {
        val stored = mutableMapOf(*initial)
        val baseline = mutableMapOf<DoubleKey, Double>()
        val pending = mutableMapOf<DoubleKey, Double>()
        val written = mutableMapOf<DoubleKey, Double>()
        val writes = mutableListOf<Pair<DoubleKey, Double>>()
        fun run(tbr70: Double, sev54: Double, tdd: Double = 40.0): List<BoostV5AutoConfigApply.Resolution> {
            val s = BoostV5AutoConfig.compute(
                BoostV5AutoConfig.V1Profile(
                    daysWithData = 28, bgReadingCount = 6000, tddMedianU = tdd,
                    manualBolusesU = List(20) { 4.0 }, smbAmountsU = List(200) { 0.3 },
                    tbrBelow70Pct = tbr70, timeBelow54Pct = sev54, meanGlucoseMgdl = 130.0,
                    currentMaxIobU = 6.0, currentMaxBolusU = 2.5))!!
            return BoostV5AutoConfigApply.redrive(
                s, tbr70, sev54,
                storedValue = { stored[it] }, baselineValue = { baseline[it] }, pendingValue = { pending[it] },
                put = { k, v -> writes += k to v; stored[k] = v },
                setBaseline = { k, v -> baseline[k] = v },
                setPending = { k, v -> if (v == null) pending.remove(k) else pending[k] = v },
                lastWritten = { written[it] }, recordWritten = { k, v -> written[k] = v })
        }
    }

    @Test fun `hypoCaution falling is held while the guard is tripped`() {
        val st = Store(HC to 2.0, AGG to 0.85)
        st.run(8.0, 2.0)                                   // baseline: derived caution 2.0
        repeat(3) {
            val r = st.run(5.0, 0.5)                       // derived 1.3; TBR<70 5% still over the 4% guard
            assertThat(r.first { it.key == HC }.outcome).isEqualTo(Outcome.SUGGESTED_NOT_APPLIED_TBR)
        }
        assertThat(st.stored[HC]).isEqualTo(2.0)
        assertThat(st.writes.none { it.first == HC }).isTrue()
    }

    @Test fun `hypoCaution falling on severe time below range alone is held`() {
        val st = Store(HC to 2.0, AGG to 0.85)
        st.run(8.0, 2.0)
        repeat(2) { st.run(3.0, 1.2) }                     // <70 under 4% but <54 over 1%
        assertThat(st.stored[HC]).isEqualTo(2.0)
    }

    @Test fun `hypoCaution falls once the guard clears`() {
        val st = Store(HC to 2.0, AGG to 0.85)
        st.run(8.0, 2.0)
        repeat(2) { st.run(5.0, 0.5) }                     // held
        repeat(2) { st.run(3.0, 0.5) }                     // guard clear; derived 1.0; confirm twice
        assertThat(st.stored[HC]!!).isLessThan(2.0)
    }

    @Test fun `aggression rising is held while the guard is tripped`() {
        val st = Store(AGG to 0.85, HC to 1.0)
        st.run(7.0, 0.5)                                   // hypo-prone: derived aggression 0.85
        repeat(3) {
            val r = st.run(5.0, 0.5)                       // derived 0.92, but TBR<70 5% trips the guard
            assertThat(r.first { it.key == AGG }.outcome).isEqualTo(Outcome.SUGGESTED_NOT_APPLIED_TBR)
        }
        assertThat(st.stored[AGG]).isEqualTo(0.85)
    }

    @Test fun `aggression is never auto-raised above neutral`() {
        val st = Store(AGG to 0.95, HC to 1.0)
        st.run(7.0, 0.5)                                   // baseline 0.85
        repeat(2) { st.run(1.0, 0.1) }                     // derived 1.0: +0.15 would give 1.10
        assertThat(st.stored[AGG]!!).isWithin(1e-9).of(1.0)
    }

    @Test fun `a hand-set aggression above neutral is not raised further`() {
        val st = Store(AGG to 1.1, HC to 1.0)
        st.run(5.0, 0.5)                                   // baseline 0.92
        repeat(3) {
            val r = st.run(1.0, 0.1)                       // derived 1.0: +0.08 would give 1.18
            assertThat(r.first { it.key == AGG }.outcome).isEqualTo(Outcome.AT_NEUTRAL_CEILING)
        }
        assertThat(st.stored[AGG]).isEqualTo(1.1)
        assertThat(st.writes.none { it.first == AGG }).isTrue()
    }

    @Test fun `a hand-set aggression above neutral may still be lowered`() {
        val st = Store(AGG to 1.2, HC to 1.0)
        st.run(1.0, 0.1)                                   // baseline 1.0
        repeat(2) { st.run(5.0, 0.5) }                     // derived 0.92: a tightening, applies under the guard
        assertThat(st.stored[AGG]!!).isWithin(1e-9).of(1.12)
    }

    @Test fun `a larger primer is held while the guard is tripped`() {
        // committedCap 1.0 and a primer auto-config wrote at 0.3; this window derives 0.6 x 1.0.
        val st = Store(CCAP to 1.0, PRIMER to 0.3, AGG to 0.92, HC to 1.3)
        st.written[PRIMER] = 0.3
        val r = st.run(5.0, 0.5)
        assertThat(r.first { it.key == PRIMER }.outcome).isEqualTo(Outcome.SUGGESTED_NOT_APPLIED_TBR)
        assertThat(st.stored[PRIMER]).isEqualTo(0.3)
    }

    @Test fun `a smaller primer still applies while the guard is tripped`() {
        val st = Store(CCAP to 1.0, PRIMER to 0.9, AGG to 0.92, HC to 1.3)
        st.written[PRIMER] = 0.9
        st.run(5.0, 0.5)
        assertThat(st.stored[PRIMER]!!).isWithin(1e-9).of(0.6)
    }

    @Test fun `a held raise keeps its movement for when the guard clears`() {
        val st = Store(CCAP to 1.0, AGG to 1.0, HC to 1.0)
        st.run(5.0, 0.5, tdd = 40.0)                       // baseline committedCap 1.0
        st.run(5.0, 0.5, tdd = 48.0)                       // derived 1.2, held
        assertThat(st.stored[CCAP]).isEqualTo(1.0)
        st.run(1.0, 0.1, tdd = 48.0)                       // guard clear: the held movement arrives
        assertThat(st.stored[CCAP]!!).isWithin(1e-9).of(1.2)
    }

    @Test fun `the suggestion used for these cases derives what the comments say`() {
        assertThat(suggestion(7.0, 0.5).aggression).isEqualTo(0.85)
        assertThat(suggestion(5.0, 0.5).aggression).isEqualTo(0.92)
        assertThat(suggestion(1.0, 0.1).aggression).isEqualTo(1.0)
        assertThat(suggestion(8.0, 2.0).hypoCaution).isEqualTo(2.0)
        assertThat(suggestion(5.0, 0.5).hypoCaution).isEqualTo(1.3)
        assertThat(suggestion(5.0, 0.5).primerCapU / suggestion(5.0, 0.5).committedCapU).isWithin(1e-9).of(0.6)
    }
}
