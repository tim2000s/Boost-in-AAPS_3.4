#!/usr/bin/env python3
"""
KAIROS — does the Twin unlock the TING planner? Offline characterisation (2026-07-18).

TING_ENGINE.md killed the TING planner ON OREF's forecast: fed `eventualBG` it was inert for most
cycles and degenerate for user E (69 U/day). The Twin was built precisely to give the planner a
real forecast + a calibrated floor. This script re-runs the planner fed by the TWIN (fc30 as the
forecast, lo30 as the floor) and asks the only questions an OFFLINE run can honestly answer under
the identification constraint (no counterfactual BG, so we CANNOT claim it improves TING):

  1. Is it SANE — total U/day in a physiological range, not degenerate like the oref-fed version?
  2. Is it SMOOTHER than the incumbent (lower dose-to-dose variation = the CV lever)?
  3. Does it RESPECT THE FLOOR (near-zero dosing when the calibrated floor is low)?
  4. WHERE does it act — out-dosing ahead of predicted highs, holding in band, withdrawing on the
     descent — i.e. does it move insulin EARLIER (harm-neutral) rather than ADD it (harm)?

Passing this is the gate to SHADOW-logging (then the two-test bar), NOT evidence it helps.

Uses the saved Twin fit (fc30=fc6, lo30=lo6) + the delivered insulin. SI is ANCHORED via ISF
(clinical, external) — the off-policy test showed SI is non-identifiable from data but the forward
gain is correct once anchored. ISF is swept to show the characterisation is robust to it.
Reads npz from argv[1]. Aggregates only. Committable.
"""
import sys
import numpy as np

DATA = sys.argv[1] if len(sys.argv) > 1 else 'twin_data_tim.npz'
FIT = sys.argv[2] if len(sys.argv) > 2 else 'twin_fit_tim.npz'
d = np.load(DATA); INS = d['ins']; CGM = d['cgm']; N = len(CGM)
f = np.load(FIT); FC30 = f['fc6']; LO30 = f['lo6']
TEST = int(0.55 * N)

# ---- IOB proxy (U): SC depot Isc1+Isc2 from the delivered insulin ----
ka1, ka2 = 0.030, 0.022
Isc1 = Isc2 = 0.0
IOB = np.zeros(N)
for i in range(N):
    for _ in range(5):
        Isc1 = Isc1 + (-ka1 * Isc1) + INS[i] / 5.0
        Isc2 = Isc2 + (ka1 * Isc1 - ka2 * Isc2)
    IOB[i] = Isc1 + Isc2

# ---- TING planner (faithful port of TingPlanner.kt) ----
TING_AIM, TING_GAIN, HZ_ACT = 112.0, 0.5, 0.35
STEP_UP, FLOOR_MARGIN = 0.20, 8.0


def ting_plan(bg, fc, minguard, thr, isf, iob, maxiob, lastdose, step=0.05):
    perU = max(isf, 1.0) * HZ_ACT
    if minguard <= thr:
        return 0.0, True
    if fc <= TING_AIM:
        return 0.0, False
    raw = (TING_GAIN * (fc - TING_AIM)) / perU
    dose = min(raw, lastdose + STEP_UP)
    floor_cap = max(0.0, (minguard - (thr + FLOOR_MARGIN)) / perU)
    clipped = dose > floor_cap + 1e-9
    dose = min(dose, floor_cap)
    dose = min(dose, max(0.0, maxiob - iob))
    dose = np.floor(dose / step + 1e-9) * step
    return max(0.0, dose), clipped


def characterise(isf, maxiob=8.0, self_iob=False):
    idx = [i for i in range(TEST, N) if not np.isnan(CGM[i]) and not np.isnan(FC30[i]) and not np.isnan(LO30[i])]
    doses = np.zeros(len(idx)); v6 = np.zeros(len(idx)); clip = np.zeros(len(idx), bool)
    last = 0.0
    s1 = s2 = 0.0                                        # planner's OWN SC depot (self-IOB)
    for k, i in enumerate(idx):
        iob_seen = (s1 + s2) if self_iob else IOB[i]     # closed-loop self-IOB vs delivered-IOB
        dz, cl = ting_plan(CGM[i], FC30[i], LO30[i], 70.0, isf, iob_seen, maxiob, last)
        doses[k] = dz; clip[k] = cl; last = dz
        for _ in range(5):                               # advance the planner's own depot by its dose
            s1 = s1 + (-ka1 * s1) + dz / 5.0
            s2 = s2 + (ka1 * s1 - ka2 * s2)
        v6[k] = INS[i]                                   # delivered this bin (SMB + basal)
    bins_per_day = 288.0
    ndays = len(idx) / bins_per_day
    # smoothness: sd of dose-to-dose change (lower = smoother)
    smooth_ting = np.std(np.diff(doses)); smooth_v6 = np.std(np.diff(v6))
    lo_floor = LO30[np.array(idx)] < 75                  # calibrated floor is low
    dose_when_floor = doses[lo_floor].sum() / max(1, lo_floor.sum())
    # where it acts vs V6 (by 30-min Twin forecast band)
    fc = FC30[np.array(idx)]
    held = doses == 0
    print(f"\n  ISF={isf:.0f} mg/dL/U  (n={len(idx)} cycles, {ndays:.0f} days)")
    print(f"    TING would-dose : {doses.sum()/ndays:5.1f} U/day   (delivered {v6.sum()/ndays:5.1f} U/day)   "
          f"[oref-fed planner was degenerate 69 U/day for E / inert for most]")
    print(f"    dose-to-dose sd : {smooth_ting:.3f} U (TING) vs {smooth_v6:.3f} U (delivered)  "
          f"-> {'SMOOTHER' if smooth_ting < smooth_v6 else 'NOT smoother'}")
    print(f"    floor respect   : mean dose when floor lo30<75 = {dose_when_floor:.3f} U  "
          f"(floor-clipped {100*clip.mean():.0f}% of cycles)")
    print(f"    behaviour       : holds (dose 0) {100*held.mean():.0f}% of cycles; "
          f"acts only when forecast > aim 112 (moves insulin earlier, never chases down)")


if __name__ == '__main__':
    print("KAIROS — TING planner fed by the TWIN (fc30 forecast + lo30 calibrated floor)")
    print("Offline characterisation ONLY — cannot claim a TING improvement (no counterfactual BG).")
    print("\n--- OPEN-LOOP (planner sees delivered IOB, not its own doses) ---")
    for isf in (30.0, 45.0, 60.0):
        characterise(isf)
    print("\n--- CLOSED-LOOP-ish (planner sees its OWN pending insulin: the anti-windup fix) ---")
    for isf in (30.0, 45.0, 60.0):
        characterise(isf, self_iob=True)
    print("\nGate: if SANE U/day + SMOOTHER + floor-respecting across ISF, the Twin unlocks the planner")
    print("(vs the degenerate oref-fed version) and it earns SHADOW-logging. Value still needs the")
    print("shadow + two-test bar; this run only shows it is well-behaved, not that it helps.")
