#!/usr/bin/env python3
"""Part 2: under-delivery decomposition by state+mechanism; confirm-floor coupling."""
import re
import numpy as np, pandas as pd, psycopg2
conn = psycopg2.connect("dbname=oref")
dec = pd.read_sql("""
  SELECT ts_utc, variant, cgm_mgdl, v1_units, boostv5_state, boostv5_finaldose,
         boostv5_budget, boostv5_actionmult, boostv5_age, boostv5_gatereduction, reason_text
  FROM boost_decisions WHERE user_id='H' AND variant='boost-other' ORDER BY ts_utc
""", conn)
cgm = pd.read_sql("SELECT ts_utc, cgm_mgdl FROM boost_cgm WHERE user_id='H' AND ts_utc>='2026-06-29' ORDER BY ts_utc", conn)
dec["ts_utc"]=pd.to_datetime(dec.ts_utc,utc=True); cgm["ts_utc"]=pd.to_datetime(cgm.ts_utc,utc=True)
dec["bucket"]=dec.ts_utc.dt.floor("5min"); dec=dec.sort_values("ts_utc").groupby("bucket",as_index=False).last()
cgm["bucket"]=cgm.ts_utc.dt.floor("5min"); cgm=cgm.sort_values("ts_utc").groupby("bucket",as_index=False).last().set_index("bucket")
c = cgm.cgm_mgdl.resample("5min").median().interpolate(limit=2)

def base_would(r):
    if not isinstance(r,str): return np.nan
    m=re.search(r"base would=([\d.]+)U",r) or re.search(r"base SMB ([\d.]+)U",r)
    return float(m.group(1)) if m else np.nan
dec["base_would"]=dec.reason_text.apply(base_would)
dec["suppressed"]=dec.reason_text.str.contains("V6 suppressed",na=False)

# same episode detection
rise35=c-c.shift(7)
onset=(rise35>=30)&((rise35.shift(1)<30)|rise35.shift(1).isna())
eps=[]
for t in c.index[onset.fillna(False)]:
    if eps and (t-eps[-1])<pd.Timedelta("90min"): continue
    eps.append(t)
eps=[t for t in eps if t>=pd.Timestamp("2026-06-29 22:00",tz="UTC")]

md=[]
for t0 in eps:
    d=dec[(dec.bucket>=t0)&(dec.bucket<t0+pd.Timedelta("90min"))].copy()
    d["ep"]=str(t0)
    md.append(d)
md=pd.concat(md)
md["v6u"]=md.v1_units.fillna(0); md["baseu"]=md.base_would.fillna(0)
md["gap"]=(md.baseu-md.v6u).clip(lower=0)
CC,CF=0.5,2.5
md["cap"]=np.where(md.boostv5_state=="COMMITTED",CC,np.where(md.boostv5_state=="CONFIRMED",CF,np.inf))
md["capclipped"]=md.v6u>=md.cap-0.011
tot=md.gap.sum()
print(f"meal-phase (90min) cycles={len(md)}  V6={md.v6u.sum():.1f}U base-would={md.baseu.sum():.1f}U gap={tot:.1f}U")
print("\ngap by state / cap-clipped:")
g=md.groupby(["boostv5_state","capclipped"]).agg(cycles=("gap","size"),gapU=("gap","sum"),v6U=("v6u","sum"),baseU=("baseu","sum")).round(2)
print(g)
print(f"\ngap on cap-clipped cycles: {md.gap[md.capclipped].sum():.2f}U ({md.gap[md.capclipped].sum()/tot*100:.0f}%)")
print(f"gap on BELOW-cap cycles:   {md.gap[~md.capclipped].sum():.2f}U ({md.gap[~md.capclipped].sum()/tot*100:.0f}%)")
print(f"gap on suppressed(sleep) cycles: {md.gap[md.suppressed].sum():.2f}U")
# gate reductions on meal-phase under-delivering cycles
u=md[md.gap>0.01]
print("\ngateReduction on under-delivering meal cycles:")
gr=u.boostv5_gatereduction.fillna("none").apply(lambda s: re.sub(r":[\d.]+","",s))
print(gr.value_counts().head(10).to_dict())
print("\nstate on under-delivering cycles:", u.boostv5_state.value_counts().to_dict())
print(f"under-delivering cycles with v6u==0: {(u.v6u<0.01).sum()}/{len(u)}, gap there {u.gap[u.v6u<0.01].sum():.1f}U")

# ── confirm-floor coupling: reconstruct prospective confirm shot at CONFIRMED entries ──
dec["rise30"]=dec.bucket.map(lambda b:(c.asof(b)-c.asof(b-pd.Timedelta("30min"))) if b in c.index or True else np.nan)
def vf(r):
    if pd.isna(r): return np.nan
    if r>=50: return 1.0
    if r<=25: return 0.4
    return 0.4+0.6*(r-25)/25
dec["vfac"]=dec.rise30.apply(vf)
prev=dec.boostv5_state.shift(1)
entries=dec[(dec.boostv5_state.isin(["CONFIRMED"]))&(prev!="CONFIRMED")].copy()
entries["prospective"]=entries.boostv5_budget*1.8*entries.vfac
print(f"\n=== CONFIRMED entries (deduped, n={len(entries)}) prospective shot = budget*1.8*vf ===")
print(entries[["bucket","cgm_mgdl","boostv5_budget","rise30","vfac","prospective","boostv5_finaldose","v1_units"]].round(2).to_string(index=False))
for fl in (0.5,0.8,1.0,1.24):
    blocked=(entries.prospective<=fl).sum()
    print(f"confirm floor {fl:>4}: would block {blocked}/{len(entries)} observed confirms")
# also OBSERVING cycles with high score that could have confirmed (age>=2) — budget dist
obs=dec[(dec.boostv5_state=="OBSERVING")]
obs_p=obs.boostv5_budget*1.8*obs.vfac
print(f"\nOBSERVING cycles n={len(obs)}: prospective-shot p25/50/75 = {obs_p.quantile(.25):.2f}/{obs_p.median():.2f}/{obs_p.quantile(.75):.2f}U")
conn.close()
