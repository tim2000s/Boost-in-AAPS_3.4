#!/usr/bin/env python3
"""If the confirm commitment were split, what would the second tranche know that the first did not?

The confirm shot is currently one decision taken at one moment, and it is 1.45 U whether the
excursion turns out to be under 30 mg/dL or over 75. Splitting it into an immediate part and a
second part released a few cycles later is only worth doing if those few cycles carry information,
so this measures exactly that: how well the trace separates the episodes that go somewhere from the
ones that do not, at the confirming cycle and at each cycle after it.

The separation is between the two ends, peak rise of 75 mg/dL or more against under 30, with the
middle dropped so the classes genuinely differ. That is the discrimination a second tranche would be
acting on.

Features are the ones a controller holds: glucose now, the rise since the confirming cycle, and the
engine's own short and long average deltas. Leave-one-out is used rather than folds because there
are 140 episodes, and the interval comes from resampling episodes.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""
import bisect, json, os, sys
import numpy as np, psycopg2
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneOut
from size_readability import auc_of

OFFSETS = (0, 5, 10, 15, 20, 30, 45)
FWD_MIN = 180
SEED = 20260827


def main():
    user = sys.argv[1] if len(sys.argv) > 1 else "tim"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 45
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"""select extract(epoch from ts_utc), accelmeal_state,
                               accelmeal_shortavgdelta, accelmeal_longavgdelta
                        from public.boost_decisions where user_id=%s
                          and accelmeal_state is not null
                          and ts_utc > now() - interval '{days} days' order by ts_utc""", (user,))
        d = cur.fetchall()
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

    eps = []
    for i in range(1, len(rows)):
        if st[i] != "CONFIRMED" or st[i - 1] == "CONFIRMED":
            continue
        t0 = dt[i]
        j = bisect.bisect_right(ts, t0) - 1
        if j < 1 or j > len(ts) - 20:
            continue
        b = bisect.bisect_right(ts, t0 + FWD_MIN * 60)
        seg = bg[j:b]
        if len(seg) < 14:
            continue
        eps.append(dict(t0=t0, j=j, bg0=float(bg[j]),
                        peak=float(seg.max() - bg[j]),
                        sad=rows[i][2], lad=rows[i][3]))
    lab = [e for e in eps if e["peak"] < 30 or e["peak"] >= 75]
    y = np.array([1 if e["peak"] >= 75 else 0 for e in lab])
    print(f"{user}: {len(eps)} confirm episodes, {len(lab)} at the ends "
          f"({int(y.sum())} large, {int((1-y).sum())} small)\n")
    rng = np.random.default_rng(SEED)
    out = []
    scores_by = {}
    scores = {}
    print(f"{'minutes after confirm':>24} {'AUC':>7} {'95% interval':>18}  what it knows")
    for off in OFFSETS:
        X, keep = [], []
        for k, e in enumerate(lab):
            m = bisect.bisect_right(ts, e["t0"] + off * 60) - 1
            if m <= e["j"] or m >= len(ts):
                if off == 0:
                    m = e["j"]
                else:
                    continue
            win = bg[e["j"]:m + 1]
            rise = float(bg[m] - e["bg0"])
            slope = float(bg[m] - bg[max(m - 1, 0)])
            X.append([e["bg0"], bg[m], rise, float(win.max() - e["bg0"]), slope,
                      float(e["sad"] or 0.0), float(e["lad"] or 0.0)])
            keep.append(k)
        if len(keep) < 40:
            continue
        Xa = np.asarray(X, dtype=float); ya = y[np.asarray(keep)]
        s = np.full(len(ya), np.nan)
        for tr, te in LeaveOneOut().split(Xa):
            lr = LogisticRegression(max_iter=2000).fit(Xa[tr], ya[tr])
            s[te] = lr.predict_proba(Xa[te])[:, 1]
        a = auc_of(ya, s)
        bs = np.array([auc_of(ya[i], s[i]) for i in
                       (rng.integers(0, len(ya), len(ya)) for _ in range(2000))])
        bs = bs[np.isfinite(bs)]
        lo, hi = np.percentile(bs, 2.5), np.percentile(bs, 97.5)
        out.append(dict(offset=off, n=int(len(ya)), auc=float(a), lo=float(lo), hi=float(hi)))
        scores_by[off] = (keep, s)
        scores[off] = (keep, s)
        note = "the confirming cycle only" if off == 0 else f"{off} min of trace after it"
        print(f"{off:>21} min {a:>7.3f} [{lo:>6.3f}, {hi:>6.3f}]  {note}", flush=True)

    # paired: the arms score the same episodes, so the difference needs its own interval
    if 0 in scores_by:
        base_k, base_s = scores_by[0]
        print("\npaired against the confirming cycle, same episodes, resampled together")
        for off, (kk, ss) in list(scores.items())[1:] if False else []:
            pass
        for off in [o for o in OFFSETS if o != 0]:
            if off not in scores_by:
                continue
            ka, sa = scores_by[off]
            common = sorted(set(ka) & set(base_k))
            if len(common) < 40:
                continue
            ia = {k: i for i, k in enumerate(ka)}; ib = {k: i for i, k in enumerate(base_k)}
            ya = np.array([y[k] for k in common])
            s1 = np.array([sa[ia[k]] for k in common])
            s0 = np.array([base_s[ib[k]] for k in common])
            d = auc_of(ya, s1) - auc_of(ya, s0)
            bs = []
            for _ in range(2000):
                idx = rng.integers(0, len(ya), len(ya))
                v = auc_of(ya[idx], s1[idx]) - auc_of(ya[idx], s0[idx])
                if np.isfinite(v):
                    bs.append(v)
            lo_, hi_ = np.percentile(bs, [2.5, 97.5])
            verdict = "distinguishable" if lo_ > 0 else "unproven"
            print(f"  +{off:>2} min: {d:+.3f} [{lo_:+.3f}, {hi_:+.3f}]  {verdict}")

    if out:
        base = out[0]["auc"]
        print(f"\ngain over the confirming cycle:")
        for r in out[1:]:
            print(f"  +{r['offset']:>2} min: {r['auc']-base:+.3f}")
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(out, open(os.path.join(here, "out", f"confirm_tranche_{user}.json"), "w"), indent=1)
    print(f"\nwrote out/confirm_tranche_{user}.json")


if __name__ == "__main__":
    sys.exit(main())
