import numpy as np, csv, datetime
from collections import defaultdict
np.random.seed(7)
GRID=300  # 5 min in seconds

rows=defaultdict(dict)  # user -> bucket -> row (last wins)
raw=defaultdict(list)
with open('hr_bg_db.csv') as f:
    for r in csv.DictReader(f):
        u=r['user_id']; ep=int(r['ts_epoch']); b=ep//GRID
        def fl(x): 
            return float(x) if x not in ('','NULL',None) else np.nan
        rows[u][b]=dict(ep=ep,bg=fl(r['cgm_mgdl']),hr=fl(r['hr_avg']),
                        hrr=fl(r['hrr_pct']),st=fl(r['steps_15m']))

def build(u, bmin=None, bmax=None):
    d=rows[u]
    bs=[b for b in d if (bmin is None or b>=bmin) and (bmax is None or b<bmax)]
    if not bs: return None
    lo,hi=min(bs),max(bs)
    n=hi-lo+1
    bg=np.full(n,np.nan);hr=np.full(n,np.nan);st=np.full(n,np.nan);hrr=np.full(n,np.nan)
    hour=np.zeros(n,int)
    for b in bs:
        i=b-lo; r=d[b]
        bg[i]=r['bg'];hr[i]=r['hr'];st[i]=r['st'];hrr[i]=r['hrr']
        hour[i]=datetime.datetime.utcfromtimestamp(b*GRID).hour
    return dict(bg=bg,hr=hr,st=st,hrr=hrr,hour=hour,n=n)

def detrend(arr,hour):
    prof=np.full(24,np.nan)
    for h in range(24):
        m=(hour==h)&~np.isnan(arr)
        if m.sum()>5: prof[h]=np.mean(arr[m])
    return arr-prof[hour]

USERS=['tim','F','A','C','D','H']
data={}
for u in USERS:
    D=build(u)
    if D is None: continue
    D['bg_res']=detrend(D['bg'],D['hour'])
    D['hr_res']=detrend(D['hr'],D['hour'])
    data[u]=D

def corr(x,y,m):
    m=m&~np.isnan(x)&~np.isnan(y)
    if m.sum()<50: return (np.nan,int(m.sum()))
    return (np.corrcoef(x[m],y[m])[0,1],int(m.sum()))

print("=== PER-USER: paired coverage & correlations ===")
print(f"{'user':5s} {'paired':>7s} {'lvl_r':>7s} {'res_r':>7s} {'sed_r':>7s} {'act_r':>7s}")
pool_bgres=[];pool_hrres=[];pool_st=[]
for u,D in data.items():
    both=~np.isnan(D['bg'])&~np.isnan(D['hr'])
    lvl,_=corr(D['bg'],D['hr'],np.ones(D['n'],bool))
    res,_=corr(D['bg_res'],D['hr_res'],np.ones(D['n'],bool))
    sed=D['st']<20; act=D['st']>=20
    sr,_=corr(D['bg_res'],D['hr_res'],sed)
    ar,_=corr(D['bg_res'],D['hr_res'],act)
    print(f"{u:5s} {both.sum():7d} {lvl:+7.3f} {res:+7.3f} {sr:+7.3f} {ar:+7.3f}")
    pool_bgres.append(D['bg_res']);pool_hrres.append(D['hr_res']);pool_st.append(D['st'])
pb=np.concatenate(pool_bgres);ph=np.concatenate(pool_hrres);ps=np.concatenate(pool_st)
print(f"{'POOL':5s} {np.sum(~np.isnan(pb)&~np.isnan(ph)):7d} "
      f"{'':7s} {corr(pb,ph,np.ones(len(pb),bool))[0]:+7.3f} "
      f"{corr(pb,ph,ps<20)[0]:+7.3f} {corr(pb,ph,ps>=20)[0]:+7.3f}")

# tim era comparability
Dg=build('tim',bmax=int(datetime.datetime(2026,6,26,tzinfo=datetime.timezone.utc).timestamp())//GRID)
Dw=build('tim',bmin=int(datetime.datetime(2026,6,26,tzinfo=datetime.timezone.utc).timestamp())//GRID)
for nm,DD in [('tim-GARMIN',Dg),('tim-WEAR',Dw)]:
    DD['bg_res']=detrend(DD['bg'],DD['hour']);DD['hr_res']=detrend(DD['hr'],DD['hour'])
    both=~np.isnan(DD['bg'])&~np.isnan(DD['hr'])
    hv=DD['hr'][~np.isnan(DD['hr'])]
    print(f"  {nm}: paired={both.sum()} HRmean={np.mean(hv):.1f} sd={np.std(hv):.1f} "
          f"lvl_r={corr(DD['bg'],DD['hr'],np.ones(DD['n'],bool))[0]:+.3f} "
          f"res_r={corr(DD['bg_res'],DD['hr_res'],np.ones(DD['n'],bool))[0]:+.3f}")

# ===== Lead-lag CCF pooled =====
def deltas(arr):
    d=np.full(len(arr),np.nan); d[1:]=arr[1:]-arr[:-1]; return d
ML=18
def ccf_pooled(shiftmap=None):
    # accumulate pairs per lag across users
    acc={lag:([],[]) for lag in range(-ML,ML+1)}
    for u,D in data.items():
        dB=deltas(D['bg_res']); dH=deltas(D['hr_res'])
        if shiftmap is not None:
            dH=np.roll(dH,shiftmap[u])
        n=len(dB)
        for lag in range(-ML,ML+1):
            if lag>=0: a=dB[:n-lag]; b=dH[lag:]
            else: a=dB[-lag:]; b=dH[:n+lag]
            m=~np.isnan(a)&~np.isnan(b)
            acc[lag][0].append(a[m]); acc[lag][1].append(b[m])
    out=[]
    for lag in range(-ML,ML+1):
        a=np.concatenate(acc[lag][0]); b=np.concatenate(acc[lag][1])
        out.append((lag,np.corrcoef(a,b)[0,1],len(a)))
    return out
cc=ccf_pooled()
print("\n=== POOLED Lead-lag CCF: dHR vs dBG (pos lag = HR follows BG) ===")
for lag,r,n in cc:
    if lag%2==0: print(f"  {lag*5:+4d}min r={r:+.4f} n={n}")
peak=max([(l,r,n) for l,r,n in cc], key=lambda x:abs(x[1]))
print(f"Peak |r| lag {peak[0]*5:+d}min r={peak[1]:+.4f} n={peak[2]}")
# permutation
obs=max(abs(r) for l,r,n in cc)
cnt=0;NP=300
for _ in range(NP):
    sm={u:np.random.randint(100,data[u]['n']-100) for u in data}
    pp=ccf_pooled(sm)
    if max(abs(r) for l,r,n in pp)>=obs: cnt+=1
print(f"Circular-perm p(peak|r|={obs:.4f}) = {(cnt+1)/(NP+1):.4f}")

# ===== Event composites pooled =====
def composite(events, win=18):
    M=np.full((len(events),2*win+1),np.nan)
    for k,(D,o) in enumerate(events):
        for j,off in enumerate(range(-win,win+1)):
            idx=o+off
            if 0<=idx<D['n']: M[k,j]=D['hr_res'][idx]
    base=np.nanmean(M[:,0:13],axis=1)
    Mb=M-base[:,None]
    return np.nanmean(Mb,axis=0), np.nanstd(Mb,axis=0)/np.sqrt(np.sum(~np.isnan(Mb),axis=0)), np.sum(~np.isnan(Mb),axis=0)

def collect_rise():
    ons=[]
    for u,D in data.items():
        dB=deltas(D['bg'])
        for i in range(2,D['n']-2):
            if dB[i]>3 and dB[i+1]>3 and not dB[i-1]>3:
                seg=D['hr_res'][max(0,i-18):i+19]
                if np.mean(~np.isnan(seg))>=0.5: ons.append((D,i))
    return ons
def key(mean,sem):
    return " ".join(f"{k:+d}:{mean[k//5+18]:+.1f}±{sem[k//5+18]:.1f}" for k in [-45,-30,-15,-10,-5,0,10,20,30,45,60])

ons=collect_rise()
sed=[(D,i) for (D,i) in ons if not np.isnan(D['st'][i]) and D['st'][i]<20]
act=[(D,i) for (D,i) in ons if not np.isnan(D['st'][i]) and D['st'][i]>=20]
print(f"\n=== RISE ONSETS pooled: all={len(ons)} sed={len(sed)} act={len(act)} ===")
for nm,ev in [('ALL',ons),('SEDENTARY',sed),('ACTIVE',act)]:
    m,s,nc=composite(ev); print(f" [{nm} n={len(ev)}] {key(m,s)}")

# Highs
def collect_cross(thr,above=True):
    ev=[]
    for u,D in data.items():
        cond=(D['bg']>thr) if above else (D['bg']<thr)
        for i in range(2,D['n']-2):
            if cond[i] and not cond[i-1]:
                seg=D['hr_res'][max(0,i-18):i+19]
                if np.mean(~np.isnan(seg))>=0.4: ev.append((D,i))
    return ev
hi=collect_cross(180,True)
m,s,nc=composite(hi); print(f"\n[HIGH>180 n={len(hi)}] {key(m,s)}")

# Lows positive control (residual + raw)
def composite_raw(events,win=18):
    M=np.full((len(events),2*win+1),np.nan)
    for k,(D,o) in enumerate(events):
        for j,off in enumerate(range(-win,win+1)):
            idx=o+off
            if 0<=idx<D['n']: M[k,j]=D['hr'][idx]
    base=np.nanmean(M[:,6:12],axis=1)  # -60..-30
    Mb=M-base[:,None]
    return np.nanmean(Mb,axis=0), np.nanstd(Mb,axis=0)/np.sqrt(np.sum(~np.isnan(Mb),axis=0))
for thr in (70,75):
    lo=collect_cross(thr,False)
    m,s=composite_raw(lo)
    peakpost=np.nanmax(m[18:31])
    print(f"[LOW<{thr} n={len(lo)}] raw HR(bpm) 0..+60 peak=+{peakpost:.1f} | {' '.join(f'{k:+d}:{m[k//5+18]:+.1f}±{s[k//5+18]:.1f}' for k in [-30,-15,0,10,20,30,45])}")
