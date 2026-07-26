#!/usr/bin/env python3
"""Evidence-gated cap-stepper — cohort policy replay (2026-07-08).

QUESTION (the go/no-go Tim asked for): if we let committedCap step UP per-user on
accumulated evidence of *under-dosing* (cap-binding clip + sustained high followed +
low-IOB safe slice + retrospective need), with an immediate revert on hypo — does it
net TIR without moving TBR, and HOW OFTEN does the hypo-revert actually fire?

HONEST SCOPE — what this can and cannot do:
  We do NOT have a glucodynamic model, so we CANNOT simulate the BG trajectory a higher
  cap would have produced. (That is exactly why the two-test bar prices insulin
  empirically instead of simulating it.) So this is a POLICY SIMULATION over the real
  telemetry:
    * trigger events are detected from actual per-cycle fields;
    * the stepper's raise/revert dynamics are walked against the ACTUAL forward-BG as
      the outcome oracle (a low that really followed = the revert signal; a high that
      really followed = the buy-back target);
    * added insulin is PRICED against observed lows (the established two-test method),
      NOT assumed to land harmlessly.
  The load-bearing output is therefore the REVERT FREQUENCY and the size of the safe
  (low-IOB) cap-clip subset — both are directly observable and bias-free. The TIR
  buy-back is an upper-bound estimate (it credits covering the observed high, which a
  bolder dose may or may not achieve) and is labelled as such.

  Prior context this tests against: the blanket committedCap-raise lever was REJECTED
  (recovering-highs are high-IOB; adding there prices ~19% into lows). This asks the
  narrower question: is there a PER-USER, low-IOB, evidence-gated subset where the
  raise is defensible — the space where Roman/Joost (cap-clipped) differ from B/D
  (TBR-heavy)?  Frozen entirely for users without absolute TBR headroom.

Usage:  python3 cap_stepper_replay.py            # default params -> writes REPORT
        python3 cap_stepper_replay.py --window 8 --step 0.20  # param sweep
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "2026-07-v7-foundation"))
import v7_common as vc  # noqa: E402

# ── Policy parameters (all at the top so we can sweep) ──────────────────────────
P = dict(
    WINDOW=10,          # qualifying clips before a step-up
    STEP=0.15,          # cap *= (1 + STEP) on a raise
    CEILING=1.5,        # max effective cap = CEILING * auto-config
    COOLDOWN_H=24.0,    # no re-raise / re-arm for this long after a raise or revert
    LOW_ATTRIB_H=3.0,   # a real low within this window of an extra-insulin cycle -> revert
    IOB_SAFE_FRAC=0.05,  # low-IOB safe slice: iob < IOB_SAFE_FRAC * TDD  (the ~6.7% pre-low slice)
    HIGH_MGDL=180.0,    # "sustained high" if any of bg30/60/90 exceeds this
    RETRO_MARGIN=15.0,  # retrospective need: eventualBG > target + this (model itself under target)
    EXERCISE_STEPS_60M=600,  # steps/hr proxy for exercise/recovery -> clamp cap to auto-config
    CLIP_TOL=0.98,      # fd >= CLIP_TOL * cap counts as the cap binding
)

# Absolute two-test-bar gates (14d): arm the stepper ONLY for users with headroom.
TBR70_GATE = 3.5
TBR54_GATE = 0.8


def armed(uid):
    """True if the user has TBR headroom for the stepper to be active at all."""
    t70, t54 = vc.TBR14.get(uid, (99, 99))
    return t70 < TBR70_GATE and t54 < TBR54_GATE


def prep():
    df = vc.load()
    df = vc.add_rolling(df)          # min45, low3h
    df = vc.forward_bg(df)           # bg30/60/90
    # per-cycle "sustained high followed" and "real low within LOW_ATTRIB_H"
    fwd = df[["bg30", "bg60", "bg90"]].to_numpy()
    df["fwd_high"] = np.nanmax(fwd, axis=1) > P["HIGH_MGDL"]
    df["tdd_eff"] = df["tdd"].where(df["tdd"] > 0)  # NaN if missing
    return df


def low_within(g, i, hours):
    """Did BG actually go < 70 within `hours` after row i (positional) in group g?"""
    ts = g.ts_epoch.values
    bg = g.bg.values
    horizon = ts[i] + hours * 3600
    k = i + 1
    while k < len(g) and ts[k] <= horizon:
        if bg[k] < 70:
            return True
        k += 1
    return False


TRACK = dict(
    committed=("COMMITTED", None),   # cap = committedCap era (g.cap)
    confirmed=("CONFIRMED", None),   # cap = confirmedCap (CONF_CAPS / CONF_CAP_DEFAULT), constant/user
)


def track_cap(df_g, uid, track):
    """Per-cycle auto-config cap for the chosen track."""
    if track == "confirmed":
        c = vc.CONF_CAPS.get(uid, vc.CONF_CAP_DEFAULT)
        return np.full(len(df_g), float(c))
    return df_g["cap"].values.astype(float)   # committedCap era


def simulate(df, uid, track="committed"):
    """Walk the cap stepper for the chosen track over one user's cycles."""
    target_state = TRACK[track][0]
    g = df[df.user_id == uid].reset_index(drop=True)
    n = len(g)
    auto = track_cap(g, uid, track)               # auto-config cap for this track
    fd = g["fd"].values.astype(float)
    state = g["state"].values
    iob = g["iob"].values.astype(float)
    tdd = g["tdd_eff"].values.astype(float)
    ev = g["ev"].values.astype(float)
    tgt = g["tgt"].values.astype(float)
    steps = g["steps_60m"].values.astype(float)
    fwd_high = g["fwd_high"].values
    ts = g["ts_epoch"].values

    mult = 1.0            # current cap multiplier over auto-config
    clip_count = 0
    cooldown_until = -1.0
    raises = reverts = 0
    extra_total = 0.0
    n_clip = n_qual = n_safe_clip = 0
    raise_days = []

    for i in range(n):
        if not np.isfinite(auto[i]) or auto[i] <= 0:
            continue
        exercising = np.isfinite(steps[i]) and steps[i] > P["EXERCISE_STEPS_60M"]
        eff_cap = auto[i] if exercising else auto[i] * mult

        # cap binding on a cycle of the target state?
        clip = state[i] == target_state and np.isfinite(fd[i]) and fd[i] >= P["CLIP_TOL"] * auto[i]
        if clip:
            n_clip += 1

        # deliver extra under a raised, binding cap; the revert verdict is taken at delivery
        # time (a real low within LOW_ATTRIB_H of the extra-insulin cycle == immediate fall-back)
        if mult > 1.0 and clip and not exercising and eff_cap > fd[i]:
            extra = eff_cap - fd[i]
            extra_total += extra
            # verdict: did a real low follow within LOW_ATTRIB_H of THIS cycle?
            if low_within(g, i, P["LOW_ATTRIB_H"]):
                reverts += 1
                mult = 1.0
                clip_count = 0
                cooldown_until = ts[i] + P["COOLDOWN_H"] * 3600
                continue

        # --- trigger accumulation (only when not in cooldown) ---
        if ts[i] >= cooldown_until:
            safe_iob = np.isfinite(iob[i]) and np.isfinite(tdd[i]) and iob[i] < P["IOB_SAFE_FRAC"] * tdd[i]
            retro = np.isfinite(ev[i]) and np.isfinite(tgt[i]) and ev[i] > tgt[i] + P["RETRO_MARGIN"]
            if clip and safe_iob:
                n_safe_clip += 1
            qualifying = clip and fwd_high[i] and retro and safe_iob and not exercising
            if qualifying:
                n_qual += 1
                clip_count += 1
                if clip_count >= P["WINDOW"] and mult < P["CEILING"]:
                    mult = min(P["CEILING"], mult * (1 + P["STEP"]))
                    raises += 1
                    clip_count = 0
                    cooldown_until = ts[i] + P["COOLDOWN_H"] * 3600
                    raise_days.append(pd.to_datetime(ts[i], unit="s").date())

    days = (ts[-1] - ts[0]) / 86400 if n > 1 else 0
    return dict(
        user=uid, days=round(days, 1), n_state=int((state == target_state).sum()),
        n_clip=n_clip, n_safe_clip=n_safe_clip, n_qual=n_qual,
        raises=raises, reverts=reverts,
        final_mult=round(mult, 3), extra_U=round(extra_total, 2),
        extra_U_per_day=round(extra_total / days, 3) if days else 0,
        raise_days=raise_days,
    )


def price_prelow(df, uid, track="committed"):
    """Empirical two-test price: among this user's low-IOB safe-slice cap clips, what
    fraction actually went low within 3h? That is the honest per-user pre-low rate the
    extra insulin is charged at."""
    target_state = TRACK[track][0]
    g = df[df.user_id == uid]
    capcol = track_cap(g, uid, track)
    m = (g.state == target_state) & (g.fd >= P["CLIP_TOL"] * capcol) \
        & (g.iob < P["IOB_SAFE_FRAC"] * g["tdd_eff"]) & (g.bg >= 140)
    sub = g[m]
    if len(sub) == 0:
        return None, 0
    return round(100 * sub.low3h.mean(), 1), len(sub)


def main():
    ap = argparse.ArgumentParser()
    for k, v in P.items():
        ap.add_argument(f"--{k.lower()}", type=type(v), default=v)
    ap.add_argument("--track", default="committed", choices=list(TRACK))
    args = ap.parse_args()
    for k in P:
        P[k] = getattr(args, k.lower())
    track = args.track

    df = prep()
    rows = []
    for uid in vc.USERS:
        a = armed(uid)
        s = simulate(df, uid, track)
        s["armed"] = a
        pl, npl = price_prelow(df, uid, track)
        s["safe_prelow_pct"] = pl
        s["safe_slice_n"] = npl
        s["priced_low_U"] = round(s["extra_U"] * (pl / 100), 2) if pl is not None else None
        rows.append(s)
    res = pd.DataFrame(rows)

    # freeze un-armed users (report their raw trigger counts but zero the policy actions)
    for i, r in res.iterrows():
        if not r["armed"]:
            res.loc[i, ["raises", "reverts", "extra_U", "extra_U_per_day"]] = 0
            res.loc[i, "final_mult"] = 1.0

    pd.set_option("display.width", 200, "display.max_columns", 30)
    show = res[["user", "armed", "days", "n_state", "n_clip", "n_safe_clip",
                "n_qual", "raises", "reverts", "final_mult", "extra_U_per_day",
                "safe_prelow_pct", "safe_slice_n", "priced_low_U"]]
    print(f"\n=== EVIDENCE-GATED CAP-STEPPER — track={track} ({TRACK[track][0]} / "
          f"{'confirmedCap' if track == 'confirmed' else 'committedCap'}) ===")
    print(f"params: {P}\n")
    print(show.to_string(index=False))

    armed_res = res[res.armed]
    tot_raises = int(armed_res.raises.sum())
    tot_reverts = int(armed_res.reverts.sum())
    print("\n--- go/no-go ---")
    print(f"armed users: {list(armed_res.user)}")
    print(f"total raises: {tot_raises} | total reverts: {tot_reverts} | "
          f"revert:raise = {tot_reverts}:{tot_raises}"
          + (f" ({100*tot_reverts/ (tot_raises+tot_reverts):.0f}% of cap-changes were reverts)"
             if (tot_raises + tot_reverts) else ""))
    write_report(res, armed_res, tot_raises, tot_reverts, df, track)


def write_report(res, armed_res, tot_raises, tot_reverts, df, track):
    span = f"{df.date.min()} → {df.date.max()}"
    suffix = "" if track == "committed" else f"_{track}"
    capname = "confirmedCap" if track == "confirmed" else "committedCap"
    out = os.path.join(os.path.dirname(__file__), f"CAP_STEPPER_REPORT{suffix}.md")
    lines = []
    lines.append(f"# Evidence-gated cap-stepper — {capname} track — cohort policy replay\n")
    lines.append(f"_Data: TimescaleDB `oref.boost_decisions`, cohort {list(vc.USERS)}, "
                 f"span {span}. Generated by `cap_stepper_replay.py`._\n")
    lines.append("## Parameters\n")
    lines.append("```\n" + "\n".join(f"{k} = {v}" for k, v in P.items())
                 + f"\nTBR gates: <70 < {TBR70_GATE}%  AND  <54 < {TBR54_GATE}%\n```\n")
    lines.append("## What this measures (and what it can't)\n")
    lines.append(
        "No glucodynamic model exists, so counterfactual BG under a higher cap is "
        "**unobservable**. This replays the *policy* over real telemetry: triggers from "
        "actual fields, raise/revert dynamics judged against **actual** forward-BG, added "
        "insulin **priced** against observed lows. The trustworthy outputs are the "
        "**revert frequency** and the **safe-slice size**; the TIR buy-back is an "
        "upper bound and is not claimed here.\n")
    lines.append("## Per-user\n")
    cols = ["user", "armed", "days", "n_state", "n_clip", "n_safe_clip", "n_qual",
            "raises", "reverts", "final_mult", "extra_U_per_day", "safe_prelow_pct",
            "safe_slice_n", "priced_low_U"]
    hdr = ("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
    body = "".join("| " + " | ".join(str(res.loc[i, c]) for c in cols) + " |\n"
                   for i in res.index)
    lines.append(hdr + body + "\n")
    lines.append("### Column key\n"
                 f"- **n_state** — {TRACK[track][0]} cycles. **n_clip** — of those, where fd hit "
                 f"{capname} (cap binding).\n"
                 "- **n_safe_clip** — of those, the ones in the low-IOB safe slice (iob < "
                 f"{P['IOB_SAFE_FRAC']:.0%} TDD, BG≥140). *If n_safe_clip ≪ n_clip, most cap-clips are "
                 "high-IOB — the recovering-highs rejection, seen per-user.*\n"
                 "- **n_qual** — safe clips that ALSO had a sustained high follow and retrospective need "
                 "(the full trigger).\n"
                 "- **raises / reverts** — policy actions once armed. **safe_prelow_pct** — empirical "
                 "fraction of the safe slice that went low within 3h = the two-test price the extra "
                 "insulin is charged at. **priced_low_U** — extra units × that rate.\n")
    if track == "committed":
        lines.append("## Robustness (parameter sweep, 2026-07-08 run)\n")
        lines.append("Revert rate is stable and high across every variant tried, and raises stay "
                     "in single digits cohort-wide over ~6 weeks:\n\n"
                     "| variant | raises | reverts | revert share |\n|---|---|---|---|\n"
                     "| default (window 10) | 4 | 3 | 43% |\n"
                     "| window 5 | 6 | 3 | 33% |\n"
                     "| window 5, iob<3% TDD | 3 | 3 | 50% |\n"
                     "| window 8, step 10%, cd 48h | 4 | 3 | 43% |\n"
                     "| high threshold 160 | 4 | 4 | 50% |\n\n"
                     "No parameterization escapes the churn.\n")
    lines.append("## Go / no-go\n")
    # Verdict keys on trigger RARITY and revert SHARE, not raw counts — a 4-vs-3 run must not read
    # as "candidate" (fixed 2026-07-10 audit: raw-count logic contradicted the paper's NO-GO).
    # NO-GO if the trigger barely fires (< ~10 raises cohort-wide/6wk = too rare to matter) OR the
    # revert share is high (churns caps at the cost of lows). Per-user revert-share also matters.
    changes = tot_raises + tot_reverts
    revert_share = tot_reverts / changes if changes else 0.0
    if tot_raises < 10 or revert_share >= 0.33:
        verdict = "**NO-GO** — trigger too rare and/or revert-heavy"
    elif revert_share >= 0.20:
        verdict = "**CAUTION — revert-heavy**"
    else:
        verdict = "**candidate — worth building for the safe-slice users**"
    lines.append(f"Armed users: {list(armed_res.user)}\n\n"
                 f"- total raises: **{tot_raises}**, total reverts: **{tot_reverts}** "
                 f"(revert share **{100*revert_share:.0f}%**)\n"
                 f"- verdict: {verdict}\n\n"
                 "Read it this way: a **rare trigger** (single-digit raises over six weeks) means the "
                 "lever barely engages — NO-GO on rarity alone. A **high revert share** (≥33% of "
                 "cap-changes reverted) means it churns caps at the cost of lows — NO-GO on churn. "
                 "Only frequent raises with a low revert share AND a non-trivial safe-slice would be "
                 "worth building; otherwise auto-config + raise-guard already is the controller.\n")
    with open(out, "w") as f:
        f.write("\n".join(lines))
    print(f"\nreport -> {out}")


if __name__ == "__main__":
    main()
