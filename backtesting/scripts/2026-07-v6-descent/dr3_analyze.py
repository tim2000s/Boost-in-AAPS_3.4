#!/usr/bin/env python3
"""
DESCENT 3 analyze — out-of-sample cross-user prediction of the plateau low. GroupKFold(user) so no
user is in both train and test (the honest generalisation test). Univariate OOS AUC per signal +
a combined logistic model. If NOTHING clears ~0.6 OOS, the plateau low is genuinely unforecastable
and the descent lever is closed; if the SLOPE (or a combo) clears it, the lever reopens Twin-gated.
"""
import json, glob, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
rows, users = [], []
for f in sorted(glob.glob("dr3_*.json")):
    d = json.load(open(f))
    for c in d['cells']:
        if any(np.isnan(c[k]) for k in ('mg', 'mp')): continue     # need oref forecasts for the head-to-head
        rows.append(c); users.append(d['user'])
users = np.array(users)
y = np.array([c['goes_low70'] for c in rows])
FEATS = ['bg', 'iob', 'd15', 'mg', 'mp', 'fc30', 'fc60', 'lo30', 'lo60', 'slope30', 'slope60', 'slope_late', 'ra', 'tmin']
X = np.array([[c[f] for f in FEATS] for rows_i, c in enumerate(rows)], float)
print(f"plateau cells: {len(y)} across {len(set(users))} users; go-low<70 base rate {100*y.mean():.0f}%\n")
gkf = GroupKFold(n_splits=min(6, len(set(users))))
def oos_auc(cols, invert=False):
    """OOS AUC using logistic on the given feature columns (GroupKFold by user)."""
    Xc = X[:, cols]; oof = np.zeros(len(y))
    for tr, te in gkf.split(Xc, y, users):
        if y[tr].sum() < 3 or y[tr].sum() == len(tr): continue
        sc = StandardScaler().fit(Xc[tr]); lr = LogisticRegression(max_iter=500).fit(sc.transform(Xc[tr]), y[tr])
        oof[te] = lr.predict_proba(sc.transform(Xc[te]))[:, 1]
    try: return roc_auc_score(y, oof)
    except Exception: return float('nan')
print("UNIVARIATE out-of-sample AUC (each signal alone, cross-user):")
for i, f in enumerate(FEATS):
    print(f"  {f:<12} {oos_auc([i]):.3f}")
print(f"\nSLOPE features together (slope30,slope60,slope_late): {oos_auc([FEATS.index(k) for k in ('slope30','slope60','slope_late')]):.3f}")
print(f"ALL Twin forecast (fc30,fc60,lo30,lo60,slopes,ra):     {oos_auc([FEATS.index(k) for k in ('fc30','fc60','lo30','lo60','slope30','slope60','slope_late','ra')]):.3f}")
print(f"oref only (mg,mp):                                     {oos_auc([FEATS.index(k) for k in ('mg','mp')]):.3f}")
print(f"EVERYTHING (all {len(FEATS)} features):                    {oos_auc(list(range(len(FEATS)))):.3f}")
print("\n0.50 = chance. A gate needs ~>=0.65 OOS to be worth acting on. If nothing clears it, the plateau")
print("low is unforecastable from what V6/the Twin can see -> descent lever stays closed, properly this time.")
