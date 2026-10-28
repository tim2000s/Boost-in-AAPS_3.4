#!/usr/bin/env python3
"""WHY does post-meal exercise raise hypo risk? Dose vs carb-counterweight. (2026-07-27)

The fully-closed-loop review found meal+exercise lows at 23% vs 14% and implied the naive
mechanism — "meal-time insulin lands into a sensitised body" (a DOSE / stacking story). This
tests it. If the crash is dose-driven, crashers should carry MORE insulin on board; if it is
carb-counterweight-driven (exercise's largely insulin-independent glucose uptake landing when
the meal's carbohydrate flux is thin), crashers should carry LESS.

Events: unannounced-meal confirmations (V5 CONFIRMED entry, COB=0) followed by activity
(steps > 2x per-user baseline) within 2h. Outcome: BG < 70 within 3h. User with no step feed
excluded. Discriminators: IOB at exercise onset, meal SMB burst, BG at exercise onset, crash
rate by IOB tertile.

Identification caveat: low IOB is partly a CONSEQUENCE of the loop zero-temping on an already
falling BG, so "low IOB -> crash" and "already-falling -> crash" cannot be fully separated
observationally. Both readings converge on the same conclusion (the driver is not insulin
excess; the loop's insulin lever is already spent), which is what the report states.
"""
import numpy as np
import pandas as pd
import psycopg2

conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
d = pd.read_sql("""
    SELECT user_id AS user, ts_epoch, cgm_mgdl AS bg, iob_iob AS iob, reason_dev AS dev,
           boostv5_finaldose AS smb, steps_30m AS steps, boostv5_state AS st, sug_cob AS cob
    FROM boost_decisions WHERE ts_utc >= now() - interval '50 days' AND cgm_mgdl IS NOT NULL
      AND user_id <> 'G'
    ORDER BY user_id, ts_epoch
""", conn).drop_duplicates(subset=['user', 'ts_epoch']).reset_index(drop=True)
d['delta'] = d.groupby('user').bg.diff()

ev = []
for uid, g in d.groupby('user'):
    g = g.reset_index(drop=True)
    base = g.steps[g.steps > 0].median() if (g.steps > 0).any() else np.nan
    if np.isnan(base):
        continue
    conf = g.index[(g.st == 'CONFIRMED') & (g.st.shift() != 'CONFIRMED') & (np.nan_to_num(g.cob) == 0)]
    for i in conf:
        post = g.iloc[i:min(len(g), i + 24)]
        fw = g.iloc[i:min(len(g), i + 36)]
        if len(fw) < 18:
            continue
        exd = post[post.steps > 2 * base]
        if len(exd) == 0:
            continue
        j = exd.index[0]
        ev.append(dict(user=uid, low=int(fw.bg.min() < 70),
                       iob_ex=g.iob[j], burst=post.smb.fillna(0).iloc[:6].sum(),
                       bg_ex=g.bg[j], lag=(g.ts_epoch[j] - g.ts_epoch[i]) / 60))
E = pd.DataFrame(ev)
lo, hi = E[E.low == 1], E[E.low == 0]
q = lambda s: f"med {s.dropna().median():.2f} [{s.dropna().quantile(.25):.2f},{s.dropna().quantile(.75):.2f}]"

print(f"meal+exercise events: {len(E)}, with a low <70 within 3h: {len(lo)} ({100*E.low.mean():.0f}%)\n")
print("DOSE story test (crashers should carry MORE insulin if dose-driven):")
print(f"  IOB at exercise onset — crashed {q(lo.iob_ex)} | didn't {q(hi.iob_ex)}")
print(f"  meal SMB burst        — crashed {q(lo.burst)} | didn't {q(hi.burst)}")
print(f"  BG at exercise onset  — crashed {q(lo.bg_ex)} | didn't {q(hi.bg_ex)}\n")
E['ter'] = pd.qcut(E.iob_ex.rank(method='first'), 3, labels=['low', 'mid', 'high'])
print("Crash rate by IOB-at-exercise tertile (dose-driven => rises with IOB; observed => falls):")
for t in ['low', 'mid', 'high']:
    s = E[E.ter == t]
    print(f"  IOB {t:4} (median {s.iob_ex.median():.2f}U): crash {100*s.low.mean():.0f}%  (n={len(s)})")
