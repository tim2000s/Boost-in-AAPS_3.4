#!/usr/bin/env python3
"""Replays the on-device tranche threshold derivation for every participant with V6 confirms.

For each participant with at least one CONFIRMED cycle under the active V6 override in the last 45
days, this counts confirm episodes from the cycle stream (repeat uploads removed, never five-minute
buckets), scores them with the shipped release rule, and derives the threshold exactly as
TrancheThresholdDeriver does on the phone. It then applies the auto-config rule
(BoostV5AutoConfigApply.resolveTrancheThreshold) to each participant's current setting, using the
time below range over the 28-day re-derivation window, which is the window the weekly run uses.

Current settings are those read from the 8 October 2026 field review
(backtesting/scripts/2026-10-tranche-cohort-review on the vehicle branch): self 0.65 set by hand,
A, E and K at 0.48. Everyone else is taken to be at the factory 0.48.

Output: out/replay.txt, out/replay.json.
"""
import json
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd
import psycopg2

import tranche_derive as td

HERE = os.path.dirname(os.path.abspath(__file__))
warnings.filterwarnings("ignore", message=".*SQLAlchemy.*")
LOOKBACK_DAYS = 45
TBR_WINDOW_DAYS = 28
REPEAT_WINDOW_S = 240
# Keyed by cohort tag. The database id of the development participant is not written here; it is
# read from BOOST_SELF_DB_ID and reported as "self".
SELF_ID = os.environ.get("BOOST_SELF_DB_ID")
CURRENT = {"self": 0.65, "A": 0.48, "E": 0.48, "K": 0.48}
HAND_SET = {"self"}


def tag(u):
    return "self" if u == SELF_ID else u


def dedup_repeats(df):
    """Copied from backtesting/scripts/2026-07-v7-foundation/v7_common.py on the vehicle branch.

    A row is a repeat upload when the same user's next row carries the same reason string and the
    same glucose within REPEAT_WINDOW_S; the last copy is kept.
    """
    g = "cgm_mgdl" if "cgm_mgdl" in df.columns else "bg"
    d = df.sort_values(["user_id", "ts_epoch"]).reset_index(drop=True)
    nxt = d.groupby("user_id")[["reason_text", g, "ts_epoch"]].shift(-1)
    rep = (d.reason_text == nxt.reason_text) & (d[g] == nxt[g]) & ((nxt.ts_epoch - d.ts_epoch) <= REPEAT_WINDOW_S)
    return d[~rep.fillna(False)].reset_index(drop=True)


def main():
    if not SELF_ID:
        raise SystemExit("set BOOST_SELF_DB_ID to the development participant's database id")
    conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - LOOKBACK_DAYS * 86_400_000
    users = pd.read_sql(
        """select distinct user_id from boost_decisions
           where ts_utc > now() - interval '45 days' and boostv5_active and boostv5_state = 'CONFIRMED'
           order by 1""", conn).user_id.tolist()

    rows, lines = [], []
    lines.append(f"run at {pd.Timestamp(now_ms, unit='ms', tz='UTC'):%Y-%m-%d %H:%M} UTC; window {LOOKBACK_DAYS} d; "
                 f"TBR over {TBR_WINDOW_DAYS} d")
    for u in users:
        cyc = pd.read_sql(
            """select user_id, ts_epoch, (extract(epoch from ts_utc) * 1000)::bigint as ms,
                      boostv5_state as state, cgm_mgdl, reason_text
               from boost_decisions
               where user_id = %s and ts_utc > now() - interval '45 days'
                 and boostv5_active and boostv5_state is not null""", conn, params=(u,))
        n_raw = len(cyc)
        cyc = dedup_repeats(cyc)
        cgm = pd.read_sql(
            """select (extract(epoch from ts_utc) * 1000)::bigint as ms, cgm_mgdl from boost_cgm
               where user_id = %s and ts_utc > now() - interval '45 days' order by ts_utc""", conn, params=(u,))
        onsets = td.confirm_onsets(list(zip(cyc.ms.astype(int), cyc.state)))
        d = td.derive(onsets, list(zip(cgm.ms.astype(int), cgm.cgm_mgdl)))
        recent = cgm[cgm.ms > now_ms - TBR_WINDOW_DAYS * 86_400_000].cgm_mgdl
        recent = recent[recent >= 1.0]
        n = len(recent)
        tbr70 = 100.0 * (recent < 70).sum() / n if n else float("nan")
        sev54 = 100.0 * (recent < 54).sum() / n if n else float("nan")
        current = CURRENT.get(tag(u), td.FACTORY)
        stored = current if tag(u) in CURRENT else None
        outcome, operative, why = td.resolve(d["threshold"], d["n_small"] + d["n_large"], stored, None, tbr70, sev54)
        if tag(u) in HAND_SET and outcome != "KEPT_USER_TUNED":
            raise SystemExit(f"{tag(u)}: hand-set value not kept ({outcome})")
        rows.append(dict(user=tag(u), cycles_raw=n_raw, cycles=len(cyc), onsets=len(onsets),
                         episodes=len(d["episodes"]), n_small=d["n_small"], n_large=d["n_large"],
                         derived=d["threshold"], j=d["j"], shortfall=d["shortfall"],
                         current=current, hand_set=tag(u) in HAND_SET, tbr70=tbr70, sev54=sev54, cgm_28d=n,
                         well_controlled=bool(tbr70 < td.WELL_CONTROLLED_MAX_TBR70 and sev54 < td.WELL_CONTROLLED_MAX_SEV54),
                         outcome=outcome, applied=operative, why=why))

    hdr = (f"{'user':>5} {'cycles':>7} {'onsets':>6} {'eps':>4} {'small':>5} {'large':>5} {'derived':>7} {'J':>5} "
           f"{'current':>8} {'TBR70':>6} {'TBR54':>6} {'wc':>3}  outcome -> applied")
    lines.append(hdr)
    for r in rows:
        dv = "-" if r["derived"] is None else f"{r['derived']:.2f}"
        jv = "-" if r["j"] is None else f"{r['j']:.2f}"
        cur = f"{r['current']:.2f}{'*' if r['hand_set'] else ''}"
        lines.append(f"{r['user']:>5} {r['cycles']:>7} {r['onsets']:>6} {r['episodes']:>4} {r['n_small']:>5} "
                     f"{r['n_large']:>5} {dv:>7} {jv:>5} {cur:>8} {r['tbr70']:>6.2f} {r['sev54']:>6.2f} "
                     f"{'yes' if r['well_controlled'] else 'no':>3}  {r['outcome']} ({r['why']}) -> {r['applied']:.2f}")
    lines.append("* set by hand. wc: well controlled, TBR<70 under 1.5% and <54 under 0.3% over 28 d.")
    text = "\n".join(lines)
    print(text)
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    with open(os.path.join(HERE, "out", "replay.txt"), "w") as f:
        f.write(text + "\n")
    with open(os.path.join(HERE, "out", "replay.json"), "w") as f:
        json.dump(dict(now_ms=now_ms, rows=rows), f, indent=1, default=float)


if __name__ == "__main__":
    sys.exit(main())
