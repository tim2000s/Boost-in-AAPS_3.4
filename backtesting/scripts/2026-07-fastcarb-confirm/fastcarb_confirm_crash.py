#!/usr/bin/env python3
"""Fast-carb CONFIRMED-shot crash analysis (2026-07-10).

Motivation: Tim's 48h review — 3 fast-carb events (07-09 12:13, 19:54; 07-10 14:00) where Boost
fired a large single CONFIRMED shot (2.4–2.6U) LATE, near the peak of a modest, self-clearing fast
carb, and the dose landed into the natural fall → crash (nadir 44/60/64). Hypothesis: on fast carbs
that peak MODESTLY and are already DECELERATING at confirm time, the full velocity-scaled CONFIRMED
dose over-treats and drives a crash — so a trim guard on that signal would cut crashes without
giving up high-time.

Design (per-user; pooled AND per-user-median reported — 2026-07-10 audit lesson):
  * A CONFIRMED "shot event" = cluster of CONFIRMED cycles with dose>0.3U within 60 min → one event
    (confirm point = first cycle; total_dosed = sum over the cluster).
  * At confirm: bg, delta_acceleration (decelerating if <0 = fired past the inflection), IOB, and
    the peak bg in [confirm, +30min] (modest if < MODEST_PEAK).
  * Outcome: nadir bg in [confirm, +3h] → CRASH if <70; max forward bg → NEEDED if peak>180.
  * Discriminator: does (decelerating AND modest-peak) at confirm separate CRASH events from NEEDED
    events? Price the trim guard: crashes it flags vs needed-doses it would wrongly trim.

Counterfactual caveat: we CANNOT simulate the trimmed BG (no glucodynamic model). "Crashes flagged"
= crash events the guard would have trimmed (priced by insulin), NOT a simulated non-crash. Directional.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "2026-07-v7-foundation"))
import v7_common as vc  # noqa

MODEST_PEAK = 170.0     # a CONFIRMED shot whose excursion peaks below this is "modest / self-clearing"
CLUSTER_MIN = 60        # cluster CONFIRMED-dose cycles within this many minutes into one event
DOSE_MIN = 0.3          # a CONFIRMED cycle with dose above this is "a shot"


def load():
    import psycopg2
    conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
    q = """
    SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
      user_id, ts_epoch, ts_utc, cgm_mgdl AS bg, boostv5_state AS state,
      boostv5_finaldose AS fd, delta_acceleration AS accl, iob_iob AS iob, tdd
    FROM boost_decisions WHERE boostv5_state IS NOT NULL AND cgm_mgdl IS NOT NULL
    ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
    """
    df = pd.read_sql(q, conn, params=None).sort_values(["user_id", "ts_epoch"]).reset_index(drop=True)
    conn.close()
    return df


def events_for_user(g):
    g = g.sort_values("ts_epoch").reset_index(drop=True)
    ts, bg = g.ts_epoch.values, g.bg.values
    st, fd = g.state.values, g.fd.values.astype(float)
    accl, iob = g.accl.values.astype(float), g.iob.values.astype(float)
    tdd = np.nanmedian(g.tdd.values)
    shots = [i for i in range(len(g)) if st[i] == "CONFIRMED" and np.isfinite(fd[i]) and fd[i] > DOSE_MIN]
    events = []
    i = 0
    while i < len(shots):
        a = shots[i]
        # cluster subsequent shots within CLUSTER_MIN of the first
        j = i
        total = fd[a]
        while j + 1 < len(shots) and ts[shots[j + 1]] - ts[a] <= CLUSTER_MIN * 60:
            j += 1
            total += fd[shots[j]]
        # peak bg in [a, +30min]; nadir in [a, +3h]; max forward in [a, +3h]
        def win(lo_s, hi_s, fn):
            vals = [bg[k] for k in range(a, len(g)) if lo_s <= ts[k] - ts[a] <= hi_s and np.isfinite(bg[k])]
            return fn(vals) if vals else np.nan
        peak = win(0, 30 * 60, max)
        nadir = win(0, 180 * 60, min)
        fmax = win(0, 180 * 60, max)
        events.append(dict(
            confirm_bg=bg[a], accl=accl[a], iob=iob[a], total_dosed=round(total, 2),
            peak=peak, nadir=nadir, fmax=fmax, tdd=tdd,
            decelerating=(np.isfinite(accl[a]) and accl[a] < 0),
            modest=(np.isfinite(peak) and peak < MODEST_PEAK),
            crash=(np.isfinite(nadir) and nadir < 70),
            needed=(np.isfinite(fmax) and fmax > 180),
        ))
        i = j + 1
    return events


def main():
    df = load()
    per_user = {}
    for uid, g in df.groupby("user_id"):
        per_user[uid] = events_for_user(g)

    print("=== CONFIRMED-shot outcomes per user ===")
    print(f"{'user':>5} {'shots':>6} {'crash%':>7} {'fired_decel%':>13} {'modest_peak%':>13} {'crash&decel&modest%':>20}")
    rows = []
    for uid in vc.USERS:
        ev = per_user.get(uid, [])
        if len(ev) < 10:
            continue
        n = len(ev)
        crash = sum(e["crash"] for e in ev)
        decel = sum(e["decelerating"] for e in ev)
        modest = sum(e["modest"] for e in ev)
        # crash events that ALSO fired decelerating + modest (the guard's target)
        cdm = sum(1 for e in ev if e["crash"] and e["decelerating"] and e["modest"])
        rows.append(dict(user=uid, n=n, crash=crash, decel=decel, modest=modest, cdm=cdm))
        print(f"{uid:>5} {n:>6} {100*crash/n:>6.0f}% {100*decel/n:>12.0f}% {100*modest/n:>12.0f}% {100*cdm/n:>19.0f}%")

    # ── the discriminator: among CRASH events vs NEEDED (high, no crash) events, how often decel+modest? ──
    print("\n=== discriminator: (decelerating AND modest-peak) at confirm — does it separate CRASH from NEEDED? ===")
    allev = [e for uid in vc.USERS for e in per_user.get(uid, [])]
    crash_ev = [e for e in allev if e["crash"]]
    needed_ev = [e for e in allev if e["needed"] and not e["crash"]]

    def frac(evs, pred):
        return 100 * np.mean([pred(e) for e in evs]) if evs else float("nan")

    dm = lambda e: e["decelerating"] and e["modest"]
    def med(evs, k):
        return np.nanmedian([e[k] for e in evs]) if evs else float("nan")
    print(f"  CRASH events (n={len(crash_ev)}):  decel+modest {frac(crash_ev, dm):.0f}%  "
          f"| ACTIONABLE-at-confirm: confirm_bg {med(crash_ev,'confirm_bg'):.0f}, IOB {med(crash_ev,'iob'):.1f}, "
          f"dose {med(crash_ev,'total_dosed'):.2f}U | (hindsight: peak {med(crash_ev,'peak'):.0f}, nadir {med(crash_ev,'nadir'):.0f})")
    print(f"  NEEDED events (n={len(needed_ev)}): decel+modest {frac(needed_ev, dm):.0f}%  "
          f"| ACTIONABLE-at-confirm: confirm_bg {med(needed_ev,'confirm_bg'):.0f}, IOB {med(needed_ev,'iob'):.1f}, "
          f"dose {med(needed_ev,'total_dosed'):.2f}U | (hindsight: peak {med(needed_ev,'peak'):.0f})")
    print("  (confirm_bg / IOB / dose are known AT confirm time — a usable guard; peak/nadir are hindsight.)")

    # ── priced trim guard: trim CONFIRMED dose when decel+modest ──
    print("\n=== priced trim guard (trim the CONFIRMED shot when decelerating AND modest-peak) ===")
    flagged = [e for e in allev if dm(e)]
    fl_crash = [e for e in flagged if e["crash"]]
    fl_needed = [e for e in flagged if e["needed"] and not e["crash"]]
    fl_neutral = [e for e in flagged if not e["crash"] and not e["needed"]]
    print(f"  shots the guard would flag: {len(flagged)} of {len(allev)} ({100*len(flagged)/len(allev):.0f}%)")
    print(f"    → of those: CRASH {len(fl_crash)} ({100*len(fl_crash)/max(len(flagged),1):.0f}%)  "
          f"| NEEDED-high {len(fl_needed)} ({100*len(fl_needed)/max(len(flagged),1):.0f}%)  "
          f"| neutral {len(fl_neutral)}")
    print(f"  insulin on flagged CRASH shots (the over-treatment): {sum(e['total_dosed'] for e in fl_crash):.1f}U total, "
          f"median {np.median([e['total_dosed'] for e in fl_crash]) if fl_crash else 0:.2f}U/shot")
    print(f"\n  READ: guard is worth it if flagged shots are mostly CRASH (over-treatment) not NEEDED-high "
          f"(under-treatment). crash:needed among flagged = {len(fl_crash)}:{len(fl_needed)}.")
    write_report(rows, crash_ev, needed_ev, flagged, fl_crash, fl_needed, df)


def write_report(rows, crash_ev, needed_ev, flagged, fl_crash, fl_needed, df):
    out = os.path.join(os.path.dirname(__file__), "FASTCARB_CONFIRM_REPORT.md")
    import numpy as np
    dm = lambda e: e["decelerating"] and e["modest"]
    med = lambda evs, k: float(np.nanmedian([e[k] for e in evs])) if evs else float("nan")
    L = ["# Fast-carb CONFIRMED-shot crash analysis\n",
         f"_Data: oref.boost_decisions, V6, span {str(df.ts_utc.min())[:10]}→{str(df.ts_utc.max())[:10]}. "
         "From Tim's 48h review (3 fast-carb rise-then-crash events). `fastcarb_confirm_crash.py`._\n",
         "## Confirmed: CONFIRMED shots crash a lot (per-user)\n",
         "| user | shots | crash% (nadir<70 in 3h) |\n|---|---|---|\n" +
         "".join(f"| {r['user']} | {r['n']} | {100*r['crash']/r['n']:.0f}% |\n" for r in rows) +
         "\nTim 29%, D 39% — a real over-treatment rate, not a bad day. So the 48h review generalises.\n",
         "## But my hypothesis (trim when DECELERATING + modest) does NOT generalise\n",
         f"- CRASH events (n={len(crash_ev)}): only **{100*np.mean([dm(e) for e in crash_ev]):.0f}%** fired decelerating+modest.\n",
         f"- NEEDED events (n={len(needed_ev)}): {100*np.mean([dm(e) for e in needed_ev]):.0f}%.\n",
         f"- The trim guard flags {len(flagged)} shots, crash:needed = **{len(fl_crash)}:{len(fl_needed)}** — a poor "
         "ratio and it catches only ~10% of crashes. **Do NOT build the decelerating guard** — Tim's 3 "
         "events happened to be decelerating, but most crashes are not.\n",
         "## The real discriminator is confirm-context (BG + IOB), and it's actionable\n",
         f"- CRASH shots fire at a LOWER current BG (**{med(crash_ev,'confirm_bg'):.0f}** vs needed {med(needed_ev,'confirm_bg'):.0f}) "
         f"and LOWER IOB (**{med(crash_ev,'iob'):.1f}** vs needed {med(needed_ev,'iob'):.1f}).\n",
         "- Reading: crashes come from **confirming a meal shot EAGERLY on a modest rise at a still-low BG "
         "with little IOB** — the 'meal' turns out small (crash peaks 143 vs needed 186) and self-limits, "
         "so the ~1U shot overshoots → crash to ~58. It is NOT 'late confirm on a big fast carb'; it's "
         "eager confirm before the rise proves itself.\n",
         "- BUT the separation (120 vs 137, 0.6 vs 1.2) is modest/overlapping — a hard guard would be "
         "imperfect. Needs a priced confirm_bg×IOB threshold sweep (or conditioning the SHOT SIZE on the "
         "confirm context) before any change, and it interacts with the existing confirm-gate/age-gate.\n",
         "## Caveat\nCounterfactual BG under a trimmed/delayed shot is unsimulable — this prices context, "
         "it does not prove a non-crash. There's a real tension with the early-dosing lever (dose early to "
         "catch real meals) — so any confirm-context guard must be shadow-logged + live-checked, not shipped blind.\n"]
    open(out, "w").write("\n".join(L))
    print(f"\nreport -> {out}")


if __name__ == "__main__":
    main()
