#!/usr/bin/env python3
"""Figures for the Boost evolution article, drawn from the database rather than from the text.

Four charts, each one a number the article already states. Anything the article claims that a
figure cannot be built for stays as prose.
"""
import os
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore")
DSN = "dbname=oref host=127.0.0.1 port=5432"
OUT = os.path.expanduser(
    "~/StudioProjects/Boost-AAPS-core/backtesting/reports/figs_boost_evolution")

# One hue, light to dark, for magnitude; a second only where a comparison needs two.
INK, MUTED, ACCENT = "#1a1a1a", "#8a8a8a", "#2b6cb0"
WARN = "#c05621"

plt.rcParams.update({
    "figure.dpi": 160, "savefig.dpi": 160, "font.size": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#cccccc", "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "font.family": "DejaVu Sans",
})


def finish(ax, title, sub=None):
    # the subtitle sits above the axes and the title above that, so neither overlaps the other
    ax.set_title(title, loc="left", fontsize=10, color=INK, pad=22 if sub else 6)
    if sub:
        ax.text(0, 1.03, sub, transform=ax.transAxes, fontsize=8, color=MUTED, va="bottom")
    ax.grid(axis="y", color="#eeeeee", lw=0.8)
    ax.set_axisbelow(True)


def fig_shadow_verdicts():
    """What each shadow was worth, as a lift over its own base rate."""
    rows = [("Accelerating meal", 2.07, "earning its place"),
            ("Anticipatory backout", 1.11, "no signal"),
            ("Plateau", 1.10, "no signal"),
            ("ISF shadow", 1.00, "at chance")]
    rows.sort(key=lambda r: r[1])
    fig, ax = plt.subplots(figsize=(6.2, 2.6))
    y = np.arange(len(rows))
    cols = [ACCENT if r[1] >= 1.5 else MUTED for r in rows]
    ax.barh(y, [r[1] for r in rows], color=cols, height=0.55)
    ax.axvline(1.0, color=WARN, lw=1.2, ls="--")
    # inside the plot, level with the top bar, clear of the tick labels below
    ax.text(1.05, len(rows) - 0.35, "no better than chance", color=WARN, fontsize=8, va="center")
    ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlim(0, 2.45); ax.set_ylim(-0.6, len(rows) - 0.15)
    ax.set_xlabel("lift over base rate")
    for i, r in enumerate(rows):
        ax.text(r[1] + 0.04, i, f"{r[1]:.2f}x", va="center", fontsize=8.5, color=INK)
    finish(ax, "Four shadow components, scored against what each claims to anticipate",
           "cohort data, 44,697 to 355,482 cycles each")
    fig.tight_layout(); fig.savefig(f"{OUT}/fig1_shadow_verdicts.png", bbox_inches="tight")
    plt.close(fig)


def fig_truncation():
    """Why the model scores 0.85 on the Commons and 0.59 on the people running it."""
    removed = [0, 10, 20, 30, 40, 47]
    dep = [0.8467, 0.7345, 0.6882, 0.6577, 0.6399, 0.6274]
    ref = [0.8610, 0.7651, 0.7319, 0.7112, 0.6983, 0.6875]
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    ax.plot(removed, dep, color=MUTED, lw=2, marker="o", ms=4, label="shipped model")
    ax.plot(removed, ref, color=ACCENT, lw=2, marker="o", ms=4, label="refit")
    ax.axvline(47, color=WARN, lw=1.2, ls="--")
    ax.text(46, 0.86, "the share the\nlow-glucose guard\nremoves", ha="right", fontsize=8, color=WARN)
    ax.set_xlabel("per cent of cycles removed, highest-risk first")
    ax.set_ylabel("area under the curve")
    ax.set_ylim(0.6, 0.89)
    ax.legend(frameon=False, fontsize=8.5, loc="lower left")
    finish(ax, "The model is judged on the harder half",
           "1,698,846 rows, 183 participants, both models out of sample")
    fig.tight_layout(); fig.savefig(f"{OUT}/fig2_truncation.png", bbox_inches="tight")
    plt.close(fig)


def fig_firing_rates(conn):
    """Why one global calibration cannot serve this cohort."""
    d = pd.read_sql("""select user_id, avg((ml_hypo_risk>=0.30)::int)*100 r
        from boost_decisions where ml_hypo_risk is not null
          and ts_utc > now() - interval '90 days' group by 1 having count(*)>2000
        order by 2""", conn)
    # the database keys a participant by name for one person; the figure carries the registry tag
    d["label"] = d.user_id.replace({"tim": "self"})
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    y = np.arange(len(d))
    ax.barh(y, d.r, color=MUTED, height=0.6)
    ax.axvline(6.62, color=ACCENT, lw=1.5)
    # low on the axis, to the right of the line, where the short bars leave room
    ax.text(7.4, 1.4, "OpenAPS Commons, 6.6%", color=ACCENT, fontsize=8.5, va="center")
    ax.set_yticks(y); ax.set_yticklabels(d.label)
    ax.set_xlabel("per cent of cycles where the damper triggers")
    finish(ax, "The cohort spans two orders of magnitude",
           "each participant's own logged trigger rate, 90 days")
    fig.tight_layout(); fig.savefig(f"{OUT}/fig3_firing_rates.png", bbox_inches="tight")
    plt.close(fig)


def fig_cadence(conn):
    """What the one-minute cycle did to delivery and to time below range."""
    arms = ["dynamic ISF\n5 min", "static ISF\n5 min", "static ISF\n1 min"]
    basal = [13.69, 13.20, 10.13]
    smb = [19.49, 19.48, 29.73]
    tbr = [5.51, 3.53, 8.94]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.6, 2.9))
    x = np.arange(3)
    a1.bar(x, basal, color="#cbd5e0", label="basal", width=0.55)
    a1.bar(x, smb, bottom=basal, color=ACCENT, label="microbolus", width=0.55)
    for i in range(3):
        a1.text(i, basal[i] + smb[i] + 0.8, f"{basal[i]+smb[i]:.1f}", ha="center", fontsize=8.5)
    a1.set_xticks(x); a1.set_xticklabels(arms, fontsize=8)
    a1.set_ylabel("units per 24 h"); a1.set_ylim(0, 52)
    # above the tallest bar and its value label, so neither is obscured
    a1.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(0, 1.0), ncol=2)
    finish(a1, "Delivery")
    a2.bar(x, tbr, color=[MUTED, MUTED, WARN], width=0.55)
    a2.axhline(4.0, color=WARN, lw=1.2, ls="--")
    # in the gap above the shortest bar, where nothing else sits
    a2.text(1.0, 4.35, "consensus 4%", ha="center", fontsize=8, color=WARN)
    for i in range(3):
        a2.text(i, tbr[i] + 0.2, f"{tbr[i]:.1f}", ha="center", fontsize=8.5)
    a2.set_xticks(x); a2.set_xticklabels(arms, fontsize=8)
    a2.set_ylabel("per cent below 70 mg/dL"); a2.set_ylim(0, 11.5)
    finish(a2, "Time below range")
    fig.suptitle("One participant, 28 days: the cadence change moved both",
                 x=0.02, ha="left", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(f"{OUT}/fig4_cadence.png", bbox_inches="tight")
    plt.close(fig)


def main():
    os.makedirs(OUT, exist_ok=True)
    conn = psycopg2.connect(DSN)
    fig_shadow_verdicts()
    fig_truncation()
    fig_firing_rates(conn)
    fig_cadence(conn)
    for f in sorted(os.listdir(OUT)):
        print(f"  {OUT}/{f}")


if __name__ == "__main__":
    main()
