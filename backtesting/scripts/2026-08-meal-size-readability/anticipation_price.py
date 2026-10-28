#!/usr/bin/env python3
"""Does the per-user anticipation shadow anticipate anything the clock does not?

The shadow logs a forward probability that a meal is coming, derived per user. Its 149,906 rows sat
in reason_text unparsed until the 2026-08-25 backfill, so this is the first time it can be priced
from columns.

The test is whether the probability is elevated before a rise actually starts. Rise onsets are built
from the participant's own glucose exactly as the detection negatives were, so no announcement is
needed and every participant running the shadow can be scored.

The control is the clock. A per-user prior over meal timing is close to a statement about the hour
of the day, and the hour is free to any controller. A shadow that merely reproduces its user's meal
clock has added nothing, so the hour-of-day rate is fitted on the participant's other days and
scored on the held-out one, and the shadow has to beat it.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""

import bisect
import json
import os
import sys

import numpy as np
import psycopg2

from extract_meals import RESCUE_BG
from size_readability import auc_of

LOOKAHEAD_MIN = (15, 30, 60)
MIN_RISE = 25.0
SEED = 20260825


def onsets_from(ts, bg):
    out, i = [], 4
    while i < len(ts) - 40:
        w = bisect.bisect_right(ts, ts[i] + 30 * 60)
        if w - i >= 4 and bg[i:w].max() - bg[i] >= MIN_RISE and bg[i] > RESCUE_BG:
            out.append(ts[i])
            i = w + 12
            continue
        i += 1
    return np.asarray(out)


def main():
    conn = psycopg2.connect("dbname=oref")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("select distinct user_id from public.boost_decisions "
                    "where anticip_p_meal is not null order by 1")
        users = [r[0] for r in cur.fetchall()]

    rows = []
    for u in users:
        with conn.cursor() as cur:
            cur.execute("select extract(epoch from ts_utc), anticip_p_meal from public.boost_decisions "
                        "where user_id=%s and anticip_p_meal is not null order by ts_utc", (u,))
            d = np.asarray(cur.fetchall(), dtype=float)
            cur.execute("select extract(epoch from ts_utc), cgm_mgdl from public.boost_cgm "
                        "where user_id=%s order by ts_utc", (u,))
            c = np.asarray(cur.fetchall(), dtype=float)
        if len(d) < 500 or len(c) < 500:
            continue
        t, p = d[:, 0], d[:, 1]
        ons = onsets_from(c[:, 0], c[:, 1])
        if len(ons) < 20:
            continue
        # keep one decision per five-minute bucket so repeated cycles do not weight a moment twice
        keep = np.concatenate([[True], np.diff(t) > 120])
        t, p = t[keep], p[keep]
        hour = ((t % 86400) / 3600.0).astype(int)
        day = (t // 86400).astype(int)

        for la in LOOKAHEAD_MIN:
            j = np.searchsorted(ons, t)
            nxt = np.where(j < len(ons), ons[np.clip(j, 0, len(ons) - 1)], np.inf)
            y = ((nxt - t) <= la * 60).astype(int)
            if y.sum() < 20 or y.sum() > len(y) - 20:
                continue
            # clock control: rate by hour, fitted leaving the scored day out
            clock = np.empty(len(y), dtype=float)
            for dd in np.unique(day):
                m = day == dd
                other = ~m
                if other.sum() < 100:
                    clock[m] = y.mean()
                    continue
                rate = np.zeros(24)
                for hh in range(24):
                    sel = other & (hour == hh)
                    rate[hh] = y[sel].mean() if sel.sum() >= 5 else y[other].mean()
                clock[m] = rate[hour[m]]
            rows.append(dict(user=u, lookahead=la, n=int(len(y)), events=int(y.sum()),
                             auc_shadow=auc_of(y, p), auc_clock=auc_of(y, clock),
                             auc_shadow_plus=auc_of(y, p + clock)))
            r = rows[-1]
            print(f"{u:>6} +{la:>3}min  n={r['n']:>6,} events={r['events']:>5}  "
                  f"shadow {r['auc_shadow']:.3f}  clock {r['auc_clock']:.3f}  "
                  f"delta {r['auc_shadow']-r['auc_clock']:+.3f}", flush=True)

    print("\npooled across participants (mean of per-participant AUCs)", flush=True)
    out = {"per_user": rows, "pooled": []}
    rng = np.random.default_rng(SEED)
    for la in LOOKAHEAD_MIN:
        sub = [r for r in rows if r["lookahead"] == la]
        if not sub:
            continue
        sh = np.array([r["auc_shadow"] for r in sub])
        ck = np.array([r["auc_clock"] for r in sub])
        dl = sh - ck
        boot = np.array([rng.choice(dl, len(dl), replace=True).mean() for _ in range(2000)])
        rec = dict(lookahead=la, participants=len(sub),
                   shadow=float(sh.mean()), clock=float(ck.mean()), delta=float(dl.mean()),
                   lo=float(np.percentile(boot, 2.5)), hi=float(np.percentile(boot, 97.5)),
                   n_above=int((dl > 0).sum()))
        out["pooled"].append(rec)
        print(f"+{la:>3}min  {rec['participants']} participants  shadow {rec['shadow']:.3f}  "
              f"clock {rec['clock']:.3f}  delta {rec['delta']:+.3f} "
              f"[{rec['lo']:+.3f}, {rec['hi']:+.3f}]  shadow ahead on {rec['n_above']}/{len(sub)}",
              flush=True)
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(out, open(os.path.join(here, "out", "anticipation_price.json"), "w"), indent=1)
    print("\nwrote out/anticipation_price.json")


if __name__ == "__main__":
    sys.exit(main())
