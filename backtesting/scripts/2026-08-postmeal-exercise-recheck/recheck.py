#!/usr/bin/env python3
"""
Does the inverted insulin-on-board relationship at post-meal exercise survive within a person?

The claim under test is that participants who go low after exercising near a meal are carrying
LESS insulin than those who do not, which was read as evidence that the crash is not dose-driven.
The supporting figures, a median of 0.96 U against 1.61 U and an area under the curve of 0.463,
are pooled across participants in absolute units.

That pooling is the problem. Insulin units are not comparable between these participants: total
daily dose varies severalfold, at least one participant uses a 200 U/mL concentration so a unit
carries twice the mass, and body size and carbohydrate ratio vary with them. A pooled comparison
of absolute units therefore mixes a within-person question, "did this person carry less insulin
on the occasions they went low", with a between-person one, "do the people who go low happen to
run less insulin". Only the first speaks to mechanism.

This script separates them. Insulin on board is expressed as a fraction of the participant's own
total daily dose, so it is dimensionless and concentration-free, and discrimination is computed
per participant and pooled with the participant as the resampling unit.

Three comparisons are reported:

  1. Pooled absolute units, reproducing the original construction.
  2. Pooled but standardised by the participant's own total daily dose.
  3. Per participant, which is the only construction that answers the mechanism question.

Exercise is taken from the step feed. A meal-and-exercise event is an exercise onset falling
within the post-meal window, and the outcome is a qualifying low within the following three hours.

Usage:  python3 recheck.py [--json out.json]
"""

import argparse
import json
import sys

import numpy as np
import psycopg2

USERS = ("A", "B", "C", "D", "E", "F", "G", "H", "I", "tim")

STEP_ONSET = 400          # steps in the preceding 30 min that marks an exercise onset
STEP_QUIET = 100          # below this the participant counts as not exercising
MEAL_WINDOW_MIN = 180     # exercise counts as post-meal if within this of a rise onset
LOW_MGDL = 70.0
LOW_HORIZON_MIN = 180
RISE_MGDL = 40.0          # a meal is a rise of this much within 90 min
RISE_WINDOW_MIN = 90
BUCKET_MIN = 5


def fetch(conn):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT ON (d.user_id, to_timestamp(floor(extract(epoch FROM d.ts_utc) / {BUCKET_MIN*60}) * {BUCKET_MIN*60}))
               d.user_id, extract(epoch FROM d.ts_utc), d.cgm_mgdl,
               d.sug_iob, d.sug_cob, d.tdd, d.steps_30m
        FROM boost_decisions d
        WHERE d.user_id = ANY(%s)
          AND d.cgm_mgdl IS NOT NULL AND d.sug_iob IS NOT NULL
          AND d.steps_30m IS NOT NULL AND d.tdd IS NOT NULL AND d.tdd > 0
        ORDER BY d.user_id,
                 to_timestamp(floor(extract(epoch FROM d.ts_utc) / {BUCKET_MIN*60}) * {BUCKET_MIN*60}),
                 d.ts_utc
    """, (list(USERS),))
    out = {}
    for uid, ts, bg, iob, cob, tdd, st in cur.fetchall():
        f = lambda v: np.nan if v is None else float(v)
        out.setdefault(uid, []).append((float(ts), float(bg), float(iob), f(cob),
                                        float(tdd), float(st)))
    for u in out:
        out[u].sort(key=lambda r: r[0])
    return out


def events(rows):
    """Exercise onsets that fall inside a post-meal window, with the outcome that followed."""
    ts = np.array([r[0] for r in rows]); bg = np.array([r[1] for r in rows])
    iob = np.array([r[2] for r in rows]); tdd = np.array([r[4] for r in rows])
    st = np.array([r[5] for r in rows])

    # meal onsets: a rise of RISE_MGDL within RISE_WINDOW_MIN
    meal = np.zeros(len(ts), dtype=bool)
    hi = np.searchsorted(ts, ts + RISE_WINDOW_MIN * 60, side="right")
    for i in range(len(ts)):
        if hi[i] > i + 1 and bg[i + 1:hi[i]].max() >= bg[i] + RISE_MGDL:
            meal[i] = True
    meal_ts = ts[meal]

    # exercise onsets: crossing STEP_ONSET from quiet
    onset = (st >= STEP_ONSET) & (np.roll(st, 1) < STEP_QUIET)
    onset[0] = False

    # low events
    low_start = []
    i = 0
    while i < len(bg):
        if bg[i] < LOW_MGDL:
            j = i
            while j + 1 < len(bg) and bg[j + 1] < LOW_MGDL and ts[j + 1] - ts[j] <= 900:
                j += 1
            if ts[j] - ts[i] >= 10 * 60:
                low_start.append(ts[i])
            i = j + 1
        else:
            i += 1
    low_ts = np.array(low_start, dtype=float)

    out = []
    last = -1e9
    for i in np.flatnonzero(onset):
        if ts[i] - last < 3600:          # one event per hour, so a long session is not counted twice
            continue
        k = np.searchsorted(meal_ts, ts[i])
        if k == 0 or ts[i] - meal_ts[k - 1] > MEAL_WINDOW_MIN * 60:
            continue                      # not post-meal
        last = ts[i]
        lo = np.searchsorted(low_ts, ts[i], side="right")
        hi_ = np.searchsorted(low_ts, ts[i] + LOW_HORIZON_MIN * 60, side="right")
        out.append(dict(ts=ts[i], bg=bg[i], iob=iob[i], tdd=tdd[i],
                        iob_frac=iob[i] / tdd[i], low=int(hi_ > lo)))
    return out


def auc(scores, labels):
    s = np.asarray(scores, float); y = np.asarray(labels, int)
    npos, nneg = int(y.sum()), len(y) - int(y.sum())
    if npos == 0 or nneg == 0:
        return None
    order = np.argsort(s, kind="mergesort"); ss = s[order]
    ranks = np.empty(len(ss)); i = 0
    while i < len(ss):
        j = i
        while j + 1 < len(ss) and ss[j + 1] == ss[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    r = np.empty(len(ss)); r[order] = ranks
    return (r[y == 1].sum() - npos * (npos + 1) / 2.0) / (npos * nneg)


def cluster_ci(per_user, key, n=4000, seed=20260813):
    us = [u for u in per_user if len({e["low"] for e in per_user[u]}) == 2]
    if len(us) < 3:
        return None, None, None, us
    rng = np.random.default_rng(seed)
    pt = auc([e[key] for u in us for e in per_user[u]],
             [e["low"] for u in us for e in per_user[u]])
    b = []
    for _ in range(n):
        pick = rng.choice(len(us), len(us), replace=True)
        s = [e[key] for k in pick for e in per_user[us[k]]]
        y = [e["low"] for k in pick for e in per_user[us[k]]]
        a = auc(s, y)
        if a is not None:
            b.append(a)
    return pt, float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5)), us


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--json", default=None)
    args = ap.parse_args()
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    rows = fetch(conn)

    per_user = {u: events(r) for u, r in rows.items()}
    per_user = {u: e for u, e in per_user.items() if len(e) >= 15}
    allev = [e for u in per_user for e in per_user[u]]
    print(f"post-meal exercise events: {len(allev)} across {len(per_user)} participants, "
          f"low rate {np.mean([e['low'] for e in allev]):.3f}\n")
    res = {"n_events": len(allev), "n_users": len(per_user)}

    print("=" * 78)
    print("1. THE ORIGINAL CONSTRUCTION: pooled, absolute units")
    print("=" * 78)
    lo_ = [e["iob"] for e in allev if e["low"]]
    hi_ = [e["iob"] for e in allev if not e["low"]]
    a_abs = auc([e["iob"] for e in allev], [e["low"] for e in allev])
    print(f"  median IOB, went low     {np.median(lo_):.2f} U   (n={len(lo_)})")
    print(f"  median IOB, did not      {np.median(hi_):.2f} U   (n={len(hi_)})")
    print(f"  pooled AUC of IOB vs low {a_abs:.3f}   (below 0.5 means less insulin went with more lows)")
    res["pooled_absolute"] = dict(median_low=float(np.median(lo_)),
                                  median_nolow=float(np.median(hi_)), auc=a_abs)

    print()
    print("=" * 78)
    print("2. THE SAME POOLED COMPARISON, STANDARDISED BY EACH PARTICIPANT'S OWN TDD")
    print("=" * 78)
    print("  IOB as a fraction of that participant's total daily dose is dimensionless and")
    print("  concentration-free, so a 200 U/mL participant is comparable with a 100 U/mL one.")
    lo_ = [e["iob_frac"] for e in allev if e["low"]]
    hi_ = [e["iob_frac"] for e in allev if not e["low"]]
    a_frac = auc([e["iob_frac"] for e in allev], [e["low"] for e in allev])
    print(f"\n  median IOB/TDD, went low  {np.median(lo_):.4f}")
    print(f"  median IOB/TDD, did not   {np.median(hi_):.4f}")
    print(f"  pooled AUC                {a_frac:.3f}")
    res["pooled_standardised"] = dict(median_low=float(np.median(lo_)),
                                      median_nolow=float(np.median(hi_)), auc=a_frac)

    print()
    print("=" * 78)
    print("3. WITHIN PARTICIPANT, which is the only version that speaks to mechanism")
    print("=" * 78)
    print(f"\n  {'user':6s} {'events':>7s} {'lows':>5s} {'AUC abs':>8s} {'AUC /TDD':>9s} "
          f"{'med IOB low':>12s} {'med IOB no':>11s}")
    res["per_user"] = {}
    for u in sorted(per_user):
        ev = per_user[u]
        y = [e["low"] for e in ev]
        if len(set(y)) < 2:
            print(f"  {u:6s} {len(ev):7d} {sum(y):5d}   (one class only)")
            continue
        aa = auc([e["iob"] for e in ev], y)
        af = auc([e["iob_frac"] for e in ev], y)
        ml = np.median([e["iob"] for e in ev if e["low"]])
        mn = np.median([e["iob"] for e in ev if not e["low"]])
        print(f"  {u:6s} {len(ev):7d} {sum(y):5d} {aa:8.3f} {af:9.3f} {ml:12.2f} {mn:11.2f}")
        res["per_user"][u] = dict(n=len(ev), lows=int(sum(y)), auc_abs=aa, auc_frac=af,
                                  med_low=float(ml), med_nolow=float(mn))

    for key, name in (("iob", "absolute units"), ("iob_frac", "fraction of own TDD")):
        pt, lo, hi, used = cluster_ci(per_user, key)
        if pt is None:
            continue
        verdict = ("inverted, distinguishable" if hi < 0.5 else
                   "positive, distinguishable" if lo > 0.5 else
                   "NOT distinguishable from chance")
        print(f"\n  pooled with participants resampled, {name}: "
              f"{pt:.3f} [{lo:.3f}, {hi:.3f}] over {len(used)} participants -> {verdict}")
        res[f"cluster_{key}"] = dict(auc=pt, lo=lo, hi=hi, n_users=len(used))

    # how much of the pooled contrast is between-participant rather than within?
    print()
    print("=" * 78)
    print("4. HOW MUCH OF THE POOLED CONTRAST IS BETWEEN PARTICIPANTS")
    print("=" * 78)
    lowrate = np.array([np.mean([e["low"] for e in per_user[u]]) for u in sorted(per_user)])
    meaniob = np.array([np.median([e["iob"] for e in per_user[u]]) for u in sorted(per_user)])
    tdds = np.array([np.median([e["tdd"] for e in per_user[u]]) for u in sorted(per_user)])
    r = np.corrcoef(meaniob, lowrate)[0, 1]
    print(f"  across participants, median IOB at exercise onset vs that participant's low rate:")
    print(f"    correlation {r:+.3f}   (a negative value means the pooled contrast is partly")
    print(f"    the people who carry less insulin also being the people who go low more)")
    print(f"\n  spread in total daily dose across participants: "
          f"{tdds.min():.0f} to {tdds.max():.0f} U, a factor of {tdds.max()/tdds.min():.1f}")
    res["between_user"] = dict(corr_iob_lowrate=float(r), tdd_min=float(tdds.min()),
                               tdd_max=float(tdds.max()))

    if args.json:
        json.dump(res, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
