#!/usr/bin/env python3
"""Does the BG-acceleration shadow detect the same meals at a lower false-alarm rate?

The accelMeal shadow is a fixed threshold on glucose curvature:

    accel = shortAvgDelta - longAvgDelta
    trig  = accel > 2.0 && rising && state in (IDLE, OBSERVING)

It is not an accelerometer. It reads the second derivative of glucose, which is inside the same
information class as the fitted detector, so the two can be compared directly on identical events.

The comparison is paired. Both detectors see the same onsets from the same participants, so the
between-person confounds that wreck cross-user work here do not apply. What differs is only the
decision rule: a hand-set threshold on one feature against a model fitted on 839 other people.

Power is the limitation and it is severe. Only participants who both run the shadow and announce
carbohydrate can be scored, which is E and F with about 115 meals between them over 22 days. A is
carried as a sensitivity check only, since at 0.45 announcements per day its unannounced class is
mostly unlogged meals. Nothing here can be more than PROVISIONAL.

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
from size_readability import LGB, SEED, auc_of

SHAPE = ("base", "rise", "rise_rate", "peak_so_far", "auc", "inc_max", "inc_last",
         "inc_mean", "accel", "curv", "pre_slope", "still_rising")
HORIZONS = (10, 15, 20, 30)
MIN_NEG_RISE = 25.0
NEG_CARB_GAP_S = 7200


def boost_series(cur, table, col, user, where=""):
    cur.execute(f"select extract(epoch from ts_utc), {col} from public.{table} "
                f"where user_id=%s {where} order by ts_utc", (user,))
    rows = [r for r in cur.fetchall() if r[1] is not None]
    if not rows:
        return np.empty(0), np.empty(0)
    a = np.asarray(rows, dtype=float)
    return a[:, 0], a[:, 1]


def build_events(ts, bg, ct):
    """Announced meals and undeclared rises, same rules as the corpus extraction."""
    pos, used = [], []
    for t in ct:
        i = bisect.bisect_right(ts, t) - 1
        if i < 4 or i > len(ts) - 20:
            continue
        recent = bg[max(0, i - 3):i + 1]
        if bg[i] <= RESCUE_BG or (len(recent) > 1 and (recent[-1] - recent[0]) / 3 <= RESCUE_FALLING):
            continue
        if used and t - used[-1] < MEAL_SEPARATION_S:
            continue
        used.append(t)
        j = i
        while j > 0 and ts[i] - ts[j] < ONSET_LOOKBACK_S and bg[j] >= bg[j - 1]:
            j -= 1
        pos.append(ts[j])
    neg, i = [], 4
    while i < len(ts) - 40:
        w = bisect.bisect_right(ts, ts[i] + 30 * 60)
        if w - i >= 4 and bg[i:w].max() - bg[i] >= MIN_NEG_RISE and bg[i] > RESCUE_BG:
            k = bisect.bisect_left(ct, ts[i] - NEG_CARB_GAP_S)
            k2 = bisect.bisect_right(ct, ts[i] + NEG_CARB_GAP_S)
            if k == k2:
                neg.append(ts[i])
                i = w + 12
                continue
        i += 1
    return pos, neg


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--data", default=os.path.join(here, "out"))
    ap.add_argument("--users", default="E,F")
    ap.add_argument("--check-users", default="A")
    args = ap.parse_args()

    # 1. fit the detector on the corpus, one model per horizon
    print("fitting detectors on the corpus", flush=True)
    loop = pd.read_parquet(os.path.join(args.data, "meals_Loop.parquet"))
    loop = loop[loop.h30_peak_so_far >= MIN_NEG_RISE].assign(is_meal=1)
    negL = pd.read_parquet(os.path.join(args.data, "negatives_Loop.parquet")).assign(is_meal=0)
    models = {}
    for h in HORIZONS:
        feats = [f"h{h}_{c}" for c in SHAPE]
        d = pd.concat([loop[feats + ["is_meal"]], negL[feats + ["is_meal"]]], ignore_index=True).dropna()
        m = lgb.LGBMClassifier(random_state=SEED, **LGB)
        m.fit(d[feats].to_numpy(float), d.is_meal.to_numpy(int))
        models[h] = m
        print(f"  h{h}: fitted on {len(d):,} corpus events", flush=True)

    conn = psycopg2.connect("dbname=oref")
    conn.autocommit = True
    out = {"per_user": [], "pooled": {}}
    frames = []
    for user in args.users.split(",") + args.check_users.split(","):
        with conn.cursor() as cur:
            ts, bg = boost_series(cur, "boost_cgm", "cgm_mgdl", user)
            ct, cg = boost_series(cur, "boost_treatments", "carbs", user,
                                  "and carbs >= %s" % MIN_CARB)
            dt, dtrig = boost_series(cur, "boost_decisions", "accelmeal_trig", user)
        if len(ts) < 100 or len(dt) == 0:
            continue
        lo, hi = dt.min(), dt.max()                      # score only where the shadow was running
        keep = (ts >= lo) & (ts <= hi)
        ts, bg = ts[keep], bg[keep]
        ct = ct[(ct >= lo) & (ct <= hi)]
        fires = dt[dtrig > 0]
        pos, neg = build_events(ts, bg, ct)
        days = (hi - lo) / 86400.0
        rows = []
        for t0, lab in [(t, 1) for t in pos] + [(t, 0) for t in neg]:
            r = dict(user=user, t0=t0, is_meal=lab)
            ok = True
            for h in HORIZONS:
                f = shape_features(ts, bg, t0, h)
                if f is None:
                    ok = False
                    break
                for k, v in f.items():
                    r[f"h{h}_{k}"] = v
            if not ok:
                continue
            # accel shadow: did it fire by each decision time, and when first
            a = bisect.bisect_left(fires, t0)
            for h in HORIZONS:
                b = bisect.bisect_right(fires, t0 + h * 60)
                r[f"accel_by{h}"] = 1 if b > a else 0
            r["accel_latency"] = (fires[a] - t0) / 60.0 if a < len(fires) and fires[a] <= t0 + 30 * 60 else np.nan
            rows.append(r)
        if not rows:
            continue
        df = pd.DataFrame(rows)
        df["days"] = days
        frames.append(df)
        print(f"{user}: {int(df.is_meal.sum())} announced meals, "
              f"{int((1-df.is_meal).sum())} undeclared rises, {days:.0f} days", flush=True)

    all_df = pd.concat(frames, ignore_index=True)
    primary = all_df[all_df.user.isin(args.users.split(","))]

    def score_block(d, label):
        res = []
        days = d.groupby("user").days.first().sum()
        y = d.is_meal.to_numpy(int)
        for h in HORIZONS:
            feats = [f"h{h}_{c}" for c in SHAPE]
            s = models[h].predict_proba(d[feats].to_numpy(float))[:, 1]
            acc = d[f"accel_by{h}"].to_numpy(int)
            # the shadow's own operating point
            sens_a = float(acc[y == 1].mean())
            fa_a = float(acc[y == 0].sum()) / days
            # the model held to the shadow's sensitivity
            thr = np.quantile(s[y == 1], 1 - sens_a) if 0 < sens_a < 1 else np.nan
            fa_m = float((s[y == 0] > thr).sum()) / days if np.isfinite(thr) else np.nan
            # the model held to the shadow's false-alarm rate
            k = int(acc[y == 0].sum())
            thr2 = np.sort(s[y == 0])[::-1][k - 1] if 0 < k <= (y == 0).sum() else np.nan
            sens_m = float((s[y == 1] > thr2).mean()) if np.isfinite(thr2) else np.nan
            res.append(dict(block=label, horizon=h, n_meals=int(y.sum()), n_rises=int((1 - y).sum()),
                            days=days, auc_model=auc_of(y, s), auc_accel=auc_of(y, acc.astype(float)),
                            accel_sens=sens_a, accel_fa_per_day=fa_a,
                            model_fa_per_day_at_accel_sens=fa_m,
                            model_sens_at_accel_fa=sens_m))
            print(f"[{label}] h{h:>3}  shadow: sens {sens_a:.3f}, {fa_a:.2f} false alarms/day  |  "
                  f"model at same sens: {fa_m:.2f} FA/day  |  model at same FA: sens {sens_m:.3f}",
                  flush=True)
        return res

    out["pooled"]["primary"] = score_block(primary, "E+F")
    for u in args.users.split(","):
        out["per_user"] += score_block(primary[primary.user == u], u)
    chk = all_df[all_df.user.isin(args.check_users.split(","))]
    if len(chk):
        out["pooled"]["check"] = score_block(chk, "A (incomplete announcer)")

    lat = primary.loc[primary.is_meal == 1, "accel_latency"].dropna()
    out["latency"] = dict(n=int(len(lat)), median=float(lat.median()) if len(lat) else None,
                          p25=float(lat.quantile(0.25)) if len(lat) else None,
                          p75=float(lat.quantile(0.75)) if len(lat) else None)
    print(f"\nshadow first-fire latency on announced meals: n={len(lat)}, "
          f"median {lat.median():.1f} min (IQR {lat.quantile(0.25):.1f} to {lat.quantile(0.75):.1f})",
          flush=True)

    p = os.path.join(args.data, "accel_vs_model.json")
    json.dump(out, open(p, "w"), indent=1, default=float)
    print(f"wrote {p}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
