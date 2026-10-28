#!/usr/bin/env python3
"""Per-user vs cross-user prediction of exercise / meal onset (2026-07-27).

Prompted by the observation that our prediction work used cross-cohort (GroupKFold-by-user)
splits. That is the right test for a PHYSIOLOGICAL signal (does it generalise across people),
but meal/exercise TIMING is habitual and idiosyncratic, so cross-user pooling cannot see the
held-out person's routine and will understate anticipatability. This compares:

  CROSS-USER : GroupKFold by user (train on other people, predict a held-out person).
  PER-USER   : temporal split within each user (train on their first 70% of time, test on the
               last 30% — honest past->future, no leakage).

Task: predict onset of exercise (steps > 2x per-user baseline) / meal (V5 CONFIRMED, COB=0)
within the next 45 min, from HABIT features only (time-of-day, day-of-week, weekend, minutes
since last onset, onsets in prior 24h) — NO glucose. Isolates "can we anticipate the routine".
"""
import numpy as np
import pandas as pd
import psycopg2
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
d = pd.read_sql("""
    SELECT user_id AS user, ts_epoch, ts_utc, steps_30m AS steps, boostv5_state AS st, sug_cob AS cob
    FROM boost_decisions WHERE ts_utc >= now() - interval '45 days'
    ORDER BY user_id, ts_epoch
""", conn).drop_duplicates(subset=['user', 'ts_epoch']).reset_index(drop=True)
d['tl'] = pd.to_datetime(d.ts_utc, utc=True)
h = d.tl.dt.hour + d.tl.dt.minute / 60
d['sinh'] = np.sin(2 * np.pi * h / 24); d['cosh'] = np.cos(2 * np.pi * h / 24)
dow = d.tl.dt.dayofweek
d['sind'] = np.sin(2 * np.pi * dow / 7); d['cosd'] = np.cos(2 * np.pi * dow / 7)
d['wknd'] = (dow >= 5).astype(int)
FEATS = ['sinh', 'cosh', 'sind', 'cosd', 'wknd', 'mins_since', 'cnt24']


def build(target):
    out = []
    for uid, g in d.groupby('user'):
        g = g.reset_index(drop=True); ts = g.ts_epoch.values
        if target == 'exercise':
            base = g.steps[g.steps > 0].median() if (g.steps > 0).any() else np.nan
            if np.isnan(base) or base == 0:
                continue
            inb = (g.steps > 2 * base).values
            onset = inb & ~np.concatenate([[False], inb[:-1]])
        else:
            stv = g.st.values; cob = np.nan_to_num(g.cob.values)
            onset = (stv == 'CONFIRMED') & (np.concatenate([['x'], stv[:-1]]) != 'CONFIRMED') & (cob == 0)
        y = np.zeros(len(g), bool)
        for i in range(len(g)):
            w = (ts > ts[i]) & (ts <= ts[i] + 45 * 60)
            if w.any():
                y[i] = onset[w].any()
        ots = ts[onset]
        mins = np.array([(ts[i] - ots[ots < ts[i]][-1]) / 60 if (ots < ts[i]).any() else 999 for i in range(len(g))])
        cnt = np.array([((ots >= ts[i] - 86400) & (ots < ts[i])).sum() for i in range(len(g))])
        out.append(g.assign(y=y, mins_since=np.clip(mins, 0, 999), cnt24=cnt, user=uid))
    return pd.concat(out, ignore_index=True)


def model():
    return GradientBoostingClassifier(n_estimators=120, max_depth=3, learning_rate=0.05,
                                      subsample=0.8, random_state=0)


def evaluate(target):
    D = build(target).dropna(subset=FEATS)
    X, y, grp = D[FEATS].values, D.y.astype(int).values, D.user.values
    oof = np.full(len(D), np.nan)
    for tr, te in GroupKFold(min(5, D.user.nunique())).split(X, y, grp):
        if len(np.unique(y[tr])) < 2:
            continue
        oof[te] = model().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    ok = ~np.isnan(oof); cross = roc_auc_score(y[ok], oof[ok])
    pu = []
    for uid, g in D.groupby('user'):
        g = g.sort_values('ts_epoch'); k = int(len(g) * 0.7)
        tr, te = g.iloc[:k], g.iloc[k:]
        if te.y.nunique() < 2 or tr.y.nunique() < 2 or te.y.sum() < 5:
            continue
        a = roc_auc_score(te.y.astype(int), model().fit(tr[FEATS], tr.y.astype(int)).predict_proba(te[FEATS])[:, 1])
        pu.append((uid, a, int(te.y.sum())))
    print(f"\n=== {target.upper()} onset within 45 min (base rate {100*y.mean():.1f}%, n={len(D)}) ===")
    print(f"  CROSS-USER GroupKFold: AUC {cross:.3f}")
    aucs = [a for _, a, _ in pu]
    print(f"  PER-USER temporal:     AUC median {np.median(aucs):.3f} (range {min(aucs):.2f}-{max(aucs):.2f}, {len(pu)} users)")
    for uid, a, n in sorted(pu, key=lambda x: -x[1]):
        print(f"      {uid}: {a:.3f} (test events {n})")


evaluate('exercise')
evaluate('meal')
