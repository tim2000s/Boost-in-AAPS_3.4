#!/usr/bin/env python3
"""Residency ML layer — foreseeability / avoidability of highs and lows (2026-07-08).

Two questions the rule-based attribution can't answer alone:
  1. Which state features actually PRECEDE a high / low? (validates the hand-coded causes)
  2. How FORESEEABLE is each episode from the state ~45 min before onset? A foreseeable
     high with a dosing-failure cause is AVOIDABLE; a surprise high is the floor.

Method: LGBM binary classifiers for forward-high (bg+60 > 180) and forward-low
(bg+60 < 70), trained with GroupKFold BY USER (no within-user leakage). Report OOF AUC,
gain importance + SHAP, then score each episode's pre-onset cycle with the OOF model to
split episode-minutes into foreseeable vs surprise, by cause.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

sys.path.append(os.path.dirname(__file__))
from residency_attribution import load_prep, segment, HIGH, LOW, MIN_PER_CYCLE, PRE_MIN  # noqa

FEATS = ["bg", "delta5", "iob", "act", "sens", "ev", "tgt", "insreq", "budget", "score",
         "age", "steps_60m", "hour", "knob", "cap", "recent_meal_iob", "bgi5"]
STATE_ORD = {"IDLE": 0, "OBSERVING": 1, "CONFIRMED": 2, "COMMITTED": 3, "RECOVERING": 4}


def build_xy(df):
    d = df.copy()
    d["state_ord"] = d.state.map(STATE_ORD).fillna(-1)
    d["ev_gap"] = d.ev - d.tgt
    d["iob_frac"] = d.iob / d.tdd.where(d.tdd > 0)
    feats = FEATS + ["state_ord", "ev_gap", "iob_frac"]
    X = d[feats].astype(float).replace([np.inf, -np.inf], np.nan)
    yhi = (d.get("bg60") > HIGH).astype(int)   # forward-high in ~60 min
    ylo = (d.get("bg60") < LOW).astype(int)
    grp = d.user_id.values
    ok = d["bg60"].notna().values
    return X[ok], yhi[ok], ylo[ok], grp[ok], d.index.values[ok], feats


def oof_model(X, y, grp, feats):
    """GroupKFold-by-user OOF predictions + a full-data model for importance."""
    oof = np.full(len(y), np.nan)
    gkf = GroupKFold(n_splits=min(5, len(np.unique(grp))))
    aucs = []
    for tr, te in gkf.split(X, y, grp):
        m = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.03, num_leaves=31,
                               subsample=0.8, colsample_bytree=0.8, min_child_samples=50,
                               n_jobs=-1, verbose=-1)
        m.fit(X.iloc[tr], y.iloc[tr])
        p = m.predict_proba(X.iloc[te])[:, 1]
        oof[te] = p
        if y.iloc[te].nunique() > 1:
            aucs.append(roc_auc_score(y.iloc[te], p))
    full = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.03, num_leaves=31,
                              subsample=0.8, colsample_bytree=0.8, min_child_samples=50,
                              n_jobs=-1, verbose=-1).fit(X, y)
    imp = pd.Series(full.booster_.feature_importance("gain"), index=feats).sort_values(ascending=False)
    return oof, np.mean(aucs), np.std(aucs), imp


def pre_onset_pos(g, onset):
    ts = g.ts_epoch.values
    target = ts[onset] - PRE_MIN * 60
    a = onset
    while a > 0 and ts[a - 1] >= target:
        a -= 1
    return a


def main():
    df = load_prep().reset_index(drop=True)
    from residency_attribution import vc  # forward horizons
    df = vc.forward_bg(df)
    X, yhi, ylo, grp, idx, feats = build_xy(df)

    print("=== forward-HIGH (bg+60 > 180) ===")
    oof_hi, auc_hi, sd_hi, imp_hi = oof_model(X, yhi, grp, feats)
    print(f"OOF AUC (grouped-by-user): {auc_hi:.3f} ± {sd_hi:.3f}")
    print("top gain features:", ", ".join(f"{k}={v:.0f}" for k, v in imp_hi.head(8).items()))

    print("\n=== forward-LOW (bg+60 < 70) ===")
    oof_lo, auc_lo, sd_lo, imp_lo = oof_model(X, ylo, grp, feats)
    print(f"OOF AUC (grouped-by-user): {auc_lo:.3f} ± {sd_lo:.3f}")
    print("top gain features:", ", ".join(f"{k}={v:.0f}" for k, v in imp_lo.head(8).items()))

    # map OOF prob back to df rows
    df["p_hi"] = np.nan
    df["p_lo"] = np.nan
    df.loc[idx, "p_hi"] = oof_hi
    df.loc[idx, "p_lo"] = oof_lo

    # Avoidability, threshold-free: the OOF model's mean risk at the pre-onset cycle
    # (PRE_MIN before each episode), by cause. Compared to the population base rate, a
    # high mean pre-onset risk => the episode was already forecastable => a dosing-failure
    # cause there is AVOIDABLE; risk near/below base rate => a genuine surprise.
    base_hi = float(yhi.mean())
    base_lo = float(ylo.mean())
    eps = json.load(open(os.path.join(os.path.dirname(__file__), "residency_episodes.json")))
    # per-user (ts -> row) for pre-onset lookup
    pre = {}
    for u, g in df.groupby("user_id", sort=False):
        gg = g.sort_values("ts_epoch")
        pre[u] = (gg.ts_epoch.values, gg.p_hi.values, gg.p_lo.values)
    from collections import defaultdict
    agg = defaultdict(lambda: {"min": 0.0, "risk_sum": 0.0, "n": 0})
    for e in eps["episodes"]:
        tsv, phi, plo = pre[e["user"]]
        target = e["onset_ts"] - PRE_MIN * 60
        j = np.searchsorted(tsv, target)
        j = min(max(j, 0), len(tsv) - 1)
        p = (phi if e["kind"] == "high" else plo)[j]
        key = (e["kind"], e["cause"])
        agg[key]["min"] += e["minutes"]
        if np.isfinite(p):
            agg[key]["risk_sum"] += p
            agg[key]["n"] += 1

    print(f"\n=== AVOIDABILITY — mean model risk {PRE_MIN}min BEFORE onset, by cause "
          f"(base rate: high {base_hi:.2f}, low {base_lo:.2f}) ===")
    print(f"{'kind':>5} {'cause':>16} {'minutes':>8} {'pre-onset risk':>15}  vs base")
    out_by_cause = {}
    for (kind, cause), v in sorted(agg.items(), key=lambda x: -x[1]["min"]):
        mr = v["risk_sum"] / v["n"] if v["n"] else float("nan")
        base = base_hi if kind == "high" else base_lo
        flag = "FORESEEABLE" if mr >= 1.5 * base else ("surprise" if mr < base else "elevated")
        print(f"{kind:>5} {cause:>16} {v['min']:>8.0f} {mr:>15.2f}  ({mr/base:.1f}x) {flag}")
        out_by_cause[f"{kind}:{cause}"] = dict(minutes=v["min"], pre_risk=round(mr, 3),
                                               x_base=round(mr / base, 2))

    json.dump(dict(auc_hi=auc_hi, auc_lo=auc_lo, base_hi=base_hi, base_lo=base_lo,
                   imp_hi=imp_hi.head(10).to_dict(), imp_lo=imp_lo.head(10).to_dict(),
                   avoidability=out_by_cause),
              open(os.path.join(os.path.dirname(__file__), "residency_ml.json"), "w"))
    print("\n-> residency_ml.json")


if __name__ == "__main__":
    main()
