#!/usr/bin/env python3
"""What is the trace doing at the moment the engine confirms?

The repeated report is that CONFIRMED fires on a decelerating rise with a modest delta. That has
been argued about from single events; this counts every confirm transition in the record and
describes the state at the moment of firing.

Deceleration here is the engine's own short-minus-long average delta, the same quantity the
curvature shadow uses, taken at the confirming cycle and at the cycle before it. A confirm is
counted as decelerating when that quantity has fallen between the two.

The July fast-carb work rejected deceleration as a predictor of which confirms crash, which is a
different question from whether the trigger fires on weak evidence. Both are reported: the share of
confirms that fire while decelerating, and what those confirms went on to do.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""
import bisect, json, os, sys
import numpy as np, psycopg2

FWD_MIN = 180
LOW = 70.0
MGDL_PER_MMOL = 18.018


def main():
    user = sys.argv[1] if len(sys.argv) > 1 else "tim"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 45
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"""select extract(epoch from ts_utc), accelmeal_state, accelmeal_bg,
                               accelmeal_shortavgdelta, accelmeal_longavgdelta, gs_delta,
                               iob_iob, boostv5_finaldose
                        from public.boost_decisions
                        where user_id=%s and accelmeal_state is not null
                          and ts_utc > now() - interval '{days} days'
                        order by ts_utc""", (user,))
        d = cur.fetchall()
        cur.execute(f"""select extract(epoch from ts_utc), cgm_mgdl from public.boost_cgm
                        where user_id=%s and ts_utc > now() - interval '{days} days'
                        order by ts_utc""", (user,))
        c = np.asarray(cur.fetchall(), dtype=float)
    ts, bg = c[:, 0], c[:, 1]

    # one row per decision moment; the engine logs a cycle more than once
    seen, rows = set(), []
    for r in d:
        k = int(r[0] // 60)
        if k in seen:
            continue
        seen.add(k)
        rows.append(r)

    confirms = []
    for i in range(1, len(rows)):
        prev, cur_ = rows[i - 1], rows[i]
        if cur_[1] != "CONFIRMED" or prev[1] == "CONFIRMED":
            continue
        t0 = cur_[0]
        sad, lad = cur_[3], cur_[4]
        psad, plad = prev[3], prev[4]
        if None in (sad, lad, psad, plad):
            continue
        accel_now, accel_prev = sad - lad, psad - plad
        j = bisect.bisect_right(ts, t0) - 1
        if j < 1 or j > len(ts) - 12:
            continue
        b = bisect.bisect_right(ts, t0 + FWD_MIN * 60)
        seg = bg[j:b]
        if len(seg) < 12:
            continue
        confirms.append(dict(
            t0=t0, bg=cur_[2], delta=cur_[5], sad=sad, lad=lad,
            accel_now=accel_now, accel_prev=accel_prev,
            decelerating=bool(accel_now < accel_prev),
            sad_falling=bool(psad is not None and sad < psad),
            iob=cur_[6], dose=cur_[7],
            peak_rise=float(seg.max() - bg[j]), went_low=int(seg.min() < LOW)))

    n = len(confirms)
    if n == 0:
        print("no confirm transitions found"); return
    dec = [c_ for c_ in confirms if c_["decelerating"]]
    sadf = [c_ for c_ in confirms if c_["sad_falling"]]
    print(f"{user}: {n} confirm transitions in {days} days\n")
    print(f"  firing while acceleration is falling : {len(dec):>4}  {100*len(dec)/n:>5.1f}%")
    print(f"  firing while shortAvgDelta is falling: {len(sadf):>4}  {100*len(sadf)/n:>5.1f}%")

    def q(g, k):
        v = [x[k] for x in g if x[k] is not None]
        return np.percentile(v, [25, 50, 75]) if v else [np.nan] * 3

    print(f"\n{'group':>26} {'n':>4}  {'shortAvgDelta (mmol/5min)':>28}  {'peak rise':>10}  {'low rate':>9}")
    for lbl, g in (("all confirms", confirms), ("acceleration falling", dec),
                   ("acceleration rising", [c_ for c_ in confirms if not c_["decelerating"]])):
        if not g:
            continue
        s = q(g, "sad")
        print(f"{lbl:>26} {len(g):>4}  "
              f"{s[0]/MGDL_PER_MMOL:>7.2f} {s[1]/MGDL_PER_MMOL:>7.2f} {s[2]/MGDL_PER_MMOL:>7.2f}  "
              f"{np.median([x['peak_rise'] for x in g]):>10.0f}  "
              f"{np.mean([x['went_low'] for x in g]):>8.1%}")

    print(f"\nshortAvgDelta at the confirming cycle, mmol/L per 5 min:")
    s = q(confirms, "sad")
    print(f"  quartiles {s[0]/MGDL_PER_MMOL:.2f} / {s[1]/MGDL_PER_MMOL:.2f} / {s[2]/MGDL_PER_MMOL:.2f}")
    weak = [c_ for c_ in confirms if c_["sad"] is not None and c_["sad"] / MGDL_PER_MMOL < 0.8]
    print(f"  confirms firing below 0.8 mmol/5min: {len(weak)} ({100*len(weak)/n:.1f}%), "
          f"median peak rise {np.median([x['peak_rise'] for x in weak]):.0f} mg/dL, "
          f"low rate {np.mean([x['went_low'] for x in weak]):.1%}" if weak else "  none below 0.8")

    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(dict(user=user, days=days, n=n,
                   decelerating=len(dec), sad_falling=len(sadf),
                   confirms=[{k: (None if v is None else float(v)) for k, v in c_.items()}
                             for c_ in confirms]),
              open(os.path.join(here, "out", f"confirm_trigger_{user}.json"), "w"), indent=1)
    print(f"\nwrote out/confirm_trigger_{user}.json")


if __name__ == "__main__":
    sys.exit(main())
