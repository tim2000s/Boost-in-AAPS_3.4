#!/usr/bin/env python3
"""
V1 (as it runs in the v7-shadow build) vs V6 — WHOLE-MEAL-WINDOW replay (the proper analog to the
earlier -7.5 TING finding, which was a whole-meal-window effect, NOT the confirm shot).

Fix vs v1_vs_v6_replay.py: that anchored on CONFIRMED cycles → selected V6's aggressive-confirm meals →
biased to V6. Here we anchor on MEAL ONSET (BG rising from near-baseline) and project the ENTIRE
excursion (rise → peak → recovery) so V1's recovery-tail corrections (which V6's high-IOB brake
suppresses) are captured.

Method: keep OBSERVED glucose (= the V6 arm, ground truth). Project the V1 counterfactual over the
window by the cumulative per-cycle insulin-action delta Sum(v1_units - finaldose) x oref activity x
DynISF. All V1 guards (post-rescue cap, cumulative cap, v12 ML) are already baked into v1_units.
ISF winsorised 250, per-user median. Report TING (63-140), tail BG (+150..210), peak, AND nadir/crash
(the hypo caveat: where V1 net-doses MORE, the first-order projection can't see a low the brake avoided).
Usage: python3 whole_meal_replay.py <user>  (writes wm_<user>.json)
"""
import sys, json, numpy as np, psycopg2
sys.path.insert(0, '../2026-07-v6-sim')
from sim_lib import acted_fraction

U = sys.argv[1]; HORIZON = 210
LO = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0          # optional onset epoch window (old/new split)
HI = float(sys.argv[3]) if len(sys.argv) > 3 else 9e18
TAG = sys.argv[4] if len(sys.argv) > 4 else "all"
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
cur.execute("""select ts_epoch, cgm_mgdl, variable_sens, boostv5_state, boostv5_finaldose, v1_units, sleep_state
   from boost_decisions where user_id=%s and variant='boost-other' and cgm_mgdl is not null
   order by ts_epoch""", (U,))
r = cur.fetchall()
EP = np.array([x[0] for x in r], float); BG = np.array([x[1] for x in r], float)
ISF = np.array([x[2] if x[2] is not None else np.nan for x in r], float)
if np.nanmedian(ISF) < 15: ISF *= 18.0
ISF = np.minimum(ISF, 250.0); isf_med = float(np.nanmedian(ISF))
STATE = [x[3] for x in r]
V6 = np.array([x[4] or 0.0 for x in r], float)
V1 = np.array([(x[5] if x[5] is not None else np.nan) for x in r], float)
AWAKE = [x[6] == 'AWAKE' for x in r]                             # meal-dosing-active window (telemetry)
N = len(r)
def idx_at(e, tol=400):
    i = np.searchsorted(EP, e); c = [j for j in (i-1, i, i+1) if 0 <= j < N and abs(EP[j]-e) < tol]
    return min(c, key=lambda j: abs(EP[j]-e)) if c else None
def bg_at(e): j = idx_at(e); return BG[j] if j is not None else np.nan

# --- meal onsets: BG rising through 130 from a near-baseline foot, AWAKE (meal-dosing active), deduped ---
onsets = []; last = -1e9
for i in range(9, N):
    if EP[i]-EP[i-1] > 900: continue
    foot = BG[max(0, i-9):i+1].min()                             # trailing ~45min min
    if BG[i] > 130 and BG[i-1] <= 130 and foot < 120 and AWAKE[i] and (EP[i]-last) > 7200:
        last = EP[i]
        if LO <= EP[i] < HI: onsets.append(i)

def ting(p): return 100.0*np.mean((p >= 63) & (p <= 140))
def project(e0, k0):
    dd = [(EP[j], V1[j]-V6[j]) for j in range(k0, N)
          if EP[j] <= e0+HORIZON*60 and not np.isnan(V1[j]) and abs(V1[j]-V6[j]) > 1e-9]
    obs, v1p = [], []
    for mm in range(0, HORIZON+1, 5):
        t = e0+mm*60; ba = bg_at(t)
        if np.isnan(ba): continue
        obs.append(ba)
        v1p.append(ba - isf_med*sum(d*acted_fraction((t-s)/60.0) for s, d in dd if s <= t))
    return (np.array(obs), np.array(v1p)) if len(obs) >= 20 else (None, None)

meals = []
for i in onsets:
    obs, v1p = project(EP[i], i)
    if obs is None: continue
    net = round(float(np.nansum([V1[j]-V6[j] for j in range(i, N) if EP[j] <= EP[i]+HORIZON*60 and not np.isnan(V1[j])])), 3)
    meals.append(dict(
        v6_ting=round(ting(obs),1), v1_ting=round(ting(v1p),1),
        v6_tail=round(obs[-8:].mean(),1), v1_tail=round(v1p[-8:].mean(),1),
        v6_peak=round(obs.max(),1), v1_peak=round(v1p.max(),1),
        v6_nadir=round(obs.min(),1), v1_nadir=round(v1p.min(),1),
        v6_t140=round(100*np.mean(obs>140),1), v1_t140=round(100*np.mean(v1p>140),1),
        v6_crash=int(obs.min()<70), v1_crash=int(v1p.min()<70),
        v6_deep=int(obs.min()<54), v1_deep=int(v1p.min()<54),
        net_v1_minus_v6=net))
json.dump(dict(user=U, isf=isf_med, n=len(meals), meals=meals), open(f"wm_{U}_{TAG}.json","w"))
def m(f): return round(np.mean([f(x) for x in meals]),1) if meals else 0
print(f"{U} [{TAG}]: {len(meals)}mw | TING% V6 {m(lambda x:x['v6_ting'])} vs V1 {m(lambda x:x['v1_ting'])}"
      f" | tail V6 {m(lambda x:x['v6_tail'])} vs V1 {m(lambda x:x['v1_tail'])}"
      f" | %>140 V6 {m(lambda x:x['v6_t140'])} vs V1 {m(lambda x:x['v1_t140'])}"
      f" | crash% V6 {100*m(lambda x:x['v6_crash']):.0f} vs V1 {100*m(lambda x:x['v1_crash']):.0f}"
      f" | net V1-V6 {m(lambda x:x['net_v1_minus_v6'])}U")
conn.close()
