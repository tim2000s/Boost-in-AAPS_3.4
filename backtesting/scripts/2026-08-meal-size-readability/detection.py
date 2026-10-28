#!/usr/bin/env python3
"""Is a declared meal distinguishable from an undeclared rise, on a thousand participants?

The other half of the 2026-08-13 carb-signature study, which put this at 0.805 ten minutes after
onset and 0.975 by thirty, on six participants. Detection is the figure the accel meal shadow is
judged against, so it is worth knowing to better than six people.

The negative class is built exactly as the prior study built it: a rise of at least 25 mg/dL
within thirty minutes, above the rescue threshold, with no carbohydrate entered within two hours
either side.

That construction carries an asymmetry the prior study noted in its limitations but did not
measure. The negatives must rise 25 mg/dL to qualify while the positives face no such bar, so the
two classes are selected on the very quantity the classifier reads. The matched variant below
applies the same 25 mg/dL requirement to the meals, which is the comparison that isolates whether
a meal looks different from another rise of similar size.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, secondary analysis.
"""

import argparse
import bisect
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

from extract_meals import HORIZONS, RESCUE_BG, _connect, _series, shape_features, subjects_of
from size_readability import LGB, N_FOLDS, SEED, auc_of, cluster_ci

import lightgbm as lgb
from sklearn.model_selection import GroupKFold

MIN_NEG_RISE = 25.0
NEG_CARB_GAP_S = 7200


def negatives_for(arg):
    subject, _age = arg
    conn = _connect()
    with conn.cursor() as cur:
        ts, bg = _series(cur, "cgm", "cgm_mgdl", subject)
        ct, _cg = _series(cur, "carbs", "carbs_g", subject)
    if len(ts) < 100:
        return None
    rows = []
    i = 4
    while i < len(ts) - 40:
        w = bisect.bisect_right(ts, ts[i] + 30 * 60)
        if w - i >= 4 and bg[i:w].max() - bg[i] >= MIN_NEG_RISE and bg[i] > RESCUE_BG:
            k = bisect.bisect_left(ct, ts[i] - NEG_CARB_GAP_S)
            k2 = bisect.bisect_right(ct, ts[i] + NEG_CARB_GAP_S)
            if k == k2:
                row = dict(subject_id=subject, t0=ts[i], is_meal=0)
                ok = True
                for h in HORIZONS:
                    f = shape_features(ts, bg, ts[i], h)
                    if f is None:
                        ok = False
                        break
                    for kk, v in f.items():
                        row[f"h{h}_{kk}"] = v
                if ok:
                    hour = (ts[i] % 86400) / 3600.0
                    row["hour"] = hour
                    row["tod_sin"] = float(np.sin(2 * np.pi * hour / 24))
                    row["tod_cos"] = float(np.cos(2 * np.pi * hour / 24))
                    rows.append(row)
                i = w + 12
                continue
        i += 1
    return pd.DataFrame(rows) if rows else None


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--data", default=os.path.join(here, "out"))
    ap.add_argument("--study", default="Loop")
    ap.add_argument("--workers", type=int, default=max(1, os.cpu_count() // 2))
    ap.add_argument("--boot", type=int, default=2000)
    args = ap.parse_args()

    negpath = os.path.join(args.data, f"negatives_{args.study}.parquet")
    if os.path.exists(negpath):
        neg = pd.read_parquet(negpath)
    else:
        subs = subjects_of(args.study)
        t0 = time.time()
        frames = []
        with Pool(args.workers) as pool:
            for i, df in enumerate(pool.imap_unordered(negatives_for, subs, chunksize=4), 1):
                if df is not None:
                    frames.append(df)
                if i % 200 == 0:
                    print(f"{i}/{len(subs)} subjects, {sum(len(f) for f in frames):,} rises, "
                          f"{time.time() - t0:.0f}s", flush=True)
        neg = pd.concat(frames, ignore_index=True)
        neg.to_parquet(negpath, index=False)
    print(f"negatives: {len(neg):,} unannounced rises, {neg.subject_id.nunique()} subjects",
          flush=True)

    pos = pd.read_parquet(os.path.join(args.data, f"meals_{args.study}.parquet"))
    pos = pos.assign(is_meal=1)
    print(f"positives: {len(pos):,} announced meals, {pos.subject_id.nunique()} subjects",
          flush=True)

    shape_cols = [c for c in neg.columns if c.startswith("h") and "_" in c and c != "hour"]
    results = []
    for variant in ("as_prior", "matched_on_rise"):
        p = pos if variant == "as_prior" else pos[pos.h30_peak_so_far >= MIN_NEG_RISE]
        d = pd.concat([p[shape_cols + ["subject_id", "is_meal"]],
                       neg[shape_cols + ["subject_id", "is_meal"]]], ignore_index=True)
        for h in HORIZONS:
            feats = [c for c in shape_cols if c.startswith(f"h{h}_")]
            dd = d.dropna(subset=feats)
            X = dd[feats].to_numpy(dtype=np.float64)
            y = dd.is_meal.to_numpy(dtype=np.int64)
            g = pd.factorize(dd.subject_id)[0]
            s = np.full(len(y), np.nan)
            for tr, te in GroupKFold(n_splits=N_FOLDS).split(X, y, g):
                m = lgb.LGBMClassifier(random_state=SEED, **LGB)
                m.fit(X[tr], y[tr])
                s[te] = m.predict_proba(X[te])[:, 1]
            ok = np.isfinite(s)
            a = auc_of(y[ok], s[ok])
            lo, hi = cluster_ci(g[ok], y[ok], s[ok], args.boot)
            r = dict(variant=variant, horizon=h, n=int(len(dd)),
                     meals=int(y.sum()), rises=int(len(y) - y.sum()),
                     subjects=int(dd.subject_id.nunique()), auc=a, lo=lo, hi=hi)
            results.append(r)
            print(f"{variant:>16} h{h:>3d}  n={r['n']:>8,} ({r['meals']:,} meals / "
                  f"{r['rises']:,} rises)  AUC {a:.3f} [{lo:.3f}, {hi:.3f}]", flush=True)

    import json
    out = os.path.join(args.data, f"detection_{args.study}.json")
    with open(out, "w") as fh:
        json.dump(dict(study=args.study, boot=args.boot, results=results), fh, indent=1)
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
