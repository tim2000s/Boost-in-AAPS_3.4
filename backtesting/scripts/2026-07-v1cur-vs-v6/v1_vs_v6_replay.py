#!/usr/bin/env python3
"""
V1 (as it runs in the V7-shadow build) vs V6 — semi-closed-loop confirm-meal replay.

KEY ARCHITECTURE FACT (OpenAPSBoostPlugin ~1345): there is ONE determine_basal call — the V1
DetermineBasalBoost — passed the RESOLVED cumulativeSmbCap60Min (line 1360). Its output rT.units IS
the logged `v1_units`, computed live each cycle WITH all of V1's guards (post-rescue cap, cumulative
cap, v12 ML hypo-risk). The V5/V6 override replaces .units AFTER (line 1505). So the DB's v1_units is
already the in-build V1 dose — no offline reconstruction needed (an earlier attempt to re-apply the
guards double-counted them and used the wrong cap default → discarded).

Two arms, same method as 2026-07-v6-sim/sim_replay.py: keep OBSERVED glucose (= what V6 ran, so the V6
arm IS the ground-truth forward trace); project the V1 counterfactual by the insulin-action delta
(v1_units - finaldose) x oref activity x DynISF. Metric window = each CONFIRMED cycle, forward 150 min.
ISF winsorised 250, per-user median. Usage: python3 v1_vs_v6_replay.py <user>  (writes vv_<user>.json)

CAVEAT: v1_units for the earliest V6-era cycles was logged by pre-2026-07-04 builds (no post-rescue
cap); but confirm meals almost never sit in a post-rescue window (BG is high), so that guard barely
moves confirm-meal v1_units — the confirm-shot comparison is representative of current-V1.
"""
import sys, json, numpy as np, psycopg2
sys.path.insert(0, '../2026-07-v6-sim')
from sim_lib import acted_fraction

U = sys.argv[1]; HORIZON = 150
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
cur.execute("""select ts_epoch, cgm_mgdl, variable_sens, boostv5_state, boostv5_finaldose, v1_units
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
N = len(r)
def idx_at(e, tol=400):
    i = np.searchsorted(EP, e); c = [j for j in (i-1, i, i+1) if 0 <= j < N and abs(EP[j]-e) < tol]
    return min(c, key=lambda j: abs(EP[j]-e)) if c else None
def bg_at(e): j = idx_at(e); return BG[j] if j is not None else np.nan
def project_v1(k0, e0):
    dd = [(EP[j], V1[j]-V6[j]) for j in range(k0, N)
          if EP[j] <= e0+HORIZON*60 and not np.isnan(V1[j]) and abs(V1[j]-V6[j]) > 1e-9]
    obs, path = [], []
    for m in range(0, HORIZON+1, 5):
        t = e0+m*60; ba = bg_at(t)
        if np.isnan(ba): continue
        obs.append(ba)
        path.append(ba - isf_med*sum(d*acted_fraction((t-s)/60.0) for s, d in dd if s <= t))
    if len(obs) < 10: return None, None
    return np.array(obs), np.array(path)
def ting(p): return 100.0*np.mean((p >= 63) & (p <= 140))
meals = []
for k in range(N):
    if STATE[k] != 'CONFIRMED' or np.isnan(V1[k]): continue
    obs, v1p = project_v1(k, EP[k])
    if obs is None: continue
    meals.append(dict(
        v6_ting=round(ting(obs),1), v1_ting=round(ting(v1p),1),
        v6_tail=round(obs[-6:].mean(),1), v1_tail=round(v1p[-6:].mean(),1),
        v6_nadir=round(obs.min(),1), v1_nadir=round(v1p.min(),1),
        v6_crash=int(obs.min()<70), v1_crash=int(v1p.min()<70),
        v6_deep=int(obs.min()<54), v1_deep=int(v1p.min()<54),
        v6_phi=int(obs[-6:].mean()>160), v1_phi=int(v1p[-6:].mean()>160),
        ddose=round(V1[k]-V6[k],3)))
json.dump(dict(user=U, isf=isf_med, n=len(meals), meals=meals), open(f"vv_{U}.json","w"))
def m(f): return round(np.mean([f(x) for x in meals]),1) if meals else 0
print(f"{U}: {len(meals)} confirm meals | TING% V6 {m(lambda x:x['v6_ting'])} vs V1 {m(lambda x:x['v1_ting'])}"
      f" | tailBG V6 {m(lambda x:x['v6_tail'])} vs V1 {m(lambda x:x['v1_tail'])}"
      f" | crash% V6 {100*m(lambda x:x['v6_crash']):.0f}→ V1 {100*m(lambda x:x['v1_crash']):.0f}"
      f" | meanΔdose(V1-V6) {m(lambda x:x['ddose'])}U")
conn.close()
