#!/usr/bin/env python3
"""Chart the residency attribution: per-user % composition of high-time and low-time by
cause, with the cohort bar, and foreseeable causes marked. Writes residency_attribution.png."""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(__file__)
S = json.load(open(os.path.join(HERE, "residency_episodes.json")))["summary"]
ML = json.load(open(os.path.join(HERE, "residency_ml.json")))

HIGH_CAUSES = ["LATE_CONFIRM", "BRAKE_SUPPRESS", "RECOVERING_HOLD", "CAP_CLIP",
               "UNDERSIZED", "UNCOVERABLE", "NO_MEAL_HIGH"]
LOW_CAUSES = ["ACTIVITY", "STACKING", "RESCUE_OVERSHOOT", "BASAL_DRIFT"]
# categorical palette (Okabe-Ito, CVD-safe)
PAL = ["#E69F00", "#D55E00", "#CC79A7", "#0072B2", "#56B4E9", "#009E73", "#999999", "#F0E442"]

users = [r["user"] for r in S["per_user"]]


def panel(ax, causes, key, title, ml_prefix):
    rows = users + ["COHORT"]
    data = []
    totals = []
    for r in S["per_user"]:
        d = r[key]
        tot = sum(d.values()) or 1
        data.append([100 * d[c] / tot for c in causes])
        totals.append(sum(d.values()))
    cohort = {c: sum(r[key][c] for r in S["per_user"]) for c in causes}
    ctot = sum(cohort.values()) or 1
    data.append([100 * cohort[c] / ctot for c in causes])
    totals.append(ctot)
    data = np.array(data)

    y = np.arange(len(rows))
    left = np.zeros(len(rows))
    for i, c in enumerate(causes):
        ax.barh(y, data[:, i], left=left, color=PAL[i % len(PAL)],
                edgecolor="white", linewidth=0.7, label=c.replace("_", " ").title())
        left += data[:, i]
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r}\n{int(t)}m" for r, t in zip(rows, totals)], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of that user's minutes")
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.axhline(len(users) - 0.5, color="#444", lw=0.8, ls="--")
    # mark foreseeable causes in the legend via the ML json
    fore = {k.split(":")[1] for k, v in ML["avoidability"].items()
            if k.startswith(ml_prefix) and v["x_base"] >= 1.5}
    ax.legend(fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.16),
              ncol=4, framealpha=0.95, title="cause  (★ = foreseeable ≥1.5× base risk)",
              title_fontsize=8)
    for t, c in zip(ax.get_legend().get_texts(), causes):
        if c in fore:
            t.set_text(t.get_text() + "  ★")


fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 6.0))
panel(a1, HIGH_CAUSES, "high", f"HIGH-time (>180) by cause  ·  AUC {ML['auc_hi']:.2f}", "high:")
panel(a2, LOW_CAUSES, "low", f"LOW-time (<70) by cause  ·  AUC {ML['auc_lo']:.2f}", "low:")
fig.suptitle("Boost residency attribution — where the TIR loss comes from  (V6, self+A–H, 2026-02→07)",
             fontsize=12, fontweight="bold")
fig.tight_layout(rect=[0, 0.10, 1, 0.96])
out = os.path.join(HERE, "residency_attribution.png")
fig.savefig(out, dpi=130)
print("->", out)
