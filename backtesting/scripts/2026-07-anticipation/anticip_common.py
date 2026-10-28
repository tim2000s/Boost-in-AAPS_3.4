#!/usr/bin/env python3
"""Shared loader + parquet cache for the 2026-07 anticipation experiments.

Pulls the fields the four analyses (bedtime / exercise-lead / dawn / recovery) need ONCE and
caches to parquet, so the four scripts run fast in parallel off local capacity. Per-user local
hour/weekday from the site-registry tz offsets (tz field only, no secrets).
"""
import json
import os

import numpy as np
import pandas as pd
import psycopg2

CACHE = os.path.join(os.path.dirname(__file__), "_anticip_cache.parquet")

_TZ = {}
try:
    for s in json.load(open(os.path.expanduser("~/.config/boost_backtest/sites.json")))["sites"]:
        _TZ[s["tag"]] = int(s.get("tz_offset_hours", 1))
except Exception:
    pass


def build_cache():
    conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
    q = """
    SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
      user_id, ts_epoch, ts_utc, cgm_mgdl AS bg, boostv5_state AS state,
      steps_5m, steps_15m, steps_30m, steps_60m, hr_avg,
      iob_iob AS iob, sug_cob AS cob
    FROM boost_decisions WHERE cgm_mgdl IS NOT NULL
    ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
    """
    df = pd.read_sql(q, conn, params=None).sort_values(["user_id", "ts_epoch"]).reset_index(drop=True)
    conn.close()
    dt = pd.to_datetime(df.ts_utc, utc=True, format="mixed")
    off = df.user_id.map(lambda u: _TZ.get(u, 1)).astype(int)
    local = dt + pd.to_timedelta(off, unit="h")
    df["hour"] = local.dt.hour
    df["minute"] = local.dt.hour * 60 + local.dt.minute
    df["dow"] = local.dt.dayofweek                 # 0=Mon
    df["weekend"] = (df.dow >= 5).astype(int)
    df["localdate"] = local.dt.date
    # "night date": the calendar date of the evening a night belongs to (shift back 12h so 00–06 groups
    # with the prior evening) — used for per-night sleep-onset.
    df["nightdate"] = (local - pd.Timedelta(hours=12)).dt.date
    df["dt_min"] = df.groupby("user_id").ts_epoch.diff() / 60
    df["delta5"] = df.groupby("user_id").bg.diff() / df.dt_min * 5
    df.loc[(df.dt_min > 7.6) | (df.dt_min < 2.0), "delta5"] = np.nan
    df.to_parquet(CACHE)
    return df


def load():
    if os.path.exists(CACHE):
        return pd.read_parquet(CACHE)
    return build_cache()


if __name__ == "__main__":
    d = build_cache()
    print(f"cache built: {len(d)} rows, {d.user_id.nunique()} users -> {CACHE}")
    print("cols:", list(d.columns))
