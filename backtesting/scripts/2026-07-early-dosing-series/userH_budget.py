#!/usr/bin/env python3
"""Why is user H's AggressionBudget ~0 on stuck-high climbs? Structural hypothesis test."""
import psycopg2, pandas as pd, numpy as np

conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
SELECT DISTINCT ON (floor(ts_epoch/300.0))
 ts_epoch, ts_utc, cgm_mgdl bg, boostv5_state state, boostv5_finaldose fd, boostv5_budget budget,
 v1_units, sug_insulinreq insreq, sug_eventualbg ev, sug_current_target tgt,
 iob_iob iob, iob_bolusiob bolusiob, tdd, ml_hypo_risk mlrisk
FROM boost_decisions WHERE user_id='H'
ORDER BY floor(ts_epoch/300.0), ts_epoch DESC""", conn).sort_values("ts_epoch").reset_index(drop=True)
df["dt"]=df.ts_epoch.diff()/60; df["delta5"]=df.bg.diff()/df.dt*5
df.loc[(df.dt>7.6)|(df.dt<2.0),"delta5"]=np.nan
df["era"]=np.where(df.state.notna(),"V6","V1")
TDD=50.0
n=len(df); ts=df.ts_epoch.values; bg=df.bg.values
low3h=np.zeros(n,bool)
for i in range(n):
    k=i+1
    while k<n and ts[k]-ts[i]<=10800: k+=1
    low3h[i]=(bg[i+1:k]<70).any()
df["low3h"]=low3h
# BG at +60 and +120 min (for eventualBG bias)
bg60=np.full(n,np.nan); bg120=np.full(n,np.nan)
for i in range(n):
    k=i
    while k<n and ts[k]-ts[i]<3300: k+=1
    if k<n and ts[k]-ts[i]<=3900: bg60[i]=bg[k]
    while k<n and ts[k]-ts[i]<6900: k+=1
    if k<n and ts[k]-ts[i]<=7500: bg120[i]=bg[k]
df["bg60"]=bg60; df["bg120"]=bg120

print("===== 1. V6-era climb cycles (delta>3, BG>150, meal session) =====")
v6 = df[df.era=="V6"]
cl = v6[(v6.delta5>3)&(v6.bg>150)&(v6.state.isin(["CONFIRMED","COMMITTED","RECOVERING"]))]
print(f"n={len(cl)}")
for c in ("insreq","iob","budget","v1_units","fd"):
    print(f"  {c}: p25/50/75 = {cl[c].quantile([.25,.5,.75]).round(2).tolist()}")
print(f"  insulinReq <= 0: {100*(cl.insreq<=0).mean():.0f}% | budget < 0.1: {100*(cl.budget<0.1).mean():.0f}%")
print(f"  IOB as %TDD on insReq<=0 climbs: med {100*cl[cl.insreq<=0].iob.median()/TDD:.1f}% | bolusIOB med {cl[cl.insreq<=0].bolusiob.median():.2f}U")
print(f"  budget vs insreq corr: {cl.budget.corr(cl.insreq):.2f} | budget=0 cycles have insreq med {cl[cl.budget<0.05].insreq.median():.2f}")
stuck = v6[(v6.bg>180)&(v6.budget<0.05)]
print(f"V6 stuck-high budget=0 cycles (BG>180): {len(stuck)}, insreq med {stuck.insreq.median():.2f}, insreq<=0 {100*(stuck.insreq<=0).mean():.0f}%, IOB med {100*stuck.iob.median()/TDD:.0f}%TDD")

print("\n===== 2. V1-era matched comparison (the crux) =====")
# match on BG band(25), delta band(3), IOB band(1.0U) to V6 budget=0 climb cycles
z = v6[(v6.delta5>3)&(v6.bg>150)&(v6.budget<0.05)].copy()
v1e = df[(df.era=="V1")&df.delta5.notna()].copy()
print(f"V6 budget=0 climb cycles to match: {len(z)}")
def band(s, w): return (s/w).round()
z["b1"],z["b2"],z["b3"] = band(z.bg,25), band(z.delta5,3), band(z.iob,1.0)
v1e["b1"],v1e["b2"],v1e["b3"] = band(v1e.bg,25), band(v1e.delta5,3), band(v1e.iob,1.0)
merged=[]
for _,r in z.iterrows():
    m = v1e[(v1e.b1==r.b1)&(v1e.b2==r.b2)&(v1e.b3==r.b3)]
    if len(m): merged.append(dict(n=len(m), v1_med=m.v1_units.fillna(0).median(), v1_mean=m.v1_units.fillna(0).mean(),
        v1_pos=(m.v1_units.fillna(0)>0).mean(), insreq_le0=(m.insreq<=0).mean(), low3h=m.low3h.mean()))
M=pd.DataFrame(merged)
print(f"matched: {len(M)}/{len(z)} cycles found V1-era matches (med {M.n.median():.0f} matches each)")
print(f"ACTING V1 at matched states: delivered med-of-med {M.v1_med.median():.2f}U, mean {M.v1_mean.mean():.2f}U, dosed>0 on {100*M.v1_pos.mean():.0f}% of matched cycles")
print(f"matched V1 cycles insulinReq<=0: {100*M.insreq_le0.mean():.0f}% | their low3h rate: {100*M.low3h.mean():.1f}%")

print("\n===== 3. Outcome adjudication: budget=0 stuck stretches =====")
runs=[]
i=0; v6i = v6.reset_index(drop=True)
while i<len(v6i):
    if v6i.bg.iloc[i]>180 and v6i.budget.iloc[i]<0.05 and v6i.state.iloc[i] in ("CONFIRMED","COMMITTED","RECOVERING","IDLE"):
        j=i
        while j+1<len(v6i) and v6i.bg.iloc[j+1]>180 and v6i.ts_epoch.iloc[j+1]-v6i.ts_epoch.iloc[j]<900: j+=1
        if v6i.ts_epoch.iloc[j]-v6i.ts_epoch.iloc[i]>=1800:
            end=v6i.ts_epoch.iloc[j]
            fw = v6i[(v6i.ts_epoch>end)&(v6i.ts_epoch<=end+5400)]
            peak_in = v6i.bg.iloc[i:j+1].max()
            resolved90 = bool(len(fw)) and fw.bg.min()<160
            dur=(end-v6i.ts_epoch.iloc[i])/60
            runs.append(dict(start=str(v6i.ts_utc.iloc[i])[:16], dur=dur, peak=peak_in,
                iob0=v6i.iob.iloc[i], resolved90after=resolved90,
                persist2h=dur>=120 or not resolved90))
        i=j+1
    else: i+=1
R=pd.DataFrame(runs)
print(f"budget=0 >180 stretches (>=30min): {len(R)}")
if len(R):
    print(R.to_string(index=False))
    print(f"resolved <160 within 90min of stretch end: {R.resolved90after.sum()}/{len(R)}")
print("\n--- eventualBG bias on V6 climb cycles (predicted vs actual) ---")
cb = v6[(v6.delta5>3)&(v6.bg>150)&v6.ev.notna()]
b60=(cb.bg60-cb.ev).dropna(); b120=(cb.bg120-cb.ev).dropna()
print(f"actual(+60) - eventualBG: med {b60.median():.0f} mg/dL (n={len(b60)}) | actual(+120) - ev: med {b120.median():.0f} (n={len(b120)})")
v1cb = df[(df.era=='V1')&(df.delta5>3)&(df.bg>150)&df.ev.notna()]
print(f"V1-era same: +60 med {(v1cb.bg60-v1cb.ev).median():.0f}, +120 med {(v1cb.bg120-v1cb.ev).median():.0f}")

print("\n===== 4a. velocity-budget counterfactual (V1-tier-like) on V6 budget=0 climbs =====")
# counterfactual dose per cycle = V1-era matched median delivered (from #2 per-cycle)
z2 = z.reset_index(drop=True)
cf=[]
for _,r in z2.iterrows():
    m = v1e[(v1e.b1==r.b1)&(v1e.b2==r.b2)&(v1e.b3==r.b3)]
    cf.append(m.v1_units.fillna(0).median() if len(m) else np.nan)
z2["cf"]=cf
val=z2.dropna(subset=["cf"])
days = v6.ts_epoch.agg(lambda s:(s.max()-s.min())/86400)
print(f"counterfactual U on his budget=0 climb cycles: {val.cf.sum():.1f}U over {days:.0f} V6 days ({val.cf.sum()/days:.2f} U/day)")
print(f"pre-low pricing (his own low3h at those cycles): {100*val[val.low3h].cf.sum()/max(val.cf.sum(),1e-9):.1f}% | cycles low3h {100*val.low3h.mean():.1f}%")
print(f"IOB where it lands: med {100*val.iob.median()/TDD:.0f}%TDD")
print("\n===== 4d. did V1's velocity dosing at these states precede lows FOR HIM? =====")
m_all = v1e[(v1e.delta5>3)&(v1e.bg>150)&(v1e.insreq<=0)&(v1e.v1_units.fillna(0)>0)]
print(f"V1-era cycles: climb+insReq<=0+V1 dosed>0: n={len(m_all)}, dose med {m_all.v1_units.median():.2f}U, low<70-in-3h followed {100*m_all.low3h.mean():.1f}% | his V1-era base low3h rate {100*df[df.era=='V1'].low3h.mean():.1f}%")

print("\n===== 4c. under-bolus quantification =====")
# excursions: V6-era rises from <150 to peak; implied missing insulin = (peak-140)/ISF41 beyond delivered
v6r = v6.reset_index(drop=True)
sm=v6r.bg.rolling(3,center=True,min_periods=1).mean().values
tss=v6r.ts_epoch.values; ex=[]
i=1; tr=0
while i<len(v6r):
    if sm[i]<sm[tr]: tr=i
    if sm[i]-sm[tr]>=40:
        pk=i
        while pk+1<len(v6r) and sm[pk+1]>=sm[pk]-1 and tss[pk+1]-tss[pk]<600: pk+=1
        peak=v6r.bg.iloc[tr:pk+1].max()
        if peak>180: ex.append((peak-160)/41.0)
        tr=pk; i=pk
    i+=1
print(f"V6-era excursions peaking >180: {len(ex)} in {days:.0f} days; implied uncovered insulin med {np.median(ex):.1f}U, p75 {np.percentile(ex,75):.1f}U per excursion")
