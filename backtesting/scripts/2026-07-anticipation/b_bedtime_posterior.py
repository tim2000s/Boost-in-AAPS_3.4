#!/usr/bin/env python3
"""B — Learned bedtime posterior → can a clock prior LEAD the HR corroboration? (2026-07-09)

Current sleep detector: clock window + HR corroboration. If HR dies overnight, SLEEPING is never
reached (the failure we keep hitting). Idea: a per-(user,weekday) bedtime POSTERIOR — tight for
regular sleepers — that can carry the SLEEPING transition on the clock prior alone when HR is dead.

Sleep-state isn't logged, so proxy sleep-ONSET = first time after 19:00 local that steps stay
quiescent (steps_60m below the user's sleep floor) for a sustained block, in the 19:00–04:00 window.

Bayesian: hierarchical Normal on onset-minute per (user, weekday), partially pooled toward the
user's overall onset (James–Stein shrinkage; borrows strength for sparse weekdays). Report the
posterior SD (tightness = clock reliability) and whether a learned prior beats a fixed clock window
at predicting the next night's onset (time-split OOS).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(__file__))
import anticip_common as ac  # noqa

QUIET_STEPS = 60          # steps_60m below this = quiescent
SUSTAIN_MIN = 90          # must stay quiet this long to count as onset
WIN_START, WIN_END = 19 * 60, 28 * 60   # 19:00 .. 04:00(+24) local minutes


def onsets_for_user(g):
    """One sleep-onset minute per night (minutes since local midnight, may exceed 1440 for after-00:00)."""
    g = g.sort_values("ts_epoch")
    out = []
    for nd, night in g.groupby("nightdate"):
        night = night.sort_values("ts_epoch")
        mins = night.minute.values.astype(float)
        # unwrap: evening minutes 19:00-23:59 stay, 00:00-04:00 become +1440
        m = np.where(mins < 12 * 60, mins + 1440, mins)
        steps = night.steps_60m.values.astype(float)
        order = np.argsort(m)
        m, steps = m[order], steps[order]
        sel = (m >= WIN_START) & (m <= WIN_END)
        m, steps = m[sel], steps[sel]
        if len(m) < 6:
            continue
        # first index where steps stay < QUIET_STEPS for SUSTAIN_MIN continuously
        onset = None
        for i in range(len(m)):
            if steps[i] < QUIET_STEPS:
                j = i
                while j + 1 < len(m) and m[j + 1] - m[i] < SUSTAIN_MIN and steps[j + 1] < QUIET_STEPS:
                    j += 1
                if m[j] - m[i] >= SUSTAIN_MIN - 5 or (j == len(m) - 1 and m[j] - m[i] > 45):
                    onset = m[i]
                    break
        if onset is not None:
            out.append((pd.Timestamp(nd).dayofweek, onset))
    return pd.DataFrame(out, columns=["dow", "onset"])


def main():
    df = ac.load()
    print("=== B. Bedtime posterior — is sleep-onset regular enough for a clock prior to lead HR? ===\n")
    print(f"{'user':>5} {'nights':>7} {'onset(med)':>11} {'overall_SD':>11} {'wkday_SD':>9} "
          f"{'OOS_MAE':>8} {'fixed_MAE':>10} {'gain':>6}")
    rows = []
    for u, g in df.groupby("user_id"):
        o = onsets_for_user(g)
        if len(o) < 20:
            print(f"{u:>5} {len(o):>7}  (too few onsets)")
            continue
        overall_sd = o.onset.std()
        # within-weekday SD (pooled): how much tighter is per-weekday than overall
        wk_sd = np.sqrt(o.groupby("dow").onset.var().mean())
        # OOS: predict each night's onset from the shrunken per-weekday mean of PRIOR nights
        o = o.reset_index(drop=True)
        pred_learned, pred_fixed, actual = [], [], []
        for i in range(len(o)):
            past = o.iloc[:i]
            if len(past) < 10:
                continue
            gm = past.onset.mean()
            wk = past[past.dow == o.dow[i]].onset
            # James–Stein-ish shrink weekday mean toward global by count
            k = len(wk)
            mu = (k * wk.mean() + 3 * gm) / (k + 3) if k > 0 else gm
            pred_learned.append(mu)
            pred_fixed.append(gm)             # "fixed clock" = user's overall mean onset
            actual.append(o.onset[i])
        if len(actual) < 10:
            continue
        mae_l = np.mean(np.abs(np.array(pred_learned) - actual))
        mae_f = np.mean(np.abs(np.array(pred_fixed) - actual))
        med = o.onset.median()
        hh = int((med % 1440) // 60)
        mm = int(med % 60)
        rows.append((u, len(o), overall_sd, wk_sd, mae_l, mae_f))
        print(f"{u:>5} {len(o):>7} {f'{hh:02d}:{mm:02d}':>11} {overall_sd:>10.0f}m {wk_sd:>8.0f}m "
              f"{mae_l:>7.0f}m {mae_f:>9.0f}m {mae_f-mae_l:>+5.0f}m")

    r = pd.DataFrame(rows, columns=["u", "n", "sd", "wksd", "mae_l", "mae_f"])
    print("\n--- verdict ---")
    print(f"median onset SD: {r.sd.median():.0f} min  (tight <60m ⇒ clock prior is reliable enough to "
          f"carry SLEEPING when HR dies)")
    print(f"per-weekday vs overall SD: {r.wksd.median():.0f} vs {r.sd.median():.0f} min "
          f"({'weekday structure helps' if r.wksd.median() < r.sd.median()-5 else 'weekday adds little'})")
    print(f"learned vs fixed-clock onset MAE: {r.mae_l.median():.0f} vs {r.mae_f.median():.0f} min "
          f"(learned better by {r.mae_f.median()-r.mae_l.median():+.0f} min median)")
    print("Read: a tight SD means a per-(user,weekday) bedtime prior can lead the HR corroboration — "
          "the upgrade to 'clock window + HR' that survives overnight HR death.")


if __name__ == "__main__":
    main()
