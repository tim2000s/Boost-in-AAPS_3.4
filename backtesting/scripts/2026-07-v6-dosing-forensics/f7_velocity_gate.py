"""Is front-loading a GOOD trade gated on VELOCITY/ACCELERATION at decision time (not peak, which is
too late)? V6 meals. For each velocity/accel bin, split by early front-load and compare plateau+crash."""
import numpy as np, psycopg2
from collections import defaultdict
conn=psycopg2.connect("dbname=oref host=127.0.0.1 port=5432");cur=conn.cursor()
USERS=['tim','F','B','A','C','H']
cur.execute("select user_id,ts_epoch,cgm_mgdl,iob_iob,boostv5_finaldose from boost_decisions where user_id=any(%s) and variant='boost-other' and reason_text ~ 'sleep=AWAKE' and reason_text !~ 'suppressed \\(SLEEPING\\)' and cgm_mgdl is not null order by 1,2",(USERS,))
by=defaultdict(list)
for u,e,g,iob,fd in cur.fetchall(): by[u].append((e,g,iob or 0,fd or 0))
for u in by: by[u]=np.array(by[u],float)
def at(arr,e,col,tol=400):
    ep=arr[:,0]; i=np.searchsorted(ep,e); c=[j for j in (i-1,i,i+1) if 0<=j<len(ep) and abs(ep[j]-e)<tol]
    return arr[min(c,key=lambda j:abs(ep[j]-e)),col] if c else np.nan
def dose_between(arr,e0,e1):
    ep=arr[:,0]; m=(ep>=e0)&(ep<e1); return arr[m,3].sum()
meals=[]
for u,arr in by.items():
    ep,g=arr[:,0],arr[:,1]; last=-1e9
    for i in range(9,len(ep)):
        if ep[i]-ep[i-1]>400: continue
        if g[i]>140 and g[i-1]<=140 and np.nanmin(g[max(0,i-6):i+1])<=130 and (ep[i]-last)>5400:
            e=ep[i]; last=e
            vel = at(arr,e,1)-at(arr,e-900,1)                    # rise rate mg/dL per 15min AT onset
            velprev = at(arr,e-900,1)-at(arr,e-1800,1)           # rate 15min earlier
            accel = vel-velprev                                   # +ve = accelerating into the rise
            bg0=at(arr,e,1); iob0=at(arr,e,2)
            early=dose_between(arr,e,e+1800)
            plat=np.nanmean([at(arr,e+m*60,1) for m in (120,150,180)])
            nadir=np.nanmin([at(arr,e+m*60,1) for m in range(30,151,5)])
            if any(np.isnan(x) for x in (vel,accel,bg0,iob0,plat,nadir)): continue
            meals.append(dict(u=u,vel=vel,accel=accel,bg0=bg0,iob0=iob0,early=early,plat=plat,crash=int(nadir<70)))
print(f"V6 meals with velocity/accel + outcome: {len(meals)}\n")

def report(meals, key, edges, labels):
    print(f"=== gated on {key} (measured AT onset) ===")
    for i,lab in enumerate(labels):
        lo=-1e9 if i==0 else edges[i-1]; hi=edges[i] if i<len(edges) else 1e9
        M=[m for m in meals if lo<=m[key]<hi]
        if len(M)<25: 
            print(f"  {lab:<18} n={len(M)} (thin)"); continue
        med=np.median([m['early'] for m in M])
        hiF=[m for m in M if m['early']>med]; loF=[m for m in M if m['early']<=med]
        s=lambda g,k: np.mean([m[k] for m in g])
        dpl=s(hiF,'plat')-s(loF,'plat'); dcr=100*(s(hiF,'crash')-s(loF,'crash'))
        verdict='GOOD trade' if (dpl< -3 and dcr<4) else ('BAD (crashes)' if dcr>=6 else 'weak')
        print(f"  {lab:<18} n={len(M):>3}  front-load {s(loF,'early'):.1f}->{s(hiF,'early'):.1f}U  "
              f"plateau {dpl:+5.0f}  crash {dcr:+5.0f}pp   [{verdict}]")
    print()

vmed=np.median([m['vel'] for m in meals])
report(meals, 'vel', [10,25,45], ['slow <10','med 10-25','fast 25-45','v.fast >45'])
report(meals, 'accel', [-5,5], ['decelerating','steady','accelerating'])
# combined: fast AND accelerating vs slow/decel
fast_acc=[m for m in meals if m['vel']>=25 and m['accel']>0]
slow_dec=[m for m in meals if m['vel']<15 or m['accel']<-5]
for lab,M in [('FAST & accelerating',fast_acc),('slow / decelerating',slow_dec)]:
    if len(M)<20: print(f"{lab}: n={len(M)} thin"); continue
    med=np.median([m['early'] for m in M]); hiF=[m for m in M if m['early']>med]; loF=[m for m in M if m['early']<=med]
    s=lambda g,k: np.mean([m[k] for m in g])
    print(f"{lab} (n={len(M)}): front-load {s(loF,'early'):.1f}->{s(hiF,'early'):.1f}U  plateau {s(hiF,'plat')-s(loF,'plat'):+.0f}  crash {100*(s(hiF,'crash')-s(loF,'crash')):+.0f}pp  (also mean bg0 {np.mean([m['bg0'] for m in M]):.0f} iob0 {np.mean([m['iob0'] for m in M]):.1f})")
conn.close()
