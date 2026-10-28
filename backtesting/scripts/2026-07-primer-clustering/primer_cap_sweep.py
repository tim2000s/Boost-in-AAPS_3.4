"""
Optimal rolling-window primer cap. Replays primer-fires (with seed/fizzle labels) over all
V6-era history, then sweeps cap designs and measures the trade-off:
  FIZZLE-BLOCKED %  (objective — cut the churn/dips)   vs
  SEED-KEPT %       (constraint — don't starve real meals; seeds may come AFTER fizzles)

Designs:
  count-cap(W,K): allow a fire only if < K ALLOWED fires in the trailing W min.
  gap+reset(W):   suppress if an allowed fire was < W min ago AND no CONFIRMED since
                  (a confirmed meal resets the refractory — targets fizzle-flapping only).
The best design maximises fizzle-blocking at high seed-retention.
"""
import psycopg2, numpy as np, pandas as pd
con = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
  select user_id, ts_epoch, cgm_mgdl, boostv5_state, delta_acceleration, sleep_state
  from boost_decisions where boostv5_state is not null and cgm_mgdl is not null
""", con)
con.close()

# ---- extract primer-fires (t, confirmed) + per-session confirm-time, per user ----
fires = {}   # user -> list of (t, confirmed)
confirm_times = {}  # user -> sorted array of CONFIRMED cycle times (for gap+reset)
for uid, g in df.groupby('user_id'):
    g = g.sort_values('ts_epoch').reset_index(drop=True)
    t = g.ts_epoch.values.astype(float); bg = g.cgm_mgdl.values.astype(float)
    accl = g.delta_acceleration.values.astype(float); st = g.boostv5_state.values; sleep = g.sleep_state.values
    d = np.diff(bg, prepend=bg[0])
    rl = np.array([np.nanmin(bg[(t>t[i]-3600)&(t<=t[i])]) if (t>t[i]-3600).any() else bg[i] for i in range(len(g))])
    ff=[]; in_sess=False; primed=False; conf=False; ft=None
    for i in range(len(g)):
        idle = (st[i]=='IDLE') or (st[i] is None)
        if idle:
            if in_sess and ft is not None: ff.append((ft,conf))
            in_sess=False; primed=False; conf=False; ft=None; continue
        if not in_sess: in_sess=True; primed=False; conf=False; ft=None
        if st[i] in ('CONFIRMED','COMMITTED'): conf=True
        if (not primed) and st[i]=='OBSERVING' and accl[i]>10 and d[i]>0 and rl[i]>=80 and sleep[i]!='SLEEPING':
            primed=True; ft=t[i]
    if in_sess and ft is not None: ff.append((ft,conf))
    fires[uid]=sorted(ff)
    confirm_times[uid]=np.sort(t[np.isin(st,['CONFIRMED'])])

tot_seed = sum(c for u in fires for _,c in fires[u])
tot_fiz  = sum((not c) for u in fires for _,c in fires[u])

def eval_countcap(W,K):
    kept_seed=blk_fiz=0
    for u,ff in fires.items():
        allowed=[]
        for t,c in ff:
            n=sum(1 for at in allowed if at> t-W*60)
            if n<K:
                allowed.append(t)
                if c: kept_seed+=1
            else:
                if not c: blk_fiz+=1
    return kept_seed/tot_seed, blk_fiz/tot_fiz

def eval_gapreset(W):
    kept_seed=blk_fiz=0
    for u,ff in fires.items():
        ct=confirm_times[u]; last_allowed=-1e18
        for t,c in ff:
            # confirmed since last allowed?  (reset refractory)
            conf_since = np.any((ct>last_allowed)&(ct<t))
            if (t-last_allowed> W*60) or conf_since:
                last_allowed=t
                if c: kept_seed+=1
            else:
                if not c: blk_fiz+=1
    return kept_seed/tot_seed, blk_fiz/tot_fiz

print(f"total fires: seeds {tot_seed}, fizzles {tot_fiz}\n")
print("=== count-cap(W,K): allow < K in trailing W min ===")
print(f"{'W(min)':>7} {'K':>2} {'seed-kept':>10} {'fizzle-blocked':>15}")
for W in [30,45,60,90,120]:
    for K in [1,2,3]:
        sk,fb=eval_countcap(W,K)
        print(f"{W:7d} {K:2d} {sk:10.0%} {fb:15.0%}")
print("\n=== gap+reset(W): suppress if allowed fire < W min ago AND no CONFIRMED since ===")
print(f"{'W(min)':>7} {'seed-kept':>10} {'fizzle-blocked':>15}")
for W in [30,45,60,90,120]:
    sk,fb=eval_gapreset(W)
    print(f"{W:7d} {sk:10.0%} {fb:15.0%}")
