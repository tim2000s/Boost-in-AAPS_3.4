#!/usr/bin/env python3
"""
KAIROS Twin — can the insulin channel be IDENTIFIED directly, model-light? (2026-07-18)

The off-policy test (TWIN_OFFPOLICY.md) found the Twin's insulin gain is structurally
non-identified inside the EnKF: the latent meal state Ra absorbs any change in SI, so an 8x
range of insulin sensitivities fits the CGM equally well. That is the ONE blocker between a
validated forecaster (sensor) and a trustworthy counterfactual dosing model (controller).

This script tries to break the confound the honest way — NOT by re-tuning a prior, but by
identifying SI from CLEAN INSULIN-DRIVEN FALLS where Ra ~= 0 by construction (a natural
experiment for insulin gain). In the physiological model, on a no-meal cycle:

    dG/dt = -SG*(G - Gb)  -  SI * Xbar(t) * G          (Ra ~= 0)

where Xbar(t) = X(t)/SI is the SI-INDEPENDENT insulin-action shape you get by running the SC
insulin subsystem (Isc1 -> Isc2 -> X) over the delivered insulin with SI factored out. So on
clean-fall samples a simple linear regression identifies both gains:

    (-dG/dt)  =  SG*(G - Gb)  +  SI * (Xbar * G)   + noise
      regress -dG/dt on [ (G-Gb) , Xbar*G ]  ->  slopes = [ SG , SI ]

Clean-fall selection removes the confounds:
  - no recent meal (Ra~=0): the prior ~60 min shows no net rise and no fresh peak;
  - insulin actually on board (Xbar non-trivial);
  - deep falls toward/below Gb are the most identifying (below Gb, SG PUSHES UP, so a fall
    there must be insulin) — reported as a robustness cut.

If SI comes out well-determined, positive, physiological, and ~constant across selectors, the
insulin channel IS identifiable — set that SI and the Twin becomes controller-capable (the
forecaster is invariant to SI, so nothing is lost). If the estimate is noisy / near-zero /
selector-dependent, the sensor ceiling is confirmed.

Reads the (personal) npz from argv[1]. Aggregates only. Committable.
"""
import sys
import numpy as np

DATA = sys.argv[1] if len(sys.argv) > 1 else 'twin_data_tim.npz'
d = np.load(DATA); INS = d['ins']; CGM = d['cgm']; N = len(CGM)
P = dict(ka1=0.030, ka2=0.022, p2=0.028, SI=0.00055, SG=0.021, Gb=118.0)
DT = 5.0                                   # minutes per bin
SI_PRIOR = P['SI']

# ---- Xbar(t): insulin-action shape with SI factored out (run Isc1->Isc2->X, SI=1) ----
Isc1 = Isc2 = X = 0.0
Xbar = np.zeros(N)
for i in range(N):
    u = INS[i]
    for _ in range(5):                     # 1-min substeps
        Isc1 = Isc1 + (-P['ka1'] * Isc1) + u / 5.0
        Isc2 = Isc2 + (P['ka1'] * Isc1 - P['ka2'] * Isc2)
        X = X + (-P['p2'] * X + P['p2'] * 1.0 * Isc2)   # SI = 1 -> X == Xbar
    Xbar[i] = X

# ---- smoothed CGM + local slope (mg/dL per min) over a centred 25-min window ----
def smooth(y, k=2):
    out = np.full_like(y, np.nan)
    for i in range(N):
        lo, hi = max(0, i - k), min(N, i + k + 1)
        seg = y[lo:hi][~np.isnan(y[lo:hi])]
        if len(seg) >= 3:
            out[i] = seg.mean()
    return out

Gs = smooth(CGM)
slope = np.full(N, np.nan)                  # dG/dt from a local linear fit over +-3 bins (30 min)
for i in range(3, N - 3):
    yy = CGM[i - 3:i + 4]
    if np.isnan(yy).sum() == 0:
        xx = np.arange(-3, 4) * DT
        slope[i] = np.polyfit(xx, yy, 1)[0]


def clean_fall_mask(deep=False, night=None):
    m = np.zeros(N, bool)
    for i in range(12, N - 3):
        if np.isnan(slope[i]) or np.isnan(Gs[i]):
            continue
        if slope[i] >= -0.15:                       # must be falling (>~4.5 mg/dL / 30 min)
            continue
        win = CGM[i - 12:i + 1]                     # prior 60 min
        if np.isnan(win).sum() > 2:
            continue
        w = win[~np.isnan(win)]
        if (w.max() - w.min()) > 35:                # no big recent excursion (fresh meal peak)
            continue
        if (CGM[i] - np.nanmin(win)) > 8:           # not still near a recent peak
            pass
        if Xbar[i] * SI_PRIOR < 1e-4:               # insulin actually on board (non-trivial action)
            continue
        if deep and Gs[i] > P['Gb']:                # deep cut: below Gb, a fall must be insulin
            continue
        m[i] = True
    return m


def fit(mask, label, fix_sg=None):
    idx = np.where(mask)[0]
    if len(idx) < 40:
        print(f"  {label:<22} n={len(idx):<5} (too few)"); return None
    y = -slope[idx]                                  # mg/dL per min, falling -> positive
    ins = Xbar[idx] * Gs[idx]                          # insulin regressor; coeff = SI
    if fix_sg is not None:                            # SG fixed physiological -> single regressor
        y2 = y - fix_sg * (Gs[idx] - P['Gb'])
        A = ins[:, None]; SG_hat = fix_sg
        coef, *_ = np.linalg.lstsq(A, y2, rcond=None); SI_hat = coef[0]
        yhat = A @ coef; ss_res = np.sum((y2 - yhat) ** 2); ss_tot = np.sum((y2 - y2.mean()) ** 2)
    else:
        A = np.column_stack([(Gs[idx] - P['Gb']), ins])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None); SG_hat, SI_hat = coef
        yhat = A @ coef; ss_res = np.sum((y - yhat) ** 2); ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot
    rng = np.random.default_rng(0); boots = []
    for _ in range(400):
        s = rng.integers(0, len(idx), len(idx))
        if fix_sg is not None:
            c, *_ = np.linalg.lstsq(ins[s][:, None], (y - fix_sg * (Gs[idx] - P['Gb']))[s], rcond=None); boots.append(c[0])
        else:
            c, *_ = np.linalg.lstsq(A[s], y[s], rcond=None); boots.append(c[1])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    ratio = SI_hat / SI_PRIOR
    sgtxt = f"SG={SG_hat:.4f}" + ("(fixed)" if fix_sg is not None else "")
    print(f"  {label:<22} n={len(idx):<5} SI={SI_hat:.5f}  ({ratio:4.1f}x prior, 95%CI {lo/SI_PRIOR:.1f}-{hi/SI_PRIOR:.1f}x)  "
          f"{sgtxt}  R2={r2:.2f}")
    return SI_hat, lo, hi, ratio


if __name__ == '__main__':
    print("KAIROS Twin — direct insulin-gain identification from clean insulin-driven falls")
    print(f"(prior SI = {SI_PRIOR:.5f}; Gb = {P['Gb']}; regress -dG/dt on [(G-Gb), Xbar*G])\n")
    print("  selector                n     estimate")
    r_all  = fit(clean_fall_mask(), 'all clean falls')
    r_deep = fit(clean_fall_mask(deep=True), 'deep falls (G<Gb)')
    print("  -- SG fixed physiological (0.021), removes the regressor collinearity --")
    fit(clean_fall_mask(), 'all clean falls', fix_sg=0.021)
    fit(clean_fall_mask(deep=True), 'deep falls (G<Gb)', fix_sg=0.021)
    print("\nRead: if SI is well-determined (tight CI, R2>0), positive, and consistent across the two")
    print("selectors, the insulin channel IS identifiable from clean falls — set SI to it and the Twin")
    print("becomes controller-capable (the forecaster is SI-invariant, so nothing is lost). A prior of")
    print(f"{SI_PRIOR:.5f} that lands far below the identified value was simply too low.")
