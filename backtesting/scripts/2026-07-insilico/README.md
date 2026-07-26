# In-silico harness — virtual-patient controller A/B (simglucose)

Runs dosing controllers side-by-side on the UVA/Padova virtual patients in accelerated time, to get a **real BG trajectory** and compare behaviour/safety (TIR/TBR/TAR, hypo events, oscillation) that our shadow telemetry can't surface counterfactually.

## What this is — and isn't

This is a **virtual-patient stress test**, not an A/B on real users. It runs a controller against the 30 synthetic FDA patients (adults/adolescents/children). It **cannot** replay a real user's trace — for that you'd need ReplayBG (see the counterfactual-BG research note), which is degraded by our unannounced-meal problem. So:

- ✅ Use this to check V6/V7 for pathological behaviour on virtual patients (oscillation, stacking, hypo induction, response to meals) in accelerated time — a legitimate pre-ship safety gate.
- ❌ Do **not** read its TIR numbers as "what V6/V7 would do to Tim / the cohort." Virtual patients ≠ our users; the value is *relative* behaviour and safety, not an absolute scoreboard.

## Setup (dedicated venv — required)

simglucose needs an isolated env (it pulls old `gym` + scipy; `gym` needs `distutils`, removed in Python 3.12+, so `setuptools<81` is installed to shim it):

```
python3 -m venv ~/.venvs/boost-insilico
~/.venvs/boost-insilico/bin/python -m pip install simglucose psycopg2-binary matplotlib "setuptools<81"
```

Run with that venv's python:
```
~/.venvs/boost-insilico/bin/python insilico_harness.py --a basal_bolus --days 3 --adults 10
~/.venvs/boost-insilico/bin/python insilico_harness.py --a basal_bolus --b boost_v6 --days 3   # A/B
```

## Status

- **Harness infrastructure: built + validated.** Runs any simglucose controller across the cohort in accelerated time, computes per-patient + cohort-median metrics, and does a paired A/B (validated: same controller both sides → Δ=0). Registry-based controller plug-in (`CONTROLLERS`).
- **Boost V6/V7 controllers: NOT yet ported** — this is the substantive remaining work.

## The Boost port — and the fidelity gate (do not skip)

A controller is any object with `policy(observation, reward, done, **info) -> Action(basal, bolus)`. To run Boost, port its decision logic to Python as `boost_controller.py` (auto-registered as `boost_v6` if importable).

**Before trusting ANY Boost-vs-V7 A/B output, the port must pass a fidelity gate:** feed the port the same per-cycle inputs we have in the DB (`boost_decisions`: glucose status, IOB, profile) and check its output dose reproduces the logged `boostv5_finaldose` within tolerance. An unfaithful port produces a confident-but-wrong A/B — exactly the failure mode the 2026-07 methodology audit guarded against. No fidelity → no A/B.

The port is non-trivial (DynISF/oref baseInsulinReq + the V5 state machine + budget + caps + composed floor for V6; the distributional sizer for V7). The `boost_simulator.html` JS port is a reference for the V6 rule; `V7Sizer.kt` / `V7ResidualTracker.kt` for V7.

## Honest limits

- Virtual patients are the 2008 UVA/Padova cohort — a fixed synthetic population, not our users.
- Meals in the scenario are **announced** (the harness tells the patient the carbs); it does not model unannounced meals, so it can't stress-test the unannounced-carb handling that dominates our real hard cases.
- The metric that matters here is *relative behaviour and safety between engines*, not absolute TIR.
