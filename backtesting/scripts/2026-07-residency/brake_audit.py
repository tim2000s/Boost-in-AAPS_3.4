#!/usr/bin/env python3
"""Brake-correctness audit — pricing the 34% BRAKE_SUPPRESS high-time (2026-07-08).

The residency attribution found the composed-multiplier brake owns ~34% of high-time and
is foreseeable — but that is PROXIMATE, not causal. This audit asks the causal question by
OUTCOME: on cycles where the brake genuinely suppressed a wanted dose during a rising high
(oref insulinReq>0, composed actionMult≈0), what happened next, and in what IOB context?

Decomposition of brake-suppressed high-cycle-minutes:
  WRONG_RECOVERABLE  stayed high, LOW IOB (safe to add), no forward low
                     -> the composed floor SHOULD dose here; this is its real target.
  RIGHT_SAVEDLOW     a low (<70 within 3h) actually followed
                     -> the brake correctly prevented a low; dosing would have deepened it.
  RIGHT_RESTRAINT    HIGH IOB (insulin already coming), no forward low
                     -> correct restraint; adding is the ~19%-pre-low recovering slice.
  HARMLESS_RESOLVED  low IOB, came back to range on its own, no low
                     -> brake was harmless (a dose would have been unnecessary).

We can't simulate counterfactual BG, so WRONG_RECOVERABLE is priced two honest ways:
the composed floor's own `floorWouldAdd` (what it would inject) and the empirical
forward-low rate of that exact slice (the two-test price of adding there).

Uses boostv5_actionmult + boostv5_floorwouldadd from oref.boost_decisions.
"""
import os
import sys

import numpy as np
import pandas as pd
import psycopg2

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "2026-07-v7-foundation"))
import v7_common as vc  # noqa: E402

# The composed brake shows up as the AggressionBudget crushed to ~0 (boostv5_actionmult is
# only the per-STATE multiplier: 0.3/0.4/1.0/1.8, never ~0; boostv5_floorwouldadd is 100% NULL
# in historical rows — the floor is too new to be logged, so it can't be priced directly here).
HI_ONSET = 170.0      # elevated
BRAKE_BUDGET = 0.10   # composed AggressionBudget below this = the dose was crushed
MIN_REQ = 0.05        # oref insulinReq above this = a dose was genuinely wanted
IOB_SAFE_FRAC = 0.05  # iob < this * TDD = safe-to-add slice
MIN_PER_CYCLE = 5.0


def load():
    conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
    q = """
    SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
      user_id, ts_epoch, ts_utc, cgm_mgdl AS bg, boostv5_state AS state,
      boostv5_finaldose AS fd, boostv5_budget AS budget, boostv5_actionmult AS amult,
      boostv5_floorwouldadd AS floor_add, sug_insulinreq AS insreq,
      iob_iob AS iob, tdd, boostv5_committedcap AS ccap
    FROM boost_decisions
    WHERE boostv5_state IS NOT NULL
    ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
    """
    df = pd.read_sql(q, conn, params=None).sort_values(["user_id", "ts_epoch"]).reset_index(drop=True)
    conn.close()
    df["dt"] = df.groupby("user_id").ts_epoch.diff() / 60
    df["delta5"] = df.groupby("user_id").bg.diff() / df.dt * 5
    df.loc[(df.dt > 7.6) | (df.dt < 2.0), "delta5"] = np.nan
    df["date"] = pd.to_datetime(df.ts_utc, utc=True, format="mixed").dt.date
    df = vc.add_rolling(df)      # min45, low3h
    df = vc.forward_bg(df)       # bg30/60/90
    df["iob_frac"] = df.iob / df.tdd.where(df.tdd > 0)
    return df


def classify(df):
    # brake-suppressed: elevated, oref genuinely wanted insulin, but the composed budget was
    # crushed to ~0 (regardless of state — the brake can fire in OBSERVING/RECOVERING/COMMITTED).
    braked = (df.bg > HI_ONSET) & (df.insreq > MIN_REQ) & (df.budget < BRAKE_BUDGET)
    b = df[braked].copy()
    stayed_high = (b.bg60 > 180) & (b.bg90 > 180)
    went_low = b.low3h.astype(bool)
    safe_iob = b.iob_frac < IOB_SAFE_FRAC
    cause = np.where(
        went_low, "RIGHT_SAVEDLOW",
        np.where(stayed_high & safe_iob, "WRONG_RECOVERABLE",
                 np.where(~safe_iob, "RIGHT_RESTRAINT", "HARMLESS_RESOLVED")))
    b["bucket"] = cause
    return b


BUCKETS = ["WRONG_RECOVERABLE", "RIGHT_SAVEDLOW", "RIGHT_RESTRAINT", "HARMLESS_RESOLVED"]


def main():
    df = load()
    b = classify(df)
    print(f"=== BRAKE-CORRECTNESS AUDIT ===")
    print(f"brake-suppressed cycles (bg>{HI_ONSET:.0f}, oref insulinReq>{MIN_REQ}, "
          f"budget<{BRAKE_BUDGET}): {len(b)}  ({len(b)*MIN_PER_CYCLE:.0f} min)")
    sm = (b.state.value_counts(normalize=True) * 100).round(0).to_dict()
    print(f"state mix of the brake set: {sm}\n")

    # per-user + cohort minute shares
    print(f"{'user':>5} {'brake_min':>9} " + " ".join(f"{x[:9]:>9}" for x in BUCKETS))
    for u in vc.USERS:
        bu = b[b.user_id == u]
        tot = len(bu) * MIN_PER_CYCLE or 1
        print(f"{u:>5} {len(bu)*MIN_PER_CYCLE:>9.0f} " +
              " ".join(f"{100*(bu.bucket==x).sum()*MIN_PER_CYCLE/tot:>8.0f}%" for x in BUCKETS))
    tot = len(b) * MIN_PER_CYCLE or 1
    print(f"{'COHORT':>5} {len(b)*MIN_PER_CYCLE:>9.0f} " +
          " ".join(f"{100*(b.bucket==x).sum()*MIN_PER_CYCLE/tot:>8.0f}%" for x in BUCKETS))

    # ── price the WRONG_RECOVERABLE slice ──
    wr = b[b.bucket == "WRONG_RECOVERABLE"]
    print(f"\n--- WRONG_RECOVERABLE (the composed-floor target) ---")
    print(f"minutes: {len(wr)*MIN_PER_CYCLE:.0f}  = {100*len(wr)/max(len(b),1):.0f}% of brake-suppressed time")
    fa = wr.floor_add.dropna()
    if len(fa):
        print(f"floorWouldAdd on these cycles: median {fa.median():.3f} U (n={len(fa)} non-null)")
    else:
        print("floorWouldAdd: unavailable (100% NULL in historical rows — floor logged only post-ship)")
    # empirical two-test price: forward-low rate of the low-IOB rising-high slice (dosing there)
    safe_slice = df[(df.bg > HI_ONSET) & (df.iob_frac < IOB_SAFE_FRAC)]
    print(f"empirical forward-low(<70 in 3h) rate of the low-IOB high slice "
          f"(the price of dosing here): {100*safe_slice.low3h.mean():.1f}%  (n={len(safe_slice)})")

    # verdict framing
    cohort = {x: (b.bucket == x).sum() * MIN_PER_CYCLE for x in BUCKETS}
    right = cohort["RIGHT_SAVEDLOW"] + cohort["RIGHT_RESTRAINT"]
    print(f"\n--- verdict ---")
    print(f"RIGHT (saved-low + correct high-IOB restraint): {100*right/tot:.0f}% of brake time")
    print(f"WRONG_RECOVERABLE (floor-addressable, safe): {100*cohort['WRONG_RECOVERABLE']/tot:.0f}%")
    print(f"HARMLESS_RESOLVED (came down anyway): {100*cohort['HARMLESS_RESOLVED']/tot:.0f}%")

    b.to_json(os.path.join(os.path.dirname(__file__), "brake_audit_cycles.json"), orient="records")


if __name__ == "__main__":
    main()
