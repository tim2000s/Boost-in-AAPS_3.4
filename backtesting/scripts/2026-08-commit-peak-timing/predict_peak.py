#!/usr/bin/env python3
"""
Is time-to-peak predictable at the moment of commit, and does predicting it help?

The interval from commit to glucose peak separates the commits followed by hypoglycaemia from
those that are not, at 26.8 per cent against 16.0. It is measured from data after the commit, so
it cannot gate one. This asks whether it can be anticipated instead.

Two questions, in order, because the second is the one that matters and the first does not imply
it.

  1. Can a model trained on the state available at the commit predict that the peak will arrive
     within ten minutes? Scored out of sample with participants held out as folds, so what is
     measured is cross-participant generalisation rather than per-person memorisation.

  2. Does that model's out-of-sample probability predict the low that follows, and does it add
     anything over what the algorithm already has? A predictor of peak timing is only worth
     building if using it separates the outcome.

Every feature is drawn strictly from before the commit. The approach increments come from the
sensor series up to and including the commit cycle; nothing downstream of it is admitted.

Usage:  python3 predict_peak.py [--json out.json]
"""

import argparse
import json
import sys

import numpy as np
import psycopg2
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from peak_timing import (USERS, PEAK_WINDOW_MIN, LOW_HORIZON_MIN, LOW_MGDL, LOW_SUSTAIN_MIN,
                         BUCKET_MIN, auc, cgm_of, low_onsets)

EARLY_CUT_MIN = 10


def fetch(conn):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT ON (user_id, to_timestamp(floor(extract(epoch FROM ts_utc)/{BUCKET_MIN*60})*{BUCKET_MIN*60}))
               user_id, extract(epoch FROM ts_utc), boostv5_state, cgm_mgdl,
               boostv5_finaldose, sug_iob, sug_cob, sug_eventualbg, boostv5_score,
               boostv5_age, boostv5_budget, delta_acceleration, tdd, steps_30m, steps_60m,
               hr_avg, sug_insulinreq, iob_activity, variable_sens
        FROM boost_decisions
        WHERE user_id = ANY(%s) AND boostv5_state IS NOT NULL AND cgm_mgdl IS NOT NULL
        ORDER BY user_id,
                 to_timestamp(floor(extract(epoch FROM ts_utc)/{BUCKET_MIN*60})*{BUCKET_MIN*60}),
                 ts_utc
    """, (list(USERS),))
    names = [d[0] for d in cur.description][1:]
    out = {}
    for r in cur.fetchall():
        d = {}
        for k, v in zip(names, r[1:]):
            d[k] = np.nan if v is None else (v if isinstance(v, str) else float(v))
        out.setdefault(r[0], []).append(d)
    for u in out:
        out[u].sort(key=lambda x: x["extract"])
    return out


def build(rows, cgm_ts, cgm_bg, lows, last_commit_holder):
    """One row per entry into CONFIRMED, with features from before the commit only."""
    feats, ys, lowy, meta = [], [], [], []
    prev_commit = None
    for k in range(1, len(rows)):
        if rows[k]["boostv5_state"] != "CONFIRMED" or rows[k - 1]["boostv5_state"] == "CONFIRMED":
            continue
        t = rows[k]["extract"]
        a = np.searchsorted(cgm_ts, t + 1)          # strictly at or before the commit
        b = np.searchsorted(cgm_ts, t + PEAK_WINDOW_MIN * 60)
        if a < 8 or b - a < 6:
            continue
        # the approach, from the sensor series only
        hist = cgm_bg[max(0, a - 8):a]
        ht = cgm_ts[max(0, a - 8):a]
        if len(hist) < 6:
            continue
        inc = np.diff(hist)
        curv = np.diff(inc)
        rise60 = hist[-1] - hist[0]
        # forward outcome, used as the label only
        seg_t, seg_b = cgm_ts[a - 1:b], cgm_bg[a - 1:b]
        pk = int(np.argmax(seg_b))
        interval = (seg_t[pk] - t) / 60.0
        lo = np.searchsorted(lows, t, side="right")
        hi = np.searchsorted(lows, t + LOW_HORIZON_MIN * 60, side="right")

        r = rows[k]
        since_commit = 720.0 if prev_commit is None else min(720.0, (t - prev_commit) / 60.0)
        prev_commit = t
        f = dict(
            bg=r["cgm_mgdl"],
            inc1=inc[-1], inc2=inc[-2], inc3=inc[-3], inc4=inc[-4],
            curv1=curv[-1], curv2=curv[-2],
            inc_max=float(inc[-4:].max()), inc_mean=float(inc[-4:].mean()),
            inc_slope=float(inc[-1] - inc[-4]),
            rise_35min=float(rise60),
            bg_min_hist=float(hist.min()), bg_range=float(hist.max() - hist.min()),
            iob=r["sug_iob"], cob=r["sug_cob"], eventual=r["sug_eventualbg"],
            score=r["boostv5_score"], age=r["boostv5_age"], budget=r["boostv5_budget"],
            delta_accl=r["delta_acceleration"], tdd=r["tdd"],
            steps30=r["steps_30m"], steps60=r["steps_60m"], hr=r["hr_avg"],
            insulinreq=r["sug_insulinreq"], activity=r["iob_activity"],
            varsens=r["variable_sens"],
            hour=float(int((t // 3600) % 24)),
            since_last_commit=since_commit,
        )
        feats.append(f)
        ys.append(int(interval <= EARLY_CUT_MIN))
        lowy.append(int(hi > lo))
        meta.append(dict(interval=interval, dose=r["boostv5_finaldose"], bg=r["cgm_mgdl"]))
    return feats, ys, lowy, meta


def cluster_ci(users, scores, labels, n=3000, seed=20260813):
    us = sorted(set(users))
    rng = np.random.default_rng(seed)
    idx = {u: np.flatnonzero(users == u) for u in us}
    pt = auc(scores, labels)
    b = []
    for _ in range(n):
        pick = rng.choice(len(us), len(us), replace=True)
        sel = np.concatenate([idx[us[k]] for k in pick])
        v = auc(scores[sel], labels[sel])
        if v is not None:
            b.append(v)
    return pt, float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--json", default=None)
    args = ap.parse_args()
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    rows, cgm = fetch(conn), cgm_of(conn)

    F, Y, L, U, M = [], [], [], [], []
    for u, r in rows.items():
        if u not in cgm:
            continue
        ct, cb = cgm[u]
        f, y, l, m = build(r, ct, cb, low_onsets(ct, cb), None)
        if len(f) < 20:
            continue
        F += f; Y += y; L += l; M += m; U += [u] * len(f)
    keys = sorted(F[0].keys())
    X = np.array([[r[k] for k in keys] for r in F], dtype=float)
    Y = np.array(Y); L = np.array(L); U = np.array(U)
    print(f"commits: {len(Y)} across {len(set(U))} participants")
    print(f"  peak within {EARLY_CUT_MIN} min: {Y.mean():.3f}   low within 3h: {L.mean():.3f}")
    print(f"  features: {len(keys)}\n")
    res = {"n": int(len(Y)), "base_early": float(Y.mean()), "base_low": float(L.mean())}

    print("=" * 78)
    print("1. CAN THE PEAK TIMING BE PREDICTED AT THE COMMIT?")
    print("=" * 78)
    print("  GroupKFold with the participant as the group, so no participant is in both sides.\n")
    gkf = GroupKFold(n_splits=min(5, len(set(U))))
    oof_g = np.zeros(len(Y)); oof_l = np.zeros(len(Y))
    for tr, te in gkf.split(X, Y, groups=U):
        g = HistGradientBoostingClassifier(max_iter=250, max_depth=4, learning_rate=0.05,
                                           min_samples_leaf=40, random_state=0)
        g.fit(X[tr], Y[tr]); oof_g[te] = g.predict_proba(X[te])[:, 1]
        sc = StandardScaler().fit(np.nan_to_num(X[tr]))
        lr = LogisticRegression(max_iter=2000, C=0.5)
        lr.fit(sc.transform(np.nan_to_num(X[tr])), Y[tr])
        oof_l[te] = lr.predict_proba(sc.transform(np.nan_to_num(X[te])))[:, 1]
    for nm, s in (("gradient boosted", oof_g), ("logistic (overfit control)", oof_l)):
        p, lo, hi = cluster_ci(U, s, Y)
        v = "clear of chance" if lo > 0.5 else "NOT clear of chance"
        print(f"  {nm:28s} AUC {p:.3f} [{lo:.3f}, {hi:.3f}]  {v}")
        res[f"peak_auc_{nm.split()[0]}"] = dict(auc=p, lo=lo, hi=hi)
    # single features, for comparison
    print("\n  single features available at the commit, against the same label:")
    for k in ("inc1", "inc_slope", "rise_35min", "delta_accl", "bg", "score", "iob"):
        i = keys.index(k)
        m = np.isfinite(X[:, i])
        if m.sum() < 100:
            continue
        best = max(auc(X[m, i], Y[m]), 1 - auc(X[m, i], Y[m]))
        print(f"    {k:16s} {best:.3f}")

    print()
    print("=" * 78)
    print("2. DOES THE PREDICTION SEPARATE THE OUTCOME THAT MATTERS?")
    print("=" * 78)
    print("  The out-of-sample probability of an early peak, scored against the low itself.\n")
    p, lo, hi = cluster_ci(U, oof_g, L)
    v = "clear of chance" if lo > 0.5 else "NOT clear of chance"
    print(f"  predicted early peak    -> low   AUC {p:.3f} [{lo:.3f}, {hi:.3f}]  {v}")
    res["pred_to_low"] = dict(auc=p, lo=lo, hi=hi)
    iv = np.array([m["interval"] for m in M])
    p2, lo2, hi2 = cluster_ci(U, -iv, L)
    print(f"  the true interval       -> low   AUC {p2:.3f} [{lo2:.3f}, {hi2:.3f}]"
          "   (the ceiling, unavailable at the commit)")
    res["true_to_low"] = dict(auc=p2, lo=lo2, hi=hi2)

    print("\n  low rate by decile of the predicted probability:")
    q = np.quantile(oof_g, np.linspace(0, 1, 11))
    q = np.unique(q)
    idx = np.clip(np.digitize(oof_g, q[1:-1], right=True), 0, len(q) - 2)
    print(f"    {'decile':>7s} {'n':>6s} {'pred':>7s} {'low rate':>9s} {'true early':>11s}")
    rows_out = []
    for bnum in range(len(q) - 1):
        m = idx == bnum
        if m.sum() < 20:
            continue
        print(f"    {bnum:7d} {m.sum():6d} {oof_g[m].mean():7.3f} {L[m].mean():9.3f} "
              f"{Y[m].mean():11.3f}")
        rows_out.append(dict(b=bnum, n=int(m.sum()), pred=float(oof_g[m].mean()),
                             low=float(L[m].mean()), early=float(Y[m].mean())))
    res["deciles"] = rows_out

    top = oof_g >= np.quantile(oof_g, 0.9)
    print(f"\n  top decile of predicted risk: low rate {L[top].mean():.3f} "
          f"against {L[~top].mean():.3f} elsewhere, base {L.mean():.3f}")
    res["top_decile"] = dict(low=float(L[top].mean()), rest=float(L[~top].mean()))

    print()
    print("=" * 78)
    print("3. WHY THE PREDICTION DOES NOT HELP")
    print("=" * 78)
    bg = X[:, keys.index("bg")]
    print(f"  glucose alone predicts an early peak at {auc(bg, Y):.3f}; the full model reaches "
          f"{auc(oof_g, Y):.3f}.")
    print(f"  correlation between the predicted probability and glucose at commit: "
          f"{np.corrcoef(oof_g, bg)[0, 1]:+.3f}")
    print("\n  splitting the commits by whether the peak was early and whether the model saw it:")
    print(f"\n  {'cell':38s} {'n':>6s} {'low rate':>9s} {'median BG':>10s}")
    pe = oof_g >= np.quantile(oof_g, 0.75)
    res["cells"] = {}
    for name, m in (("truly early, model predicted it", (Y == 1) & pe),
                    ("truly early, model missed it", (Y == 1) & ~pe),
                    ("not early, model predicted early", (Y == 0) & pe),
                    ("not early, model agreed", (Y == 0) & ~pe)):
        if m.sum() < 20:
            continue
        print(f"  {name:38s} {m.sum():6d} {L[m].mean():9.3f} {np.median(bg[m]):10.0f}")
        res["cells"][name] = dict(n=int(m.sum()), low=float(L[m].mean()),
                                  bg=float(np.median(bg[m])))
    print("\n  the true interval against the low, within bands of glucose at commit,")
    print("  which shows it is not merely a restatement of the glucose:")
    print(f"\n  {'glucose':>12s} {'n':>6s} {'AUC':>7s} {'low rate':>9s}")
    res["within_bg"] = []
    for lo_, hi_ in ((0, 120), (120, 150), (150, 180), (180, 400)):
        m = (bg >= lo_) & (bg < hi_)
        if m.sum() < 150:
            continue
        a = auc(-iv[m], L[m])
        print(f"  {lo_:5d}-{hi_:<6d} {m.sum():6d} {a:7.3f} {L[m].mean():9.3f}")
        res["within_bg"].append(dict(lo=lo_, hi=hi_, n=int(m.sum()), auc=a,
                                     low=float(L[m].mean())))

    if args.json:
        json.dump(res, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
