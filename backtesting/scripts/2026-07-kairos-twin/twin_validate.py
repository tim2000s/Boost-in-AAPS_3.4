#!/usr/bin/env python3
"""KAIROS Twin — out-of-sample forecast validation vs oref + persistence. Personal — scratchpad."""
import numpy as np
d=np.load('twin_data_tim.npz'); CGM=d['cgm']; EVENTUAL=d['eventual']; IOBPRED=d['iobpred']; N=len(CGM)
f=np.load('twin_fit_tim.npz'); FC={6:f['fc6'],12:f['fc12']}; LO={6:f['lo6'],12:f['lo12']}; HI={6:f['hi6'],12:f['hi12']}
HZ={6:'30 min',12:'60 min'}
TEST=int(0.55*N)                       # evaluate on the held-out later window (after warmup)

def rmse(e): e=e[~np.isnan(e)]; return np.sqrt(np.mean(e**2))
def mae(e):  e=e[~np.isnan(e)]; return np.mean(np.abs(e))

print("KAIROS Twin — forecast accuracy vs oref & persistence (out-of-sample, causal;")
print(f"parameters are PRIOR-set, not fitted; evaluated on the last {100*(1-0.55):.0f}% = {N-TEST} bins)\n")
print(f"{'horizon':>8} {'method':>16} {'RMSE':>6} {'MAE':>6} {'n':>6}")
for h in (6,12):
    idx=[i for i in range(TEST,N-h) if not np.isnan(CGM[i+h]) and not np.isnan(CGM[i])]
    idx=np.array(idx)
    truth=CGM[idx+h]
    methods={
        'Twin':        FC[h][idx]-truth,
        'oref eventualBG': EVENTUAL[idx]-truth,
        'oref iobPredBG':  IOBPRED[idx]-truth,
        'persistence': CGM[idx]-truth,
    }
    for name,err in methods.items():
        print(f"{HZ[h]:>8} {name:>16} {rmse(err):6.1f} {mae(err):6.1f} {np.sum(~np.isnan(err)):6d}")
    # calibration of the Twin's 90% interval
    inside=(truth>=LO[h][idx])&(truth<=HI[h][idx]); cov=np.mean(inside[~np.isnan(LO[h][idx])])
    print(f"{'':>8} {'Twin 90% cov':>16} {'':>6} {'':>6}   -> {100*cov:.0f}% (target 90; calibration)")
    # split: quiet vs rising (unannounced-meal cycles nobody can forecast)
    rising=np.array([ (not np.isnan(CGM[i]) and not np.isnan(CGM[i-3]) and CGM[i]-CGM[i-3]>10) for i in idx])
    for lbl,mask in [('  quiet',~rising),('  rising',rising)]:
        if mask.sum()<20: continue
        tw=rmse((FC[h][idx]-truth)[mask]); orf=rmse((EVENTUAL[idx]-truth)[mask]); pe=rmse((CGM[idx]-truth)[mask])
        print(f"{HZ[h]:>8} {lbl+' RMSE':>16}  Twin {tw:5.1f} | oref {orf:5.1f} | persist {pe:5.1f}  (n={mask.sum()})")
    print()
print("GO signal = Twin RMSE <= oref out-of-sample AND ~calibrated. Rising cycles are unannounced")
print("meals no forecaster can predict; the Twin's edge should show on quiet cycles + in calibration.")
