#!/usr/bin/env python3
"""
TING frontier — where is TING (63-140 mg/dL) won and lost, and what is the achievable ceiling?

Result (2026-07-17): TING is a VARIABILITY problem, not a dose-more problem.
  - TING vs glucose CV across the cohort:      r = -0.81, r2 = 0.65, p = 0.008
  - TING vs the 140-180 "mild-high" band:      r = -0.86, r2 = 0.74, p = 0.003
The low-TING users are high-CV; the high-TING users are low-CV. Each +1% CV costs ~1.3pp TING.
The addressable loss is the 140-180 band (glucose fine by TIR, out of the tight band). The lever
is EARLIER + SMOOTHER dosing that compresses that band and drops CV — NOT bigger corrections,
which feed the low-tail (see the residency lever-map + recovering-highs rejections). TING must be
pinned to the low-tail floor: user D shows 88% TING bought with ~10% time-below-70 — TING at any
cost is not the target.

CGM from the local DB (oref.boost_decisions), deduped to 5-min bins so rapid meal-cycle invokes
don't over-weight active periods. 90-day window. Anonymised tags only.

Usage: python3 ting_frontier.py
"""
import psycopg2, numpy as np
from scipy import stats

DAYS = 90
USERS = ['tim', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']


def bands(cur, user, days=DAYS):
    cur.execute(
        """select ts_epoch, cgm_mgdl from boost_decisions
           where user_id=%s and cgm_mgdl is not null and ts_utc > now() - interval '%s days'
           order by ts_epoch""", (user, days))
    seen = {}
    for ep, v in cur.fetchall():
        if v and v > 0:
            seen[int(ep // 300)] = v      # 5-min bin dedupe
    a = np.array(list(seen.values()), float)
    if len(a) < 500:
        return None
    return dict(
        n=len(a),
        sev=100 * np.mean(a < 54), low=100 * np.mean((a >= 54) & (a < 63)),
        ting=100 * np.mean((a >= 63) & (a <= 140)),
        mildhi=100 * np.mean((a > 140) & (a <= 180)),
        hi=100 * np.mean((a > 180) & (a <= 250)), vhi=100 * np.mean(a > 250),
        tbr70=100 * np.mean(a < 70), cv=100 * np.std(a) / np.mean(a), median=np.median(a))


def main():
    c = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = c.cursor()
    rows = {}
    print(f"TING frontier — {DAYS}d, 5-min-binned CGM\n")
    print(f"{'tag':>4} {'<54':>5} {'54-63':>6} | {'TING':>6} | {'140-180':>7} {'180-250':>7} {'>250':>5} || "
          f"{'TBR70':>5} {'CV%':>5} {'med':>4}  frontier*")
    for u in USERS:
        r = bands(cur, u)
        if not r:
            print(f"{u:>4}  (insufficient data)"); continue
        rows[u] = r
        frontier = r['ting'] + 0.5 * r['mildhi']    # crude: recover half the mild-high band at held low-tail
        print(f"{u:>4} {r['sev']:5.1f} {r['low']:6.1f} | {r['ting']:6.1f} | {r['mildhi']:7.1f} {r['hi']:7.1f} "
              f"{r['vhi']:5.1f} || {r['tbr70']:5.1f} {r['cv']:5.1f} {r['median']:4.0f}  -> {frontier:4.1f}")

    ting = np.array([rows[u]['ting'] for u in rows])
    cv = np.array([rows[u]['cv'] for u in rows])
    mh = np.array([rows[u]['mildhi'] for u in rows])
    r1, p1 = stats.pearsonr(cv, ting); r2, p2 = stats.pearsonr(mh, ting)
    b, a = np.polyfit(cv, ting, 1)
    print(f"\nMECHANISM (cross-user, n={len(ting)}):")
    print(f"  TING vs CV:        r={r1:+.2f}  r2={r1**2:.2f}  p={p1:.3f}   each +1% CV -> {b:.1f}pp TING")
    print(f"  TING vs 140-180:   r={r2:+.2f}  r2={r2**2:.2f}  p={p2:.3f}")
    print(f"  fit: TING = {a:.0f} {b:+.1f} * CV     low-CV frontier (~19% CV, like user E) -> TING ~{a+b*19:.0f}%")
    print("\n* frontier col = illustrative TING if half the 140-180 band is recovered at a HELD low-tail.")
    print("  The real lever is CV reduction (earlier+smoother dosing), floor-pinned. Not aggression.")


if __name__ == "__main__":
    main()
