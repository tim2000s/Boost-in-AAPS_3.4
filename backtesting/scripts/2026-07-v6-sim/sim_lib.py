#!/usr/bin/env python3
"""
Semi-closed-loop insulin-perturbation replay — shared library.

Approach (the developer's design): keep each user's OBSERVED glucose trace (it already contains the real
unannounced meals). Replay a candidate dosing model; where its dose DIFFERS from what actually ran,
perturb the trajectory by the insulin-action difference (oref exponential activity × DynISF-at-the-
time), and let the model RE-DOSE on the perturbed trace (semi-closed-loop). No carb model → sidesteps
the ReplayBG unannounced-meal problem; the only thing modelled is the insulin delta, via known
pharmacology + the clinical/DynISF sensitivity (not the non-identified fitted SI).

VALIDITY: first-order in the dose delta (softens for large perturbations); DynISF held at its observed
value; mlMealLikely held observed. FIDELITY-GATED: the port must reproduce logged doses first.
"""
import numpy as np

# ---- oref exponential insulin activity / IOB (the loop's own model) ----
def insulin_curves(peak=75.0, dia=300.0, dt=5.0):
    """Return (t_grid_min, iob_fraction_remaining, activity_fraction_per_min) for a unit dose."""
    t = np.arange(0, dia + dt, dt)
    tau = peak * (1 - peak / dia) / (1 - 2 * peak / dia)
    a = 2 * tau / dia
    S = 1 / (1 - a + (1 + a) * np.exp(-dia / tau))
    iob = 1 - S * (1 - a) * ((t ** 2 / (tau * dia * (1 - a)) - t / tau - 1) * np.exp(-t / tau) + 1)
    iob = np.clip(iob, 0, 1)
    acted = 1 - iob                                 # cumulative fraction of the dose that has ACTED
    return t, iob, acted

_T, _IOB, _ACTED = insulin_curves()
def acted_fraction(dt_min):
    """Cumulative fraction of a dose that has acted dt_min minutes after delivery."""
    if dt_min <= 0: return 0.0
    if dt_min >= _T[-1]: return 1.0
    return float(np.interp(dt_min, _T, _ACTED))


# ---- V6 confirm-shot reconstruction (faithful port; validated vs boostv5_finaldose) ----
CONFIRMED_MULT = 1.8
def velocity_factor(rise, lo=25.0, hi=50.0, floor=0.40):
    if rise >= hi: return 1.0
    if rise <= lo: return floor
    return floor + (1.0 - floor) * (rise - lo) / (hi - lo)

def v6_confirm_shot(budget, knob, rise, confirmed_cap):
    """The velocity-scaled, cap-clamped CONFIRMED commit shot (pre Phase-3 brake)."""
    raw = budget * (CONFIRMED_MULT * knob) * velocity_factor(rise)
    return min(raw, confirmed_cap)


# ---- the candidate FIX: IOB-aware ramp on the confirm shot ----
# Small first shot when little insulin is on board (the low-IOB overshoot/crash context, 28%/13%-deep),
# escalating to the full shot as IOB proves the meal. Rest of the insulin follows via COMMITTED holds
# on the (higher) subsequent trajectory — captured by the semi-closed-loop, not a hard block.
IOB_RAMP_FLOOR = 0.25      # fraction of the shot delivered at IOB≈0
IOB_RAMP_FULL_U = 2.0      # IOB (U) at which the full shot is allowed
def iob_ramp(iob):
    if iob >= IOB_RAMP_FULL_U: return 1.0
    return IOB_RAMP_FLOOR + (1.0 - IOB_RAMP_FLOOR) * max(0.0, iob) / IOB_RAMP_FULL_U

def fix_confirm_shot(budget, knob, rise, confirmed_cap, iob):
    return v6_confirm_shot(budget, knob, rise, confirmed_cap) * iob_ramp(iob)
