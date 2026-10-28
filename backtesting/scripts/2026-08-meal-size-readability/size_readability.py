#!/usr/bin/env python3
"""Is meal size readable from the glucose trace? Arms, horizons and bolus strata.

Primary endpoint, fixed by the protocol: area under the curve for large (>=40 g) against small
(<=20 g), participants held out, at 10/15/20/30/45/60 minutes after onset, for each arm and each
bolus stratum. Secondary: mean absolute error in grams against the baseline ladder, and the share
of large meals caught by 15 and 20 minutes at a false positive rate fixed at 10 per cent.

The learner is fixed at the prior study's hyperparameters and is never tuned. The feature space is
what varies between arms, so that a null cannot be blamed on the model.

Parallelism sits at the configuration level: one worker per (arm, stratum, horizon), each
single-threaded, so a run uses exactly as many cores as it is given. Workers load the parquet
themselves rather than inheriting it, because the start method on this platform is spawn and
forking a process that holds a gigabyte alongside LightGBM's threads is not worth the risk.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md
"""

import argparse
import json
import os
import sys
import time
import warnings
from multiprocessing import Pool

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.model_selection import GroupKFold

import lightgbm as lgb

warnings.filterwarnings("ignore")

HORIZONS = (10, 15, 20, 30, 45, 60)
SHAPE = ("base", "rise", "rise_rate", "peak_so_far", "auc", "inc_max", "inc_last",
         "inc_mean", "accel", "curv", "pre_slope", "still_rising")
TOD = ["tod_sin", "tod_cos"]
PSCALE = ["p_tdd", "p_age", "p_rise_p50", "p_rise_p90", "p_bg_p50", "p_bg_sd"]
PHIST = ["h_prior_mean", "h_prior_median", "h_prior_n", "h_prior_rise_per_g"]

# fixed in advance; not searched. Depth 4 as in the prior study, leaves capped to match.
LGB = dict(n_estimators=200, max_depth=4, num_leaves=15, learning_rate=0.06,
           min_child_samples=20, verbose=-1, deterministic=True, force_row_wise=True, n_jobs=1)
N_FOLDS = 5
SEED = 20260825

_DF = {}


def _data(path):
    if path not in _DF:
        _DF[path] = pd.read_parquet(path)
    return _DF[path]


def features_for(arm, h):
    """Arms 0 to 3 carry the trajectory. Arms 10 to 13 are the matched baselines: the same
    information about the person and the clock, with the glucose trace removed entirely.

    The increment attributable to the trajectory is arm 1 minus arm 10, arm 2 minus arm 11 and
    arm 3 minus arm 12. Read against chance instead, an arm that merely knows which person it is
    looking at scores well while saying nothing about the meal in front of it.
    """
    if arm == 10:
        return list(TOD)
    if arm == 11:
        return list(PSCALE)
    if arm == 12:
        return PSCALE + PHIST
    if arm == 13:
        return PSCALE + PHIST + TOD
    shape = [f"h{h}_{s}" for s in SHAPE]
    if arm == 0:                       # the prior study's feature set exactly, no clock
        return shape
    f = shape + TOD
    if arm >= 2:
        f += PSCALE
    if arm >= 3:
        f += PHIST
    return f


def auc_of(y, s):
    """Mann-Whitney U with mid-ranks for ties, ranking done in C."""
    n1 = float(y.sum())
    n0 = float(len(y) - n1)
    if n1 == 0 or n0 == 0:
        return np.nan
    r = rankdata(s)
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def cluster_ci(groups, y, s, n_boot):
    """Resample participants, never meals. The person carries the uncertainty."""
    k = len(np.unique(groups))
    if n_boot <= 0 or k < 3:
        return (np.nan, np.nan)
    order = np.argsort(groups, kind="stable")
    gs, ys, ss = groups[order], y[order], s[order]
    bounds = np.searchsorted(gs, np.arange(k + 1))
    members = [np.arange(bounds[i], bounds[i + 1]) for i in range(k)]
    rng = np.random.default_rng(SEED)
    vals = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, k, k)
        idx = np.concatenate([members[p] for p in pick])
        vals[i] = auc_of(ys[idx], ss[idx])
    vals = vals[np.isfinite(vals)]
    if len(vals) < 10:
        return (np.nan, np.nan)
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def oof_scores(X, y, groups, kind="clf"):
    out = np.full(len(y), np.nan)
    k = min(N_FOLDS, len(np.unique(groups)))
    if k < 2:
        return out
    for tr, te in GroupKFold(n_splits=k).split(X, y, groups):
        if kind == "clf":
            m = lgb.LGBMClassifier(random_state=SEED, **LGB)
            m.fit(X[tr], y[tr])
            out[te] = m.predict_proba(X[te])[:, 1]
        else:
            m = lgb.LGBMRegressor(random_state=SEED, **LGB)
            m.fit(X[tr], y[tr])
            out[te] = m.predict(X[te])
    return out


def tpr_at_fpr(y, s, fpr=0.10):
    neg = np.sort(s[y == 0])
    if len(neg) == 0 or (y == 1).sum() == 0:
        return np.nan
    thr = neg[int(np.ceil((1 - fpr) * len(neg))) - 1]
    return float((s[y == 1] > thr).mean())


def task_classify(job):
    path, arm, h, stratum, n_boot = job
    df = _data(path)
    d = df if stratum == "all" else df[df.bolus_stratum == stratum]
    d = d[d.size_class >= 0]
    feats = features_for(arm, h)
    need = [f for f in feats if f not in PHIST]
    d = d.dropna(subset=need + ["size_class"])
    if len(d) < 200 or d.subject_id.nunique() < 5:
        return None
    X = d[feats].to_numpy(dtype=np.float64)
    y = d.size_class.to_numpy(dtype=np.int64)
    g = pd.factorize(d.subject_id)[0]

    s = oof_scores(X, y, g, "clf")
    ok = np.isfinite(s)
    a = auc_of(y[ok], s[ok])
    lo, hi = cluster_ci(g[ok], y[ok], s[ok], n_boot)

    raw = d[f"h{h}_rise"].to_numpy(dtype=np.float64)
    a_raw = auc_of(y, raw)
    lo_r, hi_r = cluster_ci(g, y, raw, n_boot)

    return dict(arm=arm, horizon=h, stratum=stratum, n=int(len(d)),
                subjects=int(d.subject_id.nunique()),
                auc=a, lo=lo, hi=hi,
                auc_raw_rise=a_raw, raw_lo=lo_r, raw_hi=hi_r,
                delta_vs_raw=float(a - a_raw),
                tpr_at_10fpr=tpr_at_fpr(y[ok], s[ok]))


def task_quantity(job):
    path, arm, h, stratum = job
    df = _data(path)
    d = df if stratum == "all" else df[df.bolus_stratum == stratum]
    feats = features_for(arm, h)
    d = d.dropna(subset=[f for f in feats if f not in PHIST] + ["carbs"])
    if len(d) < 200 or d.subject_id.nunique() < 5:
        return None
    X = d[feats].to_numpy(dtype=np.float64)
    yq = d.carbs.to_numpy(dtype=np.float64)
    g = pd.factorize(d.subject_id)[0]
    pred = oof_scores(X, yq, g, "reg")
    ok = np.isfinite(pred)
    hour = d.hour.to_numpy()
    tod_med = pd.Series(yq).groupby((hour // 3).astype(int)).transform("median").to_numpy()
    subj_med = pd.Series(yq).groupby(g).transform("median").to_numpy()
    return dict(arm=arm, horizon=h, stratum=stratum, n=int(len(d)),
                mae=float(np.mean(np.abs(pred[ok] - yq[ok]))),
                mae_median=float(np.mean(np.abs(np.median(yq) - yq))),
                mae_tod_median=float(np.mean(np.abs(tod_med - yq))),
                mae_subject_median=float(np.mean(np.abs(subj_med - yq))),
                corr=float(np.corrcoef(pred[ok], yq[ok])[0, 1]))


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--data", default=os.path.join(here, "out"))
    ap.add_argument("--study", default="Loop")
    ap.add_argument("--arms", default="1,2,3")
    ap.add_argument("--strata", default="all,at_meal,none,pre,late_gt15")
    ap.add_argument("--horizons", default=",".join(str(h) for h in HORIZONS))
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=max(1, os.cpu_count() // 2))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    path = os.path.join(args.data, f"meals_{args.study}.parquet")
    head = pd.read_parquet(path, columns=["subject_id"])
    print(f"{len(head):,} meals, {head.subject_id.nunique()} subjects, {args.study}, "
          f"{args.workers} workers", flush=True)
    del head

    arms = [int(a) for a in args.arms.split(",")]
    hs = [int(h) for h in args.horizons.split(",")]
    strata = args.strata.split(",")

    cjobs = [(path, a, h, st, args.boot) for a in arms for st in strata for h in hs]
    qjobs = [(path, a, h, "all") for a in arms for h in hs]

    t0 = time.time()
    results, quant = [], []
    with Pool(args.workers) as pool:
        for r in pool.imap_unordered(task_classify, cjobs, chunksize=1):
            if r is None:
                continue
            results.append(r)
            print(f"arm{r['arm']} {r['stratum']:>10s} h{r['horizon']:>3d}  n={r['n']:>8,}  "
                  f"AUC {r['auc']:.3f} [{r['lo']:.3f}, {r['hi']:.3f}]  "
                  f"raw {r['auc_raw_rise']:.3f}  d {r['delta_vs_raw']:+.3f}  "
                  f"({time.time() - t0:.0f}s)", flush=True)
        for q in pool.imap_unordered(task_quantity, qjobs, chunksize=1):
            if q is None:
                continue
            quant.append(q)
            print(f"arm{q['arm']} quantity h{q['horizon']:>3d}  MAE {q['mae']:.1f} g  "
                  f"median {q['mae_median']:.1f}  subj-median {q['mae_subject_median']:.1f}  "
                  f"r {q['corr']:+.3f}", flush=True)

    results.sort(key=lambda r: (r["arm"], r["stratum"], r["horizon"]))
    quant.sort(key=lambda r: (r["arm"], r["horizon"]))
    out = args.out or os.path.join(args.data, f"results_{args.study}.json")
    with open(out, "w") as fh:
        json.dump(dict(study=args.study, boot=args.boot,
                       classification=results, quantity=quant), fh, indent=1)
    print(f"wrote {out} in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
