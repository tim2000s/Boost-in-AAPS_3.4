#!/usr/bin/env python3
"""A. Evening confirm-overshoot backtest.

Fresh CONFIRMED commit shots (state=CONFIRMED, age=0), deduped (last row per
5-min bucket). Evening band = 19:00-24:00 local (hour = UTC+1, BST cohort).
Pre-sleep proxy = confirm at local hour >= 22 (IOB carried toward sleep).

Outcome per confirm (forward from confirm ts):
  nadir4h  = min BG within 4h
  low70_4h = nadir4h < 70 ; low54 = nadir4h < 54
  peak3h   = max BG within 3h (the meal's realized top)
  sustained180 = >=3 consecutive cycles > 180 within 45 min (meal real, not fizzle)
  fizzle   = peak within 45 min <= 180 AND BG turns down (delta<0) by +45 min
  needed_U = max(0, (peak3h - target)/ISF)   ISF=variable_sens at confirm
  over_ratio = delivered / max(base_would, 0.05)   base_would = v1_units
Caveat: v1_units on a meal-state override row records the delivered SMB, so
'base-would' is reconstructed as the prospective-shot pipeline instead where
needed; we report both and flag the ambiguity.
"""
import numpy as np, pandas as pd, psycopg2, os, sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
 user_id, ts_epoch, ts_utc, cgm_mgdl bg, boostv5_state state, boostv5_age age,
 boostv5_finaldose fd, boostv5_prospectiveshot prosp, boostv5_budget budget,
 boostv5_confirmedcap ccap, boostv5_aggressionknob knob, v1_units,
 variable_sens isf, sug_current_target tgt
FROM boost_decisions WHERE boostv5_state IS NOT NULL
ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
""", conn).sort_values(["user_id","ts_epoch"]).reset_index(drop=True)
conn.close()
dtc = pd.to_datetime(df.ts_utc, utc=True, format="mixed")
df["hour"] = (dtc.dt.hour + 1) % 24            # local ~ UTC+1
df["date14"] = df.ts_epoch >= df.ts_epoch.max() - 14*86400

# forward windows per user
def fwd(g):
    ts=g.ts_epoch.values; bg=g.bg.values; n=len(g)
    nad4=np.full(n,np.nan); pk3=np.full(n,np.nan); sust=np.zeros(n,bool); fizz=np.zeros(n,bool)
    d45=np.full(n,np.nan)
    for i in range(n):
        w4=bg[(ts>ts[i])&(ts<=ts[i]+14400)]
        w3=bg[(ts>ts[i])&(ts<=ts[i]+10800)]
        w45=bg[(ts>ts[i])&(ts<=ts[i]+2700)]
        if len(w4): nad4[i]=w4.min()
        if len(w3): pk3[i]=w3.max()
        # sustained >180: >=3 consecutive over-180 in first 45min
        if len(w45):
            over=(w45>180).astype(int)
            run=0; mx=0
            for o in over:
                run=run+1 if o else 0; mx=max(mx,run)
            sust[i]=mx>=3
            pk45=w45.max()
            # turn down by +45: last of window below its own peak by >5
            fizz[i]=(pk45<=180) and (w45[-1] < pk45-5)
            d45[i]=w45[-1]-bg[i]
    return pd.DataFrame(dict(nad4=nad4,pk3=pk3,sust=sust,fizz=fizz,d45=d45), index=g.index)
df=df.join(pd.concat([fwd(g) for _,g in df.groupby("user_id",sort=False)]))

fc = df[(df.state=="CONFIRMED") & (df.age==0)].copy()
fc["evening"] = fc.hour.between(19,23)          # 19:00-23:59 local
fc["presleep"] = fc.hour>=22
fc["low70"] = fc.nad4<70
fc["low54"] = fc.nad4<54
fc["base_would"] = fc.v1_units.fillna(0)        # NOTE: records delivered on override rows
fc["over2x"] = fc.fd >= 2*np.maximum(fc.base_would,0.05)
fc["needed"] = np.maximum(0,(fc.pk3-fc.tgt)/fc.isf)
fc["over_deliver"] = fc.fd - fc.needed          # delivered minus retrospectively-needed
fc.to_csv(f"{OUT}/fresh_confirms.csv", index=False)

def blk(g):
    return pd.Series(dict(n=len(g), medU=round(g.fd.median(),2), p90U=round(g.fd.quantile(.9),2),
        low70=round(100*g.low70.mean(),1), low54=round(100*g.low54.mean(),1),
        med_nadir=round(g.nad4.median()), fizz=round(100*g.fizz.mean(),1),
        sust180=round(100*g.sust.mean(),1)))

print("=== 1. EVENING vs DAYTIME fresh confirms (cohort) ===")
fc["band"]=np.where(fc.evening,"evening(19-24)",np.where(fc.hour.between(7,18),"day(7-19)","night(0-7)"))
print(fc.groupby("band").apply(blk).to_string())
print("\npre-sleep (>=22h local) vs rest of evening:")
ev=fc[fc.evening]
print(ev.groupby("presleep").apply(blk).to_string())
print("\nper-user evening vs day low70 rate (n>=5 each):")
for u in ["tim","A","B","C","D","E","F"]:
    g=fc[fc.user_id==u]
    e=g[g.evening]; d=g[g.hour.between(7,18)]
    if len(e)>=5 and len(d)>=5:
        print(f"  {u}: evening n={len(e)} low70={100*e.low70.mean():.0f}% low54={100*e.low54.mean():.0f}% medU={e.fd.median():.2f} | day n={len(d)} low70={100*d.low70.mean():.0f}% low54={100*d.low54.mean():.0f}% medU={d.fd.median():.2f}")

print("\n=== 2. OVERSIZED confirm anatomy (delivered >= 2x base-would) ===")
ov=fc[fc.over2x]
print(f"oversized confirms: {len(ov)} of {len(fc)} ({100*len(ov)/len(fc):.0f}%); evening share {100*ov.evening.mean():.0f}%")
print(f"  prospective vs delivered: prosp med {ov.prosp.median():.2f}, capped-at-ccap {100*(ov.fd>=ov.ccap-0.01).mean():.0f}%")
print(f"  size drivers (median): budget {ov.budget.median():.2f}, knob {ov.knob.median():.2f}, prosp/budget ratio {(ov.prosp/ov.budget.replace(0,np.nan)).median():.2f} (=1.8*knob*vf)")
print(f"  outcomes: fizzle {100*ov.fizz.mean():.0f}%, sustained>180 {100*ov.sust.mean():.0f}%, low70-4h {100*ov.low70.mean():.0f}%, low54 {100*ov.low54.mean():.0f}%")
print(f"  CALIBRATION delivered vs needed: over-deliver med {ov.over_deliver.median():.2f}U; delivered>needed on {100*(ov.over_deliver>0).mean():.0f}%")
print(f"  evening oversized only: n={ov.evening.sum()}, fizzle {100*ov[ov.evening].fizz.mean():.0f}%, low70 {100*ov[ov.evening].low70.mean():.0f}%, over-deliver med {ov[ov.evening].over_deliver.median():.2f}U")
print("\nall confirms calibration (delivered vs needed-from-actual-peak):")
print(f"  over-deliver med {fc.over_deliver.median():.2f}U | delivered>needed {100*(fc.over_deliver>0).mean():.0f}% | evening {fc[fc.evening].over_deliver.median():.2f} vs day {fc[fc.hour.between(7,18)].over_deliver.median():.2f}")

print("\n=== 2b. CALIBRATION split by fizzle vs real-meal (the crux) ===")
for lbl,mask in [("fizzle",fc.fizz),("sustained>180",fc.sust),("neither",~fc.fizz&~fc.sust)]:
    g=fc[mask]
    print(f"  {lbl}: n={len(g)} medU={g.fd.median():.2f} med_needed={g.needed.median():.2f} over-deliver med={g.over_deliver.median():.2f}U low70={100*g.low70.mean():.0f}% low54={100*g.low54.mean():.0f}%")
print("  pre-sleep(>=22h) split:")
for lbl,mask in [("fizzle",fc.presleep&fc.fizz),("sustained",fc.presleep&fc.sust)]:
    g=fc[mask]
    if len(g): print(f"    presleep {lbl}: n={len(g)} medU={g.fd.median():.2f} over-deliver={g.over_deliver.median():.2f}U low54={100*g.low54.mean():.0f}%")

# incident row
inc = fc[(fc.user_id=="tim") & (fc.ts_epoch.between(pd.Timestamp("2026-07-06 22:40",tz="UTC").timestamp(),pd.Timestamp("2026-07-06 22:50",tz="UTC").timestamp()))]
print("\n  INCIDENT (tim 07-06 22:44Z):")
if len(inc):
    r=inc.iloc[0]
    print(f"    fd={r.fd} prosp={r.prosp} budget={r.budget} knob={r.knob} ccap={r.ccap} peak3h={r.pk3:.0f} needed={r.needed:.2f}U over-deliver={r.over_deliver:.2f}U nadir4h={r.nad4:.0f} low54={r.low54} fizzle={r.fizz} sust={r.sust}")

print("\n=== 3. MITIGATIONS priced (removal levers -> reduce hypo; cost = under-covered real meals) ===")
days_by_user = {u: (df[df.user_id==u].ts_epoch.max()-df[df.user_id==u].ts_epoch.min())/86400 for u in fc.user_id.unique()}
def isf_of(u): return fc[fc.user_id==u].isf.median()
def price(label, mask, new_fd):
    g=fc[mask].copy(); g["new"]=new_fd[mask]; g["rem"]=(g.fd-g["new"]).clip(lower=0)
    tot=g.rem.sum()
    rem_fizz=g.loc[g.fizz,"rem"].sum(); rem_sust=g.loc[g.sust,"rem"].sum()
    rem_low54=g.loc[g.low54,"rem"].sum()
    # tim-specific
    gt=g[g.user_id=="tim"]
    print(f"  [{label}] confirms affected={len(g)} removed={tot:.1f}U | on fizzles {100*rem_fizz/max(tot,1e-9):.0f}% (good) on real-meals {100*rem_sust/max(tot,1e-9):.0f}% (cost) | on low54-preceding {100*rem_low54/max(tot,1e-9):.0f}%")
    print(f"       tim: affected={len(gt)} removed={gt.rem.sum():.2f}U, on his low54 confirms {gt.loc[gt.low54,'rem'].sum():.2f}U")
    return g

# (a) pre-sleep damper x0.6
price("a: presleep(>=22h) x0.6", fc.presleep, fc.fd*0.6)
# (a2) presleep cap at base-would*1.5 proxy = budget*1.0*1.5 (committed-equiv x1.5)
price("a2: presleep cap min(fd, budget*1.5)", fc.presleep, np.minimum(fc.fd, fc.budget*1.5))
# (b) first-shot staged cap at 1.5U absolute (all confirms, all bands)
price("b: first confirm cap 1.5U (staged)", pd.Series(True,index=fc.index), np.minimum(fc.fd,1.5))
# (b2) staged cap at committed-equiv*2 = budget*2
price("b2: first confirm cap min(fd, budget*2.0)", pd.Series(True,index=fc.index), np.minimum(fc.fd, fc.budget*2.0))
# (c) knob-neutral evening confirms (remove the 1.3x from the commit shot)
kn = np.where((fc.evening)&(fc.knob>1), np.minimum(fc.ccap, fc.prosp/fc.knob), fc.fd)
price("c: knob-neutral evening (prosp/knob)", fc.evening, pd.Series(kn,index=fc.index))

print("\n=== 4. tim trailing-14d TBR (incl. last night) ===")
conn2=psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
tcg=pd.read_sql("""SELECT DISTINCT ON (floor(ts_epoch/300.0)) cgm_mgdl bg, ts_epoch
FROM boost_decisions WHERE user_id='tim' ORDER BY floor(ts_epoch/300.0), ts_epoch DESC""",conn2)
conn2.close()
t14=tcg[tcg.ts_epoch>=tcg.ts_epoch.max()-14*86400]
print(f"  n={len(t14)} cycles | TBR<70 = {100*(t14.bg<70).mean():.2f}% | TBR<54 = {100*(t14.bg<54).mean():.2f}%")
# without last night's episode window (00:00-03:00Z 07-07)
inc_lo,inc_hi=pd.Timestamp("2026-07-06 23:30",tz="UTC").timestamp(),pd.Timestamp("2026-07-07 04:00",tz="UTC").timestamp()
t14x=t14[~t14.ts_epoch.between(inc_lo,inc_hi)]
print(f"  excluding the incident night window: TBR<70={100*(t14x.bg<70).mean():.2f}% TBR<54={100*(t14x.bg<54).mean():.2f}% (incident contributes {100*(t14.bg<54).mean()-100*(t14x.bg<54).mean():.2f}pp to <54)")
