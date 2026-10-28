"""
How often does the primer FIZZLE-CLUSTER? Replays the live primer trigger over all V6-era
history (the live primer has only ~1 day). Primer logic (matches DetermineBasalBoostV5):
  fires on the FIRST OBSERVING cycle per meal-session where delta_accl>10, BG rising,
  recentLow(60m)>=80 (rescue-carb floor), not asleep. Once per session.
Session = maximal run of non-IDLE state (IDLE breaks it). Outcome = did the session reach
CONFIRMED (seed worked) or fizzle (never confirmed).

Clustering = primer-fires close in time (each fires once/session, so a cluster is several
short fizzle-sessions in a window, each priming → accumulating IOB). Report per user:
fires/day, fizzle%, % of fires within 90min of another, max fires per rolling 90min, and
whether a >=2-fire cluster precedes a BG dip (<80 within 60min of the last fire).
"""
import psycopg2, numpy as np, pandas as pd
np.random.seed(20260721)
con = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
  select user_id, ts_epoch, cgm_mgdl, boostv5_state, delta_acceleration, sleep_state
  from boost_decisions where boostv5_state is not null and cgm_mgdl is not null
""", con)
con.close()

PRIMER_CAP = 0.35   # approx per-fire primer U for cumulative estimates
fires_all = []
for uid, g in df.groupby('user_id'):
    g = g.sort_values('ts_epoch').reset_index(drop=True)
    t = g.ts_epoch.values.astype(float); bg = g.cgm_mgdl.values.astype(float)
    accl = g.delta_acceleration.values.astype(float); st = g.boostv5_state.values
    sleep = g.sleep_state.values
    d = np.diff(bg, prepend=bg[0])
    # recentLow60 (trailing 60-min min)
    rl = np.empty(len(g))
    for i in range(len(g)):
        w = (t > t[i]-60*60) & (t <= t[i]); rl[i] = np.nanmin(bg[w]) if w.any() else bg[i]
    # walk sessions
    in_sess = False; primed = False; sess_confirmed = False; sess_fire_t = None
    days = (t.max()-t.min())/86400.0 if len(t)>1 else 1
    for i in range(len(g)):
        idle = (st[i] == 'IDLE') or (st[i] is None)
        if idle:
            if in_sess and sess_fire_t is not None:
                fires_all.append(dict(user=uid, t=sess_fire_t, confirmed=sess_confirmed))
            in_sess = False; primed = False; sess_confirmed = False; sess_fire_t = None
            continue
        if not in_sess:
            in_sess = True; primed = False; sess_confirmed = False; sess_fire_t = None
        if st[i] in ('CONFIRMED','COMMITTED'): sess_confirmed = True
        if (not primed) and st[i]=='OBSERVING' and accl[i]>10 and d[i]>0 and rl[i]>=80 \
           and sleep[i] != 'SLEEPING':
            primed = True; sess_fire_t = t[i]
    if in_sess and sess_fire_t is not None:
        fires_all.append(dict(user=uid, t=sess_fire_t, confirmed=sess_confirmed))

F = pd.DataFrame(fires_all)
# per-user span for rates
span = df.groupby('user_id').ts_epoch.agg(lambda s:(s.max()-s.min())/86400.0)

print(f"replayed primer-fires: {len(F)}  ({F.confirmed.mean():.0%} seeded a CONFIRMED meal, "
      f"{1-F.confirmed.mean():.0%} FIZZLED)\n")
print(f"{'user':4} {'days':>5} {'fires':>6} {'/day':>5} {'fizzle%':>8} {'clustered%':>11} {'maxIn90m':>9} {'clust→dip<80':>13}")
rows=[]
for uid, fu in F.groupby('user'):
    ft = np.sort(fu.t.values); n=len(ft); dy=span.get(uid,1) or 1
    fiz = 1-fu.confirmed.mean()
    # clustering: for each fire, others within 90 min
    clustered=0; maxwin=1
    for i in range(n):
        w = np.sum((ft>ft[i]-90*60)&(ft<=ft[i]+90*60))
        if w>=2: clustered+=1
        maxwin=max(maxwin, np.sum((ft>=ft[i])&(ft<ft[i]+90*60)))
    # dip after a >=2-fizzle cluster: find windows with >=2 fizzle-fires, check BG<80 within 60min of last
    fz = np.sort(fu[~fu.confirmed].t.values)
    dips=0; clusters=0
    guser = df[df.user_id==uid].sort_values('ts_epoch'); gt=guser.ts_epoch.values.astype(float); gb=guser.cgm_mgdl.values.astype(float)
    i=0
    while i < len(fz):
        j=i
        while j+1<len(fz) and fz[j+1]-fz[i] <= 90*60: j+=1
        if j>i:  # >=2 fizzle-fires within 90min
            clusters+=1
            last=fz[j]; w=(gt>last)&(gt<=last+60*60)
            if w.any() and np.nanmin(gb[w])<80: dips+=1
        i=j+1
    rows.append((uid,dy,n,n/dy,fiz,clustered/n if n else 0,maxwin,dips,clusters))
    print(f"{uid:4} {dy:5.0f} {n:6d} {n/dy:5.1f} {fiz:8.0%} {clustered/n if n else 0:11.0%} {maxwin:9d} "
          f"{(str(dips)+'/'+str(clusters)) if clusters else '0/0':>13}")

R=pd.DataFrame(rows,columns=['u','days','n','perday','fiz','clust','maxwin','dips','clusters'])
print(f"\nPOOLED: {R.n.sum()} fires, {R.perday.mean():.1f}/day median-user, fizzle {1-F.confirmed.mean():.0%}, "
      f"clustered {R.clust.mean():.0%} of fires; {R.clusters.sum()} clusters(>=2 fizzle/90m), "
      f"{R.dips.sum()}/{R.clusters.sum()} ({(R.dips.sum()/max(1,R.clusters.sum())):.0%}) preceded BG<80")
print(f"est. primer U in a max-cluster window: {R.maxwin.max()} fires x {PRIMER_CAP}U = {R.maxwin.max()*PRIMER_CAP:.2f}U")
