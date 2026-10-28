# TING engine — core built, and what the overlay backtest honestly revealed

*2026-07-18. Follows TING_FRONTIER.md (TING is a variance problem). Core:
`plugins/aps/.../openAPSBoostTing/TingPlanner.kt` (+ 8 unit tests). Overlay:
`ting_planner_backtest.py`.*

## What was built

A pure, tested TING planner — a one-step, risk-limited **smoother** (not an amplifier), landing the
frontier finding directly:
- acts on a forecast so it nudges **early**;
- a **low-gain proportional** nudge toward a safety-biased aim (112 mg/dL), **rate-limited** from the
  last dose so it glides instead of ringing — the anti-variance mechanism;
- **never chases glucose down**, and **hard-clips** every dose so the worst-case predicted low stays
  above threshold + margin (floor sacred), plus a maxIOB clip.

It returns a *would-dose* only; it doses nothing (shadow-first by construction). 8 unit tests pin the
floor-respect and anti-ringing behaviour.

## What the overlay backtest revealed (the honest bit)

Overlaid on the cohort's real V6 trajectories, keyed on oref `eventualBG`, the planner is:

| tag | V6 U/day | TING U/day | verdict |
|---|---|---|---|
| tim, A, B, C, F, H | 22–57 | **0.0** | inert (eventualBG already ≤ aim → nothing to nudge) |
| E | 12 | **69.0** | degenerate (eventualBG runs high → nudges forever, absurd insulin) |

The "smoother" flag on the inert users is trivial — zero doses have zero jerk. This is not success;
it is the **identification constraint biting, made concrete**:

> You cannot validate a new controller by overlaying it on trajectories the *old* controller already
> dosed. You either react to glucose that was already being handled (double-dosing — user E), or to a
> closed-loop endpoint that is already at target (inertness — everyone else). Scoring a dosing POLICY
> needs the **counterfactual** trajectory.

## The consequence for sequencing

The counterfactual trajectory needs a **forecaster** — the per-person generative Twin (KAIROS Brick 1).
So the Twin is not optional; the backtest just proved, on real data, that it is the **prerequisite**
for validating the TING planner at all. The disciplined order is therefore:

1. **The Twin** — grow the shipped UKF into a per-person generative state-space model; validate it as a
   *forecaster* out-of-sample (prediction IS identifiable, unlike policy). Only once it can roll a
   trustworthy counterfactual can the TING planner be scored.
2. **Re-score the planner** against Twin rollouts (open-loop / undosed forecast), tune the aim, gain,
   step-limit and floor-margin so it compresses the 140–180 band without breaching the low-tail.
3. **Live shadow** logging → the two-test bar → and only then any influence on a delivered dose.

The engine's brain is built and floor-safe. The path from here to a TING it can actually move runs
through the forecaster first — which is exactly the KAIROS/AION landing, now with a receipt.
