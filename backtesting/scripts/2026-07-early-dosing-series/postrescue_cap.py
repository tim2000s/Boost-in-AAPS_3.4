#!/usr/bin/env python3
"""Backtest: suppress meal-state exemption from non-meal cap inside post-rescue window
(rolling 45-min min BG < 75). Cap: meal-state dose -> min(fd, v1_units) while in-window."""
import psycopg2, pandas as pd, numpy as np

conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
  user_id, ts_epoch, ts_utc, cgm_mgdl, boostv5_state AS state, boostv5_age AS age,
  boostv5_finaldose AS fd, v1_units, iob_iob AS iob
FROM boost_decisions WHERE boostv5_state IS NOT NULL
ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
""", conn).sort_values(["user_id","ts_epoch"]).reset_index(drop=True)

# rolling 45-min min BG (inclusive), forward low<70 within 3h, per user
min45 = np.full(len(df), np.nan); low3h = np.zeros(len(df), bool)
for uid, g in df.groupby("user_id", sort=False):
    ts=g.ts_epoch.values; bg=g.cgm_mgdl.values; idx=g.index.values; n=len(g)
    j=0
    for i in range(n):
        while ts[i]-ts[j] > 2700: j+=1
        min45[idx[i]] = np.nanmin(bg[j:i+1])
    for i in range(n):
        k=i+1
        while k<n and ts[k]-ts[i]<=10800: k+=1
        low3h[idx[i]] = (bg[i+1:k]<70).any()
df["min45"]=min45; df["low3h"]=low3h
df["in_window"] = df.min45 < 75
df["meal"] = df.state.isin(["CONFIRMED","COMMITTED"])
df["excess"] = (df.fd - df.v1_units.fillna(0)).clip(lower=0)

print("===== 1. EXPOSURE =====")
ex = df[df.meal & df.in_window]
print(f"meal-state cycles in post-rescue window: {len(ex)} (of {df.meal.sum()} meal-state cycles = {100*len(ex)/df.meal.sum():.1f}%)")
print("split:", ex.state.value_counts().to_dict())
print("per user:", ex.groupby("user_id").size().to_dict())
days = df.groupby("user_id").ts_epoch.agg(lambda s:(s.max()-s.min())/86400).sum()
print(f"({days:.0f} user-days -> {len(ex)/days:.2f} affected cycles/user-day)")

print("\n===== 2. INSULIN REMOVED =====")
print(f"total excess removed: {ex.excess.sum():.1f}U | cycles with excess>0: {(ex.excess>0).sum()} | dist of removed (excess>0):")
print(ex[ex.excess>0].excess.describe()[["25%","50%","75%","max"]].round(2).to_dict())
print("per user removed U:", ex.groupby("user_id").excess.sum().round(1).to_dict())

# ===== episodes: consecutive in-window meal cycles (gap<=30min) =====
eps=[]
for uid, g in df[df.meal & df.in_window].groupby("user_id"):
    g = g.sort_values("ts_epoch")
    brk = (g.ts_epoch.diff()>1800).cumsum()
    for _, ep in g.groupby(brk):
        end = ep.ts_epoch.iloc[-1]
        gu = df[df.user_id==uid]
        fw3 = gu[(gu.ts_epoch>end)&(gu.ts_epoch<=end+10800)]
        # window expiry after the FIRST cycle of episode
        after = gu[gu.ts_epoch>=ep.ts_epoch.iloc[0]]
        expi = after[~after.in_window]
        exp_ts = expi.ts_epoch.iloc[0] if len(expi) else end+2700
        # genuine meal: >180 for >60min within 3h AFTER expiry
        fwx = gu[(gu.ts_epoch>exp_ts)&(gu.ts_epoch<=exp_ts+10800)]
        m180 = 5*int((fwx.cgm_mgdl>180).sum())
        eps.append(dict(user=uid, start=ep.ts_utc.iloc[0], n=len(ep),
            has_confirm=bool((ep.state=="CONFIRMED").any()),
            fd_sum=ep.fd.sum(), v1_sum=ep.v1_units.fillna(0).sum(), removed=ep.excess.sum(),
            bg0=ep.cgm_mgdl.iloc[0], min45_0=ep.min45.iloc[0],
            second_low=bool((fw3.cgm_mgdl<70).any()) if len(fw3) else None,
            nadir3h=fw3.cgm_mgdl.min() if len(fw3) else np.nan,
            min180_after_expiry=m180, peak3h=fw3.cgm_mgdl.max() if len(fw3) else np.nan))
E = pd.DataFrame(eps)
print(f"\n===== 3. HARM SIDE (double-dip) ===== episodes: {len(E)}")
v = E[E.second_low.notna()]
print(f"followed by second low <70 within 3h: {v.second_low.sum()} ({100*v.second_low.mean():.0f}%)  [cohort base ~19%]")
print(f"removed U sitting in second-low episodes: {v[v.second_low].removed.sum():.1f}U of {v.removed.sum():.1f}U total ({100*v[v.second_low].removed.sum()/max(v.removed.sum(),1e-9):.0f}%)")
print(f"second-low episodes nadir: med {v[v.second_low].nadir3h.median():.0f}")
print("per-user second-low episodes:", v[v.second_low].groupby("user").size().to_dict())

print("\n===== 4. COST SIDE (real post-hypo meals) =====")
gm = v[v.min180_after_expiry > 60]
print(f"episodes looking like genuine meals (>180 for >60min after window expiry): {len(gm)} ({100*len(gm)/len(v):.0f}%)")
print(f"under-delivery the cap would cause them (in-window excess): total {gm.removed.sum():.1f}U, med {gm.removed.median():.2f}U, max {gm.removed.max():.2f}U")
print(f"their historical outcome WITH full V6 dosing: peak3h med {gm.peak3h.median():.0f}, second-low rate {100*gm.second_low.mean():.0f}%")
print(f"genuine-meal episodes that ALSO second-dipped: {(gm.second_low).sum()}")
both = v[(v.min180_after_expiry>60)]
print(f"overlap check — removed U: double-dip episodes {v[v.second_low].removed.sum():.1f}U vs genuine-meal episodes {gm.removed.sum():.1f}U (total pool {v.removed.sum():.1f}U)")
print("\nepisode table (removed>0.5U):")
cols=["user","start","n","has_confirm","fd_sum","v1_sum","removed","bg0","second_low","nadir3h","min180_after_expiry","peak3h"]
print(E[E.removed>0.5].sort_values("removed",ascending=False)[cols].head(20).round(2).to_string(index=False))
