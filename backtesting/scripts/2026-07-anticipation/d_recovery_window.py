#!/usr/bin/env python3
"""D — Post-exercise recovery window: recurring elevated hypo-risk AFTER activity stops? (2026-07-09)

Activity→hypo we already validated as a leading indicator. D asks the distinct question: after an
exercise episode ENDS, is there a recurring window of elevated insulin sensitivity (extra hypo risk)
— the post-exercise tail — and is it consistent enough per user to warrant a recovery damper beyond
V4's existing recovery window?

Method: find activity episode ENDS (steps_60m falls back below floor after being high). In the N
hours after each end, measure forward-low(<70) rate vs the user's baseline forward-low rate. A
consistent elevation across episodes = a real, recurring recovery window.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(__file__))
import anticip_common as ac  # noqa

TAIL_H = [1, 2, 3, 4, 6]     # hours after exercise end to probe


def main():
    df = ac.load()
    print("=== D. Post-exercise recovery window — recurring hypo tail after activity ends? ===\n")
    print(f"{'user':>5} {'ends':>5} {'base_low%':>10} " + " ".join(f"+{h}h" .rjust(7) for h in TAIL_H))
    rows = []
    for u, g in df.groupby("user_id"):
        g = g.sort_values("ts_epoch").reset_index(drop=True)
        thr = np.nanpercentile(g.steps_60m.dropna(), 80)
        if not np.isfinite(thr) or thr < 30:
            print(f"{u:>5}  (insufficient activity)")
            continue
        active = (g.steps_60m > thr).values
        ts = g.ts_epoch.values
        bg = g.bg.values
        # baseline forward-low rate (any cycle)
        def low_after(i, hours):
            hor = ts[i] + hours * 3600
            k = i + 1
            while k < len(g) and ts[k] <= hor:
                if bg[k] < 70:
                    return 1
                k += 1
            return 0
        base = np.mean([low_after(i, 3) for i in range(0, len(g), 5)])   # subsample for speed
        # episode ends: active -> not active
        ends = [i for i in range(1, len(g)) if active[i - 1] and not active[i]]
        if len(ends) < 15:
            print(f"{u:>5} {len(ends):>5}  (too few episodes)")
            continue
        tail_rates = []
        for h in TAIL_H:
            rr = np.mean([low_after(e, h) for e in ends])
            tail_rates.append(rr)
        rows.append((u, len(ends), base, tail_rates))
        print(f"{u:>5} {len(ends):>5} {100*base:>9.1f}% " +
              " ".join(f"{100*tr:>6.0f}%" for tr in tail_rates))

    print("\n--- verdict ---")
    if rows:
        # cohort: median lift at each tail vs base
        base_med = np.median([r[2] for r in rows])
        print(f"cohort median baseline 3h-low rate: {100*base_med:.1f}%")
        for hi, h in enumerate(TAIL_H):
            lifts = [r[3][hi] / r[2] if r[2] > 0 else np.nan for r in rows]
            print(f"  post-exercise +{h}h low-rate vs baseline: {np.nanmedian(lifts):.2f}x")
        print("Read: a sustained >1.3x lift for several hours after exercise ends, consistent across "
              "users, ⇒ a recurring recovery window worth an explicit post-exercise damper. Near-1x ⇒ "
              "the hypo risk is DURING activity (already handled), not a distinct recovery tail.")


if __name__ == "__main__":
    main()
