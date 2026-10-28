#!/usr/bin/env python3
"""What the auto-config raise-guard is reading, and when it would release.

The guard holds a dose-cap raise while time below 70 exceeds 4 per cent or time below 54 reaches 1
per cent, measured over the same 28-day window the re-derivation uses. A window that long carries
weeks-old days, so a period of disruption keeps holding raises well after the thing that caused it
has been fixed. This shows the daily series, the rolling window the guard actually sees, and the
date the window clears if the recent days simply continue.

The projection is arithmetic on the existing days, not a forecast: it replaces each future day with
the recent median and reports when the rolling figure would cross. It says when the old days fall
out of the window, which is a fact about the calendar, and nothing about what glucose will do.

Usage:
  python3 guard_window.py [--user tim] [--days 45] [--recent 7]
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import warnings

import numpy as np
import pandas as pd

from v6_findings import MIN_READINGS_PER_DAY, MIN_SPAN_HOURS, connect

HERE = os.path.dirname(os.path.abspath(__file__))
warnings.filterwarnings("ignore", message=".*SQLAlchemy connectable.*")

# Mirrors BoostV5AutoConfigApply. The <70 test is strictly greater, the <54 test is at-or-above.
TBR70_GUARD = 4.0
TBR54_GUARD = 1.0
REDRIVE_LOOKBACK_DAYS = 28


def daily(conn, user, days):
    d = pd.read_sql(
        """SELECT ts_utc, cgm_mgdl FROM boost_cgm
           WHERE user_id = %(u)s AND ts_utc > now() - (%(d)s || ' days')::interval
             AND cgm_mgdl BETWEEN 40 AND 400 ORDER BY ts_utc""",
        conn, params={"u": user, "d": days})
    if d.empty:
        return d
    d["day"] = pd.to_datetime(d.ts_utc, utc=True).dt.date
    rows = []
    for day, g in d.groupby("day"):
        v = g.cgm_mgdl.values.astype(float)
        span = (g.ts_utc.max() - g.ts_utc.min()).total_seconds() / 3600.0
        rows.append(dict(day=day, n=len(v),
                         complete=(len(v) >= MIN_READINGS_PER_DAY and span >= MIN_SPAN_HOURS),
                         tbr70=100 * float((v < 70).mean()),
                         tbr54=100 * float((v < 54).mean())))
    return pd.DataFrame(rows).sort_values("day").reset_index(drop=True)


def rolling_guard(df, window):
    """The guard's own reading: pooled over readings in the window, not a mean of daily rates."""
    out = []
    for i in range(len(df)):
        lo = max(0, i - window + 1)
        w = df.iloc[lo:i + 1]
        n = w.n.sum()
        out.append(dict(day=df.day.iloc[i], days_in_window=len(w),
                        tbr70=float((w.tbr70 * w.n).sum() / n) if n else np.nan,
                        tbr54=float((w.tbr54 * w.n).sum() / n) if n else np.nan))
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="tim")
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--recent", type=int, default=7)
    a = ap.parse_args()
    conn = connect()

    df = daily(conn, a.user, a.days)
    if df.empty:
        print("no data")
        return
    df = df[df.complete].reset_index(drop=True)
    roll = rolling_guard(df, REDRIVE_LOOKBACK_DAYS)
    now70 = roll.tbr70.iloc[-1]
    now54 = roll.tbr54.iloc[-1]

    print(f"{a.user}: guard inputs over the {REDRIVE_LOOKBACK_DAYS}-day window the re-derivation uses")
    print(f"  time below 70: {now70:.2f}%  (holds a raise above {TBR70_GUARD}%)")
    print(f"  time below 54: {now54:.2f}%  (holds a raise at or above {TBR54_GUARD}%)")
    held = now70 > TBR70_GUARD or now54 >= TBR54_GUARD
    print(f"  a cap raise would be {'HELD' if held else 'allowed'} right now")

    for w in (7, 14, 28):
        r = rolling_guard(df, w).iloc[-1]
        print(f"\nlast {w:2d} days: TBR<70 {r.tbr70:5.2f}%   TBR<54 {r.tbr54:5.2f}%   "
              f"({int(r.days_in_window)} complete days)")

    print(f"\nDaily, most recent {min(len(df), 21)} complete days:")
    print(f"{'day':<12}{'readings':>9}{'TBR<70':>9}{'TBR<54':>9}")
    for _, r in df.tail(21).iterrows():
        print(f"{str(r.day):<12}{int(r.n):>9}{r.tbr70:>8.1f}%{r.tbr54:>8.1f}%")

    # When do the old days leave the window? Replace each future day with the recent median and
    # roll forward. This is calendar arithmetic on days already measured.
    recent = df.tail(a.recent)
    med70, med54 = recent.tbr70.median(), recent.tbr54.median()
    med_n = int(recent.n.median())
    print(f"\nIf the next days look like the last {a.recent} "
          f"(median TBR<70 {med70:.2f}%, TBR<54 {med54:.2f}%):")
    fut = df.copy()
    today = df.day.iloc[-1]
    released = None
    for k in range(1, 29):
        fut = pd.concat([fut, pd.DataFrame([dict(day=today + dt.timedelta(days=k), n=med_n,
                                                 complete=True, tbr70=med70, tbr54=med54)])],
                        ignore_index=True)
        r = rolling_guard(fut, REDRIVE_LOOKBACK_DAYS).iloc[-1]
        if released is None and not (r.tbr70 > TBR70_GUARD or r.tbr54 >= TBR54_GUARD):
            released = (today + dt.timedelta(days=k), r.tbr70, r.tbr54)
        if k in (7, 14, 28):
            print(f"  in {k:2d} days ({today + dt.timedelta(days=k)}): "
                  f"TBR<70 {r.tbr70:5.2f}%  TBR<54 {r.tbr54:5.2f}%")
    if released:
        print(f"\n  the guard would release on {released[0]} "
              f"(TBR<70 {released[1]:.2f}%, TBR<54 {released[2]:.2f}%)")
    else:
        print("\n  the guard would still hold in 28 days on those medians")


if __name__ == "__main__":
    main()
