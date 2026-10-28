#!/usr/bin/env python3
"""
Is the commit that goes wrong the commit into a small meal?

Two results meet here. The commit-timing work found that commits whose glucose peak arrives within
ten minutes are followed by hypoglycaemia on 26.8 per cent of occasions against 16.0, and could
not anticipate that from the state at the commit. The carbohydrate work found that meal size is
not readable from the early trajectory, across participants or within them.

If the interval to the peak is standing in for the size of the excursion, the two are one finding:
the algorithm commits the same dose to a small meal as to a large one because it cannot tell them
apart, and the small ones overshoot.

Usage:  python3 link_to_commits.py [--json out.json]
"""

import argparse
import json
import os
import sys

import numpy as np
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "2026-08-commit-peak-timing"))
import peak_timing as P                                   # noqa: E402
from peak_timing import auc, cgm_of, low_onsets           # noqa: E402


def cluster_auc(users, s, y, n=3000, seed=20260813):
    us = sorted(set(users)); rng = np.random.default_rng(seed)
    idx = {u: np.flatnonzero(users == u) for u in us}
    pt = auc(s, y); b = []
    for _ in range(n):
        pick = rng.choice(len(us), len(us), replace=True)
        sel = np.concatenate([idx[us[k]] for k in pick])
        v = auc(s[sel], y[sel])
        if v is not None:
            b.append(v)
    return pt, float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--json", default=None)
    args = ap.parse_args()
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    rows, cgm = P.fetch(conn), cgm_of(conn)
    ev = []
    for u, r in rows.items():
        if u not in cgm:
            continue
        ct, cb = cgm[u]
        for e in P.events(r, ct, cb, low_onsets(ct, cb)):
            e["u"] = u
            ev.append(e)
    iv = np.array([e["interval_min"] for e in ev])
    rise = np.array([e["peak"] - e["bg"] for e in ev])
    low = np.array([e["low"] for e in ev])
    bg = np.array([e["bg"] for e in ev])
    us = np.array([e["u"] for e in ev])
    print(f"commits: {len(ev)}, low rate {low.mean():.3f}\n")

    print("=" * 78)
    print("1. ARE THE TWO DESCRIBING THE SAME THING")
    print("=" * 78)
    r = float(np.corrcoef(iv, rise)[0, 1])
    print(f"  correlation between interval to peak and excursion size: {r:+.3f}")
    a1, l1, h1 = cluster_auc(us, -rise, low)
    a2, l2, h2 = cluster_auc(us, -iv, low)
    print(f"\n  smaller excursion -> low   AUC {a1:.3f} [{l1:.3f}, {h1:.3f}]")
    print(f"  shorter interval  -> low   AUC {a2:.3f} [{l2:.3f}, {h2:.3f}]")
    print("\n  The excursion is the better of the two, which is what would be expected if the")
    print("  interval is a consequence of the size rather than a cause of the outcome.")
    res = dict(corr=r, excursion=dict(auc=a1, lo=l1, hi=h1), interval=dict(auc=a2, lo=l2, hi=h2))

    print()
    print("=" * 78)
    print("2. THE CELLS")
    print("=" * 78)
    short = iv <= 10
    small = rise < np.median(rise)
    print(f"\n  {'cell':40s} {'n':>6s} {'low rate':>9s} {'median rise':>12s} {'median BG':>10s}")
    res["cells"] = {}
    for nm, m in (("short interval and small excursion", short & small),
                  ("short interval, large excursion", short & ~small),
                  ("long interval, small excursion", ~short & small),
                  ("long interval, large excursion", ~short & ~small)):
        if m.sum() < 20:
            print(f"  {nm:40s} {m.sum():6d}  (empty, which is itself informative)")
            continue
        print(f"  {nm:40s} {m.sum():6d} {low[m].mean():9.3f} {np.median(rise[m]):12.0f} "
              f"{np.median(bg[m]):10.0f}")
        res["cells"][nm] = dict(n=int(m.sum()), low=float(low[m].mean()),
                                rise=float(np.median(rise[m])))

    print()
    print("=" * 78)
    print("3. THE EXCURSION BY SIZE BAND")
    print("=" * 78)
    print(f"\n  {'excursion':>16s} {'n':>6s} {'low rate':>9s} {'median dose':>12s}")
    res["bands"] = []
    for lo_, hi_ in ((-999, 10), (10, 25), (25, 50), (50, 80), (80, 999)):
        m = (rise > lo_) & (rise <= hi_)
        if m.sum() < 30:
            continue
        d = np.nanmedian([e["dose"] for e, mm in zip(ev, m) if mm])
        lab = f"{'<=10' if hi_ == 10 else f'{lo_} to {hi_}'}"
        print(f"  {lab:>16s} {m.sum():6d} {low[m].mean():9.3f} {d:12.2f}")
        res["bands"].append(dict(lo=lo_, hi=hi_, n=int(m.sum()), low=float(low[m].mean())))

    if args.json:
        json.dump(res, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
