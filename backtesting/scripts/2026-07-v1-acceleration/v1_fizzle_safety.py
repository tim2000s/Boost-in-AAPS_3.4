"""
V1 early-tier FIZZLE-SAFETY (the developer's design thesis): V1's early tiers deliver a small
acceleration-triggered bolus SIZED so that if the meal doesn't continue, it's harmless.
Test it on V1-era production data (V1 actually dosed these).

Anchor = acceleration fire: delta_accl > 10, V1 delivered an early bolus (v1_units>0),
         rising, dedupe 20 min.  (V1-era = boostv5_state null & ml_meal_likely null.)
Forward: peak_next = max BG in (0,60]min ; low_next = any BG<70 in (30,150]min ; sev<54.
  CONTINUED = peak_next >= bg0+30 (a real meal)
  FIZZLE    = peak_next <  bg0+15 (rise didn't materialise) -> the safety-critical case

Fizzle-safe IFF the FIZZLE low rate is NOT elevated over a matched-state baseline
(ambient low rate at the same BG+IOB band, rising, NON-accelerating cycles).
Per-user + pooled, cluster-bootstrap by user. Counterfactual caveat: V1 dosed broadly,
so the baseline is matched-ambient, not a true no-dose control — stated, not hidden.
"""
import psycopg2, numpy as np, pandas as pd
np.random.seed(20260720)
con = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
  select user_id, ts_epoch, cgm_mgdl, delta_acceleration, v1_units, iob_iob,
         (cgm_mgdl - lag(cgm_mgdl) over (partition by user_id order by ts_epoch)) as delta_est
  from boost_decisions
  where boostv5_state is null and ml_meal_likely is null and delta_acceleration is not null
        and cgm_mgdl is not null
""", con)
con.close()

def bgbin(x): return int(np.clip(x//10*10, 60, 250))
def iobbin(x):
    if x is None or np.isnan(x): return -99
    return int(np.clip(round(x*2)/2, -1, 6)*2)   # 0.5U bins

rows = []
baseline_cells = {}   # (bgbin,iobbin) -> [low_next flags] for rising non-accel cycles
for uid, g in df.groupby('user_id'):
    g = g.sort_values('ts_epoch').reset_index(drop=True)
    t = g['ts_epoch'].values.astype(float); bg = g['cgm_mgdl'].values.astype(float)
    accl = g['delta_acceleration'].values.astype(float)
    units = np.nan_to_num(g['v1_units'].values.astype(float))
    iob = g['iob_iob'].values.astype(float)
    dlt = g['delta_est'].values.astype(float)
    def fwd(i):
        pk = (t > t[i]) & (t <= t[i]+60*60); lo = (t > t[i]+30*60) & (t <= t[i]+150*60)
        if pk.sum() < 3 or lo.sum() < 3: return None
        return np.nanmax(bg[pk]), int(np.nanmin(bg[lo]) < 70), int(np.nanmin(bg[lo]) < 54)
    # baseline cells: rising, NON-accel cycles
    for i in range(len(g)):
        if dlt[i] is None or np.isnan(dlt[i]) or dlt[i] <= 0 or accl[i] > 10: continue
        f = fwd(i)
        if f: baseline_cells.setdefault((bgbin(bg[i]), iobbin(iob[i])), []).append(f[1])
    # fires: accl>10, dosed, rising, dedupe
    last = -1e18
    for i in range(len(g)):
        if not (accl[i] > 10 and units[i] > 0 and dlt[i] is not None and not np.isnan(dlt[i]) and dlt[i] > 0):
            continue
        if t[i]-last < 20*60: continue
        f = fwd(i)
        if not f: continue
        last = t[i]
        peak, low, sev = f
        kind = 'CONTINUED' if peak >= bg[i]+30 else ('FIZZLE' if peak < bg[i]+15 else 'mid')
        rows.append(dict(user=uid, kind=kind, bg0=bg[i], units=units[i], low=low, sev=sev,
                         cell=(bgbin(bg[i]), iobbin(iob[i]))))
R = pd.DataFrame(rows)
base = {k: np.mean(v) for k, v in baseline_cells.items() if len(v) >= 20}
R['base'] = R['cell'].map(base)

def cb(d, col, nb=3000):
    us=d.user.unique(); by={u:d[d.user==u][col].dropna().values for u in us}; v=[]
    for _ in range(nb):
        bu=np.random.choice(us,len(us),True); p=np.concatenate([by[u] for u in bu if len(by[u])])
        if len(p): v.append(p.mean())
    return np.percentile(v,[2.5,50,97.5])

fz = R[R.kind=='FIZZLE']; ct = R[R.kind=='CONTINUED']
print(f"acceleration fires (accl>10, V1 dosed): {len(R)}  | CONTINUED {len(ct)} ({len(ct)/len(R):.0%}), "
      f"FIZZLE {len(fz)} ({len(fz)/len(R):.0%}), mid {sum(R.kind=='mid')}")
print(f"dose on fires: median {R.units.median():.2f}U  mean {R.units.mean():.2f}U  (small = fizzle-safe by size)\n")
print("=== PER-USER: FIZZLE low<70 vs matched-ambient baseline ===")
print(f"{'user':4} {'nFz':>4} {'fzLow':>6} {'base':>6} {'fzSev':>6} {'ctLow':>6}")
for u in sorted(R.user.unique()):
    fu=fz[fz.user==u]; cu=ct[ct.user==u]
    if len(fu)<10: continue
    print(f"{u:4} {len(fu):>4} {fu.low.mean():>6.1%} {fu.base.dropna().mean():>6.1%} {fu.sev.mean():>6.1%} {cu.low.mean() if len(cu) else float('nan'):>6.1%}")
print("\n=== POOLED (cluster-bootstrap by user, 95% CI) ===")
fl,fm,fh=cb(fz,'low'); bl,bm,bh=cb(fz.dropna(subset=['base']),'base'); sl,sm,sh=cb(fz,'sev')
# paired diff fizzle-low − matched-base, resampling users jointly
us=fz.user.unique(); byL={u:fz[fz.user==u]['low'].values for u in us}; byB={u:fz[fz.user==u]['base'].dropna().values for u in us}
d=[]
for _ in range(3000):
    bu=np.random.choice(us,len(us),True)
    L=np.concatenate([byL[u] for u in bu]); B=np.concatenate([byB[u] for u in bu if len(byB[u])])
    if len(L) and len(B): d.append(L.mean()-B.mean())
dl,dm,dh=np.percentile(d,[2.5,50,97.5])
print(f"FIZZLE low<70 rate      {fm:.1%} [{fl:.1%}, {fh:.1%}]")
print(f"matched-ambient base    {bm:.1%} [{bl:.1%}, {bh:.1%}]")
print(f"Δ (fizzle − baseline)   {dm:+.1%} [{dl:+.1%}, {dh:+.1%}]  -> {'EXCESS lows' if dl>0 else 'no excess (fizzle-safe)'}")
print(f"FIZZLE severe<54 rate   {sm:.1%} [{sl:.1%}, {sh:.1%}]")
