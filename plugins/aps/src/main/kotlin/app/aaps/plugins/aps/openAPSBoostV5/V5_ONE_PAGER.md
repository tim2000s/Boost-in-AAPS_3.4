# Boost V5 — at a glance

**What it is**

Boost V5 is a clean-slate redesign of the Boost dosing decision. Instead
of the eight-tier if-else ladder the existing Boost uses, V5 has a short
three-phase pipeline that asks "is this a meal?" once, commits to a
single decision, and applies safety damping in a defined order. It's a
parallel plugin alongside the current Boost, so V5 doesn't replace
anything — it appears in the plugin selector as **"Boost V6"**, the
user-facing name it shipped under.


**Why I did it**

After releasing the current Boost (4.1.5), I spent a lot of time trying
to take it further. Each step added another layer of overlay onto the
existing tier ladder — more sophisticated meal detection, extra safety
gates, ML-backed signals, additional brake mechanisms. Each one was a
sensible local fix, but together they complicated the decision path,
made the code harder to reason about, and made it harder to add the
next thing safely.

At a certain point I decided to step back. Instead of yet another layer
on top, I went back to basics and started from scratch with what I'd
learned along the way.

V5 is the result. It keeps the bits that genuinely work (the
sensitivity stack, the exercise classifier, the post-exercise window,
the calibration block, the user's existing settings for everything
upstream of the dosing decision) and replaces the dosing decision
itself with a single coherent design. The minimal-settings tenet fell
out of that — V5's hardcoded constants get calibrated once at release;
user-facing settings only exist where per-user variation genuinely
helps.


**What V5 changes**

V5 carries an explicit "meal hypothesis" across cycles: IDLE →
OBSERVING (small test dose, 30 % of normal) → CONFIRMED (catch-up
dose, 180 % of normal) → COMMITTED (sustain) → RECOVERING (back off
as IOB takes effect) → IDLE. The whole thing is driven by a continuous
0–1 score — six weighted signals including BG delta, acceleration, an
ML meal-likelihood reading, a recent-low penalty and time of day. No
binary cliffs; just-miss patterns accumulate score over time and reach
the right state.

Safety composition has a hard floor: the dose cannot fall below 30 %
of oref's calculated need before the per-state action multipliers are
applied. The two remaining damping multipliers are graduated, so they
smooth rather than stack to zero.

V5 also introduces an ML hypo-risk damper (the existing Boost has no
ML at all) and a graduated IOB headroom brake replacing the existing
hard Tier 7 cap.


**What stays the same**

This is the part that often surprises people. V5 only redesigns the
dosing decision — the layer below `determineBasal`. The plugin code
that shapes the inputs (sleep-in window, inactivity scaling, exercise
classification, post-exercise recovery detection, dynISF velocity,
boost active time window, HR zones, profile, ISF, autosens,
TempTargets) all keeps working unchanged. V5 reads the result, it
doesn't rebuild it.

So if you're on the existing Boost today, your sleep-in, activity %,
post-exercise recovery hours, dynISF velocity, max IOB, autosens,
TempTarget handling — none of that changes. The only settings you
stop using are the dose-sizing dials that lived inside
`determineBasal`: `boost_insulin_req_pct`, `boost_scale`,
`boost_percent_scale_factor`, `boost_bolus_cap`, the per-tier toggles.
V5 has its own internal logic instead.


**What's new for the user**

Three new dials, calibrated defaults:

- **Aggression** (0.7–1.3, default 1.0): scales the catch-up dose at
  the CONFIRMED moment.
- **Hypo Caution** (1.0–2.0, default 1.0): strengthens the brake when
  the ML hypo-risk model thinks a low is coming. Raise it for hypo
  unawareness or recent severe lows.
- **Sensitivity** (0.8–1.2, default 1.0): fine sensitivity multiplier
  inside the aggression budget — shipped after backtesting justified it.

Those are the headline knobs. An Advanced sub-screen adds the dose caps
(CONFIRMED / COMMITTED / cumulative-60-min), the fast-carb confirm
toggle and the pre-meal target — all auto-seeded from the user's own
14-day history on first activation (suggestion-only).


**Where we are (updated 2026-07)**

V5 **shipped as the "Boost V6" plugin** — selectable as the active APS
algorithm and running in production (active on the developer's own pump
since ~February 2026). Selecting plain **"Boost"** instead runs V1
dosing with the V6 decision in shadow: it computes what it *would* do
each cycle and writes it to the AAPS log and Nightscout deviceStatus
(`boostV5_score`, `boostV5_state`, `boostV5_age`, `boostV5_budget`,
`boostV5_actionMult`, `boostV5_finalDose`, `boostV5_gateReduction`)
without touching the pump. Shadow-first remains the supported
onboarding for anyone but the developer.

The backtesting toolkit (`backtesting/`) tracks where V6's decisions
diverge from V1's delivery. There is still no clinical superiority
claim — the evidence is one developer's ~5 months of active use plus a
small shadow cohort (see the README's Testing & evidence section).
