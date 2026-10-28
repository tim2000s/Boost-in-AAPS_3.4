import numpy as np, csv, datetime
from collections import defaultdict
GRID=300
rows=defaultdict(dict)
with open('hr_bg_db.csv') as f:
    for r in csv.DictReader(f):
        u=r['user_id']; b=int(r['ts_epoch'])//GRID
        def fl(x): return float(x) if x not in ('','NULL',None) else np.nan
        rows[u][b]=dict(bg=fl(r['cgm_mgdl']),hr=fl(r['hr_avg']),st=fl(r['steps_15m']),
                        hour=datetime.datetime.utcfromtimestamp(b*GRID).hour)
def build(u):
    d=rows[u]; lo,hi=min(d),max(d); n=hi-lo+1
    bg=np.full(n,np.nan);hr=np.full(n,np.nan);st=np.full(n,np.nan);hour=np.zeros(n,int)
    for b in d:
        i=b-lo;r=d[b];bg[i]=r['bg'];hr[i]=r['hr'];st[i]=r['st'];hour[i]=r['hour']
    def det(a):
        p=np.full(24,np.nan)
        for h in range(24):
            m=(hour==h)&~np.isnan(a)
            if m.sum()>5:p[h]=a[m].mean()
        return a-p[hour]
    return dict(n=n,bgr=det(bg),hrr=det(hr),st=st)
data={u:build(u) for u in ['tim','F','A','C','D','H']}
def d1(a): 
    x=np.full(len(a),np.nan);x[1:]=a[1:]-a[:-1];return x
def ccf_at(lag, stmask_fn):
    A=[];B=[]
    for u,D in data.items():
        dB=d1(D['bgr']);dH=d1(D['hrr']);n=D['n']
        stm=stmask_fn(D['st'])
        if lag>=0: a=dB[:n-lag];b=dH[lag:];mm=stm[lag:]
        else: a=dB[-lag:];b=dH[:n+lag];mm=stm[:n+lag]
        m=~np.isnan(a)&~np.isnan(b)&mm
        A.append(a[m]);B.append(b[m])
    A=np.concatenate(A);B=np.concatenate(B)
    return np.corrcoef(A,B)[0,1],len(A)
for lag in (-10,-5,0,5,10):
    allr=ccf_at(lag//5, lambda s:np.ones(len(s),bool))
    sed=ccf_at(lag//5, lambda s:s<20)
    act=ccf_at(lag//5, lambda s:s>=20)
    print(f"lag {lag:+3d}min  ALL r={allr[0]:+.4f}(n={allr[1]})  SED r={sed[0]:+.4f}(n={sed[1]})  ACT r={act[0]:+.4f}(n={act[1]})")
