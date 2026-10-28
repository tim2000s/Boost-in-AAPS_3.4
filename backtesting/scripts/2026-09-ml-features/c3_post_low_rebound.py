"""Candidate 3: at the moment somebody comes out of a low, what happens next?

Boost's post-rescue rebound guard scales the final microbolus for a fixed window after a
low, as a function of glucose alone. The audit that put it in place priced its benefit at
34 per cent of removed insulin sitting before a low, and its cost at 9 per cent of genuine
meals blunted, median 0.80 U. Both halves of that trade are decided by what the next three
hours hold: another low, in which case the guard pays, or a genuine rebound that wanted
insulin, in which case it costs.

If the two can be separated at the moment of recovery, the guard could be conditioned
rather than fixed, which is the only route to recovering the meals it currently blunts
without loosening the protection that motivated it. Boost's own record holds a few hundred
of these windows. The corpora hold tens of thousands, which is what makes the question
answerable.

Anchors: the first reading back above 80 mg/dL after glucose has been below 70. Nothing
after the anchor is used as a feature.

Labels within three hours of recovery: whether glucose exceeds 180 mg/dL, and whether it
falls below 70 again.

The matched baseline is glucose at recovery plus the clock. Everything the episode itself
contributes, its depth, its length and the slope coming out of it, has to beat that.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
from multiprocessing import Pool

import lightgbm as lgb
import numpy as np
import pandas as pd
import psycopg2

import common
from c2_fall_consequence import _series

LOW_ENTER = 70.0
RECOVER_AT = 80.0
FWD_MIN = 180
HIGH_THRESHOLD = 180.0
RELOW_THRESHOLD = 70.0
MAX_EPISODE_MIN = 180

EPISODE = ("nadir", "depth", "duration_min", "recovery_slope", "recovery_slope_30",
           "pre_low_slope", "bg_recover", "time_below_54_min", "n_readings")
BASE = ("bg_recover", "tod_sin", "tod_cos")
LOOP = ("iob_iob", "iob_activity", "iob_basaliob", "sug_cob", "sug_insulinreq",
        "sug_isf", "sug_current_target")


def _episodes(ts, bg, meta, hours=None):
    """Every recovery out of a low, with what the episode itself looked like."""
    rows = []
    n = len(ts)
    i = 1
    while i < n - 40:
        if bg[i] < LOW_ENTER and bg[i - 1] >= LOW_ENTER:
            start = i
            j = i
            while j < n - 1 and bg[j] < RECOVER_AT and (ts[j] - ts[start]) < MAX_EPISODE_MIN * 60:
                j += 1
            if bg[j] < RECOVER_AT or (ts[j] - ts[start]) > MAX_EPISODE_MIN * 60:
                i = j + 1
                continue
            seg = bg[start:j + 1]
            tseg = ts[start:j + 1]
            t0 = ts[j]
            a = bisect.bisect_right(ts, t0)
            b = bisect.bisect_right(ts, t0 + FWD_MIN * 60)
            fwd = bg[a:b]
            if len(fwd) < 24:               # the forward window must be genuinely covered
                i = j + 1
                continue
            p = bisect.bisect_left(ts, ts[start] - 30 * 60)
            pre = ((bg[start] - bg[p]) / max((ts[start] - ts[p]) / 60.0, 1.0)
                   if p < start else 0.0)
            k30 = bisect.bisect_left(tseg, t0 - 30 * 60)
            r = dict(meta)
            r["t0"] = float(t0)
            r["nadir"] = float(seg.min())
            r["depth"] = float(LOW_ENTER - seg.min())
            r["duration_min"] = float((t0 - ts[start]) / 60.0)
            r["recovery_slope"] = float((bg[j] - bg[j - 1]) /
                                        max((ts[j] - ts[j - 1]) / 60.0, 1.0))
            r["recovery_slope_30"] = float((bg[j] - tseg_val(seg, k30)) /
                                           max((t0 - tseg[k30]) / 60.0, 1.0))
            r["pre_low_slope"] = pre
            r["bg_recover"] = float(bg[j])
            r["time_below_54_min"] = float(np.sum(seg < 54) * 5.0)
            r["n_readings"] = float(len(seg))
            r["y_high"] = int(fwd.max() > HIGH_THRESHOLD)
            r["y_relow"] = int(fwd.min() < RELOW_THRESHOLD)
            r["fwd_max"] = float(fwd.max())
            r["fwd_min"] = float(fwd.min())
            hour = hours[j] if hours is not None else (t0 % 86400) / 3600.0
            r["hour"] = float(hour)
            r["tod_sin"] = float(np.sin(2 * np.pi * hour / 24))
            r["tod_cos"] = float(np.cos(2 * np.pi * hour / 24))
            r["idx"] = int(j)
            rows.append(r)
            i = j + 1
            continue
        i += 1
    return rows


def tseg_val(seg, k):
    return float(seg[min(max(k, 0), len(seg) - 1)])


def _one_subject(arg):
    subject, study = arg
    conn = psycopg2.connect(common.DSN)
    try:
        with conn.cursor() as cur:
            ts, bg = _series(cur, subject)
    finally:
        conn.close()
    if ts is None or len(ts) < 500:
        return None
    rows = _episodes(ts, bg, dict(pid=subject, study=study))
    return pd.DataFrame(rows) if rows else None


def studies_episodes(workers: int) -> pd.DataFrame:
    def build():
        subs = common.query(
            "select subject_id, study_name from studies.subject order by subject_id"
        )
        jobs = list(subs.itertuples(index=False, name=None))
        out = []
        with Pool(workers) as p:
            for k, r in enumerate(p.imap_unordered(_one_subject, jobs, chunksize=4)):
                if r is not None:
                    out.append(r)
                if (k + 1) % 300 == 0:
                    print(f"    {k + 1}/{len(jobs)} subjects", flush=True)
        return pd.concat(out, ignore_index=True)

    return common.cached("c3_studies_episodes", build)


def commons_episodes() -> pd.DataFrame:
    def build():
        df = common.load_oref_commons()
        loop_cols = list(LOOP) + ["sug_eventualbg"]
        out = []
        for pid, g in df.groupby("user_id", sort=False):
            g = g.sort_values("slot")
            ts = (g["slot"].to_numpy() * common.GRID_S).astype(float)
            bg = g["cgm_mgdl"].to_numpy(dtype=float)
            if len(ts) < 500:
                continue
            hours = g["hour"].to_numpy(dtype=float)
            rows = _episodes(ts, bg, dict(pid=pid, study="commons"), hours=hours)
            if not rows:
                continue
            r = pd.DataFrame(rows)
            pos = r["idx"].to_numpy()
            for c in loop_cols:
                r[c] = g[c].to_numpy(dtype=float)[pos]
            out.append(r)
        return pd.concat(out, ignore_index=True)

    return common.cached("c3_commons_episodes", build)


PARAMS = dict(objective="binary", n_estimators=300, learning_rate=0.05, num_leaves=31,
              min_child_samples=60, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, verbose=-1, n_jobs=7, force_col_wise=True)


def oos_scores(df, feats, target, k=5):
    s = np.full(len(df), np.nan)
    folds = df["fold"].to_numpy()
    for f in range(k):
        tr, te = folds != f, folds == f
        if df.loc[tr, target].nunique() < 2 or te.sum() == 0:
            continue
        m = lgb.LGBMClassifier(random_state=0, **PARAMS)
        m.fit(df.loc[tr, feats], df.loc[tr, target])
        s[te] = m.predict_proba(df.loc[te, feats])[:, 1]
    return s


PAIRS = [
    ("episode", "clock", "episode_vs_clock"),
    ("loop", "clock", "loop_vs_clock"),
    ("loop", "episode", "loop_vs_episode"),
    ("clock", "bg_only", "clock_vs_bgonly"),
    ("clock", "eventualbg", "clock_vs_eventualbg"),
]


def price(df, label, target, out):
    arms = {
        "bg_only": ["bg_recover"],
        "clock": list(BASE),
        "episode": list(BASE) + [c for c in EPISODE if c not in BASE],
    }
    if "iob_iob" in df.columns:
        arms["loop"] = arms["episode"] + list(LOOP)
        arms["eventualbg"] = "sug_eventualbg"
    pid = df["pid"].to_numpy()
    y = df[target].to_numpy()
    S = {}
    for n, f in arms.items():
        S[n] = df[f].to_numpy() if isinstance(f, str) else oos_scores(df, f, target)
    res = {"n": int(len(df)), "n_participants": int(df.pid.nunique()),
           "base_rate": float(y.mean()), "auc": {}, "paired": {}}
    for n, s in S.items():
        a, lo, hi = common.participant_bootstrap_auc(pid, y, s)
        res["auc"][n] = [a, lo, hi]
        print(f"    {label}/{target} {n:12s} AUC {a:.4f} [{lo:.4f}, {hi:.4f}]", flush=True)
    for a, b, nm in PAIRS:
        if a in S and b in S:
            r = common.paired_participant_bootstrap(pid, y, S[a], S[b])
            res["paired"][nm] = dict(delta=r.delta, lo=r.lo, hi=r.hi, n_part=r.n_part,
                                     n_ahead=r.n_ahead, verdict=r.verdict)
            print(f"    {label}/{target} {nm:24s} {r}", flush=True)
    out.setdefault(label, {})[target] = res


if __name__ == "__main__":
    from boost_cohort import boost_low_recoveries

    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=7)
    a = ap.parse_args()
    out = {}

    print("== OpenAPS Data Commons ==", flush=True)
    cm = commons_episodes()
    cm["fold"] = [common.stable_fold(p, 5) for p in cm["pid"]]
    cm = cm[cm["sug_eventualbg"].between(20, 600)]
    print(f"  {len(cm):,} recoveries, {cm.pid.nunique()} participants", flush=True)
    for t in ("y_high", "y_relow"):
        price(cm, "commons", t, out)

    print("== Boost cohort ==", flush=True)
    bo = boost_low_recoveries()
    bo["fold"] = [common.stable_fold(p, 5) for p in bo["pid"]]
    bo = bo[bo["sug_eventualbg"].between(20, 600)]
    print(f"  {len(bo):,} recoveries, {bo.pid.nunique()} participants", flush=True)
    for t in ("y_high", "y_relow"):
        price(bo, "boost", t, out)

    print("== seven research corpora ==", flush=True)
    st = studies_episodes(a.workers)
    st["fold"] = [common.stable_fold(p, 5) for p in st["pid"]]
    print(f"  {len(st):,} recoveries, {st.pid.nunique()} participants", flush=True)
    for t in ("y_high", "y_relow"):
        price(st, "studies", t, out)

    with open(os.path.join(common.OUT, "c3_post_low_rebound.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("written c3_post_low_rebound.json")
