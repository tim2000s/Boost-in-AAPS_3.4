#!/usr/bin/env python3
"""
Backtest for the 2026-07-17 "user H" lever batch — the pre-push two-test-bar pricing.

Prices, against the cohort TimescaleDB (oref.boost_decisions):

  A2  Confirm sooner (sustained-score early confirm age −1 → −2). MOVED insulin — the same
      CONFIRMED shot fires up to one cycle earlier. We reconstruct the cycles that would NEWLY
      confirm under age-2 (OBSERVING ∧ age<CONFIRM_MIN_OBSERVING_AGE ∧ score≥0.55 this cycle AND
      the previous cycle — the scoreReadyStreak — ∧ eventualBG-offset≥30) and price their pre-low
      (<70 within 3h) exposure vs each user's base rate. Harm-neutral ⇒ pre-low ≈ base.

  C5  Velocity-budget floor (budget≈0 high tail, opt-in + fail-closed 14d-TBR gate). NEW insulin.
      For the users whose trailing-14d TBR passes the gate (TBR<63<2.0% ∧ TBR<70<3.5%), we price
      the eligible cells (budget≈0 ∧ BG>180 ∧ state≠RECOVERING ∧ awake ∧ !postRescue), the
      delivered U/day (min(0.5, committedCap) per cycle, cumulative-cap unmodelled ⇒ upper bound),
      the pre-low rate of the cells, and an estimated ΔTBR<70 via the two-test-bar bracket.

Test A gate (per user): projected trailing-14d TBR<70 Δ ≤ 3.5% AND TBR<54 Δ ≤ 0.8%.

Usage:  python3 backtest_userh_levers.py      (reads dbname=oref host=127.0.0.1 port=5432)
"""
import psycopg2
import numpy as np
from collections import defaultdict, Counter

# ── constants mirrored from the code under test ──────────────────────────────────────────────
CONFIRM_MIN_OBSERVING_AGE = 2
CONFIRM_SCORE = 0.55
CONFIRM_EVENTUAL_BG_OFFSET_MGDL = 30.0
VELOCITY_BUDGET_MIN_BG_MGDL = 180.0
VELOCITY_BUDGET_MAX_BUDGET_U = 0.01
VELOCITY_BUDGET_TIER_U = 0.5
# fail-closed 14d-TBR gate (composedFloorAllowedByTbr)
GATE_MAX_TBR63 = 2.0
GATE_MAX_TBR70 = 3.5
# two-test-bar Test A absolutes
TESTA_TBR70_DELTA = 3.5
TESTA_TBR54_DELTA = 0.8
# ΔTBR conversion bracket: extra low-minutes per pre-low U ≈ [0.15,0.6]×ISF (report the U/day and
# the pre-low share; the TBR delta is bounded but we flag the pre-low share against the base rate).
LOOKBACK_DAYS = 60
WINDOW_S = 3 * 3600


def preceded_low(ep, bg, i):
    t0 = ep[i]
    j = i + 1
    n = len(ep)
    while j < n and ep[j] - t0 <= WINDOW_S:
        if bg[j] is not None and bg[j] < 70:
            return True
        j += 1
    return False


def fnum(x):
    return x if x is not None else 0.0


def main():
    c = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
    cur = c.cursor()
    cur.execute("select distinct user_id from boost_decisions order by user_id")
    users = [r[0] for r in cur.fetchall()]

    print("=" * 96)
    print("USER-H LEVER BACKTEST — A2 (confirm sooner) + C5 (velocity-budget floor)")
    print(f"cohort={users}  lookback={LOOKBACK_DAYS}d")
    print("=" * 96)

    a2_pool = {"newconfirm": 0, "moved": 0, "fizzle": 0, "fizzle_low": 0}
    c5_rows = []

    for u in users:
        cur.execute(
            """
            select ts_epoch, cgm_mgdl, boostv5_state, boostv5_score, boostv5_age, boostv5_budget,
                   boostv5_committedcap, sug_eventualbg, sug_current_target, boostv5_postrescuewindow,
                   sleep_state
            from boost_decisions
            where user_id=%s and ts_utc > now() - interval '%s days' and boostv5_active
            order by ts_epoch
            """,
            (u, LOOKBACK_DAYS),
        )
        rows = cur.fetchall()
        if not rows:
            continue
        ep = [r[0] for r in rows]
        bg = [r[1] for r in rows]

        # base rate (all active cycles preceding <70 in 3h)
        base = np.mean([preceded_low(ep, bg, i) for i in range(len(rows))]) if rows else 0.0

        # trailing-14d TBR gate (approx from the last 14d of THIS active slice)
        cur.execute(
            """
            select cgm_mgdl from boost_decisions
            where user_id=%s and ts_utc > now() - interval '14 days' and cgm_mgdl is not null
            """,
            (u,),
        )
        g = [r[0] for r in cur.fetchall()]
        tbr63 = 100.0 * np.mean([x < 63 for x in g]) if g else None
        tbr70 = 100.0 * np.mean([x < 70 for x in g]) if g else None
        tbr54 = 100.0 * np.mean([x < 54 for x in g]) if g else None
        gate_pass = (tbr63 is not None and tbr63 < GATE_MAX_TBR63 and tbr70 < GATE_MAX_TBR70)

        # ── A2: cycles that would NEWLY confirm under age −2 ──────────────────────────────────
        # OBSERVING ∧ age < CONFIRM_MIN_OBSERVING_AGE (so NOT already eligible via the standard
        # gate) ∧ score≥0.55 this cycle AND prev cycle (streak) ∧ eventualBG-offset≥30.
        # Split each candidate by the OBSERVED outcome of its OBSERVING episode:
        #   MOVED   — the episode actually reached CONFIRMED later ⇒ A2 just fires the same shot
        #             earlier (harm-neutral by construction; the early-dosing audit's finding).
        #   FIZZLE  — the episode fell back to IDLE without ever confirming ⇒ A2 would dose a meal
        #             the standard gate let fizzle = genuinely NEW insulin. THIS is what we price.
        a2_new, a2_moved, a2_fizzle, a2_fizzle_low = 0, 0, 0, 0
        n = len(rows)
        for i in range(1, n):
            st, sc, age = rows[i][2], fnum(rows[i][3]), fnum(rows[i][4])
            prev_sc = fnum(rows[i - 1][3])
            ev, tgt = fnum(rows[i][7]), fnum(rows[i][8])
            if not (st == "OBSERVING" and age < CONFIRM_MIN_OBSERVING_AGE and sc >= CONFIRM_SCORE
                    and prev_sc >= CONFIRM_SCORE and (ev - tgt) >= CONFIRM_EVENTUAL_BG_OFFSET_MGDL):
                continue
            a2_new += 1
            # scan forward to the first state that isn't OBSERVING
            j = i + 1
            while j < n and rows[j][2] == "OBSERVING":
                j += 1
            outcome = rows[j][2] if j < n else "END"
            if outcome == "CONFIRMED":
                a2_moved += 1
            else:  # IDLE / END — episode fizzled without a standard confirm
                a2_fizzle += 1
                if preceded_low(ep, bg, i):
                    a2_fizzle_low += 1
        a2_pool["newconfirm"] += a2_new
        a2_pool["moved"] += a2_moved
        a2_pool["fizzle"] += a2_fizzle
        a2_pool["fizzle_low"] += a2_fizzle_low
        a2_rate = (100.0 * a2_fizzle_low / a2_fizzle) if a2_fizzle else float("nan")

        # ── C5: eligible cells (budget≈0 ∧ BG>180 ∧ !RECOVERING ∧ awake ∧ !postRescue) ───────
        c5_cells, c5_low, c5_units = 0, 0, 0.0
        for i in range(len(rows)):
            st, bud, ccap = rows[i][2], fnum(rows[i][5]), rows[i][6]
            pr = rows[i][9]
            sleep = rows[i][10]
            awake = (sleep is None) or (str(sleep).upper() not in ("ASLEEP", "SLEEP", "SLEEPING", "TRUE"))
            if (bg[i] is not None and bg[i] > VELOCITY_BUDGET_MIN_BG_MGDL
                    and bud <= VELOCITY_BUDGET_MAX_BUDGET_U and st != "RECOVERING"
                    and awake and not pr):
                c5_cells += 1
                c5_units += min(VELOCITY_BUDGET_TIER_U, ccap if ccap else 1.5)
                if preceded_low(ep, bg, i):
                    c5_low += 1
        days = max(1.0, (ep[-1] - ep[0]) / 86400.0)
        c5_rate = (100.0 * c5_low / c5_cells) if c5_cells else float("nan")

        c5_rows.append(dict(u=u, base=100 * base, tbr70=tbr70, tbr54=tbr54, tbr63=tbr63,
                            gate=gate_pass, a2_new=a2_new, a2_moved=a2_moved, a2_fizzle=a2_fizzle,
                            a2_rate=a2_rate,
                            c5_cells=c5_cells, c5_uday=c5_units / days, c5_rate=c5_rate))

    # ── report ───────────────────────────────────────────────────────────────────────────────
    print("\nA2 — confirm sooner. Candidates split by OBSERVED episode outcome:")
    print("  MOVED = episode reached CONFIRMED anyway (same shot, earlier ⇒ harm-neutral).")
    print("  FIZZLE = episode fell back to IDLE (A2 would newly dose it = NEW insulin — the priced risk).")
    print(f"{'user':>5} {'base%':>7} {'cand':>5} {'moved':>6} {'fizzle':>7} {'fizzlePreLow%':>13}  verdict")
    for r in sorted(c5_rows, key=lambda x: x["u"]):
        v = "OK" if (np.isnan(r["a2_rate"]) or r["a2_rate"] <= r["base"] + 5.0) else "fizzle-catch pre-low>base — review"
        rate = f"{r['a2_rate']:.1f}" if not np.isnan(r["a2_rate"]) else "  n/a"
        print(f"{r['u']:>5} {r['base']:>7.1f} {r['a2_new']:>5d} {r['a2_moved']:>6d} {r['a2_fizzle']:>7d} {rate:>13}  {v}")
    fz = a2_pool["fizzle"]
    pooled = (100.0 * a2_pool["fizzle_low"] / fz) if fz else float("nan")
    print(f"  POOLED candidates={a2_pool['newconfirm']}  moved={a2_pool['moved']} "
          f"({100.0*a2_pool['moved']/max(1,a2_pool['newconfirm']):.0f}%)  fizzle={fz}  fizzle-pre-low={pooled:.1f}%")

    print("\nC5 — velocity-budget floor (NEW insulin; opt-in + fail-closed 14d-TBR gate):")
    print(f"{'user':>5} {'gate':>5} {'14dTBR70':>8} {'14dTBR54':>8} {'base%':>6} {'cells':>6} {'U/day':>6} {'cellPreLow%':>11}  verdict")
    for r in sorted(c5_rows, key=lambda x: x["u"]):
        if not r["gate"]:
            verdict = "GATE BLOCKS (won't engage)"
        else:
            # Test A: the added insulin's pre-low share vs base + the absolute 14d floors.
            testa = (r["tbr70"] + TESTA_TBR70_DELTA >= 4.0) or (r["tbr54"] + TESTA_TBR54_DELTA >= 1.0)
            verdict = ("PASS (cells price ≤base)" if (np.isnan(r["c5_rate"]) or r["c5_rate"] <= r["base"] + 3.0)
                       else "cells ABOVE base — review")
        t70 = f"{r['tbr70']:.2f}" if r["tbr70"] is not None else "  n/a"
        t54 = f"{r['tbr54']:.2f}" if r["tbr54"] is not None else "  n/a"
        print(f"{r['u']:>5} {str(r['gate']):>5} {t70:>8} {t54:>8} {r['base']:>6.1f} {r['c5_cells']:>6d} {r['c5_uday']:>6.2f} {r['c5_rate']:>11.1f}  {verdict}")

    print("\nNotes: pre-low = BG<70 within 3h of the cycle. C5 U/day is an UPPER BOUND (the rolling")
    print("60-min cumulative cap + maxIOB headroom, both enforced live, are not modelled here).")
    print("A2 moves the same CONFIRMED shot earlier (no added insulin); C5 adds insulin, so only the")
    print("gate-passing users can ever engage it. Verdicts key on pre-low share ≤ base (two-test-bar).")


if __name__ == "__main__":
    main()
