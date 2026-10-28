#!/usr/bin/env python3
"""How much of the confirm dose should be given immediately?

The fraction was a guess. The data can narrow it, from two directions.

First, among the confirms where nothing arrived, the dose is unambiguously excess and its
relationship to the subsequent low is not confounded by a meal that needed covering. Binning those
by what was delivered at the confirming cycle says where the harm starts.

Second, a sweep: for each candidate fraction, apply the release rule's held-out decisions to the
episodes and total what would have been delivered, what withheld, and how the withholding divides
between the episodes that went nowhere and those that went somewhere. That prices the fraction
against both failure modes rather than only the hypoglycaemic one.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""
import bisect, json, os, sys
import numpy as np, psycopg2
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

FWD_MIN = 180
LOW = 70.0
BIG, SMALL = 75.0, 30.0
SEED = 20260827
FEATS = ["bg_confirm", "rise_since", "max_rise_since", "slope_now", "bg_now"]


def main():
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("select distinct user_id from public.boost_decisions "
                    "where accelmeal_state is not null order by 1")
        users = [r[0] for r in cur.fetchall()]
    eps = []
    for u in users:
        with conn.cursor() as cur:
            cur.execute("""select extract(epoch from ts_utc), accelmeal_state
                           from public.boost_decisions where user_id=%s and accelmeal_state is not null
                             and ts_utc > now() - interval '45 days' order by ts_utc""", (u,))
            d = cur.fetchall()
            cur.execute("""select extract(epoch from ts_utc), cgm_mgdl from public.boost_cgm
                           where user_id=%s and ts_utc > now() - interval '45 days' order by ts_utc""", (u,))
            c = np.asarray(cur.fetchall(), dtype=float)
            cur.execute("""select extract(epoch from ts_utc), insulin from public.boost_treatments
                           where user_id=%s and is_smb and insulin is not null
                             and ts_utc > now() - interval '45 days' order by ts_utc""", (u,))
            tr = cur.fetchall()
        if len(d) < 200 or len(c) < 200:
            continue
        seen, rows = set(), []
        for r in d:
            k = int(float(r[0]) // 60)
            if k not in seen:
                seen.add(k); rows.append(r)
        dt = np.asarray([float(r[0]) for r in rows]); st = [r[1] for r in rows]
        ts, bg = c[:, 0], c[:, 1]
        bt = np.asarray([float(r[0]) for r in tr]); bu = np.asarray([float(r[1]) for r in tr])
        for i in range(1, len(rows)):
            if st[i] != "CONFIRMED" or st[i - 1] == "CONFIRMED":
                continue
            t0 = dt[i]
            j = bisect.bisect_right(ts, t0) - 1
            m = bisect.bisect_right(ts, t0 + 10 * 60) - 1
            if j < 1 or m <= j or m >= len(ts) - 12:
                continue
            b = bisect.bisect_right(ts, t0 + FWD_MIN * 60)
            seg = bg[j:b]
            if len(seg) < 14:
                continue
            a1 = bisect.bisect_left(bt, t0 - 60); a2 = bisect.bisect_right(bt, t0 + 5 * 60)
            conf_dose = float(bu[a1:a2].sum()) if a2 > a1 else 0.0
            win = bg[j:m + 1]
            eps.append(dict(user=u, conf_dose=conf_dose, bg_confirm=float(bg[j]), bg_now=float(bg[m]),
                            rise_since=float(bg[m] - bg[j]), max_rise_since=float(win.max() - bg[j]),
                            slope_now=float(bg[m] - bg[m - 1]),
                            peak=float(seg.max() - bg[j]), low=int(seg.min() < LOW)))

    nothing = [e for e in eps if e["peak"] < SMALL]
    print(f"{len(eps)} confirm episodes; {len(nothing)} where nothing arrived (peak < {SMALL:.0f} mg/dL)\n")
    print("among those, by what was delivered at the confirming cycle:")
    dz = np.array([e["conf_dose"] for e in nothing])
    lo_ = np.array([e["low"] for e in nothing])
    edges = [0, 0.5, 1.0, 1.5, 2.0, 99]
    rng = np.random.default_rng(SEED)
    for k in range(len(edges) - 1):
        m = (dz >= edges[k]) & (dz < edges[k + 1])
        if m.sum() < 8:
            continue
        b = np.array([rng.choice(lo_[m], m.sum(), True).mean() for _ in range(4000)])
        print(f"  {edges[k]:>4.1f} to {edges[k+1] if edges[k+1]<99 else 9.9:>4.1f} U  n={m.sum():>4}  "
              f"low rate {lo_[m].mean():>5.1%}  [{np.percentile(b,2.5):>5.1%}, {np.percentile(b,97.5):>5.1%}]")

    # sweep the fraction against the held-out release rule
    lab = [e for e in eps if e["peak"] < SMALL or e["peak"] >= BIG]
    us = sorted({e["user"] for e in lab})
    X = np.array([[e[f] for f in FEATS] for e in lab], float)
    y = np.array([1 if e["peak"] >= BIG else 0 for e in lab])
    g = np.array([us.index(e["user"]) for e in lab])
    s = np.full(len(y), np.nan)
    for tr_, te_ in GroupKFold(n_splits=min(5, len(us))).split(X, y, g):
        s[te_] = LogisticRegression(max_iter=2000).fit(X[tr_], y[tr_]).predict_proba(X[te_])[:, 1]
    dose = np.array([e["conf_dose"] for e in lab])
    thr = 0.30
    rel = s > thr
    print(f"\nsweeping the immediate fraction, release rule held out, threshold {thr:.2f}")
    print(f"{'fraction':>9} {'withheld from the ones that went nowhere':>42} {'delayed on the ones that went big':>36}")
    out = []
    for f in (0.3, 0.4, 0.5, 0.6, 0.7, 1.0):
        held = dose * (1 - f)
        wasted = held[(y == 0) & ~rel].sum()
        delayed = held[(y == 1) & ~rel].sum()
        out.append(dict(fraction=f, withheld_U=float(wasted), delayed_U=float(delayed),
                        ratio=float(wasted / max(delayed, 1e-9))))
        print(f"{f:>9.1f} {wasted:>34.1f} U {delayed:>34.1f} U   ratio {wasted/max(delayed,1e-9):>4.1f}:1")
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(out, open(os.path.join(here, "out", "tranche_fraction.json"), "w"), indent=1)
    print("\nwrote out/tranche_fraction.json")


if __name__ == "__main__":
    sys.exit(main())
