#!/usr/bin/env python3
"""
FOUNDATION 1 — measure V6's post-meal recovery DIRECTLY (absolute, no V1, no flash confound).
The regression mechanism is "V6 leaves glucose parked at 143-150 for hours after a meal". Test it as
a property of V6's own current behaviour: detect meal onsets, follow the recovery, report where glucose
sits at +2-3h. If V6 genuinely plateaus high, the problem is real regardless of what V1 did. Per user.
Usage: python3 ff1_recovery.py <user>
"""
import sys, json, numpy as np, psycopg2
U = sys.argv[1]
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
cur.execute("""select ts_epoch,cgm_mgdl from boost_decisions where user_id=%s and variant='boost-other'
   and cgm_mgdl is not null order by ts_epoch""", (U,))
a = np.array(cur.fetchall(), float); EP, G = a[:, 0], a[:, 1]
def bg(e, tol=400):
    i = np.searchsorted(EP, e); c = [j for j in (i - 1, i, i + 1) if 0 <= j < len(EP) and abs(EP[j] - e) < tol]
    return G[min(c, key=lambda j: abs(EP[j] - e))] if c else np.nan
onsets = []; last = -1e9
for i in range(6, len(EP)):
    if EP[i] - EP[i - 1] > 400: continue
    if G[i] > 140 and G[i - 1] <= 140 and np.nanmin(G[max(0, i - 6):i + 1]) <= 130 and (EP[i] - last) > 5400:
        onsets.append(EP[i]); last = EP[i]
rec = []
for e0 in onsets:
    plateau = np.nanmean([bg(e0 + m * 60) for m in (120, 150, 180)])
    b180 = bg(e0 + 180 * 60); peak = np.nanmax([bg(e0 + m * 60) for m in range(0, 41, 5)])
    if np.isnan(plateau) or np.isnan(peak): continue
    rec.append((peak, plateau, b180))
rec = np.array(rec)
if len(rec):
    plat = rec[:, 1]
    out = dict(user=U, n=len(rec), median_peak=float(np.median(rec[:, 0])),
               median_plateau=float(np.median(plat)),
               pct_plateau_over140=float(100 * np.mean(plat > 140)),   # out of tight range at recovery
               pct_plateau_over160=float(100 * np.mean(plat > 160)),
               pct_recovered_under120=float(100 * np.mean(plat < 120)),
               plateau_p25=float(np.percentile(plat, 25)), plateau_p75=float(np.percentile(plat, 75)))
    json.dump(out, open(f"ff1_{U}.json", "w"))
    print(f"{U}: {len(rec)} meals | median peak {out['median_peak']:.0f} -> recovery plateau {out['median_plateau']:.0f}"
          f" | still >140: {out['pct_plateau_over140']:.0f}% | >160: {out['pct_plateau_over160']:.0f}% | recovered <120: {out['pct_recovered_under120']:.0f}%")
else:
    print(f"{U}: no meals")
conn.close()
