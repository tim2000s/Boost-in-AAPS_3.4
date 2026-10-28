#!/usr/bin/env python3
"""
Does the glucose trajectory carry the size of the meal, and how early?

The commit-timing work established that the commits followed by hypoglycaemia are those landing
near the glucose peak, that this is not anticipable from the state at the commit, and that the
one variant hinting at a mechanism was that a small eventual excursion, under 20 mg/dL over the
commit, carries excess risk. That points at meal size: a full commit dose into a small meal
overshoots it.

This asks whether meal size is readable from the trajectory, using announced carbohydrate as
ground truth. Six participants announce carbohydrate, 3,308 entries between 2 and 150 g. The
participant this fork is developed on announces essentially nothing, so any model has to transfer
across participants to be of use to him, and every figure here holds participants out as folds.

Carbohydrate entered to treat a low is not a meal and is excluded, since its glucose signature is
a recovery rather than an absorption.

Three questions, in order.

  1. Is a meal distinguishable from a non-meal rise at all, from the trajectory alone?
  2. Is the amount readable, and at what horizon after onset does it become readable?
  3. Does the reading transfer to a held-out participant, which is the only version that is any
     use to someone who does not announce.

The horizon matters more than the accuracy. A size estimate available forty minutes after onset
is a description; one available at fifteen minutes could size a dose.

Usage:  python3 carb_signature.py [--json out.json]
"""

import argparse
import bisect
import json
import sys

import numpy as np
import psycopg2
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold

USERS = ("A", "C", "D", "E", "F", "H")     # participants who announce
RESCUE_BG = 80.0        # carbohydrate entered at or below this is treated as a rescue
RESCUE_FALLING = -2.0   # or entered while falling this fast, in mg/dL per 5 min
MIN_CARB = 8.0
HORIZONS = (10, 15, 20, 30, 45, 60)
SMALL_G, LARGE_G = 20.0, 40.0


def cgm_of(conn, users):
    cur = conn.cursor()
    cur.execute("""SELECT user_id, extract(epoch FROM ts_utc), cgm_mgdl FROM boost_cgm
                   WHERE user_id = ANY(%s) AND cgm_mgdl IS NOT NULL ORDER BY user_id, ts_utc""",
                (list(users),))
    o = {}
    for u, t, b in cur.fetchall():
        o.setdefault(u, ([], []))
        o[u][0].append(float(t)); o[u][1].append(float(b))
    return {u: (np.array(a), np.array(b)) for u, (a, b) in o.items()}


def carbs_of(conn, users):
    cur = conn.cursor()
    cur.execute("""SELECT user_id, extract(epoch FROM ts_utc), carbs FROM boost_treatments
                   WHERE user_id = ANY(%s) AND carbs IS NOT NULL AND carbs > 0
                   ORDER BY user_id, ts_utc""", (list(users),))
    o = {}
    for u, t, g in cur.fetchall():
        o.setdefault(u, []).append((float(t), float(g)))
    return o


def series_at(ts, bg, t, back_min, fwd_min):
    a = bisect.bisect_right(ts, t - back_min * 60)
    b = bisect.bisect_right(ts, t + fwd_min * 60)
    return ts[a:b], bg[a:b]


def shape_features(ts, bg, t0, horizon_min):
    """Everything computable from the sensor series between onset and onset + horizon."""
    a = bisect.bisect_right(ts, t0 - 20 * 60)
    m = bisect.bisect_right(ts, t0)
    b = bisect.bisect_right(ts, t0 + horizon_min * 60)
    if m - a < 3 or b - m < 2:
        return None
    pre, post = bg[a:m], bg[m:b]
    pt = ts[m:b]
    base = float(pre[-1])
    inc = np.diff(np.concatenate([[base], post]))
    mins = (pt - t0) / 60.0
    rise = float(post[-1] - base)
    auc_ = float(np.trapezoid(post - base, mins)) if len(post) > 1 else 0.0
    return dict(
        base=base,
        rise=rise,
        rise_rate=rise / max(horizon_min, 1) * 5.0,
        peak_so_far=float(post.max() - base),
        auc=auc_,
        inc_max=float(inc.max()) if len(inc) else 0.0,
        inc_last=float(inc[-1]) if len(inc) else 0.0,
        inc_mean=float(inc.mean()) if len(inc) else 0.0,
        accel=float(inc[-1] - inc[0]) if len(inc) > 1 else 0.0,
        curv=float(np.diff(inc).mean()) if len(inc) > 2 else 0.0,
        pre_slope=float(pre[-1] - pre[0]),
        still_rising=float(inc[-1] > 0),
    )


def build(cgm, carbs):
    """One row per announced meal, plus matched non-meal rises as the negative class."""
    meals, negs = [], []
    for u, entries in carbs.items():
        if u not in cgm:
            continue
        ts, bg = cgm[u]
        used = []
        for t, g in entries:
            if g < MIN_CARB:
                continue
            i = bisect.bisect_right(ts, t) - 1
            if i < 4 or i > len(ts) - 20:
                continue
            # exclude rescue carbohydrate
            recent = bg[max(0, i - 3):i + 1]
            if bg[i] <= RESCUE_BG or (len(recent) > 1 and (recent[-1] - recent[0]) / 3 <= RESCUE_FALLING):
                continue
            if used and t - used[-1] < 90 * 60:      # one meal per 90 min
                continue
            used.append(t)
            # onset: the last non-rising point at or before the entry, within 30 min
            j = i
            while j > 0 and ts[i] - ts[j] < 30 * 60 and bg[j] >= bg[j - 1]:
                j -= 1
            t0 = ts[j]
            row = dict(user=u, t0=t0, carbs=g)
            ok = True
            for h in HORIZONS:
                f = shape_features(ts, bg, t0, h)
                if f is None:
                    ok = False
                    break
                for k, v in f.items():
                    row[f"h{h}_{k}"] = v
            # the eventual excursion, as the label a record without announcements would have
            _, seg = series_at(ts, bg, t0, 0, 180)
            row["peak_rise"] = float(seg.max() - seg[0]) if len(seg) else np.nan
            if ok:
                meals.append(row)
        # negatives: rises of at least 25 mg/dL in 30 min with no carbohydrate within 2 h
        et = np.array([x[0] for x in entries])
        i = 4
        while i < len(ts) - 40:
            w = bisect.bisect_right(ts, ts[i] + 30 * 60)
            if w - i >= 4 and bg[i:w].max() - bg[i] >= 25 and bg[i] > RESCUE_BG:
                k = bisect.bisect_left(et, ts[i] - 7200)
                k2 = bisect.bisect_right(et, ts[i] + 7200)
                if k == k2:
                    row = dict(user=u, t0=ts[i], carbs=0.0)
                    ok = True
                    for h in HORIZONS:
                        f = shape_features(ts, bg, ts[i], h)
                        if f is None:
                            ok = False; break
                        for kk, v in f.items():
                            row[f"h{h}_{kk}"] = v
                    if ok:
                        negs.append(row)
                    i = w + 12
                    continue
            i += 1
    return meals, negs


def auc(s, y):
    s = np.asarray(s, float); y = np.asarray(y, int)
    npos, nneg = int(y.sum()), len(y) - int(y.sum())
    if npos == 0 or nneg == 0:
        return None
    o = np.argsort(s, kind="mergesort"); ss = s[o]
    r = np.empty(len(ss)); i = 0
    while i < len(ss):
        j = i
        while j + 1 < len(ss) and ss[j + 1] == ss[i]:
            j += 1
        r[i:j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    rr = np.empty(len(ss)); rr[o] = r
    return (rr[y == 1].sum() - npos * (npos + 1) / 2.0) / (npos * nneg)


def cluster_ci(users, s, y, fn=auc, n=2000, seed=20260813):
    us = sorted(set(users)); rng = np.random.default_rng(seed)
    idx = {u: np.flatnonzero(users == u) for u in us}
    pt = fn(s, y)
    b = []
    for _ in range(n):
        pick = rng.choice(len(us), len(us), replace=True)
        sel = np.concatenate([idx[us[k]] for k in pick])
        v = fn(s[sel], y[sel])
        if v is not None and np.isfinite(v):
            b.append(v)
    if not b:
        return pt, None, None
    return pt, float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def oof(X, y, groups, kind="clf"):
    o = np.zeros(len(y), dtype=float)
    for tr, te in GroupKFold(n_splits=min(5, len(set(groups)))).split(X, y, groups=groups):
        if kind == "clf":
            m = HistGradientBoostingClassifier(max_iter=200, max_depth=4, learning_rate=0.06,
                                               min_samples_leaf=25, random_state=0)
            m.fit(X[tr], y[tr]); o[te] = m.predict_proba(X[te])[:, 1]
        else:
            m = HistGradientBoostingRegressor(max_iter=250, max_depth=4, learning_rate=0.06,
                                              min_samples_leaf=25, random_state=0)
            m.fit(X[tr], y[tr]); o[te] = m.predict(X[te])
    return o


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--json", default=None)
    args = ap.parse_args()
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    cgm = cgm_of(conn, USERS); carbs = carbs_of(conn, USERS)
    meals, negs = build(cgm, carbs)
    print(f"announced meals after excluding rescues: {len(meals)}")
    print(f"unannounced rises used as negatives:     {len(negs)}")
    gs = np.array([m["carbs"] for m in meals])
    print(f"  carbohydrate: median {np.median(gs):.0f} g, "
          f"quartiles {np.percentile(gs,25):.0f} to {np.percentile(gs,75):.0f}, "
          f"range {gs.min():.0f} to {gs.max():.0f}")
    from collections import Counter
    print("  per participant:", dict(Counter(m["user"] for m in meals)))
    res = {"n_meals": len(meals), "n_negs": len(negs)}

    print()
    print("=" * 78)
    print("1. IS A MEAL DISTINGUISHABLE FROM AN UNANNOUNCED RISE, BY HORIZON")
    print("=" * 78)
    print("  Both classes are rises. The question is whether a declared meal looks different")
    print("  from a rise that nobody declared, which bounds what any detector can do.\n")
    allrows = meals + negs
    y = np.array([1] * len(meals) + [0] * len(negs))
    g = np.array([r["user"] for r in allrows])
    print(f"  {'horizon':>9s} {'AUC':>7s} {'95% CI':>18s}")
    res["detect"] = {}
    for h in HORIZONS:
        keys = sorted(k for k in meals[0] if k.startswith(f"h{h}_"))
        X = np.array([[r.get(k, np.nan) for k in keys] for r in allrows], float)
        p = oof(X, y, g, "clf")
        a, lo, hi = cluster_ci(g, p, y)
        print(f"  {h:7d}m {a:7.3f}  [{lo:.3f}, {hi:.3f}]")
        res["detect"][h] = dict(auc=a, lo=lo, hi=hi)

    print()
    print("=" * 78)
    print("2. IS THE AMOUNT READABLE, AND WHEN")
    print("=" * 78)
    print(f"  Small is under {SMALL_G:.0f} g, large is over {LARGE_G:.0f} g. Middle sizes are")
    print("  dropped so the comparison is between classes that differ rather than adjacent bins.\n")
    sel = [m for m in meals if m["carbs"] < SMALL_G or m["carbs"] > LARGE_G]
    ys = np.array([1 if m["carbs"] > LARGE_G else 0 for m in sel])
    gsel = np.array([m["user"] for m in sel])
    print(f"  {len(sel)} meals, {ys.sum()} large and {len(ys)-ys.sum()} small")
    print(f"\n  {'horizon':>9s} {'AUC':>7s} {'95% CI':>18s} {'rise alone':>12s}")
    res["size"] = {}
    for h in HORIZONS:
        keys = sorted(k for k in meals[0] if k.startswith(f"h{h}_"))
        X = np.array([[m.get(k, np.nan) for k in keys] for m in sel], float)
        p = oof(X, ys, gsel, "clf")
        a, lo, hi = cluster_ci(gsel, p, ys)
        r_only = auc(np.array([m[f"h{h}_rise"] for m in sel]), ys)
        print(f"  {h:7d}m {a:7.3f}  [{lo:.3f}, {hi:.3f}] {r_only:12.3f}")
        res["size"][h] = dict(auc=a, lo=lo, hi=hi, rise_only=r_only)

    print()
    print("=" * 78)
    print("3. THE AMOUNT AS A QUANTITY, HELD OUT BY PARTICIPANT")
    print("=" * 78)
    yg = np.array([m["carbs"] for m in meals])
    gm = np.array([m["user"] for m in meals])
    print(f"\n  {'horizon':>9s} {'corr':>7s} {'MAE g':>7s} {'MAE of the mean':>16s}")
    res["regress"] = {}
    for h in HORIZONS:
        keys = sorted(k for k in meals[0] if k.startswith(f"h{h}_"))
        X = np.array([[m.get(k, np.nan) for k in keys] for m in meals], float)
        pr = oof(X, yg, gm, "reg")
        corr = float(np.corrcoef(pr, yg)[0, 1])
        mae = float(np.mean(np.abs(pr - yg)))
        base = float(np.mean(np.abs(yg - np.median(yg))))
        print(f"  {h:7d}m {corr:7.3f} {mae:7.1f} {base:16.1f}")
        res["regress"][h] = dict(corr=corr, mae=mae, baseline=base)

    print()
    print("=" * 78)
    print("4. THE EVENTUAL EXCURSION, WHICH NEEDS NO ANNOUNCEMENT")
    print("=" * 78)
    print("  The peak rise over the onset is available from the record for every rise, announced")
    print("  or not, so a model predicting it can be trained on everybody. This is the quantity")
    print("  the commit would need in order to size itself.\n")
    have = [m for m in meals if np.isfinite(m.get("peak_rise", np.nan))]
    yp = np.array([m["peak_rise"] for m in have])
    gp = np.array([m["user"] for m in have])
    print(f"  {len(have)} meals, median eventual rise {np.median(yp):.0f} mg/dL")
    print(f"\n  {'horizon':>9s} {'corr':>7s} {'MAE mg/dL':>10s} {'MAE of the mean':>16s}")
    res["excursion"] = {}
    for h in HORIZONS:
        keys = sorted(k for k in meals[0] if k.startswith(f"h{h}_"))
        X = np.array([[m.get(k, np.nan) for k in keys] for m in have], float)
        pr = oof(X, yp, gp, "reg")
        corr = float(np.corrcoef(pr, yp)[0, 1])
        mae = float(np.mean(np.abs(pr - yp)))
        base = float(np.mean(np.abs(yp - np.median(yp))))
        print(f"  {h:7d}m {corr:7.3f} {mae:10.1f} {base:16.1f}")
        res["excursion"][h] = dict(corr=corr, mae=mae, baseline=base)

    print()
    print("=" * 78)
    print("5. WITHIN A PARTICIPANT, FITTED ON THEIR EARLIER MEALS")
    print("=" * 78)
    print("  Cross-participant failure in this programme has repeatedly meant that the")
    print("  relationship lives within people. A temporal split, first 60 per cent of a")
    print("  participant's meals to fit and the last 40 to score, asks that directly.\n")
    print(f"  {'user':6s} {'meals':>6s} {'test':>5s} " +
          " ".join(f"{h:>6d}m" for h in HORIZONS))
    res["within"] = {}
    for u in sorted(set(m["user"] for m in meals)):
        mu = sorted([m for m in meals if m["user"] == u], key=lambda x: x["t0"])
        if len(mu) < 40:
            continue
        cut = int(len(mu) * 0.6)
        tr, te = mu[:cut], mu[cut:]
        yv_tr = np.array([m["carbs"] > np.median([x["carbs"] for x in tr]) for m in tr], int)
        yv_te = np.array([m["carbs"] > np.median([x["carbs"] for x in tr]) for m in te], int)
        if len(set(yv_te)) < 2:
            continue
        line, row = [], {}
        for h in HORIZONS:
            keys = sorted(k for k in meals[0] if k.startswith(f"h{h}_"))
            Xtr = np.array([[m.get(k, np.nan) for k in keys] for m in tr], float)
            Xte = np.array([[m.get(k, np.nan) for k in keys] for m in te], float)
            mdl = HistGradientBoostingClassifier(max_iter=150, max_depth=3, learning_rate=0.06,
                                                 min_samples_leaf=10, random_state=0)
            mdl.fit(Xtr, yv_tr)
            a = auc(mdl.predict_proba(Xte)[:, 1], yv_te)
            line.append(f"{a:7.3f}" if a is not None else "    n/a")
            row[h] = a
        print(f"  {u:6s} {len(mu):6d} {len(te):5d} " + "".join(line))
        res["within"][u] = row
    print("\n  Above the participant's own median carbohydrate against below it, so the class")
    print("  boundary is set per person rather than at a shared threshold.")

    if args.json:
        json.dump(res, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
