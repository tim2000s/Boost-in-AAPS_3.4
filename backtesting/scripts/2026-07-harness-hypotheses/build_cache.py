#!/usr/bin/env python3
"""Per-user cache for the harness-hypothesis batch: load the full CGM + delivered-insulin + context stream
across ALL Boost versions, run the REAL Twin (harness) once, save an npz reused by H4/H7/H2. Era per cycle
by TELEMETRY (developer's correction): boostv5_state → V5V6; else ml_meal_likely → V44x_ML; else → BoostV1_4.1.5
(the early v4.1.5 Boost, no explicit v1/v6 telemetry). Run one user: python3 build_cache.py <user>
"""
import sys, os, numpy as np, psycopg2, pandas as pd
sys.path.insert(0, os.path.expanduser("~/StudioProjects/Boost-AAPS-core/backtesting/scripts/kotlin-harness"))
from kengine import run_engine

VARPRIO = {"boost-other": 0, "trio-shadow": 1, "v1": 2, "v2": 3, "v3": 4, "v1-silent": 5}
U = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))

with psycopg2.connect("dbname=oref host=127.0.0.1 port=5432") as conn:
    df = pd.read_sql("""select ts_epoch, cgm_mgdl, boostv5_finaldose, v1_units, sug_rate, variable_sens,
        steps_5m, steps_60m, iob_iob, boostv5_state, ml_meal_likely, variant
        from boost_decisions where user_id=%s and cgm_mgdl is not null order by ts_epoch""", conn, params=(U,))
df["prio"] = df.variant.map(VARPRIO).fillna(9)
df["bucket"] = (df.ts_epoch // 300).astype(np.int64)
df = df.sort_values(["bucket", "prio"]).drop_duplicates("bucket", keep="first").sort_values("ts_epoch").reset_index(drop=True)
ep = df.ts_epoch.to_numpy(float); cgm = df.cgm_mgdl.to_numpy(float)
smb = df.boostv5_finaldose.fillna(df.v1_units).fillna(0.0).to_numpy(float)
rate = df.sug_rate.fillna(0.0).to_numpy(float)
isf = df.variable_sens.to_numpy(float)
if np.nanmedian(isf) < 15: isf = isf * 18.0
isf_med = float(np.clip(np.nanmedian(isf), 20, 250))
dt = np.clip(np.diff(ep, append=ep[-1] + 300) / 60.0, 0, 6)
deliv = smb + rate * dt / 60.0
# era per cycle (telemetry-based)
era = np.where(df.boostv5_state.notna(), "V5V6",
      np.where(df.ml_meal_likely.notna(), "V44x_ML", "BoostV1_415")).astype(object)

cycles = [{"cgm": float(cgm[i]), "bg": float(cgm[i]), "insulinThisCycleU": float(deliv[i]),
           "expectedBasalPerCycleU": float(rate[i] * 5.0 / 60.0), "deliverableU": float(deliv[i])}
          for i in range(len(df))]
res = run_engine("twin", cycles)
def col(k): return np.array([r.get(k, np.nan) for r in res], float)
fc30, fc60, lo30, ra, fgi = col("fc30"), col("fc60"), col("lo30"), col("raMean"), col("filteredGi")

np.savez(os.path.join(HERE, "cache", f"{U}.npz"),
         ep=ep, cgm=cgm, deliv=deliv, smb=smb, rate=rate, isf=np.full(len(df), isf_med),
         steps5=np.nan_to_num(df.steps_5m.to_numpy(float)), steps60=np.nan_to_num(df.steps_60m.to_numpy(float)),
         iob=np.nan_to_num(df.iob_iob.to_numpy(float)),
         fc30=fc30, fc60=fc60, lo30=lo30, ra=ra, fgi=fgi, era=era.astype(str))
print(f"{U}: cached {len(df)} cycles ({(ep[-1]-ep[0])/86400:.0f}d)  "
      f"eras V1={np.sum(era=='BoostV1_415')} ML={np.sum(era=='V44x_ML')} V5V6={np.sum(era=='V5V6')}")
