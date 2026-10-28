#!/usr/bin/env python3
"""2 — Does rolling-24h step LOAD predict subsequent insulin SENSITIVITY? (2026-07-09)

Physiology: exercise raises insulin sensitivity for 24-48h. If a rolling activity-load signal
predicts higher sensitivity, it could drive a sensitivity (ISF/target) adjustment — and we can
check whether the algorithm's existing autosens (tdd_adj_factor) already captures it.

Three views (fasting cycles, COB<10):
  A) forward-low(<70 in 3h) rate at MATCHED IOB, binned by rolling-24h load → more load = more lows
     at the same IOB = higher sensitivity.
  B) BGI residual: actual delta5 − expected BGI (−iob_activity×variable_sens×5). More negative under
     high load = insulin landing harder than the model expects = higher sensitivity. OLS on load.
  C) does the algorithm's own tdd_adj_factor already move with load? (is the signal already used?)

Rolling-24h load = mean(steps_60m) over the prior 24h per user (smooth activity level).
"""
import os
import sys

import numpy as np
import pandas as pd
import psycopg2

TDD_DEFAULT = None


def load():
    conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
    q = """
    SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
      user_id, ts_epoch, cgm_mgdl AS bg, steps_60m, iob_iob AS iob, sug_cob AS cob,
      iob_activity AS act, variable_sens AS sens, tdd, tdd_adj_factor, tdd_ratio
    FROM boost_decisions WHERE cgm_mgdl IS NOT NULL
    ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
    """
    df = pd.read_sql(q, conn, params=None).sort_values(["user_id", "ts_epoch"]).reset_index(drop=True)
    conn.close()
    df["dt"] = df.groupby("user_id").ts_epoch.diff() / 60
    df["delta5"] = df.groupby("user_id").bg.diff() / df.dt * 5
    df.loc[(df.dt > 7.6) | (df.dt < 2.0), "delta5"] = np.nan
    # rolling-24h activity load = mean steps_60m over prior 24h (time-based), per user, O(n)
    load = np.full(len(df), np.nan)
    for _, g in df.groupby("user_id", sort=False):
        ts = g.ts_epoch.values
        st = np.nan_to_num(g.steps_60m.values.astype(float))
        idx = g.index.values
        j = 0
        run = 0.0
        cnt = 0
        for i in range(len(g)):
            run += st[i]
            cnt += 1
            while ts[i] - ts[j] > 86400:
                run -= st[j]
                cnt -= 1
                j += 1
            load[idx[i]] = run / cnt if cnt else np.nan
        df.loc[idx, "load24"] = load[idx]
    df["iob_frac"] = df.iob / df.tdd.where(df.tdd > 0)
    df["bgi5"] = -df.act * df.sens * 5.0
    df["resid"] = df.delta5 - df.bgi5     # actual − expected; negative = fell more than model predicted
    return df


def main():
    df = load()
    fast = df[(df.cob.fillna(0) < 10)].copy()

    # forward-low(<70 in 3h)
    for _, g in df.groupby("user_id", sort=False):
        pass
    low3 = np.zeros(len(df), int)
    for _, g in df.groupby("user_id", sort=False):
        ts, bg, idx = g.ts_epoch.values, g.bg.values, g.index.values
        for i in range(len(g)):
            k = i + 1
            hit = 0
            while k < len(g) and ts[k] - ts[i] <= 10800:
                if bg[k] < 70:
                    hit = 1
                    break
                k += 1
            low3[idx[i]] = hit
    df["low3"] = low3
    fast = df[(df.cob.fillna(0) < 10)].copy()

    print("=== 2. Rolling-24h step load → subsequent insulin sensitivity ===\n")

    # per-user load tertiles (so each user is their own reference), then pooled
    print("A) forward-low(<70 in 3h) at MATCHED IOB (iob_frac 3-8%), by within-user load tertile")
    print(f"{'user':>5} {'low_load%':>10} {'mid%':>7} {'high_load%':>11} {'hi/lo':>7}")
    ratios = []
    for u, g in fast.groupby("user_id"):
        gg = g[(g.iob_frac > 0.03) & (g.iob_frac < 0.08) & g.load24.notna()]
        if len(gg) < 300:
            continue
        q1, q2 = gg.load24.quantile([1 / 3, 2 / 3])
        lo = gg[gg.load24 <= q1].low3.mean()
        mid = gg[(gg.load24 > q1) & (gg.load24 <= q2)].low3.mean()
        hi = gg[gg.load24 > q2].low3.mean()
        rr = hi / lo if lo > 0 else np.nan
        ratios.append(rr)
        print(f"{u:>5} {100*lo:>9.1f}% {100*mid:>6.1f}% {100*hi:>10.1f}% {rr:>6.2f}")
    print(f"  cohort median hi/lo forward-low ratio: {np.nanmedian(ratios):.2f}  "
          f"(>1 ⇒ high load → more lows at same IOB → higher sensitivity)")

    print("\nB) BGI residual (actual−expected ΔBG) vs load — fasting; more negative = harder landing")
    print(f"{'user':>5} {'slope(/1k steps)':>17} {'lo-load resid':>14} {'hi-load resid':>14}")
    slopes = []
    for u, g in fast.groupby("user_id"):
        gg = g[g.resid.notna() & g.load24.notna() & (g.iob_frac > 0.02)]
        if len(gg) < 300:
            continue
        x = gg.load24.values
        y = gg.resid.values
        b = np.polyfit(x, y, 1)[0] * 1000    # resid change per +1000 mean-steps load
        q1, q3 = gg.load24.quantile([0.25, 0.75])
        rlo = gg[gg.load24 <= q1].resid.median()
        rhi = gg[gg.load24 >= q3].resid.median()
        slopes.append(b)
        print(f"{u:>5} {b:>16.2f} {rlo:>13.1f} {rhi:>13.1f}")
    print(f"  cohort median slope: {np.nanmedian(slopes):.2f} mg/dL-per-5min per +1000 load  "
          f"(<0 ⇒ higher load → BG falls faster than model → higher sensitivity)")

    print("\nC) does the algorithm's own autosens (tdd_adj_factor) already move with load?")
    print(f"{'user':>5} {'corr(load,tdd_adj)':>19} {'lo-load adj':>12} {'hi-load adj':>12}")
    corrs = []
    for u, g in df.groupby("user_id"):
        gg = g[g.tdd_adj_factor.notna() & g.load24.notna()]
        if len(gg) < 300 or gg.tdd_adj_factor.nunique() < 3:
            print(f"{u:>5}   (tdd_adj flat/absent)")
            continue
        c = np.corrcoef(gg.load24, gg.tdd_adj_factor)[0, 1]
        q1, q3 = gg.load24.quantile([0.25, 0.75])
        alo = gg[gg.load24 <= q1].tdd_adj_factor.median()
        ahi = gg[gg.load24 >= q3].tdd_adj_factor.median()
        corrs.append(c)
        print(f"{u:>5} {c:>18.2f} {alo:>12.2f} {ahi:>12.2f}")
    if corrs:
        print(f"  cohort median corr(load, tdd_adj): {np.nanmedian(corrs):.2f}  "
              f"(near 0 ⇒ autosens does NOT capture activity load → a real gap to fill)")

    print("\n--- verdict ---")
    print("If A>1 and B<0 (sensitivity rises with load) but C≈0 (autosens misses it), then a rolling-24h "
          "activity → sensitivity adjustment is a genuine, unfilled lever. If C already tracks load, "
          "it's handled. If A≈1/B≈0, load doesn't move sensitivity beyond the acute during-exercise effect.")


if __name__ == "__main__":
    main()
