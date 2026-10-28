#!/usr/bin/env python3
"""Signal digging on the GBM forecaster (the one durable win). Three parts:
  1. WHAT IT IS — feature importances + per-regime RMSE (where it wins/loses).
  2. RESIDUAL MAP — where the OOF error concentrates (that IS the map of missing signal).
  3. CANDIDATE SIGNALS — for each candidate feature group, does adding it reduce OOS RMSE? (bootstrap CI).
Full history, all users, GroupKFold by user. BG+30 target. Row-sampled for speed."""
import sys, numpy as np, psycopg2, pandas as pd
from sklearn.model_selection import GroupKFold
import lightgbm as lgb
RNG = np.random.default_rng(0)
HORIZON = int(sys.argv[1]) if len(sys.argv) > 1 else 30    # forecast horizon (minutes)
VARPRIO = {"boost-other": 0, "trio-shadow": 1, "v1": 2, "v2": 3, "v3": 4, "v1-silent": 5}
USERS = ["tim", "A", "B", "C", "D", "E", "F", "H", "G"]

COLS = ("ts_epoch, cgm_mgdl, iob_iob, iob_activity, iob_bolusiob, iob_basaliob, sug_cob, variable_sens, "
        "delta_acceleration, steps_5m, steps_30m, steps_60m, hr_bpm_avg5m, hrr_pct, tdd_ratio, tdd_1d, "
        "tdd_7d, ml_meal_likely, ml_hypo_risk, boostv5_state, variant")
frames = []
with psycopg2.connect("dbname=oref host=127.0.0.1 port=5432") as conn:
    for u in USERS:
        d = pd.read_sql(f"select {COLS} from boost_decisions where user_id=%s and cgm_mgdl is not null order by ts_epoch", conn, params=(u,))
        d["prio"] = d.variant.map(VARPRIO).fillna(9); d["bucket"] = (d.ts_epoch // 300).astype(np.int64)
        d = d.sort_values(["bucket", "prio"]).drop_duplicates("bucket", keep="first").sort_values("ts_epoch").reset_index(drop=True)
        ep = d.ts_epoch.to_numpy(float); cgm = d.cgm_mgdl.to_numpy(float); n = len(d)
        def back(i, m):
            t = ep[i]-m*60; j = i
            while j > 0 and ep[j] > t:
                if ep[j]-ep[j-1] > 900: return np.nan
                j -= 1
            return cgm[j] if abs(ep[j]-t) < 400 else np.nan
        def fwd(i, m=HORIZON):
            t = ep[i]+m*60; j = np.searchsorted(ep, t)
            c = [k for k in (j-1, j, j+1) if 0 <= k < n and abs(ep[k]-t) < 300]
            if not c: return np.nan
            k = min(c, key=lambda k: abs(ep[k]-t))
            seg = ep[i:k+1]                                   # reject if a data gap (>20min) sits in the path
            return cgm[k] if not (len(seg) >= 2 and np.diff(seg).max() > 1200) else np.nan
        d["d5"] = [cgm[i]-back(i, 5) for i in range(n)]; d["d15"] = [cgm[i]-back(i, 15) for i in range(n)]
        d["d30"] = [cgm[i]-back(i, 30) for i in range(n)]
        d["bg_std30"] = [np.std(cgm[max(0, i-6):i+1]) if i >= 2 else np.nan for i in range(n)]
        lon = ((ep+3600) % 86400)/3600.0
        d["tod_sin"] = np.sin(2*np.pi*lon/24); d["tod_cos"] = np.cos(2*np.pi*lon/24); d["lon"] = lon
        d["y"] = [fwd(i) for i in range(n)]; d["user"] = u
        d["meal_state"] = (d.boostv5_state.isin(["CONFIRMED", "COMMITTED", "OBSERVING"])).astype(float)
        frames.append(d)
df = pd.concat(frames, ignore_index=True)
df = df[np.isfinite(df.y)].reset_index(drop=True)
if len(df) > 220000:
    df = df.sample(220000, random_state=0).reset_index(drop=True)
grp = df.user.to_numpy(); y = df.y.to_numpy(float)
print(f"[signal] {len(df)} samples, {df.user.nunique()} users")

BASE = ["cgm_mgdl", "d5", "d15", "iob_iob", "steps_5m", "steps_60m", "tod_sin", "tod_cos"]
GROUPS = {
    "accel": ["delta_acceleration"], "iob_decomp": ["iob_activity", "iob_bolusiob", "iob_basaliob"],
    "carbs+mealstate": ["sug_cob", "meal_state"], "sensitivity(dynISF+TDD)": ["variable_sens", "tdd_ratio", "tdd_1d", "tdd_7d"],
    "heart_rate": ["hr_bpm_avg5m", "hrr_pct"], "volatility": ["bg_std30", "d30"],
    "ml_signals": ["ml_meal_likely", "ml_hypo_risk"], "steps30": ["steps_30m"],
}

def oof(feats):
    X = df[feats].astype(float).to_numpy(); p = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=min(9, df.user.nunique())).split(X, y, grp):
        m = lgb.LGBMRegressor(n_estimators=180, learning_rate=0.05, num_leaves=48, min_child_samples=80,
                              random_state=0, n_jobs=-1, verbose=-1).fit(X[tr], y[tr])
        p[te] = m.predict(X[te])
    return p

p_base = oof(BASE)
def rmse(p, m=None):
    m = np.ones(len(y), bool) if m is None else m
    return float(np.sqrt(np.mean((p[m]-y[m])**2)))
res = np.abs(p_base - y)

print(f"\n=== 1. GBM (base) importances (full-fit) + base RMSE {rmse(p_base):.2f} ===")
full = lgb.LGBMRegressor(n_estimators=180, learning_rate=0.05, num_leaves=48, min_child_samples=80,
                         random_state=0, n_jobs=-1, verbose=-1).fit(df[BASE].astype(float), y)
for f, imp in sorted(zip(BASE, full.feature_importances_), key=lambda t: -t[1]):
    print(f"   {f:<12} {imp}")

print(f"\n=== 2. Residual (|error|) by regime — where the GBM still fails ===")
lon = df.lon.to_numpy()
regimes = {
    "rising (d15>+15)": df.d15 > 15, "falling (d15<-15)": df.d15 < -15, "flat": df.d15.abs() <= 15,
    "high (>180)": df.cgm_mgdl > 180, "low (<80)": df.cgm_mgdl < 80,
    "meal-state": df.meal_state > 0, "active (steps60>200)": df.steps_60m > 200,
    "overnight (0-6h)": (lon >= 0) & (lon < 6), "daytime (8-22h)": (lon >= 8) & (lon < 22),
}
for name, m in regimes.items():
    m = m.to_numpy() if hasattr(m, "to_numpy") else m
    if m.sum() > 200:
        print(f"   {name:<22} RMSE {rmse(p_base, m):5.1f}  (n={m.sum()}, {100*m.mean():.0f}%)")

print(f"\n=== 3. Candidate signals: OOS RMSE reduction when ADDED to base (bootstrap 95% CI) ===")
print(f"   base RMSE {rmse(p_base):.2f}")
for gname, feats in GROUPS.items():
    if not all(f in df.columns for f in feats):
        continue
    p_g = oof(BASE + feats)
    d = []
    for _ in range(600):
        s = RNG.choice(len(y), len(y), replace=True)
        d.append(np.sqrt(np.mean((p_g[s]-y[s])**2)) - np.sqrt(np.mean((p_base[s]-y[s])**2)))
    md, lo, hi = np.median(d), np.percentile(d, 2.5), np.percentile(d, 97.5)
    v = "HELPS" if hi < 0 else ("hurts" if lo > 0 else "no effect")
    print(f"   +{gname:<24} ΔRMSE {md:+.3f} [{lo:+.3f}, {hi:+.3f}]  → {v}")
