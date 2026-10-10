#!/usr/bin/env python3
"""Backtest: sustained-delta RECOVERING->COMMITTED re-engage rule family.

Rule: within a contiguous RECOVERING run, delta5 > 3 for >= N consecutive cycles
AND (sug_eventualbg - sug_current_target) > 20 mg/dL -> COMMITTED.
Dose model per simulated COMMITTED cycle (from fire until delta5<0 or BG<160 or gap):
  realistic = per-user median COMMITTED finaldose on delta5>3 cycles
  upper     = min(boostv5_budget_at_cycle, committedCapU_proxy)
  added     = max(0, est - v6capped_actually_delivered)
capU_proxy = clamp(max(p75(v1_units>0), median(tdd)/40), 0.25, 2.5)  # mirrors BoostV5AutoConfig
"""
import psycopg2, pandas as pd, numpy as np

SP = "/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad"
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
q = """
SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
  user_id, ts_epoch, ts_utc, cgm_mgdl, boostv5_state AS state,
  boostv5_finaldose AS v6dose, boostv5_budget AS budget, v1_units, iob_iob,
  sug_eventualbg, sug_current_target, delta_acceleration AS accl, tdd
FROM boost_decisions WHERE boostv5_state IS NOT NULL
ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
"""
df = pd.read_sql(q, conn).sort_values(["user_id","ts_epoch"]).reset_index(drop=True)
df["dt_min"] = df.groupby("user_id")["ts_epoch"].diff()/60.0
df["delta5"] = df.groupby("user_id")["cgm_mgdl"].diff()/df.dt_min*5.0
df.loc[(df.dt_min>7.6)|(df.dt_min<2.0),"delta5"]=np.nan
df["v6capped"] = np.minimum(df.v6dose.fillna(0), df.v1_units.fillna(0))
df["offset"] = df.sug_eventualbg - df.sug_current_target

# per-user constants
users = {}
for uid, g in df.groupby("user_id"):
    v1pos = g.v1_units[g.v1_units>0]
    cap = np.clip(max(v1pos.quantile(.75) if len(v1pos) else 0.25, g.tdd.median()/40.0), 0.25, 2.5)
    comm = g[(g.state=="COMMITTED") & (g.delta5>3)]
    real = comm.v6dose.median() if len(comm) else 0.0
    iob_conf_p75 = g[g.state=="CONFIRMED"].iob_iob.quantile(.75)
    users[uid] = dict(cap=cap, real=real, iob_p75=iob_conf_p75)
print("per-user: capU_proxy / realistic_committed_dose / IOB_p75_at_CONFIRMED")
for u,v in users.items(): print(f"  {u}: cap={v['cap']:.2f}U real={v['real']:.2f}U iobp75={v['iob_p75']:.2f}U")

# rolling 60-min min BG per user (inclusive of current cycle)
def roll_min(g):
    ts = g.ts_epoch.values; bg = g.cgm_mgdl.values; out = np.empty(len(g))
    j = 0
    for i in range(len(g)):
        while ts[i]-ts[j] > 3600: j += 1
        out[i] = np.nanmin(bg[j:i+1])
    return out
df["min60"] = np.concatenate([roll_min(g) for _,g in df.groupby("user_id",sort=True)])

# episodes for classification
ep = pd.read_csv(f"{SP}/episodes_v2.csv")
ep["start_ts"] = (pd.to_datetime(ep.start, utc=True, format="mixed") - pd.Timestamp(0,tz="utc")).dt.total_seconds()
ep["end_ts2"] = (pd.to_datetime(ep["end"], utc=True, format="mixed") - pd.Timestamp(0,tz="utc")).dt.total_seconds()
ep["residual"] = (ep.resolved_2h==False)&(ep.iob_falling==True)&(ep.reengaged_90m==False)
print(f"\nresidual set n={ep.residual.sum()}, gap {ep[ep.residual].gap_sum.sum():.1f}U | low-ending episodes n={(ep.low70_3h==True).sum()}")

# build RECOVERING runs
runs = []  # (user, idx_list, hist_reengaged, reeng_offset_cycles)
for uid, g in df.groupby("user_id", sort=True):
    idx = g.index.values; st = g.state.values; ts = g.ts_epoch.values
    i = 0
    while i < len(idx):
        if st[i] != "RECOVERING": i += 1; continue
        j = i
        while j+1 < len(idx) and st[j+1]=="RECOVERING" and ts[j+1]-ts[j] <= 600: j += 1
        hist_re = j+1 < len(idx) and st[j+1]=="COMMITTED" and ts[j+1]-ts[j] <= 600
        runs.append((uid, idx[i:j+1], hist_re))
        i = j+1
print(f"RECOVERING runs: {len(runs)}, historically re-engaged: {sum(r[2] for r in runs)}")

TIM_RUN = ("tim", 1780594800, 1780598400)  # 2026-06-04 17:40-18:40 UTC (= 18:40-19:40 BST)

def simulate(N=3, floor160=True, g_low80=False, g_low100=False, g_iob=False, g_accl=False):
    fires = []
    for uid, ridx, hist_re in runs:
        u = users[uid]
        sub = df.loc[ridx]
        consec = 0; fired = None
        for k,(i,r) in enumerate(sub.iterrows()):
            d = r.delta5
            consec = consec+1 if (pd.notna(d) and d > 3) else 0
            if consec < N: continue
            if not (pd.notna(r.offset) and r.offset > 20): continue
            if floor160 and not (r.cgm_mgdl > 160): continue
            if g_low80 and r.min60 < 80: continue
            if g_low100 and r.min60 < 100: continue
            if g_iob and pd.notna(r.iob_iob) and pd.notna(u["iob_p75"]) and r.iob_iob > u["iob_p75"]: continue
            if g_accl and not (pd.notna(r.accl) and r.accl >= 0): continue
            fired = (k, i, r); break
        if fired is None: continue
        k, i, r = fired
        # dose window: from fire cycle until delta5<0 or BG<160 or gap>10min (walk full user series)
        gu = df[df.user_id==uid]
        pos = gu.index.get_loc(i)
        add_real = add_up = 0.0; ncyc = 0; last_ts = None
        for _, c in gu.iloc[pos:pos+24].iterrows():
            if last_ts is not None and c.ts_epoch-last_ts > 600: break
            if pd.notna(c.delta5) and c.delta5 < 0: break
            if c.cgm_mgdl < 160: break
            est_up = min(c.budget if pd.notna(c.budget) else u["cap"], u["cap"])
            add_real += max(0.0, u["real"] - c.v6capped)
            add_up   += max(0.0, est_up - c.v6capped)
            ncyc += 1; last_ts = c.ts_epoch
        # outcomes from fire time
        fw3 = gu[(gu.ts_epoch > r.ts_epoch) & (gu.ts_epoch <= r.ts_epoch + 10800)]
        low3h = bool((fw3.cgm_mgdl < 70).any()) if len(fw3) else False
        # map to episode
        m = ep[(ep.user==uid) & (ep.start_ts-300 <= r.ts_epoch) & (ep.end_ts2+300 >= r.ts_epoch)]
        eid = m.index[0] if len(m) else None
        run_start_ts = df.loc[ridx[0]].ts_epoch
        fires.append(dict(user=uid, fire_ts=r.ts_epoch, ts_utc=r.ts_utc, bg=r.cgm_mgdl, iob=r.iob_iob,
                          hist_re=hist_re, mins_into_run=(r.ts_epoch-run_start_ts)/60.0,
                          ncyc=ncyc, add_real=add_real, add_up=add_up, low3h=low3h, eid=eid,
                          is_tim0604=(uid==TIM_RUN[0] and TIM_RUN[1]<=r.ts_epoch<=TIM_RUN[2])))
    return pd.DataFrame(fires)

variants = {
 "G0 N3 floor160":              dict(N=3, floor160=True),
 "G0 N3 nofloor":               dict(N=3, floor160=False),
 "G1 (+low80) N3 f160":         dict(N=3, floor160=True, g_low80=True),
 "G1b (+low100) N3 f160":       dict(N=3, floor160=True, g_low100=True),
 "G2 (+IOB<p75conf) N3 f160":   dict(N=3, floor160=True, g_iob=True),
 "G3 (+accl>=0) N3 f160":       dict(N=3, floor160=True, g_accl=True),
 "G4 N4 f160":                  dict(N=4, floor160=True),
 "G1+G2+G3 N3 f160":            dict(N=3, floor160=True, g_low80=True, g_iob=True, g_accl=True),
 "G1b+G2 N3 f160":              dict(N=3, floor160=True, g_low100=True, g_iob=True),
 "G1b+G2+G3 N3 f160":           dict(N=3, floor160=True, g_low100=True, g_iob=True, g_accl=True),
 "G1b+G2 N4 f160":              dict(N=4, floor160=True, g_low100=True, g_iob=True),
}

rows = []
detail = {}
for name, kw in variants.items():
    f = simulate(**kw)
    detail[name] = f
    if len(f)==0:
        rows.append(dict(variant=name, fires=0)); continue
    new = f[~f.hist_re]  # fires in runs that never historically re-engaged
    resid_ids = set(ep[ep.residual].index)
    low_ids = set(ep[ep.low70_3h==True].index)
    stuck_ids = set(ep[ep.resolved_2h==False].index)
    f_resid = f[f.eid.isin(resid_ids)]
    # recovered gap on residual: min(add, gap_sum)
    rec_real = sum(min(a, ep.loc[e].gap_sum) for a,e in zip(f_resid.add_real, f_resid.eid))
    rec_up   = sum(min(a, ep.loc[e].gap_sum) for a,e in zip(f_resid.add_up,   f_resid.eid))
    f_low = f[f.low3h]
    rows.append(dict(variant=name, fires=len(f), new_fires=len(new),
        per_user=f.user.value_counts().to_dict(),
        resid_caught=len(f_resid), resid_rec_real=round(rec_real,2), resid_rec_up=round(rec_up,2),
        stuck_caught=f.eid.isin(stuck_ids).sum(),
        low_fires=len(f_low), low_fire_pct=round(100*len(f_low)/len(f),1),
        U_real=round(f.add_real.sum(),1), U_up=round(f.add_up.sum(),1),
        U_low_real=round(f_low.add_real.sum(),1), U_low_up=round(f_low.add_up.sum(),1),
        harm_pct_real=round(100*f_low.add_real.sum()/max(f.add_real.sum(),1e-9),1),
        harm_pct_up=round(100*f_low.add_up.sum()/max(f.add_up.sum(),1e-9),1),
        med_min_into_run=round(f.mins_into_run.median(),1),
        tim0604=bool(f.is_tim0604.any())))

out = pd.DataFrame(rows)
pd.set_option("display.width", 300)
cols1 = ["variant","fires","new_fires","resid_caught","resid_rec_real","resid_rec_up","stuck_caught","low_fires","low_fire_pct","tim0604"]
cols2 = ["variant","U_real","U_up","U_low_real","U_low_up","harm_pct_real","harm_pct_up","med_min_into_run"]
print("\n===== FIRES / CATCH / TIM-CHECK =====")
print(out[cols1].to_string(index=False))
print("\n===== INSULIN ADDED / HARM / TIMING =====")
print(out[cols2].to_string(index=False))
print("\nper-user fires (G0 N3 f160):", out[out.variant=="G0 N3 floor160"].per_user.iloc[0])
print("per-user fires (G1b+G2+G3):", out[out.variant=="G1b+G2+G3 N3 f160"].per_user.iloc[0])

# timing vs existing accel re-engage: among fired runs that ALSO historically re-engaged
f0 = detail["G0 N3 floor160"]
he = f0[f0.hist_re]
print(f"\nG0 fires in runs that historically re-engaged anyway: {len(he)} (rule beats accel path by firing at med {he.mins_into_run.median():.0f} min into run)")
# tim 2026-06-04 detail for variants that fire
for name, f in detail.items():
    t = f[f.is_tim0604]
    if len(t):
        r = t.iloc[0]
        print(f"TIM 2026-06-04 FIRES under '{name}': at {r.ts_utc} BG={r.bg:.0f} IOB={r.iob:.2f} add_real={r.add_real:.2f}U add_up={r.add_up:.2f}U")
out.to_csv(f"{SP}/reengage_variants.csv", index=False)
