"""What a post-low rebound score would look like at an operating point.

An AUC says the ordering is better than the baseline's; it does not say whether there is a
slice of recoveries where releasing the guard would be defensible. The guard pays when
another low follows and costs when a genuine rebound follows, so the question is whether
any decile of a rebound score contains recoveries that are much more likely to rebound and
no more likely to go low again.

Both outcomes are scored out of sample with participants held out, using the same episode
features, and the recoveries are then sorted by the rebound score alone. The re-low rate in
each decile is read off, not fitted to, so the two columns are independent readings of the
same slice.

This is descriptive. Whether releasing the guard on those recoveries would improve anything
is a policy question, and with no glucodynamic simulator the counterfactual glucose is not
available, so nothing here settles it.
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

import common
from c3_post_low_rebound import BASE, EPISODE, LOOP, commons_episodes, oos_scores


def deciles(df: pd.DataFrame, label: str, feats: list[str], out: dict):
    s_high = oos_scores(df, feats, "y_high")
    s_relow = oos_scores(df, feats, "y_relow")
    d = df.assign(s_high=s_high, s_relow=s_relow).dropna(subset=["s_high", "s_relow"])
    base_h, base_l = float(d.y_high.mean()), float(d.y_relow.mean())
    res = {}
    # Sorted two ways. By the rebound score, because that is what a released guard would be
    # betting on; and by the repeat-low score, because releasing the guard is only
    # defensible where the repeat low it protects against is genuinely less likely.
    for sort_by in ("s_high", "s_relow"):
        d["dec"] = pd.qcut(d[sort_by], 10, labels=False, duplicates="drop")
        rows = []
        for k, g in d.groupby("dec"):
            rows.append(dict(decile=int(k) + 1, n=int(len(g)),
                             rebound=float(g.y_high.mean()),
                             relow=float(g.y_relow.mean()),
                             both=float((g.y_high & g.y_relow).mean()),
                             median_nadir=float(g.nadir.median()),
                             median_bg_recover=float(g.bg_recover.median())))
            print(f"    {label} by {sort_by} decile {k + 1:2d}  n={len(g):6,}  "
                  f"rebound {rows[-1]['rebound']:.3f}  re-low {rows[-1]['relow']:.3f}  "
                  f"both {rows[-1]['both']:.3f}", flush=True)
        top, bot = rows[-1], rows[0]
        print(f"    {label} by {sort_by}: base {base_h:.3f}/{base_l:.3f}; "
              f"top decile {top['rebound']:.3f}/{top['relow']:.3f}, "
              f"bottom {bot['rebound']:.3f}/{bot['relow']:.3f}", flush=True)
        res[sort_by] = rows
    out[label] = dict(base_rebound=base_h, base_relow=base_l, by=res,
                      n=int(len(d)), n_participants=int(d.pid.nunique()))


if __name__ == "__main__":
    from boost_cohort import boost_low_recoveries

    ep = list(BASE) + [c for c in EPISODE if c not in BASE]
    out = {}

    cm = commons_episodes()
    cm["fold"] = [common.stable_fold(p, 5) for p in cm["pid"]]
    cm = cm[cm["sug_eventualbg"].between(20, 600)]
    print(f"== Commons, {len(cm):,} recoveries ==", flush=True)
    deciles(cm, "commons_episode", ep, out)
    deciles(cm, "commons_loop", ep + list(LOOP), out)

    bo = boost_low_recoveries()
    bo["fold"] = [common.stable_fold(p, 5) for p in bo["pid"]]
    bo = bo[bo["sug_eventualbg"].between(20, 600)]
    print(f"== Boost, {len(bo):,} recoveries ==", flush=True)
    deciles(bo, "boost_episode", ep, out)
    deciles(bo, "boost_loop", ep + list(LOOP), out)

    with open(os.path.join(common.OUT, "c3_operating.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("written c3_operating.json")
