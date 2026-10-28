#!/usr/bin/env python3
"""needs_breakdown.py — INTENDED vs RETROSPECTIVE-need vs DELIVERED per meal cycle.

For each CONFIRMED/COMMITTED cycle in a user's V6-ACTIVE era (boostv5_active=true, dedup last-invoke
per 5-min bucket):
  1. INTENDED   = budget × actionMult × velocityFactor   (pre-cap, pre-maxIOB, pre-round — what V6 WANTS)
                  actionMult: CONFIRMED = 1.8×knob, COMMITTED = 1.0 (logged boostv5_actionmult preferred)
                  velocityFactor from cumRise30 = max(0, shortAvgDelta×6): 0.4 (≤25) .. 1.0 (≥50) linear
  2. RETRO_NEED = max(0, (episode_actual_peak − target)/ISF − IOB)   (first-order, no absorption model)
                  target = cycle's sug_current_target; ISF = cycle's variable_sens (mg/dL/U); IOB = iob_iob
  3. DELIVERED  = boostv5_finaldose

Episode = contiguous run of meal/RECOVERING states (gap ≤10 min); peak = max BG over episode + 2 h.
REAL rise = BG sustained >180 for ≥30 min (≥6 consec) in episode+2h; else FIZZLE.

Outputs: out/H_needs.csv (per-cycle) + out/H_needs_summary.csv (distribution/gap table).
Usage: python3 needs_breakdown.py [USER]   # default H
"""
import sys, os, numpy as np, pandas as pd, psycopg2

USER = sys.argv[1] if len(sys.argv) > 1 else "H"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"); os.makedirs(OUT, exist_ok=True)
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
SELECT DISTINCT ON (floor(ts_epoch/300.0))
  ts_epoch, ts_utc, cgm_mgdl bg, boostv5_state state, boostv5_age age,
  boostv5_budget budget, boostv5_actionmult am, boostv5_finaldose fd,
  boostv5_aggressionknob knob, boostv5_committedcap cc, boostv5_confirmedcap fc,
  iob_iob iob, variable_sens isf, sug_current_target tgt
FROM boost_decisions WHERE user_id=%s AND boostv5_active=true
ORDER BY floor(ts_epoch/300.0), ts_epoch DESC
""", conn, params=(USER,)).sort_values("ts_epoch").reset_index(drop=True)
conn.close()

df["delta5"] = df.bg.diff() / (df.ts_epoch.diff()/60) * 5
df.loc[(df.ts_epoch.diff()/60 > 7.6) | (df.ts_epoch.diff()/60 < 2.0), "delta5"] = np.nan
df["cumRise30"] = (df.delta5.rolling(3, min_periods=1).mean() * 6).clip(lower=0)
df["velF"] = df.cumRise30.apply(lambda c: 1.0 if c >= 50 else (0.40 if c <= 25 else 0.40 + 0.60*(c-25)/25))
df["knob_use"] = df.knob.ffill().fillna(1.3)
df["isf_use"] = df.isf.replace(0, np.nan)
df["tgt_use"] = df.tgt

# episodes: contiguous meal/RECOVERING runs, gap<=600s; episode peak over run + 2h
df["ismeal_ext"] = df.state.isin(["CONFIRMED", "COMMITTED", "RECOVERING"])
ep_id = np.full(len(df), -1); eid = 0
i = 0
ts = df.ts_epoch.values; bg = df.bg.values; me = df.ismeal_ext.values
episodes = {}
while i < len(df):
    if me[i] and (i == 0 or not me[i-1] or ts[i]-ts[i-1] > 600):
        j = i
        while j+1 < len(df) and me[j+1] and ts[j+1]-ts[j] <= 600:
            j += 1
        end = ts[j]
        peak = bg[(ts >= ts[i]) & (ts <= end + 7200)].max()
        w = bg[(ts >= ts[i]) & (ts <= end + 7200)]
        over = (w > 180).astype(int); run = 0; mx = 0
        for o in over:
            run = run+1 if o else 0; mx = max(mx, run)
        real = mx >= 6  # >=30 min sustained >180
        ep_id[i:j+1] = eid
        episodes[eid] = dict(peak=peak, real=real, start=ts[i])
        eid += 1
        i = j+1
    else:
        i += 1
df["ep_id"] = ep_id
df["ep_peak"] = df.ep_id.map(lambda e: episodes.get(e, {}).get("peak", np.nan))
df["real"] = df.ep_id.map(lambda e: episodes.get(e, {}).get("real", np.nan))

meal = df[df.state.isin(["CONFIRMED", "COMMITTED"])].copy()
meal["am_use"] = meal.apply(lambda r: r.am if pd.notna(r.am)
                            else (1.8*r.knob_use if r.state == "CONFIRMED" else 1.0), axis=1)
meal["intended"] = meal.budget * meal.am_use * meal.velF
meal["retro_need"] = np.maximum(0.0, (meal.ep_peak - meal.tgt_use)/meal.isf_use - meal.iob)
meal["delivered"] = meal.fd
meal["rise"] = np.where(meal.real == True, "real", np.where(meal.real == False, "fizzle", "unk"))

# per-cycle CSV
cols = ["ts_utc","state","bg","budget","am_use","velF","intended","retro_need","delivered",
        "rise","ep_peak","tgt_use","isf_use","iob"]
meal[cols].rename(columns={"am_use":"actionMult","tgt_use":"target","isf_use":"isf"}).to_csv(
    f"{OUT}/{USER}_needs.csv", index=False)
print(f"[written] {OUT}/{USER}_needs.csv  ({len(meal)} meal cycles)")

def dist(s):
    s = s.dropna()
    if not len(s): return dict(n=0)
    q = np.percentile(s, [10,25,50,75,90,95])
    return dict(n=len(s), p10=round(q[0],2), p25=round(q[1],2), p50=round(q[2],2),
                p75=round(q[3],2), p90=round(q[4],2), p95=round(q[5],2), max=round(s.max(),2), mean=round(s.mean(),2))

rows = []
for st in ["CONFIRMED", "COMMITTED"]:
    for rise in ["all", "real", "fizzle"]:
        sub = meal[meal.state == st]
        if rise != "all": sub = sub[sub.rise == rise]
        for metric in ["intended", "retro_need", "delivered"]:
            d = dist(sub[metric])
            rows.append(dict(state=st, rise=rise, metric=metric, **d))
summary = pd.DataFrame(rows)
summary.to_csv(f"{OUT}/{USER}_needs_summary.csv", index=False)
print(f"[written] {OUT}/{USER}_needs_summary.csv")
pd.set_option("display.width", 240)
print("\n=== distribution table (U) ===")
print(summary.to_string(index=False))

print("\n=== GAP: mean intended vs delivered vs retro_need, per state × rise ===")
for st in ["CONFIRMED", "COMMITTED"]:
    for rise in ["real", "fizzle"]:
        sub = meal[(meal.state == st) & (meal.rise == rise)]
        if not len(sub): continue
        print(f"  {st}/{rise} (n={len(sub)}): intended {sub.intended.mean():.2f}  delivered {sub.delivered.mean():.2f}  "
              f"retro_need {sub.retro_need.mean():.2f}  | under-vs-need {sub.retro_need.mean()-sub.delivered.mean():+.2f}U/cyc  "
              f"| under-vs-intent {sub.intended.mean()-sub.delivered.mean():+.2f}U/cyc")

# episode-level headline: on REAL meals, per-episode delivered vs retro_need
epreal = meal[meal.rise == "real"].groupby("ep_id").agg(
    deliv=("delivered","sum"), retro=("retro_need","max"), intend=("intended","sum"), peak=("ep_peak","max"))
print(f"\n=== REAL-meal episodes (n={len(epreal)}): per-episode delivered vs retro_need ===")
if len(epreal):
    print(f"  delivered/episode: med {epreal.deliv.median():.2f}U  |  retro_need/episode: med {epreal.retro.median():.2f}U  "
          f"|  intended-sum/episode: med {epreal.intend.median():.2f}U")
    print(f"  SHORTFALL vs retro_need: med {(epreal.retro-epreal.deliv).clip(lower=0).median():.2f}U/episode, "
          f"mean {(epreal.retro-epreal.deliv).clip(lower=0).mean():.2f}U/episode, max {(epreal.retro-epreal.deliv).max():.2f}U")

# implied caps
cr = meal[(meal.state=="COMMITTED") & (meal.rise=="real")].intended
cf = meal[(meal.state=="CONFIRMED") & (meal.rise=="real")].intended
print("\n=== IMPLIED CAPS (to deliver intended-on-REAL) ===")
if len(cr):
    print(f"  committedCap to cover COMMITTED-real intended: p50={cr.median():.2f} p75={cr.quantile(.75):.2f} p90={cr.quantile(.9):.2f}  (current 1.2)")
if len(cf):
    print(f"  confirmedCap to cover CONFIRMED-real intended: p90={cf.quantile(.9):.2f} max={cf.max():.2f}  (current ~6)")
# auto-config formula proxies from his own dosing
smb = pd.read_sql if False else None
print("\n=== intended-vs-need divergence flag ===")
for st in ["CONFIRMED","COMMITTED"]:
    for rise in ["real","fizzle"]:
        sub = meal[(meal.state==st)&(meal.rise==rise)]
        if len(sub)>=3:
            div = sub.intended.mean() - sub.retro_need.mean()
            tag = "engine WANTS MORE than outcomes justify" if div>0.3 else ("engine wants LESS than needed" if div<-0.3 else "aligned")
            print(f"  {st}/{rise}: intended {sub.intended.mean():.2f} vs retro_need {sub.retro_need.mean():.2f} -> {tag}")
