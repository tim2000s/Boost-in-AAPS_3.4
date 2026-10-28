#!/usr/bin/env python3
"""Fit the shippable form of the consequence prior and report what the simplification costs.

The measurement used a gradient booster, which is not what should go on a phone. The prior needs
three inputs, glucose at the onset and the two clock terms, so a logistic regression is the natural
shipping form: four coefficients, deterministic, no library, and pre-trained at inference, which is
what the dose-path rule permits.

What matters is the gap between the booster and the logistic. If the logistic gives most of the
separation the booster does, the simplification is free and the coefficients below are what the
engine carries.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""
import json, os, sys
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
import lightgbm as lgb
from size_readability import LGB, SEED, auc_of

FEATS = ["h10_base", "tod_sin", "tod_cos"]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    n_sub = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    d = pd.read_parquet(os.path.join(here, "out", "rise_outcomes.parquet"),
                        columns=["subject_id", "study", "max_bg", "peak_rise"] + FEATS)
    keep = sorted(d.subject_id.unique())[:n_sub]
    d = d[d.subject_id.isin(keep)].dropna()
    g = pd.factorize(d.subject_id)[0]
    X = d[FEATS].to_numpy(float)
    out = {}
    for target, y in (("max_bg_gt_180", (d.max_bg > 180).astype(int).to_numpy()),
                      ("peak_rise_ge_60", (d.peak_rise >= 60).astype(int).to_numpy())):
        sl = np.full(len(y), np.nan)
        sb = np.full(len(y), np.nan)
        for tr, te in GroupKFold(n_splits=5).split(X, y, g):
            lr = LogisticRegression(max_iter=2000)
            lr.fit(X[tr], y[tr])
            sl[te] = lr.predict_proba(X[te])[:, 1]
            bm = lgb.LGBMClassifier(random_state=SEED, **LGB)
            bm.fit(X[tr], y[tr])
            sb[te] = bm.predict_proba(X[te])[:, 1]
        full = LogisticRegression(max_iter=2000).fit(X, y)
        out[target] = dict(auc_logistic=auc_of(y, sl), auc_booster=auc_of(y, sb),
                           base_rate=float(y.mean()),
                           intercept=float(full.intercept_[0]),
                           coef=dict(zip(FEATS, [float(c) for c in full.coef_[0]])))
        o = out[target]
        print(f"{target}: base {o['base_rate']:.3f}  logistic {o['auc_logistic']:.3f}  "
              f"booster {o['auc_booster']:.3f}  cost {o['auc_logistic']-o['auc_booster']:+.3f}",
              flush=True)
        print(f"   p = sigmoid({o['intercept']:+.5f} "
              + " ".join(f"{v:+.6f}*{k}" for k, v in o["coef"].items()) + ")", flush=True)
    out["n"] = int(len(d))
    out["participants"] = int(d.subject_id.nunique())
    json.dump(out, open(os.path.join(here, "out", "consequence_prior_fit.json"), "w"), indent=1)
    print(f"\n{len(d):,} onsets, {d.subject_id.nunique()} participants; wrote "
          "out/consequence_prior_fit.json")


if __name__ == "__main__":
    sys.exit(main())
