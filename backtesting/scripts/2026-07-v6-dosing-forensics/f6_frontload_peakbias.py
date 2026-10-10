"""Does MORE early front-load (t0-30 after meal onset) => LOWER recovery plateau (the developer's hypothesis),
controlling for peak height? Or does it just add crashes / get braked? V6 meals, 6 users."""
import numpy as np, psycopg2
from collections import defaultdict
conn=psycopg2.connect("dbname=oref host=127.0.0.1 port=5432");cur=conn.cursor()
USERS=['tim','F','B','A','C','H']
cur.execute("select user_id,ts_epoch,cgm_mgdl,iob_iob,boostv5_finaldose from boost_decisions where user_id=any(%s) and variant='boost-other' and reason_text ~ 'sleep=AWAKE' and reason_text !~ 'suppressed \\(SLEEPING\\)' and cgm_mgdl is not null order by 1,2",(USERS,))
rows=cur.fetchall()
by=defaultdict(list)
for u,e,g,iob,fd in rows: by[u].append((e,g,iob or 0,fd or 0))
for u in by: by[u]=np.array(by[u],float)
def at(arr,e,col,tol=400):
    ep=arr[:,0]; i=np.searchsorted(ep,e); c=[j for j in (i-1,i,i+1) if 0<=j<len(ep) and abs(ep[j]-e)<tol]
    return arr[min(c,key=lambda j:abs(ep[j]-e)),col] if c else np.nan
def dose_between(arr,e0,e1):
    ep=arr[:,0]; m=(ep>=e0)&(ep<e1); return arr[m,3].sum()
meals=[]
for u,arr in by.items():
    ep,g=arr[:,0],arr[:,1]; last=-1e9
    for i in range(6,len(ep)):
        if ep[i]-ep[i-1]>400: continue
        if g[i]>140 and g[i-1]<=140 and np.nanmin(g[max(0,i-6):i+1])<=130 and (ep[i]-last)>5400:
            e=ep[i]; last=e
            peak=np.nanmax([at(arr,e+m*60,1) for m in range(0,61,5)])
            early=dose_between(arr,e,e+1800)              # insulin t0-30 (the front-load userH amplifies)
            iob90=at(arr,e+5400,2)                          # IOB during descent (t+90)
            plat=np.nanmean([at(arr,e+m*60,1) for m in (120,150,180)])
            nadir=np.nanmin([at(arr,e+m*60,1) for m in range(30,151,5)])
            if np.isnan(peak) or np.isnan(plat) or np.isnan(nadir): continue
            meals.append(dict(u=u,peak=peak,early=early,iob90=iob90,plat=plat,nadir=nadir,crash=int(nadir<70)))
print(f"V6 meals: {len(meals)}\n")
# control for peak height; within each peak band split by early front-load (median)
for lo,hi,lab in [(140,175,'peak 140-175'),(175,200,'peak 175-200'),(200,400,'peak >200')]:
    M=[m for m in meals if lo<=m['peak']<hi]
    if len(M)<30: continue
    med=np.median([m['early'] for m in M])
    hiF=[m for m in M if m['early']>med]; loF=[m for m in M if m['early']<=med]
    def s(g,k): return np.mean([m[k] for m in g])
    print(f"{lab} (n={len(M)}, split at early-dose {med:.2f}U):")
    print(f"   LOW  front-load (n={len(loF)}): early {s(loF,'early'):.2f}U  IOB@90 {s(loF,'iob90'):.1f}  -> plateau {s(loF,'plat'):.0f}  crash {100*s(loF,'crash'):.0f}%")
    print(f"   HIGH front-load (n={len(hiF)}): early {s(hiF,'early'):.2f}U  IOB@90 {s(hiF,'iob90'):.1f}  -> plateau {s(hiF,'plat'):.0f}  crash {100*s(hiF,'crash'):.0f}%")
    print(f"   => more front-load moves plateau {s(hiF,'plat')-s(loF,'plat'):+.0f} mg/dL, crash {100*(s(hiF,'crash')-s(loF,'crash')):+.0f}pp\n")
# overall correlation, peak-residualised
peak=np.array([m['peak'] for m in meals]); early=np.array([m['early'] for m in meals]); plat=np.array([m['plat'] for m in meals])
A=np.column_stack([np.ones_like(peak),peak]); 
er=early-A@np.linalg.lstsq(A,early,rcond=None)[0]; pr=plat-A@np.linalg.lstsq(A,plat,rcond=None)[0]
print(f"peak-residualised corr(early front-load, recovery plateau) = {np.corrcoef(er,pr)[0,1]:+.2f}  (negative = more front-load -> lower plateau = the developer's hypothesis)")
conn.close()
