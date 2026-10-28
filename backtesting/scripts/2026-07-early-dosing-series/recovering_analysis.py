#!/usr/bin/env python3
"""RECOVERING-high episode analysis for the developer's 'standard SMB in RECOVERING' proposal.

Episode def: consecutive deduped cycles with state=RECOVERING, BG>160, delta>=0 (flat-or-rising),
first qualifying cycle within <=90 min after a CONFIRMED cycle.
"""
import psycopg2, pandas as pd, numpy as np

conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
q = """
SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
  user_id, ts_epoch, ts_utc, cgm_mgdl, boostv5_state AS state,
  boostv5_finaldose AS v6dose, boostv5_budget AS budget, boostv5_age AS v5age,
  v1_units, iob_iob, sug_iob, sug_insulinreq, tdd_blended, tdd
FROM boost_decisions
WHERE boostv5_state IS NOT NULL
ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
"""
df = pd.read_sql(q, conn)
df = df.sort_values(["user_id", "ts_epoch"]).reset_index(drop=True)
print(f"deduped cycles: {len(df)}")

# per-user delta from consecutive cycles (only valid when gap <= 7.5 min)
df["dt_min"] = df.groupby("user_id")["ts_epoch"].diff() / 60.0
df["delta"] = df.groupby("user_id")["cgm_mgdl"].diff()
df.loc[(df.dt_min > 7.6) | (df.dt_min < 2.0), "delta"] = np.nan
# normalize delta to per-5-min
df["delta5"] = df.delta / df.dt_min * 5.0

# minutes since last CONFIRMED cycle (per user)
def mins_since_confirmed(g):
    last_conf = np.where(g.state.values == "CONFIRMED", g.ts_epoch.values, np.nan)
    last_conf = pd.Series(last_conf).ffill().values
    return (g.ts_epoch.values - last_conf) / 60.0
df["min_since_conf"] = np.concatenate([mins_since_confirmed(g) for _, g in df.groupby("user_id", sort=True)])

# qualifying cycle
df["qual160"] = (df.state == "RECOVERING") & (df.cgm_mgdl > 160) & (df.delta5 >= 0) & (df.min_since_conf <= 90)
df["qual180"] = df.qual160 & (df.cgm_mgdl > 180)
df["rec"] = df.state == "RECOVERING"

# retroactive non-meal cap
df["v6capped"] = np.minimum(df.v6dose.fillna(0), df.v1_units.fillna(0))
df["gap"] = (df.v1_units.fillna(0) - df.v6capped).clip(lower=0)

# ---- build episodes: consecutive qualifying cycles (allow 1-cycle gap of non-qual RECOVERING) ----
episodes = []
for uid, g in df.groupby("user_id", sort=True):
    g = g.reset_index(drop=True)
    i = 0
    n = len(g)
    while i < n:
        if not g.qual160.iloc[i]:
            i += 1; continue
        # extend while qualifying and contiguous in time (<=10 min between cycles)
        j = i
        while j + 1 < n and g.qual160.iloc[j+1] and (g.ts_epoch.iloc[j+1] - g.ts_epoch.iloc[j]) <= 600:
            j += 1
        ep = g.iloc[i:j+1]
        end_ts = g.ts_epoch.iloc[j]
        # forward windows
        fw2h = g[(g.ts_epoch > end_ts) & (g.ts_epoch <= end_ts + 7200)]
        fw3h = g[(g.ts_epoch > end_ts) & (g.ts_epoch <= end_ts + 10800)]
        # what state followed within 60 min of episode START (re-engage audit)
        fw_states = g[(g.ts_epoch > g.ts_epoch.iloc[i]) & (g.ts_epoch <= g.ts_epoch.iloc[i] + 5400)]
        reengaged = "COMMITTED" in fw_states.state.values
        t_reeng = np.nan
        if reengaged:
            t_reeng = (fw_states[fw_states.state == "COMMITTED"].ts_epoch.iloc[0] - g.ts_epoch.iloc[i]) / 60.0
        # next non-RECOVERING state after episode end
        after = g[g.ts_epoch > end_ts]
        nxt = after[after.state != "RECOVERING"]
        next_state = nxt.state.iloc[0] if len(nxt) else None
        # IOB trend across episode
        iob_start = ep.iob_iob.iloc[0]; iob_end = ep.iob_iob.iloc[-1]
        episodes.append(dict(
            user=uid, start=ep.ts_utc.iloc[0], end=ep.ts_utc.iloc[-1],
            n_cycles=len(ep), dur_min=(end_ts - g.ts_epoch.iloc[i])/60.0 + 5,
            bg_start=ep.cgm_mgdl.iloc[0], bg_end=ep.cgm_mgdl.iloc[-1],
            bg_max=ep.cgm_mgdl.max(), any180=bool(ep.qual180.any()), all180=bool(ep.qual180.all()),
            min_since_conf=ep.min_since_conf.iloc[0],
            v6capped_sum=ep.v6capped.sum(), v1_sum=ep.v1_units.fillna(0).sum(), gap_sum=ep.gap.sum(),
            iob_start=iob_start, iob_end=iob_end,
            iob_falling=bool(pd.notna(iob_start) and pd.notna(iob_end) and iob_end < iob_start - 0.05),
            resolved_2h=bool((fw2h.cgm_mgdl < 160).any()) if len(fw2h) else None,
            low70_3h=bool((fw3h.cgm_mgdl < 70).any()) if len(fw3h) else None,
            min_bg_3h=fw3h.cgm_mgdl.min() if len(fw3h) else np.nan,
            reengaged_90m=reengaged, t_reengage_min=t_reeng,
            next_state=next_state,
            # counterfactual: extra insulin = gap (v1 - v6capped) while qualifying (delta>=0 already enforced)
            cf_extra_u=ep.gap.sum(),
        ))
        i = j + 1

ep = pd.DataFrame(episodes)
ep.to_csv("/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad/episodes.csv", index=False)

pd.set_option("display.width", 250)
print("\n===== 1. EPISODE COUNTS =====")
print(f"total episodes (BG>160): {len(ep)}")
print(ep.groupby("user").agg(n=("user","size"), med_dur=("dur_min","median"), max_dur=("dur_min","max"),
                             med_bgmax=("bg_max","median")).round(1))
print(f"\nepisodes with any cycle >180: {ep.any180.sum()}; all cycles >180: {ep.all180.sum()}")
print("duration distribution (min):")
print(ep.dur_min.describe().round(1))
print("cycles per episode:", ep.n_cycles.value_counts().sort_index().to_dict())

print("\n===== 2. DOSE GAP (retro non-meal cap applied) =====")
print(f"per-episode: v6capped_sum med={ep.v6capped_sum.median():.2f} v1_sum med={ep.v1_sum.median():.2f}")
print(f"gap per episode: mean={ep.gap_sum.mean():.2f}U med={ep.gap_sum.median():.2f}U max={ep.gap_sum.max():.2f}U total={ep.gap_sum.sum():.1f}U")
print("gap quartiles:", ep.gap_sum.quantile([.25,.5,.75,.9,.95]).round(2).to_dict())

print("\n===== 3. OUTCOMES =====")
val = ep[ep.resolved_2h.notna()]
print(f"episodes w/ outcome data: {len(val)}")
print(f"resolved <160 within 2h WITHOUT extra insulin: {val.resolved_2h.sum()} ({100*val.resolved_2h.mean():.0f}%)")
print(f"low <70 within 3h of episode end: {val.low70_3h.sum()} ({100*val.low70_3h.mean():.0f}%)")
stuck = val[(val.resolved_2h == False)]
print(f"stuck (not <160 in 2h): {len(stuck)} ({100*len(stuck)/len(val):.0f}%)")
print(f"  of stuck, IOB falling during episode: {stuck.iob_falling.sum()}")
print(f"  of stuck, later low<70 in 3h: {stuck.low70_3h.sum()}")
print("cross-tab resolved x low:")
print(pd.crosstab(val.resolved_2h, val.low70_3h))
print("min BG in 3h after end, by resolved:", val.groupby("resolved_2h").min_bg_3h.median().round(0).to_dict())

print("\n===== 4. RE-ENGAGE AUDIT =====")
print(f"episodes that re-engaged to COMMITTED within 90 min of episode start: {ep.reengaged_90m.sum()} ({100*ep.reengaged_90m.mean():.0f}%)")
print(f"time-to-reengage (min): {ep[ep.reengaged_90m].t_reengage_min.describe().round(1).to_dict()}")
print("next state after episode end:", ep.next_state.value_counts().to_dict())
print("re-engage rate among STUCK episodes:", f"{stuck.reengaged_90m.sum()}/{len(stuck)}")

print("\n===== 5. COUNTERFACTUAL =====")
print(f"extra U if V6 dosed v1_units in these cycles (bounded by non-meal cap):")
print(f"  all episodes: total={ep.cf_extra_u.sum():.1f}U, mean/ep={ep.cf_extra_u.mean():.2f}U")
print(f"  stuck subset: total={stuck.cf_extra_u.sum():.1f}U, mean/ep={stuck.cf_extra_u.mean():.2f}U")
lows = val[val.low70_3h == True]
print(f"  episodes ending in low<70: n={len(lows)}, extra insulin they would have received: mean={lows.cf_extra_u.mean():.2f}U med={lows.cf_extra_u.median():.2f}U max={lows.cf_extra_u.max():.2f}U")
resolved_lows = val[(val.resolved_2h==True)]
print(f"  self-resolved episodes: n={len(resolved_lows)}, extra: mean={resolved_lows.cf_extra_u.mean():.2f}U max={resolved_lows.cf_extra_u.max():.2f}U")

print("\n===== >180 subset =====")
v180 = val[val.any180]
if len(v180):
    s180 = v180[v180.resolved_2h==False]
    print(f"n={len(v180)} resolved={v180.resolved_2h.mean()*100:.0f}% low3h={v180.low70_3h.mean()*100:.0f}% stuck={len(s180)}")
    print(f"gap: med={v180.gap_sum.median():.2f} mean={v180.gap_sum.mean():.2f}")

print("\n===== stuck episode detail (top 15 by gap) =====")
cols = ["user","start","dur_min","bg_start","bg_max","bg_end","iob_start","iob_end","v6capped_sum","v1_sum","gap_sum","reengaged_90m","next_state","low70_3h","min_bg_3h"]
print(stuck.sort_values("gap_sum", ascending=False)[cols].head(15).to_string())
