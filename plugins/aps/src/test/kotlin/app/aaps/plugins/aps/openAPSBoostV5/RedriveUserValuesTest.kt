package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.core.keys.DoubleKey
import app.aaps.plugins.aps.openAPSBoostV5.BoostV5AutoConfigApply.Outcome
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Dose-path audit item 15. The weekly re-derivation recomputes the cumulative 60-minute cap and the
 * primer cap from the operative per-shot caps. It used to write the recomputation over whatever was
 * stored, so a cumulative cap the user had lowered was raised again and a primer the user had set
 * to 0 (its only off switch) was switched back on. Both are now kept by the rule onboarding uses:
 * a value off every factory default that is not the value auto-config last wrote is the user's.
 */
class RedriveUserValuesTest {

    private val CUM = DoubleKey.ApsBoostCumulativeSmbCap60Min
    private val PRIMER = DoubleKey.ApsBoostV5PrimerCapU
    private val CCAP = DoubleKey.ApsBoostV5CommittedCapU
    private val FCAP = DoubleKey.ApsBoostV5ConfirmedCapU

    private fun suggestion(tdd: Double = 40.0, tbr70: Double = 1.0, sev54: Double = 0.1) =
        BoostV5AutoConfig.compute(
            BoostV5AutoConfig.V1Profile(
                daysWithData = 28, bgReadingCount = 6000, tddMedianU = tdd,
                manualBolusesU = List(20) { 4.0 }, smbAmountsU = List(200) { 0.3 },
                tbrBelow70Pct = tbr70, timeBelow54Pct = sev54, meanGlucoseMgdl = 130.0,
                currentMaxIobU = 6.0, currentMaxBolusU = 2.5
            )
        )!!

    /** Caps 3.0 / 1.0 give a cumulative cap of 5.0 and, well controlled, a primer of 0.75. */
    private class Store(vararg initial: Pair<DoubleKey, Double>) {
        val stored = mutableMapOf(FCAP_ to 3.0, CCAP_ to 1.0).apply { putAll(initial) }
        val baseline = mutableMapOf<DoubleKey, Double>()
        val written = mutableMapOf<DoubleKey, Double>()
        val writes = mutableListOf<Pair<DoubleKey, Double>>()
        fun run(s: BoostV5AutoConfig.V5Suggestion, tbr70: Double = 1.0, sev54: Double = 0.1) =
            BoostV5AutoConfigApply.redrive(
                s, tbr70, sev54,
                storedValue = { stored[it] }, baselineValue = { baseline[it] }, pendingValue = { null },
                put = { k, v -> writes += k to v; stored[k] = v },
                setBaseline = { k, v -> baseline[k] = v }, setPending = { _, _ -> },
                lastWritten = { written[it] }, recordWritten = { k, v -> written[k] = v })

        companion object {
            val FCAP_ = DoubleKey.ApsBoostV5ConfirmedCapU
            val CCAP_ = DoubleKey.ApsBoostV5CommittedCapU
        }
    }

    // ── primer set to 0 ──────────────────────────────────────────────────────────────────────
    @Test fun `a primer the user set to 0 after auto-config wrote one is never switched back on`() {
        val st = Store(PRIMER to 0.0)
        st.written[PRIMER] = 0.75
        repeat(4) {
            val r = st.run(suggestion())
            assertThat(r.single { it.key == PRIMER }.outcome).isEqualTo(Outcome.KEPT_USER_TUNED)
        }
        assertThat(st.stored[PRIMER]).isEqualTo(0.0)
        assertThat(st.writes.none { it.first == PRIMER }).isTrue()
    }

    @Test fun `a stored primer of 0 with no record of a write is kept too`() {
        val st = Store(PRIMER to 0.0)
        st.run(suggestion())
        assertThat(st.stored[PRIMER]).isEqualTo(0.0)
    }

    @Test fun `a primer the user raised is kept`() {
        val st = Store(PRIMER to 1.5)
        st.written[PRIMER] = 0.75
        val r = st.run(suggestion())
        assertThat(r.single { it.key == PRIMER }.outcome).isEqualTo(Outcome.KEPT_USER_TUNED)
        assertThat(st.stored[PRIMER]).isEqualTo(1.5)
    }

    @Test fun `a primer auto-config wrote still follows committedCap`() {
        val st = Store(PRIMER to 0.75)
        st.written[PRIMER] = 0.75
        st.run(suggestion(tdd = 40.0))                     // baseline
        st.run(suggestion(tdd = 48.0))                     // committedCap 1.0 -> 1.2
        assertThat(st.stored[PRIMER]!!).isWithin(1e-9).of(0.9)
        assertThat(st.written[PRIMER]!!).isWithin(1e-9).of(0.9)
    }

    @Test fun `a never-set primer is provisioned`() {
        val st = Store()
        st.run(suggestion())
        assertThat(st.stored[PRIMER]!!).isWithin(1e-9).of(0.75)
    }

    // ── cumulative cap lowered ───────────────────────────────────────────────────────────────
    @Test fun `a cumulative cap the user lowered is not raised back`() {
        val st = Store(CUM to 3.0)
        st.written[CUM] = 5.0                              // auto-config wrote 5.0; the user set 3.0
        st.run(suggestion(tdd = 40.0))
        st.run(suggestion(tdd = 48.0))                     // caps move; the recomputation would be 5.4
        assertThat(st.stored[CUM]).isEqualTo(3.0)
        assertThat(st.writes.none { it.first == CUM }).isTrue()
    }

    @Test fun `with no record of a write a cumulative cap off the recomputation is the user's`() {
        val st = Store(CUM to 3.0)                         // the recomputation from 3.0 / 1.0 is 5.0
        val r = st.run(suggestion())
        assertThat(r.single { it.key == CUM }.outcome).isEqualTo(Outcome.KEPT_USER_TUNED)
        assertThat(st.stored[CUM]).isEqualTo(3.0)
    }

    @Test fun `with no record a cumulative cap at the recomputation is auto-config's and follows the caps`() {
        val st = Store(CUM to 5.0)
        st.run(suggestion(tdd = 40.0))
        assertThat(st.written[CUM]).isEqualTo(5.0)         // ownership recorded on first sight
        st.run(suggestion(tdd = 48.0))                     // committedCap 1.2 -> 3.0 + 2.4 = 5.4
        assertThat(st.stored[CUM]!!).isWithin(1e-9).of(5.4)
        // Once recorded, a later edit by the user is recognised exactly.
        st.stored[CUM] = 4.0
        st.run(suggestion(tdd = 60.0))
        assertThat(st.stored[CUM]).isEqualTo(4.0)
    }

    @Test fun `a cumulative cap at a factory default is auto-config's, as at onboarding`() {
        val st = Store(CUM to 10.0)                        // current factory default
        st.run(suggestion())
        assertThat(st.stored[CUM]!!).isWithin(1e-9).of(5.0)
    }

    @Test fun `onboarding records what it wrote so re-derivation can recognise it`() {
        val store = mutableMapOf<DoubleKey, Double>()
        val written = mutableMapOf<DoubleKey, Double>()
        BoostV5AutoConfigApply.applyAutoConfig(
            suggestion(), tbrBelow70Pct = 1.0, timeBelow54Pct = 0.1,
            isResolved = { false }, storedValue = { store[it] },
            put = { k, v -> store[k] = v }, markResolved = { },
            lastWritten = { written[it] }, recordWritten = { k, v -> written[k] = v })
        assertThat(written[CUM]).isEqualTo(store[CUM])
        assertThat(written[PRIMER]).isEqualTo(store[PRIMER])
    }

    // ── the ownership rule itself ────────────────────────────────────────────────────────────
    @Test fun `ownership rule`() {
        val own = BoostV5AutoConfigApply::computedKnobOwned
        assertThat(own(CUM, null, null, listOf(5.0), 1e-4)).isTrue()        // never set
        assertThat(own(CUM, 6.0, null, listOf(5.0), 1e-4)).isTrue()         // an old factory default
        assertThat(own(CUM, 5.0, 5.0, listOf(9.9), 1e-4)).isTrue()          // auto-config's last write
        assertThat(own(CUM, 3.0, 5.0, listOf(3.0), 1e-4)).isFalse()         // record wins over the heuristic
        assertThat(own(CUM, 5.0, null, listOf(5.0), 1e-4)).isTrue()         // legacy, at the recomputation
        assertThat(own(CUM, 3.0, null, listOf(5.0), 1e-4)).isFalse()        // legacy, off it
        assertThat(own(PRIMER, 0.62, null, listOf(0.38, 0.6, 0.75), 0.056)).isTrue()
        assertThat(own(PRIMER, 1.2, null, listOf(0.38, 0.6, 0.75), 0.056)).isFalse()
    }
}
