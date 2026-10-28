import re, numpy as np, pandas as pd, psycopg2
conn=psycopg2.connect("dbname=oref")
dec=pd.read_sql("SELECT ts_utc,variant,v1_units,boostv5_state,boostv5_finaldose,boostv5_budget,reason_text FROM boost_decisions WHERE user_id='H' AND variant='boost-other' ORDER BY ts_utc",conn)
cgm=pd.read_sql("SELECT ts_utc,cgm_mgdl FROM boost_cgm WHERE user_id='H' AND ts_utc>='2026-06-29' ORDER BY ts_utc",conn)
dec["ts_utc"]=pd.to_datetime(dec.ts_utc,utc=True);cgm["ts_utc"]=pd.to_datetime(cgm.ts_utc,utc=True)
dec["bucket"]=dec.ts_utc.dt.floor("5min");dec=dec.sort_values("ts_utc").groupby("bucket",as_index=False).last()
def bw(r):
    if not isinstance(r,str):return np.nan
    m=re.search(r"base would=([\d.]+)U",r) or re.search(r"base SMB ([\d.]+)U",r)
    return float(m.group(1)) if m else np.nan
dec["base_would"]=dec.reason_text.apply(bw)
dec[["bucket","boostv5_state","boostv5_finaldose","v1_units","base_would","boostv5_budget"]].to_csv(f"{'/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad'}/H_v6era_cycles_deduped.csv",index=False)
print("saved", len(dec), "deduped V6-era cycles")
conn.close()
