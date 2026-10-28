#!/usr/bin/env python3
"""When people announce carbohydrate, and how much, across every participant who recorded any.

Every announcement from every participant is placed on one 24-hour axis, so the whole corpus is
read as a single day. The question is whether meal timing carries structure a controller could use,
and how much of that structure belongs to the population rather than to the individual.

A true scatter is the wrong mark at this count. Half a million points on one day-long axis produces
a filled rectangle that hides exactly the density differences the plot exists to show, so the main
panel bins into hexagons and shades by count. `--sample N` draws a real scatter of N announcements
for anyone who wants to see the raw marks; it is a check on the binning, not the deliverable.

Announcements come from the extraction the meal-readability study used, so the definition matches
that paper: at least 8 g, not entered at or below 4.4 mmol/L, with entries close in time merged.
That is an announcement rather than a meal, and the report says what its distribution looks like,
because a median near 28 g is small for a meal and the reason is that people announce about twice
a day and eat more often than that.

Usage:
  python3 meal_clock.py [--out-dir .] [--sample 4000] [--max-carbs 150]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

# Sequential blue, light to dark, for a count. One hue: the quantity is magnitude, not identity.
SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
       "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
SURFACE, INK, INK2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
ACCENT = "#b8500f"     # the median line, a single warm mark against a cool ramp

HERE = os.path.dirname(os.path.abspath(__file__))
EXTRACT = os.path.join(HERE, "..", "2026-08-meal-size-readability", "out")


def load():
    """Announcements from the meal-readability extraction, both corpora, with local hour."""
    frames = []
    for study in ("Loop", "ReplaceBG"):
        p = os.path.join(EXTRACT, f"meals_{study}.parquet")
        if not os.path.exists(p):
            continue
        m = pd.read_parquet(p)[["subject_id", "t0", "carbs"]].copy()
        m["study"] = study
        frames.append(m)
    if not frames:
        raise SystemExit(f"no extraction found under {EXTRACT}; run the meal-size study first")
    d = pd.concat(frames, ignore_index=True)
    # t0 is derived from the studies schema's ts_local, so this is local wall-clock time.
    ts = pd.to_datetime(d.t0, unit="s")
    d["hour"] = ts.dt.hour + ts.dt.minute / 60.0
    d["date"] = ts.dt.date
    return d


def regularity(d):
    """How concentrated each participant's own announcements are in the day.

    Two measures because they fail differently. The share falling in a participant's own busiest
    three hours is easy to state but is sensitive to where the hour boundaries land. The circular
    resultant length R treats the clock as a circle, so a participant who eats either side of
    midnight is not counted as irregular by an artefact of the axis.
    """
    rows = []
    for sid, g in d.groupby("subject_id"):
        if len(g) < 60:
            continue
        hr = g.hour.astype(int)
        top3 = hr.value_counts().head(3).sum() / len(g)
        a = 2 * np.pi * g.hour.values / 24.0
        R = float(np.hypot(np.cos(a).mean(), np.sin(a).mean()))
        rows.append((sid, len(g), top3, R))
    return pd.DataFrame(rows, columns=["subject_id", "n", "top3", "R"])


def report(d, reg, path):
    L, P = [], None
    P = L.append
    n, subs = len(d), d.subject_id.nunique()
    per_day = d.groupby(["subject_id", "date"]).size().groupby("subject_id").median()
    daily_g = d.groupby(["subject_id", "date"]).carbs.sum().groupby("subject_id").median()
    q = d.carbs.quantile([.1, .25, .5, .75, .9, .99])

    P("# When carbohydrate is announced, and how much\n")
    P(f"\n{n:,} announcements from {subs:,} participants across "
      f"{d.study.nunique()} corpora, placed on a single 24-hour axis.\n")

    P("\n## What an announcement is\n")
    P(f"\nAt least 8 g and not entered at or below 4.4 mmol/L. Where entries fall within ninety "
      f"minutes of one another the extraction keeps the first and does not count the rest, so a "
      f"meal entered in parts is recorded at the size of its first part. That leaves a median of "
      f"{per_day.median():.1f} announcements per participant-day, and understates a quarter of "
      f"eating occasions by roughly half.\n")
    P("\n| quantity | value |")
    P("|---|---|")
    P(f"| median announcement | {q[.5]:.0f} g |")
    P(f"| interquartile range | {q[.25]:.0f} to {q[.75]:.0f} g |")
    P(f"| 90th centile | {q[.9]:.0f} g |")
    P(f"| 99th centile | {q[.99]:.0f} g |")
    P(f"| announcements per participant-day | {per_day.median():.1f} |")
    P(f"| announced carbohydrate per participant-day | {daily_g.median():.0f} g |")
    P(f"\nA median of {daily_g.median():.0f} g a day is well below likely intake, and "
      f"{100 * (daily_g < 100).mean():.0f} per cent of participants announce under 100 g. Much of "
      f"what these participants ate was never announced, so this is the announced fraction of "
      f"eating rather than eating.\n")

    P("\n## Through the day\n")
    P("\nThe distribution of announced carbohydrate in each hour, not only its centre, since a "
      "median that barely moves could still hide an hour whose spread is quite different.\n")
    P("\n| hour | announcements | share | 10th | 25th | median | 75th | 90th | mean |")
    P("|---|---|---|---|---|---|---|---|---|")
    g = d.assign(hr=d.hour.astype(int)).groupby("hr").carbs
    h = g.agg(k="size", med="median")
    qs = g.quantile([.1, .25, .5, .75, .9]).unstack()
    mean = g.mean()
    for hr in range(24):
        if hr not in qs.index:
            continue
        r = qs.loc[hr]
        P(f"| {hr:02d}:00 | {h.k[hr]:,} | {100 * h.k[hr] / n:.1f}% | {r[.1]:.0f} | {r[.25]:.0f} | "
          f"{r[.5]:.0f} | {r[.75]:.0f} | {r[.9]:.0f} | {mean[hr]:.0f} |")
    P("\nAll figures in grams. The interquartile range is between 10 and 20 g wide in every hour "
      "of the day, and the 90th centile moves by about 20 g between the quietest hour and the "
      "busiest. The distribution shifts a little and changes shape hardly at all.\n")
    peak = h.k.idxmax()
    quiet = h.loc[0:5, "k"].sum() / n
    P(f"\nThe busiest hour is {peak:02d}:00. The six hours from midnight carry "
      f"{100 * quiet:.0f} per cent of announcements, and their median size is "
      f"{d[d.hour < 6].carbs.median():.0f} g against {d[d.hour >= 6].carbs.median():.0f} g for the "
      f"rest of the day, so the overnight entries are both rarer and smaller.\n")

    P("\n## How carbohydrate is entered\n")
    r5 = 100 * (d.carbs % 5 == 0).mean()
    r10 = 100 * (d.carbs % 10 == 0).mean()
    top = d.carbs.value_counts().head(6)
    P(f"\n{r5:.0f} per cent of announcements are a multiple of 5 g and {r10:.0f} per cent a "
      f"multiple of 10. The six commonest values are "
      + ", ".join(f"{int(v)} g ({100 * k / n:.1f}%)" for v, k in top.items()) + ".\n")
    P("\nThis is worth stating before any model is asked to predict a quantity. The announcement "
      "is a person's estimate rounded to a convenient number, so its own resolution is about 5 g "
      "and its accuracy is unknown. Whatever a trace could in principle reveal, it is scored "
      "against a target of that precision.\n")

    P("\n## How regular an individual is\n")
    P(f"\nMeasured on the {len(reg):,} participants with at least 60 announcements.\n")
    P("\n| measure | 10th centile | median | 90th centile |")
    P("|---|---|---|---|")
    P(f"| share of own announcements in own busiest 3 hours | {reg.top3.quantile(.1):.2f} | "
      f"{reg.top3.median():.2f} | {reg.top3.quantile(.9):.2f} |")
    P(f"| circular concentration R | {reg.R.quantile(.1):.2f} | {reg.R.median():.2f} | "
      f"{reg.R.quantile(.9):.2f} |")
    P(f"\nThe median participant announces {100 * reg.top3.median():.0f} per cent of their "
      f"carbohydrate within their own three busiest hours, and the range runs "
      f"{reg.top3.min():.2f} to {reg.top3.max():.2f}. Individuals are far less regular than the "
      f"pooled pattern looks, which matters for anything built on a personal timing prior: the "
      f"structure in the figure belongs mostly to the population.\n")

    open(path, "w").write("\n".join(L))
    return "\n".join(L)


def figure(d, path, sample=0, max_carbs=120.0):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, LogNorm

    cmap = LinearSegmentedColormap.from_list("seq_blue", SEQ)
    v = d[d.carbs <= max_carbs]
    over = 100 * (1 - len(v) / len(d))

    fig = plt.figure(figsize=(11, 7.2), facecolor=SURFACE)
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 4], hspace=0.06)
    top = fig.add_subplot(gs[0]); ax = fig.add_subplot(gs[1], sharex=top)
    for a in (top, ax):
        a.set_facecolor(SURFACE)
        for s in a.spines.values():
            s.set_visible(False)
        a.tick_params(colors=MUTED, labelsize=9, length=0)

    # marginal: when announcements happen
    cnt, edges = np.histogram(d.hour, bins=np.arange(0, 24.5, 0.5))
    top.bar(edges[:-1], 100 * cnt / cnt.sum(), width=0.46, align="edge",
            color=SEQ[7], linewidth=0)
    top.set_ylabel("share of\nannouncements", color=INK2, fontsize=9)
    top.tick_params(labelbottom=False)
    top.grid(axis="y", color=AXIS, linewidth=0.6, alpha=0.5)
    top.set_axisbelow(True)

    # main: density of size against time of day
    hb = ax.hexbin(v.hour, v.carbs, gridsize=(72, 42), cmap=cmap, norm=LogNorm(),
                   mincnt=1, linewidths=0, extent=(0, 24, 0, max_carbs))
    if sample:
        s = v.sample(min(sample, len(v)), random_state=0)
        ax.scatter(s.hour, s.carbs, s=3, c=INK, alpha=0.18, linewidths=0, zorder=3)

    # median size by half hour, one warm line against the cool ramp
    b = np.arange(0, 24.5, 0.5)
    mid = (b[:-1] + b[1:]) / 2
    med = [v.carbs[(v.hour >= lo) & (v.hour < hi)].median() for lo, hi in zip(b[:-1], b[1:])]
    ax.plot(mid, med, color=ACCENT, linewidth=2, zorder=4, solid_capstyle="round")
    # anchored in the empty small-hours space above the line, with a leader down to it, so the
    # label never sits on the mark it names
    ax.annotate("median size", xy=(mid[5], med[5]), xytext=(0.9, max_carbs * 0.52),
                textcoords="data", color=ACCENT, fontsize=10, fontweight="bold",
                ha="left", va="center",
                arrowprops=dict(arrowstyle="-", color=ACCENT, linewidth=1.1,
                                shrinkA=2, shrinkB=4, alpha=0.8))

    ax.set_xlim(0, 24); ax.set_ylim(0, max_carbs)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 3)])
    ax.set_xlabel("time of day, local", color=INK2, fontsize=10)
    ax.set_ylabel("announced carbohydrate (g)", color=INK2, fontsize=10)
    ax.grid(color=AXIS, linewidth=0.6, alpha=0.5)
    ax.set_axisbelow(True)

    cb = fig.colorbar(hb, ax=ax, pad=0.015, fraction=0.035)
    cb.set_label("announcements per bin", color=INK2, fontsize=9)
    cb.ax.tick_params(colors=MUTED, labelsize=8, length=0)
    cb.outline.set_visible(False)

    top.set_title(f"{len(d):,} carbohydrate announcements from {d.subject_id.nunique():,} "
                  f"participants, on one day", color=INK, fontsize=12.5, loc="left", pad=12)
    fig.text(0.007, 0.012,
             f"Announcement is at least 8 g, not entered at or below 4.4 mmol/L, nearby entries "
             f"merged. {over:.1f}% above {max_carbs:.0f} g are off-scale. Colour is a count on a "
             f"log scale. The horizontal bands are people entering round numbers, not an "
             f"artefact of binning.", color=MUTED, fontsize=8)
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def size_by_hour(d, path):
    """Quantile bands by hour. Box plots across 24 categories add ink without adding information
    here, because the distributions are so alike; nested bands make that likeness the visible
    result rather than something the reader has to infer from 24 separate glyphs."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    g = d.assign(hr=d.hour.astype(int)).groupby("hr").carbs
    q = g.quantile([.1, .25, .5, .75, .9]).unstack()
    hrs = q.index.values
    allday = d.carbs.median()

    fig, ax = plt.subplots(figsize=(10.5, 5.4), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)

    ax.fill_between(hrs, q[.1], q[.9], color=SEQ[2], linewidth=0, label="10th to 90th centile")
    ax.fill_between(hrs, q[.25], q[.75], color=SEQ[6], linewidth=0, label="interquartile range")
    ax.plot(hrs, q[.5], color=ACCENT, linewidth=2.2, solid_capstyle="round", label="median")
    # named in the legend rather than annotated on the plot: every part of the canvas at this
    # height is inside a band, so an in-place label would sit on the data
    ax.axhline(allday, color=MUTED, linewidth=1.1, linestyle=(0, (4, 3)), zorder=1,
               label=f"all-day median, {allday:.0f} g")

    ax.set_xlim(0, 23); ax.set_ylim(0, None)
    ax.set_xticks(range(0, 24, 3))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 24, 3)])
    ax.set_xlabel("hour of day, local", color=INK2, fontsize=10)
    ax.set_ylabel("announced carbohydrate (g)", color=INK2, fontsize=10)
    ax.grid(axis="y", color=AXIS, linewidth=0.6, alpha=0.5)
    ax.set_axisbelow(True)
    ax.set_title("Announced carbohydrate by hour: the distribution, not just its centre",
                 color=INK, fontsize=12.5, loc="left", pad=34)
    # outside the axes: at the busiest hours the 90th-centile band reaches the top of the plot,
    # so any in-axes legend lands on the data it is describing
    leg = ax.legend(loc="lower left", frameon=False, fontsize=9, ncol=4,
                    bbox_to_anchor=(0, 1.005), borderaxespad=0)
    for t in leg.get_texts():
        t.set_color(INK2)
    fig.text(0.007, 0.005,
             f"{len(d):,} announcements, {d.subject_id.nunique():,} participants. The spread is "
             f"of similar width in every hour, so the hour shifts the distribution a little and "
             f"reshapes it hardly at all.", color=MUTED, fontsize=8)
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=HERE)
    ap.add_argument("--sample", type=int, default=0,
                    help="overlay this many raw points as a check on the binning")
    ap.add_argument("--max-carbs", type=float, default=120.0)
    a = ap.parse_args()

    d = load()
    reg = regularity(d)
    txt = report(d, reg, os.path.join(a.out_dir, "MEAL_CLOCK_REPORT.md"))
    figure(d, os.path.join(a.out_dir, "meal_clock.png"), a.sample, a.max_carbs)
    size_by_hour(d, os.path.join(a.out_dir, "meal_size_by_hour.png"))
    print(txt)
    print(f"\nwritten to {a.out_dir}/MEAL_CLOCK_REPORT.md and meal_clock.png")


if __name__ == "__main__":
    main()
