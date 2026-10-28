#!/usr/bin/env python3
"""Does the time-of-day gain survive on meals that are off the usual schedule?

A habit prior improves average performance by predicting that a climb is likely at the hours a
person usually eats. That is useful, but it is exactly the wrong behaviour if it works only on
habitual meals and fails on the unexpected one, since the unexpected meal is the one a
controller is least prepared for.

Climb onsets are split by whether they fall in an hour the user habitually eats in. Habitual is
defined from training days only, as the top third of half-hour slots by historical onset rate.
Performance is then reported separately for the two groups.
"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anticip_lib as A
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

H = 15
print("02. DOES THE HABIT PRIOR HELP ON OFF-SCHEDULE MEALS?\n")
rows = []
for u in A.users():
    d = A.load_user(u)
    ts, bg, day, tod = d["ts"], d["bg"], d["day"], d["tod"]
    nom = A.nominal_interval(ts); nom = 5.0 if nom > 3.0 else nom
    n = len(ts)
    G = A.glucose_features(ts, bg, nom)
    sl15 = A.causal_slope(ts, bg, 15, nom)
    eps = A.climb_episodes(ts, bg, nom)
    onset_ts = np.array([ts[a] for a, _ in eps], np.int64)
    onset_flag = np.zeros(n)
    for t0 in onset_ts:
        k = np.searchsorted(ts, t0)
        if k < n: onset_flag[k] = 1.0
    lab = np.zeros(n)
    for t0 in onset_ts:
        lo = np.searchsorted(ts, t0-H*60_000, side="left"); hi = np.searchsorted(ts, t0, side="right")
        lab[lo:hi] = 1.0
    quiet = np.isfinite(sl15) & (np.abs(sl15) < 2.0)
    tcyc = np.column_stack([np.sin(2*np.pi*tod/24), np.cos(2*np.pi*tod/24),
                            np.sin(4*np.pi*tod/24), np.cos(4*np.pi*tod/24)])
    m = np.isfinite(G).all(1) & quiet
    if m.sum() < 2000 or lab[m].sum() < 60: continue
    y = lab[m]; g = day[m]
    Xg = G[m]; Xh = np.column_stack([G, tcyc, np.zeros(n)])[m]
    pg = np.full(len(y), np.nan); ph = np.full(len(y), np.nan)
    habitual = np.zeros(len(y), bool)
    for tr, te in GroupKFold(n_splits=5).split(Xg, y, groups=g):
        if len(np.unique(y[tr])) < 2: continue
        tmask = np.isin(day, list(set(g[tr])))
        hp_all = A.habit_prior(tod[tmask], onset_flag[tmask], tod[m])
        Xh_tr, Xh_te = Xh[tr].copy(), Xh[te].copy()
        Xh_tr[:, 12] = hp_all[tr]; Xh_te[:, 12] = hp_all[te]
        thr = np.percentile(hp_all[tr], 100*2/3.0)
        habitual[te] = hp_all[te] >= thr
        s1 = StandardScaler().fit(Xg[tr])
        pg[te] = LogisticRegression(max_iter=3000).fit(s1.transform(Xg[tr]), y[tr]) \
                 .predict_proba(s1.transform(Xg[te]))[:, 1]
        s2 = StandardScaler().fit(Xh_tr)
        ph[te] = LogisticRegression(max_iter=3000).fit(s2.transform(Xh_tr), y[tr]) \
                 .predict_proba(s2.transform(Xh_te))[:, 1]
    ok = np.isfinite(pg) & np.isfinite(ph)
    r = dict(user=u)
    for grp, sel in (("habitual hours", ok & habitual), ("off-schedule hours", ok & ~habitual)):
        if sel.sum() < 400 or len(np.unique(y[sel])) < 2: continue
        r[grp] = dict(n=int(sel.sum()), base=float(y[sel].mean()),
                      auc_glucose=float(roc_auc_score(y[sel], pg[sel])),
                      auc_habit=float(roc_auc_score(y[sel], ph[sel])))
    rows.append(r)
    if "habitual hours" in r and "off-schedule hours" in r:
        a, b = r["habitual hours"], r["off-schedule hours"]
        print(f"  {u:>4s}  habitual: base {100*a['base']:4.1f}%  glucose {a['auc_glucose']:.3f} -> "
              f"habit {a['auc_habit']:.3f} ({a['auc_habit']-a['auc_glucose']:+.3f})   "
              f"off-schedule: base {100*b['base']:4.1f}%  {b['auc_glucose']:.3f} -> "
              f"{b['auc_habit']:.3f} ({b['auc_habit']-b['auc_glucose']:+.3f})")

print("\n  Cohort medians")
for grp in ("habitual hours", "off-schedule hours"):
    gl = [r[grp]["auc_glucose"] for r in rows if grp in r]
    hb = [r[grp]["auc_habit"] for r in rows if grp in r]
    if not gl: continue
    d_ = [h-g for h, g in zip(hb, gl)]
    print(f"    {grp:<20s} glucose {np.median(gl):.3f}  with habit {np.median(hb):.3f}  "
          f"gain {np.median(d_):+.4f}  better in {sum(1 for x in d_ if x>0)}/{len(d_)}")
A.save("02_offschedule.json", rows)
