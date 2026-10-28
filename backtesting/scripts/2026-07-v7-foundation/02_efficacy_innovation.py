#!/usr/bin/env python3
"""V7 Backtest 2 — efficacy-innovation discrimination (Transplant-2 teeth).

Innovation(t) = observed dBG(5m) - BGI5(t)   [mg/dL per 5 min; model in v7_common]
innov30 = rolling 6-cycle mean (30 min), the DAMPER-side statistic.

(a) DAMPER: does sustained POSITIVE efficacy (BG falling faster than the IOB
    projection => innovation strongly NEGATIVE) separate known exercise /
    fresh-sensitivity periods from matched quiet periods?
      - tim festival window 2026-06-17..22 (day cycles) vs 06-03..13 day cycles
      - cohort high-step (steps_60m >= per-user p90) vs low-step (<= p50), day
(b) FLAG: on outcome-adjudicated stretches (tim Episode-B = TRUE
    under-absorption; tim Episode-A + H budget=0 stretches = correct
    restraint; auto-detected compression events = artifact), do
    innovation + site-age + IOB separate under-absorption? n(true)=1 —
    reported as a feature table, not an AUC.
"""
import numpy as np, pandas as pd, sys, os, json, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v7_common import load, USERS

df = load()
df["dbg"] = df.groupby("user_id").bg.diff() / df.dt * 5
df.loc[(df.dt > 7.6) | (df.dt < 2.0), "dbg"] = np.nan
df["innov"] = df.dbg - df.bgi5
df["innov30"] = df.groupby("user_id").innov.transform(lambda s: s.rolling(6, min_periods=4).mean())
df["day"] = df.hour.between(7, 22)
dtc = pd.to_datetime(df.ts_utc, utc=True, format="mixed")

print("=== (a) DAMPER side ===")
tim = df[df.user_id == "tim"]
fest = tim[(tim.date >= pd.Timestamp("2026-06-17").date()) & (tim.date <= pd.Timestamp("2026-06-22").date()) & tim.day].innov30.dropna()
quiet = tim[(tim.date >= pd.Timestamp("2026-06-03").date()) & (tim.date <= pd.Timestamp("2026-06-13").date()) & tim.day].innov30.dropna()
pool_sd = np.sqrt((fest.var() + quiet.var()) / 2)
d_eff = (fest.mean() - quiet.mean()) / pool_sd
print(f"tim festival (06-17..22, day): innov30 mean {fest.mean():.2f} sd {fest.std():.2f} n={len(fest)}")
print(f"tim quiet    (06-03..13, day): innov30 mean {quiet.mean():.2f} sd {quiet.std():.2f} n={len(quiet)}")
print(f"Cohen's d = {d_eff:.2f}")
for thr in (-3, -5, -8):
    tpr = 100 * (fest < thr).mean(); fpr = 100 * (quiet < thr).mean()
    print(f"  threshold innov30 < {thr}: TPR {tpr:.0f}% / FPR {fpr:.0f}%")

print("\ncohort high-step vs low-step (day cycles, per-user steps_60m p90/p50):")
rows = []
for uid, g in df[df.day].groupby("user_id"):
    s = g.steps_60m.dropna()
    if len(s) < 500 or s.quantile(.9) == 0:
        continue
    hi = g[(g.steps_60m >= s.quantile(.9))].innov30.dropna()
    lo = g[(g.steps_60m <= s.quantile(.5))].innov30.dropna()
    if len(hi) < 50:
        continue
    dd = (hi.mean() - lo.mean()) / np.sqrt((hi.var() + lo.var()) / 2)
    rows.append(dict(user=uid, n_hi=len(hi), hi_mean=round(hi.mean(), 2),
                     lo_mean=round(lo.mean(), 2), cohens_d=round(dd, 2),
                     tpr_m5=round(100 * (hi < -5).mean()), fpr_m5=round(100 * (lo < -5).mean())))
print(pd.DataFrame(rows).to_string(index=False))

print("\n=== (b) FLAG side: labeled stretches feature table ===")
def stretch(uid, t0, t1, label):
    g = df[(df.user_id == uid)]
    m = g[(pd.to_datetime(g.ts_utc, utc=True, format="mixed") >= pd.Timestamp(t0, tz="UTC")) &
          (pd.to_datetime(g.ts_utc, utc=True, format="mixed") <= pd.Timestamp(t1, tz="UTC"))]
    if not len(m):
        return None
    return dict(user=uid, label=label, t0=t0, n=len(m),
                bg=round(m.bg.mean()), innov=round(m.innov.mean(), 2),
                innov30=round(m.innov30.mean(), 2), iob=round(m.iob.mean(), 2),
                insreq=round(m.insreq.mean(), 2))

LABELED = [
    ("tim", "2026-07-06 13:38", "2026-07-06 14:43", "UNDER-ABSORPTION (Episode B)"),
    ("tim", "2026-07-06 10:03", "2026-07-06 10:33", "correct-restraint (Episode A)"),
    ("H",   "2026-07-02 11:23", "2026-07-02 12:53", "correct-restraint (H)"),
    ("H",   "2026-07-03 09:54", "2026-07-03 10:44", "correct-restraint (H)"),
    ("H",   "2026-07-05 11:29", "2026-07-05 12:48", "correct-restraint (H)"),
    ("H",   "2026-07-05 16:39", "2026-07-05 17:09", "correct-restraint (H)"),
    ("H",   "2026-07-06 04:14", "2026-07-06 06:44", "correct-restraint (H)"),
]
rows = [r for r in (stretch(*a) for a in LABELED) if r]
# auto-detected compression artifacts (night, sharp drop then rebound)
for uid, g in df.groupby("user_id"):
    g = g.reset_index(drop=True)
    hits = 0
    for i in range(2, len(g) - 4):
        if (not g.day.iloc[i]) and pd.notna(g.delta5.iloc[i]) and g.delta5.iloc[i] <= -25:
            fw = g.iloc[i + 1:i + 5]
            if (fw.delta5 >= 15).any():
                rows.append(dict(user=uid, label="sensor-artifact (compression)",
                                 t0=str(g.ts_utc.iloc[i])[:16], n=4,
                                 bg=round(g.bg.iloc[i]), innov=round(g.innov.iloc[i:i + 4].mean(), 2),
                                 innov30=round(g.innov30.iloc[i:i + 4].mean(), 2),
                                 iob=round(g.iob.iloc[i], 2), insreq=np.nan))
                hits += 1
                if hits >= 2:
                    break
# site age for tim's stretches from NS treatments
try:
    url = ("https://<REDACTED_NS_HOST>/api/v1/treatments.json?count=200"
           "&find[eventType][$regex]=Site|Insulin&find[created_at][$gte]=2026-06-25"
           "&token=<REDACTED_TOKEN>")
    tx = json.load(urllib.request.urlopen(url, timeout=30))
    site_changes = sorted(pd.Timestamp(t["created_at"]) for t in tx
                          if "Site" in (t.get("eventType") or "") or "Cannula" in (t.get("eventType") or ""))
    for r in rows:
        if r["user"] == "tim":
            t0 = pd.Timestamp(r["t0"], tz="UTC")
            prior = [s for s in site_changes if s <= t0]
            r["site_age_h"] = round((t0 - prior[-1]).total_seconds() / 3600, 1) if prior else np.nan
except Exception as e:
    print(f"[warn] NS treatments unavailable: {e}")

F = pd.DataFrame(rows)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(out, exist_ok=True)
F.to_csv(f"{out}/flag_feature_table.csv", index=False)
print(F.to_string(index=False))
print("\nNOTE: n(true under-absorption)=1 — no AUC is honest at this n. If Episode B's")
print("innovation does not visibly separate from the correct-restraint stretches, the")
print("flag stays evidence-free and V7 ships damper-only (per the red-team design).")
