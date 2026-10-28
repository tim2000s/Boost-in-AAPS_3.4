#!/usr/bin/env python3
"""Does the shape of a rise say anything about where it ends up, beyond where it started?

Every rise onset in the corpus is scored at four horizons against outcomes read from the trace
afterwards, so no announcement is needed and all seven studies contribute.

Three arms, and the third is the only one that can earn anything. Glucose at the onset alone is a
strong predictor of both labels for a trivial reason: a rise beginning at 160 has less room before
it matters than one beginning at 90. Adding the clock is free. The question is whether the shape of
the first ten to thirty minutes adds anything to those two, because a controller has them already.

Thresholds are swept rather than fixed, since the anchor already requires a 25 mg/dL rise and a low
threshold leaves almost every rise positive.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""

import argparse
import json
import os
import sys
import warnings
from multiprocessing import Pool

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

import lightgbm as lgb
from size_readability import LGB, N_FOLDS, SEED, auc_of, cluster_ci

warnings.filterwarnings("ignore")

SHAPE = ("base", "rise", "rise_rate", "peak_so_far", "auc", "inc_max", "inc_last",
         "inc_mean", "accel", "curv", "pre_slope", "still_rising")
TOD = ["tod_sin", "tod_cos"]
HORIZONS = (10, 15, 20, 30)
LABELS = {
    "peak_rise_ge_60": ("peak_rise", 60.0),
    "peak_rise_ge_80": ("peak_rise", 80.0),
    "peak_rise_ge_100": ("peak_rise", 100.0),
    "max_bg_gt_180": ("max_bg", 180.0),
    "max_bg_gt_250": ("max_bg", 250.0),
}
_DF = {}
SUBSET = {}


def data(path, cols):
    """Read only the columns this job needs.

    Parquet is columnar, so a slim read is cheap, and reading the whole frame in every worker is
    what put the machine into swap the first time this ran: seven workers each holding two million
    rows by fifty-five columns is about six gigabytes of duplicated data for no reason.
    """
    key = (path, tuple(sorted(cols)), SUBSET.get("n", 0))
    if key not in _DF:
        _DF.clear()
        d = pd.read_parquet(path, columns=list(cols))
        n = SUBSET.get("n", 0)
        if n:
            # Sample participants, not rows: the fold unit and the bootstrap unit is the person, so
            # cutting people is the only reduction that leaves the uncertainty honest. 400 is far
            # more than GroupKFold needs and keeps the whole run inside a few hundred megabytes.
            keep = sorted(d.subject_id.unique())[:n]
            d = d[d.subject_id.isin(keep)]
        for c in d.columns:
            if d[c].dtype == "float64":
                d[c] = d[c].astype("float32")
        _DF[key] = d
    return _DF[key]


def features_for(arm, h):
    if arm == "onset_bg":
        return [f"h{h}_base"]
    if arm == "onset_bg_clock":
        return [f"h{h}_base"] + TOD
    return [f"h{h}_{s}" for s in SHAPE] + TOD


def tpr_at_fpr(y, s, fpr=0.20):
    neg = np.sort(s[y == 0])
    if len(neg) == 0 or (y == 1).sum() == 0:
        return np.nan
    thr = neg[int(np.ceil((1 - fpr) * len(neg))) - 1]
    return float((s[y == 1] > thr).mean())


def task(job):
    path, arm, h, label, n_boot, n_sub = job
    SUBSET["n"] = n_sub
    col, thr = LABELS[label]
    feats = features_for(arm, h)
    d = data(path, set(feats) | {col, "subject_id"}).dropna(subset=feats + [col])
    if len(d) < 1000:
        return None
    y = (d[col].to_numpy(float) >= thr).astype(np.int64)
    if y.mean() < 0.02 or y.mean() > 0.98:
        return None
    X = d[feats].to_numpy(np.float32)
    g = pd.factorize(d.subject_id)[0]
    s = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=N_FOLDS).split(X, y, g):
        m = lgb.LGBMClassifier(random_state=SEED, **LGB)
        m.fit(X[tr], y[tr])
        s[te] = m.predict_proba(X[te])[:, 1]
    ok = np.isfinite(s)
    a = auc_of(y[ok], s[ok])
    lo, hi = cluster_ci(g[ok], y[ok], s[ok], n_boot)
    return dict(arm=arm, horizon=h, label=label, n=int(len(d)),
                subjects=int(d.subject_id.nunique()), base_rate=float(y.mean()),
                auc=a, lo=lo, hi=hi, tpr_at_20fpr=tpr_at_fpr(y[ok], s[ok]))


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--data", default=os.path.join(here, "out"))
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--subjects", type=int, default=400)
    args = ap.parse_args()
    SUBSET["n"] = args.subjects
    path = os.path.join(args.data, "rise_outcomes.parquet")
    head = pd.read_parquet(path, columns=["subject_id", "study"])
    print(f"{len(head):,} rise onsets, {head.subject_id.nunique()} participants, "
          f"{head.study.nunique()} studies", flush=True)
    del head

    jobs = [(path, arm, h, lab, args.boot, args.subjects)
            for lab in LABELS for h in HORIZONS for arm in ("onset_bg", "onset_bg_clock", "shape")]
    res = []
    # Serial by default. Every failure in this analysis came from the pool rather than the
    # arithmetic: workers duplicating the frame, orphans surviving a kill of the parent, broken
    # pipes after a worker was reclaimed. One process reading one slim frame is slower and it
    # finishes, which is the only property that matters here.
    def _results():
        if args.workers <= 1:
            for j in jobs:
                yield task(j)
        else:
            with Pool(args.workers) as pool:
                yield from pool.imap_unordered(task, jobs, chunksize=1)

    for r in _results():
            if r is None:
                continue
            res.append(r)
            print(f"{r['label']:>16} {r['arm']:>15} h{r['horizon']:>3}  "
                  f"base {r['base_rate']:.2f}  AUC {r['auc']:.3f} [{r['lo']:.3f}, {r['hi']:.3f}]",
                  flush=True)

    res.sort(key=lambda r: (r["label"], r["horizon"], r["arm"]))
    idx = {(r["label"], r["arm"], r["horizon"]): r for r in res}
    print("\nwhat the shape of the rise adds over onset glucose and the clock\n", flush=True)
    for lab in LABELS:
        for h in HORIZONS:
            a = idx.get((lab, "shape", h))
            b = idx.get((lab, "onset_bg_clock", h))
            if a and b:
                print(f"{lab:>16} h{h:>3}  shape {a['auc']:.3f}  baseline {b['auc']:.3f}  "
                      f"delta {a['auc']-b['auc']:+.3f}", flush=True)
    out = os.path.join(args.data, "rise_consequence.json")
    json.dump(res, open(out, "w"), indent=1)
    print(f"\nwrote {out}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
