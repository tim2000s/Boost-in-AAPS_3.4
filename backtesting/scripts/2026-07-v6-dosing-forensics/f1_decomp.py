#!/usr/bin/env python3
"""
FORENSIC 1 — WHERE and via WHICH stage does V6 add insulin over V1, on the meal-dosing window?

Same-cycle: boostv5_finaldose (V6 delivered) vs v1_units (V1 would-dose, same cycle). Decompose the
excess (V6 − V1) by context (BG, trend, IOB, state) and trace V6's own dose chain
(v1_units → velocityFactor → doseAfterCaps → doseAfterBrakes → finalDose) to see which stage sets it.
Telemetry-defined meal window (sleep=AWAKE, not suppressed). 5 users with V1 sleep telemetry.
"""
import numpy as np, psycopg2
from collections import defaultdict
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
USERS = ['tim', 'F', 'B', 'A', 'C']
MEAL = "reason_text ~ 'sleep=AWAKE' and reason_text !~ 'suppressed \\(SLEEPING\\)'"

# per-user CGM series for trend
cur.execute("select user_id,ts_epoch,cgm_mgdl from boost_decisions where user_id=any(%s) and cgm_mgdl is not null order by 1,2", (USERS,))
tmp = defaultdict(list)
for u, e, g in cur.fetchall(): tmp[u].append((e, g))
S = {u: (np.array([x[0] for x in v], float), np.array([x[1] for x in v], float)) for u, v in tmp.items()}
def bg_at(u, e, tol=400):
    ep, g = S[u]; i = np.searchsorted(ep, e)
    cand = [j for j in (i - 1, i, i + 1) if 0 <= j < len(ep) and abs(ep[j] - e) < tol]
    return g[min(cand, key=lambda j: abs(ep[j] - e))] if cand else np.nan

cur.execute(f"""select user_id,ts_epoch,cgm_mgdl,iob_iob,boostv5_state,boostv5_finaldose,v1_units,
   boostv5_velocityfactor,boostv5_doseaftercaps,boostv5_doseafterbrakes,boostv5_budget,boostv5_aggressionknob
   from boost_decisions where user_id=any(%s) and variant='boost-other' and {MEAL}
   and boostv5_finaldose is not null and v1_units is not null and cgm_mgdl is not null order by 1,2""", (USERS,))
R = []
for u, e, bg, iob, st, fd, v1, vf, dac, dab, bud, agg in cur.fetchall():
    d15 = bg - bg_at(u, e - 900)
    R.append(dict(u=u, bg=bg, iob=iob or 0, st=st or '?', fd=fd, v1=v1, exc=fd - v1, d15=d15,
                  vf=vf, dac=dac, dab=dab, bud=bud, agg=agg))
n = len(R)
print(f"meal-window V6 cycles: {n}\n")

def band(rs, key, edges, labels):
    print(f"  by {key}:")
    for i, lab in enumerate(labels):
        lo = -1e9 if i == 0 else edges[i - 1]; hi = edges[i] if i < len(edges) else 1e9
        s = [r for r in rs if lo <= r[key] < hi]
        if len(s) < 30: continue
        exc = np.mean([r['exc'] for r in s]); v6 = np.mean([r['fd'] for r in s]); v1 = np.mean([r['v1'] for r in s])
        outrate = np.mean([r['exc'] > 0.02 for r in s]) * 100
        print(f"    {lab:<16} n={len(s):>5}  V1 {v1:.3f}  V6 {v6:.3f}  excess {exc:+.3f}U  ({outrate:.0f}% cycles V6>V1)")

band(R, 'bg', [140, 180], ['<140', '140-180', '>180'])
band([r for r in R if not np.isnan(r['d15'])], 'd15', [-5, 5, 20], ['falling', 'flat', 'rising', 'fast-rise'])
band(R, 'iob', [1.0, 2.5], ['low<1', 'mid1-2.5', 'high>2.5'])
print("  by state:")
for st in ('IDLE', 'OBSERVING', 'CONFIRMED', 'COMMITTED', 'RECOVERING'):
    s = [r for r in R if r['st'] == st]
    if len(s) < 20: continue
    print(f"    {st:<12} n={len(s):>5}  excess {np.mean([r['exc'] for r in s]):+.3f}U  share of total excess {100*sum(r['exc'] for r in s)/max(sum(r['exc'] for r in R),1e-9):.0f}%")

# dose-chain: where in V6's own chain does the excess appear? (only cycles where V6 out-doses)
out = [r for r in R if r['exc'] > 0.02 and r['vf'] is not None]
print(f"\n  V6 dose chain on OUT-DOSE cycles (n={len(out)}): mean values")
for k, lab in [('v1', 'V1 base'), ('dac', 'after caps'), ('dab', 'after brakes'), ('fd', 'final')]:
    vals = [r[k] for r in out if r[k] is not None]
    if vals: print(f"    {lab:<14} {np.mean(vals):.3f}U")
vf = [r['vf'] for r in out if r['vf'] is not None]; agg = [r['agg'] for r in out if r['agg'] is not None]
print(f"    velocityFactor {np.mean(vf):.2f}   aggressionKnob {np.mean(agg):.2f}")
print("\nREAD: the context with the largest positive excess is where V6 front-loads over V1; if final≈after-brakes")
print("and velocityFactor/aggression are elevated, the excess is the aggression/velocity amplification, not caps.")
conn.close()
