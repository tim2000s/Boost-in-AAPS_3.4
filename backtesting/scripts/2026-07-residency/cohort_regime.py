#!/usr/bin/env python3
"""Regime decomposition of the Boost-vs-oref/Trio edge — WHERE does it live? (2026-07-08)

The cohort finding: Boost-dosing cohort (AAPS, V1+ generation) shows a small, consistent
TIR edge over the oref/Trio reference cohort (+2.9pp raw / +1.2pp difficulty-adjusted, NS).
This asks where that edge concentrates:
  - by LOCAL HOUR (overnight vs day) — a night-mode signal would live 00–06;
  - by METRIC (is the TIR gain from less high-time TAR>180, or less low-time TBR<70?).

Local hour: AAPS uses per-user tz_offset from the site registry (tz only, no secrets read);
the oref/Trio table already carries a local `hour` column. Median-across-users per cohort.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import psycopg2

# tz offset per AAPS tag (hours) — read from the registry, tz field only
_TZ = {}
try:
    for s in json.load(open(os.path.expanduser("~/.config/boost_backtest/sites.json")))["sites"]:
        _TZ[s["tag"]] = int(s.get("tz_offset_hours", 1))
except Exception:
    pass


def load():
    conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
    a = pd.read_sql("""
        SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
          user_id, ts_utc, cgm_mgdl AS bg
        FROM boost_decisions WHERE cgm_mgdl IS NOT NULL
        ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
    """, conn)
    uth = pd.to_datetime(a.ts_utc, utc=True, format="mixed").dt.hour
    a["hour"] = [(h + _TZ.get(u, 1)) % 24 for h, u in zip(uth, a.user_id)]
    a["platform"] = "AAPS-Boost"
    t = pd.read_sql("""
        SELECT user_id, hour, cgm_mmol*18.0 AS bg FROM multiuser_combined WHERE cgm_mmol > 2
    """, conn)
    t["platform"] = "oref/Trio"
    conn.close()
    df = pd.concat([a[["user_id", "hour", "bg", "platform"]], t], ignore_index=True)
    return df[(df.bg > 20) & (df.bg < 500)]


def tir(x):
    return 100 * np.mean((x >= 70) & (x < 180))


def main():
    df = load()

    # per-user TIR/TBR/TAR by regime, then median across users per platform
    df["night"] = df.hour.between(0, 5)   # 00:00–05:59 local

    def cohort_regime(mask, label):
        sub = df[mask]
        rows = []
        for (p, u), g in sub.groupby(["platform", "user_id"]):
            bg = g.bg.values
            if len(bg) < 200:
                continue
            rows.append((p, tir(bg), 100 * np.mean(bg < 70), 100 * np.mean(bg > 180)))
        r = pd.DataFrame(rows, columns=["platform", "TIR", "TBR", "TAR"])
        med = r.groupby("platform")[["TIR", "TBR", "TAR"]].median()
        b, o = med.loc["AAPS-Boost"], med.loc["oref/Trio"]
        print(f"\n{label}:")
        print(f"  {'':8}{'TIR':>7}{'TBR<70':>8}{'TAR>180':>9}")
        print(f"  Boost  {b.TIR:>7.1f}{b.TBR:>8.1f}{b.TAR:>9.1f}")
        print(f"  oref   {o.TIR:>7.1f}{o.TBR:>8.1f}{o.TAR:>9.1f}")
        print(f"  GAP    {b.TIR-o.TIR:>+7.1f}{b.TBR-o.TBR:>+8.1f}{b.TAR-o.TAR:>+9.1f}")
        return dict(tir_gap=b.TIR - o.TIR, tbr_gap=b.TBR - o.TBR, tar_gap=b.TAR - o.TAR)

    print("=== REGIME DECOMPOSITION of the Boost-vs-oref edge ===")
    allr = cohort_regime(df.index.notna(), "ALL")
    night = cohort_regime(df.night, "OVERNIGHT (00:00–05:59 local)")
    day = cohort_regime(~df.night, "DAYTIME (06:00–23:59 local)")

    print("\n--- where the TIR edge lives ---")
    print(f"  overnight TIR gap {night['tir_gap']:+.1f}pp  vs  daytime {day['tir_gap']:+.1f}pp")
    print(f"  overall TIR gap {allr['tir_gap']:+.1f}pp splits: less high-time (TAR gap {allr['tar_gap']:+.1f}pp) "
          f"vs less low-time (TBR gap {allr['tbr_gap']:+.1f}pp)")

    # hourly TIR gap curve
    hourly = []
    for h in range(24):
        sub = df[df.hour == h]
        per = sub.groupby(["platform", "user_id"]).bg.apply(lambda x: tir(x.values) if len(x) > 50 else np.nan)
        med = per.groupby("platform").median()
        if "AAPS-Boost" in med and "oref/Trio" in med:
            hourly.append((h, med["AAPS-Boost"], med["oref/Trio"]))
    hr = pd.DataFrame(hourly, columns=["hour", "boost", "oref"])
    hr["gap"] = hr.boost - hr.oref
    chart(hr, allr, night, day)


def chart(hr, allr, night, day):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.6))
    a1.plot(hr.hour, hr.boost, "-o", color="#0072B2", label="AAPS-Boost", ms=4)
    a1.plot(hr.hour, hr.oref, "-o", color="#E69F00", label="oref/Trio", ms=4)
    a1.axvspan(0, 6, color="#888", alpha=0.12, label="overnight")
    a1.set_xlabel("local hour"); a1.set_ylabel("median TIR %"); a1.set_title("TIR by hour", fontweight="bold")
    a1.legend(fontsize=8); a1.grid(alpha=0.25); a1.set_xticks(range(0, 24, 3))
    colors = ["#0072B2" if g >= 0 else "#D55E00" for g in hr.gap]
    a2.bar(hr.hour, hr.gap, color=colors, edgecolor="white", linewidth=0.5)
    a2.axvspan(0, 6, color="#888", alpha=0.12)
    a2.axhline(0, color="#444", lw=0.8)
    a2.set_xlabel("local hour"); a2.set_ylabel("Boost − oref TIR (pp)")
    a2.set_title(f"TIR edge by hour  (overnight {night['tir_gap']:+.1f} vs day {day['tir_gap']:+.1f})", fontweight="bold")
    a2.grid(axis="y", alpha=0.25); a2.set_xticks(range(0, 24, 3))
    fig.suptitle("Where the Boost-vs-oref TIR edge lives", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out = os.path.join(os.path.dirname(__file__), "cohort_regime.png")
    fig.savefig(out, dpi=130)
    print("->", out)


if __name__ == "__main__":
    main()
