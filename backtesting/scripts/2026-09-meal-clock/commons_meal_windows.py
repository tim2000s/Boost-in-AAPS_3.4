#!/usr/bin/env python3
"""Announcement size in the three meal windows, OpenAPS Data Commons.

The Commons is in the database as loop decision records rather than treatments: oref_v5, oref_v6
and oref_v7 partition 183 participants, U000 to U182, with no overlap, and carry carbohydrate on
board but no carbohydrate entries. Announcements are therefore DERIVED from step increases in COB.

That derivation is the main thing to hold in mind when comparing these curves with the Jaeb ones.
COB only rises when carbohydrate is entered, so a step up is an announcement, and its height is the
amount entered less whatever decayed during the five minutes of the step, which biases every size
slightly low. Two entries inside one cycle merge into a single larger step. And COB is what the
loop believed, after its own absorption model, not what the person typed.

Platform labels come from the platform column where the table has one. oref_v5 does not, and is
labelled by its table name rather than guessed at.

Usage: python3 commons_meal_windows.py [--min-carbs 8] [--max-carbs 120] [--sigma 3]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
import psycopg2
from scipy.ndimage import gaussian_filter1d

DSN = "dbname=oref host=127.0.0.1 port=5432"
TABLES = [("oref_v5", "oref_v5 (unlabelled)"),
          ("oref_v6", "AndroidAPS, pre-DynISF"),
          ("oref_v7", "OpenAPS oref0 SMB")]
WINDOWS = [("breakfast", 6, 9, "#2a78d6"),
           ("lunch", 12, 15, "#eb6834"),
           ("dinner", 17, 20, "#1baf7a")]
SURFACE, INK, INK2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
HERE = os.path.dirname(os.path.abspath(__file__))


def derive(min_carbs):
    """Announcements as positive steps in COB, per participant, in chronological order."""
    rows = []
    with psycopg2.connect(DSN) as c:
        for table, label in TABLES:
            # the COB column is quoted uppercase in some of these tables and lowercase in
            # others, so resolve the real name rather than assume one spelling
            col = pd.read_sql("""select column_name from information_schema.columns
                 where table_name = %s and lower(column_name) = 'sug_cob'""",
                 c, params=(table,)).column_name.iloc[0]
            sql = (f'select user_id, ts_relative_sec, hour, "{col}" as sug_cob '
                   f'from {table} where "{col}" is not null '
                   f'order by user_id, ts_relative_sec')
            d = pd.read_sql(sql, c)
            for uid, g in d.groupby("user_id", sort=False):
                cob = g.sug_cob.values.astype(float)
                hr = g.hour.values
                ts = g.ts_relative_sec.values.astype(float)
                step = np.diff(cob)
                # only where the rows are actually adjacent in time; a gap in the record would
                # otherwise read as a step
                adjacent = np.diff(ts) <= 15 * 60
                k = np.flatnonzero((step >= min_carbs) & adjacent)
                for i in k:
                    rows.append((label, uid, int(hr[i + 1]), float(step[i])))
    return pd.DataFrame(rows, columns=["platform", "user_id", "hr", "carbs_g"])


def curves(d, max_carbs, sigma):
    grid = np.arange(0, max_carbs + 1)
    out = {}
    for name, lo, hi, colour in WINDOWS:
        v = d.carbs_g[(d.hr >= lo) & (d.hr < hi)].values.astype(float)
        if len(v) < 50:
            continue
        h, _ = np.histogram(v[v <= max_carbs], bins=np.arange(0, max_carbs + 2))
        y = gaussian_filter1d(h.astype(float), sigma)
        out[name] = dict(grid=grid, y=100.0 * y / y.sum(), v=v, colour=colour, lo=lo, hi=hi)
    return out


def figure(by_plat, path, max_carbs, sigma, n_total, min_carbs):
    n_win = sum(len(c['v']) for cur in by_plat.values() for c in cur.values())
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plats = [p for p in by_plat if by_plat[p]]
    fig, axes = plt.subplots(1, len(plats), figsize=(5.6 * len(plats), 5.4),
                             facecolor=SURFACE, sharey=True)
    axes = np.atleast_1d(axes)
    ymax = max(c["y"].max() for cur in by_plat.values() for c in cur.values())

    for ax, plat in zip(axes, plats):
        cur = by_plat[plat]
        ax.set_facecolor(SURFACE)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.tick_params(colors=MUTED, labelsize=9, length=0)
        ax.grid(axis="y", color=AXIS, linewidth=0.6, alpha=0.5)
        ax.set_axisbelow(True)
        for name, lo, hi, colour in WINDOWS:
            if name not in cur:
                continue
            c = cur[name]
            ax.plot(c["grid"], c["y"], color=colour, linewidth=2.2, solid_capstyle="round",
                    label=f"{name}, {lo:02d}:00-{hi:02d}:00")
            ax.fill_between(c["grid"], c["y"], color=colour, alpha=0.10, linewidth=0)
        present = [w for w in WINDOWS if w[0] in cur]
        ys = np.vstack([cur[w[0]]["y"] for w in present])
        xk = int(np.argmax(ys.max(axis=0) - ys.min(axis=0)))
        for i, (name, lo, hi, colour) in enumerate(sorted(present, key=lambda w: -cur[w[0]]["y"][xk])):
            c = cur[name]
            ax.annotate(name, (c["grid"][xk], c["y"][xk]), xytext=(16, 11 - 11 * i),
                        textcoords="offset points", color=colour, fontsize=9.5,
                        fontweight="bold", va="center", ha="left",
                        arrowprops=dict(arrowstyle="-", color=colour, linewidth=1,
                                        shrinkA=1, shrinkB=2, alpha=0.75))
        n = sum(len(cur[w[0]]["v"]) for w in present)
        ax.set_title(f"{plat}\n{n:,} in the three windows", color=INK, fontsize=11, loc="left",
                     pad=8)
        ax.set_xlim(0, max_carbs); ax.set_ylim(0, ymax * 1.12)
        ax.set_xlabel("carbohydrate entered (g)", color=INK2, fontsize=10)
    axes[0].set_ylabel("% of that window's announcements", color=INK2, fontsize=10)
    leg = axes[-1].legend(frameon=False, fontsize=9, loc="upper right")
    for t in leg.get_texts():
        t.set_color(INK2)
    fig.suptitle("OpenAPS Data Commons: announcement size in the three meal windows",
                 color=INK, fontsize=13, x=0.007, ha="left", y=1.03)
    fig.text(0.007, -0.05,
             f"{n_win:,} announcements in the three windows, of {n_total:,} across the whole "
             f"day. DERIVED from step increases in carbohydrate on board of {min_carbs:.0f} g "
             f"or more, not from recorded entries.\n"
             f"A step is the amount entered less whatever decayed inside the five-minute "
             f"cycle, so sizes are biased slightly low and entries inside one cycle merge. "
             f"Panels share a vertical scale.",
             color=MUTED, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-carbs", type=float, default=8.0)
    ap.add_argument("--max-carbs", type=float, default=120.0)
    ap.add_argument("--sigma", type=float, default=3.0)
    ap.add_argument("--out-dir", default=HERE)
    a = ap.parse_args()

    d = derive(a.min_carbs)
    by_plat = {p: curves(g, int(a.max_carbs), a.sigma) for p, g in d.groupby("platform")}

    L, P = [], None
    P = L.append
    P("# OpenAPS Data Commons: announcement size in the three meal windows\n")
    P(f"\n{len(d):,} announcements from {d.user_id.nunique()} participants across "
      f"{d.platform.nunique()} platform groups. Breakfast 06:00-09:00, lunch 12:00-15:00, "
      f"dinner 17:00-20:00.\n")
    P(f"\nThe Commons carries no carbohydrate entries, only carbohydrate on board, so an "
      f"announcement here is a step increase in COB of {a.min_carbs:.0f} g or more between "
      f"adjacent cycles. That measures the amount entered less whatever decayed inside the cycle, "
      f"which biases every size slightly low, and merges entries made inside one cycle. It is a "
      f"different measurement from the recorded entries in the Jaeb corpora and the two should "
      f"not be compared to the gram.\n")
    P("\n| platform | window | announcements | 25th | median | 75th | mean |")
    P("|---|---|---|---|---|---|---|")
    for plat in sorted(by_plat):
        for name, lo, hi, _ in WINDOWS:
            if name not in by_plat[plat]:
                continue
            v = pd.Series(by_plat[plat][name]["v"])
            q = v.quantile([.25, .5, .75])
            P(f"| {plat} | {name} | {len(v):,} | {q[.25]:.0f} | {q[.5]:.0f} | {q[.75]:.0f} | "
              f"{v.mean():.0f} |")
    P("\nAll sizes in grams.\n")
    for plat in sorted(by_plat):
        ms = [float(pd.Series(by_plat[plat][w[0]]["v"]).median())
              for w in WINDOWS if w[0] in by_plat[plat]]
        P(f"\nIn {plat} the window medians run "
          + ", ".join(f"{m:.0f}" for m in ms) + f" g, a span of {max(ms) - min(ms):.0f} g.\n")
    open(os.path.join(a.out_dir, "COMMONS_WINDOWS_REPORT.md"), "w").write("\n".join(L))
    figure(by_plat, os.path.join(a.out_dir, "commons_meal_windows.png"),
           int(a.max_carbs), a.sigma, len(d), a.min_carbs)
    print("\n".join(L))


if __name__ == "__main__":
    main()
