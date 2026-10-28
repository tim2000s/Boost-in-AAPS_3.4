#!/usr/bin/env python3
"""
Does the state estimator see, at the commit, what the commit-to-peak interval sees afterwards?

The interval from commit to glucose peak separates the commits followed by hypoglycaemia, and it
is not anticipable from the ordinary state, because the predictable part of it is driven by
glucose and the harmful part is the residual: early peaks arriving at ordinary glucose, around
131 mg/dL, followed by a low on 35 per cent of occasions.

The state estimator is the one instrument that might reach that residual, and for a reason rather
than by having more features. Its inferred glucose appearance rate is an estimate of how much
carbohydrate is still arriving, which is dose-independent and is exactly the quantity that
distinguishes a meal still climbing from one nearly absorbed. If a commit lands where appearance
has already turned over, the peak is imminent whatever the glucose reads.

Primary comparison, fixed before running: appearance rate at the commit as a fraction of its own
maximum over the preceding thirty minutes, scored against the low. A low fraction means the meal
has passed its absorption peak. Every other quantity examined is listed rather than footnoted.

The estimator has been logging since 2026-07-18 and doses nothing, so this is a clean out-of-sample
question about a shadow component. The sample is 307 commits, which is small; a null here bounds
the effect loosely rather than closing the question.

Usage:  python3 twin_at_commit.py [--json out.json]
"""

import argparse
import json
import sys

import numpy as np
import psycopg2

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from peak_timing import (USERS, PEAK_WINDOW_MIN, LOW_HORIZON_MIN, BUCKET_MIN,
                         auc, cgm_of, low_onsets)

EARLY_CUT_MIN = 10
RA_WINDOW_MIN = 30


def fetch(conn):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT ON (user_id, to_timestamp(floor(extract(epoch FROM ts_utc)/{BUCKET_MIN*60})*{BUCKET_MIN*60}))
               user_id, extract(epoch FROM ts_utc), boostv5_state, cgm_mgdl, sug_iob,
               boosttwin_ra, boosttwin_lo30, boosttwin_lo60, boosttwin_fc30, boosttwin_gi,
               boosttwin_insu, boosttwin_floorbreach, boostv5_finaldose
        FROM boost_decisions
        WHERE user_id = ANY(%s) AND boostv5_state IS NOT NULL AND cgm_mgdl IS NOT NULL
        ORDER BY user_id,
                 to_timestamp(floor(extract(epoch FROM ts_utc)/{BUCKET_MIN*60})*{BUCKET_MIN*60}),
                 ts_utc
    """, (list(USERS),))
    out = {}
    for r in cur.fetchall():
        f = lambda v: np.nan if v is None else (v if isinstance(v, (str, bool)) else float(v))
        out.setdefault(r[0], []).append(dict(
            t=float(r[1]), state=r[2], bg=float(r[3]), iob=f(r[4]), ra=f(r[5]),
            lo30=f(r[6]), lo60=f(r[7]), fc30=f(r[8]), gi=f(r[9]), insu=f(r[10]),
            fb=r[11], dose=f(r[12])))
    for u in out:
        out[u].sort(key=lambda x: x["t"])
    return out


def events(rows, cgm_ts, cgm_bg, lows):
    out = []
    win = RA_WINDOW_MIN * 60
    for k in range(1, len(rows)):
        if rows[k]["state"] != "CONFIRMED" or rows[k - 1]["state"] == "CONFIRMED":
            continue
        r = rows[k]
        if not np.isfinite(r["ra"]):
            continue
        t = r["t"]
        a = np.searchsorted(cgm_ts, t + 1)
        b = np.searchsorted(cgm_ts, t + PEAK_WINDOW_MIN * 60)
        if b - a < 6:
            continue
        seg_t, seg_b = cgm_ts[a - 1:b], cgm_bg[a - 1:b]
        pk = int(np.argmax(seg_b))
        interval = (seg_t[pk] - t) / 60.0
        lo = np.searchsorted(lows, t, side="right")
        hi = np.searchsorted(lows, t + LOW_HORIZON_MIN * 60, side="right")
        # the appearance-rate trajectory over the approach
        hist = [x["ra"] for x in rows[max(0, k - 8):k + 1]
                if t - x["t"] <= win and np.isfinite(x["ra"])]
        if len(hist) < 3:
            continue
        ra_max = max(hist)
        out.append(dict(
            ra=r["ra"],
            ra_frac=(r["ra"] / ra_max) if ra_max > 1e-9 else 1.0,
            ra_drop=float(ra_max - r["ra"]),
            ra_slope=float(hist[-1] - hist[0]),
            lo30=r["lo30"], lo60=r["lo60"], fc30=r["fc30"], gi=r["gi"], insu=r["insu"],
            bg=r["bg"], iob=r["iob"], dose=r["dose"],
            early=int(interval <= EARLY_CUT_MIN),
            interval=interval,
            low=int(hi > lo)))
    return out


def cluster_auc(per_user, key, sign, n=4000, seed=20260813, target="low"):
    us = [u for u in per_user if per_user[u]]
    rng = np.random.default_rng(seed)
    get = lambda ev: ([sign * e[key] for e in ev if np.isfinite(e[key])],
                      [e[target] for e in ev if np.isfinite(e[key])])
    s, y = get([e for u in us for e in per_user[u]])
    if len(set(y)) < 2:
        return None, None, None
    pt = auc(s, y)
    b = []
    for _ in range(n):
        pick = rng.choice(len(us), len(us), replace=True)
        s2, y2 = get([e for k in pick for e in per_user[us[k]]])
        if len(set(y2)) < 2:
            continue
        v = auc(s2, y2)
        if v is not None:
            b.append(v)
    if not b:
        return pt, None, None
    return pt, float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--json", default=None)
    args = ap.parse_args()
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    rows, cgm = fetch(conn), cgm_of(conn)

    per_user = {}
    for u, r in rows.items():
        if u not in cgm:
            continue
        ct, cb = cgm[u]
        ev = events(r, ct, cb, low_onsets(ct, cb))
        if len(ev) >= 10:
            per_user[u] = ev
    allev = [e for u in per_user for e in per_user[u]]
    if not allev:
        print("no commits with estimator fields"); return 1
    print(f"commits with estimator fields: {len(allev)} across {len(per_user)} participants")
    print(f"  low within 3h {np.mean([e['low'] for e in allev]):.3f}   "
          f"peak within {EARLY_CUT_MIN} min {np.mean([e['early'] for e in allev]):.3f}")
    print(f"  per participant: " + ", ".join(f"{u}={len(v)}" for u, v in sorted(per_user.items())))
    res = {"n": len(allev), "n_users": len(per_user),
           "base_low": float(np.mean([e['low'] for e in allev]))}

    print()
    print("=" * 78)
    print("0. WHETHER THE PRIMARY DISCRIMINATOR HAS ANY SPREAD TO TEST")
    print("=" * 78)
    raf = np.array([e["ra_frac"] for e in allev])
    ra = np.array([e["ra"] for e in allev])
    print("  quantiles of appearance / recent max: " +
          " ".join(f"{q}%={np.percentile(raf, q):.3f}" for q in (1, 5, 10, 25, 50, 75, 100)))
    print(f"  at or above 0.95 on {100*np.mean(raf >= 0.95):.1f} per cent of commits")
    print(f"  exactly at its own recent maximum on {100*np.mean(raf > 0.999):.1f} per cent")
    print("  quantiles of the appearance rate itself:   " +
          " ".join(f"{q}%={np.percentile(ra, q):.2f}" for q in (5, 25, 50, 75, 95)))
    res["ra_frac_at_max_pct"] = float(np.mean(raf > 0.999))
    res["ra_frac_p50"] = float(np.median(raf))
    print("\n  The estimator's inferred appearance has essentially never turned over at the")
    print("  moment of commit, so the discriminator this test was built on has no spread and")
    print("  the areas under the curve below cannot be read as a test of it.")

    print()
    print("=" * 78)
    print("1. THE PRIMARY, REPORTED FOR COMPLETENESS")
    print("=" * 78)
    print(f"  A low fraction means appearance has turned over within the last {RA_WINDOW_MIN} min,")
    print("  so the meal is past its absorption peak. Negated, so lower scores higher.\n")
    p, lo, hi = cluster_auc(per_user, "ra_frac", -1.0)
    v = "clear of chance" if (lo is not None and lo > 0.5) else "NOT clear of chance"
    print(f"  appearance fraction -> low   AUC {p:.3f} [{lo:.3f}, {hi:.3f}]  {v}")
    res["primary"] = dict(auc=p, lo=lo, hi=hi)
    print(f"\n  {'fraction band':>16s} {'n':>5s} {'low rate':>9s} {'early rate':>11s} {'median BG':>10s}")
    for a_, b_ in ((0, .25), (.25, .5), (.5, .75), (.75, .95), (.95, 1.01)):
        m = [e for e in allev if a_ <= e["ra_frac"] < b_]
        if len(m) < 15:
            continue
        print(f"  {a_:.2f}-{b_:.2f}      {len(m):5d} {np.mean([e['low'] for e in m]):9.3f} "
              f"{np.mean([e['early'] for e in m]):11.3f} {np.median([e['bg'] for e in m]):10.0f}")

    print()
    print("=" * 78)
    print("2. EVERY ESTIMATOR QUANTITY AT THE COMMIT, AGAINST BOTH TARGETS")
    print("=" * 78)
    print(f"\n  {'quantity':30s} {'-> low':>22s} {'-> early peak':>22s}")
    fields = [("ra_frac", -1.0, "appearance / recent max"),
              ("ra", -1.0, "appearance rate"),
              ("ra_drop", 1.0, "fall in appearance"),
              ("ra_slope", -1.0, "appearance slope"),
              ("lo30", -1.0, "projected low at 30 min"),
              ("lo60", -1.0, "projected low at 60 min"),
              ("fc30", -1.0, "forecast at 30 min"),
              ("gi", 1.0, "glucose in the model"),
              ("insu", 1.0, "insulin in the model"),
              ("bg", 1.0, "glucose at commit (reference)"),
              ("iob", 1.0, "insulin on board (reference)")]
    res["fields"] = {}
    for key, sign, label in fields:
        pl = cluster_auc(per_user, key, sign, target="low")
        pe = cluster_auc(per_user, key, sign, target="early")
        if pl[0] is None:
            continue
        f = lambda t: "  n/a" if t[0] is None or t[1] is None else \
            f"{t[0]:.3f} [{t[1]:.3f},{t[2]:.3f}]"
        star = " *" if (pl[1] is not None and (pl[1] > 0.5 or pl[2] < 0.5)) else "  "
        print(f"  {label:30s} {f(pl):>20s}{star} {f(pe):>20s}")
        res["fields"][label] = dict(low=dict(auc=pl[0], lo=pl[1], hi=pl[2]),
                                    early=dict(auc=pe[0], lo=pe[1], hi=pe[2]))
    print("\n  * marks an interval clear of chance against the low.")

    print()
    print("=" * 78)
    print("3. DOES ANY OF IT REACH THE HARMFUL CELL?")
    print("=" * 78)
    print("  The cell that matters is an early peak arriving at ordinary glucose, which is what")
    print("  a glucose-keyed predictor cannot see. Restricted to commits below 150 mg/dL.\n")
    sub = {u: [e for e in v if e["bg"] < 150] for u, v in per_user.items()}
    sub = {u: v for u, v in sub.items() if len(v) >= 10}
    n_sub = sum(len(v) for v in sub.values())
    if n_sub < 60:
        print(f"  only {n_sub} commits below 150 mg/dL; too few to test")
    else:
        print(f"  {n_sub} commits across {len(sub)} participants, "
              f"low rate {np.mean([e['low'] for u in sub for e in sub[u]]):.3f}\n")
        for key, sign, label in fields[:7]:
            p2 = cluster_auc(sub, key, sign, target="low")
            if p2[0] is None or p2[1] is None:
                continue
            star = " *" if (p2[1] > 0.5 or p2[2] < 0.5) else ""
            print(f"  {label:30s} {p2[0]:.3f} [{p2[1]:.3f}, {p2[2]:.3f}]{star}")
        res["low_bg_subset_n"] = n_sub

    if args.json:
        json.dump(res, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
