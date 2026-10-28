#!/usr/bin/env python3
"""Ten minutes after a confirm, is the engine still in a position to deliver?

The release half of the tranche sits inside the same block as the confirm, guarded by v5Active,
microBolusAllowed, a non-null decision, not asleep, the cumulative cap not reached, and boostActive.
A confirm necessarily satisfies all of those. Ten minutes later any of them can be false, and a
remainder that cannot be delivered is a silent withhold rather than a decision.

The direct evidence that the block executed is the line it writes, "V6-ACTIVE drove SMB". This counts
how often that line is present on the cycle a release would land on, and where it is absent, reads
the reason text for which gate was shut.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""
import bisect, json, os, re, sys
import numpy as np, psycopg2

OFFSETS = (10, 15)
TOL_S = 200


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 45
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("select distinct user_id from public.boost_decisions "
                    "where accelmeal_state is not null order by 1")
        users = [r[0] for r in cur.fetchall()]
    tot = {o: [0, 0] for o in OFFSETS}
    reasons = {}
    per_user = []
    for u in users:
        with conn.cursor() as cur:
            cur.execute(f"""select extract(epoch from ts_utc), accelmeal_state, reason_text
                            from public.boost_decisions where user_id=%s
                              and accelmeal_state is not null
                              and ts_utc > now() - interval '{days} days' order by ts_utc""", (u,))
            d = cur.fetchall()
        seen, rows = set(), []
        for r in d:
            k = int(float(r[0]) // 60)
            if k not in seen:
                seen.add(k); rows.append(r)
        if len(rows) < 200:
            continue
        t = np.asarray([float(r[0]) for r in rows], dtype=float)
        st = [r[1] for r in rows]
        rt = [r[2] or "" for r in rows]
        mine = {o: [0, 0] for o in OFFSETS}
        for i in range(1, len(rows)):
            if st[i] != "CONFIRMED" or st[i - 1] == "CONFIRMED":
                continue
            for o in OFFSETS:
                j = bisect.bisect_left(t, t[i] + o * 60)
                cand = [k for k in (j - 1, j) if 0 <= k < len(t) and abs(t[k] - (t[i] + o * 60)) <= TOL_S]
                if not cand:
                    continue
                k = min(cand, key=lambda k: abs(t[k] - (t[i] + o * 60)))
                mine[o][1] += 1
                tot[o][1] += 1
                if "V6-ACTIVE drove SMB" in rt[k]:
                    mine[o][0] += 1
                    tot[o][0] += 1
                elif o == 10:
                    for pat, lbl in (("SMB not allowed", "microBolus not allowed"),
                                     ("cumulative", "cumulative cap"),
                                     ("SLEEP", "asleep"),
                                     ("boostActive=false", "boost inactive"),
                                     ("V1 drove", "V1 drove the cycle")):
                        if pat.lower() in rt[k].lower():
                            reasons[lbl] = reasons.get(lbl, 0) + 1
                            break
                    else:
                        reasons["other or no override line"] = reasons.get("other or no override line", 0) + 1
        if mine[10][1] >= 10:
            per_user.append(dict(user=u, n=mine[10][1], reachable=mine[10][0],
                                 pct=100.0 * mine[10][0] / mine[10][1]))
            print(f"{u:>6}  {mine[10][0]:>4}/{mine[10][1]:<4} "
                  f"{100*mine[10][0]/mine[10][1]:>5.1f}% deliverable at +10 min", flush=True)

    print()
    for o in OFFSETS:
        a, b = tot[o]
        print(f"pooled at +{o:>2} min: {a}/{b} = {100*a/max(b,1):.1f}% of releases would land on a "
              f"cycle where the block runs")
    if reasons:
        print("\nwhere it would not land, what the cycle said instead:")
        for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  {k:>28}  {v:>4}")
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(dict(pooled={str(o): tot[o] for o in OFFSETS}, per_user=per_user, reasons=reasons),
              open(os.path.join(here, "out", "tranche_release_reachable.json"), "w"), indent=1)
    print("\nwrote out/tranche_release_reachable.json")


if __name__ == "__main__":
    sys.exit(main())
