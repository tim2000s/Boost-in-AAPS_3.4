#!/usr/bin/env python3
"""Does a consequence prior add anything to what the loop already does with glucose?

Onset glucose and the hour separate consequential rises from unconsequential ones. That is only a
lever if the loop is not already acting on the same information, and it acts on glucose constantly,
through ISF, through target, and through the dose calculation itself. So the question is not whether
the prior predicts, which is settled, but whether it predicts anything the loop's own output does
not already encode.

Two baselines, both taken from the engine's own record at the onset. Its forward projection,
eventualBG, is what it believes will happen. Its delivered insulin over the following thirty minutes
is what it did about it. If either already tracks the eventual excursion, a prior built from onset
glucose and the clock is redundant.

The dose baseline carries a confound that cannot be removed here and should not be glossed: insulin
delivered changes the excursion it is being scored against, so a flat relationship between dose and
outcome is ambiguous between a loop that cannot see the difference and a loop that sees it and
successfully cancels it. The projection baseline does not have that problem, which is why both are
reported.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""

import bisect
import json
import os
import sys

import numpy as np
import psycopg2
from sklearn.model_selection import GroupKFold

import lightgbm as lgb
from extract_meals import RESCUE_BG
from size_readability import LGB, SEED, auc_of

MIN_RISE = 25.0
FWD_MIN = 180
DOSE_WINDOW_MIN = 30
THRESHOLD = 60.0


def main():
    conn = psycopg2.connect("dbname=oref")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("""select user_id from public.boost_decisions
                       where sug_eventualbg is not null and ts_utc > now() - interval '60 days'
                       group by 1 having count(*) > 3000 order by count(*) desc""")
        users = [r[0] for r in cur.fetchall()]
    print(f"{len(users)} participants with an engine record\n", flush=True)

    rows = []
    for u in users:
        with conn.cursor() as cur:
            cur.execute("select extract(epoch from ts_utc), cgm_mgdl from public.boost_cgm "
                        "where user_id=%s order by ts_utc", (u,))
            c = np.asarray(cur.fetchall(), dtype=float)
            cur.execute("select extract(epoch from ts_utc), sug_eventualbg, iob_iob "
                        "from public.boost_decisions where user_id=%s and sug_eventualbg is not null "
                        "order by ts_utc", (u,))
            dd = np.asarray(cur.fetchall(), dtype=float)
            cur.execute("select extract(epoch from ts_utc), insulin from public.boost_treatments "
                        "where user_id=%s and insulin is not null and is_smb order by ts_utc", (u,))
            tr = cur.fetchall()
        if len(c) < 500 or len(dd) < 500:
            continue
        ts, bg = c[:, 0], c[:, 1]
        dt, ev, iob = dd[:, 0], dd[:, 1], dd[:, 2]
        bt = np.asarray([r[0] for r in tr], dtype=float) if tr else np.empty(0)
        bu = np.asarray([r[1] for r in tr], dtype=float) if tr else np.empty(0)
        i = 4
        while i < len(ts) - 40:
            w = bisect.bisect_right(ts, ts[i] + 30 * 60)
            if w - i >= 4 and bg[i:w].max() - bg[i] >= MIN_RISE and bg[i] > RESCUE_BG:
                t0 = ts[i]
                b = bisect.bisect_right(ts, t0 + FWD_MIN * 60)
                b2 = bisect.bisect_right(ts, t0 + 120 * 60)
                seg, seg2 = bg[i:b], bg[i:b2]
                k = bisect.bisect_left(dt, t0)
                if len(seg) >= 12 and k < len(dt) and dt[k] - t0 < 600:
                    a1 = bisect.bisect_left(bt, t0)
                    a2 = bisect.bisect_right(bt, t0 + DOSE_WINDOW_MIN * 60)
                    hour = (t0 % 86400) / 3600.0
                    rows.append(dict(user=u, onset_bg=float(bg[i]),
                                     tod_sin=float(np.sin(2 * np.pi * hour / 24)),
                                     tod_cos=float(np.cos(2 * np.pi * hour / 24)),
                                     eventualbg=float(ev[k]), iob=float(iob[k]),
                                     dose30=float(bu[a1:a2].sum()) if a2 > a1 else 0.0,
                                     y=int(seg.max() - bg[i] >= THRESHOLD),
                                     y_abs=int(seg2.max() > 180.0) if len(seg2) >= 8 else None))
                i = w + 12
                continue
            i += 1
    rows = [r for r in rows if r.get("y_abs") is not None]
    print(f"{len(rows):,} rise onsets from {len({r['user'] for r in rows})} participants", flush=True)
    users = sorted({r["user"] for r in rows})
    g = np.asarray([users.index(r["user"]) for r in rows])

    ARMS = {
        "loop projection (eventualBG)":             ["eventualbg"],
        "loop projection and IOB":                  ["eventualbg", "iob"],
        "loop delivery (insulin, 30 min)":          ["dose30"],
        "loop projection, IOB and delivery":        ["eventualbg", "iob", "dose30"],
        "onset glucose and the clock":              ["onset_bg", "tod_sin", "tod_cos"],
        "loop record plus onset glucose and clock": ["eventualbg", "iob", "dose30",
                                                     "onset_bg", "tod_sin", "tod_cos"],
    }
    here = os.path.dirname(os.path.abspath(__file__))
    for target, lbl in (("y", "peak rise >= 60 mg/dL"), ("y_abs", "glucose exceeds 180 mg/dL")):
        y = np.array([r[target] for r in rows])
        print(f"\n=== {lbl}, base rate {y.mean():.3f} ===", flush=True)
        res = []
        for name, cols in ARMS.items():
            X = np.array([[r[c] for c in cols] for r in rows], dtype=np.float64)
            sc = np.full(len(y), np.nan)
            for tr_i, te_i in GroupKFold(n_splits=5).split(X, y, g):
                m = lgb.LGBMClassifier(random_state=SEED, **LGB)
                m.fit(X[tr_i], y[tr_i])
                sc[te_i] = m.predict_proba(X[te_i])[:, 1]
            a = auc_of(y, sc)
            res.append(dict(arm=name, auc=a))
            print(f"{name:>42}  AUC {a:.3f}", flush=True)
        json.dump(dict(target=target, n=len(rows), base_rate=float(y.mean()), arms=res),
                  open(os.path.join(here, "out", f"prior_vs_loop_{target}.json"), "w"), indent=1)
    print("\nwrote out/prior_vs_loop_*.json")


if __name__ == "__main__":
    sys.exit(main())
