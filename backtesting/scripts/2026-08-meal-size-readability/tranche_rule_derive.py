#!/usr/bin/env python3
"""Derive the second-tranche release rule across the population, then see what varies by person.

The rule decides, ten minutes after a confirm, whether the held half of the commitment is released.
Fitting it on one participant and scoring the same participant, as the first pass did, tells you
nothing about whether it would work on anyone else.

The population here is the eleven participants running the engine rather than the observational
corpus, because a confirm is an engine event and the corpus has no equivalent. The confirm fires a
median of 29 minutes into a rise, so a corpus stand-in would have to be re-extracted at matched
horizons; that is worth doing later for scale, not for the first derivation.

Participants are held out as folds, so every score is produced by a rule that never saw that person.
A logistic is used because the shipping form has to be four or five coefficients on a phone.

The last section is what auto-config would need: how much the per-person optimum differs from the
population rule, which decides whether personalisation is a threshold shift or a refit.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""
import bisect, json, os, sys
import numpy as np, psycopg2
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from size_readability import auc_of

OFFSET_MIN = 10
FWD_MIN = 180
BIG, SMALL = 75.0, 30.0
FEATS = ["bg_confirm", "rise_since", "max_rise_since", "slope_now", "bg_now"]
SEED = 20260827


def load():
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("select distinct user_id from public.boost_decisions "
                    "where accelmeal_state is not null order by 1")
        users = [r[0] for r in cur.fetchall()]
    eps = []
    for u in users:
        with conn.cursor() as cur:
            cur.execute("""select extract(epoch from ts_utc), accelmeal_state
                           from public.boost_decisions where user_id=%s
                             and accelmeal_state is not null
                             and ts_utc > now() - interval '45 days' order by ts_utc""", (u,))
            d = cur.fetchall()
            cur.execute("""select extract(epoch from ts_utc), cgm_mgdl from public.boost_cgm
                           where user_id=%s and ts_utc > now() - interval '45 days'
                           order by ts_utc""", (u,))
            c = np.asarray(cur.fetchall(), dtype=float)
        if len(d) < 200 or len(c) < 200:
            continue
        seen, rows = set(), []
        for r in d:
            k = int(r[0] // 60)
            if k not in seen:
                seen.add(k); rows.append(r)
        dt = np.asarray([float(r[0]) for r in rows], dtype=float)
        st = [r[1] for r in rows]
        ts, bg = c[:, 0], c[:, 1]
        for i in range(1, len(rows)):
            if st[i] != "CONFIRMED" or st[i - 1] == "CONFIRMED":
                continue
            t0 = dt[i]
            j = bisect.bisect_right(ts, t0) - 1
            m = bisect.bisect_right(ts, t0 + OFFSET_MIN * 60) - 1
            if j < 1 or m <= j or m >= len(ts) - 12:
                continue
            b = bisect.bisect_right(ts, t0 + FWD_MIN * 60)
            seg = bg[j:b]
            if len(seg) < 14:
                continue
            win = bg[j:m + 1]
            eps.append(dict(user=u, bg_confirm=float(bg[j]), bg_now=float(bg[m]),
                            rise_since=float(bg[m] - bg[j]),
                            max_rise_since=float(win.max() - bg[j]),
                            slope_now=float(bg[m] - bg[m - 1]),
                            peak=float(seg.max() - bg[j])))
    return eps


def main():
    eps = load()
    lab = [e for e in eps if e["peak"] < SMALL or e["peak"] >= BIG]
    users = sorted({e["user"] for e in lab})
    X = np.array([[e[f] for f in FEATS] for e in lab], dtype=float)
    y = np.array([1 if e["peak"] >= BIG else 0 for e in lab])
    g = np.array([users.index(e["user"]) for e in lab])
    print(f"{len(eps)} confirm episodes across {len({e['user'] for e in eps})} participants; "
          f"{len(lab)} at the ends ({int(y.sum())} large, {int((1-y).sum())} small)\n")

    s = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=min(5, len(users))).split(X, y, g):
        s[te] = LogisticRegression(max_iter=2000).fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    rng = np.random.default_rng(SEED)
    a = auc_of(y, s)
    bs = np.array([auc_of(y[i], s[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(2000))])
    bs = bs[np.isfinite(bs)]
    print(f"population rule, participants held out: AUC {a:.3f} "
          f"[{np.percentile(bs,2.5):.3f}, {np.percentile(bs,97.5):.3f}]")

    full = LogisticRegression(max_iter=2000).fit(X, y)
    print(f"\nshipping form, p = sigmoid({full.intercept_[0]:+.5f} "
          + " ".join(f"{c:+.6f}*{f}" for c, f in zip(full.coef_[0], FEATS)) + ")")

    print(f"\noperating points on the held-out scores")
    small_m, big_m = y == 0, y == 1
    for thr in (0.20, 0.30, 0.40, 0.50):
        withheld = s <= thr
        print(f"  release when p>{thr:.2f}: withhold on {100*(withheld&small_m).sum()/small_m.sum():>5.1f}% "
              f"of the {small_m.sum()} that go nowhere, "
              f"{100*(withheld&big_m).sum()/big_m.sum():>5.1f}% of the {big_m.sum()} that go big")

    print(f"\nper participant, on the held-out score")
    rows = []
    for u in users:
        m = np.array([e["user"] == u for e in lab])
        if m.sum() < 15 or len(set(y[m])) < 2:
            continue
        au = auc_of(y[m], s[m])
        best = max(((t, ((s[m] <= t) & (y[m] == 0)).sum() / max((y[m] == 0).sum(), 1)
                     - ((s[m] <= t) & (y[m] == 1)).sum() / max((y[m] == 1).sum(), 1))
                    for t in np.arange(0.10, 0.70, 0.05)), key=lambda x: x[1])
        rows.append(dict(user=u, n=int(m.sum()), auc=float(au), best_threshold=float(best[0]),
                         youden=float(best[1]), base_rate=float(y[m].mean())))
        print(f"  {u:>6}  n={m.sum():>4}  AUC {au:>5.3f}  best threshold {best[0]:.2f}  "
              f"large share {y[m].mean():>5.1%}")
    if rows:
        t = np.array([r["best_threshold"] for r in rows])
        print(f"\nbest threshold varies {t.min():.2f} to {t.max():.2f} across participants, "
              f"median {np.median(t):.2f}")
        br = np.array([r["base_rate"] for r in rows])
        if len(rows) > 2:
            print(f"correlation between a participant's large-share and their best threshold: "
                  f"{np.corrcoef(br, t)[0,1]:+.2f}")
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(dict(auc=float(a), coef=dict(zip(FEATS, [float(c) for c in full.coef_[0]])),
                   intercept=float(full.intercept_[0]), per_user=rows),
              open(os.path.join(here, "out", "tranche_rule.json"), "w"), indent=1)
    print("\nwrote out/tranche_rule.json")


if __name__ == "__main__":
    sys.exit(main())
