import numpy as np
d=np.load('hr_bg_arrays.npz', allow_pickle=True)
bg=d['bg']; hrL=d['hrL']; hrA=d['hrA']; st=d['st']; hour=d['hour']
hrL_res=d['hrL_res']; hrA_res=d['hrA_res']; bg_res=d['bg_res']
N=len(bg)
raw_dBG=np.full(N,np.nan); raw_dBG[1:]=bg[1:]-bg[:-1]

def composite(onsets, arr, win=18, minfrac=0.5):
    # returns mean trajectory residual arr, ±win slots, relative to t=0
    M=np.full((len(onsets),2*win+1),np.nan)
    for k,o in enumerate(onsets):
        for j,off in enumerate(range(-win,win+1)):
            idx=o+off
            if 0<=idx<N: M[k,j]=arr[idx]
    # baseline-subtract each event by its pre-window mean (-90..-30 = slots 0..12)
    base=np.nanmean(M[:,0:13],axis=1)
    Mb=M-base[:,None]
    mean=np.nanmean(Mb,axis=0)
    sem=np.nanstd(Mb,axis=0)/np.sqrt(np.sum(~np.isnan(Mb),axis=0))
    ncov=np.sum(~np.isnan(Mb),axis=0)
    return mean,sem,ncov,Mb

# ---- Rise onsets: first of >=2 consecutive delta>3 mg/dL ----
onsets=[]
for i in range(2,N-2):
    if (raw_dBG[i]>3 and raw_dBG[i+1]>3 and not (raw_dBG[i-1]>3)):
        onsets.append(i)
# require HR coverage in window
def has_hr(o,win=18,frac=0.5):
    seg=hrL_res[max(0,o-win):o+win+1]
    return np.mean(~np.isnan(seg))>=frac
onsets=[o for o in onsets if has_hr(o)]
sed_on=[o for o in onsets if (not np.isnan(st[o]) and st[o]<20)]
act_on=[o for o in onsets if (not np.isnan(st[o]) and st[o]>=20)]
print(f"Rise onsets (>=2 consec dBG>3, w/HR cover): {len(onsets)} | sedentary {len(sed_on)} active {len(act_on)}")

def show(name,onset_list):
    if len(onset_list)<5: print(f"  [{name}] n={len(onset_list)} too few"); return
    mean,sem,ncov,_=composite(onset_list,hrL_res)
    # print at key offsets
    offs=list(range(-18,19))
    print(f"  [{name}] n={len(onset_list)} HR_res(latest) baseline-sub, bpm at min offset:")
    keys=[-60,-30,-15,-10,-5,0,5,10,15,30,45,60,90]
    s="   "
    for kk in keys:
        j=kk//5+18
        s+=f" {kk:+d}:{mean[j]:+.1f}±{sem[j]:.1f}"
    print(s)

show("ALL rise onsets",onsets)
show("SEDENTARY onsets",sed_on)
show("ACTIVE onsets",act_on)

# BG trajectory sanity around onset (all)
mean,sem,ncov,_=composite(onsets,bg)  # not residual, raw levels rel baseline
print("\n  BG(raw,baseline-sub) around ALL onsets:",
      " ".join(f"{k:+d}:{mean[k//5+18]:+.0f}" for k in [-30,-15,0,15,30,60,90]))

# ---- Highs >180 sustained onset ----
high_on=[]
above=bg>180
for i in range(2,N-2):
    if above[i] and not above[i-1] and np.all(above[i:i+3] if i+3<=N else [False]):
        high_on.append(i)
high_on=[o for o in high_on if has_hr(o)]
print(f"\nHigh(>180 sustained>=15min) onsets w/HR: {len(high_on)}")
show("HIGH onsets",high_on)

# ---- Lows <70 onset (positive control) ----
low_on=[]
below=bg<70
for i in range(2,N-2):
    if below[i] and not below[i-1]:
        low_on.append(i)
low_on=[o for o in low_on if has_hr(o,frac=0.4)]
print(f"\nLow(<70) onsets w/HR: {len(low_on)}")
show("LOW onsets (pos control)",low_on)
# also raw HR bpm change for lows
if len(low_on)>=3:
    mean,sem,ncov,_=composite(low_on,hrL)
    print("  LOW raw HR(bpm,baseline-sub):",
          " ".join(f"{k:+d}:{mean[k//5+18]:+.1f}±{sem[k//5+18]:.1f}" for k in [-30,-15,0,15,30,45,60]))
