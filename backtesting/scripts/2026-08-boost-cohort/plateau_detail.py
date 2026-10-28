#!/usr/bin/env python3
"""What the plateau nudge shadow did for one participant, and what it would do now.

The cohort report showed this layer reporting its safety floor satisfied on every triggered cycle,
which is the signature of the fail-open defect rather than evidence of safety. That makes the
recorded floor state unusable. It does not make the whole record unusable, because the trigger
context is logged alongside it: the glucose, the trend and the insulin on board at the moment of
each trigger are all stored. The guards added since can therefore be applied to the historical
triggers directly, which gives an answer that does not depend on which build was running.

Three questions are answered.

Whether the floor ever vetoed anything, and from what date it began to, which locates when a fixed
build reached the participant without having to guess from release dates.

How the triggers are distributed in trend, since the trigger condition was unbounded below and a
steep descent satisfied it just as a genuine plateau did.

How many triggers survive the guards now in place, which is the number that matters for deciding
whether this layer is worth carrying forward.

Usage:
  python3 plateau_detail.py --user tim [--days 90]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
DSN = "dbname=oref host=127.0.0.1 port=5432"

# Guards as they now stand on the shipping branches.
PLATEAU_MIN_TREND = -3.0     # mg/dL per 5 min; steeper than this is a descent, not a plateau
MINGUARD_FLOOR = 85.0        # mg/dL forward low below which the nudge is vetoed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="tim")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--out")
    a = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    d = pd.read_sql(
        """SELECT ts_utc, boostv5_plateau_trig trig, boostv5_plateau_wouldnudge nudge,
                  boostv5_plateau_bg bg, boostv5_plateau_trend trend,
                  boostv5_plateau_iob iob, boostv5_plateau_floor floor, reason_minguardbg
           FROM boost_decisions
           WHERE user_id = %s AND ts_utc > now() - (%s || ' days')::interval
             AND boostv5_plateau_trig IS NOT NULL
           ORDER BY ts_utc""", conn, params=(a.user, a.days))
    conn.close()

    L, P = [], None
    P = L.append
    P(f"# Plateau nudge shadow, participant {a.user}\n")
    if d.empty:
        P("\nNo cycles carry this layer over the window.\n")
        open(a.out or os.path.join(HERE, f"PLATEAU_{a.user}.md"), "w").write("\n".join(L))
        print("\n".join(L)); return

    d["day"] = pd.to_datetime(d.ts_utc, utc=True).dt.date
    t = d[d.trig > 0].copy()
    P(f"\n{len(d):,} cycles carry the layer over the last {a.days} days, of which {len(t):,} "
      f"triggered, or {100 * len(t) / len(d):.1f} per cent. The would-be nudge is "
      f"{t.nudge.mean():.2f} U where it fired, so the layer proposes about "
      f"{t.nudge.sum() / max(1, d.day.nunique()):.2f} U per day in total.\n")

    P("\n## Did the floor ever veto\n")
    fl = d[d.trig > 0].floor.fillna("unset").value_counts()
    P("\n| floor state on a triggered cycle | cycles | share |")
    P("|---|---|---|")
    for k, v in fl.items():
        P(f"| {k} | {v:,} | {100 * v / len(t):.1f}% |")
    non_ok = t[~t.floor.fillna("unset").isin(["ok", "unset"])]
    if non_ok.empty:
        P("\nThe floor recorded no veto at any point in the window. On its own that is consistent "
          "either with a participant who never approached a low while plateau conditions held, or "
          "with a floor that was not working. The trend distribution below distinguishes the two.\n")
    else:
        P(f"\nThe floor first vetoed on {non_ok.day.min()}, and has done so on {len(non_ok):,} "
          f"cycles since. That date locates when a build carrying the fix reached this "
          f"participant, which is firmer than inferring it from release dates.\n")

    P("\n## Trend at the moment of trigger\n")
    P("\nThe trigger condition required the trend to be at or below 1.7 mg/dL per 5 min and set no "
      "lower bound, so a steep descent satisfied it exactly as a flat stretch did. The guard added "
      f"since vetoes a trigger whose trend is steeper than {PLATEAU_MIN_TREND:.0f}.\n")
    bins = [-np.inf, -10, -5, -3, -1, 1, np.inf]
    labels = ["steeper than -10", "-10 to -5", "-5 to -3", "-3 to -1", "-1 to +1", "above +1"]
    cut = pd.cut(t.trend, bins=bins, labels=labels)
    vc = cut.value_counts().reindex(labels).fillna(0).astype(int)
    P("\n| trend at trigger (mg/dL per 5 min) | cycles | share |")
    P("|---|---|---|")
    for k in labels:
        P(f"| {k} | {vc[k]:,} | {100 * vc[k] / len(t):.1f}% |")
    falling = int((t.trend < PLATEAU_MIN_TREND).sum())
    P(f"\n{falling:,} triggers, or {100 * falling / len(t):.1f} per cent, occurred on a trend "
      f"steeper than {PLATEAU_MIN_TREND:.0f} and would now be vetoed as a descent rather than "
      f"treated as a plateau.\n")

    P("\n## What survives the guards now in place\n")
    have_mg = t.reason_minguardbg.notna()
    mg_veto = int((t.reason_minguardbg < MINGUARD_FLOOR).sum())
    mg_unknown = int((~have_mg).sum())
    surv = t[(t.trend >= PLATEAU_MIN_TREND) & have_mg & (t.reason_minguardbg >= MINGUARD_FLOOR)]
    P(f"\nApplying both guards to the recorded triggers, {falling:,} fall to the trend bound, "
      f"{mg_veto:,} to a forward low under {MINGUARD_FLOOR:.0f} mg/dL, and {mg_unknown:,} to the "
      f"absence of a forward low, which now vetoes rather than passes. That leaves {len(surv):,} "
      f"triggers of the original {len(t):,}, or {100 * len(surv) / len(t):.1f} per cent, and about "
      f"{surv.nudge.sum() / max(1, d.day.nunique()):.2f} U per day proposed rather than "
      f"{t.nudge.sum() / max(1, d.day.nunique()):.2f}.\n")
    if len(surv):
        P(f"\nAmong the survivors the median glucose at trigger is {surv.bg.median():.0f} mg/dL, "
          f"the median trend {surv.trend.median():+.1f} and the median insulin on board "
          f"{surv.iob.median():.2f} U.\n")

    P("\n## Reading this\n")
    P("\nThe surviving count is what the layer would propose today, computed from this "
      "participant's own history rather than from a rerun, so it does not depend on which build "
      "was installed when. It is a reasonable basis for deciding whether the layer is worth "
      "carrying forward. It is not a substitute for collecting the shadow again on a fixed build, "
      "because the floor state recorded at the time is unusable and only the trigger context has "
      "been reused here.\n")

    open(a.out or os.path.join(HERE, f"PLATEAU_{a.user}.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
