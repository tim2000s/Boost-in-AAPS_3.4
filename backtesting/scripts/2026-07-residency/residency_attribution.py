#!/usr/bin/env python3
"""Residency attribution — "where does the TIR loss actually come from?" (2026-07-08).

Segments each user's timeline into HIGH (>180) and LOW (<70) episodes, attributes each
episode's ONSET to a proximate mechanism from the telemetry, and sums the minutes by
cause. The onset owns the whole episode's minutes (the actionable framing: fix the onset
mechanism and the episode doesn't happen).

Purely ATTRIBUTIVE over observed data — no counterfactual BG is claimed. The companion
`residency_ml.py` adds an LGBM avoidable/unavoidable split.

Data: TimescaleDB oref.boost_decisions, V6 (boostv5_*) cycles, self + A-H.
Minutes: CGM cadence = one reading per ~5 min, so episode minutes = n_cycles * 5.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "2026-07-v7-foundation"))
import v7_common as vc  # noqa: E402

HIGH, LOW = 180.0, 70.0
MIN_PER_CYCLE = 5.0
PRE_MIN = 45          # onset look-back window (minutes)
MERGE_GAP_MIN = 20    # bridge episodes separated by < this (brief dips) into one
RISE_MGDL5 = 8.0      # delta5 that counts as a meal-rate rise
BRAKE_BUDGET = 0.10   # budget below this on a rising high = suppression
ACT_STEPS = 400       # steps/hr in the pre-window = activity-driven
IOB_LO_FRAC = 0.05    # iob < this * TDD  -> "no insulin on board" context
IOB_HI_FRAC = 0.12    # iob > this * TDD  -> "insulin stacked"
MEAL_STATES = ("CONFIRMED", "COMMITTED")

HIGH_CAUSES = ["LATE_CONFIRM", "BRAKE_SUPPRESS", "RECOVERING_HOLD", "CAP_CLIP",
               "UNDERSIZED", "UNCOVERABLE", "NO_MEAL_HIGH"]
LOW_CAUSES = ["ACTIVITY", "STACKING", "RESCUE_OVERSHOOT", "BASAL_DRIFT"]


def load_prep():
    df = vc.load()
    df = vc.add_rolling(df)      # min45, low3h
    # rolling meal-state insulin over the prior 2h (stacking signal), per user, O(n)
    recent = np.zeros(len(df))
    for _, g in df.groupby("user_id", sort=False):
        ts = g.ts_epoch.values
        fdv = np.where(np.isin(g.state.values, MEAL_STATES), np.nan_to_num(g.fd.values), 0.0)
        idx = g.index.values
        j = 0
        run = 0.0
        for i in range(len(g)):
            run += fdv[i]
            while ts[i] - ts[j] > 7200:
                run -= fdv[j]
                j += 1
            recent[idx[i]] = run - fdv[i]      # insulin already onboard BEFORE this cycle
    df["recent_meal_iob"] = recent
    df["tdd_eff"] = df["tdd"].where(df["tdd"] > 0)
    return df


def segment(hot, ts):
    """Episodes of `hot`==True, merging two runs whose time gap < MERGE_GAP_MIN (brief dips).
    Returns [(a,b)] positional bounds. Minutes are counted from the hot cycles only, elsewhere."""
    runs = []
    i, n = 0, len(hot)
    while i < n:
        if hot[i]:
            a = i
            while i + 1 < n and hot[i + 1]:
                i += 1
            runs.append([a, i])
        i += 1
    merged = []
    for a, b in runs:
        if merged and ts[a] - ts[merged[-1][1]] <= MERGE_GAP_MIN * 60:
            merged[-1][1] = b          # bridge across a brief dip
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def pre_slice(g, onset, cols):
    ts = g.ts_epoch.values
    lo = ts[onset] - PRE_MIN * 60
    a = onset
    while a > 0 and ts[a - 1] >= lo:
        a -= 1
    return g.iloc[a:onset + 1]


def classify_high(g, a, b):
    w = pre_slice(g, a, None)
    tdd = np.nanmedian(w.tdd_eff.values) or np.nan
    rose = np.nanmax(w.delta5.values) > RISE_MGDL5 if len(w) else False
    meal = w.state.isin(MEAL_STATES)
    dosed = bool((meal & (w.fd.fillna(0) > 0)).any())
    dose_fd = float(w.fd.where(meal).fillna(0).sum())
    need = float(np.nanmax(w.insreq.values)) if np.isfinite(w.insreq.values).any() else 0.0
    clipped = bool((meal & (w.fd.fillna(0) >= 0.98 * w["cap"].fillna(1e9))).any())
    rising_hi = (w.bg > 160) & (w.delta5 > 0)
    braked = bool((rising_hi & (w.budget.fillna(1) < BRAKE_BUDGET)).any())
    recovering = bool((w.state == "RECOVERING").any())
    iob0 = float(g.iob.values[a]) if np.isfinite(g.iob.values[a]) else 0.0
    iob_lo = np.isfinite(tdd) and iob0 < IOB_LO_FRAC * tdd

    if not rose and not dosed and iob_lo:
        return "NO_MEAL_HIGH"
    if rose and not dosed:
        return "LATE_CONFIRM"
    if braked:
        return "BRAKE_SUPPRESS"
    if recovering and rose:
        return "RECOVERING_HOLD"
    if clipped:
        return "CAP_CLIP"
    if dosed and need > 0 and dose_fd < 0.8 * need:
        return "UNDERSIZED"
    if dosed:
        return "UNCOVERABLE"
    return "NO_MEAL_HIGH"


def classify_low(g, a, b):
    w = pre_slice(g, a, None)
    tdd = np.nanmedian(w.tdd_eff.values) or np.nan
    steps = np.nanmax(w.steps_60m.values) if np.isfinite(w.steps_60m.values).any() else 0.0
    iob0 = float(g.iob.values[a]) if np.isfinite(g.iob.values[a]) else 0.0
    recent = float(g.recent_meal_iob.values[a])
    prior_low = bool(g.low3h.values[a]) if "low3h" in g else False
    iob_hi = np.isfinite(tdd) and iob0 > IOB_HI_FRAC * tdd

    if steps > ACT_STEPS:
        return "ACTIVITY"
    if recent > 0.05 or iob_hi:
        return "STACKING"
    if prior_low:
        return "RESCUE_OVERSHOOT"
    return "BASAL_DRIFT"


def per_user(df, uid):
    g = df[df.user_id == uid].reset_index(drop=True)
    ts = g.ts_epoch.values
    hi_mask = (g.bg > HIGH).values
    lo_mask = (g.bg < LOW).values
    hi_eps = segment(hi_mask, ts)
    lo_eps = segment(lo_mask, ts)
    rec = {"user": uid, "high": {c: 0.0 for c in HIGH_CAUSES},
           "low": {c: 0.0 for c in LOW_CAUSES}, "episodes": []}
    total_min = len(g) * MIN_PER_CYCLE
    for a, b in hi_eps:
        mins = int(hi_mask[a:b + 1].sum()) * MIN_PER_CYCLE   # only the cycles actually >180
        c = classify_high(g, a, b)
        rec["high"][c] += mins
        rec["episodes"].append(dict(user=uid, kind="high", cause=c, minutes=mins,
                                    onset_ts=int(ts[a]), onset_bg=float(g.bg.values[a])))
    for a, b in lo_eps:
        mins = int(lo_mask[a:b + 1].sum()) * MIN_PER_CYCLE
        c = classify_low(g, a, b)
        rec["low"][c] += mins
        rec["episodes"].append(dict(user=uid, kind="low", cause=c, minutes=mins,
                                    onset_ts=int(ts[a]), onset_bg=float(g.bg.values[a])))
    rec["total_min"] = total_min
    rec["high_min"] = sum(rec["high"].values())
    rec["low_min"] = sum(rec["low"].values())
    return rec


def main():
    df = load_prep()
    recs = Parallel(n_jobs=-1)(delayed(per_user)(df, u) for u in vc.USERS)

    # ── per-user high-cause table (% of that user's high-time) ──
    print("\n=== HIGH-TIME attribution (% of each user's >180 minutes) ===")
    hdr = f"{'user':>5} {'high%':>6} " + " ".join(f"{c[:9]:>9}" for c in HIGH_CAUSES)
    print(hdr)
    for r in recs:
        hm = r["high_min"] or 1
        row = f"{r['user']:>5} {100*r['high_min']/r['total_min']:>5.1f}% " + \
            " ".join(f"{100*r['high'][c]/hm:>8.0f}%" for c in HIGH_CAUSES)
        print(row)
    # cohort totals — BOTH pooled (minute-weighted) AND per-user median (the honest pair; the
    # two can disagree / re-rank when a few users dominate the minute-pool — 2026-07-10 audit).
    tot = {c: sum(r["high"][c] for r in recs) for c in HIGH_CAUSES}
    thm = sum(tot.values()) or 1
    print(f"{'POOL':>5} {'':>6} " + " ".join(f"{100*tot[c]/thm:>8.0f}%" for c in HIGH_CAUSES))
    med_h = {c: float(np.median([100 * r["high"][c] / (r["high_min"] or 1) for r in recs if r["high_min"] > 0])) for c in HIGH_CAUSES}
    print(f"{'MEDN':>5} {'':>6} " + " ".join(f"{med_h[c]:>8.0f}%" for c in HIGH_CAUSES))

    print("\n=== LOW-TIME attribution (% of each user's <70 minutes) ===")
    print(f"{'user':>5} {'low%':>6} " + " ".join(f"{c[:13]:>15}" for c in LOW_CAUSES))
    for r in recs:
        lm = r["low_min"] or 1
        print(f"{r['user']:>5} {100*r['low_min']/r['total_min']:>5.1f}% " +
              " ".join(f"{100*r['low'][c]/lm:>14.0f}%" for c in LOW_CAUSES))
    lot = {c: sum(r["low"][c] for r in recs) for c in LOW_CAUSES}
    tlm = sum(lot.values()) or 1
    print(f"{'POOL':>5} {'':>6} " + " ".join(f"{100*lot[c]/tlm:>14.0f}%" for c in LOW_CAUSES))
    med_l = {c: float(np.median([100 * r["low"][c] / (r["low_min"] or 1) for r in recs if r["low_min"] > 0])) for c in LOW_CAUSES}
    print(f"{'MEDN':>5} {'':>6} " + " ".join(f"{med_l[c]:>14.0f}%" for c in LOW_CAUSES))
    print("  (POOL = minute-weighted pooled; MEDN = per-user median. They can re-rank — see the "
          "2026-07-10 audit note in RESIDENCY_REPORT.md; low-time activity/rescue flips between them.)")

    # dump episodes + summary for the ML step and the chart
    out = os.path.join(os.path.dirname(__file__), "residency_episodes.json")
    eps = [e for r in recs for e in r["episodes"]]
    summary = dict(high_cohort=tot, low_cohort=lot,
                   per_user=[{k: r[k] for k in ("user", "high", "low", "high_min",
                                                "low_min", "total_min")} for r in recs])
    with open(out, "w") as f:
        json.dump(dict(summary=summary, episodes=eps), f)
    print(f"\n{len(eps)} episodes -> {out}")


if __name__ == "__main__":
    main()
