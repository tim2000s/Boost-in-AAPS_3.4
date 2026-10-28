#!/usr/bin/env python3
"""Correction chart: the cumulative D view (misleading, window-length artifact) vs the
de-artifacted per-hour hazard (the truth — a modest, flat ~1.2x elevation)."""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(__file__)
# cohort cumulative multiples (original D, artifact-inflated)
CUM_H = [1, 2, 3, 4, 6]
CUM = [0.59, 0.91, 1.20, 1.48, 1.93]
# de-artifacted per-hour hazard multiples (cohort median)
HAZ_H = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]
HAZ = [1.26, 1.21, 1.18, 1.21, 1.09, 1.05, 0.95, 0.90]

fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(CUM_H, CUM, "-o", color="#D55E00", ms=6, lw=2,
        label="cumulative low-rate ÷ fixed-3h baseline (ARTIFACT — window length inflates late)")
ax.plot(HAZ_H, HAZ, "-s", color="#0072B2", ms=6, lw=2,
        label="per-hour hazard ÷ matched baseline (DE-ARTIFACTED — the truth)")
ax.axhline(1.0, color="#444", lw=1.2, ls="--")
ax.axvspan(0, 2, color="#888", alpha=0.10, label="V4 recovery window (2h default)")
ax.set_xlabel("hours after exercise ends")
ax.set_ylabel("hypo-rate ÷ baseline")
ax.set_title("Post-exercise recovery tail: the delayed 2× ramp was a window-length artifact\n"
             "De-artifacted, it's a modest ~1.2× elevation, immediate & fairly flat — V4's 2h window is ~right",
             fontsize=10, fontweight="bold")
ax.legend(fontsize=8, loc="upper left")
ax.grid(alpha=0.25)
fig.tight_layout()
out = os.path.join(HERE, "recovery_tail_correction.png")
fig.savefig(out, dpi=130)
print("->", out)
