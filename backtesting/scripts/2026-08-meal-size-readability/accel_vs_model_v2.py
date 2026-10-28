#!/usr/bin/env python3
"""Shadow against fitted detector, scored continuously and counted as episodes.

The accelMeal shadow is a per-cycle flag, so one rise sets it on many consecutive cycles. Counting
cycles would charge it many times for one alarm and would not describe what a controller sees.
Both detectors are therefore run over the whole timeline and their firings collapsed into episodes,
consecutive firings less than GAP apart being one event.

The fitted detector is run in the same streaming form: at each cycle T and horizon h, the features
are computed over the window ending at T and beginning h minutes earlier, which is the information
a controller would hold at T if a meal had started at T minus h.

A detection is credited when an episode begins within [-15, +45] minutes of an announced meal
onset. Everything else is a false alarm. Sensitivity and false alarms per day are then directly
comparable, and the model's threshold is swept so it can be held to the shadow's own operating
point from either side.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, secondary analysis.
"""

import argparse
import bisect
import json
import os
import sys

import numpy as np
import pandas as pd
import psycopg2

import lightgbm as lgb
from extract_meals import (MEAL_SEPARATION_S, MIN_CARB, ONSET_LOOKBACK_S, RESCUE_BG,
                           RESCUE_FALLING, shape_features)
from size_readability import LGB, SEED

SHAPE = ("base", "rise", "rise_rate", "peak_so_far", "auc", "inc_max", "inc_last",
         "inc_mean", "accel", "curv", "pre_slope", "still_rising")
HORIZONS = (10, 20, 30)
MIN_NEG_RISE = 25.0
EPISODE_GAP_S = 45 * 60
CREDIT_BEFORE_S = 15 * 60
CREDIT_AFTER_S = 45 * 60


def series(cur, table, col, user, extra=""):
    cur.execute(f"select extract(epoch from ts_utc), {col} from public.{table} "
                f"where user_id=%s {extra} order by ts_utc", (user,))
    rows = [r for r in cur.fetchall() if r[1] is not None]
    if not rows:
        return np.empty(0), np.empty(0)
    a = np.asarray(rows, dtype=float)
    return a[:, 0], a[:, 1]


def episodes(times, gap=EPISODE_GAP_S):
    """Collapse firing times into episodes; return the start of each."""
    if len(times) == 0:
        return np.empty(0)
    t = np.sort(np.asarray(times, dtype=float))
    starts = [t[0]]
    for a, b in zip(t[:-1], t[1:]):
        if b - a > gap:
            starts.append(b)
    return np.asarray(starts)


def meal_onsets(ts, bg, ct):
    """Announced meals, with the exclusion cascade counted."""
    kept, used = [], []
    drop = dict(edge=0, rescue=0, too_close=0)
    for t in ct:
        i = bisect.bisect_right(ts, t) - 1
        if i < 4 or i > len(ts) - 20:
            drop["edge"] += 1
            continue
        recent = bg[max(0, i - 3):i + 1]
        if bg[i] <= RESCUE_BG or (len(recent) > 1 and (recent[-1] - recent[0]) / 3 <= RESCUE_FALLING):
            drop["rescue"] += 1
            continue
        if used and t - used[-1] < MEAL_SEPARATION_S:
            drop["too_close"] += 1
            continue
        used.append(t)
        j = i
        while j > 0 and ts[i] - ts[j] < ONSET_LOOKBACK_S and bg[j] >= bg[j - 1]:
            j -= 1
        kept.append(ts[j])
    return np.asarray(kept), drop


def credit(ep_starts, onsets):
    """Split episodes into hits and false alarms; report meals caught."""
    if len(onsets) == 0:
        return 0, len(ep_starts), 0.0
    hits, fa = 0, 0
    caught = set()
    for e in ep_starts:
        k = np.where((onsets >= e - CREDIT_AFTER_S) & (onsets <= e + CREDIT_BEFORE_S))[0]
        if len(k):
            hits += 1
            caught.add(int(k[0]))
        else:
            fa += 1
    return hits, fa, len(caught) / len(onsets)


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--data", default=os.path.join(here, "out"))
    ap.add_argument("--users", default="E,F")
    args = ap.parse_args()

    print("fitting detectors on the corpus", flush=True)
    loop = pd.read_parquet(os.path.join(args.data, "meals_Loop.parquet"))
    loop = loop[loop.h30_peak_so_far >= MIN_NEG_RISE].assign(is_meal=1)
    negL = pd.read_parquet(os.path.join(args.data, "negatives_Loop.parquet")).assign(is_meal=0)
    models = {}
    for h in HORIZONS:
        feats = [f"h{h}_{c}" for c in SHAPE]
        d = pd.concat([loop[feats + ["is_meal"]], negL[feats + ["is_meal"]]],
                      ignore_index=True).dropna()
        m = lgb.LGBMClassifier(random_state=SEED, **LGB)
        m.fit(d[feats].to_numpy(float), d.is_meal.to_numpy(int))
        models[h] = m
    print(f"  fitted on {len(d):,} corpus events per horizon\n", flush=True)

    conn = psycopg2.connect("dbname=oref")
    conn.autocommit = True
    out = {"users": [], "sweep": []}

    for user in args.users.split(","):
        with conn.cursor() as cur:
            ts, bg = series(cur, "boost_cgm", "cgm_mgdl", user)
            ct, _ = series(cur, "boost_treatments", "carbs", user, f"and carbs >= {MIN_CARB}")
            dt, dtrig = series(cur, "boost_decisions", "accelmeal_trig", user)
        if len(dt) == 0:
            continue
        lo, hi = dt.min(), dt.max()
        keep = (ts >= lo) & (ts <= hi)
        ts, bg = ts[keep], bg[keep]
        ct = ct[(ct >= lo) & (ct <= hi)]
        days = (hi - lo) / 86400.0

        onsets, drop = meal_onsets(ts, bg, ct)
        shadow_ep = episodes(dt[dtrig > 0])
        s_hit, s_fa, s_sens = credit(shadow_ep, onsets)
        print(f"{user}: {len(ct)} announcements >= {MIN_CARB:.0f} g -> {len(onsets)} meal onsets "
              f"(dropped {drop['rescue']} as rescue, {drop['too_close']} within 90 min, "
              f"{drop['edge']} at edges) over {days:.0f} days", flush=True)
        print(f"  shadow: {len(shadow_ep)} episodes, catches {s_sens:.1%} of meals, "
              f"{s_fa/days:.2f} false alarms/day", flush=True)

        # streaming model scores
        rec = dict(user=user, days=days, n_onsets=int(len(onsets)),
                   shadow_episodes=int(len(shadow_ep)), shadow_sens=s_sens,
                   shadow_fa_per_day=s_fa / days, drops=drop, horizons={})
        for h in HORIZONS:
            sc, tt = [], []
            for i in range(len(ts)):
                t_now = ts[i]
                f = shape_features(ts, bg, t_now - h * 60, h)
                if f is None:
                    continue
                sc.append([f[c] for c in SHAPE])
                tt.append(t_now)
            if not sc:
                continue
            sc = models[h].predict_proba(np.asarray(sc, dtype=float))[:, 1]
            tt = np.asarray(tt)
            pts = []
            for thr in np.quantile(sc, np.linspace(0.50, 0.999, 40)):
                ep = episodes(tt[sc > thr])
                hit, fa, sens = credit(ep, onsets)
                pts.append(dict(thr=float(thr), episodes=int(len(ep)),
                                sens=sens, fa_per_day=fa / days))
            rec["horizons"][h] = pts
            # the model held to the shadow's false-alarm budget
            elig = [p for p in pts if p["fa_per_day"] <= rec["shadow_fa_per_day"] + 1e-9]
            best = max(elig, key=lambda p: p["sens"]) if elig else None
            # and held to the shadow's sensitivity
            elig2 = [p for p in pts if p["sens"] >= s_sens - 1e-9]
            cheap = min(elig2, key=lambda p: p["fa_per_day"]) if elig2 else None
            print(f"  model h{h:>3}: at the shadow's {rec['shadow_fa_per_day']:.2f} FA/day it catches "
                  f"{best['sens']:.1%}" if best else f"  model h{h:>3}: no point within budget",
                  flush=True)
            if cheap:
                print(f"            at the shadow's {s_sens:.1%} sensitivity it costs "
                      f"{cheap['fa_per_day']:.2f} FA/day", flush=True)
            rec["horizons"][f"{h}_at_shadow_fa"] = best
            rec["horizons"][f"{h}_at_shadow_sens"] = cheap
        out["users"].append(rec)
        print(flush=True)

    p = os.path.join(args.data, "accel_vs_model_v2.json")
    json.dump(out, open(p, "w"), indent=1, default=float)
    print(f"wrote {p}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
