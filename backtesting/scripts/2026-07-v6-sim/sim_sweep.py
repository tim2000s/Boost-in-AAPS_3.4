#!/usr/bin/env python3
"""
Ramp-parameter sweep: map crash-prevention vs high-plateau cost over the IOB-ramp (floor × full-IOB).
Reuses the fidelity-gated semi-closed-loop replay; pulls each user's data ONCE, then runs every param
combo in memory. floor=1.0 recovers V6 (no ramp). Usage: python3 sim_sweep.py <user>  (parallel).
"""
import sys, json, numpy as np, psycopg2
sys.path.insert(0, '.')
from sim_lib import v6_confirm_shot, acted_fraction

USER = sys.argv[1]
FLOORS = [0.0, 0.15, 0.25, 0.40, 0.60, 1.0]
FULLS = [1.0, 1.5, 2.0, 3.0]
MARGIN, HORIZON = 20.0, 150

def iob_ramp(iob, floor, full):
    if floor >= 1.0: return 1.0
    if iob >= full: return 1.0
    return floor + (1.0 - floor) * max(0.0, iob) / full

conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
cur.execute("""select ts_epoch, cgm_mgdl, variable_sens, sug_current_target, iob_iob,
   boostv5_state, boostv5_finaldose, boostv5_budget, boostv5_aggressionknob, boostv5_confirmedcap, boostv5_committedcap
   from boost_decisions where user_id=%s and variant='boost-other' and cgm_mgdl is not null order by ts_epoch""", (USER,))
rows = cur.fetchall(); conn.close()
EP = np.array([r[0] for r in rows], float); BG = np.array([r[1] for r in rows], float)
ISF = np.array([r[2] if r[2] is not None else np.nan for r in rows], float)
if np.nanmedian(ISF) < 15: ISF *= 18.0
TGT = np.array([(r[3] if r[3] is not None else 100.0) for r in rows], float)
if np.nanmedian(TGT) < 20: TGT *= 18.0
BUD = np.array([r[7] if r[7] is not None else np.nan for r in rows], float)
def bg_at(e, tol=400):
    i = np.searchsorted(EP, e); c = [j for j in (i - 1, i, i + 1) if 0 <= j < len(EP) and abs(EP[j] - e) < tol]
    return BG[min(c, key=lambda j: abs(EP[j] - e))] if c else np.nan
def idx_at(e, tol=200):
    i = np.searchsorted(EP, e); c = [j for j in (i - 1, i, i + 1) if 0 <= j < len(EP) and abs(EP[j] - e) < tol]
    return min(c, key=lambda j: abs(EP[j] - e)) if c else None

# cache confirm-meal inputs once
CM = []
for k in range(len(rows)):
    if rows[k][5] != 'CONFIRMED' or rows[k][7] is None or rows[k][8] is None: continue
    e0 = EP[k]; rise = max(0.0, 2.0 * (BG[k] - bg_at(e0 - 900)))
    if np.isnan(rise): continue
    ccap, mcap = rows[k][9] or 0.25, rows[k][10] or 0.25
    s_v6 = v6_confirm_shot(rows[k][7], rows[k][8], rise, ccap)
    isf_meal = ISF[k] if not np.isnan(ISF[k]) else np.nanmedian(ISF)
    CM.append(dict(e0=e0, iob0=rows[k][4] or 0.0, s_v6=s_v6, mcap=mcap, budget=rows[k][7], isf=isf_meal))

def sim(meal, floor, full):
    s_fix = meal['s_v6'] * iob_ramp(meal['iob0'], floor, full)
    reserve = max(0.0, meal['s_v6'] - s_fix); delivered = 0.0
    dd = [(meal['e0'], s_fix - meal['s_v6'])]; e0 = meal['e0']
    path = []
    for m in range(0, HORIZON + 1, 5):
        t = e0 + m * 60; ba = bg_at(t)
        if np.isnan(ba): continue
        bf = ba - meal['isf'] * sum(d * acted_fraction((t - s) / 60.0) for s, d in dd)
        path.append(bf)
        if 0 < m <= 90 and delivered < reserve - 1e-6:
            j = idx_at(t); tgt = TGT[j] if j is not None and not np.isnan(TGT[j]) else 100.0
            if bf > tgt + MARGIN:
                bud = BUD[j] if j is not None and not np.isnan(BUD[j]) else meal['budget']
                h = min(meal['mcap'], bud, reserve - delivered); dd.append((t, h)); delivered += h
    if len(path) < 10: return None
    p = np.array(path); return dict(nadir=p.min(), plat=p[-6:].mean())

out = {}
for fl in FLOORS:
    for fu in FULLS:
        if fl >= 1.0 and fu != FULLS[0]: continue          # floor=1 is V6, full irrelevant
        res = [sim(m, fl, fu) for m in CM]; res = [r for r in res if r]
        if not res: continue
        out[f"{fl}_{fu}"] = dict(floor=fl, full=fu, n=len(res),
            crash=float(np.mean([r['nadir'] < 70 for r in res])),
            deep=float(np.mean([r['nadir'] < 54 for r in res])),
            high=float(np.mean([r['plat'] > 160 for r in res])),
            plat=float(np.mean([r['plat'] for r in res])))
json.dump(dict(user=USER, n=len(CM), combos=out), open(f"sweep_{USER}.json", "w"))
print(f"{USER}: {len(CM)} meals × {len(out)} combos")
