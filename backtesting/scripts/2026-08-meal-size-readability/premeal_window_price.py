#!/usr/bin/env python3
"""Does the learned pre-meal window actually precede a meal?

The window has been logging "V6 pre-meal WOULD apply" without dosing since it was built, which is
exactly the banked counterfactual it was put in shadow to produce. Nobody has scored it.

The question is its precision. When the window opens, does a rise follow while it is still open or
shortly after? Against that, how often does a rise follow an equivalent stretch of time chosen at
random, because a window that covers a fifth of the day will contain meals whether or not it knows
anything.

A rise onset is built from the participant's own glucose as elsewhere in this work, so nothing turns
on announcements. Windows are collapsed into episodes, since the tag fires on every cycle the window
is open and counting cycles would score one window many times.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""
import bisect, json, os, sys
import numpy as np, psycopg2
from extract_meals import RESCUE_BG

MIN_RISE = 25.0
GAP_S = 45 * 60
CREDIT_AFTER_MIN = 90     # a rise this soon after the window opens counts as anticipated
SEED = 20260826


def onsets_from(ts, bg):
    out, i = [], 4
    while i < len(ts) - 40:
        w = bisect.bisect_right(ts, ts[i] + 30 * 60)
        if w - i >= 4 and bg[i:w].max() - bg[i] >= MIN_RISE and bg[i] > RESCUE_BG:
            out.append(ts[i]); i = w + 12; continue
        i += 1
    return np.asarray(out)


def episodes(times):
    if len(times) == 0:
        return np.empty(0)
    t = np.sort(times); keep = [t[0]]
    for a, b in zip(t[:-1], t[1:]):
        if b - a > GAP_S:
            keep.append(b)
    return np.asarray(keep)


def main():
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("""select user_id from public.boost_decisions
                       where reason_text ~* 'pre.?meal' and ts_utc > now() - interval '45 days'
                       group by 1 having count(*) > 300 order by count(*) desc""")
        users = [r[0] for r in cur.fetchall()]
    rng = np.random.default_rng(SEED)
    rows = []
    for u in users:
        with conn.cursor() as cur:
            cur.execute("""select extract(epoch from ts_utc) from public.boost_decisions
                           where user_id=%s and reason_text ~* 'V6 pre-meal (WOULD|ACTIVE)'
                             and ts_utc > now() - interval '45 days' order by ts_utc""", (u,))
            wt = np.asarray([r[0] for r in cur.fetchall()], dtype=float)
            cur.execute("""select extract(epoch from ts_utc), cgm_mgdl from public.boost_cgm
                           where user_id=%s and ts_utc > now() - interval '45 days'
                           order by ts_utc""", (u,))
            c = np.asarray(cur.fetchall(), dtype=float)
            cur.execute("""select count(*) from public.boost_decisions
                           where user_id=%s and ts_utc > now() - interval '45 days'""", (u,))
            total_cycles = cur.fetchone()[0]
        if len(wt) < 50 or len(c) < 500:
            continue
        ts, bg = c[:, 0], c[:, 1]
        ons = onsets_from(ts, bg)
        if len(ons) < 20:
            continue
        wins = episodes(wt)
        hit = sum(1 for w in wins if ((ons >= w) & (ons <= w + CREDIT_AFTER_MIN * 60)).any())
        # control: same number of windows at random times, same crediting rule
        lo, hi = ts[0], ts[-1] - CREDIT_AFTER_MIN * 60
        ctrl_hits = []
        for _ in range(200):
            r = rng.uniform(lo, hi, len(wins))
            ctrl_hits.append(sum(1 for w in r if ((ons >= w) & (ons <= w + CREDIT_AFTER_MIN * 60)).any()))
        ctrl = float(np.mean(ctrl_hits)) / len(wins)
        prec = hit / len(wins)
        share = len(wt) / max(total_cycles, 1)
        rows.append(dict(user=u, windows=int(len(wins)), precision=prec, control=ctrl,
                         lift=100.0 * (prec - ctrl), day_share=share, onsets=int(len(ons))))
        r = rows[-1]
        print(f"{u:>6}  {r['windows']:>4} windows  precede a rise {prec:>5.1%}  "
              f"control {ctrl:>5.1%}  lift {r['lift']:>+5.1f}pp  "
              f"window covers {share:>5.1%} of cycles", flush=True)

    if rows:
        d = np.array([r["lift"] for r in rows])   # already in percentage points
        boot = np.array([rng.choice(d, len(d), True).mean() for _ in range(4000)])
        lo_, hi_ = np.percentile(boot, 2.5), np.percentile(boot, 97.5)
        print(f"\npooled over {len(rows)} participants: lift {d.mean():+.1f} pp "
              f"[{lo_:+.1f}, {hi_:+.1f}]  "
              f"{'distinguishable' if lo_ > 0 else 'unproven'}", flush=True)
        print(f"mean precision {np.mean([r['precision'] for r in rows]):.1%}, "
              f"mean control {np.mean([r['control'] for r in rows]):.1%}, "
              f"window covers {np.mean([r['day_share'] for r in rows]):.1%} of cycles", flush=True)
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(rows, open(os.path.join(here, "out", "premeal_window_price.json"), "w"), indent=1)
    print("\nwrote out/premeal_window_price.json")


if __name__ == "__main__":
    sys.exit(main())
