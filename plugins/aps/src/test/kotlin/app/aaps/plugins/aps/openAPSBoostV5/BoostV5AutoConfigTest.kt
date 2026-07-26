package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.core.keys.DoubleKey
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Tests for the V5 auto-config calculator: conservative, transparent derivation of V5 knobs from a
 * user's last-N-day V1 history. Pure-function tests on [BoostV5AutoConfig.compute] plus the apply
 * layer ([BoostV5AutoConfigApply]) invariants.
 */
class BoostV5AutoConfigTest {

    // Default manual list has >= MIN_MANUAL_BOLUS_SAMPLES entries so the meal-bolus p90 term
    // participates (p90 = 6.0); smaller fixtures exercise the min-sample fallback explicitly.
    private fun profile(
        days: Int = 14, bg: Int = 3500, tdd: Double = 40.0,
        manual: List<Double> = listOf(3.0, 3.5, 4.0, 4.0, 4.5, 5.0, 5.0, 5.5, 6.0, 6.0),
        smb: List<Double> = listOf(0.2, 0.3, 0.4, 0.6, 0.8),
        tbr70: Double = 3.0, sev54: Double = 0.4, meanBg: Double = 130.0,
        maxIob: Double = 8.0, maxBolus: Double = 10.0
    ) = BoostV5AutoConfig.V1Profile(days, bg, tdd, manual, smb, tbr70, sev54, meanBg, maxIob, maxBolus)

    @Test fun `insufficient days returns null`() {
        assertThat(BoostV5AutoConfig.compute(profile(days = 5))).isNull()
    }

    @Test fun `insufficient bg readings returns null`() {
        assertThat(BoostV5AutoConfig.compute(profile(bg = 800))).isNull()
    }

    @Test fun `in-target user gets neutral aggression and no extra caution`() {
        val s = BoostV5AutoConfig.compute(profile(tbr70 = 2.5, sev54 = 0.2))!!
        assertThat(s.aggression).isEqualTo(1.0)
        assertThat(s.hypoCaution).isEqualTo(1.0)
        assertThat(s.fastCarbConfirm).isTrue()
    }

    @Test fun `hypo-prone user gets gentler aggression, higher caution, fast-carb off`() {
        val s = BoostV5AutoConfig.compute(profile(tbr70 = 8.0, sev54 = 2.5))!!
        assertThat(s.aggression).isEqualTo(0.85)
        assertThat(s.hypoCaution).isGreaterThan(1.0)
        assertThat(s.fastCarbConfirm).isFalse()
    }

    // 2026-07-17 — insulin-adding opt-in switches auto-enable ONLY for clearly well-controlled users.
    @Test fun `well-controlled user auto-enables aggressive early confirm and velocity-budget floor`() {
        val s = BoostV5AutoConfig.compute(profile(tbr70 = 0.6, sev54 = 0.1))!!   // user-H-like
        assertThat(s.aggressiveEarlyConfirm).isTrue()
        assertThat(s.velocityBudgetFloor).isTrue()
    }

    @Test fun `moderate-TBR user keeps the insulin-adding switches OFF`() {
        // 2.5% <70 is fine for fastCarbConfirm (!hypoProne) but OVER the strict 1.5% well-controlled cut.
        val s = BoostV5AutoConfig.compute(profile(tbr70 = 2.5, sev54 = 0.2))!!
        assertThat(s.fastCarbConfirm).isTrue()
        assertThat(s.aggressiveEarlyConfirm).isFalse()
        assertThat(s.velocityBudgetFloor).isFalse()
    }

    @Test fun `low-70 but elevated-54 keeps the insulin-adding switches OFF`() {
        val s = BoostV5AutoConfig.compute(profile(tbr70 = 1.0, sev54 = 0.5))!!   // <54 over the 0.3 cut
        assertThat(s.aggressiveEarlyConfirm).isFalse()
        assertThat(s.velocityBudgetFloor).isFalse()
    }

    @Test fun `aggression is never auto-raised above neutral`() {
        // Even a pristine, never-low user does not get aggression > 1.0 on day one.
        val s = BoostV5AutoConfig.compute(profile(tbr70 = 0.5, sev54 = 0.0))!!
        assertThat(s.aggression).isAtMost(1.0)
    }

    @Test fun `caps derive from dose distribution and clamp to ranges`() {
        val s = BoostV5AutoConfig.compute(
            profile(
                manual = listOf(2.0, 2.5, 3.0, 3.0, 3.5, 4.0, 4.0, 4.5, 5.0, 5.0),
                smb = listOf(0.3, 0.5, 0.7)
            )
        )!!
        assertThat(s.confirmedCapU).isAtLeast(1.5)
        assertThat(s.confirmedCapU).isAtMost(7.5)
        assertThat(s.committedCapU).isAtLeast(0.25)
        assertThat(s.committedCapU).isAtMost(2.5)
        assertThat(s.cumulativeSmbCap60MinU).isAtLeast(1.0)
        assertThat(s.cumulativeSmbCap60MinU).isAtMost(BoostV5AutoConfig.CUMULATIVE_CAP_MAX_U)
        // cumulative cap is never below a single confirm shot (it must allow ≥1 confirm)
        assertThat(s.cumulativeSmbCap60MinU).isAtLeast(s.confirmedCapU - 1e-9)
    }

    @Test fun `confirmed cap covers a big-meal bolus user`() {
        val big = BoostV5AutoConfig.compute(
            profile(manual = listOf(5.0, 5.0, 6.0, 6.0, 7.0, 7.0, 8.0, 9.0, 10.0, 11.0))
        )!!
        val small = BoostV5AutoConfig.compute(
            profile(manual = listOf(1.0, 1.0, 1.5, 1.5, 1.5, 2.0, 2.0, 2.0, 2.0, 2.0))
        )!!
        assertThat(big.confirmedCapU).isGreaterThan(small.confirmedCapU)
    }

    @Test fun `cumulative cap is never below a single confirmed shot, even for a big-meal user`() {
        // Big eater: confirmedCap clamps to its 7.5 ceiling. The hourly cumulative budget must not
        // saturate below that (was clamped to 5.0 before the 2026-06-26 fix).
        val s = BoostV5AutoConfig.compute(
            profile(manual = listOf(5.0, 6.0, 7.0, 7.0, 8.0, 9.0, 9.0, 10.0, 11.0, 11.0))
        )!!
        assertThat(s.confirmedCapU).isEqualTo(7.5)
        assertThat(s.cumulativeSmbCap60MinU).isAtLeast(s.confirmedCapU - 1e-9)
    }

    @Test fun `cumulative budget keeps its two holds for a big-confirm user`() {
        // 2026-07-06 amendment: the old max(5.0, confirmedCap) ceiling collapsed "one confirm +
        // two holds" to "confirm + ~0 holds" for big-confirm users (cohort: 6 of one user's 8
        // projected suppressions; another landed cumulative == confirmedCap exactly). New clamp is
        // the pref range max (10.0): conf 6.0 + 2×1.26 = 8.52 → 8.5, NOT 6.0.
        val s = BoostV5AutoConfig.compute(
            profile(
                tdd = 50.4,                                       // 50.4/40 = 1.26 committed
                manual = listOf(4.0, 4.0, 5.0, 5.0, 5.0, 6.0, 6.0, 6.0, 6.0, 6.0)  // p90 = 6.0
            )
        )!!
        assertThat(s.confirmedCapU).isEqualTo(6.0)
        assertThat(s.committedCapU).isEqualTo(1.26)
        assertThat(s.cumulativeSmbCap60MinU).isEqualTo(8.5)
    }

    @Test fun `confirmed cap ignores manual-bolus p90 when the sample is too small`() {
        // 2026-07-06 amendment (min-sample guard): one cohort user's derived confirmedCap 6.8
        // rested on a p90 of FOUR manual boluses, one an 8U outlier. With
        // n < MIN_MANUAL_BOLUS_SAMPLES the cap must come from the SMB p95 alone.
        val fourWithOutlier = listOf(2.0, 3.0, 4.0, 8.0)
        val smbs = listOf(0.3, 0.4, 0.5, 0.5, 0.6)
        val s = BoostV5AutoConfig.compute(profile(manual = fourWithOutlier, smb = smbs))!!
        // SMB p95 ≈ 0.58 → clamped to the 1.5 floor; the 8U outlier must NOT reach the cap.
        assertThat(s.confirmedCapU).isEqualTo(1.5)
        // Same doses with an honest sample size DO drive the cap.
        val tenManual = listOf(2.0, 2.0, 3.0, 3.0, 3.0, 4.0, 4.0, 4.0, 8.0, 8.0)
        val s10 = BoostV5AutoConfig.compute(profile(manual = tenManual, smb = smbs))!!
        assertThat(s10.confirmedCapU).isGreaterThan(1.5)
    }

    @Test fun `maxIob and bolus cap are carried and clamped`() {
        val s = BoostV5AutoConfig.compute(profile(maxIob = 15.0, maxBolus = 12.0))!!
        assertThat(s.maxIobU).isEqualTo(12.0)   // clamped to key max
        assertThat(s.bolusCapU).isEqualTo(10.0) // clamped to key max
    }

    @Test fun `percentile interpolates`() {
        val v = listOf(1.0, 2.0, 3.0, 4.0)
        assertThat(BoostV5AutoConfig.percentile(v, 0.0)).isEqualTo(1.0)
        assertThat(BoostV5AutoConfig.percentile(v, 100.0)).isEqualTo(4.0)
        assertThat(BoostV5AutoConfig.percentile(v, 50.0)).isWithin(1e-9).of(2.5)
        assertThat(BoostV5AutoConfig.percentile(emptyList(), 90.0)).isEqualTo(0.0)
    }

    @Test fun `rationale explains every setting`() {
        val s = BoostV5AutoConfig.compute(profile())!!
        assertThat(s.rationale).isNotEmpty()
        assertThat(s.rationale.any { it.contains("HypoCaution") }).isTrue()
        assertThat(s.rationale.any { it.contains("Aggression") }).isTrue()
        // Amendment 2026-07-06 (#6): the committedCap rationale is honest about BOTH terms — the
        // TDD/40 floor binds for most cohort users, not just "routine SMB size".
        assertThat(s.rationale.any { it.contains("Committed cap") && it.contains("TDD/40") }).isTrue()
    }

    // ── Application of the suggestion (BoostV5AutoConfigApply): per-key resolution ──
    // These exercise the SAME helper OpenAPSBoostV5Plugin.maybeAutoConfigure uses, so they lock:
    // tuning one V6 knob must not block the others; each knob resolves (applied once, or
    // skipped-because-user-tuned, or held as a TBR suggestion) exactly once; insufficient data
    // leaves knobs unresolved; the cumulative cap is recomputed from the OPERATIVE per-shot caps.

    private val safeTbr = 2.0   // below the raise-guard threshold: raises apply normally

    /** Minimal in-memory stand-in for the plugin's preference + resolution-mark I/O. */
    private class FakeStore(vararg preset: Pair<DoubleKey, Double>) {
        val store = linkedMapOf(*preset)
        val resolved = mutableSetOf<DoubleKey>()
        fun apply(s: BoostV5AutoConfig.V5Suggestion, tbr: Double, sev54: Double = 0.0) = BoostV5AutoConfigApply.applyAutoConfig(
            s,
            tbrBelow70Pct = tbr,
            timeBelow54Pct = sev54,
            isResolved = { it in resolved },
            storedValue = { store[it] },
            put = { k, v -> store[k] = v },
            markResolved = { resolved += it }
        )
    }

    private fun List<BoostV5AutoConfigApply.Resolution>.appliedKeys() =
        filter { it.outcome == BoostV5AutoConfigApply.Outcome.APPLIED }.map { it.key }

    @Test fun `managed knobs cover exactly the auto-configured doubles`() {
        val keys = BoostV5AutoConfigApply.managedDoubleKnobs(BoostV5AutoConfig.compute(profile())!!).map { it.first }
        assertThat(keys).containsExactlyElementsIn(BoostV5AutoConfigApply.managedDoubleKeys)
        assertThat(keys).containsExactly(
            DoubleKey.ApsBoostV5Aggression, DoubleKey.ApsBoostV5HypoCaution,
            DoubleKey.ApsBoostV5ConfirmedCapU, DoubleKey.ApsBoostV5CommittedCapU,
            DoubleKey.ApsBoostCumulativeSmbCap60Min, DoubleKey.ApsBoostMaxIob, DoubleKey.ApsBoostBolus
        )
    }

    @Test fun `with nothing preset, every knob is configured and resolved — including the cumulative cap`() {
        val s = BoostV5AutoConfig.compute(profile())!!
        val f = FakeStore()
        val res = f.apply(s, safeTbr)
        assertThat(res.appliedKeys()).containsExactlyElementsIn(BoostV5AutoConfigApply.managedDoubleKeys)
        assertThat(f.store.keys).containsExactlyElementsIn(BoostV5AutoConfigApply.managedDoubleKeys)
        assertThat(f.resolved).containsExactlyElementsIn(BoostV5AutoConfigApply.managedDoubleKeys)
        // With both per-shot caps applied, the cumulative recompute equals the derivation's value.
        assertThat(f.store[DoubleKey.ApsBoostCumulativeSmbCap60Min]).isEqualTo(s.cumulativeSmbCap60MinU)
    }

    @Test fun `tuning one knob keeps it (resolved-skipped) and still configures all the others`() {
        val s = BoostV5AutoConfig.compute(profile())!!
        val preset = DoubleKey.ApsBoostCumulativeSmbCap60Min   // user tuned the SMB cap (≠ any factory: 2.5 ∉ {1.5, 6, 10})
        val presetValue = 2.5
        val f = FakeStore(preset to presetValue)
        val res = f.apply(s, safeTbr)
        val others = BoostV5AutoConfigApply.managedDoubleKeys.filter { it != preset }
        // tuned knob NOT applied; every other knob IS; tuned knob still RESOLVED (never revisited)
        assertThat(res.appliedKeys()).containsExactlyElementsIn(others)
        assertThat(res.appliedKeys()).doesNotContain(preset)
        assertThat(f.resolved).contains(preset)
        assertThat(res.single { it.key == preset }.outcome).isEqualTo(BoostV5AutoConfigApply.Outcome.KEPT_USER_TUNED)
        assertThat(res.single { it.key == preset }.reason).contains("kept-user-tuned value=2.5")
        // tuned value untouched; all others now written with the suggested value
        assertThat(f.store[preset]).isEqualTo(presetValue)
        assertThat(f.store[DoubleKey.ApsBoostV5ConfirmedCapU]).isEqualTo(s.confirmedCapU)
        assertThat(f.store[DoubleKey.ApsBoostV5CommittedCapU]).isEqualTo(s.committedCapU)
    }

    @Test fun `a knob persisted AT its factory default does not block the suggestion`() {
        // user H's failure mode with the old presence test: committedCap existed in storage at the
        // stock 0.5 (settings import / pref-dialog OK) and was skipped forever. Value == default
        // means nobody objected — the suggestion must still be applied.
        val s = BoostV5AutoConfig.compute(profile())!!
        val key = DoubleKey.ApsBoostV5CommittedCapU
        val f = FakeStore(key to key.defaultValue)             // present, but stock
        val res = f.apply(s, safeTbr)
        assertThat(res.appliedKeys()).contains(key)
        assertThat(f.store[key]).isEqualTo(s.committedCapU)
    }

    // ── Historical factory defaults (2026-07-06 amendment #1) ──
    // Factories changed across build eras: committedCap 0.25→0.5, confirmedCap 1.0→2.5,
    // cumulative 1.5→6.0→10.0 (verified from git history — see BoostV5AutoConfigApply KDoc). A
    // stored OLD factory value must read as at-factory/derivable, or old-build users are frozen
    // at the tightest-ever values (cohort users C/D).

    @Test fun `every historical factory value is recognised as at-factory, off-factory values as tuned`() {
        val committed = DoubleKey.ApsBoostV5CommittedCapU
        val confirmed = DoubleKey.ApsBoostV5ConfirmedCapU
        val cumulative = DoubleKey.ApsBoostCumulativeSmbCap60Min
        // every value each key ever shipped as its default → NOT user-tuned
        listOf(0.25, 0.5).forEach { assertThat(BoostV5AutoConfigApply.isUserTuned(committed, it)).isFalse() }
        listOf(1.0, 2.5).forEach { assertThat(BoostV5AutoConfigApply.isUserTuned(confirmed, it)).isFalse() }
        listOf(1.5, 6.0, 10.0).forEach { assertThat(BoostV5AutoConfigApply.isUserTuned(cumulative, it)).isFalse() }
        // genuinely tuned values still detected
        assertThat(BoostV5AutoConfigApply.isUserTuned(committed, 1.24)).isTrue()
        assertThat(BoostV5AutoConfigApply.isUserTuned(confirmed, 4.0)).isTrue()
        assertThat(BoostV5AutoConfigApply.isUserTuned(cumulative, 2.5)).isTrue()
        // absent value is never "tuned"
        assertThat(BoostV5AutoConfigApply.isUserTuned(committed, null)).isFalse()
    }

    @Test fun `a knob stranded at an OLD era's factory default is still derivable`() {
        // Old-build user: committedCap persisted at the ORIGINAL factory 0.25, confirmedCap at 1.0,
        // cumulative at the 6.0 era. All must be treated as never-touched and re-derived.
        val s = BoostV5AutoConfig.compute(profile())!!
        val f = FakeStore(
            DoubleKey.ApsBoostV5CommittedCapU to 0.25,
            DoubleKey.ApsBoostV5ConfirmedCapU to 1.0,
            DoubleKey.ApsBoostCumulativeSmbCap60Min to 6.0
        )
        val res = f.apply(s, safeTbr)
        assertThat(res.appliedKeys()).containsExactlyElementsIn(BoostV5AutoConfigApply.managedDoubleKeys)
        assertThat(f.store[DoubleKey.ApsBoostV5CommittedCapU]).isEqualTo(s.committedCapU)
        assertThat(f.store[DoubleKey.ApsBoostV5ConfirmedCapU]).isEqualTo(s.confirmedCapU)
    }

    // ── Cumulative cap from RESOLVED values (2026-07-06 amendment #3) ──

    @Test fun `cumulative cap is computed from the OPERATIVE caps, not the derivation's`() {
        // Cohort user E: derivation suggested confirmedCap 4.65 but his operative (user-tuned) cap
        // was 2.0 — the cumulative budget must be sized from what actually applies.
        val s = BoostV5AutoConfig.compute(profile(tdd = 49.6, smb = listOf(0.5, 0.5, 0.5, 0.5, 0.5)))!!
        assertThat(s.committedCapU).isEqualTo(1.24)            // derived, will apply
        val keptConfirmed = 2.0                                 // user-tuned (≠ factories 1.0/2.5)
        val f = FakeStore(DoubleKey.ApsBoostV5ConfirmedCapU to keptConfirmed)
        f.apply(s, safeTbr)
        // cumulative = clamp(2.0 + 2×1.24, 1, 10) = 4.48 → 4.5 — from the KEPT 2.0, not derived 6.0
        assertThat(f.store[DoubleKey.ApsBoostV5ConfirmedCapU]).isEqualTo(keptConfirmed)
        assertThat(f.store[DoubleKey.ApsBoostCumulativeSmbCap60Min]).isEqualTo(4.5)
        assertThat(f.store[DoubleKey.ApsBoostCumulativeSmbCap60Min]).isNotEqualTo(s.cumulativeSmbCap60MinU)
    }

    // ── TBR raise-guard on dose caps (2026-07-06 amendment #5, cohort user B) ──

    @Test fun `dose-cap RAISE with elevated TBR is held as a suggestion, not applied`() {
        val s = BoostV5AutoConfig.compute(profile(tbr70 = 4.3))!!
        assertThat(s.committedCapU).isGreaterThan(DoubleKey.ApsBoostV5CommittedCapU.defaultValue)
        val f = FakeStore()
        val res = f.apply(s, tbr = 4.3)
        val held = res.single { it.key == DoubleKey.ApsBoostV5CommittedCapU }
        assertThat(held.outcome).isEqualTo(BoostV5AutoConfigApply.Outcome.SUGGESTED_NOT_APPLIED_TBR)
        assertThat(held.suggestedValue).isEqualTo(s.committedCapU)   // suggestion recorded for the notification
        assertThat(held.reason).contains("suggested-not-applied (TBR)")
        assertThat(f.store).doesNotContainKey(DoubleKey.ApsBoostV5CommittedCapU)
        assertThat(f.resolved).contains(DoubleKey.ApsBoostV5CommittedCapU)  // resolved: not retried forever
        // The confirmed cap (also a raise: 6.0 > factory 2.5) is held too...
        assertThat(res.single { it.key == DoubleKey.ApsBoostV5ConfirmedCapU }.outcome)
            .isEqualTo(BoostV5AutoConfigApply.Outcome.SUGGESTED_NOT_APPLIED_TBR)
        // ...while non-cap knobs still apply (hypo-protective tightenings must never be blocked).
        assertThat(res.appliedKeys()).contains(DoubleKey.ApsBoostV5Aggression)
        assertThat(res.appliedKeys()).contains(DoubleKey.ApsBoostV5HypoCaution)
        // The cumulative cap TIGHTENS (from factory 10.0 down to the operative-cap budget) → applied.
        assertThat(res.appliedKeys()).contains(DoubleKey.ApsBoostCumulativeSmbCap60Min)
        assertThat(f.store[DoubleKey.ApsBoostCumulativeSmbCap60Min]!!).isLessThan(10.0)
    }

    @Test fun `dose-cap LOWERING applies even with elevated TBR`() {
        // Tightenings are exactly what a TBR-heavy user needs — the guard must never block them.
        // Small-dose user: confirmedCap derives to the 1.5 floor, below the factory 2.5.
        val s = BoostV5AutoConfig.compute(
            profile(tbr70 = 4.3, manual = listOf(0.5, 0.5, 0.5, 0.5), smb = listOf(0.2, 0.2, 0.3))
        )!!
        assertThat(s.confirmedCapU).isEqualTo(1.5)
        val f = FakeStore()
        val res = f.apply(s, tbr = 4.3)
        assertThat(res.appliedKeys()).contains(DoubleKey.ApsBoostV5ConfirmedCapU)
        assertThat(f.store[DoubleKey.ApsBoostV5ConfirmedCapU]).isEqualTo(1.5)
    }

    @Test fun `dose-cap RAISE applies normally when TBR is at target`() {
        val s = BoostV5AutoConfig.compute(profile(tbr70 = 2.0))!!
        assertThat(s.committedCapU).isGreaterThan(DoubleKey.ApsBoostV5CommittedCapU.defaultValue)
        val f = FakeStore()
        val res = f.apply(s, tbr = 2.0)
        assertThat(res.appliedKeys()).contains(DoubleKey.ApsBoostV5CommittedCapU)
        assertThat(f.store[DoubleKey.ApsBoostV5CommittedCapU]).isEqualTo(s.committedCapU)
    }

    // ── <54 severe co-guard on the raise-guard (2026-07-07, user-B pattern) ──
    // TBR<70 alone missed user B: <70 3.83% sat under the 4.0% line while <54 1.01% sat over the
    // 1.0% consensus severe line. A raise must also be held on severe exposure.

    @Test fun `dose-cap RAISE held when below-54 trips even though below-70 is under its line`() {
        val s = BoostV5AutoConfig.compute(profile(tbr70 = 3.8))!!
        assertThat(s.committedCapU).isGreaterThan(DoubleKey.ApsBoostV5CommittedCapU.defaultValue)
        val f = FakeStore()
        val res = f.apply(s, tbr = 3.8, sev54 = 1.1)
        val held = res.single { it.key == DoubleKey.ApsBoostV5CommittedCapU }
        assertThat(held.outcome).isEqualTo(BoostV5AutoConfigApply.Outcome.SUGGESTED_NOT_APPLIED_TBR)
        assertThat(held.reason).contains("<54=1.1%")
        assertThat(f.store).doesNotContainKey(DoubleKey.ApsBoostV5CommittedCapU)
        assertThat(f.resolved).contains(DoubleKey.ApsBoostV5CommittedCapU)
        // boundary: exactly 1.0% is AT the consensus line -> held (guard is >=)
        val f2 = FakeStore()
        val res2 = f2.apply(s, tbr = 3.8, sev54 = BoostV5AutoConfigApply.TBR54_RAISE_GUARD_PCT)
        assertThat(res2.single { it.key == DoubleKey.ApsBoostV5CommittedCapU }.outcome)
            .isEqualTo(BoostV5AutoConfigApply.Outcome.SUGGESTED_NOT_APPLIED_TBR)
    }

    @Test fun `dose-cap RAISE applies when both guards are under their lines`() {
        val s = BoostV5AutoConfig.compute(profile(tbr70 = 3.8))!!
        val f = FakeStore()
        val res = f.apply(s, tbr = 3.8, sev54 = 0.9)
        assertThat(res.appliedKeys()).contains(DoubleKey.ApsBoostV5CommittedCapU)
        assertThat(f.store[DoubleKey.ApsBoostV5CommittedCapU]).isEqualTo(s.committedCapU)
    }

    @Test fun `dose-cap LOWERING applies even with elevated below-54`() {
        // Tightenings are exactly what a severe-hypo-exposed user needs — never blocked.
        val s = BoostV5AutoConfig.compute(
            profile(tbr70 = 3.8, manual = listOf(0.5, 0.5, 0.5, 0.5), smb = listOf(0.2, 0.2, 0.3))
        )!!
        assertThat(s.confirmedCapU).isEqualTo(1.5)   // below factory 2.5 = a lowering
        val f = FakeStore()
        val res = f.apply(s, tbr = 3.8, sev54 = 2.0)
        assertThat(res.appliedKeys()).contains(DoubleKey.ApsBoostV5ConfirmedCapU)
        assertThat(f.store[DoubleKey.ApsBoostV5ConfirmedCapU]).isEqualTo(1.5)
    }

    @Test fun `once applied, a knob is resolved and never re-applied`() {
        val s = BoostV5AutoConfig.compute(profile())!!
        val f = FakeStore()
        f.apply(s, safeTbr)
        // User later sets a knob BACK to something (even the suggestion's own value re-derivation
        // would overwrite differently) — a second run must not touch anything.
        f.store[DoubleKey.ApsBoostV5CommittedCapU] = 0.33
        val rederived = s.copy(committedCapU = 2.0, confirmedCapU = 7.0)   // a different suggestion
        val resAgain = f.apply(rederived, safeTbr)
        assertThat(resAgain).isEmpty()
        assertThat(f.store[DoubleKey.ApsBoostV5CommittedCapU]).isEqualTo(0.33)
    }

    @Test fun `insufficient data resolves nothing so knobs genuinely retry`() {
        // The caller gets no suggestion → applyAutoConfig is never invoked → no knob resolves.
        assertThat(BoostV5AutoConfig.compute(profile(days = 5))).isNull()
        val f = FakeStore()
        assertThat(f.resolved).isEmpty()                        // still all eligible
        // Once data accrues, the SAME store applies everything.
        val res = f.apply(BoostV5AutoConfig.compute(profile())!!, safeTbr)
        assertThat(res.appliedKeys()).containsExactlyElementsIn(BoostV5AutoConfigApply.managedDoubleKeys)
    }

    // ── Versioned re-migration (schema v2 — the promoted-APK-window incident, 2026-07-06) ──
    // The b2c0705e5e build shipped WITHOUT historical-factory awareness: its era-blind isUserTuned
    // resolved knobs stored at OLD factory values (0.25/1.0/6.0) as "kept-user-tuned" — terminally.
    // The b2c0705e5e-era persistence is a bare boolean resolved flag per knob (no outcome detail),
    // so the v2 audit re-runs the NEW isUserTuned on every resolved knob and re-opens the
    // at-any-factory ones.

    /** Runs the schema migration against a [FakeStore] with an explicit persisted version. */
    private class VersionedStore(vararg preset: Pair<DoubleKey, Double>) {
        val f = FakeStore(*preset)
        var version = 0                                        // pre-versioning installs have no stamp
        fun migrate() = BoostV5AutoConfigApply.runSchemaMigrations(
            storedVersion = version,
            keys = BoostV5AutoConfigApply.managedDoubleKeys,
            isResolved = { it in f.resolved },
            storedValue = { f.store[it] },
            clearResolved = { f.resolved -= it },
            setVersion = { version = it }
        )
    }

    @Test fun `re-migration v2 re-opens a knob the era-blind build stranded at an old factory value`() {
        // Stranded path: the promoted APK saw committedCap 0.25 (old-era factory), judged it
        // user-tuned, and persisted the resolved flag. The v2 audit must clear the flag so the
        // normal derivation applies the formula value on the next cycle.
        val key = DoubleKey.ApsBoostV5CommittedCapU
        val v = VersionedStore(key to 0.25)
        v.f.resolved += key                                    // as persisted by the era-blind build
        val cleared = v.migrate()
        assertThat(cleared).containsExactly(key)
        assertThat(v.f.resolved).doesNotContain(key)
        assertThat(v.version).isEqualTo(BoostV5AutoConfigApply.AUTO_CONFIG_SCHEMA_VERSION)
        // Next cycle: the ordinary per-knob path now derives and applies the formula value.
        val s = BoostV5AutoConfig.compute(profile())!!
        val res = v.f.apply(s, safeTbr)
        assertThat(res.appliedKeys()).contains(key)
        assertThat(v.f.store[key]).isEqualTo(s.committedCapU)
    }

    @Test fun `re-migration v2 keeps a genuinely user-tuned knob resolved`() {
        val key = DoubleKey.ApsBoostV5CommittedCapU
        val v = VersionedStore(key to 0.8)                     // 0.8 ∉ {0.25, 0.5} — really tuned
        v.f.resolved += key
        val cleared = v.migrate()
        assertThat(cleared).isEmpty()
        assertThat(v.f.resolved).contains(key)
        assertThat(v.version).isEqualTo(BoostV5AutoConfigApply.AUTO_CONFIG_SCHEMA_VERSION)
        // And the kept value survives the next cycle untouched.
        v.f.apply(BoostV5AutoConfig.compute(profile())!!, safeTbr)
        assertThat(v.f.store[key]).isEqualTo(0.8)
    }

    @Test fun `re-migration v2 is a no-op on a fresh install (still stamps the version)`() {
        val v = VersionedStore()                               // nothing stored, nothing resolved
        val cleared = v.migrate()
        assertThat(cleared).isEmpty()
        assertThat(v.f.resolved).isEmpty()
        assertThat(v.f.store).isEmpty()
        assertThat(v.version).isEqualTo(BoostV5AutoConfigApply.AUTO_CONFIG_SCHEMA_VERSION)
    }

    @Test fun `re-migration runs once — a stamped version is never re-audited`() {
        val key = DoubleKey.ApsBoostV5CommittedCapU
        val v = VersionedStore(key to 0.25)
        v.f.resolved += key
        assertThat(v.migrate()).containsExactly(key)           // first startup: cleared + stamped
        // The knob resolves again at a factory-coincident value (e.g. auto-applied and later reset).
        v.f.resolved += key
        assertThat(v.migrate()).isEmpty()                      // second startup: version 2 → no re-clear
        assertThat(v.f.resolved).contains(key)
    }

    // ── Migration from the legacy global done-flag ──

    @Test fun `legacy-flag migration resolves only knobs off their factory default`() {
        val tuned = DoubleKey.ApsBoostV5ConfirmedCapU           // user/old-run value ≠ any factory (1.0/2.5)
        val stock = DoubleKey.ApsBoostV5CommittedCapU           // persisted AT default 0.5 (user H)
        val oldEra = DoubleKey.ApsBoostCumulativeSmbCap60Min    // persisted at the OLD 6.0 factory era
        val store = mapOf(tuned to 4.0, stock to stock.defaultValue, oldEra to 6.0)  // others absent
        val resolved = mutableSetOf<DoubleKey>()
        val migrated = BoostV5AutoConfigApply.migrateLegacyDoneFlag(
            BoostV5AutoConfigApply.managedDoubleKeys,
            storedValue = { store[it] },
            markResolved = { resolved += it }
        )
        assertThat(migrated).containsExactly(tuned)             // off-every-factory → left alone forever
        assertThat(resolved).containsExactly(tuned)
        // stock, historical-factory and absent keys stay UNRESOLVED → eligible for derivation again
        assertThat(resolved).doesNotContain(stock)
        assertThat(resolved).doesNotContain(oldEra)
    }

    @Test fun `userH regression — flag consumed, keys at defaults, rich history — caps get applied`() {
        // user H: V6-active 06-30, months of history, TDD ~50U; committedCap stuck at factory 0.5
        // although his derived value is 1.24. After migration (nothing resolved because everything
        // is at stock), the next cycle must apply BOTH the committed cap and the cumulative cap.
        val userH = profile(
            tdd = 49.6,                                          // 49.6/40 = 1.24 committed
            smb = listOf(0.5, 0.5, 0.5, 0.5, 0.5),               // p75 clipped at the old 0.5 cap
            manual = listOf(4.0, 4.0, 5.0, 5.0, 5.0, 6.0, 6.0, 6.0, 6.0, 6.0)  // p90 = 6.0 → confirmedCap 6.0
        )
        val s = BoostV5AutoConfig.compute(userH)!!
        assertThat(s.confirmedCapU).isEqualTo(6.0)
        assertThat(s.committedCapU).isEqualTo(1.24)
        // cumulative = clamp(6.0 + 2×1.24, 1.0, 10.0) = 8.48 → 8.5. (2026-07-06 amendment #2:
        // previously the max(5.0, conf) ceiling collapsed this to 6.0 — confirm + ~0 holds.)
        assertThat(s.cumulativeSmbCap60MinU).isEqualTo(8.5)

        // Storage as found in the field: managed knobs present at stock (or absent) after the old run.
        val f = FakeStore(
            DoubleKey.ApsBoostV5CommittedCapU to DoubleKey.ApsBoostV5CommittedCapU.defaultValue,
            DoubleKey.ApsBoostCumulativeSmbCap60Min to DoubleKey.ApsBoostCumulativeSmbCap60Min.defaultValue
        )
        val migrated = BoostV5AutoConfigApply.migrateLegacyDoneFlag(
            BoostV5AutoConfigApply.managedDoubleKeys, storedValue = { f.store[it] }, markResolved = { f.resolved += it }
        )
        assertThat(migrated).isEmpty()                           // nothing off-default → all eligible
        val res = f.apply(s, tbr = 3.0)                          // user H's TBR<70 3.0% < guard 4.0%
        assertThat(res.appliedKeys()).contains(DoubleKey.ApsBoostV5CommittedCapU)
        assertThat(res.appliedKeys()).contains(DoubleKey.ApsBoostCumulativeSmbCap60Min)
        assertThat(f.store[DoubleKey.ApsBoostV5CommittedCapU]).isEqualTo(1.24)
        assertThat(f.store[DoubleKey.ApsBoostCumulativeSmbCap60Min]).isEqualTo(8.5)
        // Invariant: the suggestion never auto-raises Aggression above neutral.
        assertThat(s.aggression).isAtMost(1.0)
    }
}
