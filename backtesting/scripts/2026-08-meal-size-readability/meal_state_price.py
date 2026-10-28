#!/usr/bin/env python3
"""Does the meal state ladder select for the excursions that warrant escalation?

The ladder exists to decide when to commit insulin. Its stages express rising confidence that a
meal is happening, and the dose ceiling rises with them. Whether that is any good is a question
about selection: an episode the ladder escalates should turn out larger than one it does not, and
the further it escalates the larger the excursion should be.

Episodes are built from the state stream itself, a run of cycles beginning when the state first
leaves IDLE and ending when it returns to IDLE or RECOVERING for a sustained period. Each episode
is labelled with the highest state it reached, and scored against what the glucose actually did
from the moment the episode began: the peak rise over the starting value within three hours, and
whether the trace subsequently dropped below 70.

The comparison that matters is not whether CONFIRMED episodes are larger than IDLE, which is
circular, but whether escalating past OBSERVING selects for anything. OBSERVING is the stage that
has already decided a rise is under way; CONFIRMED is the stage that decides it is worth a large
dose. If those two look the same downstream, the ladder is spending its largest dose on a
distinction it cannot make.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""

import bisect
import json
import os
import sys

import numpy as np
import psycopg2

RANK = {"IDLE": 0, "OBSERVING": 1, "CONFIRMED": 2, "COMMITTED": 3, "RECOVERING": 0}
FWD_MIN = 180
LOW_MGDL = 70.0
GAP_S = 45 * 60
SEED = 20260825


def episodes_of(t, st):
    """Runs of non-IDLE state, split on a sustained return to IDLE or RECOVERING."""
    out, cur = [], None
    for i in range(len(t)):
        active = st[i] in ("OBSERVING", "CONFIRMED", "COMMITTED")
        if active:
            if cur is None or t[i] - cur["last"] > GAP_S:
                if cur is not None:
                    out.append(cur)
                cur = dict(start=t[i], last=t[i], top=RANK[st[i]])
                if RANK[st[i]] >= 2:
                    cur["esc_min"] = 0.0
            else:
                cur["last"] = t[i]
                cur["top"] = max(cur["top"], RANK[st[i]])
                if RANK[st[i]] >= 2 and "esc_min" not in cur:
                    cur["esc_min"] = (t[i] - cur["start"]) / 60.0
    if cur is not None:
        out.append(cur)
    return out


def main():
    conn = psycopg2.connect("dbname=oref")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("select distinct user_id from public.boost_decisions "
                    "where accelmeal_state is not null order by 1")
        users = [r[0] for r in cur.fetchall()]

    rows = []
    for u in users:
        with conn.cursor() as cur:
            cur.execute("select extract(epoch from ts_utc), accelmeal_state from public.boost_decisions "
                        "where user_id=%s and accelmeal_state is not null order by ts_utc", (u,))
            d = cur.fetchall()
            cur.execute("select extract(epoch from ts_utc), cgm_mgdl from public.boost_cgm "
                        "where user_id=%s order by ts_utc", (u,))
            c = np.asarray(cur.fetchall(), dtype=float)
        if len(d) < 500 or len(c) < 500:
            continue
        t = np.asarray([r[0] for r in d], dtype=float)
        st = [r[1] for r in d]
        ts, bg = c[:, 0], c[:, 1]
        for ep in episodes_of(t, st):
            pass
        for ep in episodes_of(t, st):
            i = bisect.bisect_right(ts, ep["start"]) - 1
            if i < 1 or i > len(ts) - 12:
                continue
            b = bisect.bisect_right(ts, ep["start"] + FWD_MIN * 60)
            seg = bg[i:b]
            if len(seg) < 12:
                continue
            k15 = bisect.bisect_right(ts, ep["start"] + 15 * 60)
            r15 = float(bg[i:k15].max() - bg[i]) if k15 > i else 0.0
            rows.append(dict(user=u, top=ep["top"], start_bg=float(bg[i]), rise15=r15,
                             esc_min=ep.get("esc_min", float("nan")),
                             peak_rise=float(seg.max() - bg[i]),
                             went_low=int(seg.min() < LOW_MGDL),
                             dur_min=(ep["last"] - ep["start"]) / 60.0))
    print(f"{len(rows):,} episodes from {len({r['user'] for r in rows})} participants\n", flush=True)

    name = {1: "OBSERVING only", 2: "reached CONFIRMED", 3: "reached COMMITTED"}
    rng = np.random.default_rng(SEED)

    def boot_ci(vals, fn=np.mean, n=2000):
        v = np.asarray(vals, dtype=float)
        if len(v) < 5:
            return (np.nan, np.nan)
        b = np.array([fn(rng.choice(v, len(v), replace=True)) for _ in range(n)])
        return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))

    out = {"groups": [], "per_user": []}
    print(f"{'group':>18} {'n':>6} {'start BG':>9} {'peak rise':>11} {'95% CI':>16} "
          f"{'went low':>9} {'fizzle<25':>10}", flush=True)
    for k in (1, 2, 3):
        g = [r for r in rows if r["top"] == k]
        if len(g) < 20:
            continue
        pr = np.array([r["peak_rise"] for r in g])
        lo, hi = boot_ci(pr)
        rec = dict(group=name[k], n=len(g), start_bg=float(np.mean([r["start_bg"] for r in g])),
                   peak_rise=float(pr.mean()), lo=lo, hi=hi,
                   low_rate=float(np.mean([r["went_low"] for r in g])),
                   fizzle=float((pr < 25).mean()))
        out["groups"].append(rec)
        print(f"{name[k]:>18} {len(g):>6,} {rec['start_bg']:>9.0f} {rec['peak_rise']:>11.1f} "
              f"[{lo:>5.1f},{hi:>5.1f}] {rec['low_rate']:>9.1%} {rec['fizzle']:>10.1%}", flush=True)

    # the contrast that matters, within participant
    print("\nwithin participant: reached CONFIRMED minus OBSERVING only", flush=True)
    diffs, lows = [], []
    for u in sorted({r["user"] for r in rows}):
        a = [r["peak_rise"] for r in rows if r["user"] == u and r["top"] == 1]
        b = [r["peak_rise"] for r in rows if r["user"] == u and r["top"] >= 2]
        la = [r["went_low"] for r in rows if r["user"] == u and r["top"] == 1]
        lb = [r["went_low"] for r in rows if r["user"] == u and r["top"] >= 2]
        if len(a) >= 15 and len(b) >= 15:
            diffs.append(np.mean(b) - np.mean(a))
            lows.append(np.mean(lb) - np.mean(la))
            out["per_user"].append(dict(user=u, n_obs=len(a), n_conf=len(b),
                                        d_peak=float(np.mean(b) - np.mean(a)),
                                        d_low=float(np.mean(lb) - np.mean(la))))
            print(f"{u:>6}  OBSERVING n={len(a):>4} peak {np.mean(a):>5.1f}  |  "
                  f"CONFIRMED+ n={len(b):>4} peak {np.mean(b):>5.1f}  |  "
                  f"delta {np.mean(b)-np.mean(a):>+6.1f} mg/dL, low {np.mean(lb)-np.mean(la):>+5.1%}",
                  flush=True)
    if diffs:
        lo, hi = boot_ci(diffs)
        lo2, hi2 = boot_ci(lows)
        out["pooled"] = dict(n_participants=len(diffs), mean_d_peak=float(np.mean(diffs)),
                             lo=lo, hi=hi, mean_d_low=float(np.mean(lows)), low_lo=lo2, low_hi=hi2)
        print(f"\npooled over {len(diffs)} participants: peak rise {np.mean(diffs):+.1f} mg/dL "
              f"[{lo:+.1f}, {hi:+.1f}], low rate {np.mean(lows):+.1%} [{lo2:+.1%}, {hi2:+.1%}]",
              flush=True)
    here = os.path.dirname(os.path.abspath(__file__))
    op = os.path.join(here, "out", "meal_state_price.json")
    json.dump(out, open(op, "w"), indent=1)
    import numpy as _np
    e = _np.array([r["esc_min"] for r in rows if r["top"] >= 2 and r["esc_min"] == r["esc_min"]])
    print(f"\ntime from episode start to first escalation: n={len(e)}, "
          f"median {_np.median(e):.0f} min, "
          f"{(e <= 15).mean():.0%} within 15 min, {(e <= 30).mean():.0%} within 30", flush=True)
    matched(rows, op)
    print("\nrestricted to episodes that escalated within 15 minutes", flush=True)
    matched([r for r in rows if r["top"] < 2 or (r["esc_min"] == r["esc_min"] and r["esc_min"] <= 15)], op)
    print("\nwrote out/meal_state_price.json")




# ── matched comparison ────────────────────────────────────────────────────────────────────────
def matched(rows_with_early, out_path):
    """Given the rise already visible at the decision point, does escalating add anything?

    An episode escalates because its rise continued, so comparing escalated against non-escalated
    episodes unconditionally is circular: the label and the outcome are both downstream of the same
    trajectory. The test that is not circular holds the visible rise fixed and asks whether the
    ladder's decision carries information beyond it.
    """
    import numpy as np
    rng = np.random.default_rng(20260825)
    early = np.array([r["rise15"] for r in rows_with_early], dtype=float)
    peak = np.array([r["peak_rise"] for r in rows_with_early], dtype=float)
    esc = np.array([1 if r["top"] >= 2 else 0 for r in rows_with_early])
    edges = np.quantile(early, [0, .2, .4, .6, .8, 1.0])
    print(f"\n{'rise at +15 min':>18} {'n obs':>7} {'n esc':>7} {'peak obs':>9} {'peak esc':>9} "
          f"{'delta':>8} {'95% CI':>16}", flush=True)
    recs = []
    for i in range(5):
        lo_e, hi_e = edges[i], edges[i + 1]
        m = (early >= lo_e) & (early <= hi_e if i == 4 else early < hi_e)
        a, b = peak[m & (esc == 0)], peak[m & (esc == 1)]
        if len(a) < 15 or len(b) < 15:
            continue
        d = b.mean() - a.mean()
        bs = np.array([rng.choice(b, len(b), True).mean() - rng.choice(a, len(a), True).mean()
                       for _ in range(2000)])
        lo, hi = np.percentile(bs, 2.5), np.percentile(bs, 97.5)
        recs.append(dict(bin=f"{lo_e:.0f} to {hi_e:.0f}", n_obs=len(a), n_esc=len(b),
                         peak_obs=float(a.mean()), peak_esc=float(b.mean()),
                         delta=float(d), lo=float(lo), hi=float(hi)))
        print(f"{lo_e:>7.0f} to {hi_e:>6.0f} {len(a):>7} {len(b):>7} {a.mean():>9.1f} "
              f"{b.mean():>9.1f} {d:>+8.1f} [{lo:>+6.1f},{hi:>+6.1f}]", flush=True)
    import json
    d = json.load(open(out_path))
    d["matched"] = recs
    json.dump(d, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    sys.exit(main())
