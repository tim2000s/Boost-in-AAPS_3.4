"""Candidate 1: does a hypo-risk model get better with 183 participants than with 28?

Boost ships a hypo-risk model trained on its own 28-user cohort. The OpenAPS Data Commons
holds the same kind of record, a loop's own decision state joined to the glucose that
followed, for 183 participants. That is the first time the question can be asked at all,
because until the Commons was loaded there was no second cohort of controller records to
grow the training set with.

Target: the shipped one, whether glucose falls below 70 mg/dL at any point in the next four
hours. A sixty-minute variant is run alongside because the four-hour horizon is a risk
score rather than a dose decision, and the decision a hypo score gates is open now.

Design: participants are assigned to five folds by a hash of their id, so every arm sees
the same split. Within a fold's training participants, random subsets of 7, 14, 28, 56 and
112 are drawn, three seeds each, and each fitted model scores the identical held-out rows.
The full pool is fitted with the same three seeds, so a sized arm is never compared against
a differently ensembled opponent. Comparisons are paired at the row level and the interval
comes from resampling participants.
"""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor

import lightgbm as lgb
import numpy as np
import pandas as pd

import common

LAG_FEATURES = ["cgm_mgdl", "iob_iob", "iob_activity", "sug_eventualbg"]
STATIC_FEATURES = [
    "cgm_mgdl",
    "hour",
    "iob_iob",
    "iob_activity",
    "iob_basaliob",
    "iob_bolusiob",
    "sug_cob",
    "sug_eventualbg",
    "sug_insulinreq",
    "sug_isf",
    "sug_current_target",
]
N_LAGS = 5
THIN = 12  # keep one row an hour; rows inside a 4 h window are near-duplicates

HORIZONS = {"4h": 48, "1h": 12}
LOW_MGDL = 70.0


def feature_names() -> list[str]:
    names = list(STATIC_FEATURES)
    for c in LAG_FEATURES:
        names += [f"{c}_lag{k}" for k in range(1, N_LAGS + 1)]
    return names


def build_table(tag: str, horizon_slots: int) -> pd.DataFrame:
    def build():
        df = common.load_oref_commons()
        cols = sorted(set(STATIC_FEATURES) | set(LAG_FEATURES))
        out = []
        for pid, g in df.groupby("user_id", sort=False):
            s = g["slot"].to_numpy()
            s0 = int(s.min())
            n = int(s.max() - s0 + 1)
            if n > 4_000_000:
                continue
            idx = (s - s0).astype(np.int64)
            arrs = {}
            for c in cols:
                a = np.full(n, np.nan, dtype=np.float32)
                a[idx] = g[c].to_numpy(dtype=np.float32)
                arrs[c] = a
            cgm = arrs["cgm_mgdl"]
            fut_min = common.forward_window_min(cgm, 1, horizon_slots)
            cov = common.coverage(cgm, 1, horizon_slots)
            keep = (
                np.isfinite(cgm)
                & np.isfinite(fut_min)
                & (cov >= 0.8)
                & (np.arange(n) % THIN == 0)
                & np.isfinite(np.concatenate([np.full(N_LAGS, np.nan, np.float32),
                                              cgm[:-N_LAGS]]))
            )
            if keep.sum() == 0:
                continue
            k = np.flatnonzero(keep)
            d = {
                "user_id": pid,
                "slot": (k + s0).astype("int64"),
                "y": (fut_min[k] < LOW_MGDL).astype("int8"),
            }
            for c in STATIC_FEATURES:
                d[c] = arrs[c][k]
            for c in LAG_FEATURES:
                a = arrs[c]
                for j in range(1, N_LAGS + 1):
                    lag = np.full(n, np.nan, dtype=np.float32)
                    lag[j:] = a[:-j]
                    d[f"{c}_lag{j}"] = lag[k]
            out.append(pd.DataFrame(d))
        res = pd.concat(out, ignore_index=True)
        res["fold"] = [common.stable_fold(p, 5) for p in res["user_id"]]
        return res

    return common.cached(f"c1_table_{tag}", build)


PARAMS = dict(
    objective="binary",
    n_estimators=150,
    learning_rate=0.05,
    num_leaves=31,
    min_child_samples=200,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.8,
    verbose=-1,
    n_jobs=1,
    force_col_wise=True,
)


def run(tag: str, horizon_slots: int, out: dict, workers: int):
    df = build_table(tag, horizon_slots)
    feats = feature_names()
    base_feats = ["cgm_mgdl", "hour"]
    loop_feats = ["cgm_mgdl", "hour", "iob_iob", "sug_eventualbg"]
    print(f"  table: {len(df):,} rows, {df.user_id.nunique()} participants, "
          f"base rate {df.y.mean():.3f}", flush=True)

    sizes = [7, 14, 28, 56, 112]
    n_seeds = 3
    test_pid, test_y = [], []
    # scores[(arm, seed)] -> list of per-fold prediction arrays
    scores: dict[tuple[str, int], list] = {}

    for fold in range(5):
        te = df[df["fold"] == fold]
        tr_pool = df[df["fold"] != fold]
        tr_parts = tr_pool["user_id"].unique()
        test_pid.append(te["user_id"].to_numpy())
        test_y.append(te["y"].to_numpy())
        Xte = te[feats]

        jobs, labels = [], []
        for s in sizes:
            if s > len(tr_parts):
                continue
            for seed in range(n_seeds):
                rng = np.random.default_rng(1000 * fold + 17 * s + seed)
                pick = set(rng.choice(tr_parts, size=s, replace=False))
                sub = tr_pool[tr_pool["user_id"].isin(pick)]
                jobs.append((sub, Xte, feats, seed))
                labels.append((f"n{s}", seed))
        # the full training pool is fitted with the same number of seeds so the sized arms
        # are never compared against a differently-ensembled opponent
        for seed in range(n_seeds):
            jobs.append((tr_pool, Xte, feats, seed))
            labels.append(("nall", seed))
        jobs.append((tr_pool, Xte, base_feats, 0))
        labels.append(("base_clock", 0))
        jobs.append((tr_pool, Xte, loop_feats, 0))
        labels.append(("base_loop", 0))

        def fit_score(job):
            sub, Xt, f, seed = job
            m = lgb.LGBMClassifier(random_state=seed, **PARAMS)
            m.fit(sub[f], sub["y"].to_numpy())
            return m.predict_proba(Xt[f])[:, 1]

        with ThreadPoolExecutor(max_workers=workers) as ex:
            preds = list(ex.map(fit_score, jobs))

        for lab, p in zip(labels, preds):
            scores.setdefault(lab, []).append(p)
        scores.setdefault(("eventualbg", 0), []).append(-te["sug_eventualbg"].to_numpy())
        print(f"  fold {fold}: {len(te):,} test rows, "
              f"{te['user_id'].nunique()} participants", flush=True)

    pid = np.concatenate(test_pid)
    y = np.concatenate(test_y).astype(int)
    S = {k: np.concatenate(v) for k, v in scores.items()}

    res = {"n_rows": int(len(y)), "n_participants": int(df.user_id.nunique()),
           "base_rate": float(y.mean()), "auc": {}, "auc_by_seed": {}, "paired": {}}
    arms = sorted({a for a, _ in S})
    for arm in arms:
        per_seed = [common.auc(y, S[(arm, sd)]) for (a, sd) in S if a == arm]
        res["auc_by_seed"][arm] = [float(v) for v in per_seed]
        a, lo, hi = common.participant_bootstrap_auc(pid, y, S[(arm, 0)])
        res["auc"][arm] = [a, lo, hi]
        spread = (f" seeds {min(per_seed):.4f}-{max(per_seed):.4f}"
                  if len(per_seed) > 1 else "")
        print(f"  {tag} {arm:12s} AUC {a:.4f} [{lo:.4f}, {hi:.4f}]{spread}", flush=True)

    def pair(a, b, name):
        if (a, 0) not in S or (b, 0) not in S:
            return
        r = common.paired_participant_bootstrap(pid, y, S[(a, 0)], S[(b, 0)])
        res["paired"][name] = dict(delta=r.delta, lo=r.lo, hi=r.hi,
                                   n_part=r.n_part, n_ahead=r.n_ahead,
                                   verdict=r.verdict)
        print(f"  {tag} {name:28s} {r}", flush=True)

    pair("nall", "n28", "scale_183_vs_28")
    pair("n28", "n7", "scale_28_vs_7")
    pair("nall", "n112", "scale_183_vs_112")
    pair("n112", "n28", "scale_112_vs_28")
    pair("nall", "base_clock", "full_vs_clock")
    pair("nall", "base_loop", "full_vs_loopstate")
    pair("base_loop", "eventualbg", "loopstate_vs_eventualbg")
    pair("base_clock", "eventualbg", "clock_vs_eventualbg")
    out[tag] = res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--horizons", default="4h,1h")
    a = ap.parse_args()
    out = {}
    for tag in a.horizons.split(","):
        print(f"== horizon {tag} ==", flush=True)
        run(tag, HORIZONS[tag], out, a.workers)
    with open(os.path.join(common.OUT, "c1_hypo_scale.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("written", os.path.join(common.OUT, "c1_hypo_scale.json"))
