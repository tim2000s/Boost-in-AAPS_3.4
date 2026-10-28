#!/usr/bin/env python3
"""
FOUNDATION 4 — the fix replay, PER USER with WINSORISED DynISF (not pooled). tim's ISF is genuinely
~117-151 mg/dL/U (sensitive U200 user — reason text shows 6.5 mmol = 117; NOT an 18× bug), 3× the U100
users, with spurious outliers (max 623). Pooling users of 3× different sensitivity is invalid (the U200
flag) and the outliers inflate his swings. Fix: cap variable_sens at a physiological 250, aggregate as
MEDIAN across users. Reuses the fidelity-gated sim. Usage: python3 ff4_sim_peruser.py  (standalone).
"""
import sys, numpy as np, psycopg2
sys.path.insert(0, '../2026-07-v6-sim')
from sim_lib import v6_confirm_shot, fix_confirm_shot, acted_fraction
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
USERS = ['tim', 'F', 'H', 'B', 'E', 'A', 'C', 'D']
ISF_CAP = 250.0; MARGIN, HORIZON = 20.0, 150
per = {}
for U in USERS:
    cur.execute("""select ts_epoch,cgm_mgdl,variable_sens,sug_current_target,iob_iob,boostv5_state,
       boostv5_finaldose,boostv5_budget,boostv5_aggressionknob,boostv5_confirmedcap,boostv5_committedcap
       from boost_decisions where user_id=%s and variant='boost-other' and cgm_mgdl is not null order by ts_epoch""", (U,))
    r = cur.fetchall()
    if not r: continue
    EP = np.array([x[0] for x in r], float); G = np.array([x[1] for x in r], float)
    ISF = np.array([min(x[2], ISF_CAP) if x[2] is not None else np.nan for x in r], float)
    if np.nanmedian(ISF) < 15: ISF *= 18.0
    TGT = np.array([(x[3] if x[3] is not None else 100.0) for x in r], float)
    if np.nanmedian(TGT) < 20: TGT *= 18.0
    def bg(e, tol=400):
        i = np.searchsorted(EP, e); c = [j for j in (i - 1, i, i + 1) if 0 <= j < len(EP) and abs(EP[j] - e) < tol]
        return G[min(c, key=lambda j: abs(EP[j] - e))] if c else np.nan
    def ix(e, tol=200):
        i = np.searchsorted(EP, e); c = [j for j in (i - 1, i, i + 1) if 0 <= j < len(EP) and abs(EP[j] - e) < tol]
        return min(c, key=lambda j: abs(EP[j] - e)) if c else None
    ca = cf = da = df = hi_a = hi_f = ntot = 0
    for k in range(len(r)):
        if r[k][5] != 'CONFIRMED' or r[k][7] is None or r[k][8] is None: continue
        e0 = EP[k]; rise = max(0.0, 2.0 * (G[k] - bg(e0 - 900)))
        if np.isnan(rise): continue
        ccap, mcap, iob0 = r[k][9] or 0.25, r[k][10] or 0.25, r[k][4] or 0.0
        s_v6 = v6_confirm_shot(r[k][7], r[k][8], rise, ccap); s_fix = fix_confirm_shot(r[k][7], r[k][8], rise, ccap, iob0)
        reserve = max(0.0, s_v6 - s_fix); deliv = 0.0; dd = [(e0, s_fix - s_v6)]
        isf = ISF[k] if not np.isnan(ISF[k]) else np.nanmedian(ISF)
        pa, pf = [], []
        for m in range(0, HORIZON + 1, 5):
            t = e0 + m * 60; ba = bg(t)
            if np.isnan(ba): continue
            bf = ba - isf * sum(d * acted_fraction((t - s) / 60.0) for s, d in dd)
            pa.append(ba); pf.append(bf)
            if 0 < m <= 90 and deliv < reserve - 1e-6:
                j = ix(t); tgt = TGT[j] if j is not None and not np.isnan(TGT[j]) else 100.0
                if bf > tgt + MARGIN:
                    h = min(mcap, r[k][7], reserve - deliv); dd.append((t, h)); deliv += h
        if len(pa) < 10: continue
        pa, pf = np.array(pa), np.array(pf); ntot += 1
        ca += pa.min() < 70; cf += pf.min() < 70; da += pa.min() < 54; df += pf.min() < 54
        hi_a += pa[-6:].mean() > 160; hi_f += pf[-6:].mean() > 160
    if ntot >= 5:
        per[U] = dict(n=ntot, crash_a=100 * ca / ntot, crash_f=100 * cf / ntot, deep_a=100 * da / ntot,
                      deep_f=100 * df / ntot, hi_a=100 * hi_a / ntot, hi_f=100 * hi_f / ntot)
print(f"{'user':<5}{'n':>5}{'crash V6→fix':>16}{'deep V6→fix':>15}{'high>160 V6→fix':>18}")
for u, p in per.items():
    print(f"{u:<5}{p['n']:>5}   {p['crash_a']:>5.0f}→{p['crash_f']:<4.0f}    {p['deep_a']:>5.0f}→{p['deep_f']:<4.0f}     {p['hi_a']:>5.0f}→{p['hi_f']:<4.0f}")
def med(k): return np.median([p[k] for p in per.values()])
print(f"\nMEDIAN across users (the valid aggregate, U200-safe):")
print(f"  crash    {med('crash_a'):.0f}% → {med('crash_f'):.0f}%   (median Δ {med('crash_f')-med('crash_a'):+.0f}pp)")
print(f"  deep<54  {med('deep_a'):.0f}% → {med('deep_f'):.0f}%   (median Δ {med('deep_f')-med('deep_a'):+.0f}pp)")
print(f"  high>160 {med('hi_a'):.0f}% → {med('hi_f'):.0f}%   (median Δ {med('hi_f')-med('hi_a'):+.0f}pp)")
print("compare to the POOLED headline (crash 22→15, deep 8→5, high 26→~34) — pooling was tim-weighted.")
conn.close()
