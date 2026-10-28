import json, numpy as np, datetime
from collections import Counter
np.random.seed(42)

ds=json.load(open('hr_bg_devicestatus.json'))
ent=json.load(open('hr_bg_entries.json'))

GRID=300000  # 5 min ms
def slot(ms): return int(ms//GRID)

# ---- Build 5-min grid ----
# CGM: median sgv per slot
cgm={}
for r in ent:
    if r['ms'] is None: continue
    cgm.setdefault(slot(r['ms']),[]).append(r['sgv'])
cgm={k:float(np.median(v)) for k,v in cgm.items()}

# devicestatus: take latest record per slot (they update ~every 5min)
dsl={}
for r in ds:
    if r['ms'] is None: continue
    s=slot(r['ms'])
    # keep most recent within slot
    if s not in dsl or r['ms']>dsl[s]['ms']:
        dsl[s]=r

slots=sorted(set(cgm)|set(dsl))
smin,smax=min(slots),max(slots)
allslots=list(range(smin,smax+1))
N=len(allslots)

# arrays
bg=np.full(N,np.nan); hrA=np.full(N,np.nan); hrL=np.full(N,np.nan)
hrc=np.zeros(N); st=np.full(N,np.nan); sleep=np.array([None]*N,dtype=object)
hour=np.zeros(N,dtype=int); tod_min=np.zeros(N)
utc_off_ms=2*3600*1000  # local = UTC+2 (utcOffset 120)
for i,s in enumerate(allslots):
    ms=s*GRID
    lt=datetime.datetime.utcfromtimestamp((ms+utc_off_ms)/1000)
    hour[i]=lt.hour; tod_min[i]=lt.hour*60+lt.minute
    if s in cgm: bg[i]=cgm[s]
    if s in dsl:
        r=dsl[s]
        c=r['hrCount15'] or 0
        hrc[i]=c
        # HR valid only if fresh readings and worn source
        worn = (r['hrSrc'] or '').startswith('worn')
        if c>0 and worn:
            if r['hrAvg15'] is not None: hrA[i]=r['hrAvg15']
            if r['hrLatest'] is not None: hrL[i]=r['hrLatest']
        if r['steps15'] is not None: st[i]=r['steps15']
        sleep[i]=r['sleep']

print(f"Grid: {N} 5-min slots spanning {(smax-smin)*5/60/24:.1f} days")
print(f"CGM present: {np.sum(~np.isnan(bg))} ({100*np.mean(~np.isnan(bg)):.0f}%)")
print(f"HR(avg,fresh+worn) present: {np.sum(~np.isnan(hrA))} ({100*np.mean(~np.isnan(hrA)):.0f}%)")
print(f"HR(latest) present: {np.sum(~np.isnan(hrL))} ({100*np.mean(~np.isnan(hrL)):.0f}%)")
both=(~np.isnan(bg))&(~np.isnan(hrA))
print(f"Paired BG+HR slots: {np.sum(both)} ({100*np.mean(both):.0f}%)")

# ---- Gap detection ----
valid_hr=~np.isnan(hrA)
runs=[]; i=0
while i<N:
    if not valid_hr[i]:
        j=i
        while j<N and not valid_hr[j]: j+=1
        runs.append((i,j,j-i))
        i=j
    else: i+=1
runs.sort(key=lambda x:-x[2])
print("\nLongest HR gaps (slots, ~min, start local):")
for a,b,l in runs[:6]:
    lt=datetime.datetime.utcfromtimestamp((allslots[a]*GRID+utc_off_ms)/1000)
    print(f"  {l*5} min gap starting {lt.strftime('%m-%d %H:%M')}")

# ---- Day/night HR distribution ----
isnight=(hour>=0)&(hour<6)
def dist(mask):
    v=hrA[mask & ~np.isnan(hrA)]
    return f"n={len(v)} mean={np.mean(v):.1f} sd={np.std(v):.1f} med={np.median(v):.0f} p10={np.percentile(v,10):.0f} p90={np.percentile(v,90):.0f}"
print("\nHR distribution:")
print("  night(00-06):", dist(isnight))
print("  day  (06-24):", dist(~isnight))
print("  sleep=SLEEPING:", dist(np.array([s=='SLEEPING' for s in sleep])))
print("  sleep=AWAKE:", dist(np.array([s=='AWAKE' for s in sleep])))

# ---- Circadian detrend: hour-of-day mean profiles ----
def detrend(arr):
    prof=np.full(24,np.nan)
    for h in range(24):
        m=(hour==h)&~np.isnan(arr)
        if m.sum()>0: prof[h]=np.mean(arr[m])
    res=arr-prof[hour]
    return res,prof
bg_res,bg_prof=detrend(bg)
hrA_res,hrA_prof=detrend(hrA)
hrL_res,hrL_prof=detrend(hrL)
print("\nHour-of-day BG profile (mg/dL):", " ".join(f"{x:.0f}" for x in bg_prof))
print("Hour-of-day HR profile (bpm):   ", " ".join(f"{x:.0f}" for x in hrA_prof))

# ---- Correlations ----
def corr(x,y,mask):
    m=mask&~np.isnan(x)&~np.isnan(y)
    if m.sum()<30: return (np.nan,m.sum())
    return (np.corrcoef(x[m],y[m])[0,1], m.sum())
sed = st<20   # sedentary: <20 steps/15min
act = st>=20
awake=np.array([s=='AWAKE' for s in sleep])
asleep=np.array([s in ('SLEEPING','PRE_SLEEP') for s in sleep])
allm=np.ones(N,bool)
print("\n=== LEVEL correlations BG vs HR(avg) ===")
for name,m in [("all",allm),("sedentary",sed),("active",act),("awake",awake),("asleep",asleep)]:
    r,n=corr(bg,hrA,m); print(f"  {name:10s} r={r:+.3f} n={n}")
print("=== RESIDUAL (circadian-detrended) correlations ===")
for name,m in [("all",allm),("sedentary",sed),("active",act),("awake",awake),("asleep",asleep)]:
    r,n=corr(bg_res,hrA_res,m); print(f"  {name:10s} r={r:+.3f} n={n}")

# ---- Lead-lag cross-correlation of deltas ----
# delta over 5-min, residualized. Use contiguous runs only (both valid at t and t-1)
def deltas(arr):
    d=np.full(N,np.nan)
    d[1:]=arr[1:]-arr[:-1]
    return d
dBG=deltas(bg_res); dHR=deltas(hrL_res)  # use latest HR for timing precision
# also avg version
dHRa=deltas(hrA_res)

def ccf(dx,dy,maxlag):
    # corr(dy at t+lag, dx at t): positive lag => dy follows dx
    out=[]
    for lag in range(-maxlag,maxlag+1):
        if lag>=0:
            a=dx[:N-lag]; b=dy[lag:]
        else:
            a=dx[-lag:]; b=dy[:N+lag]
        m=~np.isnan(a)&~np.isnan(b)
        if m.sum()<50: out.append((lag,np.nan,m.sum())); continue
        out.append((lag,np.corrcoef(a[m],b[m])[0,1],m.sum()))
    return out
ML=18  # 90 min
print("\n=== Lead-lag CCF: dHR(latest) vs dBG, lag in min (pos=HR follows BG) ===")
cc=ccf(dBG,dHR,ML)
for lag,r,n in cc:
    if lag%2==0: print(f"  lag {lag*5:+4d}min r={r:+.3f} n={n}")
# peak
valid=[(l,r) for l,r,n in cc if not np.isnan(r)]
peak=max(valid,key=lambda x:abs(x[1]))
print(f"Peak |r| at lag {peak[0]*5:+d} min, r={peak[1]:+.3f}")

# circular permutation significance for peak
def circ_perm_peak(dx,dy,maxlag,nperm=500):
    obs=ccf(dx,dy,maxlag)
    obs_peak=max(abs(r) for l,r,n in obs if not np.isnan(r))
    cnt=0
    for _ in range(nperm):
        shift=np.random.randint(50,N-50)
        dyp=np.roll(dy,shift)
        pp=ccf(dx,dyp,maxlag)
        pmax=max(abs(r) for l,r,n in pp if not np.isnan(r))
        if pmax>=obs_peak: cnt+=1
    return obs_peak,(cnt+1)/(nperm+1)
op,pval=circ_perm_peak(dBG,dHR,ML,nperm=300)
print(f"Circular-permutation p for peak |r|={op:.3f}: p={pval:.3f}")

np.savez('hr_bg_arrays.npz', bg=bg,hrA=hrA,hrL=hrL,st=st,hour=hour,
         bg_res=bg_res,hrA_res=hrA_res,hrL_res=hrL_res,
         sleep=np.array([str(s) for s in sleep]), allslots=np.array(allslots),
         dBG=dBG,dHR=dHR,dHRa=dHRa,hrc=hrc)
print("\nsaved arrays")
