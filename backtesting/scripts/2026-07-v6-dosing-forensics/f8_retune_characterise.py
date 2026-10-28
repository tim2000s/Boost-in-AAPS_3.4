#!/usr/bin/env python3
"""
FIX CHARACTERISATION — retune the EXISTING velocity gate to match the data, and show WHAT it changes
(offline, reproducible; the OUTCOME is a policy change → unvalidatable offline, this only prices the
dose delta). The forensic says onset front-load only helps on genuinely steep rises (~>45 mg/dL/15min
= ~90/30min) and mostly crashes on modest rises. Current gate gives FULL front-load at 50/30min and a
0.40 floor on flat rises. Retune: RISE_HI 50→90, FLOOR 0.40→0.15 (LO 25 unchanged).

Shows, over historical V6 meal onsets, how much front-load the retune removes and WHERE (velocity ×
crash context) — it should strip the modest-rise/crash front-loads and preserve the steep-rise ones.
"""
import numpy as np, psycopg2
from collections import defaultdict
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
USERS = ['tim', 'F', 'B', 'A', 'C', 'H']

def vfactor(rise, lo, hi, floor):
    if rise >= hi: return 1.0
    if rise <= lo: return floor
    return floor + (1.0 - floor) * (rise - lo) / (hi - lo)
CUR = dict(lo=25.0, hi=50.0, floor=0.40)
NEW = dict(lo=25.0, hi=90.0, floor=0.15)

cur.execute("select user_id,ts_epoch,cgm_mgdl,boostv5_finaldose from boost_decisions where user_id=any(%s) and variant='boost-other' and reason_text ~ 'sleep=AWAKE' and reason_text !~ 'suppressed \\(SLEEPING\\)' and cgm_mgdl is not null order by 1,2", (USERS,))
by = defaultdict(list)
for u, e, g, fd in cur.fetchall(): by[u].append((e, g, fd or 0.0))
for u in by: by[u] = np.array(by[u], float)
def at(arr, e, col, tol=400):
    ep = arr[:, 0]; i = np.searchsorted(ep, e); c = [j for j in (i - 1, i, i + 1) if 0 <= j < len(ep) and abs(ep[j] - e) < tol]
    return arr[min(c, key=lambda j: abs(ep[j] - e)), col] if c else np.nan
def dsum(arr, e0, e1): m = (arr[:, 0] >= e0) & (arr[:, 0] < e1); return arr[m, 2].sum()

meals = []
for u, arr in by.items():
    ep, g = arr[:, 0], arr[:, 1]; last = -1e9
    for i in range(9, len(ep)):
        if ep[i] - ep[i - 1] > 400: continue
        if g[i] > 140 and g[i - 1] <= 140 and np.nanmin(g[max(0, i - 6):i + 1]) <= 130 and (ep[i] - last) > 5400:
            e = ep[i]; last = e
            d15 = at(arr, e, 1) - at(arr, e - 900, 1)
            rise30 = max(0.0, 2.0 * d15)                 # cumulativeRise30min proxy = 2×(15-min delta)
            early = dsum(arr, e, e + 1800)               # actual delivered front-load t0-30
            nadir = np.nanmin([at(arr, e + m * 60, 1) for m in range(30, 151, 5)])
            bg0 = at(arr, e, 1)
            if any(np.isnan(x) for x in (d15, nadir, bg0)): continue
            meals.append(dict(u=u, rise30=rise30, early=early, crash=int(nadir < 70), bg0=bg0))
print(f"V6 meals: {len(meals)}\n")
print("Effect of retune (RISE_HI 50→90, FLOOR 0.40→0.15) on the confirm front-load multiplier,")
print("and the front-load insulin it would remove, by velocity band (× crash context):\n")
print(f"{'rise30 band':<16}{'n':>5}{'cur vf':>8}{'new vf':>8}{'mult chg':>9}{'crash%':>8}{'mean front-load U':>18}")
tot_cur = tot_new = 0.0
for lab, lo, hi in [('flat <20', 0, 20), ('modest 20-50', 20, 50), ('fast 50-90', 50, 90), ('steep >90', 90, 999)]:
    M = [m for m in meals if lo <= m['rise30'] < hi]
    if not M: continue
    cvf = np.mean([vfactor(m['rise30'], **CUR) for m in M]); nvf = np.mean([vfactor(m['rise30'], **NEW) for m in M])
    crash = 100 * np.mean([m['crash'] for m in M]); fl = np.mean([m['early'] for m in M])
    # front-load scales ~linearly with vf; retuned front-load ≈ current × new/cur
    for m in M:
        c = vfactor(m['rise30'], **CUR); nw = vfactor(m['rise30'], **NEW)
        tot_cur += m['early']; tot_new += m['early'] * (nw / c if c > 0 else 1)
    print(f"{lab:<16}{len(M):>5}{cvf:>8.2f}{nvf:>8.2f}{100*(nvf/cvf-1):>+8.0f}%{crash:>8.0f}{fl:>18.2f}")
print(f"\nTotal front-load insulin: current {tot_cur:.1f}U → retuned {tot_new:.1f}U  ({100*(tot_new/tot_cur-1):+.0f}%)")
print("Retune should CUT the flat/modest bands (high crash%, no plateau benefit) and PRESERVE the")
print("steep >90 band (the only band where front-loading lowered the plateau). Shadow-first + two-test bar.")
conn.close()
