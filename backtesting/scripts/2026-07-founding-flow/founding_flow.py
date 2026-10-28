"""
Founding-Boost flow backtest: seed early -> trigger UAM -> firm up on behaviour -> appropriate dose.
Did V6 slip off the early graded delivery, and does bringing it back help?

Anchor = acceleration SEED: delta_accl>10, rising, BG 90-160 (meal onset), pre-confirm
(V1-era = both telemetry null; V6-era = state IDLE/OBSERVING), leading to a REAL meal
(peak in +90min >= bg0+40). Dedupe 30 min. v1_units = actual delivered SMB (both eras).

(1) Does the seed trigger the loop's response earlier? — UAM prediction (uampredbg) is
    era-agnostic, so measure DOSING relative to it: time-to-first-dose, and insulin
    delivered BY the moment UAM engages (uampredbg - bg > 25).
(2) Firm-up curve — cumulative delivered at T+10..45 from the seed: V1 graded ramp vs
    V6 flat-then-step? Plus outcome: peak BG + low rate (earlier delivery without more lows?).

Within-user (users with both eras), cluster-bootstrap by user.
"""
import psycopg2, numpy as np, pandas as pd
np.random.seed(20260720)
con = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
  select user_id, ts_epoch, cgm_mgdl, delta_acceleration, v1_units, iob_iob,
         reason_uampredbg, boostv5_state, ml_meal_likely
  from boost_decisions where cgm_mgdl is not null and delta_acceleration is not null
""", con)
con.close()
df['era'] = np.where(df.boostv5_state.notna(), 'V6',
             np.where(df.ml_meal_likely.notna(), 'ML', 'V1'))
df = df[df.era.isin(['V1', 'V6'])].copy()

Ts = [10, 20, 30, 45]
rows = []
for uid, g in df.groupby('user_id'):
    g = g.sort_values('ts_epoch').reset_index(drop=True)
    t = g.ts_epoch.values.astype(float); bg = g.cgm_mgdl.values.astype(float)
    accl = g.delta_acceleration.values.astype(float); units = np.nan_to_num(g.v1_units.values.astype(float))
    uam = g.reason_uampredbg.values.astype(float); st = g.boostv5_state.values; era = g.era.values
    # per-cycle delta est
    d = np.diff(bg, prepend=bg[0])
    last = {'V1': -1e18, 'V6': -1e18}
    for i in range(len(g)):
        e = era[i]
        preconfirm = (e == 'V1') or (st[i] in ('IDLE', 'OBSERVING'))
        if not (accl[i] > 10 and d[i] > 0 and 90 <= bg[i] <= 160 and preconfirm): continue
        if t[i] - last[e] < 30*60: continue
        pk = (t > t[i]) & (t <= t[i]+90*60)
        if pk.sum() < 5: continue
        peak = np.nanmax(bg[pk])
        if peak < bg[i] + 40: continue           # real meal only
        last[e] = t[i]
        row = dict(user=uid, era=e, bg0=bg[i], peak=peak)
        # (2) cumulative delivered at each horizon
        for T in Ts:
            w = (t > t[i]) & (t <= t[i]+T*60)
            row[f'cum{T}'] = units[w].sum()
        # (1) UAM engagement time + dose delivered by then
        we = (t > t[i]) & (t <= t[i]+60*60)
        idx = np.where(we)[0]
        eng = idx[(uam[idx] - bg[idx]) > 25]
        if len(eng):
            teng = (t[eng[0]] - t[i]) / 60.0
            row['uam_engage_min'] = teng
            row['dose_by_engage'] = units[(t > t[i]) & (t <= t[eng[0]])].sum()
        else:
            row['uam_engage_min'] = np.nan; row['dose_by_engage'] = np.nan
        # time to first meaningful dose
        fd = idx[units[idx] > 0.1]
        row['first_dose_min'] = (t[fd[0]] - t[i]) / 60.0 if len(fd) else np.nan
        # outcome: low in +30..180
        lo = (t > t[i]+30*60) & (t <= t[i]+180*60)
        row['low'] = int(np.nanmin(bg[lo]) < 70) if lo.sum() else np.nan
        rows.append(row)
r = pd.DataFrame(rows)
# users with both eras, >=15 anchors each
cnt = r.groupby(['user','era']).size().unstack().fillna(0)
both = cnt[(cnt.get('V1',0) >= 15) & (cnt.get('V6',0) >= 15)].index.tolist()
r = r[r.user.isin(both)].copy()
print(f"anchors (real-meal seeds): {len(r)}  users w/ both eras: {len(both)}  "
      f"(V1 {sum(r.era=='V1')}, V6 {sum(r.era=='V6')})\n")

def cbdiff(col, nb=3000):
    us = r.user.unique()
    a = {u: r[(r.user==u)&(r.era=='V1')][col].dropna().values for u in us}
    b = {u: r[(r.user==u)&(r.era=='V6')][col].dropna().values for u in us}
    va=[]; vb=[]; vd=[]
    for _ in range(nb):
        bu = np.random.choice(us, len(us), True)
        la = [a[u] for u in bu if len(a[u])]; lb = [b[u] for u in bu if len(b[u])]
        if not la or not lb: continue
        pa = np.concatenate(la); pb = np.concatenate(lb)
        va.append(pa.mean()); vb.append(pb.mean()); vd.append(pa.mean()-pb.mean())
    if not vd: return (np.array([np.nan]*3),)*3
    return (np.percentile(va,[2.5,50,97.5]), np.percentile(vb,[2.5,50,97.5]), np.percentile(vd,[2.5,50,97.5]))

def fmt(x, pct=False): return f"{x:5.1%}" if pct else f"{x:5.2f}"
print("=== (2) FIRM-UP CURVE — cumulative SMB delivered by T min after the seed (U) ===")
print(f"{'horizon':>8} {'V1':>7} {'V6':>7} {'V1-V6 (95% CI)':>22}")
for T in Ts:
    (a,b,dd) = cbdiff(f'cum{T}')
    v = "V1 EARLIER" if dd[0]>0 else ("V6 earlier" if dd[2]<0 else "ns")
    print(f"  T+{T:<4} {fmt(a[1])} {fmt(b[1])}   {fmt(dd[1])} [{fmt(dd[0])},{fmt(dd[2])}]  {v}")
print("\n=== (1) SEED TRIGGERS RESPONSE EARLIER ===")
for col, lab, pct in [('first_dose_min','time to first dose ≥0.1U (min)',False),
                      ('dose_by_engage','SMB delivered by UAM-engagement (U)',False),
                      ('uam_engage_min','UAM engages at (min, era-agnostic check)',False)]:
    (a,b,dd) = cbdiff(col)
    print(f"  {lab:42} V1 {fmt(a[1])}  V6 {fmt(b[1])}  Δ {fmt(dd[1])} [{fmt(dd[0])},{fmt(dd[2])}]")
print("\n=== OUTCOME (does earlier delivery cost lows?) ===")
(a,b,dd) = cbdiff('low')
print(f"  low<70 rate (30-180min)   V1 {fmt(a[1],1)}  V6 {fmt(b[1],1)}  Δ {fmt(dd[1],1)} [{fmt(dd[0],1)},{fmt(dd[2],1)}]")
(a,b,dd) = cbdiff('peak')
print(f"  peak BG (mg/dL)           V1 {a[1]:5.0f}  V6 {b[1]:5.0f}  Δ {dd[1]:+5.0f} [{dd[0]:+.0f},{dd[2]:+.0f}]")
print("\n=== PER-USER first-dose timing (min) V1 vs V6 ===")
for u in sorted(both):
    ru = r[r.user==u]
    v1 = ru[ru.era=='V1'].first_dose_min.dropna(); v6 = ru[ru.era=='V6'].first_dose_min.dropna()
    if len(v1) and len(v6):
        print(f"  {u:4} V1 {v1.median():4.1f}  V6 {v6.median():4.1f}  (cum30: V1 {ru[ru.era=='V1'].cum30.mean():.2f} V6 {ru[ru.era=='V6'].cum30.mean():.2f})")
