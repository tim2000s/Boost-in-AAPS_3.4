#!/usr/bin/env python3
"""H4 — does a Twin + GBM HYBRID forecaster beat either alone at predicting BG+30? Twin fc30 (real engine,
cached) vs a GBM on context features vs a GBM that also gets the Twin outputs. OOS GroupKFold by user;
bootstrap 95% CI on the RMSE differences. Verdict = hybrid distinguishably below BOTH."""
import os, glob, numpy as np
from sklearn.model_selection import GroupKFold
import lightgbm as lgb
HERE = os.path.dirname(os.path.abspath(__file__))
RNG = np.random.default_rng(0)

Xb, Xh, y, tw, grp = [], [], [], [], []
for f in sorted(glob.glob(os.path.join(HERE, "cache", "*.npz"))):
    u = os.path.basename(f)[:-4]; d = np.load(f, allow_pickle=True)
    ep, cgm = d["ep"], d["cgm"]; n = len(ep)
    def back(i, mins):
        t = ep[i]-mins*60; j = i
        while j > 0 and ep[j] > t:
            if ep[j]-ep[j-1] > 900: return np.nan
            j -= 1
        return cgm[j] if abs(ep[j]-t) < 400 else np.nan
    def fwd(i, mins=30):
        t = ep[i]+mins*60; j = np.searchsorted(ep, t)
        c = [k for k in (j-1, j, j+1) if 0 <= k < n and abs(ep[k]-t) < 300]
        if not c: return np.nan
        k = min(c, key=lambda k: abs(ep[k]-t)); seg = ep[i:k+1]
        return cgm[k] if not (len(seg) >= 2 and np.diff(seg).max() > 1200) else np.nan
    d15 = np.array([cgm[i]-back(i, 15) for i in range(n)])
    lon = ((ep+3600) % 86400)/3600.0
    tgt = np.array([fwd(i) for i in range(n)])
    base = np.column_stack([cgm, np.nan_to_num(d15), d["iob"], d["steps5"], d["steps60"],
                            np.sin(2*np.pi*lon/24), np.cos(2*np.pi*lon/24)])
    hyb = np.column_stack([base, np.nan_to_num(d["fc30"], nan=cgm), np.nan_to_num(d["lo30"], nan=cgm), np.nan_to_num(d["ra"])])
    m = np.isfinite(tgt) & np.isfinite(d["fc30"])
    Xb.append(base[m]); Xh.append(hyb[m]); y.append(tgt[m]); tw.append(d["fc30"][m]); grp += [u]*m.sum()

Xb = np.vstack(Xb); Xh = np.vstack(Xh); y = np.concatenate(y); tw = np.concatenate(tw); grp = np.array(grp)
print(f"[H4] {len(y)} samples, {len(np.unique(grp))} users")

def oof(X):
    p = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=min(8, len(np.unique(grp)))).split(X, y, grp):
        mdl = lgb.LGBMRegressor(n_estimators=250, learning_rate=0.05, num_leaves=48,
                                min_child_samples=80, random_state=0, n_jobs=-1, verbose=-1).fit(X[tr], y[tr])
        p[te] = mdl.predict(X[te])
    return p

p_base, p_hyb = oof(Xb), oof(Xh)
def rmse(pred): return float(np.sqrt(np.mean((pred-y)**2)))
def boot_diff(a, b):                       # RMSE(a) - RMSE(b), bootstrap CI
    idx = np.arange(len(y)); dd = []
    for _ in range(1000):
        s = RNG.choice(idx, len(idx), replace=True)
        dd.append(np.sqrt(np.mean((a[s]-y[s])**2)) - np.sqrt(np.mean((b[s]-y[s])**2)))
    return np.median(dd), np.percentile(dd, 2.5), np.percentile(dd, 97.5)

print(f"\n=== H4 BG+30 forecast RMSE (OOS, GroupKFold by user) ===")
print(f"  Twin fc30 alone : {rmse(tw):.2f} mg/dL")
print(f"  GBM (context)   : {rmse(p_base):.2f}")
print(f"  GBM + Twin (hyb): {rmse(p_hyb):.2f}")
for lbl, a, b in [("hybrid − Twin", p_hyb, tw), ("hybrid − GBM", p_hyb, p_base), ("GBM − Twin", p_base, tw)]:
    m, lo, hi = boot_diff(a, b)
    v = "hybrid better" if hi < 0 else ("worse" if lo > 0 else "NOT distinguishable")
    print(f"  Δ {lbl:>13}: {m:+.2f} [{lo:+.2f}, {hi:+.2f}] mg/dL  → {v}")
