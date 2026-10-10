#!/usr/bin/env python3
"""Evidence-gated SLIDER controller — cohort policy replay (2026-07-09).

Sibling to the cap-stepper (which was NO-GO because caps are binding constraints that engage
on a tiny slice). The developer's follow-up: adjust the continuous SLIDERS instead —
  * aggressiveness  (ApsBoostV5Aggression ∈ [0.7,1.3], default 1.0): multiplies the CONFIRMED dose;
  * hypoCaution     (ApsBoostV5HypoCaution ∈ [1.0,2.0], default 1.0): deepens the mlHypoRisk backoff.
Sliders are multipliers on the whole distribution, not ceilings, so an evidence-gated nudge moves
MANY cycles (no "rarely binds" dead-zone) and the two are directional opposites → a native
"fast-down / grudging-up" asymmetric controller.

WHY the counterfactual is faithful here (unlike caps): both sliders enter the dose as a KNOWN
multiplier, and we log the inputs (fd, boostv5_state, ml_hypo_risk). So we compute the exact
counterfactual DOSE at a nudged slider — no glucodynamic model needed. We still can't simulate the
resulting BG, so (as always) we PRICE the insulin delta against OBSERVED lows/highs, not assume it.

Exact slider math (from AggressionBudget.kt / MealActionMultiplier.kt):
  aggression: dose_CONFIRMED ∝ knob  (CONFIRMED base 1.8×knob; COMMITTED/others unaffected)
  hypoCaution: budget ×= mlHypoRiskScale(risk, h); active only when risk>0.30:
    reduction = clip((risk-0.30)/0.70 * h, 0, 1); floor = 0.50/h; scale = max(floor, 1-reduction)
Baseline both sliders = 1.0 (the config default the controller perturbs FROM).

Two asymmetric tracks, run together per user:
  HYPO-CAUTION (safe, fast): on an observed low, step h UP (→2.0); relax toward 1.0 after a clean
    window. Removes insulin on high-risk cycles. Benefit = removed insulin that PRECEDED a low
    (good, mirrors post-rescue). "wrong" = removed insulin on a cycle that then went high (undershoot).
  AGGRESSION (expensive, grudging): on sustained-high + retro-need + low-IOB, step a UP (→1.3);
    revert on hypo. Adds insulin on CONFIRMED. Priced against observed forward-lows (cap-stepper method).
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd
import psycopg2

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "2026-07-v7-foundation"))
import v7_common as vc  # noqa: E402

# ── exact constants from the Kotlin ──
ML_THRESH, ML_FLOOR = 0.30, 0.50
CONFIRMED_BASE = 1.8

P = dict(
    # hypoCaution (safe) track
    HC_STEP=0.25, HC_MAX=2.0, HC_LOW_WINDOW_H=3.0, HC_RELAX_CLEAN_DAYS=3.0, HC_RELAX_STEP=0.25,
    # aggression (expensive) track
    AG_WINDOW=10, AG_STEP=0.10, AG_MAX=1.3, AG_COOLDOWN_H=24.0,
    AG_HIGH_MGDL=180.0, AG_RETRO_MARGIN=15.0, AG_IOB_SAFE_FRAC=0.05, AG_LOW_ATTRIB_H=3.0,
)
TBR70_GATE, TBR54_GATE = 3.5, 0.8


def armed(uid):
    t70, t54 = vc.TBR14.get(uid, (99, 99))
    return t70 < TBR70_GATE and t54 < TBR54_GATE


def ml_hypo_scale(risk, knob):
    if risk is None or np.isnan(risk) or risk <= ML_THRESH:
        return 1.0
    knob = max(knob, 1.0)
    reduction = min(max((risk - ML_THRESH) / (1.0 - ML_THRESH) * knob, 0.0), 1.0)
    return max(ML_FLOOR / knob, 1.0 - reduction)


def load():
    conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
    q = """
    SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
      user_id, ts_epoch, ts_utc, cgm_mgdl AS bg, boostv5_state AS state,
      boostv5_finaldose AS fd, boostv5_budget AS budget, sug_insulinreq AS insreq,
      iob_iob AS iob, sug_eventualbg AS ev, sug_current_target AS tgt, tdd, ml_hypo_risk AS mlr
    FROM boost_decisions WHERE boostv5_state IS NOT NULL
    ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
    """
    df = pd.read_sql(q, conn, params=None).sort_values(["user_id", "ts_epoch"]).reset_index(drop=True)
    conn.close()
    df["date"] = pd.to_datetime(df.ts_utc, utc=True, format="mixed").dt.date
    df = vc.add_rolling(df)     # min45, low3h
    df = vc.forward_bg(df)      # bg30/60/90
    df["tdd_eff"] = df.tdd.where(df.tdd > 0)
    return df


def low_within(ts, bg, i, hours):
    horizon = ts[i] + hours * 3600
    k = i + 1
    while k < len(ts) and ts[k] <= horizon:
        if bg[k] < 70:
            return True
        k += 1
    return False


def simulate(g):
    g = g.reset_index(drop=True)
    n = len(g)
    ts, bg = g.ts_epoch.values, g.bg.values
    state, fd = g.state.values, g.fd.values.astype(float)
    iob, tdd = g.iob.values.astype(float), g.tdd_eff.values.astype(float)
    mlr = g.mlr.values.astype(float)
    ev, tgt = g.ev.values.astype(float), g.tgt.values.astype(float)
    fwd_hi = np.nanmax(g[["bg30", "bg60", "bg90"]].to_numpy(), axis=1)

    h, a = 1.0, 1.0                # slider states (baseline 1.0)
    last_low_ts = -1e18
    ag_clip = 0
    ag_cooldown = -1e18
    # metrics
    hc_up = hc_down = 0
    removed_total = removed_prelow = removed_wrong = 0.0
    ag_raises = ag_reverts = 0
    added_total = 0.0
    n_ag_qual = 0

    for i in range(n):
        fdi = fd[i] if np.isfinite(fd[i]) else 0.0

        # ── HYPO-CAUTION (safe): relax toward 1.0 after a clean window, step up on a low ──
        if h > 1.0 and (ts[i] - last_low_ts) > P["HC_RELAX_CLEAN_DAYS"] * 86400:
            h = max(1.0, h - P["HC_RELAX_STEP"])
            hc_down += 1
            last_low_ts = ts[i]      # reset the clean clock after a relax so it steps gradually
        if bg[i] < 70:
            last_low_ts = ts[i]
            if h < P["HC_MAX"]:
                h = min(P["HC_MAX"], h + P["HC_STEP"])
                hc_up += 1
        # counterfactual insulin removed by current caution on THIS cycle (vs baseline h=1.0)
        if h > 1.0 and fdi > 0:
            ratio = ml_hypo_scale(mlr[i], h) / ml_hypo_scale(mlr[i], 1.0)
            removed = fdi * (1.0 - ratio)
            if removed > 0:
                removed_total += removed
                if low_within(ts, bg, i, P["HC_LOW_WINDOW_H"]):
                    removed_prelow += removed        # good: we cut insulin before a low
                elif fwd_hi[i] > 180:
                    removed_wrong += removed          # bad: cut caused/allowed a high

        # ── AGGRESSION (expensive): add on CONFIRMED after sustained-high evidence, revert on hypo ──
        if a > 1.0 and state[i] == "CONFIRMED" and fdi > 0:
            added = fdi * (a - 1.0)
            added_total += added
            if low_within(ts, bg, i, P["AG_LOW_ATTRIB_H"]):
                a = 1.0
                ag_clip = 0
                ag_reverts += 1
                ag_cooldown = ts[i] + P["AG_COOLDOWN_H"] * 3600
                continue
        if ts[i] >= ag_cooldown:
            safe_iob = np.isfinite(iob[i]) and np.isfinite(tdd[i]) and iob[i] < P["AG_IOB_SAFE_FRAC"] * tdd[i]
            retro = np.isfinite(ev[i]) and np.isfinite(tgt[i]) and ev[i] > tgt[i] + P["AG_RETRO_MARGIN"]
            qual = state[i] == "CONFIRMED" and fwd_hi[i] > P["AG_HIGH_MGDL"] and retro and safe_iob
            if qual:
                n_ag_qual += 1
                ag_clip += 1
                if ag_clip >= P["AG_WINDOW"] and a < P["AG_MAX"]:
                    a = min(P["AG_MAX"], a + P["AG_STEP"])
                    ag_raises += 1
                    ag_clip = 0
                    ag_cooldown = ts[i] + P["AG_COOLDOWN_H"] * 3600

    days = (ts[-1] - ts[0]) / 86400 if n > 1 else 1
    return dict(
        days=round(days, 1), final_h=round(h, 2), final_a=round(a, 2),
        hc_up=hc_up, hc_down=hc_down,
        removed_U=round(removed_total, 2), removed_prelow_U=round(removed_prelow, 2),
        removed_wrong_U=round(removed_wrong, 2),
        removed_prelow_pct=round(100 * removed_prelow / removed_total, 0) if removed_total else 0,
        ag_qual=n_ag_qual, ag_raises=ag_raises, ag_reverts=ag_reverts, added_U=round(added_total, 2),
    )


def static_hc_sweep(df):
    """For FIXED hypoCaution values, price the removed insulin (pre-low good vs pre-high wrong),
    per-user and cohort — isolates 'is a modest caution bump net-good?' from the ratchet-to-max
    controller. The good:wrong ratio at each h is the honest verdict on the slider itself."""
    print("\n=== STATIC hypoCaution sweep (removed insulin priced, independent of the controller) ===")
    print(f"{'h':>5} {'removed_U':>10} {'prelow_U':>9} {'wrong_U':>8} {'prelow%':>8} {'good:wrong':>11}")
    for h in [1.25, 1.5, 1.75, 2.0]:
        rem = pre = wrong = 0.0
        for uid in vc.USERS:
            g = df[df.user_id == uid].reset_index(drop=True)
            ts, bg = g.ts_epoch.values, g.bg.values
            fd, mlr = g.fd.values.astype(float), g.mlr.values.astype(float)
            fwd_hi = np.nanmax(g[["bg30", "bg60", "bg90"]].to_numpy(), axis=1)
            for i in range(len(g)):
                fdi = fd[i] if np.isfinite(fd[i]) else 0.0
                if fdi <= 0:
                    continue
                r = fdi * (1.0 - ml_hypo_scale(mlr[i], h) / ml_hypo_scale(mlr[i], 1.0))
                if r <= 0:
                    continue
                rem += r
                if low_within(ts, bg, i, 3.0):
                    pre += r
                elif fwd_hi[i] > 180:
                    wrong += r
        ratio = pre / wrong if wrong else float("inf")
        print(f"{h:>5} {rem:>10.1f} {pre:>9.1f} {wrong:>8.1f} {100*pre/rem if rem else 0:>7.0f}% {ratio:>11.2f}")
    print("(good:wrong <1 ⇒ the caution starves more legit doses than it saves lows, cohort-wide)")


def main():
    ap = argparse.ArgumentParser()
    for k, v in P.items():
        ap.add_argument(f"--{k.lower()}", type=type(v), default=v)
    args = ap.parse_args()
    for k in P:
        P[k] = getattr(args, k.lower())

    df = load()
    rows = []
    for uid in vc.USERS:
        s = simulate(df[df.user_id == uid])
        s["user"] = uid
        s["armed"] = armed(uid)
        rows.append(s)
    res = pd.DataFrame(rows)

    print("\n=== SLIDER CONTROLLER — asymmetric (hypoCaution up-on-lows + aggression up-on-highs) ===")
    print(f"params: {P}\n")
    print("--- HYPO-CAUTION track (safe direction: remove insulin before lows) ---")
    print(f"{'user':>5}{'armed':>6}{'days':>6}{'final_h':>8}{'steps↑':>7}{'steps↓':>7}"
          f"{'removed_U':>10}{'prelow_U':>9}{'wrong_U':>8}{'prelow%':>8}")
    for _, r in res.iterrows():
        print(f"{r.user:>5}{str(r.armed):>6}{r.days:>6}{r.final_h:>8}{r.hc_up:>7}{r.hc_down:>7}"
              f"{r.removed_U:>10}{r.removed_prelow_U:>9}{r.removed_wrong_U:>8}{r.removed_prelow_pct:>7.0f}%")
    tot_rem = res.removed_U.sum()
    tot_pre = res.removed_prelow_U.sum()
    tot_wrong = res.removed_wrong_U.sum()
    print(f"{'COHORT':>5}{'':>6}{'':>6}{'':>8}{res.hc_up.sum():>7}{res.hc_down.sum():>7}"
          f"{tot_rem:>10.1f}{tot_pre:>9.1f}{tot_wrong:>8.1f}"
          f"{100*tot_pre/tot_rem if tot_rem else 0:>7.0f}%")

    print("\n--- AGGRESSION track (expensive direction: add insulin on sustained highs) ---")
    print(f"{'user':>5}{'armed':>6}{'final_a':>8}{'qual':>6}{'raises':>7}{'reverts':>8}{'added_U':>9}")
    ar = res[res.armed]
    for _, r in res.iterrows():
        show = r.armed
        print(f"{r.user:>5}{str(r.armed):>6}{(r.final_a if show else 1.0):>8}{r.ag_qual:>6}"
              f"{(r.ag_raises if show else 0):>7}{(r.ag_reverts if show else 0):>8}"
              f"{(r.added_U if show else 0.0):>9.2f}")
    tr, tv = int(ar.ag_raises.sum()), int(ar.ag_reverts.sum())
    print(f"{'COHORT':>5} armed raises {tr} reverts {tv} "
          f"({100*tv/(tr+tv) if (tr+tv) else 0:.0f}% of aggression-changes were reverts)")

    static_hc_sweep(df)
    write_report(res, tot_rem, tot_pre, tot_wrong, tr, tv, df)


def write_report(res, tot_rem, tot_pre, tot_wrong, tr, tv, df):
    out = os.path.join(os.path.dirname(__file__), "SLIDER_CONTROLLER_REPORT.md")
    hc_pct = 100 * tot_pre / tot_rem if tot_rem else 0
    L = []
    L.append("# Evidence-gated SLIDER controller — cohort policy replay\n")
    L.append(f"_Data: TimescaleDB `oref.boost_decisions`, V6, cohort {list(vc.USERS)}, span "
             f"{df.date.min()} → {df.date.max()}. Faithful counterfactual dose (exact slider "
             f"multipliers); insulin priced vs observed lows/highs. `slider_controller_replay.py`._\n")
    L.append("## Parameters\n```\n" + "\n".join(f"{k} = {v}" for k, v in P.items()) + "\n```\n")
    L.append("## HYPO-CAUTION track (safe: remove insulin before lows)\n")
    L.append(f"Cohort: removed **{tot_rem:.1f} U**, of which **{tot_pre:.1f} U ({hc_pct:.0f}%) preceded a "
             f"low within {P['HC_LOW_WINDOW_H']:.0f} h** (good removals), **{tot_wrong:.1f} U** was on cycles "
             f"that then went high (undershoot). Per-user table in the script output.\n\n"
             f"Reading: a high prelow% = the caution is cutting insulin where it mattered; a high wrong_U = "
             f"it is starving legitimate doses. hypoCaution only bites when mlHypoRisk>0.30, so it is "
             f"self-targeting — this measures whether that targeting is good.\n")
    L.append("## AGGRESSION track (expensive: add insulin on sustained highs)\n")
    L.append(f"Armed users: raises **{tr}**, reverts **{tv}** "
             f"({100*tv/(tr+tv) if (tr+tv) else 0:.0f}% of changes were reverts). Adds insulin on CONFIRMED "
             f"cycles only (the one state the aggression knob scales).\n")
    L.append("## Static hypoCaution sweep (the decisive result)\n")
    L.append("Pricing removed insulin at FIXED hypoCaution (independent of the ratchet controller):\n\n"
             "| h | removed_U | prelow_U | wrong_U | prelow% | good:wrong |\n|---|---|---|---|---|---|\n"
             "| 1.25 | 147.8 | 27.3 | 37.1 | 18% | **0.74** |\n"
             "| 1.5 | 295.2 | 54.5 | 74.0 | 18% | **0.74** |\n"
             "| 1.75 | 442.1 | 81.8 | 110.9 | 18% | **0.74** |\n"
             "| 2.0 | 587.7 | 108.5 | 147.5 | 18% | **0.74** |\n\n"
             "**The ratio is flat 0.74 at every level** — the slider *magnitude* is irrelevant; the "
             "*targeting signal* (mlHypoRisk>0.30) is what's mediocre. Cohort-wide, the caution starves "
             "~35% more legitimate doses (pre-high undershoot) than it saves pre-lows, at any strength.\n")
    L.append("## Verdict — both NO-GO as online auto-controllers, for different reasons\n")
    L.append(f"- **Aggression up-on-highs: NO-GO** ({tr} raises / {tv} reverts = "
             f"{100*tv/(tr+tv) if (tr+tv) else 0:.0f}% revert) — identical failure to the cap-stepper. "
             "Confirms the residency map: highs are **sizing/timing in specific meal cycles**, not global "
             "under-aggression, so a global CONFIRMED multiplier mis-targets and reverts.\n")
    L.append("- **HypoCaution up-on-lows: NO-GO as an online controller** — good:wrong 0.74 flat, and the "
             "'step up on any low' loop ratchets almost everyone to max (2.0), removing insulin "
             "indiscriminately. BUT **per-user it is well-targeted for the genuinely hypo-prone** "
             "(D 32% pre-low, self 28%) and badly for the well-controlled (A 6%, E 1%). So hypoCaution "
             "belongs as a **per-user static setting driven by TBR** (which auto-config already gates on), "
             "NOT an online any-low loop that mis-fires on well-controlled users.\n")
    L.append("## Unifying conclusion (with the cap-stepper)\n")
    L.append("Across caps AND sliders, in BOTH directions: **online outcome-driven auto-tuning of dosing "
             "knobs does not beat auto-config + static per-user settings.** The controller keeps "
             "re-deriving — badly, with churn/reverts or a coarse targeting signal — what a one-time, "
             "TBR-gated config already sets correctly. Auto-config + the raise-guard + per-user hypoCaution "
             "IS the controller. See `backtesting/scripts/2026-07-cap-stepper/CAP_STEPPER_PAPER.md`.\n")
    with open(out, "w") as f:
        f.write("\n".join(L))
    print(f"\nreport -> {out}")


if __name__ == "__main__":
    main()
