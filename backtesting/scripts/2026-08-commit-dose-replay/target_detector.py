#!/usr/bin/env python3
"""
Can the commits where a cut is cheap be identified at the commit?

Cutting a late commit costs about 1.0 mg/dL hours of added exposure and avoids 0.099 lows; cutting
a normal one costs 8.48 and avoids 0.119. The benefit is comparable and the cost differs by a
factor of eight, so a targeted reduction is 6.6 times more efficient than a uniform one at the same
multiplier. Whether that is reachable depends on identifying the cheap commits in advance.

An earlier attempt predicted the peak timing and failed for an instructive reason: the predictable
early peaks were the ones arriving at high glucose, which are the benign ones. This targets the
quantity that actually matters instead, which is the cost of cutting this particular commit, and
evaluates a policy rather than an area under the curve.

  1. Predict, from state strictly before the commit and with participants held out, the exposure
     cost of scaling this commit.
  2. Treat the cheapest predicted fraction and measure what that policy realises: lows avoided,
     exposure added, and the ratio.
  3. Compare against treating everything, treating at random, and treating the truly cheapest,
     which is the oracle and the ceiling.

A policy curve is the right output because the decision is how many commits to treat, not how well
a score correlates with anything.

Usage:  python3 target_detector.py [--mult 0.85] [--json out.json]
"""

import argparse
import bisect
import json
import os
import sys

import numpy as np
import psycopg2
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "2026-08-commit-peak-timing"))
import commit_dose_replay as R                              # noqa: E402
from peak_timing import cgm_of, low_onsets                  # noqa: E402

PEAK_EARLY_MIN = 10


def features(rows, k, cgm_ts, cgm_bg):
    """State available at the commit, from the sensor series and the decision row."""
    t = rows[k]["t"]
    a = bisect.bisect_right(cgm_ts, t + 1)
    if a < 9:
        return None
    hist = cgm_bg[a - 9:a]
    inc = np.diff(hist)
    r = rows[k]
    return dict(
        bg=r["bg"], dose=r["dose"], iob=r["iob"], isf=r["isf"],
        inc1=float(inc[-1]), inc2=float(inc[-2]), inc3=float(inc[-3]), inc4=float(inc[-4]),
        inc_mean=float(inc[-4:].mean()), inc_max=float(inc[-4:].max()),
        inc_slope=float(inc[-1] - inc[-4]),
        curv=float(np.diff(inc[-4:]).mean()),
        rise_40=float(hist[-1] - hist[0]),
        rise_20=float(hist[-1] - hist[-5]),
        bg_min=float(hist.min()), bg_range=float(hist.max() - hist.min()),
        decel=float(inc[-1] - inc[-2]),
        hour=float(int((t // 3600) % 24)),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mult", type=float, default=0.85)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    rows, cgm = R.fetch(conn), cgm_of(conn)

    F, cost, ben, late, U = [], [], [], [], []
    for u, rr in rows.items():
        if u not in cgm:
            continue
        ct, cb = cgm[u]
        ev = R.commits(rr, ct, cb)
        # index the commit rows so features come from the same decision series
        idx = {round(e["t"]): e for e in ev}
        for k in range(1, len(rr)):
            if rr[k]["state"] != "CONFIRMED" or rr[k - 1]["state"] == "CONFIRMED":
                continue
            e = idx.get(round(rr[k]["t"]))
            if e is None:
                continue
            f = features(rr, k, ct, cb)
            if f is None:
                continue
            p = R.price(e, args.mult, R.DEFAULT_PEAK_MIN, R.DEFAULT_DIA_MIN)
            F.append(f)
            cost.append(p["added_auc"] / 60.0)
            ben.append(p["obs_low"] - p["cf_low"])
            late.append(int(e["interval"] <= PEAK_EARLY_MIN))
            U.append(u)
    keys = sorted(F[0])
    X = np.array([[r[k] for k in keys] for r in F], float)
    cost = np.array(cost); ben = np.array(ben); late = np.array(late); U = np.array(U)
    n = len(cost)
    print(f"commits: {n} across {len(set(U))} participants, multiplier {args.mult}")
    print(f"  late commits {late.mean():.3f}, lows avoidable by cutting everything {ben.sum():.0f}")
    print(f"  exposure cost of cutting everything {cost.sum():.0f} mg/dL.h\n")
    res = {"n": int(n), "mult": args.mult}

    # out-of-sample predicted cost, participants held out
    pred = np.zeros(n)
    for tr, te in GroupKFold(n_splits=min(5, len(set(U)))).split(X, cost, groups=U):
        m = HistGradientBoostingRegressor(max_iter=300, max_depth=4, learning_rate=0.05,
                                          min_samples_leaf=30, random_state=0)
        m.fit(X[tr], cost[tr]); pred[te] = m.predict(X[te])
    print("=" * 86)
    print("1. IS THE COST OF CUTTING PREDICTABLE AT THE COMMIT")
    print("=" * 86)
    print(f"  correlation between predicted and realised cost: {np.corrcoef(pred, cost)[0,1]:+.3f}")
    print(f"  MAE {np.mean(np.abs(pred-cost)):.2f} against {np.mean(np.abs(cost-np.median(cost))):.2f} "
          "for predicting the median")
    res["cost_corr"] = float(np.corrcoef(pred, cost)[0, 1])

    print()
    print("=" * 86)
    print("2. THE POLICY CURVE: TREAT THE CHEAPEST PREDICTED FRACTION")
    print("=" * 86)
    print("  Realised outcomes, so a wrong prediction is charged at what it actually cost.\n")
    print(f"  {'treated':>8s} {'n':>6s} {'lows avoided':>13s} {'mg/dL.h':>9s} {'per low':>9s} "
          f"{'late share':>11s} {'vs uniform':>11s}")
    uni_eff = cost.sum() / ben.sum()
    res["uniform"] = dict(avoided=float(ben.sum()), cost=float(cost.sum()), per_low=float(uni_eff))
    res["curve"] = []
    order = np.argsort(pred)
    for frac in (0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 1.00):
        k = max(1, int(frac * n))
        sel = order[:k]
        b, c = ben[sel].sum(), cost[sel].sum()
        eff = c / b if b else float("nan")
        print(f"  {100*frac:7.0f}% {k:6d} {b:13.0f} {c:9.0f} {eff:9.1f} "
              f"{late[sel].mean():11.3f} {uni_eff/eff if b else float('nan'):10.2f}x")
        res["curve"].append(dict(frac=frac, n=int(k), avoided=float(b), cost=float(c),
                                 per_low=float(eff), late_share=float(late[sel].mean())))

    print()
    print("=" * 86)
    print("3. AGAINST THE ALTERNATIVES AT THE SAME TREATED FRACTION")
    print("=" * 86)
    print("  Oracle sorts on the realised cost and is the ceiling. Random is the base rate.\n")
    rng = np.random.default_rng(20260813)
    oracle_order = np.argsort(cost)
    print(f"  {'treated':>8s} {'model':>9s} {'oracle':>9s} {'random':>9s} {'late-only rule':>15s}")
    res["compare"] = []
    for frac in (0.05, 0.10, 0.20, 0.30):
        k = max(1, int(frac * n))
        def eff_of(sel):
            b, c = ben[sel].sum(), cost[sel].sum()
            return c / b if b else float("nan")
        m_ = eff_of(order[:k]); o_ = eff_of(oracle_order[:k])
        rs = [eff_of(rng.choice(n, k, replace=False)) for _ in range(200)]
        r_ = float(np.nanmedian(rs))
        lsel = np.flatnonzero(late)
        l_ = eff_of(lsel[:k]) if len(lsel) >= k else eff_of(lsel)
        print(f"  {100*frac:7.0f}% {m_:9.1f} {o_:9.1f} {r_:9.1f} {l_:15.1f}")
        res["compare"].append(dict(frac=frac, model=float(m_), oracle=float(o_),
                                   random=r_, late_rule=float(l_)))

    print()
    print("=" * 86)
    print("4. PRECISION FOR LATENESS AT THE OPERATING POINTS")
    print("=" * 86)
    print(f"\n  base rate of late commits {late.mean():.3f}\n")
    print(f"  {'treated':>8s} {'precision':>10s} {'lift':>6s}")
    res["precision"] = []
    for frac in (0.05, 0.10, 0.20, 0.30):
        k = max(1, int(frac * n))
        p = float(late[order[:k]].mean())
        print(f"  {100*frac:7.0f}% {p:10.3f} {p/late.mean():5.2f}x")
        res["precision"].append(dict(frac=frac, precision=p, lift=p / float(late.mean())))

    if args.json:
        json.dump(res, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
