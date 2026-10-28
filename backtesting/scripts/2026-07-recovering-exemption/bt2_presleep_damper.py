#!/usr/bin/env python3
"""BT2 — pre-sleep confirm damper (REMOVES insulin; Test A can only improve).

Candidate (spec): first CONFIRMED of a session, pre-sleep gate, capped at
    min(confirmedCap, base_would * K),  K in {1.3, 1.5, 2.0}
remainder available to subsequent COMMITTED holds (staged).
Pre-sleep gate variants: clock >= 22:00 local  vs  within 90 min of night start
(tim night ~00:38 BST => 23:08-00:38 BST window; differs from clock>=22).

Population: V6-ACTIVE confirms only (those actually drive the pump AND carry a
parseable 'base would=' in the reason). Shadow confirms don't reach the pump so
the damper is moot for them. Also test an ABSOLUTE cap and a x-scale, because the
spec's base_would*1.5 is shown to be a no-op on the incident.
"""
import numpy as np, pandas as pd, psycopg2, os
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"out"); os.makedirs(OUT,exist_ok=True)
TBR14={"tim":(3.11,0.51),"A":(1.11,0.22),"B":(3.83,1.01),"C":(3.82,0.60),
       "D":(10.14,1.81),"E":(1.04,0.00),"F":(2.99,0.35),"H":(1.35,0.28)}
conn=psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df=pd.read_sql("""
SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
 user_id, ts_epoch, ts_utc, cgm_mgdl bg, boostv5_state state, boostv5_age age,
 boostv5_finaldose fd, boostv5_confirmedcap ccap, variable_sens isf, sug_current_target tgt,
 substring(reason_text from 'base would=([0-9.]+)') basewould,
 (reason_text LIKE '%%V6-ACTIVE drove%%') v6active
FROM boost_decisions WHERE boostv5_state IS NOT NULL
ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
""",conn).sort_values(["user_id","ts_epoch"]).reset_index(drop=True)
conn.close()
df["basewould"]=pd.to_numeric(df.basewould,errors="coerce")
dtc=pd.to_datetime(df.ts_utc,utc=True,format="mixed")
df["hour"]=(dtc.dt.hour+1)%24
# forward: fizzle/sustained + min-BG-4h + time>180 in 3h
def fwd(g):
    ts=g.ts_epoch.values; bg=g.bg.values; m=len(g)
    nad=np.full(m,np.nan); sust=np.zeros(m,bool); fizz=np.zeros(m,bool); t180=np.zeros(m)
    low54=np.zeros(m,bool)
    for i in range(m):
        w4=bg[(ts>ts[i])&(ts<=ts[i]+14400)]
        w45=bg[(ts>ts[i])&(ts<=ts[i]+2700)]
        w3=bg[(ts>ts[i])&(ts<=ts[i]+10800)]
        if len(w4): nad[i]=w4.min(); low54[i]=(w4<54).any()
        t180[i]=5*int((w3>180).sum())
        if len(w45):
            over=(w45>180).astype(int); run=0; mx=0
            for o in over: run=run+1 if o else 0; mx=max(mx,run)
            sust[i]=mx>=3; pk=w45.max(); fizz[i]=(pk<=180)and(w45[-1]<pk-5)
    return pd.DataFrame(dict(nad=nad,sust=sust,fizz=fizz,t180=t180,low54=low54),index=g.index)
df=df.join(pd.concat([fwd(g) for _,g in df.groupby("user_id",sort=False)]))

fc=df[(df.state=="CONFIRMED")&(df.age==0)&(df.v6active)].copy()
fc["presleep"]=fc.hour>=22
print(f"=== BT2: pre-sleep confirm damper ===\nV6-active fresh confirms: {len(fc)} | with parseable base_would: {int(fc.basewould.notna().sum())}")
ev=fc[fc.presleep & fc.basewould.notna()]
print(f"pre-sleep(>=22h) V6-active confirms w/ base_would: {len(ev)}")

print("\n--- spec: cap at min(confirmedCap, base_would*K); removed = fd - cap ---")
for K in (1.3,1.5,2.0):
    ev=ev.copy(); ev["cap"]=np.minimum(ev.ccap, ev.basewould*K); ev["rem"]=(ev.fd-ev.cap).clip(lower=0)
    tot=ev.rem.sum(); rf=ev.loc[ev.fizz,"rem"].sum(); rs=ev.loc[ev.sust,"rem"].sum()
    add180=(ev.loc[ev.sust,"t180"]).sum()  # real-meal time>180 potentially extended
    print(f"K={K}: confirms touched {int((ev.rem>0).sum())}/{len(ev)} removed {tot:.2f}U | fizzle {100*rf/max(tot,1e-9):.0f}% real-meal {100*rs/max(tot,1e-9):.0f}% | tim removed {ev[ev.user_id=='tim'].rem.sum():.2f}U")
print("\n--- alternatives (catch the incident) ---")
for lbl,capfn in [("abs cap 1.5U",lambda g:np.minimum(g.fd,1.5)),
                  ("abs cap 2.0U",lambda g:np.minimum(g.fd,2.0)),
                  ("x0.6 scale",lambda g:g.fd*0.6),
                  ("cap base_would*1.0",lambda g:np.minimum(g.ccap,g.basewould*1.0))]:
    e=fc[fc.presleep & fc.basewould.notna()].copy(); e["new"]=capfn(e); e["rem"]=(e.fd-e["new"]).clip(lower=0)
    tot=e.rem.sum(); rf=e.loc[e.fizz,"rem"].sum(); rs=e.loc[e.sust,"rem"].sum()
    print(f"{lbl}: removed {tot:.2f}U | fizzle {100*rf/max(tot,1e-9):.0f}% real-meal {100*rs/max(tot,1e-9):.0f}% | tim {e[e.user_id=='tim'].rem.sum():.2f}U | avg time>180 added on real-meals: {e.loc[e.sust,'t180'].mean() if e.sust.any() else 0:.0f}min")

print("\n=== 2. Incident replay (tim 07-06 22:44Z, fd=3.0 base_would=2.0 ccap=3.0 peak=219) ===")
inc=fc[(fc.user_id=='tim')&(fc.ts_epoch.between(pd.Timestamp('2026-07-06 21:42',tz='UTC').timestamp(),pd.Timestamp('2026-07-06 21:46',tz='UTC').timestamp()))]
if len(inc):
    r=inc.iloc[0]
    for K in (1.3,1.5,2.0): print(f"  base_would*{K}={r.basewould*K:.1f} -> cap min(ccap,.)= {min(r.ccap,r.basewould*K):.1f} -> delivered {min(r.fd,min(r.ccap,r.basewould*K)):.1f} (removes {max(0,r.fd-min(r.ccap,r.basewould*K)):.1f}U)")
    print(f"  abs 1.5U -> delivered 1.5 (removes 1.5U); needed-from-peak (219,ISF {r.isf:.0f})={(219-r.tgt)/r.isf:.2f}U")

print("\n=== 3. Gate comparison (tim): clock>=22 vs within-90min-of-night-start(23:08-00:38 BST=22:08-23:38 UTC) ===")
tc=df[(df.state=='CONFIRMED')&(df.age==0)&(df.user_id=='tim')].copy()
tcu=pd.to_datetime(tc.ts_utc,utc=True,format="mixed")
tc["clock22"]=tc.hour>=22
tc["nightprox"]=(tcu.dt.hour+ tcu.dt.minute/60).between(22.13,23.63)  # 22:08-23:38 UTC = 23:08-00:38 BST
for g,lbl in [("clock22","clock>=22 local"),("nightprox","within 90min of night start")]:
    sub=tc[tc[g]]
    print(f"  {lbl}: n={len(sub)} confirms, fizzle {100*sub.fizz.mean():.0f}%, <54 {100*sub.low54.mean():.0f}%, catches incident: {'YES' if (sub.ts_epoch.between(pd.Timestamp('2026-07-06 21:42',tz='UTC').timestamp(),pd.Timestamp('2026-07-06 21:46',tz='UTC').timestamp())).any() else 'NO'}")

print("\n=== 4. Per-user Test A (removal -> improves TBR; est via ISF on removed-pre-low U) ===")
best=fc[fc.presleep & fc.basewould.notna()].copy(); best["new"]=np.minimum(best.fd,1.5); best["rem"]=(best.fd-best["new"]).clip(lower=0)
for u,g in best.groupby("user_id"):
    if g.rem.sum()<=0: continue
    isf=g.isf.median(); rem54=g.loc[g.low54,"rem"].sum()
    print(f"  {u}: removed {g.rem.sum():.2f}U (of which {rem54:.2f}U preceded <54) -> TBR can only improve; cost = under-cover on {int(g.sust.sum())} real-meal confirms (avg t>180={g.loc[g.sust,'t180'].mean() if g.sust.any() else 0:.0f}min)")
best.to_csv(f"{OUT}/bt2_presleep_abs15.csv",index=False)
