#!/usr/bin/env python3
"""decompose_meal_doses.py — why do a user's CONFIRMED/COMMITTED doses give little?

Per-cycle reconstruction of the V6 dose pipeline for every CONFIRMED/COMMITTED cycle in a
user's V6-ACTIVE era (boostv5_active=true, deduped last-invoke per 5-min bucket):

    raw        = budget × actionMult                       (actionMult logged; 1.8 CONFIRMED / 1.0 COMMITTED)
    afterVf    = raw × velocityFactor                      (vf reconstructed from CGM cumRise30, see below)
    afterBrake = afterVf × iobHeadroomBrake × decelBrake   (both parsed from boostv5_gateReduction)
    capped     = min(afterBrake, operativeCap)             (confirmedCap / committedCap; logged or era-inferred)
    clamped    = min(capped, maxIob − IOB)                 (maxIob from console 'maxIOB:'; masked 1.0 vs real)
    finalDose  = floor(clamped / 0.05) × 0.05

velocityFactor (SafetyGates/DetermineBasalBoostV5): cumRise30 = max(0, shortAvgDelta×6);
    vf = 0.4 if cumRise≤25, 1.0 if ≥50, else 0.4 + 0.6·(cumRise−25)/25.  shortAvgDelta = mean 5-min
    delta over the last 3 readings. (Reconstruction validated against actual finalDose; match rate reported.)

For each cycle we compute the multiplier at each stage and attribute the budget→delivered collapse to
the DOMINANT factor (largest multiplicative cut / the binding clamp). Aggregates the ranked reasons by
% of cycles and % of total suppressed-U, separately for CONFIRMED and COMMITTED, and splits
ROUTINE (vf/decel/iobBrake/budget/cap) from RARE-CATASTROPHIC (maxIOB-mask/G3/minGuard).

Usage: python3 decompose_meal_doses.py [USER]   # default H
"""
import sys, os, numpy as np, pandas as pd, psycopg2

USER = sys.argv[1] if len(sys.argv) > 1 else "H"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"); os.makedirs(OUT, exist_ok=True)
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")

# full active-era decision series (for vf reconstruction we need contiguous CGM/delta)
df = pd.read_sql("""
SELECT DISTINCT ON (floor(ts_epoch/300.0))
  ts_epoch, ts_utc, cgm_mgdl bg, boostv5_state state, boostv5_age age,
  boostv5_budget budget, boostv5_actionmult am, boostv5_finaldose fd, boostv5_prospectiveshot prosp,
  boostv5_committedcap cc, boostv5_confirmedcap fc, boostv5_aggressionknob knob, iob_iob iob,
  boostv5_gatereduction gate, boostv5_cumulativecapu cumcap, boostv5_smbvol60min smbvol,
  substring(console_error from 'maxIOB: ?([0-9.,]+)') mx,
  (console_error ~* 'G3 HOLD|G3-HOLD') g3, reason_minguardbg mguard
FROM boost_decisions WHERE user_id=%s AND boostv5_active=true
ORDER BY floor(ts_epoch/300.0), ts_epoch DESC
""", conn, params=(USER,)).sort_values("ts_epoch").reset_index(drop=True)
conn.close()
df["mx"] = pd.to_numeric(df.mx.astype(str).str.replace(",", "."), errors="coerce")
df["delta5"] = df.bg.diff() / (df.ts_epoch.diff()/60) * 5
df.loc[(df.ts_epoch.diff()/60 > 7.6) | (df.ts_epoch.diff()/60 < 2.0), "delta5"] = np.nan
df["shortAvgDelta"] = df.delta5.rolling(3, min_periods=1).mean()
df["cumRise30"] = (df.shortAvgDelta * 6).clip(lower=0)
def vf(c):
    if pd.isna(c): return 1.0
    if c <= 25: return 0.40
    if c >= 50: return 1.0
    return 0.40 + 0.60*(c-25)/25
df["velF"] = df.cumRise30.apply(vf)

# operative caps: forward-fill logged; else era default (0.5 committed / 2.5 confirmed pre-logging)
df["op_cc"] = df.cc.ffill().fillna(0.5)
df["op_fc"] = df.fc.ffill().fillna(2.5)
df["op_knob"] = df.knob.ffill().fillna(1.3)
df["op_mx"] = df.mx.fillna(8.0)  # console maxIOB; if missing assume real 8

# parse brakes from gateReduction
def parse(pat, s):
    import re
    m = re.search(pat, str(s)) if isinstance(s, str) else None
    return float(m.group(1)) if m else 1.0
df["iobBrake"] = df.gate.apply(lambda s: parse(r"iobHeadroom:([0-9.]+)", s))
df["decelBrake"] = df.gate.apply(lambda s: parse(r"decel:([0-9.]+)", s))
df["maxiob_flag"] = df.gate.astype(str).str.contains("maxIOB", case=False, na=False)
df["mguard_flag"] = df.gate.astype(str).str.contains("min_guard|minGuard|HARD", case=False, na=False)

meal = df[df.state.isin(["CONFIRMED", "COMMITTED"])].copy()
# actionMult: logged, else 1.8*knob (CONFIRMED) / 1.0 (COMMITTED)
meal["am_use"] = meal.apply(lambda r: r.am if pd.notna(r.am)
                            else (1.8*r.op_knob if r.state=="CONFIRMED" else 1.0), axis=1)
# forward-simulate
meal["raw"] = meal.budget * meal.am_use
meal["afterVf"] = meal.raw * meal.velF
meal["afterBrake"] = meal.afterVf * meal.iobBrake * meal.decelBrake
meal["cap"] = np.where(meal.state=="CONFIRMED", meal.op_fc, meal.op_cc)
meal["capped"] = np.minimum(meal.afterBrake, meal.cap)
meal["clamped"] = np.minimum(meal.capped, np.maximum(meal.op_mx - meal.iob, 0))
meal["recon_fd"] = np.floor(meal.clamped/0.05 + 1e-9)*0.05
meal["recon_err"] = (meal.recon_fd - meal.fd).abs()

# attribute dominant suppressor: the factor with the largest ABSOLUTE loss on the budget→fd path
def attribute(r):
    losses = {}
    # each stage loss in U
    losses["velocityFactor"] = r.raw - r.afterVf
    losses["iobHeadroomBrake"] = r.afterVf - r.afterVf*r.iobBrake
    losses["decelBrake"] = (r.afterVf*r.iobBrake) - r.afterBrake
    losses["cap_clamp"] = max(0, r.afterBrake - r.capped)
    losses["maxIOB_clamp"] = max(0, r.capped - r.clamped)
    # rounding
    losses["round"] = max(0, r.clamped - r.recon_fd)
    # if raw itself is tiny (budget small): flag when raw < 0.5 and no other big loss
    tot = sum(v for v in losses.values() if v > 0)
    if r.mguard_flag: return "minGuardBG(HARD)", r.raw  # hard gate zeroes everything
    if r.g3: return "G3_HOLD", r.raw
    if tot < 0.10 and r.raw < 0.6: return "budget_small", 0.0
    dom = max(losses, key=lambda k: losses[k])
    # tag maxIOB clamp as masked if op_mx==1.0
    if dom == "maxIOB_clamp" and r.op_mx <= 1.01: dom = "maxIOB_MASK(1.0)"
    return dom, losses[dom]
att = meal.apply(lambda r: pd.Series(attribute(r), index=["dominant","dom_loss_U"]), axis=1)
meal = pd.concat([meal, att], axis=1)
meal["suppressed_U"] = (meal.raw - meal.fd).clip(lower=0)  # wanted(raw) minus delivered

ROUTINE = {"velocityFactor","decelBrake","iobHeadroomBrake","cap_clamp","budget_small","round"}
def report(sub, label):
    print(f"\n===== {label}: n={len(sub)} cycles, fd p50={sub.fd.median():.2f} p90={sub.fd.quantile(.9):.2f} max={sub.fd.max():.2f} | recon match(|err|<0.05)={100*(sub.recon_err<0.05).mean():.0f}% =====")
    g = sub.groupby("dominant").agg(cycles=("fd","size"), suppr_U=("suppressed_U","sum"), med_fd=("fd","median"))
    g["pct_cycles"] = (100*g.cycles/len(sub)).round(0)
    g["pct_suppr_U"] = (100*g.suppr_U/max(sub.suppressed_U.sum(),1e-9)).round(0)
    g = g.sort_values("suppr_U", ascending=False)
    print(g[["cycles","pct_cycles","pct_suppr_U","med_fd"]].to_string())
    rare = sub[~sub.dominant.isin(ROUTINE)]
    print(f"  ROUTINE {100*sub.dominant.isin(ROUTINE).mean():.0f}% of cycles | RARE-CATASTROPHIC {100*(~sub.dominant.isin(ROUTINE)).mean():.0f}% ({sorted(rare.dominant.unique())})")
    return g

conf = meal[meal.state=="CONFIRMED"]; comm = meal[meal.state=="COMMITTED"]
gc = report(conf, "CONFIRMED"); gm = report(comm, "COMMITTED")

# fresh confirm shot vs subsequent committed holds
fresh = conf[conf.age.fillna(0)==0]
print(f"\n=== confirm-shot vs committed-hold sizes ===")
print(f"fresh CONFIRMED shots: n={len(fresh)}, fd p50={fresh.fd.median():.2f} p90={fresh.fd.quantile(.9):.2f}")
print(f"COMMITTED holds: n={len(comm)}, fd p50={comm.fd.median():.2f} p90={comm.fd.quantile(.9):.2f}, %delivering 0 = {100*(comm.fd==0).mean():.0f}%")
days = df.ts_utc.dt.date.nunique() if hasattr(df.ts_utc.dt,'date') else pd.to_datetime(df.ts_utc,utc=True,format='mixed').dt.date.nunique()
print(f"CONFIRMED events/day (fresh, age==0): {len(fresh)/max(days,1):.2f}")

meal[["ts_utc","state","bg","budget","am_use","velF","iobBrake","decelBrake","cap","op_mx","iob","fd","recon_fd","dominant","suppressed_U"]].to_csv(f"{OUT}/decompose_{USER}_meal.csv", index=False)
print(f"\n[written] {OUT}/decompose_{USER}_meal.csv")
# routine-vs-rare headline
print(f"\n=== HEADLINE for {USER} ===")
allm = meal
print(f"dominant everyday reason (routine cycles, by suppressed-U): "
      f"{allm[allm.dominant.isin(ROUTINE)].groupby('dominant').suppressed_U.sum().idxmax()}")
print(f"COMMITTED dominant: {gm.index[0]} ({int(gm.iloc[0].pct_cycles)}% cycles); CONFIRMED dominant: {gc.index[0]} ({int(gc.iloc[0].pct_cycles)}% cycles)")
