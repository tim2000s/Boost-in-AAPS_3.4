#!/usr/bin/env python3
"""H12 — did Boost get better across versions? Glycaemic scorecard per version-era, per user + cohort.
Eras (telemetry-based, developer's correction): BoostV1_415 (early v4.1.5, no explicit v1/v6 telemetry) →
V44x_ML → V5V6. Descriptive, CGM-only. CAVEAT: eras are also different SEASONS (V1=spring, V6=summer) and
partly different users → this is the honest scorecard WITH those confounds stated, not a clean A/B."""
import os, glob, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ERAS = ["BoostV1_415", "V44x_ML", "V5V6"]


def scorecard(cgm):
    return dict(n=len(cgm), mean=round(float(cgm.mean()), 0),
                cv=round(100 * cgm.std() / cgm.mean(), 1),
                ting=round(100 * np.mean((cgm >= 63) & (cgm <= 140)), 1),
                tir=round(100 * np.mean((cgm >= 70) & (cgm <= 180)), 1),
                tbr70=round(100 * np.mean(cgm < 70), 2), tbr54=round(100 * np.mean(cgm < 54), 2))


rows = {e: [] for e in ERAS}
print(f"{'user':>4} {'era':>12} {'n':>6} {'mean':>4} {'CV':>5} {'TING':>5} {'TIR':>5} {'<70':>5} {'<54':>5}")
for f in sorted(glob.glob(os.path.join(HERE, "cache", "*.npz"))):
    u = os.path.basename(f)[:-4]; d = np.load(f, allow_pickle=True)
    cgm = d["cgm"]; era = d["era"].astype(str)
    for e in ERAS:
        c = cgm[era == e]
        if len(c) < 500:
            continue
        s = scorecard(c); rows[e].append((u, s))
        print(f"{u:>4} {e:>12} {s['n']:>6} {s['mean']:>4.0f} {s['cv']:>5.1f} {s['ting']:>5.1f} "
              f"{s['tir']:>5.1f} {s['tbr70']:>5.2f} {s['tbr54']:>5.2f}")

print("\n=== COHORT (median across users per era) — the Boost evolution scorecard ===")
print(f"{'era':>12} {'users':>5} {'mean':>4} {'CV':>5} {'TING':>5} {'TIR':>5} {'<70':>5} {'<54':>5}")
for e in ERAS:
    r = rows[e]
    if not r:
        print(f"{e:>12}  (no data)"); continue
    def med(k): return np.median([s[k] for _, s in r])
    print(f"{e:>12} {len(r):>5} {med('mean'):>4.0f} {med('cv'):>5.1f} {med('ting'):>5.1f} "
          f"{med('tir'):>5.1f} {med('tbr70'):>5.2f} {med('tbr54'):>5.2f}")
# within-user paired V1->V6 (the users present in both eras) with bootstrap CI on the deltas
common = set(u for u, _ in rows["BoostV1_415"]) & set(u for u, _ in rows["V5V6"])
if len(common) >= 3:
    v1 = {u: s for u, s in rows["BoostV1_415"]}; v6 = {u: s for u, s in rows["V5V6"]}
    rng = np.random.default_rng(0)
    print(f"\n=== WITHIN-USER V1(4.1.5)→V5V6 paired (n={len(common)}), median Δ [95% CI] (season-confounded) ===")
    for k in ["ting", "tir", "tbr70", "tbr54", "cv", "mean"]:
        d = np.array([v6[u][k] - v1[u][k] for u in common])
        boots = [np.median(rng.choice(d, len(d), replace=True)) for _ in range(3000)]
        lo, hi = np.percentile(boots, [2.5, 97.5])
        sig = "" if (lo > 0 or hi < 0) else "  (overlaps 0 — unproven)"
        print(f"   Δ{k:>6}: {np.median(d):+6.2f} [{lo:+6.2f}, {hi:+6.2f}]{sig}")
