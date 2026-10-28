#!/usr/bin/env python3
"""
KAIROS Twin — the OFF-POLICY calibration test (2026-07-18). THE make-or-break experiment for
KAIROS-as-a-controller.

The Twin is validated as a FORECASTER: it predicts BG under the insulin that was actually
delivered. An MPC controller would instead query it COUNTERFACTUALLY — "what BG if I dose a
sequence the real loop did NOT give?" — which pushes the model off the delivered-insulin manifold.
The identification wall does not vanish; it moves up one level. This script asks the one question
that decides whether KAIROS can be a controller or only a sensor:

    How far off the delivered-insulin policy can the Twin be trusted, and does its calibrated band
    widen honestly when it can't?

Two identifiable legs (both use ONLY real data + real outcomes):

  A. NATURAL EXPERIMENT. The delivered insulin already varies cycle-to-cycle for reasons only
     partly explained by state (SMBs fire or not; temp basals vary). Regress horizon insulin on
     state, take the residual = the part of dosing NOT explained by observed state ≈ exogenous
     policy variation. Bin test forecasts by the SIGNED residual and measure 90%-band coverage +
     RMSE in each bin. If coverage holds in the off-modal bins, the Twin's glucose response is
     trustworthy across the insulin range a controller would explore.
       - UNDER-dosed bins (less insulin than typical) = the direction idea-4 WITHDRAWAL explores.
       - OVER-dosed  bins (more insulin than typical) = the direction "dose-more" MPC explores.
     If it holds under-dosed but not over-dosed, that is exactly the asymmetry that says: ship the
     safe half (withdrawal) first, and distrust the dose-more counterfactual.

  B. PERTURBATION. At quiet test cycles, re-forecast under insulin scaled x{0,0.5,1,1.5,2}. Check
     (i) the point forecast moves PHYSIOLOGICALLY (more insulin -> lower BG, monotone, ~ISF sized),
     and (ii) whether the BAND WIDENS as |scale-1| grows — the "uncertainty as off-policy
     regulariser" property the chance-constrained MPC dream relies on to be self-limiting. If the
     band does NOT widen off-policy, MPC cannot lean on band-width to refuse far-off-policy doses.

Reads the (personal) npz from argv[1]. Prints only aggregates. Committable — no personal data.
Mirrors the calibrated forecast scheme in twin_model.py / TwinEnkf.kt.
"""
import sys
import numpy as np

import os
DATA = sys.argv[1] if len(sys.argv) > 1 else 'twin_data_tim.npz'
d = np.load(DATA); INS = d['ins']; CGM = d['cgm']; N = len(CGM)
SUB = 5
P = dict(ka1=0.030, ka2=0.022, p2=0.028, SI=0.00055, SG=0.021, Gb=118.0, taui=12.0, kra=0.020)
P['SI'] *= float(os.environ.get('SI_MULT', '1'))   # sensitivity probe: is weak insulin gain a fixable prior?
M = 150
Qsd = np.array([0.02, 0.02, 1e-4, 0.55, 2.0, 0.6])
Rsd = 6.0
INFLATE0, MEAL_P, MEAL_RA = 28.0, 0.03, 5.0        # calibrated scheme (twin_calibrate.py)
TEST = int(0.55 * N)
HZ = {6: '30 min', 12: '60 min'}


def forward5(x, u5):
    for _ in range(SUB):
        Isc1, Isc2, X, Ra, G, Gi = x
        Isc1 = Isc1 + (-P['ka1'] * Isc1) + u5 / SUB
        Isc2 = Isc2 + (P['ka1'] * Isc1 - P['ka2'] * Isc2)
        X = X + (-P['p2'] * X + P['p2'] * P['SI'] * Isc2)
        Ra = Ra + (-P['kra'] * Ra)
        G = G + (-P['SG'] * (G - P['Gb']) - X * np.maximum(G, 1.0) + Ra)
        Gi = Gi + (G - Gi) / P['taui']
        x = np.array([Isc1, Isc2, np.maximum(X, 0), Ra, np.maximum(G, 10.0), np.maximum(Gi, 10.0)])
    return x


def forecast(x, ins_seq, h, rng):
    """Calibrated forecast from ensemble x under a given per-step insulin sequence. Returns
    (median, p5, p95, band_width) of the OBSERVED-CGM predictive at horizon h."""
    xf = x.copy()
    xf[4] = xf[4] + rng.standard_normal(M) * INFLATE0
    xf[5] = xf[5] + rng.standard_normal(M) * INFLATE0
    for j in range(h):
        xf = forward5(xf, ins_seq[j])
        xf = xf + np.array([0., 0., 0., 0.95, 2.2, 0.])[:, None] * rng.standard_normal((6, M))
        meal = (rng.random(M) < MEAL_P)
        xf[3] = xf[3] + meal * np.abs(rng.standard_normal(M)) * MEAL_RA
        xf[4] = np.maximum(xf[4], 10.0)
    gi_obs = xf[5] + rng.normal(0, Rsd, M)
    p5, p95 = np.percentile(gi_obs, 5), np.percentile(gi_obs, 95)
    return np.median(xf[5]), p5, p95, p95 - p5


def run_filter_capture():
    """Run the EnKF; capture the posterior ensemble + actual-insulin forecast at every step."""
    rng = np.random.default_rng(1)
    g0 = np.nanmedian(CGM[:200]); g0 = 120.0 if np.isnan(g0) else g0
    x = np.zeros((6, M)); x[4] = g0 + rng.normal(0, 8, M); x[5] = g0 + rng.normal(0, 8, M); x[3] = rng.normal(0, 2, M)
    ens = [None] * N
    fc = {6: np.full(N, np.nan), 12: np.full(N, np.nan)}
    lo = {6: np.full(N, np.nan), 12: np.full(N, np.nan)}
    hi = {6: np.full(N, np.nan), 12: np.full(N, np.nan)}
    for i in range(N):
        if i >= TEST:
            ens[i] = x.copy()
            for h in (6, 12):
                if i + h < N:
                    m, p5, p95, _ = forecast(x, [INS[i + j] for j in range(h)], h, rng)
                    fc[h][i], lo[h][i], hi[h][i] = m, p5, p95
        x = forward5(x, INS[i]) + Qsd[:, None] * rng.standard_normal((6, M))
        x[4] = np.maximum(x[4], 10); x[5] = np.maximum(x[5], 10); x[2] = np.maximum(x[2], 0)
        if not np.isnan(CGM[i]):
            y = CGM[i]; hx = x[5]; hm = hx.mean(); xm = x.mean(1, keepdims=True)
            Pxy = ((x - xm) * (hx - hm)).mean(1); Pyy = ((hx - hm) ** 2).mean() + Rsd ** 2
            K = Pxy / Pyy
            x = x + K[:, None] * (y + rng.normal(0, Rsd, M) - hx)[None, :]
            x[4] = np.maximum(x[4], 10); x[5] = np.maximum(x[5], 10); x[2] = np.maximum(x[2], 0)
    return ens, fc, lo, hi


def leg_a(fc, lo, hi):
    print("=" * 78)
    print("LEG A — natural experiment: is the Twin calibrated when insulin deviates from policy?")
    print("=" * 78)
    for h in (6, 12):
        idx = np.array([i for i in range(TEST, N - h)
                        if not np.isnan(CGM[i + h]) and not np.isnan(CGM[i]) and not np.isnan(fc[h][i])
                        and not np.isnan(CGM[i - 3])])
        # state features and horizon insulin
        Uh = np.array([INS[i:i + h].sum() for i in idx])
        bg = CGM[idx]; trend = CGM[idx] - CGM[idx - 3]
        iobproxy = np.array([INS[max(0, i - 6):i].sum() for i in idx])
        Xd = np.column_stack([np.ones(len(idx)), bg, trend, iobproxy])
        beta, *_ = np.linalg.lstsq(Xd, Uh, rcond=None)
        resid = Uh - Xd @ beta                       # exogenous-ish dosing deviation (U over horizon)
        truth = CGM[idx + h]
        cov_all = np.mean((truth >= lo[h][idx]) & (truth <= hi[h][idx]))
        rising = trend > 10
        print(f"\n{HZ[h]}  (n={len(idx)}, overall cov {100*cov_all:.0f}%; dosing-deviation sd {resid.std():.2f}U)")
        # signed quintiles of the deviation
        q = np.quantile(resid, [0, .2, .4, .6, .8, 1.0])
        labels = ['under--', 'under-', 'modal', 'over-', 'over--']
        print(f"  {'bin':<8}{'dev U':>10}{'n':>6}{'cov%':>7}{'below%':>8}{'above%':>8}{'RMSE':>7}   (quiet-only cov%)")
        for b in range(5):
            m = (resid >= q[b]) & (resid <= q[b + 1] if b == 4 else resid < q[b + 1])
            if m.sum() < 20:
                continue
            t = truth[m]; c = np.mean((t >= lo[h][idx][m]) & (t <= hi[h][idx][m]))
            below = np.mean(t < lo[h][idx][m]); above = np.mean(t > hi[h][idx][m])
            rm = np.sqrt(np.mean((fc[h][idx][m] - t) ** 2))
            mq = m & ~rising
            cq = np.mean((truth[mq] >= lo[h][idx][mq]) & (truth[mq] <= hi[h][idx][mq])) if mq.sum() >= 20 else np.nan
            print(f"  {labels[b]:<8}{resid[m].mean():>10.2f}{m.sum():>6}{100*c:>7.0f}{100*below:>8.0f}"
                  f"{100*above:>8.0f}{rm:>7.1f}      {100*cq:>5.0f}" if not np.isnan(cq)
                  else f"  {labels[b]:<8}{resid[m].mean():>10.2f}{m.sum():>6}{100*c:>7.0f}{100*below:>8.0f}{100*above:>8.0f}{rm:>7.1f}        n/a")


def leg_b(ens):
    print("\n" + "=" * 78)
    print("LEG B — perturbation: does the forecast move physiologically & the band widen off-policy?")
    print("=" * 78)
    # A controller's lever is a BOLUS NOW, which acts over 60-90 min — not scaled basal over 30 min.
    # Add ΔU as a bolus at step 0 (on top of actual delivery) and forecast where it acts. Withdrawal
    # is modelled by zeroing future basal over the horizon (the zero-temp a real loop would command).
    rng = np.random.default_rng(7)
    HMAX = 18                                         # need 90-min sequences
    cand = [i for i in range(TEST, N - HMAX)
            if ens[i] is not None and not np.isnan(CGM[i]) and not np.isnan(CGM[i - 3])
            and CGM[i] - CGM[i - 3] <= 10 and 110 <= CGM[i] <= 200]  # mid/high, where you'd dose more
    rng.shuffle(cand); cand = cand[:400]
    base_ins = {i: [INS[i + j] for j in range(HMAX)] for i in cand}
    for h in (12, 18):
        print(f"\n  --- {HZ.get(h, str(h*5)+' min')} horizon ---  (n={len(cand)} quiet mid/high test cycles)")
        # dose-more: add a bolus at t=0
        print(f"  DOSE-MORE (bolus at t=0):")
        print(f"  {'ΔU':>6}{'mean pt':>10}{'Δ pt':>8}{'Δpt/U':>8}{'band w':>9}{'w ratio':>9}")
        rows = {}
        for du in (0.0, 1.0, 2.0, 3.0):
            pt = []; w = []
            for i in cand:
                seq = list(base_ins[i]); seq[0] = seq[0] + du
                m, _, _, ww = forecast(ens[i], seq, h, np.random.default_rng(2000 + i))
                pt.append(m); w.append(ww)
            rows[du] = (np.mean(pt), np.mean(w))
        base_pt, base_w = rows[0.0]
        for du in (0.0, 1.0, 2.0, 3.0):
            mp, mw = rows[du]
            perU = (mp - base_pt) / du if du > 0 else 0.0
            print(f"  {du:>6.1f}{mp:>10.1f}{mp-base_pt:>+8.1f}{perU:>+8.1f}{mw:>9.1f}{mw/base_w:>9.2f}")
        # withdrawal: zero future basal (the zero-temp lever)
        pt0 = []; w0 = []
        for i in cand:
            seq = [0.0] * HMAX                            # zero-temp: no basal over the horizon
            m, _, _, ww = forecast(ens[i], seq, h, np.random.default_rng(3000 + i))
            pt0.append(m); w0.append(ww)
        print(f"  WITHDRAWAL (zero-temp): mean pt {np.mean(pt0):>6.1f} ({np.mean(pt0)-base_pt:+.1f} vs actual), "
              f"band w {np.mean(w0):.1f} (ratio {np.mean(w0)/base_w:.2f})")
    print("\n  Physiological check: Δpt/U should be NEGATIVE and ~ a fraction of ISF (more insulin ->")
    print("  lower BG), growing with horizon as the bolus acts. Self-limiting check: band 'w ratio'")
    print("  > 1 as ΔU grows means the Twin widens its uncertainty off-policy (MPC can auto-refuse on")
    print("  band width); ~1 means the chance-constraint must lean on the MEAN crossing the floor.")


if __name__ == '__main__':
    print("Running EnKF with ensemble capture (calibrated scheme)...")
    ens, fc, lo, hi = run_filter_capture()
    leg_a(fc, lo, hi)
    leg_b(ens)
