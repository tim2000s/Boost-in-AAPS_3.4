#!/usr/bin/env python3
"""target_effect.py — how a user's (low) target affects dosing via min-guard blocking,
with an honest counterfactual of raising the base target.

DB, V6-ACTIVE cycles, dedup last-invoke per 5-min bucket. Units: reason_minguardbg / pred
curves are mmol/L; cgm_mgdl / sug_current_target are mg/dL. LGS/min-guard threshold read from
reason lines (H = 5.5 mmol = 99 mg/dL). ISF from logged variable_sens (mg/dL/U).

Structural point under test: base target 80 < LGS threshold 99 → does the 80-99 band get
min-guard-blocked while ABOVE target? Counterfactual: base target 80 → 100 has OPPOSING effects —
(a) higher target → lower insulinReq → LESS budget; (b) fewer min-guard blocks — data decides net.

Usage: python3 target_effect.py [USER]   # default H
"""
import sys, os, numpy as np, pandas as pd, psycopg2

USER = sys.argv[1] if len(sys.argv) > 1 else "H"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"); os.makedirs(OUT, exist_ok=True)
MMOL = 18.0
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
SELECT DISTINCT ON (floor(ts_epoch/300.0))
  ts_epoch, ts_utc, cgm_mgdl bg, boostv5_state state, boostv5_budget budget, boostv5_finaldose fd,
  boostv5_actionmult am, boostv5_gatereduction gate, sug_current_target tgt, sug_eventualbg ev,
  sug_insulinreq insreq, iob_iob iob, variable_sens isf,
  reason_minguardbg mg_mmol, reason_iobpredbg iobp_mmol, reason_uampredbg uamp_mmol
FROM boost_decisions WHERE user_id=%s AND boostv5_active=true
ORDER BY floor(ts_epoch/300.0), ts_epoch DESC
""", conn, params=(USER,)).sort_values("ts_epoch").reset_index(drop=True)
conn.close()
df["delta5"] = df.bg.diff() / (df.ts_epoch.diff()/60) * 5
df.loc[(df.ts_epoch.diff()/60 > 7.6) | (df.ts_epoch.diff()/60 < 2.0), "delta5"] = np.nan
df["mg_mgdl"] = df.mg_mmol * MMOL
df["blocked"] = df.gate.astype(str).str.contains("min_guard", case=False, na=False)
df["date"] = pd.to_datetime(df.ts_utc, utc=True, format="mixed").dt.date
days = df.date.nunique()
THR = 99.0  # 5.5 mmol, confirmed from reason lines

print(f"=== {USER}: {len(df)} V6-active cycles / {days} days | min-guard threshold {THR:.0f} mg/dL (5.5 mmol) ===")

# 1. block rate
print("\n=== 1. MIN-GUARD BLOCK RATE ===")
def rate(mask, lbl):
    sub = df[mask]; b = sub.blocked.sum()
    print(f"  {lbl}: {b}/{len(sub)} = {100*b/max(len(sub),1):.1f}%")
rate(pd.Series(True, index=df.index), "all cycles")
rate(df.budget > 0, "budget>0 (wanted to dose)")
rate(df.delta5 > 3, "rising (delta>3)")
rate((df.budget > 0) & (df.delta5 > 3), "budget>0 AND rising")
# intended U lost to min-guard: intended on blocked cycles (budget×actionMult, no vf — upper bound)
bl = df[df.blocked].copy()
bl["am_use"] = bl.am.fillna(1.0)
bl["intended"] = bl.budget * bl.am_use
print(f"  intended U on min-guard-blocked cycles: total {bl.intended.sum():.1f}U = {bl.intended.sum()/days:.2f} U/day (upper bound; delivered 0)")
print(f"  of blocked, budget>0: {(bl.budget>0).sum()} cycles ({bl[bl.budget>0].intended.sum():.1f}U); budget≈0: {(bl.budget<=0.05).sum()} (nothing wanted anyway)")

# 2. driver decomposition
print("\n=== 2. WHAT DRIVES THE BLOCK (blocked cycles) ===")
print(f"  target: base(<=85) {(bl.tgt<=85).sum()} | mid(85-109) {bl.tgt.between(85,109).sum()} | RAISED(>=110) {(bl.tgt>=110).sum()}")
print(f"  BG: avg {bl.bg.mean():.0f}, in 80-99 band {(bl.bg.between(80,99)).sum()}/{len(bl)} ({100*bl.bg.between(80,99).mean():.0f}%); below-target {(bl.bg<bl.tgt).sum()}/{len(bl)}")
print(f"  IOB: avg {bl.iob.mean():.2f}U, >2U on {(bl.iob>2).sum()}; minGuardBG avg {bl.mg_mgdl.mean():.0f} mg/dL (predictions crashing)")
print(f"  minGuardBG < 0 (pred crash) on {(bl.mg_mgdl<0).sum()}/{len(bl)} blocked cycles")
# which pred curve binds (lowest of iobpred/uampred ~ minGuard)
bl["bind_iob"] = (bl.iobp_mmol <= bl.uamp_mmol.fillna(999)) | bl.uamp_mmol.isna()
print(f"  binding prediction: IOBpredBG lowest on {bl.bind_iob.sum()}/{len(bl)} ({100*bl.bind_iob.mean():.0f}%) — IOB-driven crash")
# is it target or IOB? blocked cycles at base target vs raised, and IOB
print(f"  --> blocks at BASE target 80: {(bl.tgt<=85).sum()} (structural hypothesis predicts these); at RAISED: {(bl.tgt>=110).sum()}")

# 3. counterfactual: base target 80 -> 100
print("\n=== 3. COUNTERFACTUAL: base target 80 -> 100 (5.5 mmol) ===")
base = df[df.tgt <= 85].copy()  # cycles at his base target
print(f"  cycles at base target (<=85): {len(base)} ({100*len(base)/len(df):.0f}% of all)")
# 3a budget effect: insulinReq ~ (eventualBG - target)/ISF; raising target 20 mg/dL cuts req by 20/ISF
base["isf_use"] = base.isf.replace(0, np.nan)
base["req_cut"] = (20.0 / base.isf_use).clip(lower=0)  # U reduction per dosing cycle
base_dosing = base[base.budget > 0]
print(f"  3a BUDGET: on {len(base_dosing)} base-target dosing cycles, raising target +20 cuts insulinReq by "
      f"~{base_dosing.req_cut.mean():.2f}U/cyc → −{base_dosing.req_cut.sum():.1f}U total = −{base_dosing.req_cut.sum()/days:.2f} U/day (LESS dosing)")
# 3b min-guard unblock: how many blocked cycles are at base target (would higher target help)?
bl_base = bl[bl.tgt <= 85]
print(f"  3b MIN-GUARD: blocked cycles at base target = {len(bl_base)} of {len(bl)} → raising base target unblocks ≈{len(bl_base)} cycles "
      f"({bl_base.intended.sum():.1f}U). His blocks are at RAISED targets, unaffected by base change.")
# also: at target 100, would the 80-99 BG band clear? min-guard is about PREDICTIONS not BG; predictions crash from IOB
print(f"  3c NET: budget effect −{base_dosing.req_cut.sum()/days:.2f} U/day; min-guard unblock +{bl_base.intended.sum()/days:.2f} U/day → "
      f"NET {(bl_base.intended.sum() - base_dosing.req_cut.sum())/days:+.2f} U/day")

# 4. reframe: is he well-controlled?
print("\n=== 4. REFRAME: is his target even the issue? ===")
cgm = pd.read_sql("SELECT cgm_mgdl bg FROM boost_cgm WHERE user_id=%s AND ts_utc BETWEEN %s AND %s AND cgm_mgdl IS NOT NULL",
                  psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"), params=(USER, str(df.ts_utc.min()), str(df.ts_utc.max())))
bg = cgm.bg
print(f"  TIR 70-180 {100*bg.between(70,180).mean():.1f}% | TING 63-140 {100*bg.between(63,140).mean():.1f}% | "
      f"TBR<70 {100*(bg<70).mean():.1f}% | TAR>180 {100*(bg>180).mean():.1f}% | mean {bg.mean():.0f}")

# save per-cycle blocked detail + summary
bl[["ts_utc","bg","tgt","mg_mgdl","iobp_mmol","uamp_mmol","iob","delta5","budget","intended"]].to_csv(f"{OUT}/{USER}_minguard_blocked.csv", index=False)
summary = pd.DataFrame([
    dict(metric="minguard_block_rate_all_pct", value=round(100*df.blocked.mean(),1)),
    dict(metric="minguard_block_rate_budget_gt0_pct", value=round(100*df[df.budget>0].blocked.mean(),1)),
    dict(metric="intended_U_lost_per_day", value=round(bl[bl.budget>0].intended.sum()/days,2)),
    dict(metric="blocked_at_base_target_pct", value=round(100*(bl.tgt<=85).mean(),1)),
    dict(metric="blocked_at_raised_target_pct", value=round(100*(bl.tgt>=110).mean(),1)),
    dict(metric="blocked_IOBpred_binding_pct", value=round(100*bl.bind_iob.mean(),1)),
    dict(metric="cf_budget_cut_U_per_day", value=round(base_dosing.req_cut.sum()/days,2)),
    dict(metric="cf_minguard_unblock_U_per_day", value=round(bl_base.intended.sum()/days,2)),
    dict(metric="cf_net_U_per_day", value=round((bl_base.intended.sum()-base_dosing.req_cut.sum())/days,2)),
    dict(metric="TIR_70_180", value=round(100*bg.between(70,180).mean(),1)),
    dict(metric="TBR_70", value=round(100*(bg<70).mean(),1)),
])
summary.to_csv(f"{OUT}/{USER}_target_effect_summary.csv", index=False)
print(f"\n[written] {OUT}/{USER}_minguard_blocked.csv + {USER}_target_effect_summary.csv")
