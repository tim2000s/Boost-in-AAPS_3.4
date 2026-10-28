#!/usr/bin/env python3
"""H7 — can the Twin distinguish a COMPRESSION low from a real low? A compression low is a sudden overnight
CGM drop the physiology can't explain (no insulin/meal cause), which recovers fast. The Twin's "surprise"
= its 30-min-ago forecast minus the actual reading (a big unexpected drop). Test whether that surprise
separates compression lows from real lows. Labels (developer's definition): overnight (23:30–07:00 local) dip <75 that
RECOVERS to ≥90 within 30 min = compression; a <75 dip that stays low / recovers slowly = real. Pooled
(compression is rare); AUC of the surprise signal, bootstrap CI. Uses the cache (cgm, fc30)."""
import os, glob, numpy as np
from sklearn.metrics import roc_auc_score
HERE = os.path.dirname(os.path.abspath(__file__))
RNG = np.random.default_rng(0)

surprise, label = [], []                    # label 1 = compression, 0 = real low
per_user = {}
for f in sorted(glob.glob(os.path.join(HERE, "cache", "*.npz"))):
    u = os.path.basename(f)[:-4]; d = np.load(f, allow_pickle=True)
    ep, cgm, fc30 = d["ep"], d["cgm"], d["fc30"]; n = len(ep)
    lon = ((ep+3600) % 86400)/3600.0
    def bg_at(t, tol=400):
        j = np.searchsorted(ep, t); c = [k for k in (j-1, j, j+1) if 0 <= k < n and abs(ep[k]-t) < tol]
        return cgm[min(c, key=lambda k: abs(ep[k]-t))] if c else np.nan
    def fc_ago(i, mins=30):                  # the fc30 issued ~mins ago (predicting now)
        t = ep[i]-mins*60; j = np.searchsorted(ep, t)
        c = [k for k in (j-1, j, j+1) if 0 <= k < n and abs(ep[k]-t) < 400 and np.isfinite(fc30[k])]
        return fc30[min(c, key=lambda k: abs(ep[k]-t))] if c else np.nan
    nu = 0
    for i in range(6, n):
        if not (cgm[i] < 75 and cgm[i-1] >= 75):        # a dip crossing <75
            continue
        overnight = lon[i] >= 23.5 or lon[i] < 7.0
        rec = bg_at(ep[i] + 30*60)                       # BG 30 min later
        if np.isnan(rec):
            continue
        compression = overnight and rec >= 90            # fast overnight recovery
        real = rec < 75                                  # still low 30 min on
        if not (compression or real):
            continue
        s = fc_ago(i) - cgm[i]                            # forecast-minus-actual = unexpected-drop surprise
        if np.isnan(s):
            continue
        surprise.append(s); label.append(1 if compression else 0)
        nu += 1
    per_user[u] = nu

surprise, label = np.array(surprise), np.array(label)
nc, nr = int(label.sum()), int((label == 0).sum())
print(f"[H7] pooled dips: {nc} compression, {nr} real-low  (per user: {per_user})")
if nc >= 8 and nr >= 8:
    auc = roc_auc_score(label, surprise)
    boots = []
    for _ in range(2000):
        s = RNG.choice(np.arange(len(label)), len(label), replace=True)
        if 2 <= label[s].sum() < len(s):
            boots.append(roc_auc_score(label[s], surprise[s]))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print(f"\n  Twin-surprise AUC (compression vs real low): {auc:.2f} [{lo:.2f}, {hi:.2f}]")
    print(f"  mean surprise: compression {surprise[label==1].mean():+.1f}, real {surprise[label==0].mean():+.1f} mg/dL")
    print(f"  → {'SEPARATES (CI clears 0.5)' if lo > 0.5 else 'UNPROVEN (overlaps 0.5)'}")
else:
    print(f"\n  too few events to test (need ≥8 each) — compression lows are rare in this data.")
