#!/usr/bin/env python3
"""Does the carbohydrate-to-glucose mapping invert between people, and is the bolus doing it?

The carb-signature study explained its sub-chance out-of-sample result by saying the mapping from
carbohydrate to early glucose differs between people. On six participants that could be asserted
and not measured. Here it is measured directly: a slope of glucose rise on announced carbohydrate
is fitted per participant, and the distribution of those slopes is the quantity of interest.

The observed spread of slopes overstates the real heterogeneity, because every slope carries its
own estimation error. A DerSimonian-Laird random-effects decomposition separates the two and gives
tau, the standard deviation of the true slopes, from which the share of participants whose true
slope is negative follows. That is the number the inversion claim stands or falls on.

Deviation from the protocol, recorded with its reason: section 6 specifies a mixed model with a
random slope. statsmodels is not installable into the system Python here, and with hundreds of
meals per participant the per-participant fits are well determined, so the random-effects
decomposition below is used instead. It answers the same question and exposes the noise term,
which a single MixedLM fit would not.

The within-participant contrast by bolus stratum is the sharper test. A person is compared with
themselves: their slope on meals they bolused against their slope on meals they did not. If the
inversion is an artefact of dosing insulin in proportion to the food, it appears there and it is
not a statement about people differing from one another at all.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md
"""

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HORIZONS = (10, 15, 20, 30, 45, 60)
MIN_MEALS = 30
SEED = 20260825


def ols_slope(x, y):
    """Slope of y on x with its standard error. Returns (b, se, n)."""
    n = len(x)
    if n < 5:
        return np.nan, np.nan, n
    xm, ym = x.mean(), y.mean()
    sxx = float(((x - xm) ** 2).sum())
    if sxx <= 0:
        return np.nan, np.nan, n
    b = float(((x - xm) * (y - ym)).sum() / sxx)
    resid = y - (ym + b * (x - xm))
    if n <= 2:
        return b, np.nan, n
    s2 = float((resid ** 2).sum() / (n - 2))
    return b, float(np.sqrt(s2 / sxx)), n


def dersimonian_laird(b, se):
    """Random-effects pooling. Returns pooled mean, tau, I^2, and Q."""
    ok = np.isfinite(b) & np.isfinite(se) & (se > 0)
    b, se = b[ok], se[ok]
    k = len(b)
    if k < 3:
        return dict(k=k)
    w = 1.0 / se ** 2
    mu_fe = float((w * b).sum() / w.sum())
    Q = float((w * (b - mu_fe) ** 2).sum())
    c = float(w.sum() - (w ** 2).sum() / w.sum())
    tau2 = max(0.0, (Q - (k - 1)) / c) if c > 0 else 0.0
    wr = 1.0 / (se ** 2 + tau2)
    mu = float((wr * b).sum() / wr.sum())
    se_mu = float(np.sqrt(1.0 / wr.sum()))
    i2 = float(max(0.0, (Q - (k - 1)) / Q) * 100) if Q > 0 else 0.0
    tau = float(np.sqrt(tau2))
    # share of true slopes below zero, under the fitted normal
    from math import erf, sqrt
    share_neg = float(0.5 * (1 + erf((0 - mu) / (tau * sqrt(2))))) if tau > 0 else (1.0 if mu < 0 else 0.0)
    return dict(k=k, mu=mu, se_mu=se_mu, tau=tau, i2=i2, Q=Q,
                ci_lo=mu - 1.96 * se_mu, ci_hi=mu + 1.96 * se_mu,
                share_true_negative=share_neg,
                observed_share_negative=float((b < 0).mean()),
                share_sig_negative=float(((b + 1.96 * se) < 0).mean()),
                share_sig_positive=float(((b - 1.96 * se) > 0).mean()))


def per_subject_slopes(df, h, stratum=None):
    d = df if stratum in (None, "all") else df[df.bolus_stratum == stratum]
    col = f"h{h}_rise"
    d = d.dropna(subset=[col, "carbs"])
    out = []
    for sid, g in d.groupby("subject_id", sort=False):
        if len(g) < MIN_MEALS:
            continue
        b, se, n = ols_slope(g["carbs"].to_numpy(float), g[col].to_numpy(float))
        if np.isfinite(b):
            out.append((sid, b, se, n))
    if not out:
        return pd.DataFrame(columns=["subject_id", "b", "se", "n"])
    return pd.DataFrame(out, columns=["subject_id", "b", "se", "n"])


def within_subject_bolus_contrast(df, h):
    """Same person, bolused meals against unbolused. Paired, so people cannot cause it."""
    col = f"h{h}_rise"
    d = df.dropna(subset=[col, "carbs"])
    bolused = d[d.bolus_stratum.isin(["at_meal", "pre"])]
    unbolused = d[d.bolus_stratum.isin(["none", "late_gt15"])]
    rows = []
    for sid, gu in unbolused.groupby("subject_id", sort=False):
        gb = bolused[bolused.subject_id == sid]
        if len(gu) < 15 or len(gb) < 15:
            continue
        bu, seu, nu = ols_slope(gu["carbs"].to_numpy(float), gu[col].to_numpy(float))
        bb, seb, nb = ols_slope(gb["carbs"].to_numpy(float), gb[col].to_numpy(float))
        if np.isfinite(bu) and np.isfinite(bb):
            rows.append(dict(subject_id=sid, b_unbolused=bu, se_unbolused=seu, n_unbolused=nu,
                             b_bolused=bb, se_bolused=seb, n_bolused=nb, diff=bu - bb))
    if not rows:
        return None
    t = pd.DataFrame(rows)
    rng = np.random.default_rng(SEED)
    dif = t["diff"].to_numpy(float)
    boot = np.array([rng.choice(dif, len(dif), replace=True).mean() for _ in range(2000)])
    return dict(n_subjects=int(len(t)),
                mean_diff=float(dif.mean()), median_diff=float(np.median(dif)),
                ci_lo=float(np.percentile(boot, 2.5)), ci_hi=float(np.percentile(boot, 97.5)),
                share_unbolused_gt_bolused=float((dif > 0).mean()),
                mean_b_unbolused=float(t.b_unbolused.mean()),
                mean_b_bolused=float(t.b_bolused.mean()))


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--data", default=os.path.join(here, "out"))
    ap.add_argument("--study", default="Loop")
    ap.add_argument("--strata", default="all,at_meal,none,pre,late_gt15")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    df = pd.read_parquet(os.path.join(args.data, f"meals_{args.study}.parquet"))
    print(f"{len(df):,} meals, {df.subject_id.nunique()} subjects", flush=True)

    res = {"study": args.study, "min_meals_per_subject": MIN_MEALS, "pooled": [], "within": []}
    for st in args.strata.split(","):
        for h in HORIZONS:
            t = per_subject_slopes(df, h, st)
            if len(t) < 3:
                continue
            p = dersimonian_laird(t["b"].to_numpy(float), t["se"].to_numpy(float))
            p.update(horizon=h, stratum=st)
            res["pooled"].append(p)
            print(f"{st:>10s} h{h:>3d}  k={p['k']:>4d}  slope {p['mu']:+.4f} "
                  f"[{p['ci_lo']:+.4f}, {p['ci_hi']:+.4f}]  tau {p['tau']:.4f}  "
                  f"I2 {p['i2']:.0f}%  true-neg {p['share_true_negative']*100:.0f}%  "
                  f"sig-neg {p['share_sig_negative']*100:.0f}%", flush=True)

    print("\nwithin-participant, unbolused minus bolused slope", flush=True)
    for h in HORIZONS:
        w = within_subject_bolus_contrast(df, h)
        if not w:
            continue
        w["horizon"] = h
        res["within"].append(w)
        print(f"h{h:>3d}  n={w['n_subjects']:>4d}  diff {w['mean_diff']:+.4f} "
              f"[{w['ci_lo']:+.4f}, {w['ci_hi']:+.4f}]  "
              f"unbolused {w['mean_b_unbolused']:+.4f} vs bolused {w['mean_b_bolused']:+.4f}  "
              f"share+ {w['share_unbolused_gt_bolused']*100:.0f}%", flush=True)

    out = args.out or os.path.join(args.data, f"slopes_{args.study}.json")
    with open(out, "w") as fh:
        json.dump(res, fh, indent=1)
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
