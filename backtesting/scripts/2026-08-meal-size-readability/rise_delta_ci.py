#!/usr/bin/env python3
"""A confidence interval on the DIFFERENCE, not on each arm separately.

Two areas under the curve each carrying their own interval says nothing directly about whether they
differ, because the arms are scored on the same events by the same participants and their errors are
strongly correlated. The interval that matters is on the difference, computed by resampling
participants once per draw and scoring both arms on that same resample.

Only the horizons where the answer is in doubt are computed: at thirty minutes the gap is several
times the width of either interval and needs no test.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""
import json, os, sys
import numpy as np, pandas as pd
from sklearn.model_selection import GroupKFold
import lightgbm as lgb
from size_readability import LGB, N_FOLDS, SEED, auc_of
from rise_consequence import LABELS, SHAPE, TOD, features_for

N_BOOT = 1000


def oof(X, y, g):
    s = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=N_FOLDS).split(X, y, g):
        m = lgb.LGBMClassifier(random_state=SEED, **LGB)
        m.fit(X[tr], y[tr])
        s[te] = m.predict_proba(X[te])[:, 1]
    return s


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "out", "rise_outcomes.parquet")
    n_sub = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    out = []
    for label in ("peak_rise_ge_60", "max_bg_gt_180"):
        col, thr = LABELS[label]
        for h in (10, 20):
            fb, fs = features_for("onset_bg_clock", h), features_for("shape", h)
            cols = set(fb) | set(fs) | {col, "subject_id"}
            d = pd.read_parquet(path, columns=list(cols))
            keep = sorted(d.subject_id.unique())[:n_sub]
            d = d[d.subject_id.isin(keep)].dropna(subset=list(cols - {"subject_id"}))
            y = (d[col].to_numpy(float) >= thr).astype(np.int64)
            g = pd.factorize(d.subject_id)[0]
            sb = oof(d[fb].to_numpy(np.float32), y, g)
            ss = oof(d[fs].to_numpy(np.float32), y, g)
            ok = np.isfinite(sb) & np.isfinite(ss)
            y, g, sb, ss = y[ok], g[ok], sb[ok], ss[ok]
            order = np.argsort(g, kind="stable")
            g, y, sb, ss = g[order], y[order], sb[order], ss[order]
            k = len(np.unique(g))
            bounds = np.searchsorted(g, np.arange(k + 1))
            members = [np.arange(bounds[i], bounds[i + 1]) for i in range(k)]
            rng = np.random.default_rng(SEED)
            deltas = np.empty(N_BOOT)
            for i in range(N_BOOT):
                idx = np.concatenate([members[p] for p in rng.integers(0, k, k)])
                deltas[i] = auc_of(y[idx], ss[idx]) - auc_of(y[idx], sb[idx])
            r = dict(label=label, horizon=h, n=int(len(y)), participants=k,
                     auc_baseline=auc_of(y, sb), auc_shape=auc_of(y, ss),
                     delta=auc_of(y, ss) - auc_of(y, sb),
                     lo=float(np.percentile(deltas, 2.5)),
                     hi=float(np.percentile(deltas, 97.5)),
                     share_above_zero=float((deltas > 0).mean()))
            out.append(r)
            print(f"{label:>16} h{h:>3}  baseline {r['auc_baseline']:.3f}  shape {r['auc_shape']:.3f}  "
                  f"delta {r['delta']:+.4f} [{r['lo']:+.4f}, {r['hi']:+.4f}]  "
                  f"draws above zero {r['share_above_zero']:.1%}", flush=True)
    json.dump(out, open(os.path.join(here, "out", "rise_delta_ci.json"), "w"), indent=1)
    print("wrote out/rise_delta_ci.json")


if __name__ == "__main__":
    sys.exit(main())
