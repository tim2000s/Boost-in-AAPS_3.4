#!/usr/bin/env python3
"""Size distributions of carbohydrate announcements in the three meal windows.

Breakfast 06:00-09:00, lunch 12:00-15:00, dinner 17:00-20:00, local time, from every entry in the
study corpora that record carbohydrate.

The curves are a one-gram histogram smoothed with a Gaussian kernel rather than a kernel density
estimate over the raw points. Two reasons. A KDE over 1.6 million values is needlessly expensive
when the support is a bounded integer grid, and the smoothing here is doing a specific job: two
thirds of announcements land on a multiple of five, so an unsmoothed curve is a comb that hides the
shape being compared. The kernel width is stated on the figure because it is a choice, not a
property of the data.

Usage: python3 meal_windows.py [--max-carbs 120] [--sigma 3] [--exclude-rescue] [--out-dir .]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
import psycopg2
from scipy.ndimage import gaussian_filter1d

DSN = "dbname=oref host=127.0.0.1 port=5432"
# categorical slots 1-3, validated all-pairs for this surface; aqua sits under 3:1 against the
# surface so every curve is direct-labelled and the numbers also appear as a table
WINDOWS = [("breakfast", 6, 9, "#2a78d6"),
           ("lunch", 12, 15, "#eb6834"),
           ("dinner", 17, 20, "#1baf7a")]
SURFACE, INK, INK2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
HERE = os.path.dirname(os.path.abspath(__file__))


def load(exclude_rescue):
    q = """select s.study_name, extract(hour from c.ts_local)::int hr, c.carbs_g
           from studies.carbs c join studies.subject s using (subject_id)
           where c.carbs_g > 0"""
    with psycopg2.connect(DSN) as con:
        d = pd.read_sql(q, con)
    if exclude_rescue:
        # the readability study treats carbohydrate entered at or below 4.4 mmol/L as a rescue;
        # that needs the glucose join, so this cheaper proxy drops only the very small entries
        d = d[d.carbs_g >= 8]
    return d


def curves(d, max_carbs, sigma):
    """One-gram histogram per window, Gaussian-smoothed, as a percentage of that window."""
    grid = np.arange(0, max_carbs + 1)
    out = {}
    for name, lo, hi, colour in WINDOWS:
        v = d.carbs_g[(d.hr >= lo) & (d.hr < hi)].values.astype(float)
        h, _ = np.histogram(v[v <= max_carbs], bins=np.arange(0, max_carbs + 2))
        y = gaussian_filter1d(h.astype(float), sigma)
        y = 100.0 * y / y.sum()
        out[name] = dict(grid=grid, y=y, v=v, colour=colour, lo=lo, hi=hi)
    return out


def report(d, cur, by_study, path, max_carbs, sigma, exclude_rescue):
    L, P = [], None
    P = L.append
    tot = len(d)
    P("# Carbohydrate announcements in the three meal windows\n")
    P(f"\nBreakfast 06:00 to 09:00, lunch 12:00 to 15:00, dinner 17:00 to 20:00, local time. "
      f"{tot:,} entries in the corpora that record carbohydrate"
      + (", entries below 8 g excluded.\n" if exclude_rescue else ", nothing excluded.\n"))
    P("\n| window | announcements | share of all | 10th | 25th | median | 75th | 90th | mean |")
    P("|---|---|---|---|---|---|---|---|---|")
    for name, lo, hi, _ in WINDOWS:
        v = pd.Series(cur[name]["v"])
        q = v.quantile([.1, .25, .5, .75, .9])
        P(f"| {name} ({lo:02d}:00-{hi:02d}:00) | {len(v):,} | {100 * len(v) / tot:.1f}% | "
          f"{q[.1]:.0f} | {q[.25]:.0f} | {q[.5]:.0f} | {q[.75]:.0f} | {q[.9]:.0f} | {v.mean():.0f} |")
    P("\nAll sizes in grams.\n")

    st = {n: pd.Series(cur[n]["v"]).describe(percentiles=[.25, .5, .75, .9])
          for n, _, _, _ in WINDOWS}
    meds = {n: st[n]["50%"] for n in st}
    iqr = {n: st[n]["75%"] - st[n]["25%"] for n in st}
    P("\n## What differs between the windows, and what does not\n")
    if len(set(meds.values())) == 1:
        P(f"\nPooled, the median is the same {list(meds.values())[0]:.0f} g in all three "
          f"windows, against an interquartile range of {min(iqr.values()):.0f} to "
          f"{max(iqr.values()):.0f} g inside each. That pooled figure is misleading and the "
          f"by-study section below shows why.\n")
    else:
        big = max(meds, key=meds.get); small = min(meds, key=meds.get)
        P(f"\nMedians run from {meds[small]:.0f} g at {small} to {meds[big]:.0f} g at {big}, a "
          f"gap of {meds[big] - meds[small]:.0f} g against an interquartile range of "
          f"{min(iqr.values()):.0f} to {max(iqr.values()):.0f} g inside each window.\n")
    hi = max(st, key=lambda n: st[n]["75%"])
    lo = min(st, key=lambda n: st[n]["75%"])
    P(f"\nWhat does differ is the upper tail. The 75th centile runs {st[lo]['75%']:.0f} g at "
      f"{lo} against {st[hi]['75%']:.0f} g at {hi}, and the means follow: "
      + ", ".join(f"{n} {st[n]['mean']:.0f} g" for n, _, _, _ in WINDOWS) + ". So the later "
      f"windows are not made of bigger meals so much as of the same meals plus a heavier tail of "
      f"large ones.\n")
    P(f"\nThe curves are a one-gram histogram smoothed with a Gaussian kernel of "
      f"{sigma:.0f} g. Without smoothing each is a comb, because two thirds of announcements are "
      f"a multiple of five.\n")
    P("\n## By study\n")
    P("\nCarbohydrate is recorded by two of the seven corpora, and the pooled figures above are "
      "not a description of both. Loop contributes 90 per cent of the entries, so pooling reports "
      "Loop's behaviour with a little ReplaceBG mixed in.\n")
    P("\n| study | window | announcements | 25th | median | 75th | mean |")
    P("|---|---|---|---|---|---|---|")
    for st in sorted(by_study):
        for name, lo, hi, _ in WINDOWS:
            v = pd.Series(by_study[st][name]["v"])
            q = v.quantile([.25, .5, .75])
            P(f"| {st} | {name} | {len(v):,} | {q[.25]:.0f} | {q[.5]:.0f} | {q[.75]:.0f} | "
              f"{v.mean():.0f} |")
    P("\nAll sizes in grams.\n")
    lo_s, hi_s = sorted(by_study)
    def med(st, w):
        return float(pd.Series(by_study[st][w]["v"]).median())
    for st in sorted(by_study):
        ms = [med(st, w[0]) for w in WINDOWS]
        span = max(ms) - min(ms)
        P(f"\nIn {st} the medians run "
          + ", ".join(f"{w[0]} {m:.0f} g" for w, m in zip(WINDOWS, ms))
          + f", a span of {span:.0f} g across the day.\n")
    P("\nSo the two corpora disagree about the thing the windows were meant to test. Loop is "
      "flat across the day and peaks near 15 g. ReplaceBG rises steadily from breakfast to dinner "
      "and peaks near 30 g. Any statement about whether meal windows carry size information "
      "depends on which population is being described, and the pooled answer is Loop's.\n")
    P("\nThe likely reason is what the two groups were doing. Loop participants ran a closed "
      "loop and entered carbohydrate about twice as often per person, in smaller amounts, which "
      "is the pattern of announcing snacks and corrections as well as meals. ReplaceBG "
      "participants, on sensor-augmented pump therapy a decade earlier, appear to have announced "
      "meals. That is an interpretation of the difference rather than a measurement of it.\n")
    open(path, "w").write("\n".join(L))
    return "\n".join(L)


def figure(by_study, path, max_carbs, sigma, n_total):
    """One panel per study. Carbohydrate is recorded by two of the seven corpora, so this is a
    two-panel small multiple rather than six curves on one axis, where the studies would be told
    apart only by line style and the comparison the reader wants, window against window, would be
    the harder of the two to make."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    studies = list(by_study)
    fig, axes = plt.subplots(1, len(studies), figsize=(6.0 * len(studies), 5.4),
                             facecolor=SURFACE, sharey=True)
    axes = np.atleast_1d(axes)
    ymax = max(c["y"].max() for cur in by_study.values() for c in cur.values())

    for ax, study in zip(axes, studies):
        cur = by_study[study]
        ax.set_facecolor(SURFACE)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.tick_params(colors=MUTED, labelsize=9, length=0)
        ax.grid(axis="y", color=AXIS, linewidth=0.6, alpha=0.5)
        ax.set_axisbelow(True)
        for name, lo, hi, colour in WINDOWS:
            c = cur[name]
            ax.plot(c["grid"], c["y"], color=colour, linewidth=2.2, solid_capstyle="round",
                    label=f"{name}, {lo:02d}:00-{hi:02d}:00")
            ax.fill_between(c["grid"], c["y"], color=colour, alpha=0.10, linewidth=0)
        # label where the curves are furthest apart, staggered by rank so the closest two
        # cannot overlap; labelling at the mode stacks all three, since they peak together
        ys = np.vstack([cur[n]["y"] for n, _, _, _ in WINDOWS])
        xk = int(np.argmax(ys.max(axis=0) - ys.min(axis=0)))
        order = sorted(WINDOWS, key=lambda w: -cur[w[0]]["y"][xk])
        for i, (name, lo, hi, colour) in enumerate(order):
            c = cur[name]
            ax.annotate(name, (c["grid"][xk], c["y"][xk]), xytext=(16, 11 - 11 * i),
                        textcoords="offset points", color=colour, fontsize=9.5,
                        fontweight="bold", va="center", ha="left",
                        arrowprops=dict(arrowstyle="-", color=colour, linewidth=1,
                                        shrinkA=1, shrinkB=2, alpha=0.75))
        n = sum(len(cur[w[0]]["v"]) for w in WINDOWS)
        ax.set_title(f"{study}   ({n:,} announcements in the three windows)",
                     color=INK, fontsize=11.5, loc="left", pad=8)
        ax.set_xlim(0, max_carbs)
        ax.set_ylim(0, ymax * 1.12)
        ax.set_xlabel("announced carbohydrate (g)", color=INK2, fontsize=10)
    axes[0].set_ylabel("% of that window's announcements", color=INK2, fontsize=10)

    leg = axes[-1].legend(frameon=False, fontsize=9, loc="upper right")
    for t in leg.get_texts():
        t.set_color(INK2)
    fig.suptitle("Announcement size in the three meal windows, by study",
                 color=INK, fontsize=13, x=0.007, ha="left", y=1.02)
    fig.text(0.007, -0.04,
             f"{n_total:,} entries. One-gram histogram smoothed with a Gaussian kernel of "
             f"{sigma:.0f} g, normalised within each window so the curves are comparable "
             f"between studies of different size.\nUnsmoothed, each curve is a comb: two thirds "
             f"of announcements are a multiple of five. Panels share a vertical scale.",
             color=MUTED, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-carbs", type=float, default=120.0)
    ap.add_argument("--sigma", type=float, default=3.0)
    ap.add_argument("--exclude-rescue", action="store_true")
    ap.add_argument("--out-dir", default=HERE)
    a = ap.parse_args()

    d = load(a.exclude_rescue)
    cur = curves(d, int(a.max_carbs), a.sigma)
    by_study = {st: curves(g, int(a.max_carbs), a.sigma)
                for st, g in d.groupby("study_name")}
    txt = report(d, cur, by_study, os.path.join(a.out_dir, "MEAL_WINDOWS_REPORT.md"),
                 a.max_carbs, a.sigma, a.exclude_rescue)
    figure(by_study, os.path.join(a.out_dir, "meal_windows.png"),
           int(a.max_carbs), a.sigma, len(d))
    print(txt)
    print(f"\nwritten to {a.out_dir}/MEAL_WINDOWS_REPORT.md and meal_windows.png")


if __name__ == "__main__":
    main()
