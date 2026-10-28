#!/usr/bin/env python3
"""
Follow-up to the calibration review: what the tenth decile actually is.

The audit established that the shipped hypo model discriminates (0.655, beating the glucose
baseline by 0.068) but that its top decile predicts 0.392 and observes 0.072. Three
explanations were left open. This script separates them.

  A. State check. The model, probed directly, returns above 0.30 only at glucose below about
     80 mg/dL. If the cycles actually scoring above 0.30 in the field sit at that glucose, the
     model is reading its input correctly and the miscalibration is about the outcome rate at
     that state, not about the score. If they sit at normal glucose, the feature vector is wrong.

  B. Prior shift. If the state is right and the event is simply rarer here than in training,
     the model is well-ranked and mis-scaled, which is a recalibration problem rather than a
     model problem. Measured by comparing the observed rate at a given state against what the
     score claims, and by asking whether a single monotone map fixes it.

  C. Cold start. 36 of the 53 features come from a persisted six-cycle ring buffer. On an empty
     buffer the lag values default to the current cycle's value, where the training pipeline
     used a median fill. Cycles shortly after a gap in the decision series are running on a
     partly-cold buffer, so if that path is wrong their scores should differ systematically
     from steady-state cycles at the same glucose.

  D. The firing spread. The damper engages on 0.49 to 27.7 per cent of cycles depending on the
     participant. Whether that is a defect or correct behaviour depends on whether it tracks
     the participant's own hypoglycaemia rate.

Restricted throughout to the current model generation, from 2026-06-29.

Usage:  python3 calibration_followup.py [--json out.json]
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

ERA_START = "2026-06-29"
RISK_SCALE_THRESHOLD = 0.30
BUCKET_MIN = 5
GAP_SECONDS = 30 * 60      # a break in the decision series long enough to cool the ring buffer
COLD_CYCLES = 6            # the buffer depth, so this many cycles after a gap are partly cold


def fetch(conn):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT ON (d.user_id, to_timestamp(floor(extract(epoch FROM d.ts_utc) / {BUCKET_MIN*60}) * {BUCKET_MIN*60}))
               d.user_id, extract(epoch FROM d.ts_utc), d.cgm_mgdl, d.ml_hypo_risk, d.sug_iob
        FROM boost_decisions d
        WHERE d.user_id = ANY(%s) AND d.cgm_mgdl IS NOT NULL
          AND d.ml_hypo_risk IS NOT NULL AND d.ts_utc >= '{ERA_START}'
        ORDER BY d.user_id,
                 to_timestamp(floor(extract(epoch FROM d.ts_utc) / {BUCKET_MIN*60}) * {BUCKET_MIN*60}),
                 d.ts_utc
    """, (list(BOOST_USERS),))
    out = {}
    for uid, ts, cgm, risk, iob in cur.fetchall():
        out.setdefault(uid, []).append(
            (float(ts), float(cgm), float(risk), np.nan if iob is None else float(iob)))
    for u in out:
        out[u].sort(key=lambda r: r[0])
    return out


def boot_ci(values, n=2000, seed=20260813):
    rng = np.random.default_rng(seed)
    v = np.asarray(values, dtype=float)
    if len(v) < 2:
        return float("nan"), float("nan")
    b = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(n)]
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    rows = fetch(conn)
    cgm = cgm_series(conn, 0)

    per_user = {}
    S, Y, BG, IOB, COLD, U = [], [], [], [], [], []
    for uid, rr in rows.items():
        if uid not in cgm:
            continue
        ts = np.array([r[0] for r in rr])
        bg = np.array([r[1] for r in rr])
        s = np.array([r[2] for r in rr])
        iob = np.array([r[3] for r in rr])
        c_ts, c_bg = cgm[uid]
        y = label_hypo(ts, hypo_onsets(c_ts, c_bg, HYPO_MIN_SPAN_MIN), HYPO_HORIZON_MIN)
        # a cycle is "cold" if fewer than COLD_CYCLES contiguous cycles precede it
        gap = np.diff(ts, prepend=ts[0] - 1e9) > GAP_SECONDS
        since = np.zeros(len(ts), dtype=int)
        run = 10 ** 6
        for i in range(len(ts)):
            run = 0 if gap[i] else run + 1
            since[i] = run
        cold = since < COLD_CYCLES
        per_user[uid] = dict(s=s, y=y, bg=bg, cold=cold)
        S.append(s); Y.append(y); BG.append(bg); IOB.append(iob); COLD.append(cold)
        U.append(np.array([uid] * len(s)))
    S = np.concatenate(S); Y = np.concatenate(Y); BG = np.concatenate(BG)
    IOB = np.concatenate(IOB); COLD = np.concatenate(COLD); U = np.concatenate(U)
    print(f"era from {ERA_START}: n = {len(S)} scored cycles, base rate {Y.mean():.4f}\n")
    res = {"n": int(len(S)), "base_rate": float(Y.mean())}

    # ------------------------------------------------------------------ A
    print("=" * 78)
    print("A. WHAT STATE ARE THE HIGH-SCORING CYCLES IN?")
    print("=" * 78)
    print("  The model probed directly returns 0.44 at 75 mg/dL, 0.17 at 90 and 0.08 at 140.")
    print("  If field cycles scoring high sit at that glucose, the input is being read correctly.")
    print(f"\n  {'score band':>12s} {'n':>7s} {'BG mean':>8s} {'BG p10':>7s} {'BG p90':>7s} "
          f"{'IOB':>6s} {'observed':>9s}")
    bands = [(0, .05), (.05, .10), (.10, .30), (.30, .45), (.45, .60), (.60, 1.01)]
    res["state_by_band"] = []
    for lo, hi in bands:
        m = (S >= lo) & (S < hi)
        if m.sum() < 30:
            continue
        row = dict(lo=lo, hi=hi, n=int(m.sum()), bg=float(np.nanmean(BG[m])),
                   bg10=float(np.nanpercentile(BG[m], 10)), bg90=float(np.nanpercentile(BG[m], 90)),
                   iob=float(np.nanmean(IOB[m])), obs=float(Y[m].mean()))
        print(f"  {lo:.2f}-{hi:.2f}   {row['n']:7d} {row['bg']:8.1f} {row['bg10']:7.1f} "
              f"{row['bg90']:7.1f} {row['iob']:6.2f} {row['obs']:9.4f}")
        res["state_by_band"].append(row)

    # ------------------------------------------------------------------ B
    print()
    print("=" * 78)
    print("B. IS IT A PRIOR SHIFT? observed rate at the state the model thinks it is in")
    print("=" * 78)
    print("  Within a narrow glucose band the state is held roughly fixed, so what remains is")
    print("  whether the event rate at that state matches what the score claims.")
    print(f"\n  {'glucose':>12s} {'n':>7s} {'mean score':>11s} {'observed':>9s} {'ratio':>7s} "
          f"{'AUC in band':>12s}")
    res["by_bg"] = []
    for lo, hi in ((0, 70), (70, 80), (80, 90), (90, 110), (110, 140), (140, 400)):
        m = (BG >= lo) & (BG < hi)
        if m.sum() < 200:
            continue
        a = auc(S[m], Y[m])
        obs = float(Y[m].mean()); pred = float(S[m].mean())
        ratio = pred / obs if obs > 0 else float("inf")
        print(f"  {lo:4d}-{hi:<7d} {m.sum():7d} {pred:11.3f} {obs:9.4f} {ratio:7.1f} "
              f"{'n/a' if a is None else f'{a:12.3f}'}")
        res["by_bg"].append(dict(lo=lo, hi=hi, n=int(m.sum()), pred=pred, obs=obs,
                                 ratio=None if obs == 0 else ratio, auc=a))

    # ------------------------------------------------------------------ C
    print()
    print("=" * 78)
    print("C. COLD START: cycles running on a partly-filled ring buffer")
    print("=" * 78)
    print(f"  A cycle is cold if fewer than {COLD_CYCLES} contiguous cycles precede it, taking a")
    print(f"  break of {GAP_SECONDS//60} min as breaking contiguity. Compared within glucose bands so")
    print("  the comparison is not confounded by when gaps happen.")
    print(f"\n  cold cycles: {COLD.sum()} of {len(COLD)} ({100*COLD.mean():.1f}%)")
    print(f"\n  {'glucose':>12s} {'n cold':>7s} {'n warm':>7s} {'score cold':>11s} "
          f"{'score warm':>11s} {'difference':>22s}")
    res["cold_start"] = []
    for lo, hi in ((0, 80), (80, 110), (110, 140), (140, 400)):
        mb = (BG >= lo) & (BG < hi)
        c, w = mb & COLD, mb & ~COLD
        if c.sum() < 100 or w.sum() < 100:
            continue
        d = float(S[c].mean() - S[w].mean())
        rng = np.random.default_rng(20260813)
        boots = [S[c][rng.integers(0, c.sum(), c.sum())].mean()
                 - S[w][rng.integers(0, w.sum(), w.sum())].mean() for _ in range(2000)]
        dlo, dhi = np.percentile(boots, [2.5, 97.5])
        flag = "" if dlo <= 0 <= dhi else "   <== differs"
        print(f"  {lo:4d}-{hi:<7d} {c.sum():7d} {w.sum():7d} {S[c].mean():11.3f} "
              f"{S[w].mean():11.3f} {d:+8.3f} [{dlo:+.3f},{dhi:+.3f}]{flag}")
        res["cold_start"].append(dict(lo=lo, hi=hi, n_cold=int(c.sum()), n_warm=int(w.sum()),
                                      score_cold=float(S[c].mean()), score_warm=float(S[w].mean()),
                                      delta=d, lo_ci=float(dlo), hi_ci=float(dhi)))
    ac, aw = auc(S[COLD], Y[COLD]), auc(S[~COLD], Y[~COLD])
    print(f"\n  discrimination on cold cycles {ac if ac is None else round(ac,3)}, "
          f"on warm cycles {aw if aw is None else round(aw,3)}")
    res["auc_cold"], res["auc_warm"] = ac, aw

    # ------------------------------------------------------------------ D
    print()
    print("=" * 78)
    print("D. IS THE FIRING SPREAD A DEFECT OR CORRECT BEHAVIOUR?")
    print("=" * 78)
    print("  The damper engaging more often for a participant who goes low more often is the")
    print("  intended behaviour, not a fault. Firing rate against each participant's own rate.")
    print(f"\n  {'user':6s} {'n':>7s} {'own hypo rate':>14s} {'fires >0.30':>12s} {'AUC':>7s}")
    fr, br = [], []
    res["per_user"] = {}
    for uid in sorted(per_user):
        d = per_user[uid]
        f = float((d["s"] > RISK_SCALE_THRESHOLD).mean())
        b = float(d["y"].mean())
        a = auc(d["s"], d["y"])
        fr.append(f); br.append(b)
        print(f"  {uid:6s} {len(d['s']):7d} {b:14.4f} {100*f:11.2f}% "
              f"{'n/a' if a is None else f'{a:7.3f}'}")
        res["per_user"][uid] = dict(n=len(d["s"]), base=b, fire=f, auc=a)
    fr, br = np.array(fr), np.array(br)
    rho = float(np.corrcoef(fr, br)[0, 1])
    rng = np.random.default_rng(20260813)
    boots = []
    for _ in range(5000):
        k = rng.integers(0, len(fr), len(fr))
        if len(set(k.tolist())) < 3:
            continue
        c = np.corrcoef(fr[k], br[k])[0, 1]
        if np.isfinite(c):
            boots.append(c)
    rlo, rhi = np.percentile(boots, [2.5, 97.5])
    verdict = ("tracks the participant's own risk" if rlo > 0
               else "does NOT track the participant's own risk")
    print(f"\n  correlation between firing rate and own hypo rate: {rho:+.3f} "
          f"[{rlo:+.3f}, {rhi:+.3f}]  -> {verdict}")
    res["fire_vs_base_rho"] = dict(rho=rho, lo=float(rlo), hi=float(rhi))

    # ------------------------------------------------------------------ E
    print()
    print("=" * 78)
    print("E. WHAT A RE-PLACED THRESHOLD LOOKS LIKE")
    print("=" * 78)
    print("  The 0.30 cut was set on the previous model. Quantiles of the current distribution")
    print("  say where an equivalently rare cut now sits.")
    qs = [50, 75, 90, 95, 99, 99.5]
    print(f"\n  {'quantile':>10s} {'score':>8s} {'fires':>8s} {'observed rate above':>20s}")
    res["quantiles"] = []
    for q in qs:
        t = float(np.percentile(S, q))
        m = S > t
        obs = float(Y[m].mean()) if m.sum() else float("nan")
        print(f"  {q:9.1f}% {t:8.3f} {100*m.mean():7.2f}% {obs:20.4f}")
        res["quantiles"].append(dict(q=q, threshold=t, fires=float(m.mean()), obs=obs))
    m30 = S > RISK_SCALE_THRESHOLD
    print(f"\n  at the shipped 0.30 cut: fires {100*m30.mean():.2f}%, "
          f"observed rate above {Y[m30].mean():.4f}, below {Y[~m30].mean():.4f}, "
          f"base {Y.mean():.4f}")
    lift = Y[m30].mean() / Y.mean() if Y.mean() else float("nan")
    print(f"  lift of the damped population over base: {lift:.2f}x")
    res["shipped_cut"] = dict(fires=float(m30.mean()), obs_above=float(Y[m30].mean()),
                              obs_below=float(Y[~m30].mean()), lift=float(lift))

    # ------------------------------------------------------------------ F
    print()
    print("=" * 78)
    print("F. WHAT THE COLD PATH COSTS AT THE OPERATING POINT")
    print("=" * 78)
    print("  Restricted to normal glucose, where the model probed directly returns well below")
    print("  the 0.30 cut, so any crossing there is the feature vector rather than the glucose.")
    print(f"\n  {'score band':>12s} {'n':>7s} {'cold share':>11s} {'BG mean':>8s}")
    res["cold_share_by_band"] = []
    for lo, hi in bands:
        m = (S >= lo) & (S < hi)
        if m.sum() < 30:
            continue
        print(f"  {lo:.2f}-{hi:.2f}   {m.sum():7d} {100*COLD[m].mean():10.1f}% "
              f"{np.nanmean(BG[m]):8.1f}")
        res["cold_share_by_band"].append(dict(lo=lo, hi=hi, n=int(m.sum()),
                                              cold=float(COLD[m].mean())))
    norm = (BG >= 100) & (BG < 160)
    cc, ww = norm & COLD, norm & ~COLD
    pc = float((S[cc] > RISK_SCALE_THRESHOLD).mean())
    pw = float((S[ww] > RISK_SCALE_THRESHOLD).mean())
    rng = np.random.default_rng(20260813)
    boots = [(S[cc][rng.integers(0, cc.sum(), cc.sum())] > RISK_SCALE_THRESHOLD).mean()
             - (S[ww][rng.integers(0, ww.sum(), ww.sum())] > RISK_SCALE_THRESHOLD).mean()
             for _ in range(2000)]
    dlo, dhi = np.percentile(boots, [2.5, 97.5])
    print(f"\n  glucose 100-160 mg/dL")
    print(f"    cold cycles cross 0.30 on {100*pc:.2f}% of cycles (n={cc.sum()})")
    print(f"    warm cycles cross 0.30 on {100*pw:.2f}% of cycles (n={ww.sum()})")
    print(f"    difference {100*(pc-pw):+.2f} points [{100*dlo:+.2f}, {100*dhi:+.2f}], "
          f"ratio {pc/pw:.2f}x")
    res["cold_operating_point"] = dict(cold=pc, warm=pw, ratio=pc / pw,
                                       lo=float(dlo), hi=float(dhi))

    if args.json:
        json.dump(res, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
