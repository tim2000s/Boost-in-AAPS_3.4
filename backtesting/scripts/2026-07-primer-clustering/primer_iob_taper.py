"""
IOB-taper test. Instead of BLOCKING primers in a cluster (which the sweep showed loses seeds
1:1), TAPER the dose: primer = min(base, CAP - recentPrimerIOB), so the seed always fires but
the cumulative primer IOB in a cluster is bounded at CAP. Tests whether that cuts primer-caused
dips while preserving the seed on real meals.

Method: replay primer fires (base 0.35U vs taper CAP). Estimate the primer's ADDITIVE BG effect
with a bounded insulin-perturbation replay (fizzle fires are additive; seed fires are netted off
the commit-shot -> net ~0). Insulin model: IOBfrac(t)=(1+t/tp)e^{-t/tp}, tp=75; acted=1-IOB.
Primer-caused dip = observed BG stayed >=80 but observed-depression < 80 (and <70 = low).
Identification caveat: first-order perturbation over bounded (<=DIA) windows; associational.
"""
import psycopg2, numpy as np, pandas as pd
con = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
  select user_id, ts_epoch, cgm_mgdl, boostv5_state, delta_acceleration, sleep_state,
         coalesce(variable_sens, dynamic_isf, sens_normal_target, 45.0) isf
  from boost_decisions where boostv5_state is not null and cgm_mgdl is not null
""", con)
con.close()

TP=75.0; DIA=300.0; BASE=0.35
def iobfrac(tau):  # fraction still on board
    return (1.0 + tau/TP)*np.exp(-tau/TP)
def acted(tau):
    return 1.0 - iobfrac(tau)

# extract fires (t, confirmed, isf) + full bg series per user
U = {}
for uid, g in df.groupby('user_id'):
    g=g.sort_values('ts_epoch').reset_index(drop=True)
    t=g.ts_epoch.values.astype(float); bg=g.cgm_mgdl.values.astype(float)
    accl=g.delta_acceleration.values.astype(float); st=g.boostv5_state.values
    sleep=g.sleep_state.values; isf=g.isf.values.astype(float)
    d=np.diff(bg,prepend=bg[0])
    rl=np.array([np.nanmin(bg[(t>t[i]-3600)&(t<=t[i])]) if (t>t[i]-3600).any() else bg[i] for i in range(len(g))])
    ff=[]; in_s=False; primed=False; conf=False; ft=None; fisf=None
    for i in range(len(g)):
        idle=(st[i]=='IDLE') or (st[i] is None)
        if idle:
            if in_s and ft is not None: ff.append([ft,conf,fisf])
            in_s=False; primed=False; conf=False; ft=None; continue
        if not in_s: in_s=True; primed=False; conf=False; ft=None
        if st[i] in ('CONFIRMED','COMMITTED'): conf=True
        if (not primed) and st[i]=='OBSERVING' and accl[i]>10 and d[i]>0 and rl[i]>=80 and sleep[i]!='SLEEPING':
            primed=True; ft=t[i]; fisf=isf[i] if isf[i]>0 else 45.0
    if in_s and ft is not None: ff.append([ft,conf,fisf])
    U[uid]=dict(t=t,bg=bg,fires=sorted(ff,key=lambda x:x[0]))

def assign(cap):  # returns list of (t, u, confirmed, isf) per user
    out={}
    for uid,dd in U.items():
        allowed=[]  # (t,u)
        res=[]
        for ft,conf,fisf in dd['fires']:
            if cap is None:
                u=BASE
            else:
                riob=sum(pu*iobfrac((ft-pt)/60.0) for pt,pu in allowed if 0<=(ft-pt)/60.0<DIA)
                u=min(BASE, max(0.0, cap-riob))
            if u>0.001: allowed.append((ft,u))
            res.append((ft,u,conf,fisf))
        out[uid]=res
    return out

def evaluate(cap):
    tot_u=fiz_u=0.0; seed_doses=[]; fiz_doses=[]
    dip_cyc=low_cyc=0
    doses=assign(cap)
    for uid,dd in U.items():
        t=dd['t']; bg=dd['bg']; fires=doses[uid]
        tot_u+=sum(u for _,u,_,_ in fires)
        for _,u,c,_ in fires:
            (seed_doses if c else fiz_doses).append(u)
            if not c: fiz_u+=u
        # depression from FIZZLE fires only (additive); seeds netted
        fz=[(ft,u,fisf) for ft,u,c,fisf in fires if (not c) and u>0]
        if not fz: continue
        fa=np.array([x[0] for x in fz]); fu=np.array([x[1] for x in fz]); fi=np.array([x[2] for x in fz])
        for i in range(len(t)):
            tau=(t[i]-fa)/60.0
            m=(tau>0)&(tau<DIA)
            if not m.any(): continue
            dep=np.sum(fu[m]*fi[m]*acted(tau[m]))
            if bg[i]>=80 and bg[i]-dep<80: dip_cyc+=1
            if bg[i]>=70 and bg[i]-dep<70: low_cyc+=1
    return dict(cap=cap, tot_u=tot_u, fiz_u=fiz_u, dip=dip_cyc, low=low_cyc,
                seed_dose=np.mean(seed_doses) if seed_doses else 0,
                fiz_dose=np.mean(fiz_doses) if fiz_doses else 0)

print(f"{'design':>10} {'primer U':>9} {'fizzle U':>9} {'dip<80 cyc':>11} {'low<70 cyc':>11} {'avg seed':>9} {'avg fizzle':>11}")
base=evaluate(None)
def row(r,label):
    print(f"{label:>10} {r['tot_u']:9.1f} {r['fiz_u']:9.1f} {r['dip']:11d} {r['low']:11d} {r['seed_dose']:9.3f} {r['fiz_dose']:11.3f}")
row(base,'base')
for cap in [1.0,0.7,0.5,0.35]:
    r=evaluate(cap)
    print(f"{('cap '+str(cap)):>10} {r['tot_u']:9.1f} {r['fiz_u']:9.1f} {r['dip']:11d} {r['low']:11d} {r['seed_dose']:9.3f} {r['fiz_dose']:11.3f}"
          + f"   (dip {(1-r['dip']/max(1,base['dip'])):+.0%}, U {(1-r['tot_u']/base['tot_u']):+.0%}, seed {(r['seed_dose']/base['seed_dose']-1):+.0%})")
