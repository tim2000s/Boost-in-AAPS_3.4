#!/usr/bin/env python3
"""Chart the two actionable anticipation findings: D (post-exercise recovery ramp) + A (habit lead)."""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(__file__)
# D: per-user post-exercise low-rate vs baseline (from d_recovery_window run)
TAILS = [1, 2, 3, 4, 6]
D = {  # user: (baseline%, [ +1h,+2h,+3h,+4h,+6h ])
    "A": (8.6, [4, 7, 9, 12, 18]), "B": (21.2, [8, 16, 23, 27, 38]),
    "C": (20.0, [14, 21, 31, 39, 47]), "D": (38.3, [32, 43, 50, 58, 69]),
    "E": (5.3, [4, 7, 9, 11, 14]), "F": (16.2, [12, 19, 27, 31, 38]),
    "H": (9.7, [2, 5, 8, 11, 15]), "self": (30.1, [14, 22, 30, 36, 50]),
}
# A: per-user (pre-armed %, lead_med, precision)
A = {"A": (38, 55, .68), "B": (0, 5, .63), "C": (91, 56, .57), "D": (34, 50, .69),
     "E": (70, 55, .63), "F": (67, 55, .65), "H": (74, 55, .40), "self": (43, 55, .60)}

PAL = plt.cm.tab10(np.linspace(0, 1, 10))
fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5))

# D: low-rate as MULTIPLE of each user's baseline, vs hours after exercise end
for i, (u, (base, tail)) in enumerate(D.items()):
    mult = [t / base for t in tail]
    a1.plot(TAILS, mult, "-o", color=PAL[i], ms=4, label=u, alpha=0.85)
a1.axhline(1.0, color="#444", lw=1.2, ls="--", label="baseline")
a1.axvspan(0, 2, color="#888", alpha=0.10)
a1.set_xlabel("hours after exercise ends")
a1.set_ylabel("hypo-rate ÷ user baseline")
a1.set_title("D. Post-exercise recovery tail\n(low at +1h → crosses baseline ~+2-3h → climbs)", fontweight="bold", fontsize=10)
a1.legend(fontsize=7, ncol=2); a1.grid(alpha=0.25)

# A: pre-armed% (bar) with lead annotation; precision as marker
us = list(A.keys())
prearm = [A[u][0] for u in us]
prec = [A[u][2] for u in us]
x = np.arange(len(us))
bars = a2.bar(x, prearm, color=[PAL[i] for i in range(len(us))], alpha=0.8, edgecolor="white")
a2.set_xticks(x); a2.set_xticklabels(us, fontsize=8)
a2.set_ylabel("% of exercise episodes PRE-ARMED")
a2.set_title("A. Habit prior leads reactive signal\n(bar=%pre-armed; ● = armed-window precision)", fontweight="bold", fontsize=10)
a2b = a2.twinx()
a2b.plot(x, prec, "ko", ms=7)
a2b.set_ylabel("armed precision"); a2b.set_ylim(0, 1)
a2b.axhline(0.5, color="#aaa", lw=0.8, ls=":")
a2.grid(axis="y", alpha=0.25)

fig.suptitle("Anticipation experiments — the two actionable findings  (V6, self+A–H)", fontsize=12, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.95])
out = os.path.join(HERE, "anticipation_findings.png")
fig.savefig(out, dpi=130)
print("->", out)
