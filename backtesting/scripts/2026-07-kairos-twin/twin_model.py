#!/usr/bin/env python3
"""
KAIROS Twin — a physiological per-person glucose model + Ensemble Kalman Filter, validated
out-of-sample as a FORECASTER against oref's own predictions. Personal — scratchpad only.

Physiology (Bergman-minimal glucose + 2-compartment SC insulin absorption + interstitial lag +
LATENT glucose appearance Ra that the filter infers from CGM — the only way to model a pure-UAM
user who announces no carbs). State x = [Isc1, Isc2, X, Ra, G, Gi]:
  Isc1,Isc2  subcutaneous insulin depots (U)              dIsc1 = -ka1*Isc1 (+u);  dIsc2 = ka1*Isc1 - ka2*Isc2
  X          insulin action (1/min)                        dX   = -p2*X + p2*SI*Isc2
  Ra         glucose rate of appearance (mg/dL/min, latent) dRa  = -kra*Ra  (+ process noise = meals)
  G          blood glucose (mg/dL)                          dG   = -SG*(G-Gb) - X*G + Ra
  Gi         interstitial / CGM glucose (mg/dL)             dGi  = (G-Gi)/taui
  measure: CGM = Gi + noise
Interpretable, physiological, cannot produce a non-physical trajectory. Parameters per-person.
"""
import numpy as np

d=np.load('twin_data_tim.npz'); INS=d['ins']; CGM=d['cgm']; EVENTUAL=d['eventual']; IOBPRED=d['iobpred']; N=len(CGM)
SUB=5  # 1-min substeps per 5-min grid step

# ---- physiological parameters (tim: priors + TDD/ISF anchoring) ----
P=dict(ka1=0.030, ka2=0.022, p2=0.028, SI=0.00055, SG=0.021, Gb=118.0, taui=12.0, kra=0.020)

def step(x, u, P, dt=1.0):
    """One 1-min forward step. x columns = ensemble members. u = insulin this minute (U)."""
    Isc1,Isc2,X,Ra,G,Gi = x
    Isc1 = Isc1 + dt*(-P['ka1']*Isc1) + u
    Isc2 = Isc2 + dt*(P['ka1']*Isc1 - P['ka2']*Isc2)
    X    = X + dt*(-P['p2']*X + P['p2']*P['SI']*Isc2)
    Ra   = Ra + dt*(-P['kra']*Ra)
    G    = G + dt*(-P['SG']*(G-P['Gb']) - X*np.maximum(G,1.0) + Ra)
    Gi   = Gi + dt*((G-Gi)/P['taui'])
    return np.array([Isc1,Isc2,np.maximum(X,0), Ra, np.maximum(G,10.0), np.maximum(Gi,10.0)])

def forward5(x, u5, P):
    """One 5-min grid step = 5 one-min substeps, insulin spread across the bin."""
    for _ in range(SUB): x = step(x, u5/SUB, P)
    return x

# ---- Ensemble Kalman Filter ----
M=150                                  # ensemble size
# process noise sd per state per 5-min step; Ra is LARGE so the filter can discover meals from CGM
Qsd = np.array([0.02,0.02,1e-4, 0.55, 2.0, 0.6])
Rsd = 6.0                               # CGM measurement noise (mg/dL)
rng=np.random.default_rng(1)
# ---- forecast calibration (2026-07-18, twin_calibrate.py) — fixes the 30-min under-dispersion ----
# Baseline was under-dispersed (30-min 90%-band cov 77%, tails 10/13). Three physical corrections,
# held-out-calibrated on tim: (INFLATE0) additive EnKF covariance inflation at h=0 for the structural
# short-horizon error the filter is over-confident about; (MEAL_P/MEAL_RA) unannounced-meal risk as
# Poisson positive-Ra impulses → right-skewed upper band; (+Rsd) the band predicts an OBSERVED CGM.
# Point forecast = ensemble MEDIAN so the meal skew fattens the upside without biasing the estimate.
# Result: 30-min cov 77→85%, 60-min 86→91%, RMSE unchanged. Mirrored in the Kotlin TwinEnkf.
INFLATE0 = 28.0                        # mg/dL sd added to G,Gi at forecast start
MEAL_P   = 0.03                        # per-member per-5-min meal-onset probability (forecast only)
MEAL_RA  = 5.0                         # Ra impulse size (mg/dL/min, half-normal scale)

def run_enkf(P, forecast_h=(6,12)):
    # init ensemble near a plausible fasting state
    g0 = np.nanmedian(CGM[:200]) if not np.isnan(np.nanmedian(CGM[:200])) else 120.0
    x = np.zeros((6,M))
    x[4]=g0+rng.normal(0,8,M); x[5]=g0+rng.normal(0,8,M); x[3]=rng.normal(0,2,M)
    est=np.full((N,6),np.nan)
    # forecasts: for each horizon, predicted Gi made AT time i for time i+h
    fc={h:np.full(N,np.nan) for h in forecast_h}
    fclo={h:np.full(N,np.nan) for h in forecast_h}; fchi={h:np.full(N,np.nan) for h in forecast_h}
    for i in range(N):
        # forecast from current posterior BEFORE assimilating i (roll fwd under KNOWN future insulin).
        # Symmetric process noise (model error) + right-skewed meal impulses (unpredictable future
        # meals — a pure-UAM twin must honestly not-know when a meal is coming) + covariance inflation.
        Qf=np.array([0.0,0.0,0.0, 0.95, 2.2, 0.0])
        for h in forecast_h:
            if i+h<N:
                xf=x.copy()
                xf[4]=xf[4]+rng.standard_normal(M)*INFLATE0            # covariance inflation at h=0
                xf[5]=xf[5]+rng.standard_normal(M)*INFLATE0
                for j in range(h):
                    xf=forward5(xf, INS[i+j], P) + Qf[:,None]*rng.standard_normal((6,M))
                    meal=(rng.random(M)<MEAL_P)                        # Poisson positive meal risk
                    xf[3]=xf[3]+meal*np.abs(rng.standard_normal(M))*MEAL_RA
                    xf[4]=np.maximum(xf[4],10.0)
                gi_obs=xf[5]+rng.normal(0,Rsd,M)                       # band predicts an OBSERVED CGM
                fc[h][i]=np.median(xf[5])                              # point = median (robust to skew)
                fclo[h][i]=np.percentile(gi_obs,5); fchi[h][i]=np.percentile(gi_obs,95)
        # predict to i (add process noise)
        x=forward5(x, INS[i], P) + (Qsd[:,None]*rng.standard_normal((6,M)))
        x[3]=x[3]  # Ra free; keep others physical
        x[4]=np.maximum(x[4],10); x[5]=np.maximum(x[5],10); x[2]=np.maximum(x[2],0)
        # update with CGM if present
        if not np.isnan(CGM[i]):
            y=CGM[i]; hx=x[5]                       # measurement = Gi
            hm=hx.mean(); xm=x.mean(1,keepdims=True)
            Pxy=((x-xm)*(hx-hm)).mean(1)
            Pyy=((hx-hm)**2).mean()+Rsd**2
            K=Pxy/Pyy
            x=x+K[:,None]*(y+rng.normal(0,Rsd,M)-hx)[None,:]
            x[4]=np.maximum(x[4],10); x[5]=np.maximum(x[5],10); x[2]=np.maximum(x[2],0)
        est[i]=x.mean(1)
    return est, fc, fclo, fchi

if __name__=='__main__':
    est,fc,fclo,fchi=run_enkf(P)
    # sanity: filtered Gi tracks CGM?
    m=~np.isnan(CGM)
    rmse_fit=np.sqrt(np.nanmean((est[m,5]-CGM[m])**2))
    print(f"filter fit: Gi vs CGM RMSE = {rmse_fit:.1f} mg/dL (should be ~Rsd={Rsd})")
    print(f"latent Ra: mean {np.nanmean(est[:,5]*0+est[:,3]):.2f}, p95 {np.nanpercentile(est[:,3],95):.2f} mg/dL/min (meal spikes)")
    np.savez('twin_fit_tim.npz', est=est, **{f'fc{h}':fc[h] for h in fc}, **{f'lo{h}':fclo[h] for h in fc}, **{f'hi{h}':fchi[h] for h in fc})
    print("saved twin_fit_tim.npz")
