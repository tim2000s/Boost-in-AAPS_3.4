import psycopg2, pandas as pd, numpy as np
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
q = """
SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
  user_id, ts_epoch, cgm_mgdl, boostv5_state AS state, boostv5_finaldose AS v6dose, v1_units, iob_iob
FROM boost_decisions WHERE boostv5_state IS NOT NULL
ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
"""
df = pd.read_sql(q, conn).sort_values(["user_id","ts_epoch"]).reset_index(drop=True)
df["v6capped"] = np.minimum(df.v6dose.fillna(0), df.v1_units.fillna(0))
ep = pd.read_csv("/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad/episodes.csv")
ep["end_dt"] = pd.to_datetime(ep["end"], utc=True, format="mixed")
ep["end_ts"] = (ep.end_dt - pd.Timestamp(0, tz="utc")).dt.total_seconds()
print("sample end_ts:", ep.end_ts.iloc[0], "df ts range:", df.ts_epoch.min(), df.ts_epoch.max())
res4, post2h_v6, post2h_v1 = [], [], []
for _,r in ep.iterrows():
    g = df[df.user_id==r["user"]]
    fw4 = g[(g.ts_epoch>r.end_ts)&(g.ts_epoch<=r.end_ts+14400)]
    res4.append(bool((fw4.cgm_mgdl<160).any()) if len(fw4) else None)
    fw2 = g[(g.ts_epoch>r.end_ts)&(g.ts_epoch<=r.end_ts+7200)]
    post2h_v6.append(fw2.v6capped.sum()); post2h_v1.append(fw2.v1_units.fillna(0).sum())
ep["resolved_4h"]=res4; ep["post2h_v6"]=post2h_v6; ep["post2h_v1"]=post2h_v1
stuck = ep[ep.resolved_2h==False]
print(f"stuck n={len(stuck)}; resolved<160 by 4h: {stuck.resolved_4h.sum()} ({100*stuck.resolved_4h.mean():.0f}%)")
print(f"post-episode 2h insulin (stuck): v6capped mean {stuck.post2h_v6.mean():.2f}U med {stuck.post2h_v6.median():.2f}U | v1 mean {stuck.post2h_v1.mean():.2f}U med {stuck.post2h_v1.median():.2f}U | parity {100*stuck.post2h_v6.sum()/stuck.post2h_v1.sum():.0f}%")
print(f"episode gap (stuck): mean {stuck.gap_sum.mean():.2f}U — vs post-2h v6 delivery mean {stuck.post2h_v6.mean():.2f}U")
allv = ep[ep.resolved_2h.notna()]
print(f"all episodes post-2h: v6 mean {allv.post2h_v6.mean():.2f} v1 mean {allv.post2h_v1.mean():.2f}")
ep.to_csv("/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad/episodes_v2.csv", index=False)
