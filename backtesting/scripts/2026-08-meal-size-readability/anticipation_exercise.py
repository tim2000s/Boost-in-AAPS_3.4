#!/usr/bin/env python3
"""The anticipation shadow's other arm: does it see exercise coming?

The meal arm was priced and loses to the hour of day. The exercise arm has never been scored, and it
points at the one mechanism that separates from background in this participant's lows, a rise with
insulin committed into it followed by movement.

Movement onsets are taken from the participant's own step feed, the first cycle of a sustained lift
after a quiet period, so no announcement is needed. The control is the same as for the meal arm: an
hour-of-day rate fitted on the participant's other days, because a per-user prior over when someone
exercises is largely a statement about their week and the clock is free.

Cycles with no step feed are dropped rather than treated as stationary. A missing feed and a still
participant look identical and conflating them is how the activity share was over-stated before.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""
import json, os, sys
import numpy as np, psycopg2
from size_readability import auc_of

LOOKAHEAD_MIN = (15, 30, 60)
STEP_ACTIVE = 250          # steps in 30 min that count as movement
QUIET_MIN = 60             # a movement onset must follow this much quiet
SEED = 20260826


def main():
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("select distinct user_id from public.boost_decisions "
                    "where anticip_p_ex is not null order by 1")
        users = [r[0] for r in cur.fetchall()]
    rows = []
    for u in users:
        with conn.cursor() as cur:
            cur.execute("""select extract(epoch from ts_utc), anticip_p_ex, steps_30m
                           from public.boost_decisions
                           where user_id=%s and anticip_p_ex is not null order by ts_utc""", (u,))
            d = cur.fetchall()
        t = np.asarray([r[0] for r in d], dtype=float)
        p = np.asarray([r[1] for r in d], dtype=float)
        st = np.asarray([np.nan if r[2] is None else r[2] for r in d], dtype=float)
        ok = np.isfinite(st)
        if ok.sum() < 500:
            continue
        t, p, st = t[ok], p[ok], st[ok]
        keep = np.concatenate([[True], np.diff(t) > 120])
        t, p, st = t[keep], p[keep], st[keep]
        active = st >= STEP_ACTIVE
        onset = []
        for i in range(1, len(t)):
            if active[i] and not active[i - 1]:
                back = (t >= t[i] - QUIET_MIN * 60) & (t < t[i])
                if back.any() and not active[back].any():
                    onset.append(t[i])
        onset = np.asarray(onset)
        if len(onset) < 20:
            continue
        hour = ((t % 86400) / 3600.0).astype(int)
        day = (t // 86400).astype(int)
        for la in LOOKAHEAD_MIN:
            j = np.searchsorted(onset, t)
            nxt = np.where(j < len(onset), onset[np.clip(j, 0, len(onset) - 1)], np.inf)
            y = ((nxt - t) <= la * 60).astype(int)
            if y.sum() < 20 or y.sum() > len(y) - 20:
                continue
            clock = np.empty(len(y), dtype=float)
            for dd in np.unique(day):
                m = day == dd; other = ~m
                if other.sum() < 100:
                    clock[m] = y.mean(); continue
                rate = np.zeros(24)
                for hh in range(24):
                    sel = other & (hour == hh)
                    rate[hh] = y[sel].mean() if sel.sum() >= 5 else y[other].mean()
                clock[m] = rate[hour[m]]
            rows.append(dict(user=u, lookahead=la, n=int(len(y)), events=int(y.sum()),
                             onsets=int(len(onset)),
                             auc_shadow=auc_of(y, p), auc_clock=auc_of(y, clock)))
            r = rows[-1]
            print(f"{u:>6} +{la:>3}min  n={r['n']:>6,} onsets={r['onsets']:>4}  "
                  f"shadow {r['auc_shadow']:.3f}  clock {r['auc_clock']:.3f}  "
                  f"delta {r['auc_shadow']-r['auc_clock']:+.3f}", flush=True)

    print("\npooled across participants", flush=True)
    rng = np.random.default_rng(SEED); out = {"per_user": rows, "pooled": []}
    for la in LOOKAHEAD_MIN:
        sub = [r for r in rows if r["lookahead"] == la]
        if len(sub) < 3:
            continue
        sh = np.array([r["auc_shadow"] for r in sub]); ck = np.array([r["auc_clock"] for r in sub])
        dl = sh - ck
        boot = np.array([rng.choice(dl, len(dl), True).mean() for _ in range(2000)])
        rec = dict(lookahead=la, participants=len(sub), shadow=float(sh.mean()),
                   clock=float(ck.mean()), delta=float(dl.mean()),
                   lo=float(np.percentile(boot, 2.5)), hi=float(np.percentile(boot, 97.5)),
                   n_above=int((dl > 0).sum()))
        out["pooled"].append(rec)
        print(f"+{la:>3}min  {rec['participants']} participants  shadow {rec['shadow']:.3f}  "
              f"clock {rec['clock']:.3f}  delta {rec['delta']:+.3f} "
              f"[{rec['lo']:+.3f}, {rec['hi']:+.3f}]  ahead on {rec['n_above']}/{len(sub)}", flush=True)
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(out, open(os.path.join(here, "out", "anticipation_exercise.json"), "w"), indent=1)
    print("\nwrote out/anticipation_exercise.json")


if __name__ == "__main__":
    sys.exit(main())
