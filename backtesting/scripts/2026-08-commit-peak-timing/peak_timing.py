#!/usr/bin/env python3
"""
Does a commit landing at or after the glucose peak predict the hypoglycaemia that follows?

A separate analysis tested whether a commit approached with decaying delta_accl predicts the
crash, and returned a null across nine threshold variants. That metric is one hundred times the
difference between the current change and its short average, divided by that average floored at
two, so on a steady or steepening rise it reads near zero by construction. An event on
2026-08-13 read -2.4, -1.4, -1.9 and -0.6 across the approach while the raw five-minute
increments were +12, +14 and +21, and glucose peaked one cycle after the commit. The metric
called that approach flat; the glucose called it the steepest yet.

This asks the question the metric could not: how long after the commit does glucose peak, and
does a short interval predict the low. The mechanism, if there is one, is that a commit landing
near the peak delivers insulin against carbohydrate that has already been absorbed.

Primary comparison, fixed before running: commits whose peak falls at or within 10 minutes of the
commit, against commits whose peak is later. Secondary: the continuous interval scored as a
predictor. Every additional variant examined is listed in the output rather than in a footnote,
because a discriminator hunted across enough cuts of the same events will eventually clear.

The identification caveat applies throughout. This is an association measured on observed
outcomes; nothing here establishes that a smaller dose at those commits would have avoided the
low.

Usage:  python3 peak_timing.py [--json out.json]
"""

import argparse
import json
import sys

import numpy as np
import psycopg2

USERS = ("A", "B", "C", "D", "E", "F", "H", "I", "tim")
PEAK_WINDOW_MIN = 180      # look this far ahead for the peak
LOW_HORIZON_MIN = 180      # and this far ahead for the outcome
LOW_MGDL = 70.0
LOW_SUSTAIN_MIN = 10
PRIMARY_CUT_MIN = 10
BUCKET_MIN = 5


def fetch(conn):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT ON (user_id, to_timestamp(floor(extract(epoch FROM ts_utc)/{BUCKET_MIN*60})*{BUCKET_MIN*60}))
               user_id, extract(epoch FROM ts_utc), boostv5_state, cgm_mgdl,
               boostv5_finaldose, sug_iob, boostv5_score, delta_acceleration
        FROM boost_decisions
        WHERE user_id = ANY(%s) AND boostv5_state IS NOT NULL AND cgm_mgdl IS NOT NULL
        ORDER BY user_id,
                 to_timestamp(floor(extract(epoch FROM ts_utc)/{BUCKET_MIN*60})*{BUCKET_MIN*60}),
                 ts_utc
    """, (list(USERS),))
    out = {}
    for u, t, st, bg, dose, iob, sc, da in cur.fetchall():
        f = lambda v: np.nan if v is None else float(v)
        out.setdefault(u, []).append((float(t), st, float(bg), f(dose), f(iob), f(sc), f(da)))
    for u in out:
        out[u].sort(key=lambda r: r[0])
    return out


def cgm_of(conn):
    cur = conn.cursor()
    cur.execute("""SELECT user_id, extract(epoch FROM ts_utc), cgm_mgdl FROM boost_cgm
                   WHERE user_id = ANY(%s) AND cgm_mgdl IS NOT NULL ORDER BY user_id, ts_utc""",
                (list(USERS),))
    o = {}
    for u, t, b in cur.fetchall():
        o.setdefault(u, ([], []))
        o[u][0].append(float(t)); o[u][1].append(float(b))
    return {u: (np.array(a), np.array(b)) for u, (a, b) in o.items()}


def low_onsets(ts, bg):
    out, i, n = [], 0, len(bg)
    while i < n:
        if bg[i] < LOW_MGDL:
            j = i
            while j + 1 < n and bg[j + 1] < LOW_MGDL and ts[j + 1] - ts[j] <= 900:
                j += 1
            if ts[j] - ts[i] >= LOW_SUSTAIN_MIN * 60:
                out.append(ts[i])
            i = j + 1
        else:
            i += 1
    return np.array(out, dtype=float)


def events(rows, cgm_ts, cgm_bg, lows):
    """One event per entry into CONFIRMED, which is where the committed dose fires."""
    out = []
    for k in range(1, len(rows)):
        if rows[k][1] != "CONFIRMED" or rows[k - 1][1] == "CONFIRMED":
            continue
        t = rows[k][0]
        a = np.searchsorted(cgm_ts, t - 60)
        b = np.searchsorted(cgm_ts, t + PEAK_WINDOW_MIN * 60)
        if b - a < 6:
            continue
        seg_t, seg_b = cgm_ts[a:b], cgm_bg[a:b]
        pk = int(np.argmax(seg_b))
        # the approach: the three five-minute increments before the commit
        pa = np.searchsorted(cgm_ts, t - 20 * 60)
        approach = np.diff(cgm_bg[pa:a + 1]) if a + 1 - pa >= 2 else np.array([0.0])
        lo = np.searchsorted(lows, t, side="right")
        hi = np.searchsorted(lows, t + LOW_HORIZON_MIN * 60, side="right")
        out.append(dict(
            t=t,
            interval_min=(seg_t[pk] - t) / 60.0,
            peak=float(seg_b[pk]),
            bg=float(rows[k][2]),
            dose=rows[k][3],
            iob=rows[k][4],
            score=rows[k][5],
            delta_accl=rows[k][6],
            last_inc=float(approach[-1]),
            rising_hardest=bool(len(approach) >= 2 and approach[-1] >= approach.max()),
            low=int(hi > lo)))
    return out


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


def cluster_boot(per_user, fn, n=4000, seed=20260813):
    us = [u for u in per_user if per_user[u]]
    rng = np.random.default_rng(seed)
    pt = fn([e for u in us for e in per_user[u]])
    b = []
    for _ in range(n):
        pick = rng.choice(len(us), len(us), replace=True)
        v = fn([e for k in pick for e in per_user[us[k]]])
        if v is not None and np.isfinite(v):
            b.append(v)
    if not b:
        return pt, None, None
    return pt, float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def rate_diff(ev, pred):
    a = [e["low"] for e in ev if pred(e)]
    b = [e["low"] for e in ev if not pred(e)]
    if not a or not b:
        return None
    return float(np.mean(a) - np.mean(b))


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
        if len(ev) >= 15:
            per_user[u] = ev
    allev = [e for u in per_user for e in per_user[u]]
    print(f"commits: {len(allev)} across {len(per_user)} participants, "
          f"low within 3h {np.mean([e['low'] for e in allev]):.3f}\n")
    res = {"n": len(allev), "n_users": len(per_user)}

    print("=" * 78)
    print("1. HOW LONG AFTER THE COMMIT DOES GLUCOSE PEAK")
    print("=" * 78)
    iv = np.array([e["interval_min"] for e in allev])
    print(f"  quantiles (min): p10 {np.percentile(iv,10):.0f}  p25 {np.percentile(iv,25):.0f}  "
          f"median {np.median(iv):.0f}  p75 {np.percentile(iv,75):.0f}  p90 {np.percentile(iv,90):.0f}")
    print(f"  at or before the commit: {100*np.mean(iv<=0):.1f}%   within 10 min: {100*np.mean(iv<=10):.1f}%")
    print(f"\n  {'interval':>14s} {'n':>6s} {'low rate':>9s} {'median dose':>12s} {'median BG':>10s}")
    for lo, hi in ((-999, 0), (0, 10), (10, 20), (20, 40), (40, 80), (80, 999)):
        m = [e for e in allev if lo < e["interval_min"] <= hi]
        if len(m) < 15:
            continue
        lab = f"{'<=0' if hi==0 else f'{lo}-{hi}'}"
        print(f"  {lab:>14s} {len(m):6d} {np.mean([e['low'] for e in m]):9.3f} "
              f"{np.nanmedian([e['dose'] for e in m]):12.2f} {np.median([e['bg'] for e in m]):10.0f}")
    res["interval_quantiles"] = [float(np.percentile(iv, q)) for q in (10, 25, 50, 75, 90)]

    print()
    print("=" * 78)
    print("2. PRIMARY COMPARISON, FIXED BEFORE RUNNING")
    print("=" * 78)
    print(f"  peak at or within {PRIMARY_CUT_MIN} min of the commit, against later.\n")
    pu = {u: per_user[u] for u in per_user}
    pred = lambda e: e["interval_min"] <= PRIMARY_CUT_MIN
    early = [e for e in allev if pred(e)]; late = [e for e in allev if not pred(e)]
    d, lo, hi = cluster_boot(pu, lambda ev: rate_diff(ev, pred))
    print(f"  peak within {PRIMARY_CUT_MIN} min : n={len(early):5d}  low rate {np.mean([e['low'] for e in early]):.3f}")
    print(f"  peak later            : n={len(late):5d}  low rate {np.mean([e['low'] for e in late]):.3f}")
    verdict = "distinguishable" if (lo is not None and (lo > 0 or hi < 0)) else "NOT distinguishable from zero"
    print(f"  difference {d:+.3f} [{lo:+.3f}, {hi:+.3f}]  -> {verdict}")
    res["primary"] = dict(n_early=len(early), n_late=len(late),
                          rate_early=float(np.mean([e['low'] for e in early])),
                          rate_late=float(np.mean([e['low'] for e in late])),
                          diff=d, lo=lo, hi=hi)

    print()
    print("=" * 78)
    print("3. THE CONTINUOUS INTERVAL AS A PREDICTOR, AND WHAT IT ADDS")
    print("=" * 78)
    print("  Negated so that a shorter interval scores higher, and compared against the two")
    print("  quantities already available at the commit.\n")
    res["auc"] = {}
    for name, key, sign in (("shorter interval", "interval_min", -1.0),
                            ("committed dose", "dose", 1.0),
                            ("glucose at commit", "bg", 1.0),
                            ("insulin on board", "iob", 1.0),
                            ("delta_accl (the retired metric)", "delta_accl", -1.0)):
        f = lambda ev, k=key, s=sign: auc([s * e[k] for e in ev if np.isfinite(e[k])],
                                          [e["low"] for e in ev if np.isfinite(e[k])])
        p, l, h = cluster_boot(pu, f)
        if p is None:
            continue
        v = "clear of chance" if (l is not None and (l > 0.5 or h < 0.5)) else "not clear of chance"
        print(f"  {name:34s} {p:.3f} [{l:.3f}, {h:.3f}]  {v}")
        res["auc"][name] = dict(auc=p, lo=l, hi=h)

    print()
    print("=" * 78)
    print("4. EVERY OTHER VARIANT EXAMINED")
    print("=" * 78)
    variants = [
        ("peak at or before the commit", lambda e: e["interval_min"] <= 0),
        ("peak within 5 min", lambda e: e["interval_min"] <= 5),
        ("peak within 15 min", lambda e: e["interval_min"] <= 15),
        ("peak within 20 min", lambda e: e["interval_min"] <= 20),
        ("peak within 30 min", lambda e: e["interval_min"] <= 30),
        ("last increment was the largest of the approach", lambda e: e["rising_hardest"]),
        ("peak within 10 min AND dose >= 2 U", lambda e: e["interval_min"] <= 10 and e["dose"] >= 2),
        ("peak within 10 min AND glucose >= 180", lambda e: e["interval_min"] <= 10 and e["bg"] >= 180),
        ("peak rise over the commit < 20 mg/dL", lambda e: (e["peak"] - e["bg"]) < 20),
    ]
    res["variants"] = {}
    for name, pr in variants:
        n_hit = sum(1 for e in allev if pr(e))
        if n_hit < 20 or n_hit > len(allev) - 20:
            print(f"  {name:48s} n={n_hit:5d}  (too few either side)")
            continue
        d, l, h = cluster_boot(pu, lambda ev, p=pr: rate_diff(ev, p))
        flag = "" if (l is None or (l <= 0 <= h)) else "   <== clears zero"
        print(f"  {name:48s} n={n_hit:5d}  {d:+.3f} [{l:+.3f}, {h:+.3f}]{flag}")
        res["variants"][name] = dict(n=n_hit, diff=d, lo=l, hi=h)

    print()
    print("=" * 78)
    print("5. PER PARTICIPANT, PRIMARY CUT")
    print("=" * 78)
    print(f"\n  {'user':6s} {'commits':>8s} {'early':>6s} {'rate early':>11s} {'rate late':>10s} {'diff':>8s}")
    res["per_user"] = {}
    for u in sorted(per_user):
        ev = per_user[u]
        a = [e["low"] for e in ev if pred(e)]; b = [e["low"] for e in ev if not pred(e)]
        if not a or not b:
            print(f"  {u:6s} {len(ev):8d}  (one side empty)"); continue
        print(f"  {u:6s} {len(ev):8d} {len(a):6d} {np.mean(a):11.3f} {np.mean(b):10.3f} "
              f"{np.mean(a)-np.mean(b):+8.3f}")
        res["per_user"][u] = dict(n=len(ev), n_early=len(a), early=float(np.mean(a)),
                                  late=float(np.mean(b)))

    if args.json:
        json.dump(res, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
