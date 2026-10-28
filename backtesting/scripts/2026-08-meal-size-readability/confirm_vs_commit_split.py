#!/usr/bin/env python3
"""Where does the insulin in a meal response actually come from?

The proposal is to shrink the confirm commitment and enlarge the committed holds that follow. What
that is worth depends entirely on how the delivery already divides between the two, and nobody has
measured it: if most of an episode's insulin already arrives on committed cycles then lowering the
confirm cap barely moves anything, and if most arrives in the confirm shot then raising the
committed cap barely compensates.

Each confirm transition opens an episode. Every micro bolus in the following window is attributed to
the engine state at the moment it was delivered, using the nearest decision cycle at or before it.
Episodes are also split by what the excursion turned out to be, because the case that matters is the
one where nothing arrives.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""
import bisect, json, os, sys
import numpy as np, psycopg2

WINDOW_MIN = 90
FWD_MIN = 180
LOW = 70.0


def main():
    user = sys.argv[1] if len(sys.argv) > 1 else "tim"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 45
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"""select extract(epoch from ts_utc), accelmeal_state
                        from public.boost_decisions where user_id=%s
                          and accelmeal_state is not null
                          and ts_utc > now() - interval '{days} days' order by ts_utc""", (user,))
        d = cur.fetchall()
        cur.execute(f"""select extract(epoch from ts_utc), insulin from public.boost_treatments
                        where user_id=%s and is_smb and insulin is not null
                          and ts_utc > now() - interval '{days} days' order by ts_utc""", (user,))
        tr = cur.fetchall()
        cur.execute(f"""select extract(epoch from ts_utc), cgm_mgdl from public.boost_cgm
                        where user_id=%s and ts_utc > now() - interval '{days} days'
                        order by ts_utc""", (user,))
        c = np.asarray(cur.fetchall(), dtype=float)
    ts, bg = c[:, 0], c[:, 1]
    seen, rows = set(), []
    for r in d:
        k = int(r[0] // 60)
        if k not in seen:
            seen.add(k); rows.append(r)
    dt = np.asarray([r[0] for r in rows], dtype=float)
    st = [r[1] for r in rows]
    bt = np.asarray([r[0] for r in tr], dtype=float)
    bu = np.asarray([r[1] for r in tr], dtype=float)

    eps = []
    for i in range(1, len(rows)):
        if st[i] != "CONFIRMED" or st[i - 1] == "CONFIRMED":
            continue
        t0 = dt[i]
        j = bisect.bisect_right(ts, t0) - 1
        if j < 1 or j > len(ts) - 12:
            continue
        b = bisect.bisect_right(ts, t0 + FWD_MIN * 60)
        seg = bg[j:b]
        if len(seg) < 12:
            continue
        a1 = bisect.bisect_left(bt, t0 - 60)
        a2 = bisect.bisect_right(bt, t0 + WINDOW_MIN * 60)
        by = {"CONFIRMED": 0.0, "COMMITTED": 0.0, "other": 0.0}
        for k in range(a1, a2):
            m = bisect.bisect_right(dt, bt[k]) - 1
            s = st[m] if 0 <= m < len(st) else "other"
            by[s if s in by else "other"] += float(bu[k])
        eps.append(dict(t0=t0, confirmed=by["CONFIRMED"], committed=by["COMMITTED"],
                        other=by["other"], total=sum(by.values()),
                        peak_rise=float(seg.max() - bg[j]),
                        went_low=int(seg.min() < LOW)))
    if not eps:
        print("no episodes"); return

    def show(lbl, g):
        if not g:
            return
        tot = np.array([x["total"] for x in g])
        cf = np.array([x["confirmed"] for x in g])
        cm = np.array([x["committed"] for x in g])
        ok = tot > 0
        print(f"{lbl:>28} {len(g):>4}  total {np.median(tot):>5.2f} U  "
              f"confirm {np.median(cf):>5.2f}  committed {np.median(cm):>5.2f}  "
              f"confirm share {100*np.mean(cf[ok]/tot[ok]):>5.1f}%  "
              f"low {np.mean([x['went_low'] for x in g]):>5.1%}")

    print(f"{user}: {len(eps)} confirm episodes, insulin in the {WINDOW_MIN} min after confirm\n")
    print(f"{'group':>28} {'n':>4}  {'median totals and split':>60}")
    show("all episodes", eps)
    show("peak rise under 30 mg/dL", [x for x in eps if x["peak_rise"] < 30])
    show("peak rise 30 to 75", [x for x in eps if 30 <= x["peak_rise"] < 75])
    show("peak rise 75 or more", [x for x in eps if x["peak_rise"] >= 75])

    tot = np.array([x["total"] for x in eps]); cf = np.array([x["confirmed"] for x in eps])
    ok = tot > 0
    print(f"\nacross all episodes the confirm cycle carries "
          f"{100*cf[ok].sum()/tot[ok].sum():.1f}% of the insulin delivered in the window")
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(eps, open(os.path.join(here, "out", f"confirm_split_{user}.json"), "w"), indent=1)
    print(f"wrote out/confirm_split_{user}.json")


if __name__ == "__main__":
    sys.exit(main())
