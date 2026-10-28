#!/usr/bin/env python3
"""
FORENSIC 3 — the shots that go wrong. Isolate V6's meaningful meal-window SMBs (finalDose over a
threshold), split by state, and follow the forward trajectory: does the shot land well (glucose
settles into tight range) or badly (overshoots down / rebounds up / crashes)? Compare each shot's
size to what V1 would have given the SAME cycle (v1_units) to price the over-treatment.

Targets the CONFIRMED/COMMITTED front-loads specifically — the fast-carb CONFIRMED-shot crash
hypothesis (memory: V6 over-treats modest rises, crashes 20–39%). Transition window, 5 users.
"""
import numpy as np, psycopg2
from collections import defaultdict
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
USERS = ['tim', 'F', 'B', 'A', 'C']
MEAL = "reason_text ~ 'sleep=AWAKE' and reason_text !~ 'suppressed \\(SLEEPING\\)'"

cur.execute("select user_id,ts_epoch,cgm_mgdl from boost_decisions where user_id=any(%s) and cgm_mgdl is not null order by 1,2", (USERS,))
tmp = defaultdict(list)
for u, e, g in cur.fetchall(): tmp[u].append((e, g))
S = {u: (np.array([x[0] for x in v], float), np.array([x[1] for x in v], float)) for u, v in tmp.items()}
def bg_at(u, e, tol=400):
    ep, g = S[u]; i = np.searchsorted(ep, e)
    cand = [j for j in (i - 1, i, i + 1) if 0 <= j < len(ep) and abs(ep[j] - e) < tol]
    return g[min(cand, key=lambda j: abs(ep[j] - e))] if cand else np.nan
def fwd_min(u, e, h=150): return np.nanmin([bg_at(u, e + m * 60) for m in range(20, h + 1, 5)])
def fwd_at(u, e, m): return bg_at(u, e + m * 60)

# V6 meal-window shots
cur.execute(f"""select user_id,ts_epoch,cgm_mgdl,iob_iob,boostv5_state,boostv5_finaldose,v1_units
   from boost_decisions where user_id=any(%s) and variant='boost-other' and {MEAL}
   and boostv5_finaldose > 0.15 and cgm_mgdl is not null order by 1,2""", (USERS,))
shots = []
for u, e, bg, iob, st, fd, v1 in cur.fetchall():
    d15 = bg - bg_at(u, e - 900)
    nadir = fwd_min(u, e); b120 = fwd_at(u, e, 120)
    if np.isnan(nadir) or np.isnan(d15): continue
    over = fd - (v1 or 0)
    shots.append(dict(u=u, st=st or '?', bg=bg, iob=iob or 0, d15=d15, fd=fd, v1=v1 or 0, over=over,
                      nadir=nadir, b120=b120,
                      crash=int(nadir < 70), deep=int(nadir < 54),
                      rebound=int(not np.isnan(b120) and nadir < 90 and b120 > 160)))
print(f"V6 meal-window shots >0.15U: {len(shots)}\n")

def summ(label, S):
    if len(S) < 15:
        print(f"  {label:<26} n={len(S)} (thin)"); return
    print(f"  {label:<26} n={len(S):>4}  shot {np.mean([s['fd'] for s in S]):.2f}U  "
          f"over-V1 {np.mean([s['over'] for s in S]):+.2f}U  atBG {np.mean([s['bg'] for s in S]):.0f}  "
          f"Δ15 {np.mean([s['d15'] for s in S]):+.0f}  |  nadir {np.mean([s['nadir'] for s in S]):.0f}  "
          f"crash<70 {100*np.mean([s['crash'] for s in S]):.0f}%  deep<54 {100*np.mean([s['deep'] for s in S]):.0f}%  "
          f"rebound {100*np.mean([s['rebound'] for s in S]):.0f}%")

print("By V6 state:")
for st in ('OBSERVING', 'CONFIRMED', 'COMMITTED', 'IDLE', 'RECOVERING'):
    summ(st, [s for s in shots if s['st'] == st])
print("\nBy pre-shot context:")
summ("modest rise (Δ15 5-25)", [s for s in shots if 5 <= s['d15'] < 25])
summ("sharp rise (Δ15 >=25)", [s for s in shots if s['d15'] >= 25])
summ("shot at BG<150", [s for s in shots if s['bg'] < 150])
summ("shot at IOB>2.5U", [s for s in shots if s['iob'] > 2.5])
summ("V6 over-doses V1 >0.3U", [s for s in shots if s['over'] > 0.3])
summ("V6 ~= V1 (|over|<0.1)", [s for s in shots if abs(s['over']) < 0.1])
print("\nREAD: if the shots that CRASH (or rebound) cluster in a state/context where V6 over-doses V1")
print("most (big over-V1, modest rise, BG<150, or high IOB), that names the over-treatment to fix.")
conn.close()
