"""
Does V1's acceleration gate (delta_accl > 10, the G3-release threshold) detect an
unannounced meal EARLIER than V6's CONFIRMED state? Clean detection-timing test on
V6-era data (both the % acceleration and the confirm state coexist there).

delta_acceleration = V1's % form: 100*(delta - shortAvgDelta)/max(|shortAvgDelta|,2).
It is exported by every Boost generation, so it's in the DB for all cycles.

Acceleration-FIRE = delta_acceleration > 10 while state is pre-confirm (IDLE|OBSERVING) & rising.
  TP  = a CONFIRMED follows within 30 min  -> lead = t_confirm - t_fire (how much earlier)
  FP  = no CONFIRMED within 30 min          (fired on a non-meal / fizzle)
Recall = of CONFIRMED episodes, how many had an acceleration-fire in the 30 min before.

Precision, recall, median lead: per-user + pooled, cluster-bootstrap by user.
"""
import psycopg2, numpy as np, pandas as pd
np.random.seed(20260720)
con = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
  select user_id, ts_epoch, cgm_mgdl, boostv5_state, delta_acceleration
  from boost_decisions where boostv5_state is not null and delta_acceleration is not null
""", con)
con.close()

ACCL_THR = 10.0   # V1's G3-release / boost-tier threshold
HORIZON = 30*60   # a confirm must follow within 30 min to count the fire a true meal-lead
DEDUPE = 20*60
fires, confirms = [], []
for uid, g in df.groupby('user_id'):
    g = g.sort_values('ts_epoch').reset_index(drop=True)
    t = g['ts_epoch'].values.astype(float)
    accl = g['delta_acceleration'].values.astype(float)
    st = g['boostv5_state'].values
    bg = g['cgm_mgdl'].values.astype(float)
    conf_t = t[st == 'CONFIRMED']
    # dedupe confirmed episodes (>40 min apart = new meal)
    ep = []
    for ct in np.sort(conf_t):
        if not ep or ct - ep[-1] > 40*60: ep.append(ct)
    ep = np.array(ep)
    # acceleration fires: accl>thr while pre-confirm
    pre = np.isin(st, ['IDLE', 'OBSERVING'])
    fire_idx = np.where((accl > ACCL_THR) & pre)[0]
    last = -1e18
    for i in fire_idx:
        if t[i] - last < DEDUPE: continue
        last = t[i]
        nxt = ep[(ep > t[i]) & (ep <= t[i] + HORIZON)]
        tp = len(nxt) > 0
        fires.append(dict(user=uid, tp=int(tp), lead=(nxt.min()-t[i])/60.0 if tp else np.nan))
    # recall: of confirmed episodes, was there a fire in the 30 min before?
    for ct in ep:
        w = (t >= ct - HORIZON) & (t < ct) & pre & (accl > ACCL_THR)
        confirms.append(dict(user=uid, led=int(w.any())))
F = pd.DataFrame(fires); C = pd.DataFrame(confirms)

def cboot(d, col, agg=np.mean, nb=3000):
    us = d.user.unique(); by = {u: d[d.user==u][col].dropna().values for u in us}
    v = []
    for _ in range(nb):
        bu = np.random.choice(us, len(us), replace=True)
        pool = np.concatenate([by[u] for u in bu if len(by[u])])
        if len(pool): v.append(agg(pool))
    return np.percentile(v, [2.5, 50, 97.5])

print(f"acceleration-fires (delta_accl>10, pre-confirm): {len(F)}   confirmed episodes: {len(C)}\n")
print("=== PER-USER ===")
print(f"{'user':4} {'fires':>5} {'prec':>6} {'medLead':>8} {'recall':>7}")
for u in sorted(F.user.unique()):
    fu = F[F.user==u]; cu = C[C.user==u]
    print(f"{u:4} {len(fu):>5} {fu.tp.mean():>6.1%} {np.nanmedian(fu.lead):>7.1f}m {cu.led.mean():>7.1%}")
print("\n=== POOLED (cluster-bootstrap by user, 95% CI) ===")
pl, pm, ph = cboot(F, 'tp')
rl, rm, rh = cboot(C, 'led')
ll, lm, lh = cboot(F.dropna(subset=['lead']), 'lead', np.median)
print(f"precision (fire→confirm ≤30m)  {pm:.1%} [{pl:.1%}, {ph:.1%}]")
print(f"recall    (confirm led by fire) {rm:.1%} [{rl:.1%}, {rh:.1%}]")
print(f"median lead of fire over confirm {lm:.1f} min [{ll:.1f}, {lh:.1f}]")
