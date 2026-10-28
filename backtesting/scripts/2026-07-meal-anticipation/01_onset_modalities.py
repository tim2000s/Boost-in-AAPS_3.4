#!/usr/bin/env python3
"""Q1. What is the cheapest additional channel that makes meal onset anticipation usable?

Baseline is glucose alone, which on one subject gave AUC around 0.65 for whether a climb
begins in the next H minutes, judged from a non-rising state. Here the question is asked
across the whole cohort at five minutes, adding channels in increasing order of cost:

  glucose            what every system already has
  + time of day      free, no hardware
  + habit prior      free; the user's own historical rate of climb onsets by time of day,
                     estimated on training days only so it cannot leak
  + steps            requires a phone or watch

Models are per user, validated with GroupKFold over whole days. A cross-user model is also
fitted, grouped by user, to separate the value of personalisation from the value of the extra
channel.

Lift is precision in the top risk decile divided by that user's base rate, and is the figure
that decides whether an alarm or a pre-emptive dose could act on the output.
"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anticip_lib as A
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

H_LIST = [15, 30]
print("01. MEAL ONSET: WHICH EXTRA CHANNEL HELPS?\n")
US = A.users()
per_user, pooled_rows = {}, []
for u in US:
    d = A.load_user(u)
    ts, bg, day, tod = d["ts"], d["bg"], d["day"], d["tod"]
    nom = A.nominal_interval(ts)
    if nom > 3.0: nom = 5.0
    n = len(ts)
    G = A.glucose_features(ts, bg, nom)
    steps = A.align_steps(ts, d["st_ts"], d["st"])
    sl15 = A.causal_slope(ts, bg, 15, nom)
    eps = A.climb_episodes(ts, bg, nom)
    onset_ts = np.array([ts[a] for a, _ in eps], np.int64)
    quiet = np.isfinite(sl15) & (np.abs(sl15) < 2.0)
    per_user[u] = dict(n_climbs=len(eps), horizons={})
    for H in H_LIST:
        lab = np.zeros(n)
        for t0 in onset_ts:
            lo = np.searchsorted(ts, t0 - H*60_000, side="left")
            hi = np.searchsorted(ts, t0, side="right")
            lab[lo:hi] = 1.0
        onset_flag = np.zeros(n)
        for t0 in onset_ts:
            k = np.searchsorted(ts, t0); 
            if k < n: onset_flag[k] = 1.0
        base_ok = np.isfinite(G).all(1) & quiet
        if base_ok.sum() < 2000 or lab[base_ok].sum() < 60: continue
        tcyc = np.column_stack([np.sin(2*np.pi*tod/24), np.cos(2*np.pi*tod/24),
                                np.sin(4*np.pi*tod/24), np.cos(4*np.pi*tod/24)])
        sets = {"glucose": G,
                "+ time of day": np.column_stack([G, tcyc]),
                "+ habit prior": np.column_stack([G, tcyc, np.zeros(n)]),   # filled per fold
                "+ steps": np.column_stack([G, tcyc, np.zeros(n), steps])}
        res = {}
        for name, X in sets.items():
            m = base_ok & np.isfinite(X).all(1)
            if m.sum() < 2000: continue
            y = lab[m]; g = day[m]; Xm = X[m].copy()
            if len(np.unique(y)) < 2: continue
            p = np.full(len(y), np.nan)
            for tr, te in GroupKFold(n_splits=5).split(Xm, y, groups=g):
                Xtr, Xte = Xm[tr].copy(), Xm[te].copy()
                if "habit" in name or "steps" in name:      # habit column is index 12
                    tr_days = set(g[tr])
                    tmask = np.isin(day, list(tr_days))
                    hp = A.habit_prior(tod[tmask], onset_flag[tmask], tod[m])
                    Xtr[:, 12] = hp[tr]; Xte[:, 12] = hp[te]
                if len(np.unique(y[tr])) < 2: continue
                sc = StandardScaler().fit(Xtr)
                mdl = LogisticRegression(max_iter=3000).fit(sc.transform(Xtr), y[tr])
                p[te] = mdl.predict_proba(sc.transform(Xte))[:, 1]
            ok = np.isfinite(p)
            if ok.sum() < 500 or len(np.unique(y[ok])) < 2: continue
            auc = float(roc_auc_score(y[ok], p[ok]))
            k = max(int(0.1*ok.sum()), 50)
            top = np.nonzero(ok)[0][np.argsort(-p[ok])[:k]]
            lift = float(y[top].mean()/max(y[ok].mean(), 1e-9))
            res[name] = dict(auc=auc, lift=lift, base=float(y[ok].mean()), n=int(ok.sum()))
            pooled_rows.append(dict(user=u, H=H, channel=name, auc=auc, lift=lift))
        per_user[u]["horizons"][str(H)] = res
    if per_user[u]["horizons"]:
        H0 = str(H_LIST[0])
        r = per_user[u]["horizons"].get(H0, {})
        line = "  ".join(f"{k.split('+ ')[-1][:9]:>9s} {v['auc']:.3f}" for k, v in r.items())
        print(f"  {u:>4s}  climbs {per_user[u]['n_climbs']:4d}  H={H0}m  {line}")

print("\n  Cohort summary (median across users, and the spread)")
for H in H_LIST:
    print(f"    horizon {H} min")
    for ch in ["glucose", "+ time of day", "+ habit prior", "+ steps"]:
        a = [r["auc"] for r in pooled_rows if r["H"] == H and r["channel"] == ch]
        l = [r["lift"] for r in pooled_rows if r["H"] == H and r["channel"] == ch]
        if not a: continue
        print(f"      {ch:<15s} n={len(a):2d} users  AUC median {np.median(a):.3f} "
              f"[{np.min(a):.3f}, {np.max(a):.3f}]  lift median {np.median(l):.2f}x")
    g = {r["user"]: r["auc"] for r in pooled_rows if r["H"] == H and r["channel"] == "glucose"}
    for ch in ["+ time of day", "+ habit prior", "+ steps"]:
        d_ = [{r["user"]: r["auc"] for r in pooled_rows if r["H"] == H and r["channel"] == ch}.get(u, np.nan) - g.get(u, np.nan)
              for u in g]
        d_ = [x for x in d_ if np.isfinite(x)]
        if d_:
            better = sum(1 for x in d_ if x > 0)
            print(f"      gain from {ch:<15s} median {np.median(d_):+.4f}, "
                  f"better in {better}/{len(d_)} users")
A.save("01_onset_modalities.json", dict(per_user=per_user, rows=pooled_rows))
