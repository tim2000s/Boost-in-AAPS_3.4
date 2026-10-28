#!/usr/bin/env python3
"""
TING planner — offline characterisation on the cohort (2026-07-18).

Mirrors plugins/aps/.../openAPSBoostTing/TingPlanner.kt and overlays it on the REAL per-cycle
trajectories the cohort visited under V6 (from oref.boost_decisions). A dosing POLICY cannot be
validated counterfactually — no glucodynamic simulator (the identification constraint) — so this
does NOT claim a TING gain. It answers only the two questions data can answer:
  (1) is the planner SMOOTHER than what was actually delivered? (the whole thesis: TING = variance)
  (2) does it RESPECT THE FLOOR? (does its added insulin land ahead of lows more than the base rate?)

The planner's own previous would-dose is carried forward as lastDose (self-consistent smoothness),
but the STATES (bg, forecast, minGuard, iob, isf) are the historical ones V6 produced. This is a
shadow overlay, not a closed-loop simulation.

Usage: python3 ting_planner_backtest.py
"""
import psycopg2, numpy as np
from collections import defaultdict

# ── constants mirrored from TingPlanner.kt ──────────────────────────────────────────────────────
TING_AIM = 112.0
TING_GAIN = 0.5
TING_HORIZON_ACTIVITY = 0.35
TING_MAX_STEP_UP_U = 0.20
TING_FLOOR_MARGIN = 8.0
THRESH = 80.0
ROUND = 0.05


def ting_plan(bg, forecast, minguard, isf, iob, maxiob, last):
    isf = isf if isf and isf > 1 else 40.0
    perU = isf * TING_HORIZON_ACTIVITY
    if minguard is None or minguard <= THRESH:
        return 0.0
    if forecast is None or forecast <= TING_AIM:
        return 0.0
    gap = forecast - TING_AIM
    dose = min(TING_GAIN * gap / perU, last + TING_MAX_STEP_UP_U)           # nudge + rate-limit
    floor_cap = max(0.0, (minguard - (THRESH + TING_FLOOR_MARGIN)) / perU)  # floor clip
    dose = min(dose, floor_cap)
    dose = min(dose, max(0.0, maxiob - (iob or 0.0)))                       # maxIOB
    dose = np.floor(dose / ROUND + 1e-9) * ROUND
    return max(0.0, dose)


def f(x):
    return x if x is not None else 0.0


def main():
    c = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = c.cursor()
    users = ['tim', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
    print("TING planner shadow overlay — smoothness + floor-respect (60d, active cycles)\n")
    print(f"{'tag':>4} {'cyc':>6}  {'V6 U/d':>7} {'TING U/d':>8}  {'V6 jerk':>8} {'TINGjerk':>8} {'smoother?':>9}  "
          f"{'base<70':>7} {'TINGadd<70':>10}  verdict")
    for u in users:
        cur.execute("""select ts_epoch, cgm_mgdl, sug_eventualbg, reason_minguardbg, isf_mgdl_for_carbs,
                              iob_iob, boostv5_finaldose, v1_units
                       from boost_decisions
                       where user_id=%s and ts_utc > now() - interval '60 days' and boostv5_active
                       order by ts_epoch""", (u,))
        rows = cur.fetchall()
        if len(rows) < 500:
            print(f"{u:>4}  (insufficient)"); continue
        ep = [r[0] for r in rows]; bg = [r[1] for r in rows]
        maxiob = 12.0
        ting, v6, last = [], [], 0.0
        for r in rows:
            _, g, fc, mg, isf, iob, v6dose, v1 = r
            d = ting_plan(g, fc, mg, isf, iob, maxiob, last)
            ting.append(d); last = d
            v6.append(f(v6dose))
        ting = np.array(ting); v6 = np.array(v6)
        days = max(1.0, (ep[-1] - ep[0]) / 86400.0)
        # smoothness = std of dose-to-dose change (jerk); lower = smoother
        jerk_t = np.std(np.diff(ting)); jerk_v = np.std(np.diff(v6))
        # floor respect: cycles where TING adds MORE than V6 — do they precede <70 in 3h?
        add_idx = [i for i in range(len(rows)) if ting[i] > v6[i] + 1e-6]

        def preceded_low(i):
            t0 = ep[i]; j = i + 1
            while j < len(rows) and ep[j] - t0 <= 3 * 3600:
                if bg[j] is not None and bg[j] < 70:
                    return True
                j += 1
            return False
        base = np.mean([preceded_low(i) for i in range(len(rows))])
        add_low = np.mean([preceded_low(i) for i in add_idx]) if add_idx else float('nan')
        smoother = jerk_t < jerk_v
        floor_ok = np.isnan(add_low) or add_low <= base + 0.03
        verdict = ("SMOOTHER + floor-ok" if smoother and floor_ok else
                   "SMOOTHER, floor-review" if smoother else "not smoother")
        al = f"{100*add_low:.1f}" if not np.isnan(add_low) else " n/a"
        print(f"{u:>4} {len(rows):>6}  {v6.sum()/days:7.1f} {ting.sum()/days:8.1f}  {jerk_v:8.3f} {jerk_t:8.3f} "
              f"{str(smoother):>9}  {100*base:6.1f}% {al:>9}%  {verdict}")
    print("\nNOTE: shadow overlay on V6's real trajectories — characterises PROPOSALS, not a")
    print("counterfactual outcome. 'jerk' = std of dose-to-dose change (lower = smoother = the TING")
    print("lever). floor-ok = TING's added-insulin cycles don't precede <70 above base+3pp.")
    print("If TING U/day >> V6 or floor-review trips, v0's point-forecast needs the risk-sensitive")
    print("(CVaR) forecast before it earns live shadow — that is the next brick, honestly.")


if __name__ == "__main__":
    main()
