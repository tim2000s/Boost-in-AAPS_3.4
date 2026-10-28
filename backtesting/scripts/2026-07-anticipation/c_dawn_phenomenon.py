#!/usr/bin/env python3
"""C — Recurring dawn phenomenon: is the early-morning rise regular enough to pre-empt? (2026-07-09)

A dawn rise = a fasting BG climb in the early morning driven by hormonal insulin resistance. If it
recurs at a consistent time/magnitude per user, an anticipatory pre-dawn correction could pre-empt
it (relevant to the morning-deficit finding). Question: how REGULAR is it per user?

Per night, in 03:00–08:00 local, with low COB/quiet (fasting proxy): the max sustained rise
(delta over the window) and the hour it starts. Bayesian: posterior on rise magnitude + onset hour
per user; report the fraction of nights showing a rise and the tightness of onset timing.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(__file__))
import anticip_common as ac  # noqa

DAWN_START, DAWN_END = 3 * 60, 8 * 60      # local minutes
RISE_MGDL = 25                              # fasting rise over the window to count as a dawn event
QUIET_COB = 5                               # COB below this = fasting-ish


def main():
    df = ac.load()
    print("=== C. Dawn phenomenon — recurring, pre-emptable morning rise? ===\n")
    print(f"{'user':>5} {'nights':>7} {'dawn%':>6} {'med_rise':>9} {'onset(med)':>11} {'onset_SD':>9}")
    rows = []
    for u, g in df.groupby("user_id"):
        g = g.sort_values("ts_epoch")
        events = []
        nnights = 0
        for nd, night in g.groupby("nightdate"):
            w = night[(night.minute >= DAWN_START) & (night.minute <= DAWN_END)]
            w = w[(w.cob.fillna(0) < QUIET_COB)]
            if len(w) < 6:
                continue
            nnights += 1
            w = w.sort_values("minute")
            bg = w.bg.values
            mn = w.minute.values
            # max rise from any trough to a later peak within the window
            trough = np.inf
            trough_m = None
            best = 0
            best_onset = None
            for i in range(len(bg)):
                if bg[i] < trough:
                    trough = bg[i]
                    trough_m = mn[i]
                elif bg[i] - trough > best:
                    best = bg[i] - trough
                    best_onset = trough_m
            if best >= RISE_MGDL:
                events.append((best, best_onset))
        if nnights < 20:
            print(f"{u:>5} {nnights:>7}  (too few fasting nights)")
            continue
        dawn_pct = 100 * len(events) / nnights
        if events:
            rises = np.array([e[0] for e in events])
            onsets = np.array([e[1] for e in events])
            med_rise = np.median(rises)
            onset_med = np.median(onsets)
            onset_sd = onsets.std()
            hh, mm = int(onset_med // 60), int(onset_med % 60)
            rows.append((u, dawn_pct, med_rise, onset_sd))
            print(f"{u:>5} {nnights:>7} {dawn_pct:>5.0f}% {med_rise:>8.0f}m {f'{hh:02d}:{mm:02d}':>11} "
                  f"{onset_sd:>8.0f}m")
        else:
            print(f"{u:>5} {nnights:>7} {dawn_pct:>5.0f}%   (no dawn events)")

    if rows:
        r = pd.DataFrame(rows, columns=["u", "pct", "rise", "onset_sd"])
        print("\n--- verdict ---")
        print(f"median dawn-event frequency: {r.pct.median():.0f}% of fasting nights, "
              f"median rise {r.rise.median():.0f} mg/dL")
        print(f"median onset SD: {r.onset_sd.median():.0f} min "
              f"({'regular ⇒ pre-emptable' if r.onset_sd.median()<75 else 'timing too variable to pre-empt'})")
        print("Read: high frequency + tight onset ⇒ a per-user pre-dawn correction is worth testing; "
              "low/irregular ⇒ dawn is not a reliable anticipatory target.")


if __name__ == "__main__":
    main()
