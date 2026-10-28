# Pre-registered protocol — Sleep-gate (night mode) isolation A/B

**Status:** PRE-REGISTERED (analysis plan fixed before data collection)
**Registered:** 2026-07-08
**Version:** 1.0
**Applies to:** Boost overnight sleep-gate ("night mode"), `SleepStateDetector` SLEEPING branch.

> Pre-registration discipline: the hypotheses, arms, endpoints, sample size, stopping rules and
> analysis model below are fixed **before** any A/B data is collected. Deviations are recorded in
> the amendment log at the end, dated, with reason. This document is the reference the eventual
> upstream PR cites as its evidence base.

---

## 1. Background & rationale

A cohort comparison (Boost-dosing users vs an oref/Trio reference cohort) found Boost's overnight
(00:00–06:00 local) time-in-range is **+13.3 pp** higher, with both fewer lows (−4.4 pp TBR<70)
and fewer highs (−9.1 pp TAR>180); the daytime difference is ~0. See
`backtesting/scripts/2026-07-residency/COHORT_REGIME_REPORT.md`.

That finding is **observational and confounded**: it compares two different populations and bundles
the sleep-gate with the entire Boost dosing stack. Overnight is fasting/basal-dominated, so several
rival causes could produce the same overnight-specific gap **without any sleep-gate contribution**:

| # | Rival cause | Sleep-gate? |
|---|---|---|
| 1 | Basal/profile tuning quality (curated cohort vs broad reference) — **strongest confound** | no |
| 2 | Dynamic ISF vs static/AutoISF overnight sensitivity handling | no (Boost, not gate) |
| 3 | oref overnight SMB instability (aggressive-dawn → low → rebound) that Boost caps damp | no (Boost, not gate) |
| 4 | Sensor mix / compression lows inflating reference TBR | no (artifact) |
| 5 | Eating patterns bleeding into 00–06 | no |
| 6 | **The sleep gate (night mode)** — hypothesis under test | **yes** |

No observational cut can separate #6 from #1–5 (all are baked into the between-cohort contrast). A
**within-user, night-randomised crossover** holds #1–5 constant (same person → same basal, ISF,
sensor, eating) and varies only the gate. This protocol specifies that experiment.

**Explicit expectation-setting:** this measures the gate's *marginal within-user contribution*, NOT
the whole +13.3 pp. A modest or null gate effect is a valid, informative outcome — it would relocate
the overnight advantage to basal-tuning/DynISF and redirect any upstreaming effort accordingly.

## 2. Hypotheses

- **H1 (primary):** On enrolled Boost-active users, nights with the sleep-gate ON have higher
  overnight TIR than nights with it OFF (within-user).
- **H0 (null):** No within-user difference in overnight TIR between arms.
- **H2 (safety, directional):** OFF nights do not increase overnight TBR<54 beyond the stopping
  threshold (§7).
- **H3 (secondary):** The morning-after (06:00–10:00) window is not worsened by an OFF night
  (rebound-high check).

## 3. Design

Within-user **night-level randomised crossover**. Each night independently randomised ON/OFF; each
participant is their own control, cancelling all fixed per-user factors.

- **Unit of randomisation:** one night per participant.
- **Randomisation:** seeded PRNG keyed on `(participantId, nightDate)`, balanced in blocks of 7
  nights so ON/OFF stay ~even within each week. **Not** odd/even calendar nights (that confounds arm
  with weekday).
- **Night window ("gated window"):** the participant's *detected* sleep span from
  `SleepStateDetector` (preferred); fixed clock fallback 23:00–08:00 local if detection is degraded.
- **Blinding:** participant is not told the per-night assignment (reduces behavioural confound);
  full blinding is impractical (they may infer from dosing). Analysis is on logged arm, not
  perception.

## 4. Population & eligibility

- **Include:** Boost-active users, ≥14 d of stable Boost data, with absolute TBR headroom —
  trailing-14 d **TBR<70 < 3.5 %** AND **TBR<54 < 0.8 %** (the two-test-bar absolute gates).
- **Exclude:** hypo-prone users (fail the above), users without a reliable overnight HR/steps feed
  (the gate can't be evaluated), <14 d data, pregnancy, or any condition where removing an overnight
  protection is contraindicated.
- **Target n:** 6–8 participants (see §6).

## 5. Arms

- **ON (control-with-protection):** current night mode — SLEEPING branch active (dampened overnight
  aggression, no target raise).
- **OFF (intervention / protection-removed):** the SLEEPING branch behaves as AWAKE — overnight
  dosing reverts to the pre-night-mode aggressive path (≈ what the reference cohort does).

**OFF is the riskier arm** (removes a hypo protection). It is not novel-dangerous — it restores prior
Boost behaviour and every absolute safety layer still binds (maxIOB, SMB caps, TBR kill-switches) —
but it is a live dosing change requiring consent and monitoring (§7–§8).

## 6. Sample size & power

Measured night-to-night overnight-TIR SD ≈ **13 pp** (per-user range 7.5–20.8; source: the AAPS
cohort overnight nightly-TIR series, `cohort_regime.py` data). For a night-randomised crossover
(mixed model, user random intercept), the SE of the arm effect ≈ `13 · √(2 / n_nights_per_arm)`.

| Enrolment | Nights/arm (approx) | 80 %-power MDE (overnight TIR) |
|---|---|---|
| 6–8 users × ~4 weeks (~170–220 nights total) | ~14/arm/user | **~5–6 pp** |
| 8+ users × ~6 weeks | ~21/arm/user | **~4 pp** |

A true gate effect below ~4 pp is underpowered here — but a <4 pp marginal effect is itself
decision-useful (gate is not the overnight driver). Minimum run: **4 weeks**.

## 7. Safety & stopping rules (pre-specified)

- All absolute safety unchanged: maxIOB, SMB caps, TBR kill-switches (TBR<70 >4 %, <54 >1 %).
- **Per-participant abort** (revert to gate-ON permanently, drop from A/B) if any of:
  - any single OFF night with overnight **TBR<54 > 2 %**, or
  - a 3-night rolling OFF-arm **TBR<70 > 6 %**, or
  - a participant-reported hypo event they attribute to overnight dosing.
- **Study-level abort** if ≥⅓ of participants hit a per-participant abort.
- OFF arm can only *restore* baseline aggression, never exceed existing caps.
- Informed opt-in consent; participants may withdraw any night.

## 8. Data capture (prerequisite instrumentation)

None of the required fields are currently logged — this instrumentation is a **precondition** and
must ship before enrolment:

- `nightModeArm` — the per-night assignment (ON/OFF), written every cycle in the gated window.
- `sleepState` — the `SleepStateDetector` state (already emitted to devicestatus; must be wired into
  the extractor / DB — currently absent from `boost_decisions`).
- Overnight CGM + dosing already captured; ensure the gated-window rows are identifiable by the
  night key.
- All A/B fields flow to Nightscout devicestatus → the TimescaleDB extractor, so the analysis is
  reproducible from `boost_decisions`.

## 9. Endpoints

- **Primary:** overnight (gated-window) **TIR 70–180**.
- **Secondary:** overnight **TBR<70**, **TBR<54**, **TAR>180**; **morning-after** (06:00–10:00)
  TIR/TAR (rebound check for H3).
- **Exploratory:** overnight CV; time-to-SLEEPING; per-user paired deltas.

## 10. Analysis plan (fixed)

- **Primary model:** linear mixed-effects
  `overnight_TIR ~ arm + weekday + (1 | participant)`; report the `arm` coefficient, 95 % CI, and
  p-value. Effect = the causal within-user gate contribution.
- **Secondary:** same model form for each secondary endpoint.
- **Robustness:** per-participant paired ON−OFF mean differences (non-parametric sign/Wilcoxon
  across participants) as a model-free check.
- **Handling:** nights with <2 h of gated-window CGM excluded; aborted participants analysed up to
  their abort (no post-abort nights).
- **Significance:** primary α = 0.05, two-sided. Secondary endpoints reported with CIs; no
  multiplicity claim beyond the primary.

## 11. Decision rule → upstream PR

- **Gate effect ≥ ~4–6 pp overnight TIR, CI excludes 0, safety clean** → PR-grade evidence for night
  mode *specifically*. Proceed with the two-PR upstream plan (detector PR, then opt-in sleep-gated
  SMB-dampening PR carrying this result).
- **Gate effect small/NS** → the overnight advantage is basal-tuning selection and/or DynISF, not the
  gate. Do **not** upstream night mode on a false premise; redirect to investigating DynISF /
  profile-quality as the actual overnight lever.

## 12. Ethics

Live dosing experiment on people: written informed consent, opt-in, explicit abort criteria,
monitoring. The OFF arm removes an overnight hypo protection — this is not a silent change and is
treated as such.

## Amendment log

_(date — change — reason. None yet.)_
