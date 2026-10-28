#!/usr/bin/env python3
"""H2 — does gating the Twin-lo30 withdrawal on ACTIVITY (recent steps) rescue its selectivity? The naive
lo30 withdrawal was 93% unjustified (fires when no low follows). Hypothesis: the lows lo30 catches are the
exercise/dose-then-walk ones, so requiring recent steps should keep the JUSTIFIED firings and drop the
false ones. Compare % of withdrawal bouts followed by a real low (selectivity) WITH vs WITHOUT the gate,
per user + bootstrap over bouts. Uses the cache (lo30, steps, cgm)."""
import os, glob, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
RNG = np.random.default_rng(0)
LO30_THR = 60.0; STEP60_GATE = 200                 # recent-hour steps to count as "active"


def bouts_and_justified(ep, cgm, fire):
    ev = np.where(fire)[0]; b, last = [], -1e9
    for i in ev:
        if ep[i]-last > 1800: b.append(i)
        last = ep[i]
    def low_after(i):
        m = (ep > ep[i]) & (ep <= ep[i]+90*60); return m.any() and np.nanmin(cgm[m]) < 70
    just = [low_after(i) for i in b]
    return b, just


rows = []
print(f"{'user':>4} | {'ungated bouts':>13} {'%just':>6} | {'gated bouts':>11} {'%just':>6}  {'Δjust':>6}")
for f in sorted(glob.glob(os.path.join(HERE, "cache", "*.npz"))):
    u = os.path.basename(f)[:-4]; d = np.load(f, allow_pickle=True)
    ep, cgm, lo30, s60 = d["ep"], d["cgm"], d["lo30"], d["steps60"]
    hypo = np.isfinite(lo30) & (lo30 < LO30_THR) & (cgm >= 70)
    active = s60 >= STEP60_GATE
    bu, ju = bouts_and_justified(ep, cgm, hypo)                    # ungated
    bg, jg = bouts_and_justified(ep, cgm, hypo & active)           # activity-gated
    if len(bu) < 20:
        continue
    pu = 100*np.mean(ju); pg = 100*np.mean(jg) if jg else 0.0
    rows.append((u, len(bu), pu, len(bg), pg))
    print(f"{u:>4} | {len(bu):>13} {pu:>5.1f}% | {len(bg):>11} {pg:>5.1f}%  {pg-pu:>+5.1f}")

# cohort: paired Δselectivity (gated − ungated), bootstrap CI over users
if rows:
    d = np.array([r[4] - r[2] for r in rows])          # gated %just − ungated %just, per user
    boots = [np.median(RNG.choice(d, len(d), replace=True)) for _ in range(3000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    verdict = "gate HELPS" if lo > 0 else ("gate HURTS" if hi < 0 else "NOT distinguishable")
    print(f"\n  COHORT (n={len(rows)}): median ungated %just {np.median([r[2] for r in rows]):.0f}%, "
          f"median gated %just {np.median([r[4] for r in rows]):.0f}%")
    print(f"  paired Δ (gated−ungated) median {np.median(d):+.1f} [{lo:+.1f}, {hi:+.1f}] → {verdict}")
    print(f"  (gate = recent-hr steps ≥ {STEP60_GATE}; note gated bouts are far fewer — total {sum(r[3] for r in rows)})")
