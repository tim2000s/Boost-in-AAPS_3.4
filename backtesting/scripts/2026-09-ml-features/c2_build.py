#!/usr/bin/env python3
"""Build the C2 fall-consequence model and see what it would actually do.

C2 asks a question the controller can still act on: a fall is twenty minutes old, and it is
already below where it started; is this one going to end below 70 mg/dL, or below 54?

The probe established that the shape of the fall carries information beyond the glucose reading
and the clock, and that the loop's own state adds little on top of shape. This builds the model
in the form that could ship, validates it on people it never saw, and then prices it as a
decision rather than as an AUC, because a ranking statistic says nothing about whether a
threshold placed on it would be usable.

Everything here is out of sample by participant. The Commons cohort trains and cross-validates;
the Boost cohort is held out entirely and never contributes a training row, so the external
figure is the one that says whether this transfers to the people who would run it.

Nothing here doses. A model that restrains insulin still has to be logged across the cohort and
taken through the two-test bar before it goes near the dose path.
"""
import json
import os
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CACHE = os.path.join(HERE, "cache")

# 20 minutes of observed fall. The device keeps six ring-buffer snapshots at five-minute spacing,
# so twenty minutes is four of them and fits inside what the phone already retains. Ten minutes
# scored marginally worse and thirty would need history the buffer does not hold at 5-min spacing.
H = 20

SHAPE = ["fall", "fall_rate", "nadir", "auc", "dec_max", "dec_last", "dec_mean",
         "accel", "curv", "pre_slope", "still_falling"]
# The clock enters circularly here rather than as a raw hour; see c5_clock_encoding.py.
BASE = ["base", "tod_sin", "tod_cos"]

PARAMS = dict(n_estimators=120, max_depth=5, num_leaves=31, learning_rate=0.05,
              min_child_samples=200, subsample=0.9, subsample_freq=1, colsample_bytree=0.9,
              verbose=-1, force_col_wise=True)


def feats():
    return [f"h{H}_{c}" for c in SHAPE] + BASE


def prep(path):
    d = pd.read_parquet(os.path.join(CACHE, path))
    f = feats()
    d = d.dropna(subset=f + ["y_low", "y_severe"]).copy()
    d["fold"] = [common.stable_fold(p, 5) for p in d.pid]
    return d


def export_trees(model, names, path, meta_path, meta_extra):
    """Same JSON shape the phone already walks for the other two models."""
    d = model.booster_.dump_model()

    def conv(n):
        if "leaf_value" in n:
            return {"leaf": n["leaf_value"]}
        return {"feature": n["split_feature"], "threshold": n["threshold"],
                "decision_type": n.get("decision_type", "<="),
                "left": conv(n["left_child"]), "right": conv(n["right_child"])}

    trees = [conv(t["tree_structure"]) for t in d["tree_info"]]
    obj = {"n_trees": len(trees), "n_features": len(names), "feature_names": names,
           "trees": trees, "objective": "binary", "average_output": False}
    with open(path, "w") as fh:
        json.dump(obj, fh)
    with open(meta_path, "w") as fh:
        json.dump(meta_extra, fh, indent=2)
    return len(trees)


def operating(y, s, name):
    """What a threshold on this score would actually do, per hundred fall onsets."""
    rows = []
    for q in (0.99, 0.95, 0.90, 0.80, 0.70, 0.50):
        thr = float(np.quantile(s, q))
        fire = s >= thr
        if fire.sum() == 0:
            continue
        prec = float(y[fire].mean())
        rec = float(y[fire].sum() / max(1, y.sum()))
        rows.append({"label": name, "fires_pct": round(100 * float(fire.mean()), 1),
                     "threshold": round(thr, 4), "precision": round(prec, 3),
                     "recall": round(rec, 3),
                     "lift": round(prec / max(1e-9, float(y.mean())), 2)})
    return rows


def main():
    com = prep("c2_commons_onsets.parquet")
    boo = prep("boost_fall_onsets.parquet")
    f = feats()
    res = {"horizon_min": H, "features": f,
           "n_commons": int(len(com)), "n_commons_participants": int(com.pid.nunique()),
           "n_boost": int(len(boo)), "n_boost_participants": int(boo.pid.nunique())}
    print(f"Commons {len(com):,} onsets / {com.pid.nunique()} participants; "
          f"Boost {len(boo):,} onsets / {boo.pid.nunique()} participants")

    for label in ("y_low", "y_severe"):
        print(f"\n=== {label}, base rate commons {com[label].mean():.3f}, "
              f"boost {boo[label].mean():.3f} ===")
        pid, y, sc, scb = [], [], [], []
        for fold in range(5):
            te, tr = com[com.fold == fold], com[com.fold != fold]
            m = lgb.LGBMClassifier(random_state=0, **PARAMS)
            m.fit(tr[f], tr[label].to_numpy())
            pid.append(te.pid.to_numpy()); y.append(te[label].to_numpy())
            sc.append(m.predict_proba(te[f])[:, 1])
            # baseline: onset glucose and the clock only, the thing a controller already has
            b = lgb.LGBMClassifier(random_state=0, **PARAMS)
            b.fit(tr[BASE], tr[label].to_numpy())
            scb.append(b.predict_proba(te[BASE])[:, 1])
        pid = np.concatenate(pid); y = np.concatenate(y)
        s = np.concatenate(sc); sb = np.concatenate(scb)

        a_full, a_base = common.auc(y, s), common.auc(y, sb)
        d = common.paired_participant_bootstrap(pid, y, s, sb, n_boot=4000)
        print(f"  within-Commons  shape {a_full:.4f}   baseline(BG+clock) {a_base:.4f}")
        print(f"  gain {d.delta:+.4f} ({d.lo:+.4f} to {d.hi:+.4f}), better on {d.n_ahead}/{d.n_part}")

        # external: train on all Commons, test on the Boost cohort, never trained on
        m = lgb.LGBMClassifier(random_state=0, **PARAMS)
        m.fit(com[f], com[label].to_numpy())
        se = m.predict_proba(boo[f])[:, 1]
        b = lgb.LGBMClassifier(random_state=0, **PARAMS)
        b.fit(com[BASE], com[label].to_numpy())
        sbe = b.predict_proba(boo[BASE])[:, 1]
        ye = boo[label].to_numpy()
        de = common.paired_participant_bootstrap(boo.pid.to_numpy(), ye, se, sbe, n_boot=4000)
        print(f"  external Boost  shape {common.auc(ye, se):.4f}   "
              f"baseline {common.auc(ye, sbe):.4f}")
        print(f"  gain {de.delta:+.4f} ({de.lo:+.4f} to {de.hi:+.4f}), "
              f"better on {de.n_ahead}/{de.n_part}")

        per = []
        for p, g in boo.groupby("pid"):
            yy = g[label].to_numpy()
            if yy.sum() < 10 or (1 - yy).sum() < 10:
                continue
            ss = m.predict_proba(g[f])[:, 1]
            per.append(common.auc(yy, ss))
        if per:
            print(f"  per-participant external AUC: median {np.median(per):.3f}, "
                  f"min {min(per):.3f}, max {max(per):.3f}, n={len(per)}")

        ops = operating(ye, se, label)
        print(f"  operating points on the Boost cohort (base rate {ye.mean():.3f})")
        print(f"    {'fires%':>7}{'precision':>11}{'recall':>9}{'lift':>7}")
        for r in ops:
            print(f"    {r['fires_pct']:>7}{r['precision']:>11}{r['recall']:>9}{r['lift']:>7}")

        res[label] = {
            "within_auc_shape": a_full, "within_auc_baseline": a_base,
            "within_gain": [d.delta, d.lo, d.hi, d.n_ahead, d.n_part],
            "external_auc_shape": common.auc(ye, se),
            "external_auc_baseline": common.auc(ye, sbe),
            "external_gain": [de.delta, de.lo, de.hi, de.n_ahead, de.n_part],
            "per_participant_external": per, "operating_points": ops,
        }

        if label == "y_low":
            os.makedirs(os.path.join(HERE, "model"), exist_ok=True)
            n = export_trees(m, f, os.path.join(HERE, "model", "fall_consequence_v1.json"),
                             os.path.join(HERE, "model", "fall_consequence_meta_v1.json"),
                             {"features": f, "horizon_min": H, "label": label,
                              "onset_rule": "fall >= 25 mg/dL within 30 min from above 70 mg/dL, "
                                            "60 min refractory",
                              "forward_window_min": 120,
                              "trained_on": "OpenAPS Data Commons",
                              "n_train_rows": int(len(com)),
                              "n_train_participants": int(com.pid.nunique()),
                              "external_auc_boost_cohort": common.auc(ye, se),
                              "base_rate_train": float(com[label].mean())})
            print(f"  exported {n} trees to model/fall_consequence_v1.json")

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "c2_build.json"), "w") as fh:
        json.dump(res, fh, indent=2)
    print(f"\nwrote {OUT}/c2_build.json")


if __name__ == "__main__":
    main()
