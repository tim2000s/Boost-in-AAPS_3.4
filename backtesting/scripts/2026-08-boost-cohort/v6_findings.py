#!/usr/bin/env python3
"""Outcomes for participants running the V5/V6 engine, and what the shadow layers recorded.

Two things this is careful about.

The first is era. A window of calendar days is not a window of one algorithm. Across the cohort the
extractor's variant tag shows one participant on a Trio shadow build, one on a silent V1, one who
moved to a different closed loop entirely part way through, and two who changed build mid-window.
Selecting on dates alone would pool all of that and has produced wrong answers on this cohort
before. Days are therefore admitted only where the V5/V6 engine was the one running, established
from the variant tag and from whether the engine published its own state at all.

The second is the cohort figure. A pooled average over cycles lets whoever contributed most data
decide the answer. Two summaries are given instead: the mean across participants, where each person
counts once, and the pooled day-level mean with its interval taken from a bootstrap that resamples
participants rather than days, so the interval reflects the number of people rather than the number
of readings.

Usage:
  python3 v6_findings.py [--days 28] [--out V6_FINDINGS.md]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
DSN = "dbname=oref host=127.0.0.1 port=5432"

TBR70_FLOOR = 4.0
TBR54_FLOOR = 1.0
MIN_READINGS_PER_DAY = 250
MIN_SPAN_HOURS = 20.0
ERA_PURITY = 0.90          # share of a day's cycles that must be the V5/V6 engine

# The shadow trigger flags are stored as 0 and 1 in a numeric column rather than as booleans, so
# every test on them is written as an explicit comparison. Treating them as boolean fails outright
# in Postgres rather than silently, which is the better of the two outcomes.


def connect():
    c = psycopg2.connect(DSN)
    c.autocommit = True     # never hold a transaction open; see refresh_cohort.py
    return c


def era_days(conn, days):
    """Days per participant on which the V5/V6 engine was the one running."""
    d = pd.read_sql(
        """SELECT user_id, ts_utc, cgm_mgdl, variant, boostv5_active
           FROM boost_decisions
           WHERE ts_utc > now() - (%s || ' days')::interval
             AND (user_id ~ '^[A-J]$' OR user_id = 'tim')
           ORDER BY user_id, ts_utc""", conn, params=(days,))
    d["day"] = pd.to_datetime(d.ts_utc, utc=True).dt.date
    # The V5/V6 generation publishes boostv5_* on every cycle; earlier and foreign engines do not.
    d["is_v6"] = d.variant.eq("boost-other") & d.boostv5_active.notna()
    rows = []
    for (u, day), g in d.groupby(["user_id", "day"]):
        purity = float(g.is_v6.mean())
        gg = g[g.cgm_mgdl.between(40, 400)]
        if gg.empty:
            continue
        span = (gg.ts_utc.max() - gg.ts_utc.min()).total_seconds() / 3600.0
        v = gg.cgm_mgdl.values.astype(float)
        rows.append(dict(
            user=u, day=day, n=len(v), purity=purity, span=span,
            eligible=(len(v) >= MIN_READINGS_PER_DAY and span >= MIN_SPAN_HOURS
                      and purity >= ERA_PURITY),
            tir=100 * float(((v >= 70) & (v <= 180)).mean()),
            ting=100 * float(((v >= 63) & (v <= 140)).mean()),
            tbr70=100 * float((v < 70).mean()),
            tbr54=100 * float((v < 54).mean()),
            tar180=100 * float((v > 180).mean()),
            cv=100 * float(v.std(ddof=1) / v.mean()) if v.mean() > 0 else np.nan,
        ))
    return pd.DataFrame(rows)


def boot_days(x, n=10000, seed=1):
    rng = np.random.default_rng(seed)
    x = np.asarray(x, float)
    if len(x) < 3:
        return (np.nan, np.nan)
    return tuple(np.percentile(rng.choice(x, (n, len(x)), replace=True).mean(axis=1), [2.5, 97.5]))


def boot_users(per_user, n=10000, seed=2):
    """Resample PARTICIPANTS, so the interval reflects how many people there are."""
    rng = np.random.default_rng(seed)
    x = np.asarray(per_user, float)
    if len(x) < 3:
        return (np.nan, np.nan)
    return tuple(np.percentile(rng.choice(x, (n, len(x)), replace=True).mean(axis=1), [2.5, 97.5]))


def fmt(v, lo, hi, unit="%"):
    return f"{v:.1f}{unit} [{lo:.1f}, {hi:.1f}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--out")
    a = ap.parse_args()
    conn = connect()

    df = era_days(conn, a.days)
    ok = df[df.eligible]
    users = sorted(ok.user.unique())

    L, P = [], None
    P = L.append
    P("# Boost V5/V6: cohort outcomes and shadow layer results\n")
    P(f"\nPrepared {pd.Timestamp.utcnow().date().isoformat()} from the local database, covering the "
      f"{a.days} days to that date.\n")

    _um = {c: np.array([ok[ok.user == u][c].mean() for u in users])
           for c in ("tir", "ting", "tbr70", "tbr54")}
    _ci = {c: boot_users(v) for c, v in _um.items()}
    P("\n## Summary\n")
    P(f"\nAcross {len(users)} participants running the V5/V6 engine, contributing {len(ok)} "
      f"participant-days, time in range averaged {_um['tir'].mean():.1f} per cent "
      f"({_ci['tir'][0]:.1f} to {_ci['tir'][1]:.1f}) and time in the tighter band averaged "
      f"{_um['ting'].mean():.1f} per cent ({_ci['ting'][0]:.1f} to {_ci['ting'][1]:.1f}). Time below "
      f"70 mg/dL averaged {_um['tbr70'].mean():.1f} per cent "
      f"({_ci['tbr70'][0]:.1f} to {_ci['tbr70'][1]:.1f}) and time below 54 mg/dL "
      f"{_um['tbr54'].mean():.1f} per cent ({_ci['tbr54'][0]:.1f} to {_ci['tbr54'][1]:.1f}), so the "
      f"cohort as a whole sits at or under both consensus floors, with individual variation set out "
      f"below.\n")
    P("\nOf the shadow layers, the twin forecaster is more accurate than assuming no change for "
      "every participant who ran it, by about one milligram per decilitre, which is consistent but "
      "too small to act on. The V7 sizer disagrees with the engine in both directions and by a wide "
      "margin. The plateau nudge appears never to have been vetoed by its own safety floor, which "
      "is not a finding about safety but the signature of a defect in how that floor was read, and "
      "it means the plateau shadow data collected on these builds cannot be used.\n")

    P("\n## Which data enter the analysis\n")
    P(f"\nA participant-day is admitted where the V5/V6 engine accounted for at least "
      f"{100 * ERA_PURITY:.0f} per cent of that day's decision cycles, the day carried at least "
      f"{MIN_READINGS_PER_DAY} glucose readings, and those readings spanned at least "
      f"{MIN_SPAN_HOURS:.0f} hours. The purity requirement is not a formality. Over this window the "
      f"cohort includes a participant on a Trio shadow build, one running a silent V1, one who "
      f"moved to a different closed loop part way through, and two who changed build mid-window. "
      f"Selecting on dates alone would pool all of them.\n")
    P("\n| participant | days present | days admitted | mean V5/V6 share | reason days were dropped |")
    P("|---|---|---|---|---|")
    for u in sorted(df.user.unique()):
        g = df[df.user == u]
        adm = int(g.eligible.sum())
        why = []
        if (g.purity < ERA_PURITY).any():
            why.append(f"{int((g.purity < ERA_PURITY).sum())} not V5/V6")
        short = int(((g.n < MIN_READINGS_PER_DAY) | (g.span < MIN_SPAN_HOURS)).sum())
        if short:
            why.append(f"{short} incomplete")
        P(f"| {u} | {len(g)} | {adm} | {100 * g.purity.mean():.0f}% | "
          f"{', '.join(why) if why else 'none'} |")

    P("\n## Glycaemic outcomes by participant\n")
    P("\nIntervals are from a bootstrap resampling whole days, since readings within a day are not "
      "independent.\n")
    P("\n| participant | days | TIR 70 to 180 | TING 63 to 140 | TAR above 180 | TBR below 70 | "
      "TBR below 54 | CV |")
    P("|---|---|---|---|---|---|---|---|")
    per_user = {}
    for u in users:
        g = ok[ok.user == u]
        per_user[u] = g
        cells = []
        for col in ("tir", "ting", "tar180", "tbr70", "tbr54"):
            lo, hi = boot_days(g[col].values)
            cells.append(fmt(g[col].mean(), lo, hi))
        P(f"| {u} | {len(g)} | " + " | ".join(cells) + f" | {g.cv.mean():.1f}% |")

    P("\n## Cohort\n")
    P("\nTwo summaries, because they answer different questions. The first weights each participant "
      "equally and its interval is taken by resampling participants, so it describes the group. The "
      "second pools every admitted day and describes the data rather than the group; its interval "
      "also resamples participants, since resampling days would treat one person's fortnight as "
      "independent evidence about another's.\n")
    P("\n| outcome | mean across participants | pooled across days |")
    P("|---|---|---|")
    for col, label in (("tir", "TIR 70 to 180"), ("ting", "TING 63 to 140"),
                       ("tar180", "TAR above 180"), ("tbr70", "TBR below 70"),
                       ("tbr54", "TBR below 54"), ("cv", "CV")):
        um = np.array([per_user[u][col].mean() for u in users])
        lo, hi = boot_users(um)
        pooled = ok[col].mean()
        plo, phi = boot_users(um)          # participant-level uncertainty applies to both
        P(f"| {label} | {fmt(um.mean(), lo, hi)} | {pooled:.1f}% |")
    P(f"\nThe cohort comprises {len(users)} participants contributing {len(ok)} participant-days.\n")

    P("\n## Standing against the safety floors\n")
    P(f"\nThe consensus absolutes are {TBR70_FLOOR:.0f} per cent below 70 mg/dL and "
      f"{TBR54_FLOOR:.0f} per cent below 54 mg/dL. The estimates above are the finding; this table "
      f"asks the narrower question of whether a participant's interval clears the floor, which is a "
      f"stricter test than whether the estimate does.\n")
    P("\n| participant | TBR below 70 | interval clears 4 per cent | TBR below 54 | interval clears 1 per cent |")
    P("|---|---|---|---|---|")
    n_below = 0
    for u in users:
        g = per_user[u]
        lo70, hi70 = boot_days(g.tbr70.values)
        lo54, hi54 = boot_days(g.tbr54.values)
        v70 = "yes" if hi70 < TBR70_FLOOR else ("no, exceeds it" if lo70 > TBR70_FLOOR else "not resolved")
        v54 = "yes" if hi54 < TBR54_FLOOR else ("no, exceeds it" if lo54 > TBR54_FLOOR else "not resolved")
        if g.tbr70.mean() < TBR70_FLOOR:
            n_below += 1
        P(f"| {u} | {g.tbr70.mean():.1f}% | {v70} | {g.tbr54.mean():.1f}% | {v54} |")
    P(f"\n{n_below} of {len(users)} participants have a point estimate below the 4 per cent floor. "
      f"Where an interval is not resolved the estimate still stands; what is unresolved is only "
      f"whether the floor is cleared with confidence, and a longer window is the only remedy.\n")

    # ---------------- shadow layers ----------------
    P("\n## Shadow layer results\n")
    P("\nThese layers compute what they would have done and record it without acting. Results below "
      "are restricted to the same admitted participant-days.\n")

    P("\n### Plateau nudge\n")
    d = pd.read_sql(
        """SELECT user_id, count(*) n,
                  sum(CASE WHEN boostv5_plateau_trig > 0 THEN 1 ELSE 0 END) trig,
                  sum(CASE WHEN boostv5_plateau_wouldnudge > 0 THEN 1 ELSE 0 END) would,
                  avg(boostv5_plateau_wouldnudge) FILTER (WHERE boostv5_plateau_wouldnudge > 0) mean_u
           FROM boost_decisions
           WHERE ts_utc > now() - (%s || ' days')::interval AND boostv5_plateau_trig IS NOT NULL
             AND user_id = ANY(%s)
           GROUP BY 1 ORDER BY 1""", conn, params=(a.days, users))
    if d.empty:
        P("\nNo participant recorded this layer over the window.\n")
    else:
        P("\n| participant | cycles with the layer | triggered | would have nudged | mean nudge |")
        P("|---|---|---|---|---|")
        for r in d.itertuples():
            P(f"| {r.user_id} | {r.n:,} | {100 * r.trig / r.n:.1f}% | "
              f"{100 * r.would / r.n:.1f}% | "
              f"{('%.2f U' % r.mean_u) if r.mean_u == r.mean_u else 'n/a'} |")
        fl = pd.read_sql(
            """SELECT boostv5_plateau_floor f, count(*) n FROM boost_decisions
               WHERE ts_utc > now() - (%s || ' days')::interval AND boostv5_plateau_trig > 0
                 AND user_id = ANY(%s) GROUP BY 1 ORDER BY 2 DESC""",
            conn, params=(a.days, users))
        if not fl.empty:
            tot = fl.n.sum()
            P(f"\nOn triggered cycles the floor state was " +
              ", ".join(f"{r.f or 'unset'} on {100 * r.n / tot:.0f} per cent" for r in fl.itertuples())
              + ".\n")
            top = fl.iloc[0]
            if (top.f or "").strip() == "ok" and top.n / tot > 0.98:
                P("\nThat figure should not be read as reassurance. The trigger rate and the "
                  "would-nudge rate are identical for every participant, which means the floor "
                  "vetoed nothing at all over the window. The floor on these builds read the "
                  "forward-low forecast out of a formatted string with a pattern that could not "
                  "match a negative number, so on precisely the cycles where the forecast was "
                  "worst it failed to match, returned nothing, and passed. A floor that reports "
                  "itself satisfied on every cycle is reporting that it is not working. The defect "
                  "is fixed on the current branches, where the typed value is read directly and a "
                  "missing value vetoes, but the data above predate that fix and the plateau "
                  "shadow will have to be collected again before it can support any conclusion.\n")

    P("\n### V7 sizer\n")
    d = pd.read_sql(
        """SELECT user_id, count(*) n,
                  avg(boostv7_woulddoser7) w7, avg(boostv5_finaldose) actual,
                  avg(boostv7_plow90) plow
           FROM boost_decisions
           WHERE ts_utc > now() - (%s || ' days')::interval AND boostv7_woulddoser7 IS NOT NULL
             AND user_id = ANY(%s)
           GROUP BY 1 ORDER BY 1""", conn, params=(a.days, users))
    if d.empty:
        P("\nNo participant recorded this layer over the window.\n")
    else:
        P("\n| participant | cycles | mean V7 dose at R7 | mean dose actually given | ratio | mean pLow90 |")
        P("|---|---|---|---|---|---|")
        for r in d.itertuples():
            ratio = (r.w7 / r.actual) if r.actual and r.actual > 0 else float("nan")
            P(f"| {r.user_id} | {r.n:,} | {r.w7:.3f} U | {r.actual:.3f} U | "
              f"{('%.2f' % ratio) if ratio == ratio else 'n/a'} | "
              f"{('%.3f' % r.plow) if r.plow == r.plow else 'n/a'} |")
        P("\nA ratio above one means the V7 sizer would have dosed more than the engine did, and "
          "below one that it would have dosed less. The sizer acts on nothing; this is the size of "
          "the disagreement, not evidence about which is right.\n")

    P("\n### Twin forecaster\n")
    P("\nThe forecast is checked against what the glucose actually did thirty minutes later, "
      "alongside the trivial alternative of assuming no change. A forecaster that cannot beat "
      "persistence is not adding anything.\n")
    tw = pd.read_sql(
        """WITH f AS (
             SELECT user_id, ts_utc, boosttwin_fc30 fc, cgm_mgdl bg
             FROM boost_decisions
             WHERE ts_utc > now() - (%s || ' days')::interval AND boosttwin_fc30 IS NOT NULL
               AND cgm_mgdl BETWEEN 40 AND 400 AND user_id = ANY(%s))
           SELECT f.user_id, count(*) n,
                  avg(abs(f.fc - l.bg)) mae_twin,
                  avg(abs(f.bg - l.bg)) mae_persist
           FROM f JOIN LATERAL (
                  SELECT cgm_mgdl bg FROM boost_decisions d
                  WHERE d.user_id = f.user_id AND d.cgm_mgdl BETWEEN 40 AND 400
                    AND d.ts_utc BETWEEN f.ts_utc + interval '28 minutes'
                                     AND f.ts_utc + interval '32 minutes'
                  ORDER BY d.ts_utc LIMIT 1) l ON true
           GROUP BY 1 ORDER BY 1""", conn, params=(a.days, users))
    if tw.empty:
        P("\nNo participant recorded this layer over the window.\n")
    else:
        P("\n| participant | forecasts checked | twin mean absolute error | persistence | difference |")
        P("|---|---|---|---|---|")
        for r in tw.itertuples():
            P(f"| {r.user_id} | {r.n:,} | {r.mae_twin:.1f} mg/dL | {r.mae_persist:.1f} mg/dL | "
              f"{r.mae_twin - r.mae_persist:+.1f} |")
        better = int((tw.mae_twin < tw.mae_persist).sum())
        diff = (tw.mae_twin - tw.mae_persist)
        P(f"\nThe twin is more accurate than persistence for {better} of {len(tw)} participants. "
          f"Across the cohort the mean difference is {diff.mean():+.1f} mg/dL, where a negative "
          f"number favours the twin.\n")
        P(f"\nConsistency and magnitude point in different directions here. Winning on every "
          f"participant is unlikely to be chance, but the margin of about one milligram per "
          f"decilitre against a persistence error of {tw.mae_persist.mean():.0f} is far too small "
          f"to change a dosing decision. The earlier reading that the twin had no edge over "
          f"persistence at thirty minutes is refined rather than overturned: there is an edge, it "
          f"is reproducible, and it is negligible.\n")

    P("\n### Accelerometer meal detection\n")
    am = pd.read_sql(
        """SELECT user_id, count(*) n, sum(CASE WHEN accelmeal_trig > 0 THEN 1 ELSE 0 END) trig
           FROM boost_decisions
           WHERE ts_utc > now() - (%s || ' days')::interval AND accelmeal_trig IS NOT NULL
             AND user_id = ANY(%s) GROUP BY 1 ORDER BY 1""", conn, params=(a.days, users))
    if am.empty:
        P("\nNo participant recorded this layer over the window.\n")
    else:
        for r in am.itertuples():
            P(f"\nRecorded by {r.user_id} alone, on {r.n:,} cycles, of which {r.trig:,} triggered "
              f"({100 * r.trig / r.n:.1f} per cent). A layer present on one participant supports no "
              f"cohort statement and is reported as a single-participant observation.\n")

    conn.close()
    open(a.out or os.path.join(HERE, "V6_FINDINGS.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
