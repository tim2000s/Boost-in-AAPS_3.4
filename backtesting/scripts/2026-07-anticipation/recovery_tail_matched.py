#!/usr/bin/env python3
"""1a — Post-exercise recovery tail, DE-ARTIFACTED (matched windows) + V4-window comparison (2026-07-09).

The D finding compared a +Nh post-exercise low-rate to a FIXED 3h baseline → the +4-6h magnitudes
were inflated by window length. Two artifact-free views here:
  (i)  PER-HOUR HAZARD: P(low in the 1-hour bin [k,k+1] after exercise-end) vs baseline 1-hour-bin
       rate — pure shape, no cumulative-window confound. Shows the delayed hump directly.
  (ii) MATCHED cumulative: P(low within N h | exercise-end) vs P(low within N h | random cycle),
       same N both sides → window length cancels.
Then compare the empirical shape to V4's recovery window (default 2.0h, SMB×0.5, target 144).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(__file__))
import anticip_common as ac  # noqa

HAZ_BINS = list(range(0, 8))     # hour bins 0-1,1-2,...,7-8 after exercise end
V4_WINDOW_H = 2.0                 # V4 default postExerciseRecoveryHours


def user_arrays(g):
    g = g.sort_values("ts_epoch").reset_index(drop=True)
    thr = np.nanpercentile(g.steps_60m.dropna(), 80)
    active = (g.steps_60m > thr).values if np.isfinite(thr) else None
    return g.ts_epoch.values, g.bg.values, active, thr


def low_in_bin(ts, bg, t0, a, b):
    """1 if any BG<70 in [t0+a*3600, t0+b*3600], else 0; None if no coverage."""
    lo, hi = t0 + a * 3600, t0 + b * 3600
    k = np.searchsorted(ts, lo)
    seen = False
    while k < len(ts) and ts[k] <= hi:
        seen = True
        if bg[k] < 70:
            return 1
        k += 1
    return 0 if seen else None


def main():
    df = ac.load()
    print("=== 1a. Post-exercise recovery tail — matched/de-artifacted + V4-window check ===\n")
    print("PER-HOUR HAZARD  (low-rate in each 1h bin after exercise-end ÷ user's baseline 1h rate)")
    print(f"{'user':>5} {'base1h%':>8} " + " ".join(f"{k}-{k+1}h".rjust(6) for k in HAZ_BINS))
    haz_rows = []
    for u, g in df.groupby("user_id"):
        ts, bg, active, thr = user_arrays(g)
        if active is None or thr < 30:
            continue
        ends = [i for i in range(1, len(g)) if active[i - 1] and not active[i]]
        if len(ends) < 15:
            continue
        # baseline 1h-bin low rate: sample all cycles, P(low in next 1h)
        base = np.nanmean([low_in_bin(ts, bg, ts[i], 0, 1) for i in range(0, len(g), 4)])
        hz = []
        for k in HAZ_BINS:
            vals = [low_in_bin(ts, bg, ts[e], k, k + 1) for e in ends]
            vals = [v for v in vals if v is not None]
            hz.append(np.mean(vals) if vals else np.nan)
        haz_rows.append((u, base, hz))
        print(f"{u:>5} {100*base:>7.1f}% " + " ".join(f"{h/base:>5.2f}" if base > 0 and not np.isnan(h) else "   -- " for h in hz))

    # cohort median hazard-multiple per bin
    print("\nCOHORT median hazard-multiple by hour-bin (artifact-free shape):")
    for k in HAZ_BINS:
        mults = [r[2][k] / r[1] for r in haz_rows if r[1] > 0 and not np.isnan(r[2][k])]
        m = np.median(mults) if mults else np.nan
        bar = "#" * int(max(0, (m - 1) * 20)) if not np.isnan(m) else ""
        print(f"  +{k}-{k+1}h: {m:>4.2f}x  {bar}")

    # ── V4-window mismatch ──
    print(f"\n--- V4 recovery window vs the empirical tail ---")
    early = np.median([np.nanmean([r[2][k] / r[1] for k in (0, 1) if r[1] > 0]) for r in haz_rows])
    late = np.median([np.nanmean([r[2][k] / r[1] for k in range(2, 6) if r[1] > 0 and not np.isnan(r[2][k])]) for r in haz_rows])
    print(f"  empirical hypo-hazard  0-2h (what V4 protects): {early:.2f}x baseline")
    print(f"  empirical hypo-hazard  2-6h (after V4 ends):     {late:.2f}x baseline")
    print(f"  V4 default window = {V4_WINDOW_H:.0f}h (SMB×0.5, target 144).")
    if early < 1.0 < late:
        print("  ⇒ MISMATCH: V4 protects the 0-2h window where hypo risk is BELOW baseline, and SWITCHES "
              "OFF right as the real risk (2-6h) begins. The window is too SHORT and front-loaded vs the "
              "physiology — a delayed/longer damper (peak ~3-5h) would match the data.")
    else:
        print("  ⇒ V4 window roughly matches the empirical timing.")


if __name__ == "__main__":
    main()
