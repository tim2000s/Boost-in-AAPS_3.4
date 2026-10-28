#!/usr/bin/env python3
"""Cohort-wide BG-level comparison — AAPS-Boost vs the oref/Trio reference cohort (2026-07-08).

The Trio cohort emits no budget/steps/HR (see BRAKE_AUDIT / ACTIVITY_HYPO reports), so the
Boost-specific cause attribution, brake audit and activity analysis stay AAPS-only. What CAN
be compared across every user is the glucose distribution and high/low RESIDENCY from BG +
the shared oref fields (IOB / COB / target / eventualBG).

  AAPS-Boost cohort:  boost_decisions (self + A–H), cgm_mgdl.        [Boost-instrumented]
  oref/Trio cohort:   multiuser_combined (U000–U020), cgm_mmol*18.   [oref fields only]

Metrics per user: TIR 70–180, TING 63–140, TBR<70, TBR<54, TAR>180, TAR>250, mean, CV,
high-time%, low-time%, and a COARSE IOB-context split of high/low minutes (the only cause
signal available on both). Writes a comparison chart + a report table.
"""
import os
import sys

import numpy as np
import pandas as pd
import psycopg2

MIN_PER_CYCLE = 5.0


def load():
    conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
    aaps = pd.read_sql("""
        SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
          user_id, ts_epoch AS t, cgm_mgdl AS bg, iob_iob AS iob, sug_cob AS cob,
          tdd
        FROM boost_decisions WHERE cgm_mgdl IS NOT NULL
        ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
    """, conn)
    aaps["platform"] = "AAPS-Boost"
    trio = pd.read_sql("""
        SELECT user_id, ts_relative_sec AS t, cgm_mmol*18.0 AS bg, iob, cob, NULL::float AS tdd
        FROM multiuser_combined WHERE cgm_mmol > 2
    """, conn)
    trio["platform"] = "oref/Trio"
    conn.close()
    df = pd.concat([aaps, trio], ignore_index=True)
    df = df[(df.bg > 20) & (df.bg < 500)]
    # per-user IOB context: low if below the user's own median IOB (tdd not available cohort-wide)
    df["iob_med"] = df.groupby("user_id").iob.transform("median")
    df["iob_hi"] = df.iob > df.iob_med
    return df


def metrics(g):
    bg = g.bg.values
    n = len(bg)
    m = lambda lo, hi: 100 * np.mean((bg >= lo) & (bg < hi))
    hi_mask = bg > 180
    lo_mask = bg < 70
    return dict(
        n=n, mean=round(np.mean(bg), 0), cv=round(100 * np.std(bg) / np.mean(bg), 0),
        TING=round(m(63, 140), 1), TIR=round(m(70, 180), 1),
        TBR70=round(100 * np.mean(lo_mask), 1), TBR54=round(100 * np.mean(bg < 54), 2),
        TAR180=round(100 * np.mean(hi_mask), 1), TAR250=round(100 * np.mean(bg > 250), 1),
        # coarse IOB-context: share of high-time at LOW iob, share of low-time at HIGH iob
        hi_lowIOB=round(100 * np.sum(hi_mask & ~g.iob_hi.values) / hi_mask.sum(), 0) if hi_mask.any() else 0,
        lo_hiIOB=round(100 * np.sum(lo_mask & g.iob_hi.values) / lo_mask.sum(), 0) if lo_mask.any() else 0,
    )


def main():
    df = load()
    rows = []
    for (plat, u), g in df.groupby(["platform", "user_id"]):
        r = dict(platform=plat, user=u)
        r.update(metrics(g))
        rows.append(r)
    res = pd.DataFrame(rows)

    pd.set_option("display.width", 220, "display.max_columns", 30)
    cols = ["platform", "user", "n", "mean", "cv", "TING", "TIR", "TBR70", "TBR54", "TAR180", "TAR250"]
    print("=== per-user BG-level metrics ===")
    print(res[cols].sort_values(["platform", "TIR"], ascending=[True, False]).to_string(index=False))

    print("\n=== platform comparison (median across users) ===")
    agg = res.groupby("platform")[["TING", "TIR", "TBR70", "TBR54", "TAR180", "TAR250", "cv"]].median().round(1)
    agg["n_users"] = res.groupby("platform").size()
    print(agg.to_string())

    # honest note on the coarse cause split
    print("\n=== coarse IOB-context (share of high-time at LOW IOB / low-time at HIGH IOB) — cohort medians ===")
    cc = res.groupby("platform")[["hi_lowIOB", "lo_hiIOB"]].median().round(0)
    print(cc.to_string())
    print("(low IOB = below the user's own median IOB; tdd-normalised context is AAPS-only. "
          "This is the only cause signal computable on the telemetry-poor Trio cohort.)")

    res.to_json(os.path.join(os.path.dirname(__file__), "cohort_bglevel.json"), orient="records")
    chart(res)


def chart(res):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    metrics_plot = ["TIR", "TBR70", "TBR54", "TAR180", "TAR250"]
    plats = ["AAPS-Boost", "oref/Trio"]
    col = {"AAPS-Boost": "#0072B2", "oref/Trio": "#E69F00"}
    fig, axes = plt.subplots(1, len(metrics_plot), figsize=(14, 4.5))
    for ax, met in zip(axes, metrics_plot):
        for i, p in enumerate(plats):
            vals = res[res.platform == p][met].values
            x = np.random.default_rng(1).normal(i, 0.06, len(vals))
            ax.scatter(x, vals, color=col[p], alpha=0.8, s=34, edgecolor="white", linewidth=0.5)
            ax.hlines(np.median(vals), i - 0.22, i + 0.22, color=col[p], lw=2.5)
        ax.set_xticks(range(len(plats)))
        ax.set_xticklabels(["AAPS\nBoost", "oref\nTrio"], fontsize=8)
        ax.set_title(met, fontsize=11, fontweight="bold")
        ax.set_ylabel("% time")
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Cohort BG-level comparison — AAPS-Boost (8) vs oref/Trio reference (21)  ·  dash = median",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out = os.path.join(os.path.dirname(__file__), "cohort_bglevel.png")
    fig.savefig(out, dpi=130)
    print("->", out)


if __name__ == "__main__":
    main()
