# KAIROS Twin — the off-policy calibration test: is the Twin a controller model or only a sensor?

*2026-07-18. Script: `twin_offpolicy.py` (+ the calibration fix in `twin_calibrate.py`). The
make-or-break test for KAIROS-as-a-controller. Aggregates only; personal traces kept in scratchpad.*

## Why this test is the pivot

The Twin is validated as a **forecaster**: it predicts BG under the insulin that was *actually
delivered* (`KAIROS_TWIN.md`). A model-predictive controller (the "dose the calibrated forecast
cone" dream) would instead query it **counterfactually** — "what BG if I dose a sequence the real
loop did *not* give?" — which pushes the model off the delivered-insulin manifold. The whole
project lives under one constraint (no glucodynamic simulator ⇒ policy is unvalidatable). A
validated Twin *conditionally* dissolves that wall — but only inside a trust region. This test
measures the trust region, with two legs that use **only real data and real outcomes**.

Before running it, the 30-min forecast band was re-calibrated (`twin_calibrate.py`): the baseline
was under-dispersed (30-min 90%-band coverage 77%, tails 10/13 vs 5/5). Fix = additive EnKF
**covariance inflation** at h=0 + **Poisson positive-Ra meal impulses** (right-skewed upper band) +
an **observed-CGM measurement term**, with the **median** as the point forecast. Held-out result:
30-min coverage **77→85%**, 60-min **86→91%**, RMSE unchanged (33.8 / 46.1). Mirrored into
`TwinEnkf.kt`. This also removes the on-device `lo30`/`floorbreach` over-fire (the real cause was
the old mean-point, un-inflated band — not "warm X", see Leg B).

## Leg A — natural experiment: calibration vs distance from the modal policy

Delivered insulin already varies cycle-to-cycle for reasons only partly explained by state. Regress
horizon insulin on state (BG, trend, an IOB proxy); the residual ≈ exogenous policy variation. Bin
test forecasts by the **signed** residual and measure 90%-band coverage + RMSE per bin. The
under-dosed bins are the direction **idea-4 withdrawal** explores; the over-dosed bins are the
direction **dose-more MPC** explores.

| 30-min bin | dev (U) | n | cov% | below/above | RMSE | quiet-only cov% |
|---|---|---|---|---|---|---|
| under-- | −0.47 | 905 | 78 | 21 / 1 | 37.0 | 82 |
| under-  | −0.26 | 904 | 95 | 5 / 1 | 22.1 | 96 |
| **modal** | −0.16 | 905 | **95** | 4 / 1 | 21.1 | 95 |
| over-   | −0.02 | 904 | 90 | 6 / 4 | 29.0 | 91 |
| over--  | +0.90 | 905 | **68** | 3 / 29 | 51.0 | 71 |

(60-min is the same shape, milder: modal 96%, over-- 84%.)

**Read.** Calibration is strong near the modal policy (90–96%) and **degrades in both off-policy
tails, worst in the dose-more tail** (over-- coverage 68%, with 29% of outcomes *above* the band).
That worst tail is partly meal-confounded — you dose big precisely when a meal is rising — and the
quiet-only column confirms it (82–96% everywhere but the extreme tails). So the trust region is
real and bounded: trustworthy for modest deviations, degrading as you push off-policy.

## Leg B — perturbation: does dosing move the forecast, and does uncertainty self-limit?

At quiet mid/high test cycles, add a **bolus at t=0** (the lever a controller actually pulls) and
forecast where it acts (60 / 90 min); also model **withdrawal** as a zero-temp over the horizon.

| horizon | ΔU | Δ point (mg/dL) | Δ per U | band-width ratio |
|---|---|---|---|---|
| 60 min | +1 / +2 / +3 | −0.4 / −0.7 / −1.1 | **−0.4** | 1.00 |
| 90 min | +1 / +2 / +3 | −0.7 / −1.4 / −2.1 | **−0.7** | 0.99 |

**Two findings, both disqualifying for MPC as-is:**

1. **The insulin response is ~5–10× too weak.** 1 U moves the 60-min forecast by 0.4 mg/dL. For a
   U200 user that should be many mg/dL. And the band does **not** widen off-policy (ratio ≈ 1.00) —
   so there is no self-limiting-via-uncertainty; a chance-constraint could only refuse a dose on the
   *mean* crossing the floor, never on the model admitting it doesn't know.

2. **The weak gain is not a fixable prior — it is structurally non-identified.** Scaling insulin
   sensitivity across an **8× range** (`SI_MULT` probe) leaves the forecaster's calibration and RMSE
   **essentially unchanged** (30-min coverage stays 85%; over-- bin 68→64%; per-bin RMSE flat), while
   the gain rises only from −0.4 to −2.7 mg/dL/U at 60 min. The latent Ra silently absorbs any change
   in insulin gain, so **the data is equally consistent with an 8× range of insulin responses.** An
   MPC controller would be dosing against a number the data cannot pin down.

## Verdict

**The Twin is a validated SENSOR, not an MPC-ready counterfactual model.**

- **Ship the sensor half.** Idea-4 descent-side **withdrawal** needs only the forecast *floor*
  (`lo30`), not a calibrated insulin gain — it clears its identifiable leg (`TWIN_HYPO_LEAD.md`) and
  is now on a properly-calibrated band. This is the safe half of a controller: withdrawing insulin
  needs far less model trust than adding it, and Leg A shows the under-dosed (withdrawal) direction
  is better-calibrated than the dose-more direction.
- **Do NOT build MPC on the current Twin.** The insulin channel is non-identified (8× invariance);
  any dose-more counterfactual is untrustworthy, and there is no uncertainty self-limiting.

## The prerequisite brick, if MPC is ever to be worth building

Identify the insulin channel by breaking the Ra/SI confound structurally, not with a prior tweak:

1. **Constrain Ra ≥ 0 and make it sparse** (meals are punctate arrivals, not a continuous latent
   that can drift negative to explain an insulin-driven fall) → falls must be explained by insulin.
2. **Anchor SI to the user's clinical ISF** (an informative prior from IOB/TDD), rather than a loose
   physiological prior the data cannot move.

Then re-run this test: identification succeeds iff the forecaster **degrades when SI is wrong**
(the 8× invariance breaks) *and* Leg B's gain becomes physiological. Only then is a chance-
constrained MPC over the Twin worth building — and it would still ship shadow-first at the two-test
bar. Until then, KAIROS earns its keep as a calibrated forecaster feeding the withdrawal signal.
