#!/usr/bin/env python3
"""
V6 vs V1 — aggregate glucose-distribution comparison for Figure 1 (2026-07-19).

A WITHIN-USER before/after: the same 7 users' glucose in their V1-Boost era (variant v1/v1-silent —
the "v4.1.5" generation, the extractor's Boost-v1 population) vs their V6 era (boostv5_active). Both
are REAL measured CGM. It is NOT a randomised crossover: the V1 era is earlier (≈Mar–Jun) and the V6
era is July, so calendar time, sensor/site changes and the user's evolving physiology are confounded.
Within-user is nonetheless far cleaner than the cross-user Boost-vs-oref comparison. Aggregated as the
MEAN across users (equal user weight, not volume-pooled), with pooled shown as a cross-check.
"""
import numpy as np, psycopg2
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
USERS = ['tim', 'F', 'H', 'B', 'E', 'A', 'C']


def dist(where, args):
    cur.execute(f"select cgm_mgdl from boost_decisions where {where} and cgm_mgdl is not null", args)
    g = np.array([r[0] for r in cur.fetchall()], float)
    if len(g) < 200:
        return None
    return dict(n=len(g), mean=g.mean(), cv=100 * g.std() / g.mean(),
               tbr=100 * np.mean(g < 70), tir=100 * np.mean((g >= 70) & (g <= 180)),
               tar=100 * np.mean(g > 180), ting=100 * np.mean((g >= 63) & (g <= 140)),
               t54=100 * np.mean(g < 54))


eras = {
    'V1': ("user_id=%s and variant in ('v1','v1-silent')", None),
    'V6': ("user_id=%s and boostv5_active", None),
}
per = {'V1': [], 'V6': []}
print(f"{'user':<5}  {'--- V1 era ---':<34}   {'--- V6 era ---':<34}")
print(f"{'':<5}  {'nCGM':>6}{'TIR':>6}{'TING':>6}{'TBR':>6}{'CV':>6}   {'nCGM':>6}{'TIR':>6}{'TING':>6}{'TBR':>6}{'CV':>6}")
for u in USERS:
    d1 = dist(eras['V1'][0], (u,)); d6 = dist(eras['V6'][0], (u,))
    if d1: per['V1'].append(d1)
    if d6: per['V6'].append(d6)
    def f(d): return f"{d['n']:>6}{d['tir']:>6.0f}{d['ting']:>6.0f}{d['tbr']:>6.1f}{d['cv']:>6.0f}" if d else f"{'—':>30}"
    print(f"{u:<5}  {f(d1)}   {f(d6)}")

print("\n=== AGGREGATE (mean across users, equal weight) ===")
print(f"{'era':<5}{'TBR<70':>8}{'TIR':>7}{'TAR':>7}{'TING':>7}{'TBR<54':>8}{'CV':>7}{'mean':>7}   n_users")
for era in ('V1', 'V6'):
    P = per[era]
    def m(k): return np.mean([p[k] for p in P])
    print(f"{era:<5}{m('tbr'):>8.1f}{m('tir'):>7.1f}{m('tar'):>7.1f}{m('ting'):>7.1f}{m('t54'):>8.2f}{m('cv'):>7.1f}{m('mean'):>7.0f}   {len(P)}")

print("\n=== POOLED (all cohort CGM, volume-weighted — cross-check) ===")
for era, (w, _) in eras.items():
    cur.execute(f"select cgm_mgdl from boost_decisions where ({w.replace('user_id=%s','user_id = any(%s)')}) and cgm_mgdl is not null", (USERS,))
    g = np.array([r[0] for r in cur.fetchall()], float)
    print(f"{era:<5} n={len(g):>7}  TIR {100*np.mean((g>=70)&(g<=180)):.1f}  TING {100*np.mean((g>=63)&(g<=140)):.1f}"
          f"  TBR<70 {100*np.mean(g<70):.1f}  TAR {100*np.mean(g>180):.1f}  CV {100*g.std()/g.mean():.1f}")
conn.close()
