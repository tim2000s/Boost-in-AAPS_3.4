#!/usr/bin/env python3
"""committedCapU raise evaluation. Era-aware operative caps detected from COMMITTED dose ceilings."""
import psycopg2, pandas as pd, numpy as np

SP = "/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad"
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
  user_id, ts_epoch, ts_utc, cgm_mgdl, boostv5_state AS state, boostv5_age AS age,
  boostv5_finaldose AS fd, boostv5_budget AS budget, v1_units, iob_iob
FROM boost_decisions WHERE boostv5_state IS NOT NULL
ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
""", conn).sort_values(["user_id","ts_epoch"]).reset_index(drop=True)
df["date"] = pd.to_datetime(df.ts_utc, utc=True, format="mixed").dt.date

# operative cap eras (start_date inclusive -> cap), detected from daily COMMITTED dose ceilings
ERAS = {
 "tim": [("2026-06-01",0.25),("2026-06-12",0.50),("2026-06-14",0.40)],
 "A":   [("2026-06-17",0.25),("2026-07-01",0.50)],
 "B":   [("2026-06-18",0.25),("2026-07-01",0.50),("2026-07-02",0.60)],
 "C":   [("2026-06-19",0.25)],
 "D":   [("2026-06-17",0.25)],
 "E":   [("2026-06-17",0.25),("2026-06-30",0.50)],
 "F":   [("2026-06-18",0.25),("2026-06-29",0.50)],
}
def op_cap(uid, d):
    cap = None
    for start, c in ERAS.get(uid, []):
        if d >= pd.to_datetime(start).date(): cap = c
    return cap
df["cap"] = [op_cap(u, d) for u, d in zip(df.user_id, df.date)]
df["capped_era"] = df.cap.notna()
df["clipped"] = (df.state=="COMMITTED") & df.capped_era & (df.fd >= 0.95*df.cap) & (df.fd>0)

# auto-config formula proxies (for Q5b)
users = {}
for uid, g in df.groupby("user_id"):
    v1pos = g.v1_units[g.v1_units>0]
    p75 = v1pos.quantile(.75) if len(v1pos) else 0
    p85 = v1pos.quantile(.85) if len(v1pos) else 0
    p95 = v1pos.quantile(.95) if len(v1pos) else 0
    users[uid] = dict(p75=p75, p85=p85, confcap=np.clip(p95,1.5,7.5))

print("===== Q1: does the cap bind? (COMMITTED cycles, capped era only) =====")
ce = df[(df.state=="COMMITTED") & df.capped_era]
q1 = ce.groupby("user_id").agg(n=("fd","size"), n_pos=("fd", lambda s:(s>0).sum()),
    n_clip=("clipped","sum"), days=("date","nunique"), cap_now=("cap","last"))
q1["clip_pct_all"] = (100*q1.n_clip/q1.n).round(0)
q1["clip_pct_pos"] = (100*q1.n_clip/q1.n_pos).round(0)
print(q1)
print(f"TOTAL: {len(ce)} capped-era COMMITTED cycles, {ce.clipped.sum()} clipped ({100*ce.clipped.mean():.0f}% of all, {100*ce.clipped.sum()/max((ce.fd>0).sum(),1):.0f}% of dosing cycles)")

# ===== meal phases: fresh CONFIRMED -> until state leaves CONFIRMED/COMMITTED =====
phases = []
for uid, g in df.groupby("user_id", sort=True):
    g = g.reset_index(drop=True); n=len(g)
    i=0
    while i < n:
        fresh = g.state.iloc[i]=="CONFIRMED" and (i==0 or g.state.iloc[i-1]!="CONFIRMED")
        if not fresh: i+=1; continue
        j=i
        while j+1<n and g.state.iloc[j+1] in ("CONFIRMED","COMMITTED") and g.ts_epoch.iloc[j+1]-g.ts_epoch.iloc[j]<=600: j+=1
        ph = g.iloc[i:j+1]
        end_ts = g.ts_epoch.iloc[j]
        fw = g[(g.ts_epoch>end_ts)]
        fw2h = fw[fw.ts_epoch<=end_ts+7200]; fw3h = fw[fw.ts_epoch<=end_ts+10800]
        # stuck-high proxy: BG>160 at 90min after phase end AND never <160 in 2h
        bg90 = fw[(fw.ts_epoch>=end_ts+4800)&(fw.ts_epoch<=end_ts+6000)]
        stuck = bool(len(fw2h)) and not (fw2h.cgm_mgdl<160).any() and bool(len(bg90)) and (bg90.cgm_mgdl>160).all()
        low = bool((fw3h.cgm_mgdl<70).any()) if len(fw3h) else False
        under = (ph.v1_units.fillna(0)-ph.fd).clip(lower=0)
        under_clip = under[ph.clipped].sum(); under_unclip = under[~ph.clipped].sum()
        phases.append(dict(user=uid, start_ts=g.ts_epoch.iloc[i], end_ts=end_ts, ncyc=len(ph),
            capped_era=bool(ph.capped_era.all()), n_clip=int(ph.clipped.sum()),
            under_clip=under_clip, under_unclip=under_unclip,
            v6_sum=ph.fd.sum(), v1_sum=ph.v1_units.fillna(0).sum(), stuck=stuck, low=low))
        i=j+1
ph = pd.DataFrame(phases)
print(f"\n===== Q2: meal phases (fresh CONFIRMED -> leave meal state): {len(ph)} total, {ph.capped_era.sum()} in capped era =====")
pce = ph[ph.capped_era]
print(f"capped-era phases with >=1 clipped cycle: {(pce.n_clip>0).sum()} ({100*(pce.n_clip>0).mean():.0f}%)")
print(f"under-delivery vs V1 in capped-era phases: on clipped cycles {pce.under_clip.sum():.1f}U vs on unclipped cycles {pce.under_unclip.sum():.1f}U")
print("clipped phases -> stuck-high rate: {:.0f}% ({} of {}) | unclipped phases: {:.0f}% ({} of {})".format(
    100*pce[pce.n_clip>0].stuck.mean(), pce[pce.n_clip>0].stuck.sum(), (pce.n_clip>0).sum(),
    100*pce[pce.n_clip==0].stuck.mean(), pce[pce.n_clip==0].stuck.sum(), (pce.n_clip==0).sum()))
print("clipped phases -> low<70 in 3h: {:.0f}% | unclipped: {:.0f}%".format(
    100*pce[pce.n_clip>0].low.mean(), 100*pce[pce.n_clip==0].low.mean()))

# episodes / residual overlap with capped era
ep = pd.read_csv(f"{SP}/episodes_v2.csv")
ep["start_ts"] = (pd.to_datetime(ep.start, utc=True, format="mixed") - pd.Timestamp(0,tz="utc")).dt.total_seconds()
ep["date"] = pd.to_datetime(ep.start, utc=True, format="mixed").dt.date
ep["in_cap_era"] = [op_cap(u,d) is not None for u,d in zip(ep.user, ep.date)]
ep["residual"] = (ep.resolved_2h==False)&(ep.iob_falling==True)&(ep.reengaged_90m==False)
print(f"\n606-episode set: {ep.in_cap_era.sum()} in capped era; residual 26: {ep[ep.residual].in_cap_era.sum()} in capped era")
# for capped-era episodes: was preceding meal phase clipped?
epc = ep[ep.in_cap_era]
clip_before = []
for _,r in epc.iterrows():
    m = ph[(ph.user==r.user)&(ph.end_ts<=r.start_ts)&(ph.end_ts>=r.start_ts-5400)]
    clip_before.append(int(m.n_clip.sum()) if len(m) else 0)
epc = epc.assign(clip_before=clip_before)
print(f"capped-era episodes preceded (<=90min) by clipped meal phase: {(epc.clip_before>0).sum()}/{len(epc)}")

print("\n===== Q3: counterfactual cap raise (clipped cycles, capped era) =====")
cl = df[df.clipped].copy()
for mult in (1.5, 2.0):
    cl["newcap"] = np.minimum(cl.cap*mult, 2.5)
    # upper: vf=1 -> min(budget,newcap)-fd ; lower: vf=0.4 -> min(max(0.4*budget, fd), newcap)-fd
    cl["ex_up"] = (np.minimum(cl.budget.fillna(cl.newcap), cl.newcap) - cl.fd).clip(lower=0)
    cl["ex_lo"] = (np.minimum(np.maximum(0.4*cl.budget.fillna(0), cl.fd), cl.newcap) - cl.fd).clip(lower=0)
    # outcomes per clipped cycle
    lows, res = [], []
    for uid, g in cl.groupby("user_id"):
        gu = df[df.user_id==uid]
        for _, r in g.iterrows():
            fw3 = gu[(gu.ts_epoch>r.ts_epoch)&(gu.ts_epoch<=r.ts_epoch+10800)]
            lows.append(bool((fw3.cgm_mgdl<70).any()) if len(fw3) else False)
    cl["low3h"] = lows
    days = df[df.capped_era].groupby("user_id").date.nunique().sum()
    tot_up, tot_lo = cl.ex_up.sum(), cl.ex_lo.sum()
    low_up, low_lo = cl[cl.low3h].ex_up.sum(), cl[cl.low3h].ex_lo.sum()
    print(f"\n--- cap x{mult} ---")
    print(f"extra U total: lo(vf=0.4)={tot_lo:.1f} up(vf=1)={tot_up:.1f} over {days} capped user-days ({tot_lo/days:.2f}-{tot_up/days:.2f} U/user-day)")
    print(f"to cycles followed by <70 in 3h: lo={low_lo:.1f} up={low_up:.1f} ({100*low_lo/max(tot_lo,1e-9):.0f}%/{100*low_up/max(tot_up,1e-9):.0f}%) | clipped cycles ->low3h: {cl.low3h.mean()*100:.0f}%")
    pu = cl.groupby("user_id").agg(nclip=("fd","size"), ex_lo=("ex_lo","sum"), ex_up=("ex_up","sum"))
    pud = df[df.capped_era].groupby("user_id").date.nunique()
    pu["U_day_lo"] = (pu.ex_lo/pud).round(2); pu["U_day_up"] = (pu.ex_up/pud).round(2)
    print(pu.round(1).to_string())

print("\n===== Q4: confirm-floor coupling =====")
conf = df[(df.state=="CONFIRMED") & df.capped_era].copy()
conf["fresh"] = conf.age.fillna(0)==0
fc = conf[conf.fresh].copy()
fc["shot_hi"] = fc.budget*1.8; fc["shot_lo"] = fc.budget*1.8*0.4
rows=[]
for mult in (1.0, 1.5, 2.0):
    blocked_hi = blocked_lo = blocked_fd = 0
    for _,r in fc.iterrows():
        cc = users[r.user_id]["confcap"]
        floor = min(min(r.cap*mult, 2.5), 0.8*cc)
        blocked_hi += r.shot_hi <= floor
        blocked_lo += r.shot_lo <= floor
        blocked_fd += r.fd <= floor
    rows.append((mult, len(fc), blocked_hi, blocked_lo, blocked_fd))
for mult,n,bh,bl,bf in rows:
    print(f"cap x{mult}: fresh confirms={n} | blocked if vf=1: {bh} ({100*bh/n:.0f}%) | vf=0.4: {bl} ({100*bl/n:.0f}%) | by delivered dose: {bf} ({100*bf/n:.0f}%)")
# tim-only
ft = fc[fc.user_id=="tim"]
for mult in (1.0,1.5,2.0):
    cc = users["tim"]["confcap"]
    fl = ft.apply(lambda r: min(min(r.cap*mult,2.5), 0.8*cc), axis=1)
    print(f"  tim cap x{mult}: {len(ft)} confirms, blocked vf=1: {(ft.shot_hi<=fl).sum()}, vf=0.4: {(ft.shot_lo<=fl).sum()}, delivered: {(ft.fd<=fl).sum()}")
print("confcap proxies:", {u:round(v['confcap'],2) for u,v in users.items()})
print("autoconfig committedCap p75-based:", {u:round(np.clip(max(v['p75'], np.nan_to_num(0)),0.25,2.5),2) for u,v in users.items()})
print("autoconfig committedCap p85-based:", {u:round(np.clip(v['p85'],0.25,2.5),2) for u,v in users.items()})
