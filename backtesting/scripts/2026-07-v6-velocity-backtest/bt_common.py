#!/usr/bin/env python3
"""
Shared logic for the V6 velocity-gate backtest. Faithful port of the V5 confirm gate + velocity
scaling (DetermineBasalBoostV5.kt, MealActionMultiplier.kt, MealHypothesis.kt as of 2026-07-19).

The gate: prospectiveConfirmShot = budget × (CONFIRMED_MULT × aggressionKnob) × velocityFactor(rise)
          confirmDoseAdequate    = prospectiveConfirmShot > confirmDoseFloor
          confirmDoseFloor        = min( min(committedCap, 0.5), 0.8 × confirmedCap )
A scenario changes ONLY velocityScaledDoseFactor's (lo, hi, floor). Everything else is telemetry.

We can price the DOSE-LEVEL change per scenario exactly; we CANNOT simulate the counterfactual
glucose (no validated simulator — identification wall). So the analysis cross-references each meal's
ACTUAL outcome (what really happened after the baseline shot) with what each scenario would DECIDE.
"""
import numpy as np

# --- ported constants ---
CONFIRMED_MULT = 1.8
CONFIRM_FLOOR_COMMITTED_TERM_MAX = 0.5
CONFIRM_DOSE_FLOOR_MAX_FRAC_OF_CONFIRMED_CAP = 0.8

# --- scenarios: (lo, hi, floor) for the velocity curve; 'decoupled' keeps baseline gate, retuned size ---
SCENARIOS = {
    'baseline':        dict(lo=25.0, hi=50.0,  floor=0.40),
    'mild':            dict(lo=25.0, hi=70.0,  floor=0.25),
    'target':          dict(lo=25.0, hi=90.0,  floor=0.15),
    'steep':           dict(lo=25.0, hi=110.0, floor=0.10),
    'decoupled_target':dict(lo=25.0, hi=90.0,  floor=0.15, gate_uses_baseline=True),
}


def velocity_factor(rise, lo, hi, floor, **_):
    if rise >= hi: return 1.0
    if rise <= lo: return floor
    return floor + (1.0 - floor) * (rise - lo) / (hi - lo)


def confirm_dose_floor(committed_cap, confirmed_cap):
    return min(min(committed_cap, CONFIRM_FLOOR_COMMITTED_TERM_MAX),
               CONFIRM_DOSE_FLOOR_MAX_FRAC_OF_CONFIRMED_CAP * confirmed_cap)


def prospective_shot(budget, knob, vf):
    return budget * (CONFIRMED_MULT * knob) * vf


def eval_scenario(rec, scn):
    """Return (confirms: bool, shot_U: float) for this confirm cycle under scenario scn."""
    p = SCENARIOS[scn]
    vf_gate = velocity_factor(rec['rise'], **SCENARIOS['baseline']) if p.get('gate_uses_baseline') \
        else velocity_factor(rec['rise'], **p)
    vf_size = velocity_factor(rec['rise'], **p)
    floor = confirm_dose_floor(rec['committed_cap'], rec['confirmed_cap'])
    confirms = prospective_shot(rec['budget'], rec['knob'], vf_gate) > floor
    shot = min(prospective_shot(rec['budget'], rec['knob'], vf_size), rec['confirmed_cap']) if confirms else 0.0
    return confirms, shot
