#!/usr/bin/env python3
"""Detection as a controller actually runs it: continuously, counted in episodes.

The 0.843 reported for detection is a ranking score on a curated event set, meal onsets against
undeclared rises of at least 25 mg/dL. A controller does not get that set. It gets a reading every
five minutes and must decide each time whether food has arrived, and it is charged for every
firing. The gap between those two framings is large, and this measures it on the corpus where
there is ground truth and enough participants to be worth believing.

Both detectors run in the same streaming form on the same cycles.

The shadow is the shipped rule, reproduced exactly from the source: deltas are computed over the
oref windows, 2.5 to 7.5 minutes for delta, 2.5 to 17.5 for shortAvgDelta and 17.5 to 42.5 for
longAvgDelta, each candidate normalised to a per-five-minute rate; it fires when
shortAvgDelta - longAvgDelta > 2.0 and the trace is rising. Its pre-confirm condition cannot be
reproduced without the Boost engine state, and omitting it can only make the shadow fire more
often; collapsing firings into episodes absorbs most of that, since the suppressed firings are the
repeat ones during a meal already detected.

The model is fitted on the same features in the same streaming form, on training participants, and
scored on held-out ones. Fitting in the form it is served in is the point: the earlier comparison
trained on windows anchored at a detected onset and then streamed them from arbitrary anchors,
which handicapped the model for a reason that had nothing to do with the signal.

A firing episode is credited when it begins within 15 minutes before or 45 minutes after an
announced onset. Everything else is a false alarm.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, secondary analysis.
"""

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
import psycopg2
from sklearn.model_selection import GroupKFold

import lightgbm as lgb
from size_readability import LGB, SEED

GRID_S = 300
ACCEL_THRESHOLD = 2.0
EPISODE_GAP_S = 45 * 60
CREDIT_BEFORE_S = 15 * 60
CREDIT_AFTER_S = 45 * 60
MEAL_WINDOW_S = 30 * 60      # a cycle is positive if an onset began within this many seconds
BUFFER_S = 90 * 60           # cycles this far past an onset are excluded from the negative class
FEATURES = ["bg", "delta", "short_avg_delta", "long_avg_delta", "accel",
            "rise10", "rise20", "rise30", "curv", "tod_sin", "tod_cos"]


def grid_of(ts, bg):
    """Put a participant's trace on a regular five-minute grid, NaN across gaps."""
    if len(ts) < 50:
        return None, None
    t0, t1 = ts[0], ts[-1]
    grid = np.arange(t0, t1 + GRID_S, GRID_S)
    idx = np.searchsorted(ts, grid)
    idx = np.clip(idx, 0, len(ts) - 1)
    prev = np.clip(idx - 1, 0, len(ts) - 1)
    pick = np.where(np.abs(ts[idx] - grid) <= np.abs(ts[prev] - grid), idx, prev)
    vals = bg[pick].astype(np.float64)
    vals[np.abs(ts[pick] - grid) > GRID_S / 2] = np.nan
    return grid, vals


def features_of(grid, v):
    """Vectorised, and the deltas match the oref windows exactly."""
    n = len(v)

    def lag(k):
        out = np.full(n, np.nan)
        if k < n:
            out[k:] = v[:-k]
        return out

    delta = v - lag(1)
    short = np.nanmean(np.vstack([(v - lag(j)) / j for j in (1, 2, 3)]), axis=0)
    long_ = np.nanmean(np.vstack([(v - lag(j)) / j for j in (4, 5, 6, 7, 8)]), axis=0)
    accel = short - long_
    hour = (grid % 86400) / 3600.0
    d = dict(bg=v, delta=delta, short_avg_delta=short, long_avg_delta=long_, accel=accel,
             rise10=v - lag(2), rise20=v - lag(4), rise30=v - lag(6),
             curv=delta - (lag(1) - lag(2)),
             tod_sin=np.sin(2 * np.pi * hour / 24), tod_cos=np.cos(2 * np.pi * hour / 24))
    X = np.vstack([d[f] for f in FEATURES]).T
    rising = (delta > 0) | (short > 0)
    shadow = (accel > ACCEL_THRESHOLD) & rising
    return X, np.nan_to_num(shadow, nan=False).astype(bool)


def episodes(times, gap=EPISODE_GAP_S):
    if len(times) == 0:
        return np.empty(0)
    t = np.sort(np.asarray(times, dtype=float))
    keep = [t[0]]
    for a, b in zip(t[:-1], t[1:]):
        if b - a > gap:
            keep.append(b)
    return np.asarray(keep)


def credit(ep, onsets):
    if len(ep) == 0:
        return 0.0, 0
    if len(onsets) == 0:
        return 0.0, len(ep)
    caught, fa = set(), 0
    for e in ep:
        k = np.where((onsets >= e - CREDIT_AFTER_S) & (onsets <= e + CREDIT_BEFORE_S))[0]
        if len(k):
            caught.add(int(k[0]))
        else:
            fa += 1
    return len(caught) / len(onsets), fa


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--data", default=os.path.join(here, "out"))
    ap.add_argument("--subjects", type=int, default=200)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    meals = pd.read_parquet(os.path.join(args.data, "meals_Loop.parquet"),
                            columns=["subject_id", "t0"])
    subs = sorted(meals.subject_id.unique())[: args.subjects]
    onsets_by = {s: np.sort(g.t0.to_numpy(float)) for s, g in
                 meals[meals.subject_id.isin(subs)].groupby("subject_id")}
    print(f"{len(subs)} participants, {sum(len(v) for v in onsets_by.values()):,} meal onsets",
          flush=True)

    conn = psycopg2.connect("dbname=oref")
    conn.autocommit = True
    per = {}
    with conn.cursor() as cur:
        for i, s in enumerate(subs, 1):
            cur.execute("select extract(epoch from ts_local), cgm_mgdl from studies.cgm "
                        "where subject_id=%s order by ts_local", (s,))
            rows = cur.fetchall()
            if len(rows) < 500:
                continue
            a = np.asarray(rows, dtype=float)
            grid, v = grid_of(a[:, 0], a[:, 1])
            if grid is None:
                continue
            X, shadow = features_of(grid, v)
            ons = onsets_by.get(s, np.empty(0))
            since = np.full(len(grid), np.inf)
            if len(ons):
                j = np.searchsorted(ons, grid, side="right") - 1
                ok = j >= 0
                since[ok] = grid[ok] - ons[j[ok]]
            y = (since <= MEAL_WINDOW_S).astype(np.int8)
            usable = np.isfinite(X).all(axis=1)
            per[s] = dict(grid=grid, X=X.astype(np.float32), shadow=shadow, y=y,
                          since=since, usable=usable, onsets=ons,
                          days=(grid[-1] - grid[0]) / 86400.0)
            if i % 50 == 0:
                print(f"  {i}/{len(subs)} participants prepared", flush=True)
    print(f"{len(per)} participants usable\n", flush=True)

    keys = sorted(per)
    g = np.arange(len(keys))
    out = {"shadow": [], "model": []}

    # the shadow needs no fitting; score it on everybody
    s_sens, s_fa, s_days = [], [], []
    for k in keys:
        p = per[k]
        ep = episodes(p["grid"][p["shadow"] & p["usable"]])
        sens, fa = credit(ep, p["onsets"])
        s_sens.append(sens)
        s_fa.append(fa / p["days"])
        s_days.append(p["days"])
    out["shadow"] = dict(sensitivity=float(np.mean(s_sens)),
                         sens_lo=float(np.percentile(s_sens, 2.5)),
                         sens_hi=float(np.percentile(s_sens, 97.5)),
                         fa_per_day=float(np.mean(s_fa)),
                         fa_lo=float(np.percentile(s_fa, 2.5)),
                         fa_hi=float(np.percentile(s_fa, 97.5)),
                         participants=len(keys), days=float(np.sum(s_days)))
    print(f"shadow: catches {np.mean(s_sens):.1%} of meals "
          f"[{np.percentile(s_sens,2.5):.1%} to {np.percentile(s_sens,97.5):.1%} across participants], "
          f"{np.mean(s_fa):.2f} false alarms/day\n", flush=True)

    # the model, fitted in the form it is served
    scores = {k: None for k in keys}
    for tr, te in GroupKFold(n_splits=args.folds).split(g, g, g):
        Xtr, ytr = [], []
        for i in tr:
            p = per[keys[i]]
            m = p["usable"] & ((p["y"] == 1) | (p["since"] > BUFFER_S))
            Xtr.append(p["X"][m])
            ytr.append(p["y"][m])
        Xtr = np.concatenate(Xtr)
        ytr = np.concatenate(ytr)
        # negatives dominate; subsample them for fitting only
        pos = np.where(ytr == 1)[0]
        neg = np.where(ytr == 0)[0]
        rng = np.random.default_rng(SEED)
        neg = rng.choice(neg, min(len(neg), 8 * len(pos)), replace=False)
        sel = np.concatenate([pos, neg])
        mdl = lgb.LGBMClassifier(random_state=SEED, **LGB)
        mdl.fit(Xtr[sel], ytr[sel])
        for i in te:
            p = per[keys[i]]
            sc = np.full(len(p["grid"]), np.nan)
            sc[p["usable"]] = mdl.predict_proba(p["X"][p["usable"]])[:, 1]
            scores[keys[i]] = sc
        print(f"  fold done, fitted on {len(sel):,} cycles", flush=True)

    pooled = np.concatenate([scores[k][np.isfinite(scores[k])] for k in keys])
    grid_thr = np.unique(np.quantile(pooled, np.concatenate([
        np.linspace(0.50, 0.95, 10), np.linspace(0.955, 0.9995, 20)])))
    del pooled
    for thr in grid_thr:
        sens, fa = [], []
        for k in keys:
            p = per[k]
            sc = scores[k]
            ep = episodes(p["grid"][np.nan_to_num(sc, nan=0) > thr])
            a, b = credit(ep, p["onsets"])
            sens.append(a)
            fa.append(b / p["days"])
        out["model"].append(dict(threshold=float(thr),
                                 sensitivity=float(np.mean(sens)),
                                 fa_per_day=float(np.mean(fa))))
        print(f"model thr {thr:.4f}: catches {np.mean(sens):.1%}, "
              f"{np.mean(fa):.2f} false alarms/day", flush=True)

    p = os.path.join(args.data, "streaming_detection.json")
    json.dump(out, open(p, "w"), indent=1)
    print(f"\nwrote {p}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
