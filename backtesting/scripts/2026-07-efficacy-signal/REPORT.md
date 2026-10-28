# Is there a true insulin-efficacy signal in our telemetry? (2026-07-27)

## Why this exists

The fully-closed-loop review asserted, untested, that no efficacy signal exists — "some way
to know that delivered insulin is or is not working." That was an assertion, not a
measurement, and the assertion is exactly the failure our method rules guard against. This
investigation measures it.

## The question, stated so it can't be circular

"BG is still high, so insulin isn't working" is **not** an efficacy signal — it is the glucose
trajectory, which prior signal-digging already showed is all the loop-visible signal. A *true*
efficacy signal must add information **beyond the trajectory and beyond the dose already
given**: at two stuck-high cycles that look identical on BG / delta / acceleration and carry
the same insulin, it must distinguish

- **"insulin hasn't acted yet but will"** → the high resolves, or over-corrects into a
  **rebound CRASH** once masking carbs finish; from
- **"insulin isn't working"** → the high **STALLS** (resistance / not-enough).

Only the *forward outcome* separates these, so we predict the outcome out-of-sample rather
than trying to label efficacy at the moment.

## Design

- **Population:** stuck-high regime — BG > 150 mg/dL, IOB > 1 U, no carbs announced.
  Anchored on **regime entries** (first cycle of a run; 1,717 independent-ish episodes across
  nine users) for the models, and all cycles (up to 36k) for single-feature reads.
- **Labels:** `CRASH` = BG < 70 within 3 h (base rate 16%); `STALL` = never < 140 within 2 h
  (base rate 32%).
- **Feature sets:** `BASE` (trajectory) = bg, delta, accel, curvature. `+EFFICACY` = oref
  deviation, IOB-activity, IOB, BGI, recent-SMB volume (60 min), post-rescue flag, IOB/TDD;
  and (one user) the **Twin's inferred glucose-appearance rate Ra** — the one *dose-independent*
  mechanism candidate, which could in principle separate carbs-masking from resistance.
- **Test:** GroupKFold by user (cross-user generalisation, no leakage). AUC(BASE) vs
  AUC(BASE+EFFICACY), computed with **both** a gradient-boosted model and a **logistic** model —
  the linear model is the overfit control in a near-chance regime. Per-user z-scoring removes
  mmol/mg-dL and U200 unit differences.

## Results

**Nothing beats the trajectory for the crash.**

| Label | GBM base → +efficacy | Logistic base → +efficacy |
|---|---|---|
| CRASH | 0.466 → 0.518 | **0.453 → 0.500** |
| STALL | 0.580 → 0.592 | 0.561 → 0.592 |

The gradient-boosted model showed a small crash increment (+0.052); the **logistic model lands
on exactly 0.500 — chance.** The GBM "signal" was overfitting weak interactions in a
near-chance regime; a linear model finds none. For the stall there is a small increment even
with the linear model (0.561 → 0.592), but it is weak in absolute terms and — see below —
carried entirely by dose-magnitude proxies.

**The only features that flicker are measures of *how much* insulin, not *whether it works*.**
Cycle-level single-feature AUCs vs crash (n up to 36k):

    iob_activity 0.569   iob 0.562   recent-SMB(60m) 0.540   iob/tdd 0.534
    delta 0.449   deviation 0.474   accel 0.476   bgi 0.483

Everything above chance is monotone in insulin-on-board — "more insulin → more likely to
overshoot low," which is mechanically obvious and already encoded by IOB-based safety. None of
it says whether the insulin is *acting*. Deviation — the loop's own model residual, the most
plausible efficacy proxy — is **0.474, below chance.** And recent-SMB stacking, a natural crash
driver, is flat across tertiles: **15% / 19% / 17%** crash rate low→high.

**The dose-independent mechanism candidate does not discriminate — but is badly under-powered.**
The Twin's inferred glucose-appearance Ra — the one feature that could separate "carbs masking
working insulin" from "genuine resistance" independent of dose — shows **AUC 0.473; high-Ra vs
low-Ra crash rate 28% vs 28%** (n = 460 cycles). The n looks adequate but is not: the Twin has
only existed since 2026-07-18, so those 460 cycles collapse to just **~30 independent stuck-high
episodes**. (The earlier "12% coverage" figure was a window artifact — over the Twin's own era Ra
covers **88–94% of stuck-highs**, and Ra is never the null field when the Twin tag is present.
The Twin does not abstain; it is simply young.) So Ra is neither confirmed nor cleanly refuted —
it is untestable at episode level until more data accrues (see the pre-registered re-run,
`RERUN_PROTOCOL.md`).

## Verdict

**A true efficacy signal is not present in our telemetry.** Out-of-sample, cohort-wide, robust
across two model classes and two outcome definitions, nothing distinguishes working from
not-working insulin beyond the glucose trajectory and the size of the dose already given. The
nearest thing our data offers is insulin-on-board magnitude — which is not efficacy.

**Confidence: SOLID for the negative on the crash** (robust to model class, replicated across
single-feature and multivariate views, cohort-wide, no Twin dependence); **PROVISIONAL on the
weak stall increment**, which is dose-magnitude rather than efficacy and weak in any case. The
Twin-Ra strand is **INCONCLUSIVE, not refuted** — ~30 independent episodes is too few to decide,
and a pre-registered re-run is scheduled for when the Twin era reaches adequate power (~1 Sep 2026).

## What this means

1. **Do not build an efficacy detector from current telemetry — there is nothing to detect.**
   This closes a rabbit hole before it opens.
2. The weak crash context our guards already key on (post-rescue window, cumulative-SMB cap,
   the composed rebound guard) is **not beaten** by any richer efficacy feature — validates
   keeping them as they are rather than seeking a cleverer read.
3. The efficacy blind spot is a **sensing problem, not a modelling one.** It is not hiding in
   the data we have; closing it needs new instrumentation — a true insulin-action or
   absorption signal — exactly as the review's deeper thesis argued. This *strengthens* that
   thesis, now with evidence rather than assertion.

## Limits and where a signal could still hide

- We tested prediction of the forward outcome from existing observables. A signal could exist
  that we simply lack the instrument for (interstitial insulin, absorption-site data, a
  tracer). The negative is "not in our telemetry," not "impossible."
- The Twin-Ra test is under-powered (the Twin is ~10 days old → ~30 independent episodes), not
  under-covered (Ra populates 88–94% of stuck-highs in-era). No code change helps; it is a
  data-accrual wait. Pre-registered confirmatory re-run in `RERUN_PROTOCOL.md`.
- Longer horizons or alternative labels were not exhausted; the negative is consistent across
  the two we tested.

*Reproduce: `efficacy_signal_probe.py` (DB refreshed to t=now). Nine users, 60-day window,
1,717 stuck-high regime entries.*
