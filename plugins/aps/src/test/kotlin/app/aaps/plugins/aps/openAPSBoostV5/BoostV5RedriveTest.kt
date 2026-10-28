package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.core.keys.DoubleKey
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-08-03 periodic re-derivation, rev 2 — MOVEMENT tracking.
 *
 * The derivation's movement since the last write is applied to whatever the knob is currently set
 * to, rather than the knob being overwritten with a fresh absolute derivation. The property that
 * makes this work is that `current / derived` is invariant across a re-derivation: a user's own
 * offset is neither discarded nor compounded.
 *
 * rev 1 used an applied-value ledger to decide which knobs auto-config "owned". It was inert on
 * every existing install, because the ledger could only be filled by the onboarding path, which had
 * already run months earlier. Movement tracking needs no ownership at all — nothing is overwritten.
 */
class BoostV5RedriveTest {

    private val CCAP = DoubleKey.ApsBoostV5CommittedCapU
    private val FCAP = DoubleKey.ApsBoostV5ConfirmedCapU
    private val CUM = DoubleKey.ApsBoostCumulativeSmbCap60Min
    private val AGG = DoubleKey.ApsBoostV5Aggression
    private val HC = DoubleKey.ApsBoostV5HypoCaution

    /** committedCap is driven by TDD/40, which is what actually binds it. */
    private fun suggestionForTdd(tdd: Double, tbr70: Double = 1.0, sev54: Double = 0.1) =
        BoostV5AutoConfig.compute(
            BoostV5AutoConfig.V1Profile(
                daysWithData = 28, bgReadingCount = 6000, tddMedianU = tdd,
                manualBolusesU = List(20) { 4.0 }, smbAmountsU = List(200) { 0.3 },
                tbrBelow70Pct = tbr70, timeBelow54Pct = sev54, meanGlucoseMgdl = 130.0,
                currentMaxIobU = 6.0, currentMaxBolusU = 2.5
            )
        )!!

    private class Store(val stored: MutableMap<DoubleKey, Double>) {
        val baseline = mutableMapOf<DoubleKey, Double>()
        val pending = mutableMapOf<DoubleKey, Double>()
        val writes = mutableListOf<Pair<DoubleKey, Double>>()
        fun run(s: BoostV5AutoConfig.V5Suggestion, tbr70: Double = 1.0, sev54: Double = 0.1) =
            BoostV5AutoConfigApply.redrive(
                s, tbr70, sev54,
                storedValue = { stored[it] },
                baselineValue = { baseline[it] },
                pendingValue = { pending[it] },
                put = { k, v -> writes += k to v; stored[k] = v },
                setBaseline = { k, v -> baseline[k] = v },
                setPending = { k, v -> if (v == null) pending.remove(k) else pending[k] = v })
    }

    private fun freshStore() = Store(mutableMapOf(
        CCAP to 1.0, FCAP to 3.0, CUM to 5.0, AGG to 1.0, HC to 1.0,
        DoubleKey.ApsBoostV5PrimerCapU to 0.4))

    // ── the first run establishes a baseline and changes nothing ───────────────────────────────
    @Test fun `first run records a baseline and writes nothing`() {
        val st = freshStore()
        val res = st.run(suggestionForTdd(40.0))
        assertThat(res.filter { it.key in BoostV5AutoConfigApply.REDRIVE_KEYS }
                      .all { it.outcome == BoostV5AutoConfigApply.Outcome.BASELINE_RECORDED }).isTrue()
        assertThat(st.writes.map { it.first }).containsNoneIn(BoostV5AutoConfigApply.REDRIVE_KEYS)
        assertThat(st.baseline).isNotEmpty()
    }

    // ── the load-bearing property ──────────────────────────────────────────────────────────────
    @Test fun `a user's offset is preserved when the driver moves`() {
        val st = freshStore()
        st.run(suggestionForTdd(40.0))                       // baseline: derived ccap = 1.0
        st.stored[CCAP] = 1.8                                // the user raises it well above derived
        st.run(suggestionForTdd(48.0))                       // TDD +20% -> derived 1.2
        assertThat(st.stored[CCAP]!!).isWithin(1e-6).of(2.16)          // 1.8 x 1.2
        assertThat(st.stored[CCAP]!! / 1.2).isWithin(1e-6).of(1.8)     // offset exactly preserved
    }

    @Test fun `repeated moves do not compound the offset`() {
        val st = freshStore()
        st.stored[CCAP] = 1.5
        st.run(suggestionForTdd(40.0))                       // baseline 1.0, offset x1.5
        st.run(suggestionForTdd(44.0))                       // derived 1.1
        val afterFirst = st.stored[CCAP]!!
        st.run(suggestionForTdd(48.4))                       // derived 1.21
        val afterSecond = st.stored[CCAP]!!
        assertThat(afterFirst / 1.1).isWithin(1e-2).of(1.5)
        assertThat(afterSecond / 1.21).isWithin(1e-2).of(1.5)
    }

    @Test fun `a knob the user never touched still tracks its driver`() {
        val st = freshStore()
        st.run(suggestionForTdd(40.0))
        st.run(suggestionForTdd(48.0))                       // +20%
        assertThat(st.stored[CCAP]!!).isWithin(1e-6).of(1.2)
    }

    // ── filters ────────────────────────────────────────────────────────────────────────────────
    @Test fun `a sub-noise move is not written and accumulates`() {
        val st = freshStore()
        st.run(suggestionForTdd(40.0))                       // baseline derived 1.0
        st.run(suggestionForTdd(41.2))                       // derived 1.03 -> move 0.03 < 0.07 band
        assertThat(st.stored[CCAP]).isEqualTo(1.0)
        assertThat(st.baseline[CCAP]).isEqualTo(1.0)         // NOT advanced, so the move is retained
        st.run(suggestionForTdd(44.0))                       // derived 1.1 -> accumulated > band
        assertThat(st.stored[CCAP]!!).isWithin(1e-6).of(1.1)
    }

    @Test fun `one step is bounded even when the driver jumps`() {
        val st = freshStore()
        st.run(suggestionForTdd(40.0))                       // baseline 1.0
        st.run(suggestionForTdd(80.0))                       // derived 2.0 — a doubling
        assertThat(st.stored[CCAP]!!).isWithin(1e-6).of(1.25)   // capped at +25% in one step
    }

    @Test fun `a clipped step keeps its remainder and converges over later runs`() {
        // The 2026-08-04 concentration-change case: diluting U200 to U100 roughly DOUBLES
        // TDD-in-units, so the derived committedCap doubles in one step. The step cap allows only
        // +25% per evaluation; if the baseline advanced to the full derived value the remainder
        // would be discarded and the cap would stall ~40% short of target forever.
        val st = freshStore()
        st.run(suggestionForTdd(40.0))                       // baseline: derived ccap 1.0
        val target = 2.0                                     // TDD 80 -> derived ccap 2.0
        val path = (1..6).map { st.run(suggestionForTdd(80.0)); st.stored[CCAP]!! }
        // each step is bounded to +25%...
        assertThat(path[0]).isWithin(1e-6).of(1.25)
        // ...and it keeps climbing rather than stalling at the first clipped step
        assertThat(path[1]).isGreaterThan(path[0])
        assertThat(path[2]).isGreaterThan(path[1])
        // It settles once the residual falls INSIDE the deadband, which is the correct stopping
        // point — the last 0.05 U is below the measured noise floor for this knob, so writing it
        // would be noise-chasing. What matters is that it got there instead of stranding at 1.25.
        val band = BoostV5AutoConfigApply.REDRIVE_DEADBAND[CCAP]!!
        assertThat(target - path.last()).isAtMost(band)
        assertThat(path.last()).isGreaterThan(1.9)
    }

    @Test fun `values are clamped to the preference range`() {
        val st = freshStore()
        st.stored[CCAP] = CCAP.max
        st.run(suggestionForTdd(40.0))
        st.run(suggestionForTdd(60.0))
        assertThat(st.stored[CCAP]!!).isAtMost(CCAP.max)
    }

    // ── direction asymmetry ────────────────────────────────────────────────────────────────────
    @Test fun `a cap raise is held when the TBR guard trips, a lowering still applies`() {
        val up = freshStore()
        up.run(suggestionForTdd(40.0, tbr70 = 6.0), tbr70 = 6.0)
        up.run(suggestionForTdd(52.0, tbr70 = 6.0), tbr70 = 6.0)
        assertThat(up.stored[CCAP]).isEqualTo(1.0)                       // raise held

        val down = freshStore()
        down.run(suggestionForTdd(40.0, tbr70 = 6.0), tbr70 = 6.0)
        down.run(suggestionForTdd(32.0, tbr70 = 6.0), tbr70 = 6.0)
        assertThat(down.stored[CCAP]!!).isLessThan(1.0)                  // lowering applies
    }

    @Test fun `hypoCaution rising is a tightening and is never held by the guard`() {
        val st = freshStore()
        st.run(suggestionForTdd(40.0, tbr70 = 1.0), tbr70 = 1.0)         // baseline caution 1.0
        st.run(suggestionForTdd(40.0, tbr70 = 8.0, sev54 = 2.0), tbr70 = 8.0, sev54 = 2.0)
        st.run(suggestionForTdd(40.0, tbr70 = 8.0, sev54 = 2.0), tbr70 = 8.0, sev54 = 2.0)
        assertThat(st.stored[HC]!!).isGreaterThan(1.0)
    }

    // ── quantised knobs ────────────────────────────────────────────────────────────────────────
    @Test fun `a quantised knob is not written until the same value repeats`() {
        val st = freshStore()
        st.run(suggestionForTdd(40.0, tbr70 = 1.0), tbr70 = 1.0)         // baseline aggression 1.0
        val first = st.run(suggestionForTdd(40.0, tbr70 = 5.0), tbr70 = 5.0)
        assertThat(first.first { it.key == AGG }.outcome)
            .isEqualTo(BoostV5AutoConfigApply.Outcome.AWAITING_CONFIRMATION)
        assertThat(st.stored[AGG]).isEqualTo(1.0)
        st.run(suggestionForTdd(40.0, tbr70 = 5.0), tbr70 = 5.0)
        assertThat(st.stored[AGG]!!).isWithin(1e-6).of(0.92)
    }

    @Test fun `a flapping quantised knob is never written`() {
        val st = freshStore()
        st.run(suggestionForTdd(40.0, tbr70 = 1.0), tbr70 = 1.0)
        repeat(6) { i ->
            val tbr = if (i % 2 == 0) 5.0 else 3.0
            st.run(suggestionForTdd(40.0, tbr70 = tbr), tbr70 = tbr)
        }
        assertThat(st.stored[AGG]).isEqualTo(1.0)
        assertThat(st.writes.none { it.first == AGG }).isTrue()
    }

    @Test fun `an offset knob keeps the user's offset too`() {
        val st = freshStore()
        st.stored[AGG] = 1.1                                             // user above neutral
        st.run(suggestionForTdd(40.0, tbr70 = 1.0), tbr70 = 1.0)         // baseline derived 1.0
        st.run(suggestionForTdd(40.0, tbr70 = 5.0), tbr70 = 5.0)         // derived 0.92: -0.08
        st.run(suggestionForTdd(40.0, tbr70 = 5.0), tbr70 = 5.0)         // confirm
        assertThat(st.stored[AGG]!!).isWithin(1e-6).of(1.02)             // 1.1 - 0.08, offset kept
    }

    // ── computed knobs ─────────────────────────────────────────────────────────────────────────
    @Test fun `the cumulative cap follows the operative caps`() {
        val st = freshStore()
        st.run(suggestionForTdd(40.0))
        st.run(suggestionForTdd(48.0))                                   // ccap 1.0 -> 1.2
        assertThat(st.stored[CUM]!!).isWithin(1e-6).of(
            BoostV5AutoConfig.cumulativeCap60Min(st.stored[FCAP]!!, st.stored[CCAP]!!))
    }

    // ── configuration ──────────────────────────────────────────────────────────────────────────
    @Test fun `no deadband is applied to a quantised knob`() {
        BoostV5AutoConfigApply.REDRIVE_CONFIRM_TWICE.forEach {
            assertThat(BoostV5AutoConfigApply.REDRIVE_DEADBAND).doesNotContainKey(it)
        }
    }

    @Test fun `the schema version is bumped so rev 1's dead stamp cannot gate rev 2`() {
        // rev 1 stamped the last-run clock from a code path that could never act. If this constant
        // is not ahead of what rev 1 shipped (0), every existing install stays dormant for a
        // further 7 days after upgrading.
        assertThat(BoostV5AutoConfig.REDRIVE_SCHEMA_VERSION).isGreaterThan(0)
    }

    @Test fun `cadence and window are the values the grid selected`() {
        assertThat(BoostV5AutoConfig.REDRIVE_INTERVAL_DAYS).isEqualTo(7L)
        assertThat(BoostV5AutoConfig.REDRIVE_LOOKBACK_DAYS).isEqualTo(28L)
    }

    @Test fun `maxIOB and the bolus cap are never tracked`() {
        assertThat(BoostV5AutoConfigApply.REDRIVE_KEYS)
            .containsNoneOf(DoubleKey.ApsBoostMaxIob, DoubleKey.ApsBoostBolus)
    }
}
