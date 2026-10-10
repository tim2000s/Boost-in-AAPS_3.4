"""
V1 fizzle-safety, ATTRIBUTED (developer's correction): allocate a low to the fizzle bolus only
if the bolus itself plausibly caused it — i.e. the insulin delivered AFTER the fizzle bolus
and before the low is NOT the dominant cause. Otherwise the low is a downstream-dosing low.

For each FIZZLE fire (accl>10, V1 dosed u0, peak_next<bg0+15):
  find first low (<70) in (t0+30, t0+150]min at t_low, and subseq = sum(v1_units in (t0,t_low]).
  PURE fizzle low  = low AND subseq <= u0      (early bolus is the dominant/last insulin)
  DOWNSTREAM low   = low AND subseq >  u0       (later SMBs are the real culprit)
Compare the PURE fizzle-low rate to the matched-ambient baseline (also attributed the same way:
an ambient low counts only if subseq <= that cycle's own dose). Apples-to-apples.
Per-user + pooled, cluster-bootstrap by user.
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

def bgbin(x): return int(np.clip(x//10*10,60,250))
def iobbin(x):
    if x is None or np.isnan(x): return -99
    return int(np.clip(round(x*2)/2,-1,6)*2)

def attribute_low(t, bg, units, i):
    """Return (had_low, pure_low): pure if the anchor's own dose >= insulin delivered after it before the low."""
    lo = (t > t[i]+30*60) & (t <= t[i]+150*60)
    if lo.sum() < 3: return None
    idx = np.where(lo)[0]
    below = idx[bg[idx] < 70]
    if len(below) == 0: return (0, 0)
    tlow = t[below[0]]
    subseq = units[(t > t[i]) & (t <= tlow)].sum()   # insulin AFTER the anchor bolus, before the low
    pure = 1 if subseq <= units[i] else 0
    return (1, pure)

rows, base_cells = [], {}
for uid, g in df.groupby('user_id'):
    g = g.sort_values('ts_epoch').reset_index(drop=True)
    t=g['ts_epoch'].values.astype(float); bg=g['cgm_mgdl'].values.astype(float)
    accl=g['delta_acceleration'].values.astype(float); units=np.nan_to_num(g['v1_units'].values.astype(float))
    iob=g['iob_iob'].values.astype(float); dlt=g['delta_est'].values.astype(float)
    # baseline cells (rising, non-accel), attributed the same way
    for i in range(len(g)):
        if dlt[i] is None or np.isnan(dlt[i]) or dlt[i] <= 0 or accl[i] > 10: continue
        a = attribute_low(t,bg,units,i)
        if a: base_cells.setdefault((bgbin(bg[i]),iobbin(iob[i])),[]).append(a[1])  # pure-attributed low
    last=-1e18
    for i in range(len(g)):
        if not (accl[i]>10 and units[i]>0 and dlt[i] is not None and not np.isnan(dlt[i]) and dlt[i]>0): continue
        if t[i]-last<20*60: continue
        pk=(t>t[i])&(t<=t[i]+60*60)
        if pk.sum()<3: continue
        if np.nanmax(bg[pk]) >= bg[i]+15: continue   # keep FIZZLE only
        a = attribute_low(t,bg,units,i)
        if not a: continue
        last=t[i]
        rows.append(dict(user=uid, u0=units[i], raw=a[0], pure=a[1], downstream=a[0]-a[1], cell=(bgbin(bg[i]),iobbin(iob[i]))))
R=pd.DataFrame(rows)
base={k:np.mean(v) for k,v in base_cells.items() if len(v)>=20}
R['base']=R['cell'].map(base)

def cb(d,col,nb=3000):
    us=d.user.unique(); by={u:d[d.user==u][col].dropna().values for u in us}; v=[]
    for _ in range(nb):
        bu=np.random.choice(us,len(us),True); p=np.concatenate([by[u] for u in bu if len(by[u])])
        if len(p): v.append(p.mean())
    return np.percentile(v,[2.5,50,97.5])

print(f"FIZZLE fires (dosed): {len(R)}   with a low: {R.raw.sum()} "
      f"(pure→fizzle bolus {R.pure.sum()}, downstream→later dosing {R.downstream.sum()})\n")
print("=== PER-USER: raw fizzle-low  vs  PURE (bolus-attributed)  vs  matched baseline ===")
print(f"{'user':4} {'nFz':>4} {'raw':>6} {'pure':>6} {'base':>6}  {'%downstream':>11}")
for u in sorted(R.user.unique()):
    ru=R[R.user==u]
    if len(ru)<10: continue
    dshare = ru.downstream.sum()/ru.raw.sum() if ru.raw.sum() else 0
    print(f"{u:4} {len(ru):>4} {ru.raw.mean():>6.1%} {ru.pure.mean():>6.1%} {ru.base.dropna().mean():>6.1%}  {dshare:>10.0%}")
print("\n=== POOLED (cluster-bootstrap by user, 95% CI) ===")
rl,rm,rh=cb(R,'raw'); pl,pm,ph=cb(R,'pure'); bl,bm,bh=cb(R.dropna(subset=['base']),'base')
us=R.user.unique(); byP={u:R[R.user==u]['pure'].values for u in us}; byB={u:R[R.user==u]['base'].dropna().values for u in us}
d=[]
for _ in range(3000):
    bu=np.random.choice(us,len(us),True)
    P=np.concatenate([byP[u] for u in bu]); B=np.concatenate([byB[u] for u in bu if len(byB[u])])
    if len(P) and len(B): d.append(P.mean()-B.mean())
dl,dm,dh=np.percentile(d,[2.5,50,97.5])
print(f"raw fizzle low<70           {rm:.1%} [{rl:.1%}, {rh:.1%}]")
print(f"PURE (bolus-attributed) low {pm:.1%} [{pl:.1%}, {ph:.1%}]")
print(f"matched-ambient baseline    {bm:.1%} [{bl:.1%}, {bh:.1%}]")
print(f"Δ (pure − baseline)         {dm:+.1%} [{dl:+.1%}, {dh:+.1%}]  -> {'EXCESS' if dl>0 else 'no excess (fizzle bolus itself is safe)'}")
