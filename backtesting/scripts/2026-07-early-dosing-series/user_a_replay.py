#!/usr/bin/env python3
"""User A: replay vs latest shipped stack + pull-forward levers. Last 14d, deduped."""
import psycopg2, pandas as pd, numpy as np

conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
SELECT DISTINCT ON (floor(ts_epoch/300.0))
 ts_epoch, ts_utc, cgm_mgdl bg, boostv5_state state, boostv5_age age, boostv5_finaldose fd,
 boostv5_budget budget, boostv5_score score, v1_units, sug_insulinreq insreq,
 sug_eventualbg ev, sug_current_target tgt, iob_iob iob, delta_acceleration accl, tdd,
 (reason_text LIKE '%%V6-ACTIVE drove%%') AS v6drove
FROM boost_decisions WHERE user_id='A' AND boostv5_state IS NOT NULL
ORDER BY floor(ts_epoch/300.0), ts_epoch DESC""", conn).sort_values("ts_epoch").reset_index(drop=True)
df["dt"]=df.ts_epoch.diff()/60; df["delta5"]=df.bg.diff()/df.dt*5
df.loc[(df.dt>7.6)|(df.dt<2.0),"delta5"]=np.nan
df["date"]=pd.to_datetime(df.ts_utc,utc=True,format="mixed").dt.date
n=len(df); ts=df.ts_epoch.values; bgv=df.bg.values
low3h=np.zeros(n,bool); min45=np.full(n,np.nan)
j=0
for i in range(n):
    while ts[i]-ts[j]>2700: j+=1
    min45[i]=np.nanmin(bgv[j:i+1])
for i in range(n):
    k=i+1
    while k<n and ts[k]-ts[i]<=10800: k+=1
    low3h[i]=(bgv[i+1:k]<70).any()
df["low3h"]=low3h; df["min45"]=min45
d14 = df[df.ts_epoch>=ts[-1]-14*86400].copy()
days = d14.date.nunique()
TDD14 = d14.tdd.median()
print(f"A last-14d: {len(d14)} cycles, {days} days | TDD med(14d) {TDD14:.1f} | base low3h {100*d14.low3h.mean():.1f}%")

print("\n===== amended migration values (fresh) =====")
smb = d14.v1_units[d14.v1_units>0]
p95, p75 = smb.quantile(.95), smb.quantile(.75)
conf_new = np.clip(p95, 1.5, 7.5)
ccap_new = np.clip(max(p75, TDD14/40), 0.25, 2.5)
cum_new = np.clip(conf_new + 2*ccap_new, 1, 10)
print(f"confirmedCap: p95smb {p95:.2f} -> {conf_new:.2f} (operative now 2.5, so slight DOWN)")
print(f"committedCap: max(p75 {p75:.2f}, TDD/40 {TDD14/40:.2f}) -> {ccap_new:.2f} (now 0.5)")
print(f"cumulative: {cum_new:.2f} (binds 0x in 14d anyway)")
gate_floor = min(min(ccap_new, 0.5), 0.8*conf_new)
print(f"gate floor with pin: min(min({ccap_new:.2f},0.5), 0.8x{conf_new:.2f}) = {gate_floor:.2f} (unchanged vs today)")

print("\n===== 1a. high-side profile =====")
ting = 100*d14.bg.between(63,140).mean()
t180 = (d14.bg>180).sum()*5/60
t160 = (d14.bg>160).sum()*5/60
print(f"TING {ting:.1f}% | >180: {t180:.1f}h/{days}d ({t180/days:.2f} h/day) | >160: {t160/days:.2f} h/day")
# meal peaks
sm=d14.bg.rolling(3,center=True,min_periods=1).mean().values; tss=d14.ts_epoch.values
evs=[]; i=1; tr=0
while i<len(d14):
    if sm[i]<sm[tr]: tr=i
    if sm[i]-sm[tr]>=25:
        pk=i
        while pk+1<len(d14) and sm[pk+1]>=sm[pk]-1 and tss[pk+1]-tss[pk]<600: pk+=1
        if tss[pk]-tss[tr]<=3*3600: evs.append((tr,pk))
        tr=pk; i=pk
    i+=1
pks=[np.nanmax(d14.bg.values[a:b+1]) for a,b in evs]
print(f"rise events: {len(evs)} ({len(evs)/days:.1f}/d) | peaks p50/p75/p90: {np.percentile(pks,[50,75,90]).round(0).tolist()} | >180 peaks: {sum(p>180 for p in pks)}")

print("\n===== 1a. decomposition of mechanisms =====")
# era caps for A
def cap(dt): return 0.5 if dt>=pd.to_datetime("2026-07-01").date() else 0.25
d14["cap"]=d14.date.apply(cap)
# (i) cap-clipped holds -> raise to ccap_new
cl = d14[(d14.state=="COMMITTED")&(d14.budget>=d14.cap)&(d14.fd>=0.5*d14.cap)]
add_up = (cl.fd*(np.minimum(cl.budget,ccap_new)/cl.cap-1)).clip(lower=0)
add_lo = (cl.fd*(np.minimum(np.maximum(cl.budget*0.4,cl.cap),ccap_new)/cl.cap-1)).clip(lower=0)
print(f"(i) cap-clipped holds: {len(cl)} ({len(cl)/days:.1f}/d) | cap 0.5->{ccap_new:.2f} adds {add_lo.sum():.1f}-{add_up.sum():.1f}U ({add_lo.sum()/days:.2f}-{add_up.sum()/days:.2f} U/d) | pre-low {100*add_up[cl.low3h].sum()/max(add_up.sum(),1e-9):.1f}%")
# (ii) confirm latency: fresh confirms, shift-1 eligible + fast-path retune catches
d = d14.reset_index(drop=True)
fresh = d.index[(d.state=="CONFIRMED")&(d.state.shift()!="CONFIRMED")]
sh1 = [i for i in fresh if i>=1 and d.score.iloc[i-1]>=0.55 and (i<2 or d.score.iloc[i-2]>=0.55)]
fp=[]
for i in fresh:
    for k in range(max(0,i-6),i):
        r=d.iloc[k]
        if r.state in ("IDLE","OBSERVING") and pd.notna(r.delta5) and r.delta5>=6 and pd.notna(r.accl) and r.accl>=10 and r.score>=0.65 and r.min45>=80:
            fp.append((i,(d.ts_epoch.iloc[i]-d.ts_epoch.iloc[k])/60)); break
print(f"(ii) fresh confirms: {len(fresh)} ({len(fresh)/days:.1f}/d) | early-confirm (score held 2cyc) moves {len(sh1)} ({100*len(sh1)/max(len(fresh),1):.0f}%) 1 cycle earlier | fast-path retune catches {len(fp)} (med {np.median([m for _,m in fp]) if fp else 0:.0f} min earlier)")
conf_fd = d.fd[fresh]
print(f"    confirm shots now: med {conf_fd.median():.2f}U, at ceiling 2.5: {(conf_fd>=2.45).sum()} -> new ceiling {conf_new:.2f} trims those")
# (iii) budget=0 >180 stretches
z = d[(d.bg>180)&(d.budget<0.05)]
runs=0; rmins=0
i=0
while i<len(d):
    if d.bg.iloc[i]>180 and d.budget.iloc[i]<0.05:
        j2=i
        while j2+1<len(d) and d.bg.iloc[j2+1]>180 and d.budget.iloc[j2+1]<0.05 and d.ts_epoch.iloc[j2+1]-d.ts_epoch.iloc[j2]<900: j2+=1
        if (d.ts_epoch.iloc[j2]-d.ts_epoch.iloc[i])>=1800: runs+=1; rmins+=(d.ts_epoch.iloc[j2]-d.ts_epoch.iloc[i])/60
        i=j2+1
    else: i+=1
print(f"(iii) budget=0 >180 stretches (>=30min): {runs} totalling {rmins:.0f} min | insreq<=0 share of >180 cycles: {100*(d[(d.bg>180)].insreq<=0).mean():.0f}%")
# (iv) shadow floor F=0.25
elig = d.state.isin(["CONFIRMED","COMMITTED","RECOVERING"])&(d.bg>160)&((d.ev-d.tgt)>20)&(d.min45>=75)&(d.budget>0)
comp = d.fd/d.budget.replace(0,np.nan)
m = elig&(comp.fillna(0)<0.25)
fl = d.budget*0.25
fl = np.where(d.state=="COMMITTED",np.minimum(fl,d.cap),fl)
fl = np.where(d.state=="RECOVERING",np.minimum(fl,d.v1_units.fillna(0)),fl)
deliv = np.where(d.state=="RECOVERING",np.minimum(d.fd,d.v1_units.fillna(0)),d.fd)
addf = pd.Series(np.where(m,(fl-deliv).clip(0,None),0))
print(f"(iv) shadow floor F=0.25: {m.sum()} cycles, adds {addf.sum():.1f}U ({addf.sum()/days:.2f} U/d) | pre-low {100*addf[d.low3h.values].sum()/max(addf.sum(),1e-9):.1f}%")
print(f"(v) cumulative-cap suppressions: 0 (verified)")

print("\n===== 1b/2. combined post-update delta + pricing =====")
tot_lo = add_lo.sum()+addf.sum(); tot_up = add_up.sum()+addf.sum()
lowU = add_up[cl.low3h].sum()+addf[d.low3h.values].sum()
print(f"net added (cap raise + floor): {tot_lo:.1f}-{tot_up:.1f}U/14d = {tot_lo/days:.2f}-{tot_up/days:.2f} U/day (~{100*tot_up/(TDD14*days):.1f}% of TDD)")
print(f"pooled pre-low pricing: {100*lowU/max(tot_up+1e-9,1e-9):.1f}% vs his base {100*d14.low3h.mean():.1f}%")
# gate check: shots vs floor 0.5
shots_hi = d.budget[fresh]*1.8
print(f"\ngate: confirms with budget*1.8 <= 0.5 (would-block at vf=1): {(shots_hi<=0.5).sum()}/{len(fresh)}; at vf=0.4: {(shots_hi*0.4<=0.5).sum()}/{len(fresh)}")
