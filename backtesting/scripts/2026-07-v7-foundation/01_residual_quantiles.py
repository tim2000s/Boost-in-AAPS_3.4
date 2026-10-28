#!/usr/bin/env python3
"""V7 Backtest 1 — residual-quantile substrate (Transplant-1 substrate).

Per user, per horizon h in {30,60,90} min:
  residual r_h(t) = bg(t+h) - [bg(t) + BGI5(t)*h/5]   (IOB-only projection; see v7_common)

Outputs: quantiles (5/25/50/75/95) per user/horizon for 14d & 30d windows;
regime splits (meal-session vs quiet, day vs night) at h=60; odd/even-day
calibration coverage; and the tail-honesty n's (how many <70-relevant samples
inform the left tail — EXPECTED to be too few; that is the documented reason
the future chance constraint may only tighten).
"""
import numpy as np, pandas as pd, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v7_common import load, forward_bg, USERS, MEAL_STATES

QS = [5, 25, 50, 75, 95]

df = load()
df = forward_bg(df)
now = df.ts_epoch.max()
for h in (30, 60, 90):
    df[f"r{h}"] = df[f"bg{h}"] - (df.bg + df.bgi5 * h / 5.0)
df["meal"] = df.state.isin(MEAL_STATES)
df["day"] = df.hour.between(7, 22)

rows, cal_rows, tail_rows = [], [], []
for uid in USERS:
    for win, days in (("14d", 14), ("30d", 30)):
        g = df[(df.user_id == uid) & (df.ts_epoch >= now - days * 86400)]
        for h in (30, 60, 90):
            r = g[f"r{h}"].dropna()
            if len(r) < 200:
                continue
            qv = np.percentile(r, QS)
            rows.append(dict(user=uid, win=win, h=h, n=len(r),
                             **{f"q{q}": round(v, 1) for q, v in zip(QS, qv)}))
            # tail honesty: samples where the OUTCOME was <70-relevant
            lo = g.dropna(subset=[f"r{h}"])
            n_lo70 = int((lo[f"bg{h}"] < 70).sum())
            thr5 = np.percentile(r, 5)
            n_tail = int((lo[f"r{h}"] <= thr5).sum())
            n_both = int(((lo[f"bg{h}"] < 70) & (lo[f"r{h}"] <= thr5)).sum())
            tail_rows.append(dict(user=uid, win=win, h=h,
                                  n_outcome_lt70=n_lo70, n_bottom5pct=n_tail,
                                  n_lt70_in_tail=n_both))
        # regime splits at h=60 (30d window only, for n)
        if win == "30d":
            for regime, mask in (("meal", g.meal), ("quiet", ~g.meal),
                                 ("day", g.day), ("night", ~g.day)):
                r = g.loc[mask, "r60"].dropna()
                if len(r) < 100:
                    continue
                qv = np.percentile(r, QS)
                rows.append(dict(user=uid, win=f"30d/{regime}", h=60, n=len(r),
                                 **{f"q{q}": round(v, 1) for q, v in zip(QS, qv)}))
    # calibration: fit on even calendar days, coverage on odd days (30d)
    g = df[(df.user_id == uid) & (df.ts_epoch >= now - 30 * 86400)].copy()
    g["odd"] = pd.to_datetime(g.date.astype(str)).dt.day % 2 == 1
    for h in (30, 60, 90):
        fit = g.loc[~g.odd, f"r{h}"].dropna(); test = g.loc[g.odd, f"r{h}"].dropna()
        if len(fit) < 200 or len(test) < 200:
            continue
        cov = {f"cov{q}": round(100 * (test <= np.percentile(fit, q)).mean(), 1) for q in QS}
        cal_rows.append(dict(user=uid, h=h, n_fit=len(fit), n_test=len(test), **cov))

pd.set_option("display.width", 250)
Q = pd.DataFrame(rows); C = pd.DataFrame(cal_rows); T = pd.DataFrame(tail_rows)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(out, exist_ok=True)
Q.to_csv(f"{out}/residual_quantiles.csv", index=False)
C.to_csv(f"{out}/residual_calibration.csv", index=False)
T.to_csv(f"{out}/residual_tail_honesty.csv", index=False)

print("=== residual quantiles (mg/dL) ===")
print(Q.to_string(index=False))
print("\n=== calibration: empirical coverage of even-day-fit quantiles on odd days (target = nominal) ===")
print(C.to_string(index=False))
print("\n=== tail honesty: <70-relevant sample counts informing the left tail ===")
print(T[T.win == "30d"].to_string(index=False))
