#!/usr/bin/env python3
"""maxIOB masking-during-%-profile-switch bug: Part A evidence, Part B counterfactual,
Part C cohort path-divergence check.

Part A (headline): the iobHeadroomBrake and the min(dose, maxIob-iob) clamp receive
maxIob=1.0 (factory default) — visible in console_error 'maxIOB: 1.0' — during a
boost_profile_switch=130 window, not the configured 8. SafetyGates.kt is correct given
its input; it is FED the wrong maxIob.
"""
import numpy as np, pandas as pd, psycopg2, os
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"out"); os.makedirs(OUT,exist_ok=True)
conn=psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")

# iobHeadroomBrake ladder (SafetyGates.kt:82-85,186-198) + hard clamp (125-128)
TH0,TH1,TH2=0.5,0.7,0.85; SC1,SC2,SC3=0.85,0.60,0.40
def brake(iob,maxiob):
    if maxiob<=0: return 1.0
    f=iob/maxiob
    return 1.0 if f<TH0 else SC1 if f<TH1 else SC2 if f<TH2 else SC3
def clamp_headroom(iob,maxiob): return max(0.0,maxiob-iob)

print("=== PART A: mechanism evidence (user H, 07-07 rise) ===")
h=pd.read_sql("""
SELECT DISTINCT ON (floor(ts_epoch/300.0)) ts_utc, cgm_mgdl bg, boostv5_state st,
 iob_iob iob, boostv5_budget budget, boostv5_finaldose fd, boostv5_confirmedcap fcap,
 boostv5_committedcap ccap, boostv5_gatereduction gate, boost_profile_switch ps,
 substring(console_error from 'maxIOB: ?([0-9.,]+)') cons_maxiob
FROM boost_decisions WHERE user_id='H' AND ts_utc BETWEEN timestamptz '2026-07-07 17:30+00' AND timestamptz '2026-07-07 19:10+00'
ORDER BY floor(ts_epoch/300.0), ts_epoch DESC""",conn).sort_values("ts_utc")
h["cons_maxiob"]=pd.to_numeric(h.cons_maxiob.str.replace(",","."),errors="coerce")
# reverse-engineer what maxIob the brake implies given the gate string
def implied(row):
    if not isinstance(row.gate,str): return np.nan
    if "iobHeadroom:0.40" in row.gate: return round(row.iob/0.85,2)  # f>=0.85 => maxiob<=iob/0.85
    return np.nan
h["maxiob_implied_from_brake"]=h.apply(implied,axis=1)
print(h.assign(t=h.ts_utc.astype(str).str[11:16])[["t","bg","st","iob","budget","fd","cons_maxiob","ccap","fcap","ps","gate","maxiob_implied_from_brake"]].round(2).to_string(index=False))
mask=h[h.cons_maxiob==1.0]; norm=h[h.cons_maxiob==8.0]
print(f"\nMASK window (cons_maxIOB=1.0): n={len(mask)} ps={sorted(mask.ps.dropna().unique())} caps={sorted(mask.ccap.dropna().unique())}/{sorted(mask.fcap.dropna().unique())} fd_sum={mask.fd.sum():.2f} budget_range={mask.budget.min():.1f}-{mask.budget.max():.1f}")
print(f"NORMAL (cons_maxIOB=8.0): n={len(norm)} ps={sorted(norm.ps.dropna().unique())} caps={sorted(norm.ccap.dropna().unique())}/{sorted(norm.fcap.dropna().unique())}")
# verify: at IOB 1.04, maxIob=1.0 -> brake=0.40 AND clamp headroom
for iobv,mx in [(1.04,1.0),(1.04,8.0),(0.93,8.0)]:
    print(f"  check iob={iobv} maxIob={mx}: brake={brake(iobv,mx)}, clamp_headroom={clamp_headroom(iobv,mx):.2f}")

print("\n=== full-day mask correlation (H) ===")
day=pd.read_sql("""
WITH d AS (SELECT DISTINCT ON (floor(ts_epoch/300.0)) substring(console_error from 'maxIOB: ?([0-9.,]+)') mx, boost_profile_switch ps FROM boost_decisions WHERE user_id='H' AND boostv5_state IS NOT NULL AND ts_utc>=timestamptz '2026-07-07 00:00+00' ORDER BY floor(ts_epoch/300.0), ts_epoch DESC)
SELECT mx, ps, count(*) n FROM d GROUP BY mx,ps ORDER BY n DESC""",conn)
print(day.to_string(index=False))
# whole-history: does maxIOB=1.0 EVER occur without ps!=100?
hist=pd.read_sql("""
WITH d AS (SELECT DISTINCT ON (floor(ts_epoch/300.0)) substring(console_error from 'maxIOB: ?([0-9.,]+)') mx, boost_profile_switch ps, ts_utc FROM boost_decisions WHERE user_id='H' ORDER BY floor(ts_epoch/300.0), ts_epoch DESC)
SELECT (mx='1.0') mask, (ps IS DISTINCT FROM 100) pct_switch, count(*) n FROM d WHERE mx IS NOT NULL GROUP BY 1,2 ORDER BY 1,2""",conn)
print("\nmask (maxIOB=1.0) vs pct-switch(ps!=100) crosstab, H full history:")
print(hist.to_string(index=False))

print("\n=== PART B: counterfactual — brake sees correct maxIob=8 ===")
# replay the mask-window CONFIRMED/COMMITTED cycles with maxIob=8: dose = min(budget*mult, cap) through brake(iob,8)+clamp(iob,8)
MULT={"CONFIRMED":1.8,"COMMITTED":1.0,"RECOVERING":0.4,"OBSERVING":0.3,"IDLE":1.0}
# use REAL caps (confirmedCap 4.0, committedCap ~1.2) that also unmask
REAL_FCAP, REAL_CCAP = 4.0, 1.2
knob=1.3  # user H's unknown; use 1.0 conservative + note. Actually H knob:
kn=pd.read_sql("SELECT boostv5_aggressionknob k FROM boost_decisions WHERE user_id='H' AND boostv5_aggressionknob IS NOT NULL ORDER BY ts_epoch DESC LIMIT 1",conn)
knob=float(kn.k.iloc[0]) if len(kn) else 1.0
print(f"(H aggression knob = {knob:.2f})")
mw=h[h.cons_maxiob==1.0].copy()
rows=[]
for _,r in mw.iterrows():
    mult=MULT.get(r.st,1.0)*(knob if r.st=="CONFIRMED" else 1.0)
    cap=REAL_FCAP if r.st=="CONFIRMED" else (REAL_CCAP if r.st=="COMMITTED" else 8.0)
    raw=min(r.budget*mult, cap)
    # maxIob=8 path: clamp then brake (decel unknown here; apply brake only, note decel separately)
    d_clamp=min(raw, clamp_headroom(r.iob,8.0))
    d_brake=d_clamp*brake(r.iob,8.0)
    rows.append(dict(t=str(r.ts_utc)[11:16],st=r.st,bg=r.bg,iob=round(r.iob,2),budget=round(r.budget,2),
        actual_fd=r.fd, cf_dose_maxiob8=round(d_brake,2), cap=cap))
cf=pd.DataFrame(rows); print(cf.to_string(index=False))
print(f"\nmask-window delivered: actual {mw.fd.sum():.2f}U  vs  counterfactual (maxIob=8, real caps, pre-decel) {cf.cf_dose_maxiob8.sum():.2f}U")
print("(counterfactual excludes decel brake — those cycles were CONFIRMED/COMMITTED still climbing, decel~1.0)")
cf.to_csv(f"{OUT}/partB_counterfactual.csv",index=False)
conn.close()
