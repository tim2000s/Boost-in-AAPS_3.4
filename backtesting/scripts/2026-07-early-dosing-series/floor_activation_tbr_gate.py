#!/usr/bin/env python3
"""Re-validation supplement (2026-07-08): per-user activation TBR gate for the composed floor.

Items 4 & 5 of the promotion re-validation:
 4. Per-user 14d + 30d TBR<70 and TBR<54 (the manual two-test-bar activation basis).
 5. The SHIPPED code gate: trailing-14d time-below-63 mg/dL (3.5 mmol) < 2.0% → floor engages.
    Confirm it reproduces the manual A/E/F/tim-GO / B/C/D-HOLD verdict; flag any disagreement.

Glycemia from boost_cgm (dense) to t=now. Deterministic. Numbers only.
"""
import os
import psycopg2, pandas as pd, numpy as np

MANUAL = {"A":"GO","E":"GO","F":"GO","tim":"GO","B":"HOLD","C":"HOLD","D":"HOLD"}
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
now = pd.read_sql("SELECT max(ts_utc) m FROM boost_cgm", conn).m.iloc[0]
rows = []
for u in ["tim","A","B","C","D","E","F","H"]:
    d = pd.read_sql("""
      SELECT ts_utc, cgm_mgdl bg FROM boost_cgm
      WHERE user_id=%s AND cgm_mgdl IS NOT NULL AND ts_utc > %s::timestamptz - interval '30 days'
    """, conn, params=(u, str(now)))
    if not len(d):
        rows.append(dict(user=u, note="no cgm")); continue
    d["ts"] = pd.to_datetime(d.ts_utc, utc=True)
    now_utc = pd.Timestamp(now); now_utc = now_utc.tz_localize("UTC") if now_utc.tzinfo is None else now_utc.tz_convert("UTC")
    t14 = d[d.ts > (now_utc - pd.Timedelta(days=14))]
    def r(s, thr): return round(100*(s < thr).mean(), 2)
    rows.append(dict(
        user=u, n30=len(d), n14=len(t14),
        tbr70_14=r(t14.bg,70), tbr63_14=r(t14.bg,63), tbr54_14=r(t14.bg,54),
        tbr70_30=r(d.bg,70), tbr54_30=r(d.bg,54),
    ))
conn.close()
T = pd.DataFrame(rows)
# code gate: 14d TBR<63 < 2.0% -> engage
T["code_gate"] = np.where(T.tbr63_14 < 2.0, "ENGAGE", "SUPPRESS")
T["manual"] = T.user.map(MANUAL).fillna("(n/a: H)")
T["agree"] = np.where(T.user=="H", "-", np.where(
    ((T.code_gate=="ENGAGE") & (T.manual=="GO")) | ((T.code_gate=="SUPPRESS") & (T.manual=="HOLD")),
    "OK", "*** DISAGREE ***"))
pd.set_option("display.width", 200)
print(f"data to t={now}")
print("\n=== item 4/5: per-user TBR + code-gate vs manual verdict ===")
print(T[["user","n14","tbr70_14","tbr63_14","tbr54_14","tbr70_30","tbr54_30","code_gate","manual","agree"]].to_string(index=False))
dis = T[(T.agree=="*** DISAGREE ***")]
print(f"\nDISAGREEMENTS: {len(dis)}" + ("" if not len(dis) else " -> "+", ".join(dis.user)))
T.to_csv(os.path.expanduser("~/StudioProjects/Boost-AAPS-core/backtesting/scripts/2026-07-early-dosing-series/floor_activation_tbr_gate.csv"), index=False)
print("[written] floor_activation_tbr_gate.csv")
