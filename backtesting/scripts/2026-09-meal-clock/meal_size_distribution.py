#!/usr/bin/env python3
"""The distribution of every reported carbohydrate entry in the study corpora.

Read straight from the studies schema rather than from the meal-readability extraction, so this is
everything anybody entered, before the 8 g floor, the rescue exclusion and the merging of nearby
entries that the modelling work applies.

It is not a bell curve, and the two panels show why in different ways. At one-gram resolution the
distribution is a comb: two thirds of entries land on a multiple of five, because people estimate
carbohydrate and then round it. At five-gram resolution that comb disappears and the underlying
shape is visible, right-skewed with a long upper tail. A normal curve of the same mean and standard
deviation is drawn over it for reference, and a log-normal, which is the usual first guess for a
positive right-skewed quantity. Neither describes it.

Usage: python3 meal_size_distribution.py [--max-carbs 150] [--out-dir .]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
import psycopg2
from scipy import stats

DSN = "dbname=oref host=127.0.0.1 port=5432"
SEQ_FILL, SEQ_DARK = "#86b6ef", "#256abf"
SURFACE, INK, INK2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
NORMAL, LOGNORM = "#b8500f", "#0d366b"
HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    with psycopg2.connect(DSN) as c:
        d = pd.read_sql("""select s.study_name, c.carbs_g
                           from studies.carbs c join studies.subject s using (subject_id)
                           where c.carbs_g > 0""", c)
    return d


def figure(d, path, max_carbs=150.0):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = d.carbs_g.values.astype(float)
    v = x[x <= max_carbs]
    mu, sd = x.mean(), x.std()
    lmu, lsd = np.log(x).mean(), np.log(x).std()

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4), facecolor=SURFACE)
    for ax in axes:
        ax.set_facecolor(SURFACE)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.tick_params(colors=MUTED, labelsize=9, length=0)
        ax.grid(axis="y", color=AXIS, linewidth=0.6, alpha=0.5)
        ax.set_axisbelow(True)
        ax.set_xlim(0, max_carbs)
        ax.set_xlabel("reported carbohydrate (g)", color=INK2, fontsize=10)

    grid = np.linspace(0.5, max_carbs, 600)
    npdf = stats.norm.pdf(grid, mu, sd)
    lpdf = stats.lognorm.pdf(grid, lsd, scale=np.exp(lmu))

    # left: one-gram bins, where the rounding behaviour is the dominant feature
    axes[0].hist(v, bins=np.arange(0, max_carbs + 1, 1), color=SEQ_FILL, linewidth=0, density=True)
    axes[0].plot(grid, npdf, color=NORMAL, linewidth=2, label="normal, same mean and SD")
    axes[0].set_ylabel("density", color=INK2, fontsize=10)
    axes[0].set_title("At 1 g resolution", color=INK, fontsize=11.5, loc="left", pad=8)
    axes[0].annotate("every spike is a multiple of 5 g", (32, axes[0].get_ylim()[1] * 0.82),
                     color=INK2, fontsize=9)
    # the same normal appears in both panels; direct-label it here rather than repeat the legend
    axes[0].annotate("normal, same mean and SD", (mu, stats.norm.pdf(mu, mu, sd)),
                     xytext=(58, 0.030), textcoords="data", color=NORMAL, fontsize=9,
                     arrowprops=dict(arrowstyle="-", color=NORMAL, linewidth=1.1,
                                     shrinkA=2, shrinkB=3, alpha=0.8))

    # right: five-gram bins, which removes the comb and leaves the shape
    axes[1].hist(v, bins=np.arange(0, max_carbs + 5, 5), color=SEQ_FILL, linewidth=0, density=True)
    axes[1].plot(grid, npdf, color=NORMAL, linewidth=2, label="normal, same mean and SD")
    axes[1].plot(grid, lpdf, color=LOGNORM, linewidth=2, linestyle=(0, (5, 2)), label="log-normal")
    axes[1].set_title("At 5 g resolution", color=INK, fontsize=11.5, loc="left", pad=8)
    leg = axes[1].legend(frameon=False, fontsize=9, loc="upper right")
    for t in leg.get_texts():
        t.set_color(INK2)

    sk, ku = stats.skew(x), stats.kurtosis(x)
    studies = ", ".join(sorted(d.study_name.unique()))
    fig.suptitle(f"{len(d):,} reported carbohydrate entries ({studies}): not a bell curve",
                 color=INK, fontsize=13, x=0.007, ha="left", y=1.005)
    fig.text(0.007, -0.03,
             f"Every entry above zero from the two corpora that record carbohydrate, before any "
             f"filtering. "
             f"Mean {mu:.1f} g, median {np.median(x):.0f} g, SD {sd:.1f}. Skew {sk:.2f} and excess "
             f"kurtosis {ku:.2f}, where a normal distribution is 0 and 0. "
             f"{100 * (x > max_carbs).mean():.1f}% above {max_carbs:.0f} g are off-scale.",
             color=MUTED, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-carbs", type=float, default=150.0)
    ap.add_argument("--out-dir", default=HERE)
    a = ap.parse_args()
    d = load()
    x = d.carbs_g.values.astype(float)
    print(f"{len(d):,} reported entries from {d.study_name.nunique()} corpora")
    print(f"  mean {x.mean():.1f} g   median {np.median(x):.0f} g   SD {x.std():.1f}")
    print(f"  skew {stats.skew(x):+.2f}   excess kurtosis {stats.kurtosis(x):+.2f}"
          f"   (a normal distribution is 0 and 0)")
    print(f"  multiples of 5 g: {100 * (x % 5 == 0).mean():.0f}%"
          f"   multiples of 10 g: {100 * (x % 10 == 0).mean():.0f}%")
    print(f"  on a log scale, skew {stats.skew(np.log(x)):+.2f}"
          f"   excess kurtosis {stats.kurtosis(np.log(x)):+.2f}")
    figure(d, os.path.join(a.out_dir, "meal_size_distribution.png"), a.max_carbs)
    print(f"\nwritten to {a.out_dir}/meal_size_distribution.png")


if __name__ == "__main__":
    main()
