#!/usr/bin/env python3
"""Outcomes and shadow-layer coverage across the Boost cohort.

Two questions, kept apart because they carry different weight.

The first is where each participant stands against the safety floors that govern this project.
That is a statement about a person rather than about a comparison, so it is reported per
participant with an interval, and the interval is what decides whether the floor is met rather
than the point estimate.

The second is what the shadow layers have actually recorded. A shadow layer doses nothing, so its
value is entirely in whether it is firing, on whom, and often enough to learn from. Several of
these layers were understood to run on one device only, and this checks that rather than repeating
it.

Days are the unit throughout. Partial days are excluded, because a day still in progress reads as
better controlled than it is. Intervals come from a bootstrap over whole days, since readings
within a day are not independent.

Usage:
  python3 cohort_report.py [--days 28] [--users A,B,tim] [--out COHORT_REPORT.md]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
DSN = "dbname=oref host=127.0.0.1 port=5432"

TBR70_FLOOR = 4.0
TBR54_FLOOR = 1.0
MIN_READINGS_PER_DAY = 250
MIN_SPAN_HOURS = 20.0

SHADOW_LAYERS = {
    "V7 sizer": "boostv7_woulddoser7",
    "Twin forecaster": "boosttwin_fc30",
    "Plateau nudge": "boostv5_plateau_trig",
    "Accel meal detect": "accelmeal_trig",
}


def boot_ci(x, n=10000, seed=20260809):
    rng = np.random.default_rng(seed)
    if len(x) < 3:
        return (np.nan, np.nan)
    b = rng.choice(np.asarray(x, float), (n, len(x)), replace=True).mean(axis=1)
    return tuple(np.percentile(b, [2.5, 97.5]))


def daily(conn, user, days):
    d = pd.read_sql(
        """SELECT ts_utc, cgm_mgdl FROM boost_decisions
           WHERE user_id = %s AND cgm_mgdl BETWEEN 40 AND 400
             AND ts_utc > now() - (%s || ' days')::interval
           ORDER BY ts_utc""", conn, params=(user, days))
    if d.empty:
        return pd.DataFrame()
    d["day"] = pd.to_datetime(d.ts_utc, utc=True).dt.date
    rows = []
    for day, g in d.groupby("day"):
        span = (g.ts_utc.max() - g.ts_utc.min()).total_seconds() / 3600.0
        v = g.cgm_mgdl.values.astype(float)
        if len(v) < MIN_READINGS_PER_DAY or span < MIN_SPAN_HOURS:
            continue
        rows.append(dict(
            day=day,
            tir=100 * float(((v >= 70) & (v <= 180)).mean()),
            ting=100 * float(((v >= 63) & (v <= 140)).mean()),
            tbr70=100 * float((v < 70).mean()),
            tbr54=100 * float((v < 54).mean()),
            cv=100 * float(v.std(ddof=1) / v.mean()) if v.mean() > 0 else np.nan,
        ))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--users", default="", help="comma separated; default is the Boost cohort")
    ap.add_argument("--out")
    a = ap.parse_args()

    conn = psycopg2.connect(DSN)
    if a.users:
        users = [u.strip() for u in a.users.split(",") if u.strip()]
    else:
        users = pd.read_sql(
            """SELECT DISTINCT user_id FROM boost_decisions
               WHERE user_id ~ '^[A-J]$' OR user_id = 'tim' ORDER BY 1""", conn).user_id.tolist()

    L, P = [], None
    P = L.append
    P("# Boost cohort: outcomes and shadow coverage\n")
    P(f"\nLast {a.days} days, {len(users)} participants. A day enters only if it carries at least "
      f"{MIN_READINGS_PER_DAY} readings spanning at least {MIN_SPAN_HOURS:.0f} hours, so a day still "
      f"in progress is excluded rather than counted as unusually good.\n")

    P("\n## Glycaemic outcomes\n")
    P("\n| user | days | TIR | TING | TBR<70 (95% CI) | TBR<54 (95% CI) | CV |")
    P("|---|---|---|---|---|---|---|")
    frames = {}
    for u in users:
        df = daily(conn, u, a.days)
        frames[u] = df
        if df.empty:
            P(f"| {u} | 0 | | | | | |")
            continue
        lo70, hi70 = boot_ci(df.tbr70.values)
        lo54, hi54 = boot_ci(df.tbr54.values)
        P(f"| {u} | {len(df)} | {df.tir.mean():.1f}% | {df.ting.mean():.1f}% | "
          f"{df.tbr70.mean():.1f}% [{lo70:.1f}, {hi70:.1f}] | "
          f"{df.tbr54.mean():.1f}% [{lo54:.1f}, {hi54:.1f}] | {df.cv.mean():.1f}% |")

    P("\n## Standing against the safety floors\n")
    P(f"\nThe consensus absolutes are {TBR70_FLOOR:.0f} per cent for time below 70 mg/dL and "
      f"{TBR54_FLOOR:.0f} per cent for time below 54 mg/dL. A participant is counted as breaching "
      f"only where the whole interval sits above the floor, and as compliant only where the whole "
      f"interval sits below it. An interval spanning the floor is neither, and is reported as "
      f"undetermined at this sample size rather than resolved in either direction.\n")
    P("\n| user | TBR<70 verdict | TBR<54 verdict |")
    P("|---|---|---|")
    tally = {"breach": 0, "compliant": 0, "undetermined": 0}
    for u in users:
        df = frames[u]
        if df.empty:
            P(f"| {u} | no data | no data |"); continue
        verdicts = []
        for col, floor in (("tbr70", TBR70_FLOOR), ("tbr54", TBR54_FLOOR)):
            lo, hi = boot_ci(df[col].values)
            if lo > floor:
                v = "breach"
            elif hi < floor:
                v = "compliant"
            else:
                v = "undetermined"
            verdicts.append(v)
            if col == "tbr70":
                tally[v] += 1
        P(f"| {u} | {verdicts[0]} | {verdicts[1]} |")
    P(f"\nOn time below 70 mg/dL that is {tally['breach']} breaching, {tally['compliant']} "
      f"compliant and {tally['undetermined']} undetermined across {len(users)} participants.\n")

    P("\n## Shadow layer coverage\n")
    P("\nEach layer computes what it would have done and records it without acting. Coverage is "
      "the share of decision cycles in the window carrying a value for that layer, which is what "
      "determines whether the layer can be analysed for a given participant at all.\n")
    P("\n| user | cycles | " + " | ".join(SHADOW_LAYERS) + " |")
    P("|---" * (len(SHADOW_LAYERS) + 2) + "|")
    for u in users:
        counts = pd.read_sql(
            f"""SELECT count(*) AS n,
                       {', '.join(f'count({c}) AS "{k}"' for k, c in SHADOW_LAYERS.items())}
                FROM boost_decisions
                WHERE user_id = %s AND ts_utc > now() - (%s || ' days')::interval""",
            conn, params=(u, a.days))
        r = counts.iloc[0]
        n = int(r["n"])
        if n == 0:
            P(f"| {u} | 0 | " + " | ".join("-" for _ in SHADOW_LAYERS) + " |")
            continue
        cells = []
        for k in SHADOW_LAYERS:
            c = int(r[k])
            cells.append("none" if c == 0 else f"{100 * c / n:.0f}%")
        P(f"| {u} | {n:,} | " + " | ".join(cells) + " |")

    P("\n## What the shadow layers recorded\n")
    for label, col in SHADOW_LAYERS.items():
        d = pd.read_sql(
            f"""SELECT user_id, count(*) AS n, count({col}) AS have
                FROM boost_decisions
                WHERE user_id = ANY(%s) AND ts_utc > now() - (%s || ' days')::interval
                GROUP BY 1 HAVING count({col}) > 0 ORDER BY 1""",
            conn, params=(users, a.days))
        if d.empty:
            P(f"\n{label}: no participant recorded this layer in the window.\n")
            continue
        who = ", ".join(f"{r.user_id} ({r.have:,} cycles)" for r in d.itertuples())
        P(f"\n{label}: recorded by {who}.\n")

    P("\nA layer present on one participant only can still be read, but nothing about it "
      "generalises, and it should be reported as a single-participant observation.\n")

    conn.close()
    open(a.out or os.path.join(HERE, "COHORT_REPORT.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
