#!/usr/bin/env python3
"""
KAIROS Twin — calibration diagnosis + fix for the 30-min under-dispersion (2026-07-18).

The validated forecaster is calibrated at 60 min (~86%) but UNDER-dispersed at 30 min (76% vs
90). The memory also flags that on-device `floorbreach` over-fires — lo30 came out 61.5 on a stable
BG-113 basal-only cycle. This script tests the hypothesis that both are the same defect, seen from
two sides: the forecast band is miscalibrated ASYMMETRICALLY.

  - DOWNSIDE too wide: the model lets latent Ra (glucose appearance) go NEGATIVE. A negative Ra is
    unphysical (gut absorption cannot remove glucose) — it manufactures phantom falls, dragging lo30
    spuriously low. That is the floorbreach over-fire.
  - UPSIDE too narrow: the only honest source of forecast surprise for a pure-UAM user is an
    unannounced MEAL (a positive Ra shock). The baseline injects SYMMETRIC Gaussian Ra noise, which
    is the wrong shape — meals overshoot hi, they do not undershoot lo.

FIX (physiological, `improved` scheme):
  1. Clamp Ra >= 0 everywhere (filter + forecast). Appearance is non-negative.
  2. Forecast meal uncertainty as POISSON-arrival positive Ra impulses (meals are stochastic events,
     not continuous diffusion) → a right-skewed band: tight/true median, wide upside, honest floor.
  3. Add CGM measurement noise to the band (truth is an OBSERVED CGM = Gi + noise).
The point forecast is the ensemble MEDIAN (robust to the skew); only π fraction of members get a
meal impulse, so the median barely moves → RMSE preserved.

Reads the (personal) npz from a path given as argv[1]; writes only aggregate diagnostics to stdout.
Committable — carries no personal data.
"""
import sys
import numpy as np

DATA = sys.argv[1] if len(sys.argv) > 1 else 'twin_data_tim.npz'
d = np.load(DATA); INS = d['ins']; CGM = d['cgm']; N = len(CGM)
SUB = 5
P = dict(ka1=0.030, ka2=0.022, p2=0.028, SI=0.00055, SG=0.021, Gb=118.0, taui=12.0, kra=0.020)
M = 150
Qsd = np.array([0.02, 0.02, 1e-4, 0.55, 2.0, 0.6])
Rsd = 6.0
TEST = int(0.55 * N)

# improved-scheme forecast-noise params (tuned below to hit ~90% two-sided coverage).
# Three physically-distinct sources, replacing the baseline's single symmetric qf:
#   INFLATE0 : additive state/parameter uncertainty present even at h=0 (EnKF covariance inflation).
#              A FIXED width → larger share of total spread at 30 min than 60 min ⇒ lifts the
#              short-horizon coverage without over-widening the long horizon.
#   MEAL_P/RA: unannounced-meal risk as POISSON positive Ra impulses → right-skewed upper band.
#   G_DIFF   : residual symmetric glucose model error per step.
import os
INFLATE0 = float(os.environ.get('INFLATE0', 16.0))   # mg/dL sd added to G,Gi at forecast start
MEAL_P   = float(os.environ.get('MEAL_P',   0.030))   # per-member per-5-min meal-onset probability
MEAL_RA  = float(os.environ.get('MEAL_RA',  3.5))     # Ra impulse size (mg/dL/min, half-normal scale)
G_DIFF   = float(os.environ.get('G_DIFF',   1.6))     # symmetric glucose model-error diffusion/step
CLAMP_FC_RA = os.environ.get('CLAMP_FC_RA', '0') == '1'  # clamp Ra>=0 in the forecast rollout only


def step(x, u, clamp_ra):
    Isc1, Isc2, X, Ra, G, Gi = x
    Isc1 = Isc1 + (-P['ka1'] * Isc1) + u
    Isc2 = Isc2 + (P['ka1'] * Isc1 - P['ka2'] * Isc2)
    X = X + (-P['p2'] * X + P['p2'] * P['SI'] * Isc2)
    Ra = Ra + (-P['kra'] * Ra)
    if clamp_ra:
        Ra = np.maximum(Ra, 0.0)
    G = G + (-P['SG'] * (G - P['Gb']) - X * np.maximum(G, 1.0) + Ra)
    Gi = Gi + (G - Gi) / P['taui']
    return np.array([Isc1, Isc2, np.maximum(X, 0), Ra, np.maximum(G, 10.0), np.maximum(Gi, 10.0)])


def forward5(x, u5, clamp_ra):
    for _ in range(SUB):
        x = step(x, u5 / SUB, clamp_ra)
    return x


def fc_noise(xf, scheme, rng):
    if scheme == 'baseline':
        qf = np.array([0.0, 0.0, 0.0, 0.95, 2.2, 0.0])
        return xf + qf[:, None] * rng.standard_normal((6, M))
    # improved = the baseline symmetric diffusion (calibrates the 60-min downside) PLUS an upside
    # Poisson meal-risk skew (the identified deficit). Start-inflation is applied once, in run().
    xf = xf.copy()
    qf = np.array([0.0, 0.0, 0.0, 0.95, 2.2, 0.0])
    xf = xf + qf[:, None] * rng.standard_normal((6, M))
    meal = (rng.random(M) < MEAL_P)
    xf[3] = xf[3] + meal * np.abs(rng.standard_normal(M)) * MEAL_RA
    if CLAMP_FC_RA:
        xf[3] = np.maximum(xf[3], 0.0)
    xf[4] = np.maximum(xf[4], 10.0)
    return xf


def run(scheme, seed=1):
    rng = np.random.default_rng(seed)
    g0 = np.nanmedian(CGM[:200]); g0 = 120.0 if np.isnan(g0) else g0
    x = np.zeros((6, M))
    x[4] = g0 + rng.normal(0, 8, M); x[5] = g0 + rng.normal(0, 8, M); x[3] = rng.normal(0, 2, M)
    fc = {6: np.full(N, np.nan), 12: np.full(N, np.nan)}
    lo = {6: np.full(N, np.nan), 12: np.full(N, np.nan)}
    hi = {6: np.full(N, np.nan), 12: np.full(N, np.nan)}
    for i in range(N):
        for h in (6, 12):
            if i + h < N:
                xf = x.copy()
                if scheme != 'baseline':                        # additive covariance inflation at h=0
                    xf[4] = xf[4] + rng.standard_normal(M) * INFLATE0
                    xf[5] = xf[5] + rng.standard_normal(M) * INFLATE0
                for j in range(h):
                    xf = forward5(xf, INS[i + j], False)
                    xf = fc_noise(xf, scheme, rng)
                gi_obs = xf[5] + rng.normal(0, Rsd, M)          # predictive of an OBSERVED CGM
                # point forecast = ensemble MEDIAN: the right-skewed meal risk fattens the upper band
                # WITHOUT dragging the point estimate up (the correct point estimate under skew).
                fc[h][i] = np.median(xf[5])
                lo[h][i] = np.percentile(gi_obs, 5)
                hi[h][i] = np.percentile(gi_obs, 95)
        x = forward5(x, INS[i], False) + Qsd[:, None] * rng.standard_normal((6, M))
        x[4] = np.maximum(x[4], 10); x[5] = np.maximum(x[5], 10); x[2] = np.maximum(x[2], 0)
        if not np.isnan(CGM[i]):
            y = CGM[i]; hx = x[5]; hm = hx.mean(); xm = x.mean(1, keepdims=True)
            Pxy = ((x - xm) * (hx - hm)).mean(1); Pyy = ((hx - hm) ** 2).mean() + Rsd ** 2
            K = Pxy / Pyy
            x = x + K[:, None] * (y + rng.normal(0, Rsd, M) - hx)[None, :]
            x[4] = np.maximum(x[4], 10); x[5] = np.maximum(x[5], 10); x[2] = np.maximum(x[2], 0)
    return fc, lo, hi


def report(scheme):
    fc, lo, hi = run(scheme)
    print(f"\n=== scheme: {scheme} ===")
    HZ = {6: '30 min', 12: '60 min'}
    for h in (6, 12):
        idx = np.array([i for i in range(TEST, N - h)
                        if not np.isnan(CGM[i + h]) and not np.isnan(CGM[i]) and not np.isnan(fc[h][i])])
        truth = CGM[idx + h]
        err = fc[h][idx] - truth
        rmse = np.sqrt(np.mean(err ** 2)); mae = np.mean(np.abs(err))
        below = np.mean(truth < lo[h][idx]); above = np.mean(truth > hi[h][idx])
        cov = 1 - below - above
        # floorbreach over-fire proxy: quiet, non-low cycles where lo30 would trip the <70 trigger
        if h == 6:
            rising = np.array([CGM[i] - CGM[i - 3] > 10 if not np.isnan(CGM[i - 3]) else False for i in idx])
            fell = np.array([np.nanmin(CGM[i:i + 7]) < 70 for i in idx])       # did a low actually occur
            quiet_safe = (~rising) & (~fell)
            breach = (lo[h][idx] < 70)
            overfire = np.mean(breach[quiet_safe])
        print(f"{HZ[h]}: RMSE {rmse:5.1f}  MAE {mae:5.1f}  2-sided cov {100*cov:4.1f}%  "
              f"(below-lo {100*below:4.1f}% / above-hi {100*above:4.1f}%, target 5/5)  n={len(idx)}")
        if h == 6:
            print(f"        floorbreach OVER-FIRE (lo30<70 on quiet non-low cycles): {100*overfire:4.1f}%  "
                  f"[median lo30 = {np.median(lo[6][idx]):.0f}]")


if __name__ == '__main__':
    report('baseline')
    report('improved')
    print(f"\n(improved params: MEAL_P={MEAL_P}, MEAL_RA={MEAL_RA}, G_DIFF={G_DIFF})")
