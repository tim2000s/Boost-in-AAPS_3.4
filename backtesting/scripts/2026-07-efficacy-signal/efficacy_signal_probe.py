#!/usr/bin/env python3
"""Does a TRUE insulin-efficacy signal exist in our telemetry? (2026-07-27)

Prompted by an UNTESTED claim in the fully-closed-loop review ("no efficacy signal exists").
This measures it. The trap is circularity: "BG still high => insulin not working" is just the
glucose trajectory, which signal-digging already showed is all the loop-visible signal. A TRUE
efficacy signal must add information BEYOND the trajectory — at two cycles identical on
BG/delta/accel, distinguish "insulin hasn't acted yet but will" (=> rebound CRASH once carbs
finish) from "insulin isn't working" (=> STALL / resistance).

Design (out-of-sample):
  Population  : stuck-high regime — BG>150, IOB>1U, COB=0. Two views:
                (a) REGIME ENTRIES (first cycle of a run) — independent-ish episodes;
                (b) all CYCLES — higher power, autocorrelated (single-feature reads only).
  Labels      : CRASH = min BG < 70 within 3h ;  STALL = never < 140 within 2h.
  Feature sets: BASE (trajectory) = bg, delta, accel, curvature.
                +EFFICACY = deviation, IOB-activity, IOB, BGI, recent-SMB(60m), post-rescue,
                IOB/TDD ; (tim-only) Twin inferred glucose-appearance Ra.
  Test        : GroupKFold by USER; AUC(BASE) vs AUC(BASE+EFFICACY) with BOTH a gradient-boosted
                and a logistic model (the linear model is the overfit control in a near-chance
                regime). Single-feature AUCs and a mechanism stratification for interpretability.
  Per-user z-scoring removes mmol/mg-dL + U200 unit differences, preserves sign/shape.

Identification note: deviation lumps unabsorbed-carb rise and genuine resistance; only the
FORWARD outcome disambiguates them, which is why we predict the outcome, not label efficacy at t.
"""
import numpy as np
import pandas as pd
import psycopg2
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

RNG = np.random.default_rng(20260727)
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")

d = pd.read_sql("""
    SELECT user_id AS user, ts_epoch, cgm_mgdl AS bg, iob_iob, iob_activity AS act,
           reason_dev AS dev, reason_bgi AS bgi, delta_acceleration AS accel,
           boostv5_smbvol60min AS smb60, boostv5_postrescuewindow AS prw,
           tdd_blended AS tdd, sug_cob AS cob, boosttwin_ra AS twin_ra
    FROM boost_decisions
    WHERE ts_utc >= now() - interval '60 days' AND cgm_mgdl IS NOT NULL
    ORDER BY user_id, ts_epoch
""", conn).drop_duplicates(subset=['user', 'ts_epoch']).reset_index(drop=True)
d['delta'] = d.groupby('user').bg.diff()
d['curv'] = d.groupby('user').delta.diff()
d['iob_tdd'] = np.where(d.tdd > 0, d.iob_iob / d.tdd, np.nan)


def forward(g):
    ts, bg = g.ts_epoch.values, g.bg.values
    crash = np.full(len(g), np.nan); stall = np.full(len(g), np.nan)
    for i in range(len(g)):
        m3 = (ts > ts[i]) & (ts <= ts[i] + 180 * 60)
        m2 = (ts > ts[i]) & (ts <= ts[i] + 120 * 60)
        if m3.sum() >= 18:
            crash[i] = int(bg[m3].min() < 70)
        if m2.sum() >= 12:
            stall[i] = int(bg[m2].min() >= 140)
    return crash, stall


cr, stl = [], []
for _, g in d.groupby('user', sort=False):
    c, s = forward(g); cr.append(c); stl.append(s)
d['crash'] = np.concatenate(cr); d['stall'] = np.concatenate(stl)

inreg = (d.bg > 150) & (d.iob_iob > 1.0) & (np.nan_to_num(d.cob) == 0)
d['entry'] = inreg & ~inreg.groupby(d.user).shift(1, fill_value=False)

BASE = ['bg', 'delta', 'accel', 'curv']
EFF = ['dev', 'act', 'iob_iob', 'bgi', 'smb60', 'prw', 'iob_tdd']


def zbyuser(df, cols):
    o = df.copy()
    for c in cols:
        o[c] = df.groupby('user')[c].transform(lambda s: (s - s.mean()) / (s.std() + 1e-9))
    return o.fillna(0.0)


def cv_auc(df, feats, label, Model):
    df = df.dropna(subset=[label]).copy()
    df['prw'] = df.prw.fillna(False).astype(float)
    if df.user.nunique() < 3 or df[label].nunique() < 2:
        return np.nan
    X = zbyuser(df, [c for c in feats])
    y = df[label].astype(int).values
    p = np.full(len(df), np.nan)
    for tr, te in GroupKFold(min(5, df.user.nunique())).split(X, y, df.user.values):
        if len(np.unique(y[tr])) < 2:
            continue
        m = Model().fit(X.iloc[tr][feats], y[tr])
        p[te] = m.predict_proba(X.iloc[te][feats])[:, 1]
    ok = ~np.isnan(p)
    return roc_auc_score(y[ok], p[ok])


GBM = lambda: GradientBoostingClassifier(n_estimators=120, max_depth=2, learning_rate=0.05,
                                         subsample=0.8, random_state=0)
LR = lambda: LogisticRegression(max_iter=500)

E = d[d.entry].copy()
print(f"stuck-high REGIME ENTRIES: {len(E)}  per-user {E.groupby('user').size().to_dict()}")
print(f"CRASH base rate {100*E.crash.mean(skipna=True):.0f}%  STALL {100*E.stall.mean(skipna=True):.0f}%\n")

for label in ('crash', 'stall'):
    bg = cv_auc(E, BASE, label, GBM); eg = cv_auc(E, BASE + EFF, label, GBM)
    bl = cv_auc(E, BASE, label, LR);  el = cv_auc(E, BASE + EFF, label, LR)
    print(f"[{label.upper()}]  GBM base {bg:.3f} -> +eff {eg:.3f} (Δ{eg-bg:+.3f})   "
          f"LOGISTIC base {bl:.3f} -> +eff {el:.3f} (Δ{el-bl:+.3f})")

# ---- cycle-level single-feature reads (higher power; autocorrelated) ----
print("\ncycle-level single-feature AUC vs CRASH (all stuck-high cycles):")
S = d[inreg & d.crash.notna()].copy()
for c in ['delta', 'accel', 'dev', 'act', 'iob_iob', 'bgi', 'smb60', 'iob_tdd']:
    s = S.dropna(subset=[c])
    if len(s) > 200 and s.crash.nunique() > 1:
        z = s.groupby('user')[c].transform(lambda x: (x - x.mean()) / (x.std() + 1e-9)).fillna(0)
        print(f"   {c:8}: {roc_auc_score(s.crash, z):.3f}   (n={len(s)})")

# recent-SMB tertile crash rate
Ss = S.dropna(subset=['smb60'])
Ss['ter'] = pd.qcut(Ss.smb60.rank(method='first'), 3, labels=['low', 'mid', 'high'])
print("recent-SMB(60m) tertile crash rate:",
      {t: f"{100*Ss[Ss.ter==t].crash.mean():.0f}%" for t in ['low', 'mid', 'high']})

# ---- Twin Ra: the mechanism candidate (does inferred carb-appearance separate crash?) ----
T = d[(d.user == 'tim') & inreg & d.twin_ra.notna() & d.crash.notna()].copy()
cov = d[(d.user == 'tim') & inreg]
print(f"\nTWIN Ra: n={len(T)} stuck-high cycles with Ra ({T.crash.mean()*100:.0f}% crash); "
      f"coverage {cov.twin_ra.notna().mean()*100:.0f}% of {len(cov)} stuck-highs")
if len(T) >= 60:
    print(f"   Ra alone AUC vs crash {roc_auc_score(T.crash, T.twin_ra):.3f}   "
          f"high-Ra crash {100*T[T.twin_ra>T.twin_ra.median()].crash.mean():.0f}% "
          f"vs low-Ra {100*T[T.twin_ra<=T.twin_ra.median()].crash.mean():.0f}%")
