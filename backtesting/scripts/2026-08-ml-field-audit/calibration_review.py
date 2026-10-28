#!/usr/bin/env python3
"""
Why the shipped hypo-risk model is anti-calibrated in its top four deciles.

The field audit established that the model predicts 25 to 54 per cent in its upper deciles
and observes 3 to 6 per cent against a base rate of 3.4. This script asks where that error
lives and what, if anything, would fix it.

An exact offline replay is not available: six of the 53 features the model consumes are not
persisted in the decision table (bg_above_target, direction_num, hour, sug_expectedDelta,
sug_minDelta, time_since_last_smb_min are absent or only partly covered), so the on-device
vector cannot be rebuilt and scored. What can be done without them:

  1. Reliability stratified by current glucose. If the model's error is uniform across
     glucose bands it is a global scale problem. If it concentrates where glucose is benign,
     the model is firing on its non-glucose features and those are what to suspect.

  2. A direct probe of the model asset. Sweep one feature at a time through the exported
     trees with everything else held at cohort medians, and read the response surface. This
     needs no telemetry at all and answers whether the model itself is sane.

  3. What recalibration buys. Fit a monotone map from score to observed frequency and report
     what it does to calibration error, to discrimination, and to how often the 0.30 and 0.60
     consumption thresholds fire. Recalibration cannot repair ranking; the question is whether
     the thresholds are at least landing where they were meant to.

Usage:  python3 calibration_review.py [--json out.json]
"""

import argparse
import json
import os
import sys

import numpy as np
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ml_field_audit import (BOOST_USERS, HYPO_HORIZON_MIN, HYPO_MIN_SPAN_MIN,
                            auc, cgm_series, hypo_onsets, label_hypo)

MODEL_PATHS = [
    os.path.expanduser("~/StudioProjects/Boost-AAPS-core/app/src/main/assets/boost/hypo_risk_model.json"),
    os.path.expanduser("~/StudioProjects/AndroidAPS/app/src/main/assets/boost/hypo_risk_model.json"),
]

RISK_SCALE_THRESHOLD = 0.30
TIER_DOWNGRADE_THRESHOLD = 0.60
BUCKET_MIN = 5


def load_model():
    for p in MODEL_PATHS:
        if os.path.exists(p):
            with open(p) as fh:
                return json.load(fh), p
    raise SystemExit("hypo_risk_model.json not found")


def walk(node, x):
    """Mirrors BoostRiskModel.parseNode/walkTree: a leaf is the key "leaf"."""
    while "leaf" not in node:
        node = node["left"] if x[node["feature"]] <= node["threshold"] else node["right"]
    return node["leaf"]


def score_vector(trees, x):
    """Sigmoid over summed leaf margins, matching BoostRiskModel.score()."""
    raw = sum(walk(t, x) for t in trees)
    return 1.0 / (1.0 + np.exp(-raw))


def fetch(conn):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT ON (d.user_id, to_timestamp(floor(extract(epoch FROM d.ts_utc) / {BUCKET_MIN*60}) * {BUCKET_MIN*60}))
               d.user_id, extract(epoch FROM d.ts_utc), d.cgm_mgdl, d.ml_hypo_risk,
               d.sug_iob, d.iob_activity, d.sug_current_target
        FROM boost_decisions d
        WHERE d.user_id = ANY(%s) AND d.cgm_mgdl IS NOT NULL AND d.ml_hypo_risk IS NOT NULL
        ORDER BY d.user_id,
                 to_timestamp(floor(extract(epoch FROM d.ts_utc) / {BUCKET_MIN*60}) * {BUCKET_MIN*60}),
                 d.ts_utc
    """, (list(BOOST_USERS),))
    out = {}
    for uid, ts, cgm, risk, iob, act, tgt in cur.fetchall():
        f = lambda v: np.nan if v is None else float(v)
        out.setdefault(uid, []).append((float(ts), float(cgm), float(risk), f(iob), f(act), f(tgt)))
    return out


def ece(pred, obs, n):
    """Expected calibration error, weighted by bin population."""
    n = np.asarray(n, dtype=float)
    return float(np.sum(n * np.abs(np.asarray(pred) - np.asarray(obs))) / n.sum())


def reliability(scores, labels, edges):
    rows = []
    idx = np.digitize(scores, edges[1:-1], right=True)
    for b in range(len(edges) - 1):
        m = idx == b
        if m.sum() < 50:
            continue
        rows.append(dict(lo=float(edges[b]), hi=float(edges[b + 1]), n=int(m.sum()),
                         pred=float(scores[m].mean()), obs=float(labels[m].mean())))
    return rows


def isotonic(x, y):
    """Pool-adjacent-violators. Returns a step function fitted on (score, label)."""
    order = np.argsort(x, kind="mergesort")
    xs, ys = x[order], y[order].astype(float)
    w = np.ones(len(ys))
    lvl, wt, bnd = [], [], []
    for i in range(len(ys)):
        lvl.append(ys[i]); wt.append(w[i]); bnd.append(xs[i])
        while len(lvl) > 1 and lvl[-2] > lvl[-1]:
            v2, w2 = lvl.pop(), wt.pop(); b2 = bnd.pop()
            v1, w1 = lvl.pop(), wt.pop(); bnd.pop()
            lvl.append((v1 * w1 + v2 * w2) / (w1 + w2)); wt.append(w1 + w2); bnd.append(b2)
    knots_x, knots_y = np.array(bnd), np.array(lvl)
    return lambda q: np.interp(q, knots_x, knots_y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    model, path = load_model()
    trees, names = model["trees"], model["feature_names"]
    print(f"model: {path}\n  {model['n_trees']} trees, {model['n_features']} features\n")

    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    rows = fetch(conn)
    cgm = cgm_series(conn, 0)

    S, Y, BG, IOB, ACT, TGT, U = [], [], [], [], [], [], []
    for uid, rr in rows.items():
        if uid not in cgm:
            continue
        rr.sort(key=lambda r: r[0])
        ts = np.array([r[0] for r in rr])
        c_ts, c_bg = cgm[uid]
        y = label_hypo(ts, hypo_onsets(c_ts, c_bg, HYPO_MIN_SPAN_MIN), HYPO_HORIZON_MIN)
        S.append(np.array([r[2] for r in rr])); Y.append(y)
        BG.append(np.array([r[1] for r in rr])); IOB.append(np.array([r[3] for r in rr]))
        ACT.append(np.array([r[4] for r in rr])); TGT.append(np.array([r[5] for r in rr]))
        U.append(np.array([uid] * len(rr)))
    S = np.concatenate(S); Y = np.concatenate(Y); BG = np.concatenate(BG)
    IOB = np.concatenate(IOB); ACT = np.concatenate(ACT); TGT = np.concatenate(TGT)
    U = np.concatenate(U)
    print(f"n = {len(S)} scored cycles, base rate {Y.mean():.4f}\n")

    result = {"n": int(len(S)), "base_rate": float(Y.mean())}

    # ---------------------------------------------------------------- 1
    print("=" * 78)
    print("1. WHERE THE ERROR LIVES: reliability within bands of current glucose")
    print("=" * 78)
    print("  If the model were merely mis-scaled, the gap would be similar in every band.")
    edges = np.array([0, .05, .10, .20, .30, .40, .55, 1.01])
    bands = [(0, 80), (80, 100), (100, 140), (140, 180), (180, 400)]
    result["by_bg_band"] = {}
    for lo, hi in bands:
        m = (BG >= lo) & (BG < hi)
        if m.sum() < 500:
            continue
        rr = reliability(S[m], Y[m], edges)
        a = auc(S[m], Y[m])
        print(f"\n  glucose {lo}-{hi} mg/dL   n={m.sum()}  base={Y[m].mean():.4f}  "
              f"AUC={'n/a' if a is None else f'{a:.3f}'}")
        print(f"    {'score band':>14s} {'n':>7s} {'pred':>7s} {'obs':>7s} {'pred/obs':>9s}")
        for r in rr:
            ratio = r['pred'] / r['obs'] if r['obs'] > 0 else float('inf')
            print(f"    {r['lo']:.2f}-{r['hi']:.2f}   {r['n']:7d} {r['pred']:7.3f} {r['obs']:7.3f} "
                  f"{ratio:9.1f}")
        result["by_bg_band"][f"{lo}-{hi}"] = {"n": int(m.sum()), "base": float(Y[m].mean()),
                                              "auc": a, "bins": rr}

    # ---------------------------------------------------------------- 2
    print()
    print("=" * 78)
    print("2. IS THE MODEL ITSELF SANE? one-feature sweeps through the exported trees")
    print("=" * 78)
    print("  All features held at the cohort median; one swept. A hypo model should rise")
    print("  steeply as glucose falls and rise with insulin on board.")
    med = {}
    for i, nm in enumerate(names):
        if nm.startswith("cgm_mgdl"):
            med[i] = float(np.nanmedian(BG))
        elif nm.startswith("iob_iob"):
            med[i] = float(np.nanmedian(IOB))
        elif nm.startswith("iob_activity"):
            med[i] = float(np.nanmedian(ACT))
        else:
            med[i] = 0.0
    base = np.array([med[i] for i in range(len(names))])

    def sweep(feature_prefixes, values, label):
        idxs = [i for i, nm in enumerate(names) if any(nm == p or nm.startswith(p + "_lag")
                                                       for p in feature_prefixes)]
        print(f"\n  sweeping {label}  (touches {len(idxs)} of {len(names)} features)")
        print(f"    {'value':>8s} {'risk':>8s}")
        out = []
        for v in values:
            x = base.copy()
            for i in idxs:
                x[i] = v
            s = score_vector(trees, x)
            out.append((float(v), float(s)))
            print(f"    {v:8.1f} {s:8.4f}")
        return out

    result["sweep_bg"] = sweep(["cgm_mgdl"], [45, 55, 65, 75, 90, 110, 140, 180, 250], "current glucose")
    result["sweep_iob"] = sweep(["iob_iob"], [0, 0.5, 1, 2, 3, 5, 8], "insulin on board")
    result["sweep_act"] = sweep(["iob_activity"], [-0.05, -0.02, 0, 0.02, 0.05, 0.1], "insulin activity")

    # ---------------------------------------------------------------- 3
    print()
    print("=" * 78)
    print("3. WHAT THE HIGH-SCORING CYCLES ACTUALLY LOOK LIKE")
    print("=" * 78)
    q = np.quantile(S, [0.5, 0.9, 0.99])
    print(f"  score quantiles: median {q[0]:.3f}, p90 {q[1]:.3f}, p99 {q[2]:.3f}")
    print(f"\n  {'score band':>14s} {'n':>7s} {'BG mean':>8s} {'BG p10':>8s} {'IOB':>7s} "
          f"{'obs rate':>9s}")
    for lo, hi in ((0, .10), (.10, .30), (.30, .45), (.45, .60), (.60, 1.01)):
        m = (S >= lo) & (S < hi)
        if m.sum() < 50:
            continue
        print(f"    {lo:.2f}-{hi:.2f}   {m.sum():7d} {np.nanmean(BG[m]):8.1f} "
              f"{np.nanpercentile(BG[m],10):8.1f} {np.nanmean(IOB[m]):7.2f} {Y[m].mean():9.4f}")
    result["score_bands"] = q.tolist()

    # ---------------------------------------------------------------- 4
    print()
    print("=" * 78)
    print("4. WHAT RECALIBRATION WOULD BUY")
    print("=" * 78)
    print("  Isotonic fit, held out by user so the map is not fitted on what it scores.")
    users = sorted(set(U.tolist()))
    cal = np.zeros_like(S)
    for u in users:
        te = U == u
        tr = ~te
        if Y[tr].sum() == 0 or te.sum() == 0:
            cal[te] = S[te]
            continue
        f = isotonic(S[tr], Y[tr])
        cal[te] = f(S[te])
    raw_rows = reliability(S, Y, edges)
    cal_rows = reliability(cal, Y, np.array([0, .01, .02, .04, .06, .10, .20, 1.01]))
    print(f"\n  expected calibration error   raw {ece([r['pred'] for r in raw_rows], [r['obs'] for r in raw_rows], [r['n'] for r in raw_rows]):.4f}"
          f"   recalibrated {ece([r['pred'] for r in cal_rows], [r['obs'] for r in cal_rows], [r['n'] for r in cal_rows]):.4f}")
    print(f"  AUC                          raw {auc(S, Y):.3f}   recalibrated {auc(cal, Y):.3f}"
          "   (a monotone map cannot change ranking; this is a sanity check)")
    print(f"\n  firing rates at the shipped thresholds")
    print(f"    riskScale engages (>0.30)  raw {100*np.mean(S > RISK_SCALE_THRESHOLD):6.2f}%"
          f"   recalibrated {100*np.mean(cal > RISK_SCALE_THRESHOLD):6.2f}%")
    print(f"    tier downgrade   (>0.60)   raw {100*np.mean(S > TIER_DOWNGRADE_THRESHOLD):6.2f}%"
          f"   recalibrated {100*np.mean(cal > TIER_DOWNGRADE_THRESHOLD):6.2f}%")
    hi = S > RISK_SCALE_THRESHOLD
    print(f"\n  observed event rate when the damper engages: {Y[hi].mean():.4f}"
          f"   when it does not: {Y[~hi].mean():.4f}   base {Y.mean():.4f}")
    result["recalibration"] = {
        "ece_raw": ece([r['pred'] for r in raw_rows], [r['obs'] for r in raw_rows], [r['n'] for r in raw_rows]),
        "ece_cal": ece([r['pred'] for r in cal_rows], [r['obs'] for r in cal_rows], [r['n'] for r in cal_rows]),
        "auc_raw": auc(S, Y), "auc_cal": auc(cal, Y),
        "fire_raw": float(np.mean(S > RISK_SCALE_THRESHOLD)),
        "fire_cal": float(np.mean(cal > RISK_SCALE_THRESHOLD)),
        "obs_when_damped": float(Y[hi].mean()), "obs_when_not": float(Y[~hi].mean())}

    if args.json:
        json.dump(result, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
