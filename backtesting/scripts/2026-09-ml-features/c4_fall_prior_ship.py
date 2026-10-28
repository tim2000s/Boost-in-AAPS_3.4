"""Candidate 4: would a fall prior survive leaving the cohort it was fitted on, and what
does the shippable form of it cost?

Boost's rise-consequence prior is a four-coefficient logistic, fitted offline on the
research corpora and evaluated at inference, which is what the dose-path rule permits. If
the fall side of the same question carries signal, it should ship the same way, so it has
to clear the same two hurdles the rise prior cleared.

The first is transfer. A prior fitted on people in clinical studies between 2015 and 2022
is being asked about populations it has never seen: 183 OpenAPS Data Commons participants
running DIY loops, and the 16 Boost participants the registry holds a clock offset for, who
are the people any of this would actually be deployed on. Each is scored twice, once by the
externally fitted prior and once by a prior fitted on that cohort itself with participants
held out, and the gap between the two is the cost of not having the cohort.

The second hurdle is the simplification. The measurement uses a gradient booster; a phone
gets a logistic. What matters is the gap between them.
"""

from __future__ import annotations

import argparse
import json
import os

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

import common
from boost_cohort import boost_fall_onsets
from c2_fall_consequence import (BASE, SHAPE, commons_onsets, studies_onsets,
                                 subsample)

PARAMS = dict(objective="binary", n_estimators=200, learning_rate=0.05, num_leaves=31,
              min_child_samples=100, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, verbose=-1, n_jobs=7, force_col_wise=True)

HORIZONS = (10, 20)

PAIRS = [
    ("external_shape", "external_clock", "external_shape_over_clock"),
    ("within_shape", "within_clock", "within_shape_over_clock"),
    ("external_clock", "within_clock", "transfer_cost_clock"),
    ("external_shape", "within_shape", "transfer_cost_shape"),
    ("external_clock_logistic", "external_clock", "logistic_cost_clock"),
    ("external_shape_logistic", "external_shape", "logistic_cost_shape"),
    ("external_shape_logistic", "external_clock_logistic", "shipping_shape_over_clock"),
]


def arms_for(h: int) -> dict:
    return {"clock": list(BASE), "shape": list(BASE) + [f"h{h}_{s}" for s in SHAPE]}


def fit_booster(tr, feats, target):
    m = lgb.LGBMClassifier(random_state=0, **PARAMS)
    m.fit(tr[feats], tr[target])
    return m


def within_cohort(df, feats, target, k=5):
    s = np.full(len(df), np.nan)
    folds = df["fold"].to_numpy()
    for f in range(k):
        tr, te = folds != f, folds == f
        if te.sum() == 0 or df.loc[tr, target].nunique() < 2:
            continue
        s[te] = fit_booster(df[tr], feats, target).predict_proba(df.loc[te, feats])[:, 1]
    return s


def logistic_arm(tr, te, feats, target):
    """The shipping form: standardised inputs, one linear model, coefficients reported."""
    sc = StandardScaler().fit(tr[feats].to_numpy(float))
    lr = LogisticRegression(max_iter=3000)
    lr.fit(sc.transform(tr[feats].to_numpy(float)), tr[target].to_numpy())
    score = lr.predict_proba(sc.transform(te[feats].to_numpy(float)))[:, 1]
    return score, dict(intercept=float(lr.intercept_[0]),
                       coef=dict(zip(feats, [float(c) for c in lr.coef_[0]])),
                       mean=dict(zip(feats, [float(x) for x in sc.mean_])),
                       scale=dict(zip(feats, [float(x) for x in sc.scale_])))


def evaluate(label: str, ev: pd.DataFrame, st: pd.DataFrame, kind: str, h: int,
             out: dict, external: dict):
    target = f"y_{kind}_after{h}"
    arms = arms_for(h)
    pid = ev["pid"].to_numpy()
    y = ev[target].to_numpy()
    S, coefs = {}, {}
    for name, feats in arms.items():
        S[f"within_{name}"] = within_cohort(ev, feats, target)
        S[f"external_{name}"] = external[name].predict_proba(ev[feats])[:, 1]
        sc, meta = logistic_arm(st, ev, feats, target)
        S[f"external_{name}_logistic"] = sc
        coefs[f"external_{name}_logistic"] = meta

    res = {"target": target, "cohort": label, "horizon_min": h, "n": int(len(ev)),
           "n_participants": int(ev.pid.nunique()), "base_rate": float(y.mean()),
           "base_rate_training": float(st[target].mean()),
           "auc": {}, "paired": {}, "coefficients": coefs}
    for n, sc in S.items():
        a, lo, hi = common.participant_bootstrap_auc(pid, y, sc)
        res["auc"][n] = [a, lo, hi]
        print(f"    {label}/{kind}/h{h} {n:26s} AUC {a:.4f} [{lo:.4f}, {hi:.4f}]",
              flush=True)
    for a, b, nm in PAIRS:
        r = common.paired_participant_bootstrap(pid, y, S[a], S[b])
        res["paired"][nm] = dict(delta=r.delta, lo=r.lo, hi=r.hi, n_part=r.n_part,
                                 n_ahead=r.n_ahead, verdict=r.verdict)
        print(f"    {label}/{kind}/h{h} {nm:28s} {r}", flush=True)
    out.setdefault(label, {}).setdefault(kind, {})[f"h{h}"] = res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=7)
    a = ap.parse_args()

    feats = sorted({f for h in HORIZONS for v in arms_for(h).values() for f in v})
    st = subsample(studies_onsets(a.workers).dropna(subset=feats), 200)
    cohorts = {
        "commons": commons_onsets().dropna(subset=feats),
        "boost": boost_fall_onsets().dropna(subset=feats),
    }
    for name, d in cohorts.items():
        d["fold"] = [common.stable_fold(p, 5) for p in d["pid"]]
        print(f"  {name}: {len(d):,} onsets / {d.pid.nunique()} participants", flush=True)
    print(f"  corpora (training source): {len(st):,} onsets / "
          f"{st.pid.nunique()} participants", flush=True)

    out = {}
    for kind in ("low", "severe"):
        for h in HORIZONS:
            target = f"y_{kind}_after{h}"
            external = {n: fit_booster(st, f, target) for n, f in arms_for(h).items()}
            for label, ev in cohorts.items():
                evaluate(label, ev, st, kind, h, out, external)
    with open(os.path.join(common.OUT, "c4_fall_prior_ship.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("written c4_fall_prior_ship.json")
