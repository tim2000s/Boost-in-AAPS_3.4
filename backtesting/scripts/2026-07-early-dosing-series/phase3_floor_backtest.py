#!/usr/bin/env python3
"""Lever 1: composed Phase-3 floor F on meal-session cycles (BG>160, ev>tgt+20, awake, no post-rescue).
Lever 2: tim committedCap raise 0.5->1.0/1.5. Capped-era discipline."""
import psycopg2, pandas as pd, numpy as np

conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
  user_id, ts_epoch, ts_utc, cgm_mgdl AS bg, boostv5_state AS state,
  boostv5_finaldose AS fd, boostv5_budget AS budget, v1_units,
  sug_eventualbg AS ev, sug_current_target AS tgt, iob_iob AS iob, tdd
FROM boost_decisions WHERE boostv5_state IS NOT NULL
ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
""", conn).sort_values(["user_id","ts_epoch"]).reset_index(drop=True)
df["date"] = pd.to_datetime(df.ts_utc, utc=True, format="mixed").dt.date
df["hour"] = (pd.to_datetime(df.ts_utc, utc=True, format="mixed").dt.hour+1)%24
df["dt"]=df.groupby("user_id").ts_epoch.diff()/60
df["delta5"]=df.groupby("user_id").bg.diff()/df.dt*5
df.loc[(df.dt>7.6)|(df.dt<2.0),"delta5"]=np.nan
min45=np.full(len(df),np.nan); low3h=np.zeros(len(df),bool)
for uid,g in df.groupby("user_id",sort=False):
    ts=g.ts_epoch.values; bg=g.bg.values; idx=g.index.values; n=len(g); j=0
    for i in range(n):
        while ts[i]-ts[j]>2700: j+=1
        min45[idx[i]]=np.nanmin(bg[j:i+1])
    for i in range(n):
        k=i+1
        while k<n and ts[k]-ts[i]<=10800: k+=1
        low3h[idx[i]]=(bg[i+1:k]<70).any()
df["min45"]=min45; df["low3h"]=low3h

ERAS = {"tim":[("2026-06-01",.25),("2026-06-12",.5),("2026-06-14",.4),("2026-07-02",.5)],
 "A":[("2026-06-17",.25),("2026-07-01",.5)],"B":[("2026-06-18",.25),("2026-07-01",.5),("2026-07-02",.6)],
 "C":[("2026-06-19",.25)],"D":[("2026-06-17",.25)],"E":[("2026-06-17",.25),("2026-06-30",.5)],
 "F":[("2026-06-18",.25),("2026-06-29",.5)]}
def op_cap(u,d):
    c=None
    for s,v in ERAS.get(u,[]):
        if d>=pd.to_datetime(s).date(): c=v
    return c
df["cap"]=[op_cap(u,d) for u,d in zip(df.user_id,df.date)]
ce = df[df.cap.notna()].copy()
udays = ce.groupby("user_id").date.nunique().sum()
print(f"capped-era cycles {len(ce)}, user-days {udays}, span -> {ce.date.max()}")

# eligibility for the floor
ce["mealsess"] = ce.state.isin(["CONFIRMED","COMMITTED","RECOVERING"])
ce["elig"] = ce.mealsess & (ce.bg>160) & ((ce.ev-ce.tgt)>20) & (ce.min45>=75) & (ce.hour.between(7,22)) & (ce.budget>0)
ce["composed"] = ce.fd/ce.budget
ce["delivered"] = np.where(ce.state=="RECOVERING", np.minimum(ce.fd, ce.v1_units.fillna(0)), ce.fd)
print(f"eligible meal-session high cycles: {ce.elig.sum()} | composed multiplier on them: p25/50/75 = "
      f"{ce[ce.elig].composed.quantile([.25,.5,.75]).round(3).tolist()}")

# stuck episodes: BG>180 runs >60min, capped era
def stuck_eps(g):
    out=[]; ts=g.ts_epoch.values; bg=g.bg.values; i=0; n=len(g)
    while i<n:
        if bg[i]>180:
            j=i
            while j+1<n and bg[j+1]>180 and ts[j+1]-ts[j]<900: j+=1
            if ts[j]-ts[i]>=3600: out.append((ts[i],ts[j]))
            i=j+1
        else: i+=1
    return out
eps = {u: stuck_eps(g) for u,g in ce.groupby("user_id")}
n_eps = sum(len(v) for v in eps.values())
print(f"stuck episodes (>180 for >60min): {n_eps}")

print("\n===== LEVER 1: composed floor sweep =====")
for F in (0.15, 0.25, 0.35):
    m = ce.elig & (ce.composed < F)
    sub = ce[m].copy()
    fl = sub.budget*F
    fl = np.where(sub.state=="COMMITTED", np.minimum(fl, sub.cap), fl)
    fl = np.where(sub.state=="RECOVERING", np.minimum(fl, sub.v1_units.fillna(0)), fl)
    add = (fl - sub.delivered).clip(lower=0)
    sub["add"]=add
    tot=add.sum()
    lowU = sub.loc[sub.low3h,"add"].sum()
    # stuck-episode rescue
    resc=0
    for u,windows in eps.items():
        gu=sub[sub.user_id==u]
        for a,b in windows:
            if gu[(gu.ts_epoch>=a)&(gu.ts_epoch<=b)]["add"].sum()>=0.5: resc+=1
    print(f"F={F}: floored cycles {m.sum()} | added {tot:.1f}U ({tot/udays:.2f} U/user-day) | "
          f"pre-low share {100*lowU/max(tot,1e-9):.1f}% (cycle low3h rate {100*sub.low3h.mean():.1f}%) | "
          f"stuck episodes rescued(>=0.5U) {resc}/{n_eps}")
    print(f"   per-user added: {sub.groupby('user_id')['add'].sum().round(1).to_dict()}")

# user H: find user with >180 episodes at 07-05 15:49-16:30Z and 07-06 04:14-04:44Z
print("\n===== USER-H ID + replay =====")
for t0,t1,lbl in ((("2026-07-05 15:45","2026-07-05 16:35"),None,"ep1"), (("2026-07-06 04:10","2026-07-06 04:50"),None,"ep2")):
    pass
w1 = df[(pd.to_datetime(df.ts_utc,utc=True,format="mixed")>=pd.Timestamp("2026-07-05 15:45",tz="UTC"))&(pd.to_datetime(df.ts_utc,utc=True,format="mixed")<=pd.Timestamp("2026-07-05 16:35",tz="UTC"))]
w2 = df[(pd.to_datetime(df.ts_utc,utc=True,format="mixed")>=pd.Timestamp("2026-07-06 04:10",tz="UTC"))&(pd.to_datetime(df.ts_utc,utc=True,format="mixed")<=pd.Timestamp("2026-07-06 04:50",tz="UTC"))]
print("ep1 users/BG:", w1.groupby("user_id").bg.agg(["min","max","count"]).to_dict("index"))
print("ep2 users/BG:", w2.groupby("user_id").bg.agg(["min","max","count"]).to_dict("index"))
