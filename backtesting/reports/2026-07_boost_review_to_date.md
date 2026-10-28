# Boost — review to date (2026-07-29)

A status review of the fork: what the controller is, how the cohort is actually doing,
what the evidence supports, and where the gaps are. Every number here was measured in
this session against the local TimescaleDB and the two branch trees; nothing is cited
from prior notes.

**Data currency.** `boost_cgm` and `boost_decisions` run to 2026-07-27; t=now is
2026-07-29. The DB is two days short of the protocol's "refresh to t=now" and was not
refreshed for this review. Nothing below turns on those two days, but the cohort table
should be re-run after a refresh before it is quoted anywhere external.

**Cohort.** Nine users (A, B, C, D, E, F, G, H, tim). Coverage from 2025-08-01 for the
five long-running users; C, G, H join between December and May. E's feed stops
2026-07-19.

---

## 1. Where the cohort is now

Per-user CGM outcomes, 30 days to 2026-07-27. TIR = 70-180, TING = 63-140, all mg/dL.

| user | n | TIR | TING | TBR<70 | TBR<54 | TAR>180 | mean | CV |
|---|---|---|---|---|---|---|---|---|
| A | 8962 | 79.9 | 58.2 | 1.55 | 0.23 | 18.6 | 139 | 32.4 |
| B | 8724 | 77.8 | 63.4 | **3.91** | **1.10** | 18.3 | 136 | 41.5 |
| C | 9005 | 90.1 | 76.5 | **5.75** | **1.22** | 4.1 | 116 | 28.9 |
| D | 8800 | 91.9 | 89.0 | **6.53** | 0.91 | 1.6 | 105 | 24.8 |
| E | 6320 | 98.4 | 88.6 | 0.97 | 0.02 | 0.6 | 116 | 18.1 |
| F | 8811 | 86.6 | 65.1 | 1.93 | 0.14 | 11.4 | 134 | 28.0 |
| G | 8359 | 87.3 | 71.5 | **3.91** | 0.84 | 8.8 | 125 | 34.7 |
| H | 8787 | 93.1 | 73.6 | 1.39 | 0.03 | 5.5 | 126 | 24.3 |
| tim | 8564 | 82.0 | 67.9 | **5.55** | **1.34** | 12.4 | 126 | 38.6 |

Over 90 days the picture is the same, with D worse: TBR<70 9.22, TBR<54 1.70.

**Finding 1 (SOLID).** Four of nine users sit above at least one of the consensus
absolutes that gate every shipped change in this project (TBR<70 ≤4%, TBR<54 ≤1%).
C and tim breach both; D breaches <70 on 30 days and both on 90 days; B breaches <54.
G sits on the <70 line at 3.91.

This is partly therapy-target driven rather than a controller defect — D runs a mean of
102-105 mg/dL, and low means buy low TBR-free time by construction. But it is the same
threshold used as a kill-switch elsewhere in the programme, and it is being crossed by a
third of the cohort in the live system. The hypoCaution-by-TBR mechanism in auto-config
already exists and is validated for exactly this; the question is whether it has been
re-derived on current data for these users.

The high-side picture is unchanged from the segmentation work: A, B and F carry the
TAR (11-19% >180) with TING in the 58-65 range, i.e. the residual problem for the
well-controlled users is time above 140, not time below 70.

---

## 2. Did the V5/V6 migration change outcomes?

`boostv5_active` is a clean era flag — verified at ~100% of cycles once a user migrates,
dipping only where the loop was off. Seven users migrated between 2026-06-26 and
2026-07-09 with ≥14 days on each side. D migrated 2026-07-27 (excluded, no post-window).
G never migrated, so G runs as a never-treated control over the same calendar dates.

Method: within-user, equal-length pre and post windows, day-level bootstrap
(2000 draws, whole days resampled — per-point CIs would be far too narrow given
within-day autocorrelation). Script `backtesting/scripts/2026-07-boost-review/era_within_user.py`.

Post minus pre, percentage points [95% CI]:

| user | TIR Δ | TING Δ | TBR<70 Δ | TBR<54 Δ |
|---|---|---|---|---|
| A | −2.84 [−6.95, +1.34] | −4.81 [−9.77, +0.15] | −0.08 [−1.51, +1.20] | −0.16 [−0.57, +0.11] |
| B | −3.66 [−9.05, +1.51] | +0.54 [−6.08, +6.94] | +1.15 [−0.84, +3.36] | +0.57 [−0.30, +1.58] |
| C | −1.71 [−6.52, +3.75] | +1.50 [−5.80, +9.31] | **+3.73 [+0.91, +6.71]** | +0.74 [−0.17, +1.75] |
| E | +0.24 [−1.35, +1.88] | +2.08 [−3.38, +8.02] | −0.08 [−1.37, +1.20] | +0.02 [+0.00, +0.06] |
| F | +3.06 [−0.66, +6.71] | +0.77 [−3.58, +5.33] | **−1.47 [−2.79, −0.18]** | **−0.29 [−0.53, −0.06]** |
| H | −2.22 [−5.73, +1.06] | **−6.60 [−12.48, −0.52]** | +0.27 [−1.13, +1.75] | −0.19 [−0.59, +0.05] |
| tim | −1.54 [−6.15, +3.18] | +0.00 [−5.85, +5.90] | +0.05 [−2.20, +2.40] | −0.45 [−1.82, +1.00] |
| **G (control)** | −1.17 [−7.09, +4.81] | −2.71 [−8.29, +3.72] | −2.06 [−4.35, +0.15] | −0.41 [−1.27, +0.39] |

**Finding 2 (SOLID as a null; underpowered for small effects).** The V1→V5/V6 migration
is outcome-neutral in this cohort. Every user's TIR change overlaps zero, and the mean
migrated TIR change (−1.24 pp) is indistinguishable from the never-migrated control's
(−1.17 pp) — whatever moved TIR over July moved it for the user who did not migrate too.

Both arms are Boost: V1 is a Boost dosing generation, not oref. So this is
Boost-V1 versus Boost-V5/V6, not Boost versus a reference controller.

Three moves are distinguishable from zero, and they do not point one way:

- C's TBR<70 rose 3.73 pp [+0.91, +6.71] — C is now one of the floor breaches above.
- F improved on both hypo measures, −1.47 pp [−2.79, −0.18] and −0.29 pp [−0.53, −0.06].
- H's TING fell 6.60 pp [−12.48, −0.52]. H is the user whose loop went offline twice on
  the confirm-crash in this window, so the H number is contaminated by the incident and
  its aftermath rather than being a clean read on the engine.

E's TBR<54 "+0.02 [+0.00, +0.06]" is degenerate — both arms are ~0.

**Power.** TIR intervals are roughly ±5 pp on 18-31 days per arm. An effect smaller than
about 5 pp is simply invisible at this n. The honest statement is "no detectable
difference", not "no difference". This independently reproduces the earlier harness
result that v4.1.5 and V5/V6 are indistinguishable across outcomes.

---

## 3. What is instrumented, and on whose device

Rows since 2026-06-01 with each field populated:

| user | accelMeal | antBackout | V7 | Twin | mlHypoRisk | sleep | HR | steps |
|---|---|---|---|---|---|---|---|---|
| A | 0 | 0 | 0 | 0 | 9834 | 9659 | 13494 | 20514 |
| B | 0 | 0 | 0 | 0 | 11973 | 9860 | 266 | 20246 |
| C | 0 | 0 | 0 | 0 | 8929 | 11379 | 11627 | 23746 |
| D | 0 | 0 | 0 | 0 | 8897 | 9635 | 6067 | 20586 |
| E | 0 | 0 | 0 | 0 | 8935 | 6069 | 6356 | 16251 |
| F | 0 | 0 | 0 | 0 | 12369 | 11524 | 15993 | 24372 |
| G | 0 | 0 | 0 | 0 | 13012 | 0 | 0 | 0 |
| H | 0 | 0 | 0 | 0 | 4791 | 9800 | 6301 | 20074 |
| tim | 262 | 2566 | 5399 | 3325 | 12253 | 10884 | 16438 | 23537 |

**Finding 3 (SOLID).** Every experimental shadow layer — the V7 substrate, the Twin
forecaster, the acceleration meal detector, the anticipation back-out — logs on one
device only. Eight of nine users contribute nothing to any of them.

This is the single biggest structural constraint on the programme right now. It means
no V7 conclusion can be cross-user, the Twin's live behaviour is n=1, and the
anticipation shadow (shipped to dev on 2026-07-25) will produce a single-user readout.
Given that the project's own methodology rule is GroupKFold with the user as the group,
the shadow pipeline is currently incapable of meeting the evidence bar the analysis side
insists on.

Two secondary sensing gaps: G has no sleep, HR or steps at all, so every exercise and
overnight protection is inert for G; B has essentially no HR (266 rows), so B's activity
classifier is running on steps alone.

---

## 4. Branch and code state

`dev` and `Boost-V6-experimental` are byte-identical in code — the shipping line is
consistent, which is what the workflow intends.

`Boost-V7-shadow` carries ~2500 lines dev does not. Most is expected and correctly
shadow-only: the V7 residual tracker, sizer and shadow seam; the Twin model, EnKF,
withdrawal and back-out shadows; the TING planner; their tests.

Two differences are **not** shadow — they are live-path fixes that exist, are tested, and
have not reached the shipping line.

**4a. UKF compression gate hardening** (`UnscentedKalmanFilterPlugin.kt`, 2026-07-16).
On V7-shadow the gate excludes negative basal IOB from the total and latches the
consecutive-compression counter while the pattern persists. dev has neither. The
consequences on dev, per the fix's own rationale:

- Negative temp-basal IOB (the loop zero-temping through a genuine descent) shrinks the
  IOB total, so the compression gate is *most* armed exactly when the loop is already
  fighting a real insulin-driven low — damping the very drop it should be following.
- Resetting the counter on a cap-trip lets an ongoing low re-arm for another burst every
  cycle, defeating the ~15-minute bound the cap exists to enforce.

**4b. Sleep detector merge and PRE_SLEEP escape** (`SleepStateDetector.kt`). V7-shadow
folds the lie-in into the state machine (live-wired: `sleepInWindowMin = sleepInHours * 60`)
and adds a PRE_SLEEP→AWAKE release on sustained step activity, ungated by clock or
drought. dev retains only the older standalone `StepFeed.sleepInActive` backstop. The
escape closes the "05:00, user demonstrably up, BG rising, still stuck in PRE_SLEEP"
trap, which suppresses dosing. dev's failsafe covers part but not all of this.

**Finding 4 (SOLID).** Two safety-relevant live-path fixes are sitting only on the
shadow branch. Neither is a research item; both are already written and tested.

---

## 5. What the evidence supports

Synthesised from `RELATIONSHIPS_REGISTER.md`, which is current and well maintained.

**Shipped on real evidence.** The overnight boostActive night-gate (~47% of over-V1
amplifications suppressed, all at night). The post-rescue meal-state cap (27% of removed
insulin sat pre-low). The composed post-rescue rebound guard (34% [32,37]). The
committedCap OBSERVING→CONFIRMED gate (~41% block). Per-user auto-config with its five
amendments. The composed brake — directionally right, and the register is appropriately
careful that the "90%" is 13% outcome-proven plus 76% correct-by-assumption. The v4 UKF.
The HR-exercise safety fix. The primer confirm-net, which only ever removes insulin.

**Repeatedly refuted, and worth not revisiting.** Online knob tuning lost to static
per-user auto-config in four separate experiments, both directions, caps and sliders.
Adding insulin into a high-IOB tail was rejected three separate ways (RECOVERING SMB,
re-engage, blanket committedCap raise). Insulin-efficacy detection from current telemetry
is at chance. The Twin is a descent sensor, not a controller or an MPC model. Cross-user
meal anticipation is at chance; only per-user exercise anticipation carries signal.

**Open and unproven.** The claim that Boost's advantage is causally overnight rests on a
regime split; the pre-registered within-user A/B is written and has never been run.
Exercise-anticipation benefit is detection-validated only. The Design 9 activity
BG-rising override was believed shipped and has never been coded in any branch — the
activity target is still unguarded.

---

## 6. Reading

Four months of work has produced a well-documented evidence base, a disciplined register,
and a controller whose individual guards are each defensible. What the measurement does
not show is an outcome gain from the flagship V5/V6 migration, and the never-treated
control says the July drift is calendar, not engine.

That is not a failure of the guards — several of them demonstrably remove insulin that
sat before a low. It is what the identification constraint has been saying all along:
with no counterfactual, the programme can price individual levers well and cannot
demonstrate an aggregate effect at this cohort size. The residual problems the data
actually shows are (a) a subset of users above the hypo floors, and (b) time above 140
for the well-controlled users — and the post-meal-exercise mechanism work already
established that the exercise half of (b) is a carbohydrate-counterweight problem the
loop cannot solve with insulin.

The marginal new dosing lever is not where the remaining loss is.

---

## 7. Recommended next actions, ranked

1. **Propagate 4a and 4b to experimental/dev, or explicitly retire them.** Two tested
   safety-relevant fixes on the wrong branch is the cheapest correction available and the
   only item here with a live-risk argument behind it.
2. **Re-derive auto-config for the four floor-breaching users on current data**, C first —
   C's TBR<70 rose 3.73 pp [+0.91, +6.71] across the migration and is now 5.75%. The
   hypoCaution-by-TBR mechanism is already built and validated for this.
3. **Get shadow instrumentation onto more than one device.** Until then V7, the Twin and
   the anticipation shadow cannot be evaluated to the standard the project applies to
   everything else, and further building on them accumulates unvalidatable work.
4. **Run the pre-registered night-mode A/B.** It is the one causal test behind the
   overnight story and it has been written and unrun since 2026-07-08.
5. **Hold new dosing levers** until 1-3 are done. The measurement does not support
   another lever being the constraint.

Confidence tiers: findings 1-4 are SOLID (direct measurement this session, CI-backed
where an effect size is claimed). Section 6 is interpretation. The recommendations in 7
are judgement, not measurement.
