"""Candidate 1b: does a hypo model trained on the Commons work on Boost's own users?

The learning curve in c1_hypo_scale is measured inside one population. It says what a
larger training set is worth when the people being scored come from the same place as the
people the model was fitted on, and that is not the question a deployment faces. Boost's
shipped model was fitted on its own 28 users; the Commons offers 183 of somebody else's,
running different loops on different pumps in a different decade.

So the same feature vector is built for the 16 Boost participants the registry holds a clock
offset for, and each row is scored three ways: by a model fitted on all 183 Commons
participants, by a model fitted on Boost itself with participants held out, and by the two
baselines the controller already holds. The gap between the first two is what not having
the deployment cohort costs.

Boost's telemetry names some fields differently and the map in boost_cohort keeps the
vector identical; the two lag features the Commons carries and Boost does not are absent
from both arms, so neither is advantaged.
"""

from __future__ import annotations

import argparse
import json
import os

import lightgbm as lgb
import numpy as np
import pandas as pd

import common
from boost_cohort import FIELD_MAP, tz_offsets
from c1_hypo_scale import (HORIZONS, LAG_FEATURES, LOW_MGDL, N_LAGS, PARAMS, STATIC_FEATURES,
                           THIN, build_table, feature_names)


def boost_table(tag: str, horizon_slots: int) -> pd.DataFrame:
    """The C1 feature table, built from Boost's record on local time."""

    def build():
        offs = tz_offsets()
        sel = ", ".join(f"{v} as {k}" for k, v in FIELD_MAP.items())
        df = common.query(
            "select user_id, ts_epoch, cgm_mgdl, iob_bolusiob, " + sel +
            " from public.boost_decisions where cgm_mgdl between 39 and 401 "
            "order by user_id, ts_epoch"
        )
        df = df[df["user_id"].isin(offs)].copy()
        sec = df["ts_epoch"].to_numpy(dtype="float64")
        assert np.nanmax(sec) > 1.6e9, f"ts_epoch looks wrong: {np.nanmax(sec)}"
        local = sec + df["user_id"].map(offs).to_numpy() * 3600.0
        df["slot"] = (local // common.GRID_S).astype("int64")
        df["hour"] = np.floor((local % 86400) / 3600.0)
        df = df.drop_duplicates(["user_id", "slot"], keep="last")
        for c in STATIC_FEATURES:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")

        cols = sorted(set(STATIC_FEATURES) | set(LAG_FEATURES))
        out = []
        for pid, g in df.groupby("user_id", sort=False):
            s = g["slot"].to_numpy()
            s0 = int(s.min())
            n = int(s.max() - s0 + 1)
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
                np.isfinite(cgm) & np.isfinite(fut_min) & (cov >= 0.8)
                & (np.arange(n) % THIN == 0)
                & np.isfinite(np.concatenate([np.full(N_LAGS, np.nan, np.float32),
                                              cgm[:-N_LAGS]]))
            )
            if keep.sum() == 0:
                continue
            k = np.flatnonzero(keep)
            d = {"user_id": f"boost:{pid}", "slot": (k + s0).astype("int64"),
                 "y": (fut_min[k] < LOW_MGDL).astype("int8")}
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

    return common.cached(f"c1b_boost_table_{tag}", build)


def fit(tr, feats):
    m = lgb.LGBMClassifier(random_state=0, **{**PARAMS, "n_jobs": 4})
    m.fit(tr[feats], tr["y"].to_numpy())
    return m


def within(df, feats, k=5):
    s = np.full(len(df), np.nan)
    folds = df["fold"].to_numpy()
    for f in range(k):
        tr, te = folds != f, folds == f
        if te.sum() == 0 or df.loc[tr, "y"].nunique() < 2:
            continue
        s[te] = fit(df[tr], feats).predict_proba(df.loc[te, feats])[:, 1]
    return s


PAIRS = [
    ("external_full", "external_clock", "external_full_over_clock"),
    ("within_full", "within_clock", "within_full_over_clock"),
    ("external_full", "within_full", "transfer_cost_full"),
    ("external_clock", "within_clock", "transfer_cost_clock"),
    ("external_full", "external_loop", "external_full_over_loopstate"),
    ("external_clock", "eventualbg", "clock_vs_eventualbg"),
]


def run(tag: str, horizon_slots: int, out: dict):
    cm = build_table(tag, horizon_slots)
    bo = boost_table(tag, horizon_slots)
    feats = feature_names()
    arms = {"full": feats, "clock": ["cgm_mgdl", "hour"],
            "loop": ["cgm_mgdl", "hour", "iob_iob", "sug_eventualbg"]}
    print(f"  {tag}: Commons {len(cm):,} rows / {cm.user_id.nunique()} participants, "
          f"Boost {len(bo):,} / {bo.user_id.nunique()}; base rate Commons "
          f"{cm.y.mean():.3f}, Boost {bo.y.mean():.3f}", flush=True)

    pid = bo["user_id"].to_numpy()
    y = bo["y"].to_numpy().astype(int)
    S = {"eventualbg": -bo["sug_eventualbg"].to_numpy()}
    for name, f in arms.items():
        S[f"external_{name}"] = fit(cm, f).predict_proba(bo[f])[:, 1]
        S[f"within_{name}"] = within(bo, f)

    res = {"n": int(len(bo)), "n_participants": int(bo.user_id.nunique()),
           "base_rate": float(y.mean()), "auc": {}, "paired": {}}
    for n, sc in S.items():
        a, lo, hi = common.participant_bootstrap_auc(pid, y, sc)
        res["auc"][n] = [a, lo, hi]
        print(f"  {tag} {n:16s} AUC {a:.4f} [{lo:.4f}, {hi:.4f}]", flush=True)
    for a, b, nm in PAIRS:
        r = common.paired_participant_bootstrap(pid, y, S[a], S[b])
        res["paired"][nm] = dict(delta=r.delta, lo=r.lo, hi=r.hi, n_part=r.n_part,
                                 n_ahead=r.n_ahead, verdict=r.verdict)
        print(f"  {tag} {nm:28s} {r}", flush=True)
    out[tag] = res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizons", default="1h,4h")
    ap.parse_args()
    out = {}
    for tag in ("1h", "4h"):
        run(tag, HORIZONS[tag], out)
    with open(os.path.join(common.OUT, "c1b_hypo_transfer.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("written c1b_hypo_transfer.json")
