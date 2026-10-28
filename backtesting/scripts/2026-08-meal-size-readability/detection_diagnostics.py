#!/usr/bin/env python3
"""What carries meal detection, where its operating point sits, and whether it transfers.

An area under the curve says a detector could be built. It does not say which inputs it needs, how
often it would fire when nothing was eaten, or whether a model fitted on one population works on
another. Those three decide whether any of this is worth putting in a controller.

Ablation follows the programme's standing finding that glucose value, delta and curvature carry
essentially all of the short-horizon signal. If that holds here, a detector needs nothing exotic.

The operating point is expressed as false alarms per subject-day rather than as a false positive
rate, because a rate says nothing until it is multiplied by how often the negative class occurs.

Transfer trains on one study and tests on the other, which crosses therapy, era and
de-identification scheme at once and is the closest available analogue to deploying a model fitted
on other people.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, secondary analysis.
"""

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

import lightgbm as lgb
from size_readability import LGB, N_FOLDS, SEED, auc_of, cluster_ci

MIN_NEG_RISE = 25.0
SHAPE = ("base", "rise", "rise_rate", "peak_so_far", "auc", "inc_max", "inc_last",
         "inc_mean", "accel", "curv", "pre_slope", "still_rising")

FEATURE_SETS = {
    "value_delta":        ("base", "rise", "inc_last"),
    "value_delta_curv":   ("base", "rise", "inc_last", "curv", "accel"),
    "full_shape":         SHAPE,
}


def load(data, study):
    pos = pd.read_parquet(os.path.join(data, f"meals_{study}.parquet"))
    pos = pos[pos.h30_peak_so_far >= MIN_NEG_RISE].assign(is_meal=1)
    neg = pd.read_parquet(os.path.join(data, f"negatives_{study}.parquet")).assign(is_meal=0)
    cols = [c for c in neg.columns if c.startswith("h") and c != "hour"]
    keep = [c for c in cols if c in pos.columns] + ["subject_id", "is_meal", "t0"]
    d = pd.concat([pos[keep], neg[keep]], ignore_index=True)
    return d


def subject_days(d):
    span = d.groupby("subject_id").t0.agg(lambda s: (s.max() - s.min()) / 86400.0)
    return float(span.sum())


def oof(d, feats, y, g):
    X = d[feats].to_numpy(dtype=np.float64)
    s = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=N_FOLDS).split(X, y, g):
        m = lgb.LGBMClassifier(random_state=SEED, **LGB)
        m.fit(X[tr], y[tr])
        s[te] = m.predict_proba(X[te])[:, 1]
    return s


def operating(y, s, days, targets=(0.70, 0.80, 0.90)):
    """At a target sensitivity, what does the detector cost in false alarms per day."""
    pos, neg = s[y == 1], s[y == 0]
    out = []
    for t in targets:
        thr = np.quantile(pos, 1 - t)
        fp = float((neg > thr).sum())
        out.append(dict(sensitivity=t, fpr=fp / len(neg),
                        false_alarms_per_day=fp / days,
                        detections_per_day=float((pos > thr).sum()) / days))
    return out


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--data", default=os.path.join(here, "out"))
    ap.add_argument("--horizons", default="10,30")
    ap.add_argument("--boot", type=int, default=1000)
    args = ap.parse_args()
    hs = [int(h) for h in args.horizons.split(",")]

    res = {"ablation": [], "operating": [], "transfer": [], "per_subject": []}
    loop = load(args.data, "Loop")
    days = subject_days(loop)
    print(f"Loop: {len(loop):,} rows, {loop.subject_id.nunique()} subjects, "
          f"{days:,.0f} subject-days\n", flush=True)

    y = loop.is_meal.to_numpy(dtype=np.int64)
    g = pd.factorize(loop.subject_id)[0]

    for h in hs:
        for name, cols in FEATURE_SETS.items():
            feats = [f"h{h}_{c}" for c in cols]
            d = loop.dropna(subset=feats)
            yy = d.is_meal.to_numpy(dtype=np.int64)
            gg = pd.factorize(d.subject_id)[0]
            s = oof(d, feats, yy, gg)
            ok = np.isfinite(s)
            a = auc_of(yy[ok], s[ok])
            lo, hi = cluster_ci(gg[ok], yy[ok], s[ok], args.boot)
            res["ablation"].append(dict(horizon=h, features=name, n_features=len(feats),
                                        n=int(len(d)), auc=a, lo=lo, hi=hi))
            print(f"h{h:>3} {name:>18} ({len(feats)} feats)  AUC {a:.3f} [{lo:.3f}, {hi:.3f}]",
                  flush=True)
            if name == "full_shape":
                for op in operating(yy[ok], s[ok], days):
                    op.update(horizon=h)
                    res["operating"].append(op)
                    print(f"      sensitivity {op['sensitivity']:.0%}: "
                          f"FPR {op['fpr']:.3f}, {op['false_alarms_per_day']:.2f} false alarms/day, "
                          f"{op['detections_per_day']:.2f} detections/day", flush=True)
                # per-participant spread: does it work for everybody?
                per = []
                for sid, idx in d.groupby(pd.factorize(d.subject_id)[0]).groups.items():
                    ii = d.index.get_indexer(idx)
                    yv, sv = yy[ii], s[ii]
                    if yv.sum() >= 20 and (len(yv) - yv.sum()) >= 20:
                        v = auc_of(yv, sv)
                        if np.isfinite(v):
                            per.append(v)
                per = np.array(per)
                res["per_subject"].append(dict(horizon=h, k=len(per),
                                               p10=float(np.percentile(per, 10)),
                                               p50=float(np.percentile(per, 50)),
                                               p90=float(np.percentile(per, 90)),
                                               below_60=float((per < 0.60).mean())))
                print(f"      per participant (k={len(per)}): p10 {np.percentile(per,10):.3f}, "
                      f"median {np.percentile(per,50):.3f}, p90 {np.percentile(per,90):.3f}, "
                      f"{(per<0.60).mean():.1%} below 0.60", flush=True)

    # transfer: fit on one study, score the other
    rbg = load(args.data, "ReplaceBG")
    print(f"\nReplaceBG: {len(rbg):,} rows, {rbg.subject_id.nunique()} subjects", flush=True)
    for h in hs:
        feats = [f"h{h}_{c}" for c in SHAPE]
        a_tr = loop.dropna(subset=feats)
        b_te = rbg.dropna(subset=feats)
        m = lgb.LGBMClassifier(random_state=SEED, **LGB)
        m.fit(a_tr[feats].to_numpy(float), a_tr.is_meal.to_numpy(int))
        s = m.predict_proba(b_te[feats].to_numpy(float))[:, 1]
        yy = b_te.is_meal.to_numpy(int)
        gg = pd.factorize(b_te.subject_id)[0]
        a = auc_of(yy, s)
        lo, hi = cluster_ci(gg, yy, s, args.boot)
        res["transfer"].append(dict(horizon=h, train="Loop", test="ReplaceBG",
                                    n=int(len(b_te)), auc=a, lo=lo, hi=hi))
        print(f"h{h:>3} train Loop -> test ReplaceBG  AUC {a:.3f} [{lo:.3f}, {hi:.3f}]", flush=True)

    out = os.path.join(args.data, "detection_diagnostics.json")
    json.dump(res, open(out, "w"), indent=1)
    print(f"\nwrote {out}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
