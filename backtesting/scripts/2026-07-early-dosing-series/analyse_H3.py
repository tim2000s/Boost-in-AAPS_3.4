#!/usr/bin/env python3
"""Part 3: counterfactual committedCap raise, era meal-peak comparison, daily totals."""
import re
import numpy as np, pandas as pd, psycopg2
conn = psycopg2.connect("dbname=oref")
dec = pd.read_sql("""SELECT ts_utc, variant, v1_units, boostv5_state, boostv5_finaldose,
  boostv5_budget, reason_text FROM boost_decisions WHERE user_id='H' ORDER BY ts_utc""", conn)
cgm = pd.read_sql("SELECT ts_utc, cgm_mgdl FROM boost_cgm WHERE user_id='H' ORDER BY ts_utc", conn)
dec["ts_utc"]=pd.to_datetime(dec.ts_utc,utc=True); cgm["ts_utc"]=pd.to_datetime(cgm.ts_utc,utc=True)
dec["bucket"]=dec.ts_utc.dt.floor("5min"); dec=dec.sort_values("ts_utc").groupby("bucket",as_index=False).last()
cgm["bucket"]=cgm.ts_utc.dt.floor("5min"); cgm=cgm.sort_values("ts_utc").groupby("bucket",as_index=False).last().set_index("bucket")
c=cgm.cgm_mgdl.resample("5min").median().interpolate(limit=2)
def base_would(r):
    if not isinstance(r,str): return np.nan
    m=re.search(r"base would=([\d.]+)U",r) or re.search(r"base SMB ([\d.]+)U",r)
    return float(m.group(1)) if m else np.nan
dec["base_would"]=dec.reason_text.apply(base_would)

# episodes across whole record
rise35=c-c.shift(7); on=(rise35>=30)&((rise35.shift(1)<30)|rise35.shift(1).isna())
eps=[]
for t in c.index[on.fillna(False)]:
    if eps and (t-eps[-1])<pd.Timedelta("90min"): continue
    eps.append(t)
V6S=pd.Timestamp("2026-06-29 22:00",tz="UTC")
def ep_metrics(t0):
    w=c[t0:t0+pd.Timedelta("3h")]
    if w.empty or w.isna().all(): return None
    return dict(peak=w.max(), over180=(w>180).sum()*5, over140=(w>140).sum()*5)
rows=[]
for t in eps:
    m=ep_metrics(t)
    if m: m["era"]="V6" if t>=V6S else ("V1-recent" if t>=V6S-pd.Timedelta(days=21) else "V1-older"); m["hr"]=t.tz_convert("Etc/GMT-2").hour; rows.append(m)
E=pd.DataFrame(rows)
print("=== MEAL EPISODE OUTCOMES BY ERA (3h window) ===")
print(E.groupby("era").agg(n=("peak","size"),peak_med=("peak","median"),peak_p75=("peak",lambda x:x.quantile(.75)),
      min180_med=("over180","median"),min180_mean=("over180","mean"),min140_mean=("over140","mean")).round(0))

# daily V6 vs base totals (V6 era only)
v6=dec[dec.variant=="boost-other"].copy(); v6["d"]=v6.bucket.dt.tz_convert("Etc/GMT-2").dt.date
g=v6.groupby("d").agg(v6u=("v1_units",lambda x:x.fillna(0).sum()), baseu=("base_would",lambda x:x.fillna(0).sum()))
print("\n=== DAILY SMB: V6 delivered vs base-would (V6 era) ===")
print(g.round(1))
print(f"total: V6={g.v6u.sum():.1f}U base={g.baseu.sum():.1f}U ratio={g.v6u.sum()/g.baseu.sum():.2f}")

# counterfactual on clipped COMMITTED cycles in meal-phase
md=[]
for t0 in [t for t in eps if t>=V6S]:
    d=v6[(v6.bucket>=t0)&(v6.bucket<t0+pd.Timedelta("90min"))].copy(); md.append(d)
md=pd.concat(md)
clip=md[(md.boostv5_state=="COMMITTED")&(md.boostv5_finaldose>=0.489)]
lo=np.minimum(clip.boostv5_budget*0.4,1.24); hi=np.minimum(clip.boostv5_budget*1.0,1.24)
print(f"\n=== COUNTERFACTUAL committedCap 0.5→1.24 on his {len(clip)} clipped meal-phase COMMITTED cycles ===")
print(f"delivered now: {clip.boostv5_finaldose.sum():.1f}U; with cap 1.24: {lo.sum():.1f}U (slow-meal vf=0.4) … {hi.sum():.1f}U (vf=1.0)")
print(f"base engine wanted on those cycles: {clip.base_would.fillna(0).sum():.1f}U")
# how often budget*vf even exceeds 0.5 (i.e. cap truly binding, not budget-limited)
print(f"clipped cycles where budget*0.4 > 0.5 (cap binding even at slow-meal scaling): {(clip.boostv5_budget*0.4>0.5).sum()}/{len(clip)}")
print(f"budget on clipped cycles p25/50/75: {clip.boostv5_budget.quantile(.25):.2f}/{clip.boostv5_budget.median():.2f}/{clip.boostv5_budget.quantile(.75):.2f}U")
conn.close()
