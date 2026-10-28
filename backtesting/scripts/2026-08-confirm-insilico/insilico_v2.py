#!/usr/bin/env python3
"""
In-silico confirm trial, per event, with the insulin-effect assumption exposed.

An earlier version of this computed the counterfactual as a running sum over the whole record and
produced a mean glucose in the thousands. The cause is in the kernel: the fraction of a bolus that
has acted rises to one and stays there, so the modelled glucose lift from a removed bolus is a
permanent step. Eighty-four permanent steps of roughly a hundred mg/dL each is where the number
came from. Glucose is a regulated variable that returns toward a set point, so a step that never
decays cannot be carried forward, and no window boundary repairs that: masking simply moves the
discontinuity somewhere else and makes time-weighted percentages unreliable.

This version keeps the linear approximation only where it is defensible, which is inside a single
event, and asks per-confirm questions that do not require summing across the record: does the
nadir that followed this confirm clear 70, and how much higher is the peak.

The assumption underneath is that removing d units raises glucose by ISF x d x acted(t). The record
cannot check it. Across 80 confirms the predicted lowering by the nadir correlates with the
observed peak-to-nadir fall at minus 0.03, because a larger confirm accompanies a larger meal and
the two move together. That is the same confounding that puts the observational dose response near
6 mg/dL per unit against a dithered estimate near 45, and it is why the trial is prospective.

Absolute effect sizes here are therefore not calibrated. What is reported is how the conclusion
moves as the assumed insulin effect is scaled from half to double, so a reader can see which parts
survive the uncertainty and which do not.

Usage:  python3 insilico_v2.py [--user tim] [--days 30] [--reps 400] [--json out.json]
"""

import argparse
import bisect
import datetime as dt
import json
import sys

import numpy as np
import psycopg2

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from insilico_confirm import (LOW, SEVERE, HIGH, ISF_MIN, ISF_MAX, acted, confirms, fetch)

WINDOW_MIN = 240


def event_windows(cts, cbg, ev):
    out = []
    for e in ev:
        i = bisect.bisect_left(cts, e["t"])
        j = bisect.bisect_right(cts, e["t"] + WINDOW_MIN * 60)
        if j - i < 12:
            continue
        out.append(dict(e, i=i, j=j, mins=(cts[i:j] - e["t"]) / 60.0, bg=cbg[i:j],
                        bg_at=e["bg"]))
    return out


def outcome(w, mult, isf_scale=1.0):
    removed = w["dose"] * (1.0 - mult)
    lift = w["isf"] * isf_scale * removed * acted(w["mins"])
    cf = w["bg"] + lift
    return dict(obs_low=int(w["bg"].min() < LOW), cf_low=int(cf.min() < LOW),
                obs_sev=int(w["bg"].min() < SEVERE), cf_sev=int(cf.min() < SEVERE),
                obs_nadir=float(w["bg"].min()), cf_nadir=float(cf.min()),
                obs_peak=float(w["bg"].max()), cf_peak=float(cf.max()),
                new_high=int(cf.max() > HIGH and w["bg"].max() <= HIGH),
                removed=float(removed))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="tim"); ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--reps", type=int, default=400); ap.add_argument("--json", default=None)
    args = ap.parse_args()
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    rows, cts, cbg = fetch(conn, args.user, args.days)
    isf_all = [r["isf"] for r in rows if r["isf"] and ISF_MIN < r["isf"] < ISF_MAX]
    ev = confirms(rows, float(np.median(isf_all)))
    W = event_windows(cts, cbg, ev)
    obs_lows = sum(int(w["bg"].min() < LOW) for w in W)
    obs_sev = sum(int(w["bg"].min() < SEVERE) for w in W)
    print(f"{args.user}, last {args.days} days: {len(W)} confirms with a "
          f"{WINDOW_MIN//60}h window and a delivered dose")
    print(f"  committed {sum(w['dose'] for w in W):.1f} U, median {np.median([w['dose'] for w in W]):.2f} U")
    print(f"  sensitivity at confirm: median {np.median([w['isf'] for w in W]):.0f} mg/dL/U")
    print(f"  windows containing a low: {obs_lows} of {len(W)}, severe {obs_sev}\n")
    res = dict(n=len(W), obs_lows=obs_lows, obs_severe=obs_sev)

    print("=" * 80)
    print("1. RANDOMISED ASSIGNMENT, MULTIPLIER DRAWN PER CONFIRM")
    print("=" * 80)
    print("  Counting windows rather than time-weighted percentages, so no masking is involved.\n")
    rng = np.random.default_rng(20260813)
    print(f"  {'range':>12s} {'lows':>14s} {'severe':>14s} {'new highs':>12s} {'U withheld':>11s}")
    res["arms"] = {}
    for lo, hi in ((0.85, 1.0), (0.7, 1.0), (0.5, 1.0), (0.5, 0.9)):
        L, S, N, U = [], [], [], []
        for _ in range(args.reps):
            m = rng.uniform(lo, hi, len(W))
            o = [outcome(w, mm) for w, mm in zip(W, m)]
            L.append(sum(x["cf_low"] for x in o)); S.append(sum(x["cf_sev"] for x in o))
            N.append(sum(x["new_high"] for x in o)); U.append(sum(x["removed"] for x in o))
        f = lambda a: f"{np.median(a):.0f} [{np.percentile(a,2.5):.0f},{np.percentile(a,97.5):.0f}]"
        print(f"  [{lo:.2f},{hi:.2f}] {f(L):>14s} {f(S):>14s} {f(N):>12s} "
              f"{np.median(U):11.1f}")
        res["arms"][f"{lo}-{hi}"] = dict(lows=float(np.median(L)), severe=float(np.median(S)),
                                         new_highs=float(np.median(N)), removed=float(np.median(U)))
    print(f"\n  observed: {obs_lows} lows, {obs_sev} severe, 0 new highs, 0 U withheld")

    print()
    print("=" * 80)
    print("2. FIXED MULTIPLIER, AND HOW MUCH IT DEPENDS ON THE ASSUMED INSULIN EFFECT")
    print("=" * 80)
    print("  The record cannot calibrate the insulin effect, so it is scaled from half to double.")
    print("  A conclusion that survives the whole row is robust to that; one that does not is not.\n")
    print(f"  {'mult':>6s} {'U off':>7s} " + "".join(f"{'x'+str(s):>22s}" for s in (0.5, 1.0, 2.0)))
    print(f"  {'':>6s} {'':>7s} " + "".join(f"{'lows / severe / new hi':>22s}" for _ in range(3)))
    res["grid"] = []
    for m in (0.95, 0.90, 0.85, 0.80, 0.70, 0.50):
        cells, row = [], dict(mult=m)
        for sc in (0.5, 1.0, 2.0):
            o = [outcome(w, m, sc) for w in W]
            l_, s_, n_ = (sum(x["cf_low"] for x in o), sum(x["cf_sev"] for x in o),
                          sum(x["new_high"] for x in o))
            cells.append(f"{l_:6d} /{s_:4d} /{n_:5d}  ")
            row[f"scale{sc}"] = dict(lows=l_, severe=s_, new_high=n_)
        u = sum(w["dose"] for w in W) * (1 - m)
        print(f"  {m:6.2f} {u:7.1f} " + "".join(f"{c:>22s}" for c in cells))
        res["grid"].append(row)
    print(f"  {'1.00':>6s} {0.0:7.1f} " +
          "".join(f"{f'{obs_lows:6d} /{obs_sev:4d} /{0:5d}  ':>22s}" for _ in range(3)))

    print()
    print("=" * 80)
    print("3. THE CONFIRMS THAT CARRY IT")
    print("=" * 80)
    print("  Halved individually at the recorded sensitivity. Ranked by how far the nadir moves.\n")
    per = []
    for w in W:
        o = outcome(w, 0.5)
        per.append(dict(t=w["t"], dose=w["dose"], isf=w["isf"], bg=w["bg_at"], iob=w["iob"],
                        obs_nadir=o["obs_nadir"], cf_nadir=o["cf_nadir"],
                        lift=o["cf_nadir"] - o["obs_nadir"],
                        rescued=int(o["obs_low"] and not o["cf_low"]),
                        new_high=o["new_high"], obs_peak=o["obs_peak"], cf_peak=o["cf_peak"]))
    per.sort(key=lambda x: -x["rescued"] * 1e6 - x["lift"])
    print(f"  {'when':>16s} {'dose':>5s} {'ISF':>4s} {'BG':>4s} {'IOB':>5s} {'nadir':>6s} "
          f"{'->':>6s} {'peak':>5s} {'->':>5s} {'saved':>6s}")
    for p in per[:14]:
        w_ = dt.datetime.fromtimestamp(p["t"]).strftime("%a %d %H:%M")
        print(f"  {w_:>16s} {p['dose']:5.2f} {p['isf']:4.0f} {(p['bg'] or 0):4.0f} "
              f"{(p['iob'] or 0):5.2f} {p['obs_nadir']:6.0f} {p['cf_nadir']:6.0f} "
              f"{p['obs_peak']:5.0f} {p['cf_peak']:5.0f} {'yes' if p['rescued'] else '':>6s}")
    res["per_confirm"] = per
    print(f"\n  halving every confirm individually rescues "
          f"{sum(p['rescued'] for p in per)} of the {obs_lows} windows containing a low")
    print(f"  and creates {sum(p['new_high'] for p in per)} windows newly above 180")

    if args.json:
        json.dump(res, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
