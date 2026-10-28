"""
The untested case: meals V6's confirm gate UNDER-responds to. The prior founding-flow
backtest only saw seeds that led to real meals in both eras; it can't see meals V6 held
OBSERVING on while BG climbed (the 26-29% over-blocked-confirm finding). Does the founding
seed/primer restore the early insulin V6's gate withheld?

V6-era anchor = acceleration seed (delta_accl>10, rising, BG 90-160, state IDLE/OBSERVING)
that became a HIGH (peak in +90min > 170). Split by V6's response:
  RESPONSIVE = V6 reached CONFIRMED within 20 min of the seed
  OVER-BLOCKED = V6 stayed IDLE/OBSERVING for 20 min (gated — dosed only V1 base)
Compare cumulative SMB delivered (T+15/+30), peak, low. Also the V1-era same-setup seeds.

The primer fires on exactly the over-blocked pattern (accel>10 in OBSERVING) — so its
early insulin is the withheld amount. Quantify the deficit + whether over-blocking costs peak.
Within-user where possible; cluster-bootstrap by user.
"""
import psycopg2, numpy as np, pandas as pd
np.random.seed(20260720)
con = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
  select user_id, ts_epoch, cgm_mgdl, delta_acceleration, v1_units,
         boostv5_state, ml_meal_likely
  from boost_decisions where cgm_mgdl is not null and delta_acceleration is not null
""", con)
con.close()
df['era'] = np.where(df.boostv5_state.notna(), 'V6',
             np.where(df.ml_meal_likely.notna(), 'ML', 'V1'))

rows = []
for uid, g in df.groupby('user_id'):
    g = g.sort_values('ts_epoch').reset_index(drop=True)
    t = g.ts_epoch.values.astype(float); bg = g.cgm_mgdl.values.astype(float)
    accl = g.delta_acceleration.values.astype(float); units = np.nan_to_num(g.v1_units.values.astype(float))
    st = g.boostv5_state.values; era = g.era.values
    d = np.diff(bg, prepend=bg[0])
    last = {'V1': -1e18, 'V6': -1e18}
    for i in range(len(g)):
        e = era[i]
        if e == 'ML': continue
        preconfirm = (e == 'V1') or (st[i] in ('IDLE', 'OBSERVING'))
        if not (accl[i] > 10 and d[i] > 0 and 90 <= bg[i] <= 160 and preconfirm): continue
        if t[i] - last[e] < 30*60: continue
        pk = (t > t[i]) & (t <= t[i]+90*60)
        if pk.sum() < 5: continue
        peak = np.nanmax(bg[pk])
        if peak <= 170: continue                       # HIGH meals only (the over-block cost surface)
        last[e] = t[i]
        cum15 = units[(t > t[i]) & (t <= t[i]+15*60)].sum()
        cum30 = units[(t > t[i]) & (t <= t[i]+30*60)].sum()
        lo = (t > t[i]+30*60) & (t <= t[i]+180*60)
        low = int(np.nanmin(bg[lo]) < 70) if lo.sum() else np.nan
        grp = 'V1'
        if e == 'V6':
            w20 = (t > t[i]) & (t <= t[i]+20*60)
            confirmed20 = np.isin(st[w20], ['CONFIRMED', 'COMMITTED']).any()
            grp = 'V6_responsive' if confirmed20 else 'V6_overblocked'
        rows.append(dict(user=uid, grp=grp, bg0=bg[i], peak=peak, cum15=cum15, cum30=cum30, low=low))
r = pd.DataFrame(rows)

n_v6 = ((r.grp=='V6_responsive')|(r.grp=='V6_overblocked')).sum()
n_ob = (r.grp=='V6_overblocked').sum()
print(f"V6-era HIGH acceleration-meals: {n_v6}   OVER-BLOCKED (no confirm in 20min): {n_ob} ({n_ob/n_v6:.0%})")
print(f"V1-era HIGH acceleration-meals: {(r.grp=='V1').sum()}\n")

def stat(grp, col):
    us = r.user.unique(); by = {u: r[(r.user==u)&(r.grp==grp)][col].dropna().values for u in us}
    vals=[]
    for _ in range(3000):
        bu = np.random.choice(us, len(us), True)
        p = np.concatenate([by[u] for u in bu if len(by[u])]) if any(len(by[u]) for u in bu) else np.array([])
        if len(p): vals.append(p.mean())
    return np.percentile(vals,[2.5,50,97.5]) if vals else np.array([np.nan]*3)

print(f"{'group':16} {'n':>5} {'cum15':>14} {'cum30':>14} {'peak':>10} {'low<70':>8}")
for grp in ['V6_overblocked','V6_responsive','V1']:
    n = (r.grp==grp).sum()
    c15=stat(grp,'cum15'); c30=stat(grp,'cum30'); pk=stat(grp,'peak'); lw=stat(grp,'low')
    print(f"{grp:16} {n:>5}  {c15[1]:4.2f}[{c15[0]:.2f},{c15[2]:.2f}] {c30[1]:4.2f}[{c30[0]:.2f},{c30[2]:.2f}] {pk[1]:4.0f}[{pk[0]:.0f},{pk[2]:.0f}] {lw[1]:5.1%}")

# the withheld early insulin = responsive - overblocked at T+15/T+30 (what the gate cost)
def cbdiff(gA, gB, col):
    us = r.user.unique()
    a={u:r[(r.user==u)&(r.grp==gA)][col].dropna().values for u in us}; b={u:r[(r.user==u)&(r.grp==gB)][col].dropna().values for u in us}
    vd=[]
    for _ in range(3000):
        bu=np.random.choice(us,len(us),True)
        la=[a[u] for u in bu if len(a[u])]; lb=[b[u] for u in bu if len(b[u])]
        if la and lb: vd.append(np.concatenate(la).mean()-np.concatenate(lb).mean())
    return np.percentile(vd,[2.5,50,97.5]) if vd else np.array([np.nan]*3)

print("\n=== the deficit the gate creates (over-blocked vs responsive) ===")
for col in ['cum15','cum30','peak']:
    dd = cbdiff('V6_overblocked','V6_responsive',col)
    tag = 'U' if 'cum' in col else 'mg/dL'
    print(f"  {col}: over-blocked − responsive = {dd[1]:+.2f} [{dd[0]:+.2f},{dd[2]:+.2f}] {tag}")
print("\n=== over-blocked V6 vs V1 (does the founding flow deliver where V6's gate doesn't?) ===")
for col in ['cum15','cum30','peak']:
    dd = cbdiff('V6_overblocked','V1',col)
    tag = 'U' if 'cum' in col else 'mg/dL'
    print(f"  {col}: over-blocked V6 − V1 = {dd[1]:+.2f} [{dd[0]:+.2f},{dd[2]:+.2f}] {tag}")
