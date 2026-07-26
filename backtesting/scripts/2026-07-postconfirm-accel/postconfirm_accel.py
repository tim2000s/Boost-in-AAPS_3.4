"""
Question (Tim): after a CONFIRMED commit-shot, if deltas are STILL ACCELERATING,
is that a signal to dose MORE (a 'second confirm')?

Clean PREDICTION test (identification-safe: we keep observed BG, just ask what follows):
  Anchor = each CONFIRMED cycle.
  Split anchors by post-confirm acceleration over the next ~10-15 min:
     STILL-ACCEL  = mean delta_acceleration(+5..+15min) > +5
     DECEL        = mean delta_acceleration(+5..+15min) < 0
  Forward outcomes from the anchor:
     peak BG within +90 min
     min  BG within +30..+180 min   (the crash window)
     LOW  = any BG < 70 within +30..+180 min  (binary)
     SEVERE LOW = any BG < 54 in same window

If STILL-ACCEL predicts sustained high with NO excess lows -> case for dosing more.
If STILL-ACCEL predicts MORE lows -> a 'second confirm' is contraindicated (it's the
fast-carb overshoot shape). Report per-user + pooled with cluster-bootstrap 95% CI.
"""
import psycopg2, numpy as np, pandas as pd

np.random.seed(20260720)
con = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
  select user_id, ts_epoch, cgm_mgdl, boostv5_state, delta_acceleration
  from boost_decisions where boostv5_state is not null and cgm_mgdl is not null
""", con)
con.close()

ACCEL_HI = 5.0      # "still accelerating" threshold (mg/dL/5min^2-ish, the delta_accl units)
PEAK_MIN = 90       # peak window minutes
LOW_LO, LOW_HI = 30, 180  # crash window minutes
rows = []
for uid, g in df.groupby('user_id'):
    g = g.sort_values('ts_epoch').reset_index(drop=True)
    t = g['ts_epoch'].values.astype(float)
    bg = g['cgm_mgdl'].values.astype(float)
    accl = g['delta_acceleration'].values.astype(float)
    st = g['boostv5_state'].values
    conf_idx = np.where(st == 'CONFIRMED')[0]
    for i in conf_idx:
        t0 = t[i]
        # post-confirm accel window +5..+15 min
        win = (t > t0 + 4*60) & (t <= t0 + 16*60)
        if win.sum() == 0: continue
        pa = np.nanmean(accl[win])
        if np.isnan(pa): continue
        # forward BG windows
        pk = (t > t0) & (t <= t0 + PEAK_MIN*60)
        lo = (t > t0 + LOW_LO*60) & (t <= t0 + LOW_HI*60)
        if pk.sum() == 0 or lo.sum() == 0: continue
        peak = np.nanmax(bg[pk]); mn = np.nanmin(bg[lo])
        rows.append(dict(user=uid, postaccl=pa, bg0=bg[i], peak=peak, minbg=mn,
                         low=int(mn < 70), severe=int(mn < 54)))
r = pd.DataFrame(rows)
r['grp'] = np.where(r.postaccl > ACCEL_HI, 'STILL-ACCEL',
            np.where(r.postaccl < 0, 'DECEL', 'flat'))
r = r[r.grp != 'flat'].copy()

def cluster_boot(sub, col, nb=4000):
    users = sub.user.unique()
    vals = []
    by = {u: sub[sub.user == u][col].values for u in users}
    for _ in range(nb):
        bu = np.random.choice(users, len(users), replace=True)
        pool = np.concatenate([by[u] for u in bu])
        vals.append(pool.mean())
    return np.percentile(vals, [2.5, 50, 97.5])

print(f"anchors used: {len(r)}  (STILL-ACCEL {sum(r.grp=='STILL-ACCEL')}, DECEL {sum(r.grp=='DECEL')})\n")
print("=== PER-USER (n_accel / n_decel | peak mg/dL | low<70 rate | severe<54 rate) ===")
print(f"{'user':4} {'nA':>4} {'nD':>4} | {'peakA':>6} {'peakD':>6} | {'lowA':>6} {'lowD':>6} | {'sevA':>6} {'sevD':>6}")
for u, gu in r.groupby('user'):
    a = gu[gu.grp=='STILL-ACCEL']; d = gu[gu.grp=='DECEL']
    if len(a)<5 or len(d)<5: continue
    print(f"{u:4} {len(a):>4} {len(d):>4} | {a.peak.mean():6.0f} {d.peak.mean():6.0f} | "
          f"{a.low.mean():6.1%} {d.low.mean():6.1%} | {a.severe.mean():6.1%} {d.severe.mean():6.1%}")

print("\n=== POOLED (cluster-bootstrap by user, 95% CI) ===")
for col, lab in [('peak','peak BG (mg/dL)'), ('low','low<70 rate'), ('severe','severe<54 rate')]:
    a = r[r.grp=='STILL-ACCEL']; d = r[r.grp=='DECEL']
    la, ma, ha = cluster_boot(a, col); ld, md, hd = cluster_boot(d, col)
    # paired diff via bootstrap of (accel-decel) resampling users jointly
    users = r.user.unique()
    byA = {u: a[a.user==u][col].values for u in users}
    byD = {u: d[d.user==u][col].values for u in users}
    diffs=[]
    for _ in range(4000):
        bu = np.random.choice(users, len(users), replace=True)
        pa = np.concatenate([byA[u] for u in bu if len(byA[u])>0])
        pd_ = np.concatenate([byD[u] for u in bu if len(byD[u])>0])
        if len(pa)==0 or len(pd_)==0: continue
        diffs.append(pa.mean()-pd_.mean())
    dl, dm, dh = np.percentile(diffs,[2.5,50,97.5])
    fmt = (lambda x: f"{x:6.1f}") if col=='peak' else (lambda x: f"{x:6.1%}")
    verdict = "DISTINGUISHABLE" if (dl>0)==(dh>0) else "overlaps 0 (unproven)"
    print(f"{lab:18}  ACCEL {fmt(ma)} [{fmt(la)},{fmt(ha)}]   DECEL {fmt(md)} [{fmt(ld)},{fmt(hd)}]   "
          f"Δ(A−D) {fmt(dm)} [{fmt(dl)},{fmt(dh)}]  -> {verdict}")
