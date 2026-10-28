#!/usr/bin/env python3
"""Does confirming into a decaying acceleration predict a crash?

The proposal is to damp the confirm action multiplier when acceleration has been decaying across the
approach, rather than to gate the confirm on an acceleration floor. That proposal rests on a claim
about frequency and consequence, and this measures both before anything is built.

The design is a comparison, not a description. Every entry into CONFIRMED is classified by what
acceleration did over the cycles leading up to it, and the outcome that follows is the lowest glucose
in the next three hours. A decaying approach is only worth acting on if it crashes more often than a
sustained one, which is what the matched comparison here is for. Reporting the crash rate of decaying
confirms alone would say nothing, since some confirms are followed by lows regardless.

Intervals are bootstrapped over PARTICIPANTS rather than events, because one person contributing four
hundred confirms would otherwise decide the answer for everyone.

Usage:
  python3 measure_decay.py [--approach 4] [--horizon 180] [--out REPORT.md]
"""
from __future__ import annotations

import argparse
import os
import warnings

import numpy as np
import pandas as pd
import psycopg2

DSN = "dbname=oref host=127.0.0.1 port=5432"
HERE = os.path.dirname(os.path.abspath(__file__))
warnings.filterwarnings("ignore", message=".*SQLAlchemy connectable.*")

LOW, SEVERE = 70.0, 54.0


def connect():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def load(conn):
    d = pd.read_sql(
        """SELECT user_id, ts_utc, boostv5_state, delta_acceleration, cgm_mgdl,
                  boostv5_finaldose, boostv5_actionmult, iob_iob
           FROM boost_decisions
           WHERE variant='boost-other' AND boostv5_active IS NOT NULL
             AND boostv5_state IS NOT NULL
           ORDER BY user_id, ts_utc""", conn)
    d["ts_utc"] = pd.to_datetime(d.ts_utc, utc=True)
    for c in ("delta_acceleration", "cgm_mgdl", "boostv5_finaldose", "boostv5_actionmult", "iob_iob"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def events(d, approach, horizon):
    """One row per entry into CONFIRMED, with the approach shape and what followed."""
    out = []
    for user, g in d.groupby("user_id"):
        g = g.reset_index(drop=True)
        prev = g.boostv5_state.shift(1)
        entries = g.index[(g.boostv5_state == "CONFIRMED") & (prev != "CONFIRMED")]
        bg = g.cgm_mgdl.values
        ts = g.ts_utc.values
        acc = g.delta_acceleration.values
        for i in entries:
            lo = max(0, i - approach)
            app = acc[lo:i + 1]
            app = app[~np.isnan(app)]
            if len(app) < 3:
                continue
            # Decaying: the value at confirm is below where the approach peaked, by enough to be
            # more than measurement wobble, and the run is downward rather than jagged.
            peak = float(np.max(app))
            atconf = float(app[-1])
            fell = peak - atconf
            monotone = bool(np.all(np.diff(app[np.argmax(app):]) <= 1e-9))
            horizon_end = ts[i] + np.timedelta64(horizon, "m")
            fut = bg[(ts > ts[i]) & (ts <= horizon_end)]
            fut = fut[~np.isnan(fut)]
            if len(fut) < 6:
                continue
            out.append(dict(
                user=user, ts=pd.Timestamp(ts[i]),
                acc_peak=peak, acc_at_confirm=atconf, acc_fall=fell, monotone=monotone,
                dose=g.boostv5_finaldose.values[i], amult=g.boostv5_actionmult.values[i],
                iob=g.iob_iob.values[i], bg_at=bg[i],
                nadir=float(np.min(fut)),
                went_low=bool(np.min(fut) < LOW), went_severe=bool(np.min(fut) < SEVERE)))
    return pd.DataFrame(out)


def boot_users(df, col, n=10000, seed=7):
    """Resample participants, then take the pooled rate within the resampled set."""
    users = df.user.unique()
    if len(users) < 3:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    by = {u: df[df.user == u][col].values for u in users}
    out = []
    for _ in range(n):
        pick = rng.choice(users, len(users), replace=True)
        vals = np.concatenate([by[u] for u in pick])
        out.append(vals.mean())
    return tuple(np.percentile(out, [2.5, 97.5]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--approach", type=int, default=4, help="cycles before the confirm to inspect")
    ap.add_argument("--horizon", type=int, default=180, help="minutes of outcome to follow")
    ap.add_argument("--fall", type=float, default=10.0, help="acceleration points that count as decay")
    ap.add_argument("--out")
    a = ap.parse_args()
    conn = connect()

    ev = events(load(conn), a.approach, a.horizon)
    ev["decaying"] = (ev.acc_fall >= a.fall) & ev.monotone

    L, P = [], None
    P = L.append
    P("# Confirming into a decaying acceleration\n")
    P(f"\nEvery entry into CONFIRMED on the V5/V6 engine, classified by what acceleration did over "
      f"the {a.approach} cycles before it, and followed for {a.horizon} minutes. A confirm counts as "
      f"decaying when acceleration fell at least {a.fall:.0f} points from its peak in the approach "
      f"and fell monotonically from that peak.\n")
    P(f"\n{len(ev)} confirms from {ev.user.nunique()} participants, "
      f"{ev.ts.min().date()} to {ev.ts.max().date()}.\n")

    P("\n## Does it predict a low\n")
    P("\nThe comparison is the point. A crash rate for decaying confirms on its own says nothing, "
      "because some confirms are followed by lows whatever the approach looked like.\n")
    P("\n| approach | confirms | participants | went below 70 | below 54 | median nadir | median dose |")
    P("|---|---|---|---|---|---|---|")
    for flag, label in ((True, "decaying"), (False, "sustained or rising")):
        g = ev[ev.decaying == flag]
        if g.empty:
            continue
        lo, hi = boot_users(g, "went_low")
        slo, shi = boot_users(g, "went_severe")
        P(f"| {label} | {len(g)} | {g.user.nunique()} | "
          f"{100*g.went_low.mean():.1f}% [{100*lo:.1f}, {100*hi:.1f}] | "
          f"{100*g.went_severe.mean():.1f}% [{100*slo:.1f}, {100*shi:.1f}] | "
          f"{g.nadir.median():.0f} | {g.dose.median():.2f} U |")

    d1 = ev[ev.decaying]
    d0 = ev[~ev.decaying]
    if not d1.empty and not d0.empty:
        diff = d1.went_low.mean() - d0.went_low.mean()
        # difference of the two rates, resampling participants once and computing both arms from
        # the same resampled set so the two are not treated as independent samples
        users = ev.user.unique()
        rng = np.random.default_rng(11)
        by = {u: ev[ev.user == u] for u in users}
        ds = []
        for _ in range(10000):
            pick = rng.choice(users, len(users), replace=True)
            s = pd.concat([by[u] for u in pick])
            x, y = s[s.decaying], s[~s.decaying]
            if len(x) and len(y):
                ds.append(x.went_low.mean() - y.went_low.mean())
        lo, hi = np.percentile(ds, [2.5, 97.5])
        verdict = ("decaying confirms crash MORE often" if lo > 0 else
                   "decaying confirms crash LESS often" if hi < 0 else
                   "not distinguishable")
        P(f"\nDifference in the rate of going below 70: {100*diff:+.1f} points "
          f"[{100*lo:+.1f}, {100*hi:+.1f}]. {verdict}.\n")

    P("\n## How much insulin the two approaches attract\n")
    P("\nIf the damper is to be worth building, the decaying case has to be receiving enough insulin "
      "for damping it to matter.\n")
    P("\n| approach | median dose | 90th percentile | median action multiplier | median IOB at confirm |")
    P("|---|---|---|---|---|")
    for flag, label in ((True, "decaying"), (False, "sustained or rising")):
        g = ev[ev.decaying == flag].dropna(subset=["dose"])
        if g.empty:
            continue
        P(f"| {label} | {g.dose.median():.2f} U | {g.dose.quantile(0.9):.2f} U | "
          f"{g.amult.median():.2f} | {g.iob.median():.2f} U |")

    P("\n## Per participant\n")
    P("\nSo that one person cannot carry the result.\n")
    P("\n| participant | decaying confirms | below 70 | sustained confirms | below 70 |")
    P("|---|---|---|---|---|")
    for u in sorted(ev.user.unique()):
        g = ev[ev.user == u]
        x, y = g[g.decaying], g[~g.decaying]
        fx = f"{100*x.went_low.mean():.0f}%" if len(x) else "-"
        fy = f"{100*y.went_low.mean():.0f}%" if len(y) else "-"
        P(f"| {u} | {len(x)} | {fx} | {len(y)} | {fy} |")

    text = "\n".join(L) + "\n"
    if a.out:
        open(os.path.join(HERE, a.out), "w").write(text)
        print(f"wrote {a.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
