#!/usr/bin/env python3
"""
A gentle reduction everywhere plus a deeper one where a cut is predicted to be cheap.

Two policies have been priced separately. A uniform reduction reaches most of the avoidable lows
and costs 66.5 mg/dL hours of added exposure per low prevented. A targeted reduction on the
commits where cutting is predicted to be cheap costs 31.8 per low and reaches far fewer. They are
not alternatives: the targeted cut is nearly free, so it can sit on top of a uniform one.

The comparison that decides anything is at matched benefit. To prevent a given number of lows,
which policy costs the least exposure. A policy that is more efficient per low but cannot reach
the required number is not cheaper, it is a different product.

Targeting uses the out-of-sample predicted cost from `target_detector.py`, refitted here with
participants held out, so nothing is scored on a model that saw the participant.

The same one-armed bound applies throughout: the carbohydrate side is held at what was observed
and only the insulin side recomputed, so lows avoided is a ceiling and the exposure cost is not.

Usage:  python3 combined_policy.py [--json out.json]
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
import target_detector as T                                 # noqa: E402
from peak_timing import cgm_of, low_onsets                  # noqa: E402


def assemble(conn):
    rows, cgm = R.fetch(conn), cgm_of(conn)
    F, EV, U = [], [], []
    for u, rr in rows.items():
        if u not in cgm:
            continue
        ct, cb = cgm[u]
        idx = {round(e["t"]): e for e in R.commits(rr, ct, cb)}
        for k in range(1, len(rr)):
            if rr[k]["state"] != "CONFIRMED" or rr[k - 1]["state"] == "CONFIRMED":
                continue
            e = idx.get(round(rr[k]["t"]))
            if e is None:
                continue
            f = T.features(rr, k, ct, cb)
            if f is None:
                continue
            F.append(f); EV.append(e); U.append(u)
    return F, EV, np.array(U)


def policy(EV, uniform_mult, target_mult, treated):
    """Scale everything by uniform_mult, and the selected commits by target_mult instead."""
    avoided = cost = 0.0
    for i, e in enumerate(EV):
        m = target_mult if treated[i] else uniform_mult
        if m >= 1.0:
            continue
        p = R.price(e, m, R.DEFAULT_PEAK_MIN, R.DEFAULT_DIA_MIN)
        avoided += p["obs_low"] - p["cf_low"]
        cost += p["added_auc"] / 60.0
    return avoided, cost


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--json", default=None)
    args = ap.parse_args()
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    F, EV, U = assemble(conn)
    keys = sorted(F[0])
    X = np.array([[r[k] for k in keys] for r in F], float)
    n = len(EV)

    # predicted cost of a cut, out of sample, participants held out
    base = np.array([R.price(e, 0.85, R.DEFAULT_PEAK_MIN, R.DEFAULT_DIA_MIN)["added_auc"] / 60.0
                     for e in EV])
    pred = np.zeros(n)
    for tr, te in GroupKFold(n_splits=min(5, len(set(U)))).split(X, base, groups=U):
        m = HistGradientBoostingRegressor(max_iter=300, max_depth=4, learning_rate=0.05,
                                          min_samples_leaf=30, random_state=0)
        m.fit(X[tr], base[tr]); pred[te] = m.predict(X[te])
    order = np.argsort(pred)
    print(f"commits {n}, participants {len(set(U))}\n")
    res = {"n": int(n)}

    print("=" * 92)
    print("1. PURE UNIFORM, AS THE REFERENCE FRONTIER")
    print("=" * 92)
    print(f"\n  {'multiplier':>11s} {'lows avoided':>13s} {'mg/dL.h':>10s} {'per low':>9s}")
    none = np.zeros(n, bool)
    res["uniform"] = []
    for m in (0.95, 0.90, 0.85, 0.80, 0.70, 0.60, 0.50):
        a, c = policy(EV, m, m, none)
        print(f"  {m:11.2f} {a:13.0f} {c:10.0f} {c/max(a,1e-9):9.1f}")
        res["uniform"].append(dict(mult=m, avoided=a, cost=c))

    print()
    print("=" * 92)
    print("2. COMBINED: A GENTLE CUT EVERYWHERE, A DEEPER ONE WHERE IT IS PREDICTED CHEAP")
    print("=" * 92)
    print("  The comparison column is the pure uniform policy that prevents the same number of")
    print("  lows, interpolated on the frontier above. Lower cost at equal benefit is a real gain.\n")
    uni = sorted([(d["avoided"], d["cost"]) for d in res["uniform"]])
    ua = np.array([x[0] for x in uni]); uc = np.array([x[1] for x in uni])

    def uniform_cost_for(a):
        if a <= ua[0]:
            return uc[0] * a / max(ua[0], 1e-9)
        if a >= ua[-1]:
            return float(np.interp(a, ua, uc))
        return float(np.interp(a, ua, uc))

    print(f"  {'uniform':>8s} {'target':>7s} {'treated':>8s} {'avoided':>8s} {'mg/dL.h':>9s} "
          f"{'per low':>8s} {'uniform at same benefit':>24s} {'saving':>8s}")
    res["combined"] = []
    for um in (1.00, 0.95, 0.90, 0.85):
        for tm in (0.70, 0.50, 0.30):
            for frac in (0.10, 0.20):
                sel = np.zeros(n, bool); sel[order[:int(frac * n)]] = True
                a, c = policy(EV, um, tm, sel)
                uc_ = uniform_cost_for(a)
                save = (uc_ - c) / uc_ * 100 if uc_ > 0 else float("nan")
                flag = "  <==" if save > 5 else ""
                print(f"  {um:8.2f} {tm:7.2f} {100*frac:7.0f}% {a:8.0f} {c:9.0f} "
                      f"{c/max(a,1e-9):8.1f} {uc_:24.0f} {save:7.1f}%{flag}")
                res["combined"].append(dict(uniform=um, target=tm, frac=frac, avoided=a,
                                            cost=c, uniform_equiv=uc_, saving_pct=save))

    print()
    print("=" * 92)
    print("3. THE SAME WITH PERFECT TARGETING, AS THE CEILING")
    print("=" * 92)
    print("  Selecting on the realised cost rather than the predicted one.\n")
    oracle = np.argsort(base)
    print(f"  {'uniform':>8s} {'target':>7s} {'treated':>8s} {'avoided':>8s} {'mg/dL.h':>9s} "
          f"{'uniform at same benefit':>24s} {'saving':>8s}")
    res["oracle"] = []
    for um in (1.00, 0.90, 0.85):
        for tm in (0.50, 0.30):
            sel = np.zeros(n, bool); sel[oracle[:int(0.20 * n)]] = True
            a, c = policy(EV, um, tm, sel)
            uc_ = uniform_cost_for(a)
            save = (uc_ - c) / uc_ * 100 if uc_ > 0 else float("nan")
            print(f"  {um:8.2f} {tm:7.2f} {20:7d}% {a:8.0f} {c:9.0f} {uc_:24.0f} {save:7.1f}%")
            res["oracle"].append(dict(uniform=um, target=tm, avoided=a, cost=c,
                                      uniform_equiv=uc_, saving_pct=save))

    if args.json:
        json.dump(res, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
