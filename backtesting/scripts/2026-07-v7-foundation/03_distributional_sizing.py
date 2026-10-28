#!/usr/bin/env python3
"""V7 Backtest 3 — distributional-sizing replay (Transplant-1 go/no-go).

Candidate rule, offline, structure-preserving:
  dose = argmax_d  -loss(d),  d in [0, envelope(state)] step 0.05
  loss(d) = mean over q in {25,50,75} of
              R * max(0, 70  - BGq(d))     (low cost, R in {4,7,10})
            +     max(0, BGq(d) - 140)     (high cost)
  BGq(d)  = bg + BGI5*12 + resid_q(60min, user, regime) - d * sens * F_ACT
  (h=60 horizon; F_ACT=0.5 of the dose acting by then — bilinear mid-curve)

Existing structure INTACT:
  - meal-state prior via envelope bound: d <= budget * stateMult (vf/brakes
    REPLACED by the distribution — that is the transplant), then
    committedCap (COMMITTED, per-user era), confirmedCap (CONFIRMED),
  - non-meal v1-bound (IDLE/OBSERVING/RECOVERING: d <= v1_units),
  - post-rescue window (min45<75): meal states ALSO d <= v1_units,
  - rolling 60-min cumulative cap on replay-delivered volume,
  - awake cycles only (07-23 local), capped-era only, budget=0 => d=0.

Priced by the two-test bar: Test A absolute (dTBR bracket [0.15,0.6]*ISF min
per pre-low U vs 14d baselines) and Test B relative (pricing vs user base).
"""
import numpy as np, pandas as pd, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v7_common import (load, add_rolling, forward_bg, USERS, MEAL_STATES,
                       CONF_CAPS, CONF_CAP_DEFAULT, CUM_CAPS, TBR14, CAP_ERAS)

F_ACT = 0.5
MULT = {"IDLE": 1.0, "OBSERVING": 0.3, "CONFIRMED": 1.8, "COMMITTED": 1.0, "RECOVERING": 0.4}

df = load()
df = add_rolling(df)
df = forward_bg(df, horizons=(60,))
df["r60"] = df.bg60 - (df.bg + df.bgi5 * 12)
df["meal"] = df.state.isin(MEAL_STATES)
now = df.ts_epoch.max()

# per-user, per-regime residual quantiles (30d fit; leakage caveat documented in report)
RQ = {}
for uid in USERS:
    g = df[(df.user_id == uid) & (df.ts_epoch >= now - 30 * 86400)]
    for regime, m in (("meal", g.meal), ("quiet", ~g.meal)):
        r = g.loc[m, "r60"].dropna()
        RQ[(uid, regime)] = np.percentile(r, [25, 50, 75]) if len(r) >= 150 else None

ce = df[df.cap.notna() & df.hour.between(7, 22)].copy()
ce["delivered"] = np.where(ce.meal & ~(ce.min45 < 75), ce.fd,
                           np.minimum(ce.fd, ce.v1_units.fillna(0)))
ISF14 = {u: 1800 / df[df.user_id == u].tdd.median() for u in USERS}

results, cyc_frames = [], []
grid = np.arange(0, 3.01, 0.05)
for R in (4, 7, 10):
    for uid in USERS:
        g = ce[ce.user_id == uid].reset_index(drop=True)
        if not len(g):
            continue
        conf_cap = CONF_CAPS.get(uid, CONF_CAP_DEFAULT)
        cum_cap = CUM_CAPS.get(uid, float(np.clip(conf_cap + 2 * (g.cap.iloc[-1]), 1, 10)))
        dose = np.zeros(len(g))
        recent = []          # (ts, dose) for cumulative cap
        for i in range(len(g)):
            r = g.iloc[i]
            rq = RQ.get((uid, "meal" if r.meal else "quiet"))
            if rq is None or pd.isna(r.sens) or pd.isna(r.budget) or r.budget <= 0:
                continue
            env = r.budget * MULT.get(r.state, 1.0)
            if r.state == "COMMITTED":
                env = min(env, r.cap)
            if r.state == "CONFIRMED":
                env = min(env, conf_cap)
            if (r.state not in ("CONFIRMED", "COMMITTED")) or (r.min45 < 75):
                env = min(env, r.v1_units if pd.notna(r.v1_units) else 0.0)
            recent = [(t, u) for (t, u) in recent if r.ts_epoch - t <= 3600]
            env = min(env, max(0.0, cum_cap - sum(u for _, u in recent)))
            if env <= 0:
                continue
            dmax = grid[grid <= env + 1e-9]
            base = r.bg + r.bgi5 * 12
            bgq = base + rq[None, :] - dmax[:, None] * r.sens * F_ACT
            loss = (R * np.clip(70 - bgq, 0, None) + np.clip(bgq - 140, 0, None)).mean(axis=1)
            d_star = dmax[int(np.argmin(loss))]
            dose[i] = d_star
            if d_star > 0:
                recent.append((r.ts_epoch, d_star))
        g["rule"] = dose
        g["diff"] = g.rule - g.delivered
        cyc_frames.append(g.assign(R=R))
        add = g["diff"].clip(lower=0); rem = (-g["diff"]).clip(lower=0)
        pre = add[g.low3h].sum()
        days = g.date.nunique()
        isf = ISF14[uid]
        dmin_lo, dmin_hi = pre * 0.15 * isf, pre * 0.6 * isf
        dtbr = (100 * dmin_lo / (days * 1440), 100 * dmin_hi / (days * 1440))
        b70, b54 = TBR14[uid]
        results.append(dict(R=R, user=uid, days=days,
                            actualU=round(g.delivered.sum(), 1), ruleU=round(g.rule.sum(), 1),
                            addU=round(add.sum(), 1), remU=round(rem.sum(), 1),
                            add_day=round(add.sum() / days, 2),
                            prelow_pct=round(100 * pre / max(add.sum(), 1e-9), 1),
                            base_low3h=round(100 * g.low3h.mean(), 1),
                            dTBR_lo=round(dtbr[0], 2), dTBR_hi=round(dtbr[1], 2),
                            testA="PASS" if b70 + dtbr[1] <= 3.5 and b54 + dtbr[1] * 0.3 <= 0.8
                                  else ("MARGINAL" if b70 + dtbr[0] <= 3.5 else "FAIL")))

RES = pd.DataFrame(results)
CY = pd.concat(cyc_frames)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(out, exist_ok=True)
RES.to_csv(f"{out}/sizing_results.csv", index=False)
pd.set_option("display.width", 260)
print("=== distributional-sizing replay, per user x cost-ratio ===")
print(RES.to_string(index=False))

print("\n=== where it differs (R=7): added U by state / BG band ===")
c7 = CY[CY.R == 7]
c7 = c7.assign(bgband=pd.cut(c7.bg, [0, 120, 160, 180, 240, 500]),
               add=c7["diff"].clip(lower=0))
print(c7.groupby(["state"], observed=True)["add"].sum().round(1).to_string())
print(c7.groupby(["bgband"], observed=True)["add"].sum().round(1).to_string())

print("\n=== stuck-episode improvement (R=7): added U inside >180->60min episodes ===")
tot_eps, touched = 0, 0
for uid, g in c7.groupby("user_id"):
    ts = g.ts_epoch.values; bg = g.bg.values
    i = 0
    while i < len(g):
        if bg[i] > 180:
            j = i
            while j + 1 < len(g) and bg[j + 1] > 180 and ts[j + 1] - ts[j] < 900:
                j += 1
            if ts[j] - ts[i] >= 3600:
                tot_eps += 1
                if g["add"].values[i:j + 1].sum() >= 0.5:
                    touched += 1
            i = j + 1
        else:
            i += 1
print(f"episodes >=0.5U extra: {touched}/{tot_eps}")

print("\n=== Episode B cycles (tim 2026-07-06 13:38..14:43Z, R=7) ===")
eb = c7[(c7.user_id == "tim")]
ebt = pd.to_datetime(eb.ts_utc, utc=True, format="mixed")
eb = eb[(ebt >= pd.Timestamp("2026-07-06 13:35", tz="UTC")) & (ebt <= pd.Timestamp("2026-07-06 14:45", tz="UTC"))]
print(eb[["ts_utc", "bg", "state", "budget", "delivered", "rule"]].round(2).to_string(index=False)
      if len(eb) else "  (tim 07-06 afternoon not in DB — check refresh)")
print("\n=== H morning stretch (2026-07-06 04:14..04:44Z, R=7): rule dose (expect 0 — budget=0 preserved) ===")
hh = c7[c7.user_id == "H"]
hht = pd.to_datetime(hh.ts_utc, utc=True, format="mixed")
hh = hh[(hht >= pd.Timestamp("2026-07-06 04:10", tz="UTC")) & (hht <= pd.Timestamp("2026-07-06 04:50", tz="UTC"))]
print(hh[["ts_utc", "bg", "state", "budget", "delivered", "rule"]].round(2).to_string(index=False) if len(hh) else "  (window outside awake filter — H stretch is 04:xx UTC = 05:xx local, included)")
