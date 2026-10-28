# Pre-registered protocol — post-rescue tight-ramp within-user crossover

**Status:** PRE-REGISTERED (analysis plan fixed before any trial data is collected)
**Registered:** 2026-08-03
**Version:** 1.1  (amended 2026-08-03, before any data collection — see §10)
**Applies to:** the composed post-rescue rebound guard, `DetermineBasalBoost.postRescueReboundScale`
and its call site in the SMB block (shipped `51e7663a36`, 2026-07-23).

> Pre-registration discipline: hypotheses, arms, endpoints, sample size, stopping rules and the
> analysis model below are fixed **before** data collection. Deviations go in the amendment log at
> the end, dated, with a reason.

---

## 1. Background

The shipped guard scales the final SMB inside a post-rescue window as a function of BG alone:

```
bg < 120         -> 0.30
120 <= bg < 170  -> 0.30 + 0.70 * (bg - 120) / 50     (linear 0.30 -> 1.00)
bg >= 170        -> the guard block does not run at all
```

A live double-crash (tim, 2026-08-02) prompted the question of whether that ramp opens too fast:
BG ran 116 → 143 → 180 in fifteen minutes, the scale went 30% → 62% → guard-off, 3.15 U was
delivered inside the window, and BG was 44.6 mg/dL two hours later.

**The cohort study says the premise is wrong** (`backtesting/scripts/2026-08-postrescue-ramp/`,
418 windows, 8 users). BG reaches 120 a median 46 minutes after the window opens and only **5% of
windows reach 170 at all** — the guard sits at its 0.30 floor for most of a typical window, and the
2026-08-02 episode is in the fast-rebound tail rather than the norm. All three candidate ramps are
**UNPROVEN**: every cluster-bootstrap CI over users overlaps zero.

| policy | U removed | removed insulin's pre-low share vs the user's own baseline |
|---|---|---|
| flat 0.30 whole window | 64.4 (11%) | −0.015 [−0.144, +0.137] |
| cap ramp at 0.60 | 18.3 (3.2%) | −0.005 [−0.175, +0.207] |
| extend ramp to 220 | 29.1 (5.0%) | −0.057 [−0.144, +0.036] |

Two signals survive as *hypothesis-generating* and motivate a trial rather than a ship:

1. The `>= 170` band, where the guard is absent rather than relaxed, carries the worst pricing
   (pre-low share 0.50 vs 0.19 baseline pooled) — but on 3.6% of window insulin, 4 users, per-user
   mean +0.159 [−0.218, +0.571].
2. Targeting is **heterogeneous**: under cap-at-0.60 only two users are favourable (A +0.64,
   tim +0.22); B, C, D, E, F and H are all negative. A cohort-wide change would remove six users'
   insulin no better than at random.

This trial therefore tests **one arm, in one user**. A — the strongest observational signal of the
eight — is excluded by participant decision (§4, amendment 1.1), so the trial is a single-subject
crossover on tim alone.

## 2. The intervention

On a treatment day the guard runs across the **whole** post-rescue window with the scale capped:

```
scale = min(postRescueReboundScale(bg), 0.60)        // and the bg < 170 gate is not applied
```

Control days run the shipped guard byte-for-byte.

**Safety property that makes a live trial acceptable:** the treatment arm is a *cap*. It can only
lower the scale, so a treatment cycle **never delivers more insulin than the same cycle would
today**, at any BG. There is no arm in which the participant is exposed to more insulin than the
current shipped behaviour. Unit-tested over BG 40–400 in `PostRescueTightRampTrialTest`.

## 3. Design

Within-user **day-level randomised crossover**; each participant is their own control.

- **Unit of randomisation:** one local calendar day.
- **Assignment:** `DetermineBasalBoost.tightRampArm(seed, dayIndex)` — a pure function of a
  once-generated per-install UUID seed (`StringKey.ApsBoostTrialSeed`) and the local day index.
  Deterministic and re-derivable offline from the seed alone, so the analysis never has to trust a
  logged flag.
- **Balance:** 7-day blocks, 4 treatment days in even blocks and 3 in odd, so arms stay even over
  any fortnight. Positions inside a block are shuffled per block, so **arm is never confounded with
  weekday** (the failure mode called out in the night-mode pre-registration).
- **Unit of analysis:** the post-rescue *episode*, assigned the arm of the day it opened. An episode
  spanning midnight keeps its opening day's arm.
- **Blinding:** none. The participant is the developer and will see the setting; the analysis is on
  the derived arm, not on perception.

## 4. Population

**Single participant: tim. n = 1 by design** (amendment 1.1, before any data collection).

- **Enrol:** tim only. Enrolment is a deliberate act
  (`BooleanKey.ApsBoostPostRescueTightRampTrial`, default OFF, *not* auto-config managed).
- **Exclude:** every other cohort user, including **A**, whose observational targeting under
  cap-at-0.60 was the most favourable of the eight (+0.64). A is excluded by participant decision,
  not by evidence — see the amendment log. B, C, D, E, F and H remain excluded on evidence: their
  per-user deltas are negative, so enrolling them would be removing insulin at random.
- No expansion path. If the trial is ever widened, that is a new registration, not an amendment.

**Consequence to state plainly:** with n = 1 this is a single-subject crossover. Nothing it produces
generalises to the cohort — it can support a decision about tim's own configuration and nothing
more. The heterogeneity in §1 is the reason that limitation is acceptable rather than fatal: a
cohort-wide answer was never the goal.

## 5. Endpoints

**Primary (safety-efficacy, episode level):** proportion of post-rescue episodes followed by a
*second* low (<70 mg/dL) within 4 h of the episode opening, treatment vs control.

**Secondary:**
1. Insulin delivered inside the window (U per episode) — the mechanical check that the cap does what
   the arithmetic says.
2. Peak BG in the 4 h after the episode opens (the rebound-high cost of removing insulin).
3. Time <54 mg/dL in the 6 h after the episode opens.
4. TING (3.5–7.8 mmol/L) over the 6 h after the episode opens.

**Mechanism check (not an endpoint):** share of treatment-day window cycles where the cap actually
bound (BG > 141.4, the crossover) — if this is near zero the trial is not exercising the arm.

## 6. Sample size, and an honest power statement

tim runs ≈1 post-rescue episode/day (89 episodes over the V6 era). Over 8 weeks that is ≈56
episodes, ≈28 per arm.

**The trial is underpowered for the primary endpoint.** At a control second-low rate around 25%,
28 episodes per arm detects roughly a 30 pp absolute difference at 80% power — far larger than any
plausible effect. This is stated up front rather than discovered later.

What the trial *is* adequately powered for:
- Secondary 1 (insulin removed) is near-deterministic and will be precise within two weeks.
- Safety surveillance against the stopping rules, which is the main purpose of running it live.
- Accumulating paired episodes toward a longer-run single-subject answer if the trial is extended
  beyond 8 weeks. There is no pooling route — n = 1 is fixed (§4).

The primary endpoint is therefore reported with its CI and will almost certainly be **unproven**
either way at 8 weeks. That is an acceptable outcome: the decision this trial informs is whether the
mechanism behaves in the field as the arithmetic predicts, not whether it improves control.

## 7. Stopping rules

Checked weekly on trailing-14-day data. Any hit stops the trial and reverts to shipped behaviour.

1. **Absolute floors** (consensus, can only tighten): TBR<70 > 4% or time<54 > 1% on trailing 14 d.
2. **Arm-attributable harm:** treatment-day TBR<54 exceeds control-day TBR<54 by more than 0.5 pp
   over ≥3 weeks.
3. **Rebound cost:** treatment-day mean peak BG in the 4 h post-episode exceeds control by >30
   mg/dL over ≥3 weeks.
4. **Participant call:** the participant stops it for any reason, recorded without justification.

Note stopping rule 1 is about the participant's overall control, not about the arm — it fires
regardless of attribution, because the floors are absolute.

## 8. Analysis

- Episode-level, single participant; arm as the only fixed effect. No clustering term is needed
  or possible at n = 1.
- Primary: difference in proportions with a bootstrap 95% CI (5000 draws, resampling episodes).
  Verdict stated explicitly as distinguishable / **unproven**. Note the resampling unit is the
  episode, so the CI describes within-tim sampling variation only and carries no cross-user
  generalisation.
- Secondaries: same bootstrap; no multiplicity correction, and all secondaries are labelled
  exploratory because of §6.
- Arm is **re-derived offline** from `ApsBoostTrialSeed` + date, and cross-checked against the
  `prTrial=` reason tag. A mismatch invalidates the affected days rather than being reconciled.
- Pre-specified subgroup: none. Any subgroup that appears goes in the amendment log first.

## 9. Telemetry

Every cycle appends `prTrial=<enrolled 0|1>,<control|tight>,<cap>;` to the reason, independent of
whether the guard fired, so exposure is countable on days the guard never engaged. The existing
`Post-rescue rebound scale …%: SMB x → y;` line continues to carry the applied scale, with a
`[trial:tight]` marker in the console line on treatment cycles.

## 10. Amendment log

| date | change | reason |
|---|---|---|
| 2026-08-03 | v1.1 — **A excluded entirely**; trial is single-subject (tim, n = 1). Staged-enrolment clause and pooled-analysis route removed; analysis model simplified to a single-participant episode bootstrap. | Participant decision. Recorded **before any data was collected** — the build had not been flashed and no trial cycle had run — so this changes the registered plan rather than revising a design already exposed to data. It narrows scope and drops the only route to a pooled result; arms, endpoints, stopping rules and randomisation are untouched. |
