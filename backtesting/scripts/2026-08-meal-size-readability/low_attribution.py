#!/usr/bin/env python3
"""Where do this participant's lows come from?

Two candidate mechanisms are on the table: responding too hard to fast carbohydrate, and
post-prandial exercise that nobody announced. They leave different traces.

A fast-carbohydrate over-response is a low preceded by a sharp rise and a large delivery into it,
with the low arriving while that insulin is still active. Post-prandial exercise is a low preceded
by movement, in the window after a rise, with delivery that need not be unusual at all.

Every low episode is classified against both, on the participant's own record, and the residue is
reported rather than forced into one of the two. Steps and heart rate are read at their own cadence
from the decision stream; where a feed was not reporting the episode is counted as unclassifiable
rather than as absence of exercise, because a missing step feed and a stationary participant look
identical and conflating them is how the activity share got over-stated before.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""

import bisect
import json
import os
import sys

import numpy as np
import psycopg2

LOW = 70.0
SEVERE = 54.0
LOOKBACK_MIN = 150
RISE_WINDOW_MIN = 120
FAST_RISE_MGDL = 45.0        # a sharp rise in the preceding window
STEP_ACTIVE = 250            # steps in 30 min that count as movement
HR_LIFT_BPM = 12.0           # over the participant's learned daytime baseline
EPISODE_GAP_S = 60 * 60


def main():
    user = sys.argv[1] if len(sys.argv) > 1 else "tim"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    conn = psycopg2.connect("dbname=oref")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("select extract(epoch from ts_utc), cgm_mgdl from public.boost_cgm "
                    "where user_id=%s and ts_utc > now() - interval '%s days' order by ts_utc",
                    (user, days))
        c = np.asarray(cur.fetchall(), dtype=float)
        cur.execute("""select extract(epoch from ts_utc), steps_30m, hr_bpm_avg15m,
                              hr_learned_daytime_bpm, iob_iob
                       from public.boost_decisions
                       where user_id=%%s and ts_utc > now() - interval '%s days'
                       order by ts_utc""" % days, (user,))
        d = cur.fetchall()
        cur.execute("select extract(epoch from ts_utc), insulin from public.boost_treatments "
                    "where user_id=%s and is_smb and insulin is not null "
                    "and ts_utc > now() - interval '%s days' order by ts_utc", (user, days))
        tr = cur.fetchall()
    ts, bg = c[:, 0], c[:, 1]
    dt = np.asarray([r[0] for r in d], dtype=float)
    st = np.asarray([np.nan if r[1] is None else r[1] for r in d], dtype=float)
    hr = np.asarray([np.nan if r[2] is None else r[2] for r in d], dtype=float)
    hrb = np.asarray([np.nan if r[3] is None else r[3] for r in d], dtype=float)
    iob = np.asarray([np.nan if r[4] is None else r[4] for r in d], dtype=float)
    bt = np.asarray([r[0] for r in tr], dtype=float)
    bu = np.asarray([r[1] for r in tr], dtype=float)

    # low episodes
    eps, i = [], 0
    while i < len(ts):
        if bg[i] < LOW:
            j = i
            while j + 1 < len(ts) and (ts[j + 1] - ts[j] < EPISODE_GAP_S) and bg[j + 1] < LOW + 10:
                j += 1
            eps.append((ts[i], float(bg[i:j + 1].min())))
            k = bisect.bisect_right(ts, ts[j] + EPISODE_GAP_S)
            i = max(k, j + 1)
        else:
            i += 1

    rows = []
    for t0, nadir in eps:
        a = bisect.bisect_left(ts, t0 - LOOKBACK_MIN * 60)
        b = bisect.bisect_right(ts, t0)
        if b - a < 12:
            continue
        pre = bg[a:b]
        rise = float(pre.max() - pre.min())
        peak_i = a + int(np.argmax(pre))
        mins_since_peak = (t0 - ts[peak_i]) / 60.0
        i1 = bisect.bisect_left(bt, t0 - RISE_WINDOW_MIN * 60)
        i2 = bisect.bisect_right(bt, t0)
        dose = float(bu[i1:i2].sum()) if i2 > i1 else 0.0
        k1 = bisect.bisect_left(dt, t0 - 45 * 60)
        k2 = bisect.bisect_right(dt, t0)
        seg_st = st[k1:k2]
        seg_hr, seg_hb = hr[k1:k2], hrb[k1:k2]
        steps_known = np.isfinite(seg_st).any()
        hr_known = np.isfinite(seg_hr).any() and np.isfinite(seg_hb).any()
        moved = bool(steps_known and np.nanmax(seg_st) >= STEP_ACTIVE)
        hr_up = bool(hr_known and (np.nanmax(seg_hr) - np.nanmedian(seg_hb)) >= HR_LIFT_BPM)
        rows.append(dict(t0=t0, nadir=nadir, rise=rise, mins_since_peak=mins_since_peak,
                         dose=dose, moved=moved, hr_up=hr_up,
                         sensed=bool(steps_known or hr_known),
                         iob=float(np.nanmax(iob[k1:k2])) if k2 > k1 and np.isfinite(iob[k1:k2]).any() else np.nan))

    n = len(rows)
    fastcarb = [r for r in rows if r["rise"] >= FAST_RISE_MGDL and r["dose"] > 0
                and r["mins_since_peak"] <= 120]
    exercise = [r for r in rows if (r["moved"] or r["hr_up"])]
    both = [r for r in rows if r in fastcarb and r in exercise]
    unsensed = [r for r in rows if not r["sensed"]]
    neither = [r for r in rows if r not in fastcarb and r not in exercise and r["sensed"]]

    print(f"{user}: {n} low episodes in {days} days, {len([r for r in rows if r['nadir'] < SEVERE])} "
          f"below {SEVERE:.0f}\n", flush=True)
    def line(lbl, g):
        if not g:
            print(f"{lbl:>34}  {0:>4} ")
            return
        print(f"{lbl:>34}  {len(g):>4}  {100*len(g)/n:>5.1f}%   "
              f"median rise {np.median([r['rise'] for r in g]):>5.0f} mg/dL, "
              f"insulin 2h {np.median([r['dose'] for r in g]):>4.2f} U, "
              f"nadir {np.median([r['nadir'] for r in g]):>3.0f}", flush=True)
    line("after a sharp rise with insulin", fastcarb)
    line("with movement or HR lift", exercise)
    line("both", both)
    line("neither, and sensing present", neither)
    line("sensing absent, unclassifiable", unsensed)

    # matched control: the same criteria applied at times that did NOT lead to a low, so that a
    # criterion which fires on two thirds of ordinary afternoons is not credited with the lows.
    rng = np.random.default_rng(20260826)
    low_t = np.array([r["t0"] for r in rows]) if rows else np.empty(0)
    ctrl, tries = [], 0
    while len(ctrl) < 1000 and tries < 20000:
        tries += 1
        t0 = float(rng.uniform(ts[0] + LOOKBACK_MIN * 60, ts[-1] - 3600))
        if len(low_t) and np.min(np.abs(low_t - t0)) < 3 * 3600:
            continue
        a = bisect.bisect_left(ts, t0 - LOOKBACK_MIN * 60); b = bisect.bisect_right(ts, t0)
        if b - a < 12:
            continue
        pre = bg[a:b]
        i1 = bisect.bisect_left(bt, t0 - RISE_WINDOW_MIN * 60); i2 = bisect.bisect_right(bt, t0)
        k1 = bisect.bisect_left(dt, t0 - 45 * 60); k2 = bisect.bisect_right(dt, t0)
        seg_st, seg_hr, seg_hb = st[k1:k2], hr[k1:k2], hrb[k1:k2]
        sk = np.isfinite(seg_st).any(); hk = np.isfinite(seg_hr).any() and np.isfinite(seg_hb).any()
        ctrl.append(dict(rise=float(pre.max() - pre.min()),
                         dose=float(bu[i1:i2].sum()) if i2 > i1 else 0.0,
                         moved=bool(sk and np.nanmax(seg_st) >= STEP_ACTIVE),
                         hr_up=bool(hk and (np.nanmax(seg_hr) - np.nanmedian(seg_hb)) >= HR_LIFT_BPM),
                         sensed=bool(sk or hk),
                         mins_since_peak=(t0 - ts[a + int(np.argmax(pre))]) / 60.0))
    cf = [r for r in ctrl if r["rise"] >= FAST_RISE_MGDL and r["dose"] > 0 and r["mins_since_peak"] <= 120]
    ce = [r for r in ctrl if r["moved"] or r["hr_up"]]
    cb = [r for r in ctrl if r in cf and r in ce]
    print(f"\nmatched control, {len(ctrl)} times at least 3 h from any low", flush=True)
    print(f"{'after a sharp rise with insulin':>34}  {len(cf):>4}  {100*len(cf)/len(ctrl):>5.1f}%", flush=True)
    print(f"{'with movement or HR lift':>34}  {len(ce):>4}  {100*len(ce)/len(ctrl):>5.1f}%", flush=True)
    print(f"{'both':>34}  {len(cb):>4}  {100*len(cb)/len(ctrl):>5.1f}%", flush=True)
    def lift_ci(k_low, k_ctl, nb=4000):
        """Bootstrap the difference in proportions, resampling episodes and control times."""
        a = np.zeros(n); a[:k_low] = 1
        b = np.zeros(len(ctrl)); b[:k_ctl] = 1
        v = np.array([rng.choice(a, n, True).mean() - rng.choice(b, len(b), True).mean()
                      for _ in range(nb)]) * 100
        return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))

    print("\nlift over control, with 95% intervals", flush=True)
    for lbl, gl, gc in (("after a sharp rise with insulin", fastcarb, cf),
                        ("with movement or HR lift", exercise, ce),
                        ("both together", both, cb)):
        d = 100 * len(gl) / n - 100 * len(gc) / len(ctrl)
        lo, hi = lift_ci(len(gl), len(gc))
        verdict = "distinguishable" if lo > 0 else "unproven"
        print(f"{lbl:>34}  {d:>+6.1f} pp  [{lo:>+5.1f}, {hi:>+5.1f}]  {verdict}", flush=True)

    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(dict(user=user, days=days, n=n,
                   fastcarb=len(fastcarb), exercise=len(exercise), both=len(both),
                   neither=len(neither), unsensed=len(unsensed)),
              open(os.path.join(here, "out", f"low_attribution_{user}.json"), "w"), indent=1)
    print(f"\nwrote out/low_attribution_{user}.json")


if __name__ == "__main__":
    sys.exit(main())
