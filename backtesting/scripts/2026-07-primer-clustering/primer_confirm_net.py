"""
The developer's idea: keep every primer firing, but at CONFIRM net the ACCUMULATED primer IOB (from the
preceding fizzles + this session's seed), beyond ONE base allowance, off the commit-shot. So the
first primer's acceleration-bonus stays additive; subsequent fizzles are "pre-paid" against the
confirmed shot → the meal's net-extra insulin is bounded to ~one base no matter how many fizzles.

This preserves seeds (unlike cap/taper) and bounds post-confirm over-delivery. It does NOT touch
pure-fizzle clusters that never confirm (their intermediate dip is unaddressed) — flagged.

Test = MAGNITUDE (clean, no counterfactual): of real (CONFIRMED) meals, how often is a confirm
preceded by material accumulated primer IOB, and how much would the confirm-net rule net off the commit-shot?
primer IOB uses the replayed once-per-session fires; IOBfrac(t)=(1+t/tp)e^{-t/tp}, tp=75, DIA=300.
"""
import psycopg2, numpy as np, pandas as pd
con = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
  select user_id, ts_epoch, cgm_mgdl, boostv5_state, delta_acceleration, sleep_state
  from boost_decisions where boostv5_state is not null and cgm_mgdl is not null
""", con)
con.close()
TP=75.0; DIA=300.0; BASE=0.35
def iobfrac(tau): return (1.0+tau/TP)*np.exp(-tau/TP)

rows=[]
for uid,g in df.groupby('user_id'):
    g=g.sort_values('ts_epoch').reset_index(drop=True)
    t=g.ts_epoch.values.astype(float); bg=g.cgm_mgdl.values.astype(float)
    accl=g.delta_acceleration.values.astype(float); st=g.boostv5_state.values; sleep=g.sleep_state.values
    d=np.diff(bg,prepend=bg[0])
    rl=np.array([np.nanmin(bg[(t>t[i]-3600)&(t<=t[i])]) if (t>t[i]-3600).any() else bg[i] for i in range(len(g))])
    # primer fire times (once per session)
    fires=[]; in_s=False; primed=False; ft=None
    confirm_ts=[]
    prev_state='IDLE'
    for i in range(len(g)):
        idle=(st[i]=='IDLE') or (st[i] is None)
        if idle:
            in_s=False; primed=False; ft=None; prev_state='IDLE'; continue
        if not in_s: in_s=True; primed=False; ft=None
        if (not primed) and st[i]=='OBSERVING' and accl[i]>10 and d[i]>0 and rl[i]>=80 and sleep[i]!='SLEEPING':
            primed=True; fires.append(t[i])
        if st[i]=='CONFIRMED' and prev_state!='CONFIRMED':
            confirm_ts.append(t[i])
        prev_state=st[i]
    fa=np.array(fires)
    lo_ep=None
    for ct in confirm_ts:
        if len(fa):
            tau=(ct-fa)/60.0; m=(tau>0)&(tau<DIA)
            piob=np.sum(BASE*iobfrac(tau[m])) if m.any() else 0.0
            npr=int(m.sum())
        else: piob=0.0; npr=0
        netoff=max(0.0, piob-BASE)
        # post-confirm low (context): any BG<70 in +30..180 min
        w=(t>ct+30*60)&(t<=ct+180*60); low=int(np.nanmin(bg[w])<70) if w.any() else np.nan
        rows.append(dict(user=uid, piob=piob, npr=npr, netoff=netoff, low=low))
R=pd.DataFrame(rows)
n=len(R)
print(f"CONFIRMED meals: {n}\n")
print(f"preceded by >=1 primer within DIA:     {(R.npr>=1).mean():.0%}")
print(f"preceded by >=2 primers (fizzle+seed): {(R.npr>=2).mean():.0%}")
print(f"primer IOB at confirm  — median {R.piob.median():.2f}U, p90 {R.piob.quantile(.9):.2f}U, max {R.piob.max():.2f}U")
print(f"\nTim's net-off (max(0, primerIOB - one base)) off the commit-shot:")
print(f"  would net off >0     : {(R.netoff>0.01).mean():.0%} of confirms")
print(f"  would net off >0.1U  : {(R.netoff>0.1).mean():.0%}")
print(f"  would net off >0.3U  : {(R.netoff>0.3).mean():.0%}")
print(f"  median net-off (when >0): {R[R.netoff>0.01].netoff.median():.2f}U ; p90 {R[R.netoff>0.01].netoff.quantile(.9):.2f}U")
print(f"\n=== safety proxy: do confirms with MORE preceding primer IOB crash more? ===")
for lab,sub in [('primerIOB=0 (no preceding)',R[R.piob<0.05]),
                ('primerIOB 0-0.35',R[(R.piob>=0.05)&(R.piob<0.35)]),
                ('primerIOB 0.35-0.7',R[(R.piob>=0.35)&(R.piob<0.7)]),
                ('primerIOB >0.7',R[R.piob>=0.7])]:
    if len(sub)>20: print(f"  {lab:26} n={len(sub):5d}  post-meal low<70 {sub.low.mean():.1%}")
print(f"\nper-user net-off>0.1U share:")
for u,gu in R.groupby('user'):
    print(f"  {u:4} confirms {len(gu):4d}  netoff>0.1 {(gu.netoff>0.1).mean():5.0%}  median-when>0 {gu[gu.netoff>0.01].netoff.median() if (gu.netoff>0.01).any() else 0:.2f}U")
