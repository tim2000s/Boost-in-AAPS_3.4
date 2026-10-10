#!/usr/bin/env python3
"""Capstone: where is EARLIER insulin available, and what does it cost?
Sections: 1 IOB-harm map, 2 confirm latency anatomy, 3 early gap vs highs,
4 early-confirm counterfactual, 5 fast-path sweep, 6 blocked-confirm audit, 7 meal-time regularity."""
import psycopg2, pandas as pd, numpy as np

SP = "/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad"
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
  user_id, ts_epoch, ts_utc, cgm_mgdl, boostv5_state AS state, boostv5_age AS age,
  boostv5_finaldose AS fd, boostv5_budget AS budget, boostv5_score AS score,
  v1_units, iob_iob AS iob, delta_acceleration AS accl, tdd
FROM boost_decisions WHERE boostv5_state IS NOT NULL
ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
""", conn).sort_values(["user_id","ts_epoch"]).reset_index(drop=True)
df["dt"] = df.groupby("user_id")["ts_epoch"].diff()/60.0
df["delta5"] = df.groupby("user_id")["cgm_mgdl"].diff()/df.dt*5.0
df.loc[(df.dt>7.6)|(df.dt<2.0),"delta5"]=np.nan
df["hour"] = (pd.to_datetime(df.ts_utc, utc=True, format="mixed").dt.hour + 1) % 24  # local ~UTC+1
tddmed = df.groupby("user_id").tdd.median()
df["iobn"] = df.iob / df.user_id.map(tddmed)  # IOB as fraction of TDD

# forward low<70 within 3h, and rolling 60-min min BG (two-pointer per user)
low3h = np.zeros(len(df), bool); min60 = np.full(len(df), np.nan)
for uid, g in df.groupby("user_id", sort=False):
    ts = g.ts_epoch.values; bg = g.cgm_mgdl.values; idx = g.index.values; n=len(g)
    j0 = 0
    for i in range(n):
        while ts[i]-ts[j0] > 3600: j0 += 1
        min60[idx[i]] = np.nanmin(bg[j0:i+1])
    k = 0
    for i in range(n):
        if k <= i: k = i+1
        while k < n and ts[k]-ts[i] <= 10800:
            k += 1
        w = bg[i+1:k]
        low3h[idx[i]] = (w < 70).any() if len(w) else False
        k = i+1  # reset (simple O(n*36) fallback)
# NOTE simple recompute per i (window <=36 cycles) — fine at this size
df["low3h"] = low3h; df["min60"] = min60

print("="*20, "1. IOB-BY-PHASE SAFETY MAP", "="*20)
st_iob = df.groupby("state").iobn.agg(["median", lambda s: s.quantile(.75)])
st_iob.columns = ["median_iobn","p75_iobn"]
print("IOB (fraction of user TDD) by state:\n", (100*st_iob).round(1).astype(str) + " %TDD")
print("\nper-state pre-low rate (all cycles):", (100*df.groupby("state").low3h.mean()).round(1).to_dict())
dos = df[df.fd > 0]
bins = [0,.025,.05,.075,.10,.15,1.0]; labs = ["<2.5","2.5-5","5-7.5","7.5-10","10-15",">15"]
dos = dos.assign(ib=pd.cut(dos.iobn, bins, labels=labs))
base = df.assign(ib=pd.cut(df.iobn, bins, labels=labs))
tab = pd.DataFrame({
  "dosing_cycles": dos.groupby("ib", observed=True).size(),
  "prelow_when_dosing_%": (100*dos.groupby("ib", observed=True).low3h.mean()).round(1),
  "prelow_base_%": (100*base.groupby("ib", observed=True).low3h.mean()).round(1),
  "med_U": dos.groupby("ib", observed=True).fd.median().round(2)})
print("\nharm-vs-IOB curve (IOB bin as %TDD; dosing cycles fd>0):\n", tab)
hi_bg = dos[dos.cgm_mgdl>=140].groupby("ib", observed=True).low3h.mean()*100
print("\nprelow% when dosing, BG>=140 only:", hi_bg.round(1).to_dict())
early_states = dos[dos.state.isin(["OBSERVING","CONFIRMED"])]
late_states = dos[dos.state.isin(["RECOVERING"]) | ((dos.state=="COMMITTED")&(dos.age>=4))]
print(f"\ndosing in OBSERVING/CONFIRMED: n={len(early_states)}, med IOB {100*early_states.iobn.median():.1f}%TDD, prelow {100*early_states.low3h.mean():.1f}%")
print(f"dosing in RECOVERING/late-COMMITTED: n={len(late_states)}, med IOB {100*late_states.iobn.median():.1f}%TDD, prelow {100*late_states.low3h.mean():.1f}%")

print("\n"+"="*20, "2. CONFIRM LATENCY ANATOMY", "="*20)
confirms = []
for uid, g in df.groupby("user_id", sort=True):
    g = g.reset_index(); n=len(g)
    for i in range(1, n):
        if g.state.iloc[i]!="CONFIRMED" or g.state.iloc[i-1]=="CONFIRMED": continue
        # onset: earliest j in [i-12, i) with delta5[j]>3 and delta5[j+1]>3, contiguous data
        onset = None
        jlo = max(0, i-12)
        for j in range(jlo, i):
            if g.ts_epoch.iloc[i]-g.ts_epoch.iloc[j] > 3900: continue
            if pd.notna(g.delta5.iloc[j]) and g.delta5.iloc[j]>3 and j+1<=i and pd.notna(g.delta5.iloc[j+1]) and g.delta5.iloc[j+1]>3:
                onset = j; break
        if onset is None: continue
        # score history between onset and confirm
        sc = g.score.iloc[onset:i]
        first_pass = next((k for k in range(onset, i) if pd.notna(g.score.iloc[k]) and g.score.iloc[k]>=0.55), None)
        lat_cyc = i - onset
        lat_min = (g.ts_epoch.iloc[i]-g.ts_epoch.iloc[onset])/60
        mech = first_pass is not None and (i - first_pass) >= 2   # score ready >=2 cycles before confirm
        confirms.append(dict(user=uid, i=g["index"].iloc[i], onset_i=g["index"].iloc[onset],
            ts=g.ts_epoch.iloc[i], lat_cyc=lat_cyc, lat_min=lat_min, mech_limited=mech,
            score_m1=g.score.iloc[i-1] if i>=1 else np.nan, score_m2=g.score.iloc[i-2] if i>=2 else np.nan,
            iob_conf=g.iob.iloc[i], iob_m1=g.iob.iloc[i-1] if i>=1 else np.nan, iob_m2=g.iob.iloc[i-2] if i>=2 else np.nan,
            ts_m1=g.ts_epoch.iloc[i-1] if i>=1 else np.nan, ts_m2=g.ts_epoch.iloc[i-2] if i>=2 else np.nan,
            fd_conf=g.fd.iloc[i], low3h_conf=g.low3h.iloc[i],
            low3h_m1=g.low3h.iloc[i-1] if i>=1 else False, low3h_m2=g.low3h.iloc[i-2] if i>=2 else False,
            gap_early=float((g.v1_units.iloc[onset:i].fillna(0)-g.fd.iloc[onset:i]).clip(lower=0).sum()),
            bg_conf=g.cgm_mgdl.iloc[i]))
cf = pd.DataFrame(confirms)
print(f"fresh confirms with detectable rise onset: {len(cf)} (of all fresh confirms)")
print("onset->CONFIRMED latency: cycles", cf.lat_cyc.describe()[["25%","50%","75%"]].round(1).to_dict(),
      "| minutes", cf.lat_min.describe()[["25%","50%","75%"]].round(0).to_dict())
print("per-user median latency min:", cf.groupby("user").lat_min.median().round(0).to_dict())
print(f"mechanically limited (score>=0.55 ready >=2 cycles pre-confirm): {cf.mech_limited.sum()} ({100*cf.mech_limited.mean():.0f}%) — the rest are score-limited")

print("\n"+"="*20, "3. EARLY GAP vs HIGHS", "="*20)
# outcome per confirm: peak BG 2h, minutes>180 in 3h
peaks, m180 = [], []
for _, r in cf.iterrows():
    gu = df[df.user_id==r.user]
    fw = gu[(gu.ts_epoch>r.ts)&(gu.ts_epoch<=r.ts+10800)]
    peaks.append(fw[fw.ts_epoch<=r.ts+7200].cgm_mgdl.max() if len(fw) else np.nan)
    m180.append(5*int((fw.cgm_mgdl>180).sum()))
cf["peak2h"]=peaks; cf["min180_3h"]=m180
v = cf.dropna(subset=["peak2h"])
print(f"early gap (onset->confirm, U vs V1): med {v.gap_early.median():.2f} p75 {v.gap_early.quantile(.75):.2f} total {v.gap_early.sum():.0f}U across {len(v)} meals")
print(f"spearman(gap_early, peak2h) = {v.gap_early.corr(v.peak2h, method='spearman'):.3f}; spearman(gap_early, min>180) = {v.gap_early.corr(v.min180_3h, method='spearman'):.3f}")
t = v.assign(terc=pd.qcut(v.gap_early.rank(method="first"), 3, labels=["lo","mid","hi"]))
print(t.groupby("terc", observed=True).agg(gapU=("gap_early","median"), peak2h=("peak2h","median"), min180=("min180_3h","median"), prelow=("low3h_conf","mean")).round(2).to_string())

print("\n"+"="*20, "4. EARLY-CONFIRM COUNTERFACTUAL", "="*20)
for shift, scol, icol, lcol, tcol in ((1,"score_m1","iob_m1","low3h_m1","ts_m1"),(2,"score_m2","iob_m2","low3h_m2","ts_m2")):
    el = cf[(cf[scol]>=0.55) & cf[icol].notna() & (cf.fd_conf>0)]
    if not len(el): print(f"shift {shift}: none eligible"); continue
    U = el.fd_conf.sum()
    harm_new = 100*el[lcol].mean(); harm_act = 100*el.low3h_conf.mean()
    print(f"shift {shift} cycle(s) earlier: eligible {len(el)}/{len(cf)} confirms ({100*len(el)/len(cf):.0f}%), shifted insulin {U:.1f}U")
    print(f"  IOB at landing: actual med {el.iob_conf.median():.2f}U -> shifted med {el[icol].median():.2f}U (norm {100*(el.iob_conf/el.user.map(tddmed)).median():.1f}%TDD -> {100*(el[icol]/el.user.map(tddmed)).median():.1f}%TDD)")
    print(f"  pre-low(<70 in 3h) exposure of that insulin: actual {harm_act:.1f}% -> shifted {harm_new:.1f}% (late levers were 14-17%)")

print("\n"+"="*20, "5. FAST-PATH SWEEP", "="*20)
# eligible cycles: IDLE/OBSERVING, awake 07-23 local, min60>=80, no CONFIRMED in prior 90 min
df["conf_recent"] = False
for uid, g in df.groupby("user_id", sort=False):
    ct = g.ts_epoch.where(g.state=="CONFIRMED").ffill()
    df.loc[g.index, "conf_recent"] = (g.ts_epoch - ct) <= 5400
elig = df[df.state.isin(["IDLE","OBSERVING"]) & (~df.conf_recent) & (df.hour.between(7,22)) & (df.min60>=80)]
conf_ts = {u: g.ts.values for u,g in cf.groupby("user")}
def sweep(D,A,S):
    f = elig[(elig.delta5>=D)&(elig.accl>=A)&(elig.score>=S)]
    # dedup: one fire per 30-min window per user
    keep = []
    last = {}
    for _, r in f.sort_values(["user_id","ts_epoch"]).iterrows():
        if r.user_id in last and r.ts_epoch-last[r.user_id] < 1800: continue
        last[r.user_id] = r.ts_epoch; keep.append(r)
    f = pd.DataFrame(keep)
    if not len(f): return dict(fires=0)
    # caught earlier: an actual confirm within +60 min
    earlier = []
    for _, r in f.iterrows():
        cts = conf_ts.get(r.user_id, np.array([]))
        d = cts[(cts>r.ts_epoch)&(cts<=r.ts_epoch+3600)]
        earlier.append((d[0]-r.ts_epoch)/60 if len(d) else np.nan)
    f = f.assign(earlier_min=earlier)
    # false fire: avg delta5 over next 30 min < 3
    false_ct = 0
    for _, r in f.iterrows():
        gu = df[(df.user_id==r.user_id)&(df.ts_epoch>r.ts_epoch)&(df.ts_epoch<=r.ts_epoch+1800)]
        if len(gu) and gu.delta5.mean() < 3: false_ct += 1
    night = df[df.state.isin(["IDLE","OBSERVING"]) & (~df.conf_recent) & (~df.hour.between(7,22)) & (df.min60>=80) &
               (df.delta5>=D)&(df.accl>=A)&(df.score>=S)]
    return dict(fires=len(f), beat_confirm=f.earlier_min.notna().sum(),
        med_earlier_min=round(np.nanmedian(f.earlier_min),0) if f.earlier_min.notna().any() else None,
        false_fires=false_ct, false_pct=round(100*false_ct/len(f),0),
        prelow=int(f.low3h.sum()), prelow_pct=round(100*f.low3h.mean(),0),
        night_would_fire=len(night))
grid = [(8,15,0.60),(8,10,0.60),(6,15,0.60),(6,10,0.60),(8,15,0.55),(6,10,0.55),(8,10,0.55),(6,15,0.55),(6,10,0.65)]
res = {f"D{d} A{a} S{s}": sweep(d,a,s) for d,a,s in grid}
print(pd.DataFrame(res).T.to_string())

print("\n"+"="*20, "6. BLOCKED-CONFIRM AUDIT (capped era)", "="*20)
ERAS = {"tim":[("2026-06-01",.25),("2026-06-12",.5),("2026-06-14",.4)],"A":[("2026-06-17",.25),("2026-07-01",.5)],
 "B":[("2026-06-18",.25),("2026-07-01",.5),("2026-07-02",.6)],"C":[("2026-06-19",.25)],"D":[("2026-06-17",.25)],
 "E":[("2026-06-17",.25),("2026-06-30",.5)],"F":[("2026-06-18",.25),("2026-06-29",.5)]}
df["date"] = pd.to_datetime(df.ts_utc, utc=True, format="mixed").dt.date
def op_cap(u,d):
    c=None
    for s,v in ERAS.get(u,[]):
        if d>=pd.to_datetime(s).date(): c=v
    return c
cf["date"] = cf.i.map(df.date); cf["cap"] = [op_cap(u,d) for u,d in zip(cf.user, cf.date)]
cf["budget_conf"] = cf.i.map(df.budget)
v1p95 = df[df.v1_units>0].groupby("user_id").v1_units.quantile(.95).clip(1.5,7.5)
cc = cf[cf.cap.notna()].copy()
cc["floor"] = np.minimum(cc.cap, 0.8*cc.user.map(v1p95))
for nm, shot in (("vf=1", cc.budget_conf*1.8), ("vf=0.4", cc.budget_conf*1.8*0.4)):
    b = cc[shot <= cc["floor"]]
    hi = fz = 0; hi_u = {}
    for _, r in b.iterrows():
        gu = df[(df.user_id==r.user)&(df.ts_epoch>r.ts)&(df.ts_epoch<=r.ts+5400)]
        if len(gu)==0: continue
        if (gu.cgm_mgdl>180).any(): hi += 1; hi_u[r.user] = hi_u.get(r.user,0)+1
        elif (gu.cgm_mgdl<160).all(): fz += 1
    print(f"{nm}: blocked {len(b)}/{len(cc)} capped-era confirms | BG>180 within 90min after: {hi} ({100*hi/max(len(b),1):.0f}%) [needed commit] | stayed<160: {fz} ({100*fz/max(len(b),1):.0f}%) [gate correct] | >180 per-user {hi_u}")

print("\n"+"="*20, "7. MEAL-TIME REGULARITY", "="*20)
# all rise onsets: delta5>3 x2 consecutive, preceded by 2 cycles delta5<=3
ons = []
for uid, g in df.groupby("user_id", sort=True):
    d = g.delta5.values; h = g.hour.values; ts=g.ts_epoch.values
    for i in range(2, len(g)-1):
        if d[i]>3 and d[i+1]>3 and not (d[i-1]>3) and not (d[i-2]>3) and pd.notna(d[i]) and pd.notna(d[i+1]):
            ons.append((uid, h[i] + (ts[i]%3600)/3600*0))  # hour resolution
o = pd.DataFrame(ons, columns=["user","hr"])
for uid, g in o.groupby("user"):
    hist = g.hr.value_counts().sort_index()
    top3 = hist.nlargest(3).index.tolist()
    near = g.hr.apply(lambda x: any(min(abs(x-m), 24-abs(x-m))<=1.5 for m in top3)).mean()
    tag = " <-- TIM" if uid=="tim" else ""
    print(f"{uid}: {len(g)} onsets, top-3 modal hours(local) {sorted(top3)}, within +/-90min of modes: {100*near:.0f}%{tag}")
cf.to_csv(f"{SP}/confirm_events.csv", index=False)
