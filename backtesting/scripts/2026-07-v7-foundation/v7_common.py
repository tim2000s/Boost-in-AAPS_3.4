#!/usr/bin/env python3
"""Shared loader/model for the 2026-07 V7-foundation backtests.

Data: local TimescaleDB `oref`, table public.boost_decisions.
Dedup: rows are ~2x duplicated per 5-min cycle (multi-invoke); keep the LAST
row per (user, floor(ts_epoch/300)) — the final invoke of the cycle.

Expected-BG model (documented honestly, used by all three scripts):
  The DB does NOT carry the +30/+60/+90 predBG curves — only endpoint fields
  (sug_eventualbg, reason_minpredbg, ...). We therefore reconstruct the
  IOB-only ZT-style projection from per-cycle fields:

      BGI5(t)      = -iob_activity(t) * variable_sens(t) * 5     [mg/dL per 5 min]
      predBG(t+h)  = bg(t) + BGI5(t) * h/5                        [constant-activity hold]

  This is oref's own BGI extrapolated; it deliberately excludes carb/UAM
  absorption. Residuals in meal regimes therefore CONTAIN unmodeled
  absorption — that is why every consumer conditions on regime
  (meal-session vs quiet). This is the honest subset of what the DB carries.
"""
import numpy as np
import pandas as pd
import psycopg2

USERS = ["tim", "A", "B", "C", "D", "E", "F", "H"]   # G excluded: thin, no era map

# Operative committedCap eras (detected from COMMITTED dose ceilings, 07-05 analysis;
# H self-set 1.8, reported 07-06).
CAP_ERAS = {
    "tim": [("2026-06-01", .25), ("2026-06-12", .5), ("2026-06-14", .4), ("2026-07-02", .5)],
    "A":   [("2026-06-17", .25), ("2026-07-01", .5)],
    "B":   [("2026-06-18", .25), ("2026-07-01", .5), ("2026-07-02", .6)],
    "C":   [("2026-06-19", .25)],
    "D":   [("2026-06-17", .25)],
    "E":   [("2026-06-17", .25), ("2026-06-30", .5)],
    "F":   [("2026-06-18", .25), ("2026-06-29", .5)],
    "H":   [("2026-06-30", .8), ("2026-07-06", 1.8)],
}
CONF_CAPS = {"tim": 3.0}          # default below
CONF_CAP_DEFAULT = 2.5
CUM_CAPS = {"tim": 2.5}           # tim's live pref (07-03 incident reason line)

# TBR<70 / <54 baselines, trailing-14d proposal window (07-07 re-review; %)
TBR14 = {"tim": (2.4, 0.5), "A": (1.11, 0.22), "B": (3.83, 1.01), "C": (3.82, 0.60),
         "D": (10.14, 1.81), "E": (1.04, 0.00), "F": (2.99, 0.35), "H": (1.35, 0.28)}

MEAL_STATES = ("CONFIRMED", "COMMITTED", "RECOVERING")


def op_cap(uid, d):
    c = None
    for s, v in CAP_ERAS.get(uid, []):
        if d >= pd.to_datetime(s).date():
            c = v
    return c


def load(users=USERS, v6_only=True):
    conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
    q = f"""
    SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
      user_id, ts_epoch, ts_utc, cgm_mgdl AS bg, boostv5_state AS state, boostv5_age AS age,
      boostv5_finaldose AS fd, boostv5_budget AS budget, boostv5_score AS score,
      v1_units, sug_eventualbg AS ev, sug_current_target AS tgt, sug_insulinreq AS insreq,
      iob_iob AS iob, iob_activity AS act, variable_sens AS sens, dynamic_isf,
      steps_60m, tdd, boostv5_aggressionknob AS knob
    FROM boost_decisions
    WHERE user_id = ANY(%s) {"AND boostv5_state IS NOT NULL" if v6_only else ""}
    ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
    """
    df = pd.read_sql(q, conn, params=(list(users),)).sort_values(
        ["user_id", "ts_epoch"]).reset_index(drop=True)
    conn.close()
    dtc = pd.to_datetime(df.ts_utc, utc=True, format="mixed")
    df["date"] = dtc.dt.date
    df["hour"] = (dtc.dt.hour + 1) % 24          # local ~UTC+1 (BST cohort assumption)
    df["dt"] = df.groupby("user_id").ts_epoch.diff() / 60
    df["delta5"] = df.groupby("user_id").bg.diff() / df.dt * 5
    df.loc[(df.dt > 7.6) | (df.dt < 2.0), "delta5"] = np.nan
    # oref BGI, mg/dL per 5 min (IOB-only expected change)
    df["bgi5"] = -df.act * df.sens * 5.0
    df["cap"] = [op_cap(u, d) for u, d in zip(df.user_id, df.date)]
    return df


def add_rolling(df):
    """min45 (post-rescue window input); low3h = low<70 within the NEXT 3h (forward, a hypo-OUTCOME
    flag — correct for brake_audit/activity_hypo); prior_low3h = low<70 within the PRIOR 3h (backward,
    a hypo-ANTECEDENT flag — use this to attribute a low's CAUSE, e.g. a recurring rescue-overshoot low;
    the forward flag must NOT be used for causal attribution, that leaks the outcome)."""
    n = len(df)
    min45 = np.full(n, np.nan)
    low3h = np.zeros(n, bool)
    prior_low3h = np.zeros(n, bool)
    for _, g in df.groupby("user_id", sort=False):
        ts = g.ts_epoch.values; bg = g.bg.values; idx = g.index.values; m = len(g)
        j = 0
        for i in range(m):
            while ts[i] - ts[j] > 2700:
                j += 1
            min45[idx[i]] = np.nanmin(bg[j:i + 1])
        for i in range(m):
            k = i + 1
            while k < m and ts[k] - ts[i] <= 10800:
                k += 1
            low3h[idx[i]] = (bg[i + 1:k] < 70).any()
        lo = 0
        for i in range(m):
            while ts[i] - ts[lo] > 10800:      # 3h backward window
                lo += 1
            prior_low3h[idx[i]] = (bg[lo:i] < 70).any()   # [lo:i] excludes i itself → strictly prior
    df["min45"] = min45
    df["low3h"] = low3h
    df["prior_low3h"] = prior_low3h
    return df


def forward_bg(df, horizons=(30, 60, 90), tol=300):
    """bg at t+h (matched within +-tol seconds), per user. Adds bg{h} columns."""
    for h in horizons:
        col = np.full(len(df), np.nan)
        for _, g in df.groupby("user_id", sort=False):
            ts = g.ts_epoch.values; bg = g.bg.values; idx = g.index.values
            k = 0
            for i in range(len(g)):
                target = ts[i] + h * 60
                while k < len(g) and ts[k] < target - tol:
                    k += 1
                if k < len(g) and abs(ts[k] - target) <= tol:
                    col[idx[i]] = bg[k]
                # target is monotone in i, so k never needs to rewind
        df[f"bg{h}"] = col
    return df
