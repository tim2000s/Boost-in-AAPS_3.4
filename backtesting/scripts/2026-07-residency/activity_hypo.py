#!/usr/bin/env python3
"""Does activity genuinely PRECEDE the hypo? (2026-07-08)

The residency attribution said ACTIVITY = 47% of low-time — but that used steps in the
pre-onset window, so it risks being co-occurrence, not prediction. This validates it:

  1. Dose-response: forward-low(<70 within 3h) rate by recent-steps bin and by HR-reserve bin.
  2. Controlled added value: LGBM forward-low with BG/IOB/time baseline vs + activity
     (steps + HR). AUC LIFT = activity's independent contribution beyond glucose state.
  3. Lead time: for real low episodes, how far ahead does activity elevate above baseline?
     (the exercise protection has to fire early enough to matter.)
  4. HR vs steps: which carries the signal — directly relevant to the Garmin HR ingest.

Uses hr_avg / hrr_pct / hr_zone + steps_{5,15,30,60}m from oref.boost_decisions.
Grouped-by-user CV so no within-user leakage.
"""
import os
import sys

import numpy as np
import pandas as pd
import psycopg2
import lightgbm as lgb
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "2026-07-v7-foundation"))
import v7_common as vc  # noqa: E402


def load():
    conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
    q = """
    SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
      user_id, ts_epoch, ts_utc, cgm_mgdl AS bg, boostv5_state AS state,
      iob_iob AS iob, iob_activity AS act, tdd, sug_eventualbg AS ev,
      steps_5m, steps_15m, steps_30m, steps_60m,
      hr_avg, hr_bpm_max5m, hrr_pct, hr_zone
    FROM boost_decisions
    WHERE boostv5_state IS NOT NULL
    ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
    """
    df = pd.read_sql(q, conn, params=None).sort_values(["user_id", "ts_epoch"]).reset_index(drop=True)
    conn.close()
    df["dt"] = df.groupby("user_id").ts_epoch.diff() / 60
    df["delta5"] = df.groupby("user_id").bg.diff() / df.dt * 5
    df.loc[(df.dt > 7.6) | (df.dt < 2.0), "delta5"] = np.nan
    dtc = pd.to_datetime(df.ts_utc, utc=True, format="mixed")
    df["hour"] = (dtc.dt.hour + 1) % 24
    df = vc.add_rolling(df)     # min45, low3h
    df = vc.forward_bg(df)      # bg30/60/90
    df["iob_frac"] = df.iob / df.tdd.where(df.tdd > 0)
    return df


def dose_response(df):
    print("=== 1. DOSE-RESPONSE: forward-low(<70 in 3h) rate by recent activity ===")
    d = df.dropna(subset=["low3h"])
    print(f"cohort base forward-low rate: {100*d.low3h.mean():.1f}%\n")
    print("  steps_60m bin        n      fwd-low%")
    bins = [-1, 0, 100, 300, 600, 1200, 1e9]
    labs = ["0", "1-100", "100-300", "300-600", "600-1200", "1200+"]
    d = d.assign(sb=pd.cut(d.steps_60m, bins=bins, labels=labs))
    for lab in labs:
        s = d[d.sb == lab]
        if len(s):
            print(f"    {lab:>10}  {len(s):>7}    {100*s.low3h.mean():>6.1f}%")
    print(f"\n  HR-reserve (hrr_pct) bin   n      fwd-low%   (null hrr%: {100*df.hrr_pct.isna().mean():.0f})")
    hb = [-1, 0, 20, 40, 60, 200]
    hl = ["0", "0-20", "20-40", "40-60", "60+"]
    dh = d.dropna(subset=["hrr_pct"]).assign(hb=pd.cut(d.dropna(subset=["hrr_pct"]).hrr_pct, bins=hb, labels=hl))
    for lab in hl:
        s = dh[dh.hb == lab]
        if len(s):
            print(f"    {lab:>10}  {len(s):>7}    {100*s.low3h.mean():>6.1f}%")


def added_value(df):
    print("\n=== 2. CONTROLLED: does activity ADD predictive value beyond BG/IOB/time? ===")
    d = df.dropna(subset=["low3h"]).copy()
    d["state_ord"] = d.state.map({"IDLE": 0, "OBSERVING": 1, "CONFIRMED": 2, "COMMITTED": 3, "RECOVERING": 4}).fillna(-1)
    y = d.low3h.astype(int).values
    grp = d.user_id.values
    base = ["bg", "delta5", "iob_frac", "hour", "ev", "state_ord"]
    act = ["steps_5m", "steps_15m", "steps_30m", "steps_60m", "act", "hr_avg", "hr_bpm_max5m", "hrr_pct"]

    def cv_auc(cols):
        X = d[cols].astype(float).replace([np.inf, -np.inf], np.nan).values
        gkf = GroupKFold(n_splits=min(5, len(np.unique(grp))))
        aucs = []
        for tr, te in gkf.split(X, y, grp):
            m = lgb.LGBMClassifier(n_estimators=350, learning_rate=0.03, num_leaves=31,
                                   min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
                                   n_jobs=-1, verbose=-1).fit(X[tr], y[tr])
            p = m.predict_proba(X[te])[:, 1]
            if len(np.unique(y[te])) > 1:
                aucs.append(roc_auc_score(y[te], p))
        return np.mean(aucs), np.std(aucs)

    a0, s0 = cv_auc(base)
    a1, s1 = cv_auc(base + act)
    print(f"  baseline (BG/IOB/time):        AUC {a0:.3f} ± {s0:.3f}")
    print(f"  + activity (steps+HR):         AUC {a1:.3f} ± {s1:.3f}")
    print(f"  activity's independent lift:   {a1 - a0:+.3f} AUC")
    # gain importance of activity features in the full model
    Xf = d[base + act].astype(float).replace([np.inf, -np.inf], np.nan).values
    mf = lgb.LGBMClassifier(n_estimators=350, learning_rate=0.03, num_leaves=31,
                            min_child_samples=50, n_jobs=-1, verbose=-1).fit(Xf, y)
    imp = pd.Series(mf.booster_.feature_importance("gain"), index=base + act).sort_values(ascending=False)
    print("  top features (gain):", ", ".join(f"{k}={v:.0f}" for k, v in imp.head(8).items()))
    ar = imp.rank(ascending=False)
    print("  activity-feature ranks:", {k: int(ar[k]) for k in act if k in ar})


def lead_time(df):
    print("\n=== 3. LEAD TIME: activity in the 3h before a low onset vs matched non-low ===")
    # low onsets: first cycle of a <70 run
    means_pre = {5: [], 15: [], 30: [], 60: [], 90: [], 120: [], 180: []}
    base_steps = []
    for u, g in df.groupby("user_id", sort=False):
        g = g.reset_index(drop=True)
        ts = g.ts_epoch.values
        low = (g.bg < 70).values
        onsets = [i for i in range(len(g)) if low[i] and (i == 0 or not low[i - 1])]
        base_steps.append(np.nanmean(g.steps_60m.values))
        for oi in onsets:
            for mins in means_pre:
                target = ts[oi] - mins * 60
                j = np.searchsorted(ts, target)
                j = min(max(j, 0), len(g) - 1)
                means_pre[mins].append(g.steps_60m.values[j])
    bs = np.nanmean(base_steps)
    print(f"  overall mean steps_60m baseline: {bs:.0f}")
    print("  mins-before-low   mean steps_60m   vs baseline")
    for mins in sorted(means_pre):
        m = np.nanmean(means_pre[mins])
        print(f"    {mins:>3} min          {m:>8.0f}        {m/bs:.1f}x")


def main():
    df = load()
    print(f"rows {len(df)} | steps_60m null% {100*df.steps_60m.isna().mean():.0f} | "
          f"hr_avg null% {100*df.hr_avg.isna().mean():.0f} | hrr_pct null% {100*df.hrr_pct.isna().mean():.0f}\n")
    dose_response(df)
    added_value(df)
    lead_time(df)


if __name__ == "__main__":
    main()
