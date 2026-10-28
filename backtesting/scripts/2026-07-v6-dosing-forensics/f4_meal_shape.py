#!/usr/bin/env python3
"""
FORENSIC 4 (tiebreaker) — the meal-response SHAPE, which matching-on-BG hides.

Matching pre-state (F2) can conditional-away the very upward drift that IS the regression. So instead:
detect meal-like excursion ONSETS from CGM, tag each by the acting algorithm at onset (V1 vs V6),
align them, and average the BG path from t−30 to t+180 min. If V6's meal peaks are higher/broader or
its recovery overshoots, that's a genuine path-level V6 effect on meals; if the curves overlie, the
outcome gap is more likely the residual (flash-date/settings) confound. Transition window, 5 users,
meal-dosing-active only.
"""
import numpy as np, psycopg2
from collections import defaultdict
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
USERS = ['tim', 'F', 'B', 'A', 'C']
WIN = "ts_utc at time zone 'Europe/London' between '2026-06-18' and '2026-07-12'"

cur.execute("select user_id,ts_epoch,cgm_mgdl from boost_decisions where user_id=any(%s) and cgm_mgdl is not null order by 1,2", (USERS,))
tmp = defaultdict(list)
for u, e, g in cur.fetchall(): tmp[u].append((e, g))
S = {u: (np.array([x[0] for x in v], float), np.array([x[1] for x in v], float)) for u, v in tmp.items()}
def bg_at(u, e, tol=400):
    ep, g = S[u]; i = np.searchsorted(ep, e)
    cand = [j for j in (i - 1, i, i + 1) if 0 <= j < len(ep) and abs(ep[j] - e) < tol]
    return g[min(cand, key=lambda j: abs(ep[j] - e))] if cand else np.nan

# acting algorithm per cycle (meal window only), for tagging onsets
cur.execute(f"""select user_id,ts_epoch, case when variant='boost-other' then 'V6' else 'V1' end alg
   from boost_decisions where user_id=any(%s) and (variant='boost-other' or variant in ('v1','v1-silent'))
   and reason_text ~ 'sleep=AWAKE' and reason_text !~ 'suppressed \\(SLEEPING\\)' and {WIN} order by 1,2""", (USERS,))
algser = defaultdict(list)
for u, e, a in cur.fetchall(): algser[u].append((e, a))
ALG = {u: (np.array([x[0] for x in v], float), np.array([x[1] for x in v], object)) for u, v in algser.items()}
def alg_at(u, e, tol=400):
    ep, a = ALG[u]; i = np.searchsorted(ep, e)
    cand = [j for j in (i - 1, i, i + 1) if 0 <= j < len(ep) and abs(ep[j] - e) < tol]
    return a[min(cand, key=lambda j: abs(ep[j] - e))] if cand else None

# detect onsets: BG crosses upward through 140 having been <=130 in the prior 30 min, deduped 90 min
grid = np.arange(-30, 181, 5)
curves = {'V1': [], 'V6': []}
for u in USERS:
    ep, g = S[u]
    last = -1e9
    for i in range(6, len(ep)):
        if ep[i] - ep[i - 1] > 400: continue
        if g[i] > 140 and g[i - 1] <= 140 and np.nanmin(g[max(0, i - 6):i + 1]) <= 130 and (ep[i] - last) > 5400:
            a = alg_at(u, ep[i])
            if a is None: continue
            traj = np.array([bg_at(u, ep[i] + int(m) * 60) for m in grid])
            if np.isnan(traj).sum() > 6: continue
            curves[a].append(traj); last = ep[i]

print(f"meal onsets: V1 {len(curves['V1'])}, V6 {len(curves['V6'])}\n")
def stat(a):
    M = np.nanmean(np.array(curves[a]), axis=0)
    peak = np.nanmax(M); tpk = grid[np.nanargmax(M)]; base = M[6]  # t=0 index (grid starts -30, step5 -> idx6=t0)
    end = M[-1]; trough_after = np.nanmin(M[np.nanargmax(M):])
    return M, peak, tpk, base, end, trough_after
print(f"{'algo':<5}{'BG@onset':>9}{'peak':>7}{'t-peak':>8}{'BG@+180':>9}{'post-peak trough':>18}")
for a in ('V1', 'V6'):
    M, peak, tpk, base, end, tr = stat(a)
    print(f"{a:<5}{base:>9.0f}{peak:>7.0f}{tpk:>7.0f}m{end:>9.0f}{tr:>18.0f}")
print("\nAveraged trajectory (mg/dL) at t = -30..+180 (5-min steps):")
for a in ('V1', 'V6'):
    M = np.nanmean(np.array(curves[a]), axis=0)
    s = "  ".join(f"{grid[i]:+d}:{M[i]:.0f}" for i in range(0, len(grid), 3))
    print(f"  {a}: {s}")
# per-user peak to control for cohort mix
print("\nPer-user mean meal peak (V1 vs V6):")
for u in USERS:
    pu = {'V1': [], 'V6': []}
    ep, g = S[u]; last = -1e9
    for i in range(6, len(ep)):
        if ep[i]-ep[i-1] > 400: continue
        if g[i] > 140 and g[i-1] <= 140 and np.nanmin(g[max(0,i-6):i+1]) <= 130 and (ep[i]-last) > 5400:
            a = alg_at(u, ep[i]);
            if a is None: continue
            tr = np.array([bg_at(u, ep[i]+int(m)*60) for m in grid])
            if np.isnan(tr).sum() > 6: continue
            pu[a].append(np.nanmax(tr)); last = ep[i]
    if len(pu['V1']) >= 5 and len(pu['V6']) >= 5:
        print(f"  {u:<4} V1 peak {np.mean(pu['V1']):.0f} (n={len(pu['V1'])})   V6 peak {np.mean(pu['V6']):.0f} (n={len(pu['V6'])})   Δ {np.mean(pu['V6'])-np.mean(pu['V1']):+.0f}")
conn.close()
