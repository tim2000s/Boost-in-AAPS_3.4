#!/usr/bin/env python3
"""
Validate the dose-conservative cold-IDLE prototype (coldConfirmDoseFactor=0.6) via the counterfactual
BG forward simulator. For each of tim's (V5-ACTIVE) cold-IDLE confirm episodes, project BG under the
actual dose path vs one where ONLY the cold-confirm cycle's SMB is scaled by the factor, and compare
the post-confirm trough (undershoot relief) and peak (coverage cost).

Basal cancels (same in both paths), so SMB-only (finalDose) paths suffice; the projection delta is
driven entirely by the cold-confirm cycle's reduced shot. ISF = tim's median DynISF (132 mg/dl/U).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.expanduser("~/oref-investigations"))
import json
import replay
from boost_v5_forward_sim import ForwardSimulator

FACTOR = 0.6
ISF = 132.0
POST = 15   # cycles after confirm to watch (75 min)
sim = ForwardSimulator(user_isf_mgdl_per_unit=ISF)

cfg = json.load(open(replay.CONFIG_PATH))
s = next(x for x in cfg["sites"] if x["tag"] == "self")
cyc = replay.load(s, 30, use_cache=True)["cyc"]

episodes = []
for j in range(1, len(cyc)):
    if cyc[j]["state"]=="CONFIRMED" and cyc[j-1]["state"]=="IDLE":
        lo, hi = j, min(j+POST+1, len(cyc))
        bgs = [cyc[k]["bg"] for k in range(lo, hi)]
        if any(b is None for b in bgs) or len(bgs) < 6: continue
        dose_actual = [cyc[k]["finalDose"] for k in range(lo, hi)]
        dose_cf = list(dose_actual); dose_cf[0] = dose_actual[0]*FACTOR   # discount the confirm shot
        bg_cf = sim.project(bgs, dose_actual, dose_cf)
        trough_obs, trough_cf = min(bgs), min(bg_cf)
        peak_obs, peak_cf = max(bgs), max(bg_cf)
        episodes.append({"confirm_bg":bgs[0], "dose":dose_actual[0],
                         "undershoot": trough_obs<=80,
                         "trough_obs":trough_obs, "trough_cf":trough_cf,
                         "peak_obs":peak_obs, "peak_cf":peak_cf})

print(f"=== Cold-IDLE dose-conservative validation (tim, V5-ACTIVE) — {len(episodes)} episodes, factor {FACTOR} ===\n")
print(f"{'#':2} {'confirmBG':9} {'shot(U)':7} {'class':10} {'trough obs→cf':16} {'peak obs→cf':14}")
for i,e in enumerate(episodes,1):
    cls = "UNDERSHOOT" if e["undershoot"] else "ok"
    print(f"{i:<2} {e['confirm_bg']:<9.0f} {e['dose']:<7.2f} {cls:10} "
          f"{e['trough_obs']:.0f}→{e['trough_cf']:.0f} (+{e['trough_cf']-e['trough_obs']:.0f}){'':4} "
          f"{e['peak_obs']:.0f}→{e['peak_cf']:.0f} (+{e['peak_cf']-e['peak_obs']:.0f})")

us = [e for e in episodes if e["undershoot"]]
ok = [e for e in episodes if not e["undershoot"]]
def avg(L,f): return sum(f(x) for x in L)/len(L) if L else 0
print(f"\n--- UNDERSHOOT episodes (n={len(us)}): mean trough lift +{avg(us, lambda e: e['trough_cf']-e['trough_obs']):.1f} mg/dL "
      f"(obs {avg(us, lambda e: e['trough_obs']):.0f} → cf {avg(us, lambda e: e['trough_cf']):.0f}); "
      f"how many cleared >80: {sum(e['trough_cf']>80 for e in us)}/{len(us)})")
print(f"--- OK/sustained episodes (n={len(ok)}): mean peak rise +{avg(ok, lambda e: e['peak_cf']-e['peak_obs']):.1f} mg/dL "
      f"(coverage cost; obs peak {avg(ok, lambda e: e['peak_obs']):.0f} → cf {avg(ok, lambda e: e['peak_cf']):.0f})")
