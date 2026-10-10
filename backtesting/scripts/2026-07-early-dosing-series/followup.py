import psycopg2, pandas as pd, numpy as np
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
q = """
SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
  user_id, ts_epoch, ts_utc, cgm_mgdl, boostv5_state AS state,
  boostv5_finaldose AS v6dose, v1_units, iob_iob, tdd_7d
FROM boost_decisions WHERE boostv5_state IS NOT NULL
ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
"""
df = pd.read_sql(q, conn).sort_values(["user_id","ts_epoch"]).reset_index(drop=True)
df["dt_min"] = df.groupby("user_id")["ts_epoch"].diff()/60.0
df["delta5"] = df.groupby("user_id")["cgm_mgdl"].diff()/df.dt_min*5.0
df.loc[(df.dt_min>7.6)|(df.dt_min<2.0),"delta5"]=np.nan
def msc(g):
    lc = pd.Series(np.where(g.state.values=="CONFIRMED", g.ts_epoch.values, np.nan)).ffill().values
    return (g.ts_epoch.values-lc)/60.0
df["min_since_conf"] = np.concatenate([msc(g) for _,g in df.groupby("user_id",sort=True)])
df["v6capped"] = np.minimum(df.v6dose.fillna(0), df.v1_units.fillna(0))

# A) In the post-CONFIRMED stuck-high window (<=90min after CONFIRMED, BG>160): state mix + dosing parity
w = df[(df.min_since_conf<=90)&(df.min_since_conf>0)&(df.cgm_mgdl>160)]
print("=== state mix in post-CONFIRMED high windows (BG>160, <=90min after CONFIRMED) ===")
agg = w.groupby("state").agg(n=("state","size"), v6capped=("v6capped","sum"), v1=("v1_units","sum"))
agg["parity_pct"] = (100*agg.v6capped/agg.v1).round(0)
print(agg.round(1))
print("total cycles:", len(w))

# per user-day normalization of RECOVERING-high gap
span = df.groupby("user_id").ts_epoch.agg(lambda s:(s.max()-s.min())/86400)
print("\nuser-days of state data:", span.round(0).to_dict(), "total:", round(span.sum()))

# B) basal-bounded counterfactual: basal_est = tdd_7d*0.45/24 U/h; add = min(v1, basal*30/60) - v6capped, >=0
df["basal_est"] = df.tdd_7d*0.45/24.0
df["qual"] = (df.state=="RECOVERING")&(df.cgm_mgdl>160)&(df.delta5>=0)&(df.min_since_conf<=90)
qd = df[df.qual]
add_basal = (np.minimum(qd.v1_units.fillna(0), qd.basal_est*0.5) - qd.v6capped).clip(lower=0)
add_v1 = (qd.v1_units.fillna(0)-qd.v6capped).clip(lower=0)
print(f"\n=== counterfactual variants over {len(qd)} qualifying cycles ===")
print(f"v1-bounded (cap as-is): total {add_v1.sum():.1f}U | basal30min-bounded: total {add_basal.sum():.1f}U")
print(f"per user-day: v1-bounded {add_v1.sum()/span.sum():.2f}U, basal-bounded {add_basal.sum()/span.sum():.2f}U")

# C) stuck episodes: do they resolve by 4h? and what dose flows in the 2h AFTER episode end (IDLE parity)?
ep = pd.read_csv("/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad/episodes.csv", parse_dates=["start","end"])
ep["end_ts"] = ep.end.astype("int64")//10**9
res4, post2h_v6, post2h_v1 = [], [], []
for _,r in ep.iterrows():
    g = df[df.user_id==r.user]
    fw4 = g[(g.ts_epoch>r.end_ts)&(g.ts_epoch<=r.end_ts+14400)]
    res4.append(bool((fw4.cgm_mgdl<160).any()) if len(fw4) else None)
    fw2 = g[(g.ts_epoch>r.end_ts)&(g.ts_epoch<=r.end_ts+7200)]
    post2h_v6.append(fw2.v6capped.sum()); post2h_v1.append(fw2.v1_units.fillna(0).sum())
ep["resolved_4h"]=res4; ep["post2h_v6capped"]=post2h_v6; ep["post2h_v1"]=post2h_v1
stuck = ep[ep.resolved_2h==False]
print(f"\n=== stuck episodes (n={len(stuck)}) ===")
print(f"resolve <160 by 4h: {stuck.resolved_4h.sum()} ({100*stuck.resolved_4h.mean():.0f}%)")
print(f"insulin flowing in 2h AFTER episode end: v6capped med {stuck.post2h_v6capped.median():.2f}U vs v1 med {stuck.post2h_v1.median():.2f}U (parity {100*stuck.post2h_v6capped.sum()/stuck.post2h_v1.sum():.0f}%)")
print(f"episode gap vs post-episode-2h delivery: gap med {stuck.gap_sum.median():.2f}U, post2h v6 med {stuck.post2h_v6capped.median():.2f}U")
# re-engaged outcomes
re_ep = ep[ep.reengaged_90m==True]; nore = ep[ep.reengaged_90m==False]
print(f"\nre-engaged episodes: n={len(re_ep)}, low<70 in 3h: {100*re_ep.low70_3h.mean():.0f}% | non-re-engaged: n={len(nore)}, low rate {100*nore.low70_3h.mean():.0f}%")
# lows analysis: extra insulin to episodes that ended low, split
lows = ep[ep.low70_3h==True]
print(f"\nlow-ending episodes: n={len(lows)}, would receive extra: total {lows.cf_extra_u.sum():.1f}U; those getting >0.5U extra: {(lows.cf_extra_u>0.5).sum()}, >1U: {(lows.cf_extra_u>1).sum()}")
# stuck with FALLING IOB and no re-engage — the true residual case
core = stuck[(stuck.iob_falling==True)&(stuck.reengaged_90m==False)]
print(f"\ntrue residual case (stuck + IOB falling + never re-engaged): n={core.shape[0]}, gap total {core.gap_sum.sum():.1f}U, med {core.gap_sum.median():.2f}U")
print(core[["user","start","dur_min","bg_max","iob_start","iob_end","gap_sum","min_bg_3h"]].sort_values("gap_sum",ascending=False).head(10).to_string())
