#!/usr/bin/env python3
"""How the clock should be encoded in the hypoglycaemia risk model.

The shipped model carries `hour` as a raw integer. A tree can only split that at a threshold, so
23:00 and 00:00 sit twenty-three units apart in a quantity whose true distance is one, and any
overnight pattern has to be reassembled from two separate splits at the ends of the range. The
obvious alternative is the circular encoding, sin and cos of the hour angle, which places
midnight adjacent to 23:00 and lets a single split separate night from day.

Four arms, differing only in how the clock is represented and otherwise identical:

  raw     the shipped encoding, `hour` as an integer
  circ    `hour` replaced by tod_sin and tod_cos
  both    `hour` kept and the circular pair added
  none    the clock removed, which prices what it buys at all

Participant is the grouping unit for the folds and the resampling unit for the intervals, so a
difference here is a difference that survives being tested on people the model never saw.
"""
import json
import os
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import c1_hypo_scale as c1

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
N_BOOT = 4000


def arms(feats):
    base = [f for f in feats if f != "hour"]
    return {
        "raw": list(feats),
        "circ": base + ["tod_sin", "tod_cos"],
        "both": list(feats) + ["tod_sin", "tod_cos"],
        "none": base,
    }


def main():
    res = {}
    for tag, path in (("4h", "c1_table_4h.parquet"), ("1h", "c1_table_1h.parquet")):
        df = pd.read_parquet(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "cache", path))
        ang = 2 * np.pi * df["hour"].to_numpy() / 24.0
        df["tod_sin"], df["tod_cos"] = np.sin(ang), np.cos(ang)
        feats = c1.feature_names()
        A = arms(feats)

        print(f"\n=== {tag} horizon: {len(df):,} rows, {df.user_id.nunique()} participants, "
              f"base rate {df.y.mean():.3f} ===", flush=True)

        pid, y = [], []
        scores = {k: [] for k in A}
        for fold in range(5):
            te = df[df.fold == fold]
            tr = df[df.fold != fold]
            pid.append(te.user_id.to_numpy())
            y.append(te.y.to_numpy())
            for name, f in A.items():
                m = lgb.LGBMClassifier(random_state=0, **c1.PARAMS)
                m.fit(tr[f], tr["y"].to_numpy())
                scores[name].append(m.predict_proba(te[f])[:, 1])
            print(f"  fold {fold} done", flush=True)

        pid = np.concatenate(pid); y = np.concatenate(y)
        s = {k: np.concatenate(v) for k, v in scores.items()}
        aucs = {k: common.auc(y, v) for k, v in s.items()}
        print(f"  AUC  " + "  ".join(f"{k} {v:.4f}" for k, v in aucs.items()))

        cmp = {}
        for a, b in [("circ", "raw"), ("both", "raw"), ("raw", "none"), ("circ", "none")]:
            d = common.paired_participant_bootstrap(pid, y, s[a], s[b], n_boot=N_BOOT)
            mean, lo, hi = d.delta, d.lo, d.hi
            verdict = "distinguishable" if (lo > 0 or hi < 0) else "UNPROVEN"
            cmp[f"{a}_vs_{b}"] = [mean, lo, hi, verdict, d.n_ahead, d.n_part]
            print(f"  {a:>5} vs {b:<5} {mean:+.4f} ({lo:+.4f} to {hi:+.4f})  {verdict}"
                  f"   better on {d.n_ahead}/{d.n_part}")
        res[tag] = {"auc": aucs, "comparisons": cmp,
                    "n_rows": int(len(df)), "n_participants": int(df.user_id.nunique()),
                    "base_rate": float(df.y.mean())}

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "c5_clock_encoding.json"), "w") as f:
        json.dump(res, f, indent=2)
    print(f"\nwrote {OUT}/c5_clock_encoding.json")


if __name__ == "__main__":
    main()
