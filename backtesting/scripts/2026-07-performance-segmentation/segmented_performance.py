#!/usr/bin/env python3
"""Performance review, re-cut by post-meal exercise exposure (2026-07-27).

The headline cohort numbers mix three very different regimes. This separates them so the loop's
actual meal-handling quality can be judged apart from the exercise confound (which the
2026-07-postmeal-exercise-mechanism study showed is a carb-counterweight failure, not the loop's
dosing fault).

Segments (per user, 30 days):
  BACKGROUND        — not within 3h of a detected meal (fasting / overnight).
  POST-MEAL, NO EX  — within 3h of an unannounced-meal confirmation (V5 CONFIRMED, COB=0) with
                      NO activity (steps > 2x per-user baseline) in the first 2h. The clean
                      fully-closed meal-handling test.
  POST-MEAL, WITH EX— same window but activity present in the first 2h.
  ALL minus EX-postmeal — the performance review with exercise-affected post-meal time removed.

User with no step feed excluded from the split (reported unsplit).
"""
import numpy as np
import pandas as pd
import psycopg2

pd.set_option('display.width', 260)
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
d = pd.read_sql("""
    SELECT user_id AS user, ts_epoch, cgm_mgdl AS bg, steps_30m AS steps,
           boostv5_state AS st, sug_cob AS cob
    FROM boost_decisions WHERE ts_utc >= now() - interval '30 days' AND cgm_mgdl IS NOT NULL
    ORDER BY user_id, ts_epoch
""", conn).drop_duplicates(subset=['user', 'ts_epoch']).reset_index(drop=True)

d['pm'] = False; d['pmx'] = False; d['has_steps'] = False
for uid, g in d.groupby('user'):
    idx = g.index; ts = g.ts_epoch.values
    base = g.steps[g.steps > 0].median() if (g.steps > 0).any() else np.nan
    hs = not np.isnan(base); d.loc[idx, 'has_steps'] = hs
    st = g.st.values; cob = np.nan_to_num(g.cob.values); steps = g.steps.values
    onset = np.where((st == 'CONFIRMED') &
                     (np.concatenate([['x'], st[:-1]]) != 'CONFIRMED') & (cob == 0))[0]
    pm = np.zeros(len(g), bool); pmx = np.zeros(len(g), bool)
    for o in onset:
        win = (ts >= ts[o]) & (ts <= ts[o] + 180 * 60); pm |= win
        if hs and ((ts >= ts[o]) & (ts <= ts[o] + 120 * 60) & (steps > 2 * base)).any():
            pmx |= win
    d.loc[idx, 'pm'] = pm; d.loc[idx, 'pmx'] = pmx


def stats(b):
    return dict(mmol=b.mean() / 18.016,
                TIR=100 * ((b >= 70) & (b <= 180)).mean(),
                TING=100 * ((b >= 63) & (b <= 140)).mean(),
                TBR70=100 * (b < 70).mean(), TBR54=100 * (b < 54).mean(),
                TAR180=100 * (b > 180).mean())


S = d[d.has_steps]; tot = len(S)
seg = {
    'ALL time': S.bg,
    'ALL minus exercise-postmeal': S[~S.pmx].bg,
    'Post-meal, NO exercise': S[S.pm & ~S.pmx].bg,
    'Post-meal, WITH exercise': S[S.pmx].bg,
    'Background (non-post-meal)': S[~S.pm].bg,
}
rows = {}
for name, b in seg.items():
    r = stats(b); r['%time'] = 100 * len(b) / tot; rows[name] = r
T = pd.DataFrame(rows).T[['%time', 'mmol', 'TIR', 'TING', 'TBR70', 'TBR54', 'TAR180']]
print("=== COHORT (8 users w/ step feed, 30d) ===")
print(T.round(1).to_string())

print("\n=== PER-USER: background | post-meal no-exercise | post-meal with-exercise ===")
print("  user │  bg:TIR TING TBR TAR │  pm-noEx:TIR TING TBR TAR │  pm-Ex:TIR TING TBR TAR")
for uid, g in S.groupby('user'):
    def row(b):
        s = stats(b)
        return f"{s['TIR']:4.0f} {s['TING']:4.0f} {s['TBR70']:4.1f} {s['TAR180']:5.1f}" if len(b) > 30 else "  –    –    –    – "
    print(f"   {uid:4}│  {row(g[~g.pm].bg)}   │   {row(g[g.pm & ~g.pmx].bg)}    │  {row(g[g.pmx].bg)}")

for uid, g in d[~d.has_steps].groupby('user'):
    s = stats(g.bg); sp = stats(g[g.pm].bg)
    print(f"\n  {uid} (no step feed): overall TIR {s['TIR']:.0f} TING {s['TING']:.0f} "
          f"TBR {s['TBR70']:.1f} | post-meal TIR {sp['TIR']:.0f} TING {sp['TING']:.0f} TAR180 {sp['TAR180']:.0f}")
