#!/usr/bin/env python3
"""
FOUNDATION 2 — anchor the "22% crash" rate. Is a confirm-shot's forward crash rate anomalous, or just
what post-meal glucose does? Compare, AT MATCHED CONTEXT (low IOB <1.5, modest rise 15-80 mg/dL/30min):
cycles where V6 fired a real shot (>0.3U) vs cycles where it barely dosed (<0.1U). Plus the ambient
base rate (any cycle → nadir<70 in 2.5h). If the shot cycles crash much more at matched context, the
shot is implicated; if similar, 22% is baseline dipping. Pooled across users (rates, not U).
Usage: python3 ff2_crash_anchor.py <user>  (writes ff2_<user>.json)
"""
import sys, json, numpy as np, psycopg2
U = sys.argv[1]
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
cur.execute("""select ts_epoch,cgm_mgdl,iob_iob,boostv5_finaldose,boostv5_state from boost_decisions
   where user_id=%s and variant='boost-other' and cgm_mgdl is not null order by ts_epoch""", (U,))
r = cur.fetchall()
EP = np.array([x[0] for x in r], float); G = np.array([x[1] for x in r], float)
IOB = np.array([x[2] if x[2] is not None else np.nan for x in r], float)
FD = np.array([x[3] if x[3] is not None else 0.0 for x in r], float)
ST = [x[4] for x in r]
def bg(e, tol=400):
    i = np.searchsorted(EP, e); c = [j for j in (i - 1, i, i + 1) if 0 <= j < len(EP) and abs(EP[j] - e) < tol]
    return G[min(c, key=lambda j: abs(EP[j] - e))] if c else np.nan
def fwd_nadir(e): return np.nanmin([bg(e + m * 60) for m in range(20, 151, 5)])
buckets = dict(confirm=[], shot_lowiob_modest=[], noshot_lowiob_modest=[], ambient=[])
for i in range(3, len(EP) - 30):
    if EP[i] - EP[i - 3] > 700: continue
    rise = max(0.0, 2.0 * (G[i] - G[i - 3]))
    na = fwd_nadir(EP[i])
    if np.isnan(na): continue
    crash = int(na < 70); deep = int(na < 54)
    buckets['ambient'].append((crash, deep))
    lowiob = (not np.isnan(IOB[i])) and IOB[i] < 1.5
    modest = 15 <= rise <= 80
    if ST[i] == 'CONFIRMED' and FD[i] > 0.3: buckets['confirm'].append((crash, deep))
    if lowiob and modest and FD[i] > 0.3: buckets['shot_lowiob_modest'].append((crash, deep))
    if lowiob and modest and FD[i] < 0.1: buckets['noshot_lowiob_modest'].append((crash, deep))
json.dump({k: [len(v), sum(c for c, d in v), sum(d for c, d in v)] for k, v in buckets.items()},
          open(f"ff2_{U}.json", "w"))
def rate(v): return (100 * sum(c for c, d in v) / len(v)) if v else float('nan')
print(f"{U}: ambient crash {rate(buckets['ambient']):.0f}% (n={len(buckets['ambient'])}) | "
      f"confirm-shot {rate(buckets['confirm']):.0f}% | lowIOB+modest: SHOT {rate(buckets['shot_lowiob_modest']):.0f}%"
      f"(n={len(buckets['shot_lowiob_modest'])}) vs NO-SHOT {rate(buckets['noshot_lowiob_modest']):.0f}%(n={len(buckets['noshot_lowiob_modest'])})")
conn.close()
