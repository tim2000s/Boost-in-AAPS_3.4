#!/usr/bin/env python3
"""Developer (self) small-meal plateau analysis (DB, user tim, last ~30d + full state era)."""
import psycopg2, pandas as pd, numpy as np

conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
SELECT DISTINCT ON (floor(ts_epoch/300.0))
  ts_epoch, ts_utc, cgm_mgdl AS bg, boostv5_state AS state, boostv5_age AS age,
  boostv5_finaldose AS fd, boostv5_budget AS budget, boostv5_score AS score,
  boostv5_gatereduction AS gate, ml_hypo_risk AS mlrisk, v1_units, iob_iob AS iob, tdd
FROM boost_decisions WHERE user_id='tim' AND boostv5_state IS NOT NULL
ORDER BY floor(ts_epoch/300.0), ts_epoch DESC
""", conn).sort_values("ts_epoch").reset_index(drop=True)
df["dt"] = df.ts_epoch.diff()/60
df["delta5"] = df.bg.diff()/df.dt*5
df.loc[(df.dt>7.6)|(df.dt<2.0),"delta5"]=np.nan
df["hour"] = (pd.to_datetime(df.ts_utc, utc=True, format="mixed").dt.hour+1)%24
ts=df.ts_epoch.values; bg=df.bg.values; n=len(df)
min45=np.full(n,np.nan); low3h=np.zeros(n,bool)
j=0
for i in range(n):
    while ts[i]-ts[j]>2700: j+=1
    min45[i]=np.nanmin(bg[j:i+1])
for i in range(n):
    k=i+1
    while k<n and ts[k]-ts[i]<=10800: k+=1
    low3h[i]=(bg[i+1:k]<70).any()
df["min45"]=min45; df["low3h"]=low3h
tddm = df.tdd.median()
last30 = df[df.ts_epoch >= df.ts_epoch.max()-30*86400]
print(f"tim cycles: {len(df)} total, {len(last30)} last-30d ({str(df.ts_utc.iloc[0])[:10]} -> {str(df.ts_utc.iloc[-1])[:10]})")

# ---- 1. rise events: trough->peak swings >=25 ----
sm = df.bg.rolling(3, center=True, min_periods=1).mean().values
events=[]
i=1; trough_i=0
while i < n:
    if sm[i] < sm[trough_i]: trough_i=i
    # candidate rise: from trough, find local peak
    if sm[i]-sm[trough_i] >= 25:
        pk=i
        while pk+1<n and sm[pk+1]>=sm[pk]-1 and ts[pk+1]-ts[pk]<600:
            pk+=1
        if ts[pk]-ts[trough_i] <= 3*3600:
            events.append((trough_i, pk))
        trough_i = pk; i = pk
    i+=1
ev = pd.DataFrame([dict(t0=a, t1=b, ts0=ts[a], ts1=ts[b], bg0=bg[a], pk=np.nanmax(bg[a:b+1]),
                        rise=np.nanmax(bg[a:b+1])-bg[a]) for a,b in events])
ev["cls"] = np.where(ev.pk>200,"big", np.where((ev.pk>=155),"small","minor"))
ev30 = ev[ev.ts1 >= ts[-1]-30*86400]
print(f"\n===== 1. PATTERN (last 30d) =====")
print("rise events (>=25 mg/dL):", ev30.cls.value_counts().to_dict(), f"({len(ev30)/30:.1f}/day)")
# plateau after small peaks: from peak, time in 155-185 while |delta|<~5 until BG<155 or >185
plat=[]
for _, r in ev30[ev30.cls=="small"].iterrows():
    k = int(r.t1); dur=0; end=k
    while end+1<n and 150<=bg[end+1]<=190 and ts[end+1]-ts[end]<600:
        end+=1
    dur = (ts[end]-ts[int(r.t1)])/60
    # second rise starting >150: next event whose bg0>150 within 3h of this peak
    nxt = ev[(ev.ts0>r.ts1)&(ev.ts0<=r.ts1+3*3600)]
    stack = bool(len(nxt)) and nxt.bg0.iloc[0]>150
    plat.append(dict(ts=r.ts1, pk=r.pk, dur=dur, stuck=dur>45, stack=stack))
P = pd.DataFrame(plat)
print(f"small-meal events: {len(P)} | stuck plateau >45min after peak: {P.stuck.sum()} ({100*P.stuck.mean():.0f}%)")
print("plateau duration min:", P.dur.describe()[["25%","50%","75%","max"]].round(0).to_dict())
print(f"second rise starts while still >150: {P["stack"].sum()} ({100*P["stack"].mean():.0f}%)")
m160 = (last30.bg>160).sum()*5
in_plat = 0
for _, r in P[P.stuck].iterrows():
    w = last30[(last30.ts_epoch>=r.ts)&(last30.ts_epoch<=r.ts+r.dur*60)]
    in_plat += (w.bg>160).sum()*5
print(f"time >160 last 30d: {m160/60:.1f} h/30d ({m160/30/60:.1f} h/day); within small-meal plateaus: {in_plat/60:.1f} h ({100*in_plat/max(m160,1):.0f}%)")

# ---- 2. plateau dosing decomposition ----
print("\n===== 2. PLATEAU DOSING (BG 155-185, |delta|<3, no post-rescue, awake, full era) =====")
pl = df[(df.bg.between(155,185)) & (df.delta5.abs()<3) & (df.min45>=75) & (df.hour.between(7,22))]
print(f"plateau cycles: {len(pl)} ({len(pl)/(len(df)/288):.1f}/day)")
print("state mix:", pl.state.value_counts().to_dict())
pl_nm = pl[pl.state.isin(["IDLE","OBSERVING","RECOVERING"])]
cap = np.minimum(pl_nm.fd, pl_nm.v1_units.fillna(0))
print(f"non-meal plateau cycles: {len(pl_nm)} | V6-capped delivery {cap.sum():.1f}U vs v1would {pl_nm.v1_units.fillna(0).sum():.1f}U -> parity {100*cap.sum()/max(pl_nm.v1_units.fillna(0).sum(),1e-9):.0f}%")
gap = (pl_nm.v1_units.fillna(0)-cap).clip(lower=0)
print(f"parity gap: {gap.sum():.1f}U over {len(df)/288:.0f} days = {gap.sum()/(len(df)/288):.2f} U/day")
gp = pl_nm[gap>0]
print(f"gap>0 cycles: {len(gp)} — binding constraint breakdown:")
print(f"  fd==0 outright: {(gp.fd==0).sum()} | 0<fd<v1: {((gp.fd>0)&(gp.fd<gp.v1_units)).sum()}")
print(f"  budget < v1 on gap cycles: {(gp.budget<gp.v1_units).sum()}/{len(gp)} (med budget {gp.budget.median():.2f} vs med v1 {gp.v1_units.median():.2f})")
print("  gateReduction strings:", gp.gate.value_counts().head(6).to_dict())
print(f"  mlHypoRisk on gap cycles: med {gp.mlrisk.median():.2f} vs plateau overall {pl_nm.mlrisk.median():.2f}")
print(f"  IOB on gap cycles: med {gp.iob.median():.2f}U ({100*gp.iob.median()/tddm:.0f}%TDD)")

# ---- 4a. lever: v1-parity on plateaus — harm pricing ----
print("\n===== 4a. LEVER: exact v1WouldDose on plateau (tim + cohort) =====")
print(f"tim: extra {gap.sum():.1f}U total ({gap.sum()/(len(df)/288):.2f} U/day); pre-low share of that insulin: {100*(gap*pl_nm.low3h).sum()/max(gap.sum(),1e-9):.1f}% | plateau-cycle low3h rate {100*pl_nm.low3h.mean():.1f}%")
print(f"tim plateau IOB: med {100*pl_nm.iob.median()/tddm:.1f}%TDD (IOB-harm curve @BG>=140: 5-7.5%TDD -> 13%, 7.5-10 -> 15%)")

# ---- 3. stacking ----
print("\n===== 3. STACKING: second-rise response =====")
ev["prior_meal_45m"]=False
conf_ts = df.ts_epoch[df.state=="CONFIRMED"].values
comm_ts = df.ts_epoch[df.state.isin(["CONFIRMED","COMMITTED"])].values
res=[]
for _, r in ev.iterrows():
    seg = df[(df.ts_epoch>=r.ts0)&(df.ts_epoch<=r.ts0+1800)]
    if not len(seg): continue
    prior = ((comm_ts<r.ts0)&(comm_ts>r.ts0-5400)).any()
    confirmed = ((conf_ts>r.ts0)&(conf_ts<=r.ts0+2700)).any()
    res.append(dict(bg0=r.bg0, rise=r.rise, prior=prior, confirmed=confirmed,
        fd30=np.minimum(seg.fd, np.where(seg.state.isin(["CONFIRMED","COMMITTED"]), seg.fd, seg.v1_units.fillna(0))).sum(),
        v130=seg.v1_units.fillna(0).sum(), maxd=seg.delta5.max()))
R = pd.DataFrame(res)
R["grp"] = np.where(R.bg0>150,"start>150", np.where(R.bg0<140,"start<140","mid"))
Rm = R[R.rise>=25]
print(Rm.groupby(["grp","prior"]).agg(n=("bg0","size"), confirm_rate=("confirmed","mean"),
      med_fd30=("fd30","median"), med_v130=("v130","median")).round(2).to_string())
print("(prior=True means CONFIRMED/COMMITTED within 90min before rise start = same-session lock likely)")

# ---- 4b. RECOVERING lingering ----
print("\n===== 4b. RECOVERING on plateaus =====")
print(f"plateau state shares: RECOVERING {100*(pl.state=='RECOVERING').mean():.0f}% IDLE {100*(pl.state=='IDLE').mean():.0f}% OBSERVING {100*(pl.state=='OBSERVING').mean():.0f}%")
rec = pl[pl.state=="RECOVERING"]; idl = pl[pl.state=="IDLE"]
print(f"parity RECOVERING: {100*np.minimum(rec.fd,rec.v1_units.fillna(0)).sum()/max(rec.v1_units.fillna(0).sum(),1e-9):.0f}% | IDLE: {100*np.minimum(idl.fd,idl.v1_units.fillna(0)).sum()/max(idl.v1_units.fillna(0).sum(),1e-9):.0f}%")
