#!/usr/bin/env python3
"""Is a quarter of confirms being followed by a low actually elevated?

The rate has been quoted twice in this programme as though it were a fault, but a rate on its own is
not a finding. Glucose falls below 70 for reasons that have nothing to do with a confirm, and unless
the same three hours starting from the same place without a confirm are safer, there is nothing here
to fix.

Each confirm is matched to control windows from the same participant: the same hour of day, a
starting glucose within 15 mg/dL, insulin on board within 0.5 U, and no confirm anywhere in the
window or the hour before it. Matching on the starting state is what makes the comparison mean
something, since confirms happen when glucose is high and rising and those windows would carry a
different low rate whatever the engine did.

The estimate is the within-participant difference in the rate, so a participant with many confirms
and a high baseline cannot move the answer on their own, and the interval resamples participants.

Usage:
  python3 base_rate.py [--horizon 180] [--out BASE_RATE.md]
"""
from __future__ import annotations

import argparse
import os
import warnings

import numpy as np
import pandas as pd
import psycopg2

DSN = "dbname=oref host=127.0.0.1 port=5432"
HERE = os.path.dirname(os.path.abspath(__file__))
warnings.filterwarnings("ignore", message=".*SQLAlchemy connectable.*")

LOW, SEVERE = 70.0, 54.0
BG_TOL, IOB_TOL = 15.0, 0.5


def connect():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def load(conn):
    d = pd.read_sql(
        """SELECT user_id, ts_utc, boostv5_state, cgm_mgdl, iob_iob, boostv5_finaldose
           FROM boost_decisions
           WHERE variant='boost-other' AND boostv5_active IS NOT NULL AND boostv5_state IS NOT NULL
           ORDER BY user_id, ts_utc""", conn)
    d["ts_utc"] = pd.to_datetime(d.ts_utc, utc=True)
    for c in ("cgm_mgdl", "iob_iob", "boostv5_finaldose"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def windows(d, horizon):
    """Every cycle as a candidate window start, flagged for whether a confirm happens at it."""
    rows = []
    H = np.timedelta64(horizon, "m")
    HOUR = np.timedelta64(60, "m")
    for user, g in d.groupby("user_id"):
        g = g.reset_index(drop=True)
        prev = g.boostv5_state.shift(1)
        is_entry = (g.boostv5_state == "CONFIRMED") & (prev != "CONFIRMED")
        ts, bg, iob = g.ts_utc.values, g.cgm_mgdl.values, g.iob_iob.values
        conf_ts = ts[is_entry.values]
        for i in range(len(g)):
            if not np.isfinite(bg[i]) or not np.isfinite(iob[i]):
                continue
            fut = bg[(ts > ts[i]) & (ts <= ts[i] + H)]
            fut = fut[~np.isnan(fut)]
            if len(fut) < 6:
                continue
            # a control must be clean: no confirm in the window, nor in the hour before it
            near = conf_ts[(conf_ts >= ts[i] - HOUR) & (conf_ts <= ts[i] + H)]
            rows.append(dict(
                user=user, ts=pd.Timestamp(ts[i]),
                hour=pd.Timestamp(ts[i]).hour, bg=bg[i], iob=iob[i],
                is_confirm=bool(is_entry.values[i]),
                clean=(len(near) == 0),
                low=bool(np.min(fut) < LOW), severe=bool(np.min(fut) < SEVERE)))
    return pd.DataFrame(rows)


def match(w):
    """For each confirm, the mean control rate from its own matched pool."""
    out = []
    for user, g in w.groupby("user"):
        conf = g[g.is_confirm]
        ctrl = g[g.clean & ~g.is_confirm]
        if conf.empty or ctrl.empty:
            continue
        cb, ci, ch = ctrl.bg.values, ctrl.iob.values, ctrl.hour.values
        clow, csev = ctrl.low.values, ctrl.severe.values
        for _, r in conf.iterrows():
            m = ((np.abs(cb - r.bg) <= BG_TOL) & (np.abs(ci - r.iob) <= IOB_TOL)
                 & (np.abs(((ch - r.hour + 12) % 24) - 12) <= 1))
            if m.sum() < 5:
                continue
            out.append(dict(user=user, ts=r.ts, n_ctrl=int(m.sum()),
                            conf_low=r.low, ctrl_low=float(clow[m].mean()),
                            conf_sev=r.severe, ctrl_sev=float(csev[m].mean())))
    return pd.DataFrame(out)


def boot(df, a, b, n=10000, seed=5):
    users = df.user.unique()
    if len(users) < 3:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    by = {u: df[df.user == u] for u in users}
    out = []
    for _ in range(n):
        s = pd.concat([by[u] for u in rng.choice(users, len(users), replace=True)])
        out.append(s[a].mean() - s[b].mean())
    return tuple(np.percentile(out, [2.5, 97.5]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=180)
    ap.add_argument("--out")
    a = ap.parse_args()
    conn = connect()
    w = windows(load(conn), a.horizon)
    m = match(w)

    L, P = [], None
    P = L.append
    P("# Is the post-confirm low rate elevated?\n")
    P(f"\nEach confirm compared against control windows from the same participant, matched on hour of "
      f"day to within an hour, starting glucose to within {BG_TOL:.0f} mg/dL and insulin on board to "
      f"within {IOB_TOL:.1f} U, with no confirm in the window or the hour before it. Outcome is the "
      f"lowest glucose in the following {a.horizon} minutes.\n")
    P(f"\n{len(m)} confirms matched, {m.user.nunique()} participants, median "
      f"{m.n_ctrl.median():.0f} controls each.\n")

    for col_c, col_k, label, thr in (("conf_low", "ctrl_low", "below 70", LOW),
                                     ("conf_sev", "ctrl_sev", "below 54", SEVERE)):
        lo, hi = boot(m, col_c, col_k)
        diff = m[col_c].mean() - m[col_k].mean()
        verdict = ("confirms are WORSE" if lo > 0 else
                   "confirms are BETTER" if hi < 0 else "not distinguishable")
        P(f"\n## {label}\n")
        P(f"\nAfter a confirm {100*m[col_c].mean():.1f} per cent, in matched control windows "
          f"{100*m[col_k].mean():.1f} per cent. Difference {100*diff:+.1f} points "
          f"[{100*lo:+.1f}, {100*hi:+.1f}]: {verdict}.\n")

    P("\n## Per participant\n")
    P("\n| participant | confirms | after a confirm | matched controls | difference |")
    P("|---|---|---|---|---|")
    for u in sorted(m.user.unique()):
        g = m[m.user == u]
        P(f"| {u} | {len(g)} | {100*g.conf_low.mean():.0f}% | {100*g.ctrl_low.mean():.0f}% | "
          f"{100*(g.conf_low.mean()-g.ctrl_low.mean()):+.0f} |")

    text = "\n".join(L) + "\n"
    if a.out:
        open(os.path.join(HERE, a.out), "w").write(text)
        print(f"wrote {a.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
