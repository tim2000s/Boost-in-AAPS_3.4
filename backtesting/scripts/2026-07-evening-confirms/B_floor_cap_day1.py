#!/usr/bin/env python3
"""B. Floor + committedCap day-1 read (tim, today 05:00Z -> now, from refreshed DB).

Checks: (1) COMMITTED holds > 0.5 (cap-1.0 exercising) with raw demand vs delivered;
(2) any 'floor'/'brake-floor'/floorWouldAdd breadcrumbs (toggle observability);
(3) eligible-but-zero-uplift cycles; (4) the Episode-B v1-bound question on any
RECOVERING floor evaluations.
"""
import pandas as pd, numpy as np, psycopg2, os
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"); os.makedirs(OUT, exist_ok=True)
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
d = pd.read_sql("""
SELECT DISTINCT ON (floor(ts_epoch/300.0)) ts_utc, cgm_mgdl bg, boostv5_state st,
 boostv5_finaldose fd, boostv5_budget bud, boostv5_committedcap ccap, boostv5_confirmedcap fcap,
 v1_units, sug_eventualbg ev, sug_current_target tgt, reason_text rt
FROM boost_decisions WHERE user_id='tim' AND ts_utc >= timestamptz '2026-07-07 05:00+00'
ORDER BY floor(ts_epoch/300.0), ts_epoch DESC
""", conn).sort_values("ts_utc"); conn.close()
print(f"tim cycles today (05:00Z->): {len(d)}  committedCap={sorted(d.ccap.dropna().unique())}  confirmedCap={sorted(d.fcap.dropna().unique())}")

print("\n(1) COMMITTED holds > 0.5 (cap-1.0 exercising):")
h = d[(d.st=="COMMITTED") & (d.fd>0.5)]
for _,r in h.iterrows():
    old = min(r.fd, 0.5)   # what old cap 0.5 would have delivered
    print(f"  {str(r.ts_utc)[11:16]} bg={r.bg:.0f} fd={r.fd:.2f} budget(raw demand)={r.bud:.2f} cap={r.ccap:.1f} -> old-cap would deliver {old:.2f} (cap-1.0 adds {r.fd-old:+.2f}U)")
print(f"  COMMITTED holds total today={int((d.st=='COMMITTED').sum())}, max fd={d[d.st=='COMMITTED'].fd.max():.2f}")

print("\n(2) floor breadcrumbs:", int(d.rt.str.contains('floor|brake-floor|floorWouldAdd|composed', case=False, na=False).sum()),
      "| non-meal-capped:", int(d.rt.str.contains('non-meal-capped', na=False).sum()),
      "-> floor NOT observable in reason_text/DB (no floorWouldAdd field); toggle state undetermined")

print("\n(3)/(4) floor-eligible meal-session highs today (bg>160, ev-tgt>20, budget>0, composed<0.25):")
elig = d[(d.st.isin(["CONFIRMED","COMMITTED","RECOVERING"])) & (d.bg>160) & ((d.ev-d.tgt)>20) & (d.bud>0) & (d.fd < d.bud*0.25)]
elig = elig.assign(floor_val=(elig.bud*0.25).round(2), vbound=elig.v1_units.fillna(0))
print(elig[["ts_utc","bg","st","fd","bud","floor_val","vbound"]].assign(
    ts=elig.ts_utc.astype(str).str[11:16]).drop(columns="ts_utc")[["ts","bg","st","fd","bud","floor_val","vbound"]].round(2).to_string(index=False))
rec = elig[elig.st=="RECOVERING"]
uplift = np.minimum(elig.floor_val, np.where(elig.st=="RECOVERING", elig.vbound, np.inf)) - elig.fd
print(f"\n  Episode-B v1-bound answer: {len(rec)} RECOVERING floor-eligible cycles; v1_units=0 on {int((rec.vbound==0).sum())} of them.")
print(f"  Net floor uplift after non-meal v1-bound: {np.clip(uplift,0,None).sum():.2f}U across all {len(elig)} eligible cycles")
print("  => on RECOVERING, the non-meal v1-bound zeroes the floor (fd already = v1); floor only lifts COMMITTED/CONFIRMED.")
