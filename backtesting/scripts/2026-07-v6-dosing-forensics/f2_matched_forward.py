#!/usr/bin/env python3
"""
FORENSIC 2 — the mechanism test. For MATCHED pre-dose states, does V6 dose more AND produce a worse
forward glucose trajectory (more variance / more overshoot) than V1?

Uses the transition window (18 Jun–12 Jul) where the same 5 users ran BOTH algorithms — seasonality
held. For each meal-window cycle: pre-state (BG, 15-min trend, IOB), the acting algorithm, the
delivered dose, and the forward CGM at +30/60/90/120 min. Match V1 vs V6 cycles on (BG band × trend ×
IOB tercile); within matched cells compare dose and forward-trajectory metrics. This is the closest to
causal without a simulator: same people, same weeks, same pre-state — only the algorithm differs.
"""
import numpy as np, psycopg2
from collections import defaultdict
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
USERS = ['tim', 'F', 'B', 'A', 'C']
MEAL = "reason_text ~ 'sleep=AWAKE' and reason_text !~ 'suppressed \\(SLEEPING\\)'"
WIN = "ts_utc at time zone 'Europe/London' between '2026-06-18' and '2026-07-12'"

cur.execute("select user_id,ts_epoch,cgm_mgdl from boost_decisions where user_id=any(%s) and cgm_mgdl is not null order by 1,2", (USERS,))
tmp = defaultdict(list)
for u, e, g in cur.fetchall(): tmp[u].append((e, g))
S = {u: (np.array([x[0] for x in v], float), np.array([x[1] for x in v], float)) for u, v in tmp.items()}
def bg_at(u, e, tol=400):
    ep, g = S[u]; i = np.searchsorted(ep, e)
    cand = [j for j in (i - 1, i, i + 1) if 0 <= j < len(ep) and abs(ep[j] - e) < tol]
    return g[min(cand, key=lambda j: abs(ep[j] - e))] if cand else np.nan

cur.execute(f"""select user_id,ts_epoch,cgm_mgdl,iob_iob,
   case when variant='boost-other' then 'V6' else 'V1' end alg,
   case when variant='boost-other' then boostv5_finaldose else v1_units end dose
   from boost_decisions where user_id=any(%s) and (variant='boost-other' or variant in ('v1','v1-silent'))
   and {MEAL} and {WIN} and cgm_mgdl is not null order by 1,2""", (USERS,))
R = []
for u, e, bg, iob, alg, dose in cur.fetchall():
    d15 = bg - bg_at(u, e - 900)
    fwd = np.array([bg_at(u, e + h * 60) for h in (30, 60, 90, 120)])
    if np.isnan(d15) or np.isnan(fwd).any(): continue
    R.append(dict(u=u, alg=alg, bg=bg, iob=iob or 0, d15=d15, dose=dose or 0,
                  nadir=fwd.min(), peak=fwd.max(), fwdrange=fwd.max() - fwd.min(),
                  dip=int(fwd.min() < 70), over=int(fwd.max() > 180), swing=int(fwd.max() - fwd.min() > 60)))
print(f"matched-window cycles with full forward trace: {len(R)}  (V1 {sum(r['alg']=='V1' for r in R)}, V6 {sum(r['alg']=='V6' for r in R)})")

it = np.percentile([r['iob'] for r in R], [33, 66])
bgb = lambda b: '<140' if b < 140 else ('140-180' if b < 180 else '>180')
db = lambda d: 'fall' if d < -5 else ('flat' if d < 5 else 'rise')
ib = lambda i: 'loIOB' if i < it[0] else ('midIOB' if i < it[1] else 'hiIOB')
for r in R: r['cell'] = f"{bgb(r['bg'])},{db(r['d15'])},{ib(r['iob'])}"
cells = defaultdict(lambda: {'V1': [], 'V6': []})
for r in R: cells[r['cell']][r['alg']].append(r)

print(f"\n{'cell (bg,trend,iob)':<22}{'nV1':>5}{'nV6':>5}{'doseV1':>8}{'doseV6':>8}{'rangeV1':>9}{'rangeV6':>9}{'over%V1':>9}{'over%V6':>9}{'dip%V1':>8}{'dip%V6':>8}")
tot = {'V1': defaultdict(list), 'V6': defaultdict(list)}
for cell, d in sorted(cells.items()):
    if len(d['V1']) < 40 or len(d['V6']) < 40: continue
    def m(alg, k): return np.mean([r[k] for r in d[alg]])
    print(f"{cell:<22}{len(d['V1']):>5}{len(d['V6']):>5}{m('V1','dose'):>8.3f}{m('V6','dose'):>8.3f}"
          f"{m('V1','fwdrange'):>9.0f}{m('V6','fwdrange'):>9.0f}{100*m('V1','over'):>9.0f}{100*m('V6','over'):>9.0f}"
          f"{100*m('V1','dip'):>8.0f}{100*m('V6','dip'):>8.0f}")
    for alg in ('V1', 'V6'):
        for k in ('dose', 'fwdrange', 'over', 'dip', 'swing'): tot[alg][k].append(m(alg, k))

print("\n=== mean over matched cells (equal cell weight) ===")
for k, lab in [('dose', 'delivered dose U'), ('fwdrange', 'forward BG range mg/dL'), ('over', 'forward >180 %'),
               ('dip', 'forward <70 %'), ('swing', 'forward swing>60 %')]:
    v1, v6 = np.mean(tot['V1'][k]), np.mean(tot['V6'][k])
    sc = 100 if k in ('over', 'dip', 'swing') else 1
    print(f"  {lab:<26} V1 {v1*sc:7.2f}   V6 {v6*sc:7.2f}   Δ {(v6-v1)*sc:+7.2f}")
print("\nREAD: if within matched pre-states V6 dose > V1 dose AND V6 forward-range/over%/swing% > V1,")
print("V6's extra meal insulin is CAUSING more downstream excursion/variance — not tighter control.")
conn.close()
