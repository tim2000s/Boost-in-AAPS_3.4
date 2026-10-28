import numpy as np
from scipy import stats
d=np.load('hr_bg_arrays.npz', allow_pickle=True)
bg=d['bg']; hrL=d['hrL']; st=d['st']; hrL_res=d['hrL_res']
N=len(bg)
raw_dBG=np.full(N,np.nan); raw_dBG[1:]=bg[1:]-bg[:-1]

# Sedentary rise onsets: test pre-onset HR_res lift (-30..-5) vs event baseline (-90..-45)
onsets=[]
for i in range(2,N-2):
    if raw_dBG[i]>3 and raw_dBG[i+1]>3 and not raw_dBG[i-1]>3: onsets.append(i)
def cover(o,w=18,f=0.5): 
    seg=hrL_res[max(0,o-w):o+w+1]; return np.mean(~np.isnan(seg))>=f
sed=[o for o in onsets if cover(o) and not np.isnan(st[o]) and st[o]<20]
pre=[]; base=[]
for o in sed:
    b=np.nanmean(hrL_res[o-18:o-9])   # -90..-45
    p=np.nanmean(hrL_res[o-6:o])      # -30..-5
    if not np.isnan(b) and not np.isnan(p): pre.append(p); base.append(b)
pre=np.array(pre); base=np.array(base); diff=pre-base
t,pv=stats.ttest_1samp(diff,0)
print(f"SEDENTARY rise onsets n={len(diff)}: pre-onset(-30..-5) HR lift vs baseline = {np.mean(diff):+.2f} bpm (SEM {np.std(diff)/np.sqrt(len(diff)):.2f}), t={t:.2f} p={pv:.3f}")

# fraction of sedentary onsets with pre-lift > +3 bpm
print(f"  fraction of sedentary onsets with pre-lift > +3 bpm: {np.mean(diff>3):.0%}")

# Positive control: expand hypo threshold to <75 and <80
for thr in (70,75,80):
    lows=[]; below=bg<thr
    for i in range(2,N-2):
        if below[i] and not below[i-1]: lows.append(i)
    lows=[o for o in lows if np.mean(~np.isnan(hrL[max(0,o-6):o+13]))>=0.4]
    ch=[]
    for o in lows:
        b=np.nanmean(hrL[o-12:o-6])  # -60..-30 baseline
        pk=np.nanmax(hrL[o:o+13]) if np.sum(~np.isnan(hrL[o:o+13]))>0 else np.nan  # 0..+60 peak
        if not np.isnan(b) and not np.isnan(pk): ch.append(pk-b)
    ch=np.array(ch)
    if len(ch)>0:
        t,pv=stats.ttest_1samp(ch,0) if len(ch)>1 else (np.nan,np.nan)
        print(f"LOW<{thr}: n={len(ch)} peak HR rise (0..+60 vs -60..-30 base) = {np.mean(ch):+.1f} bpm, t={t:.2f} p={pv:.3f}")
