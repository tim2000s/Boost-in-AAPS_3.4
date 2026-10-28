#!/usr/bin/env python3
"""
FOUNDATION 3 — does the −7.5 meal-window regression survive including H and E (the 2 best performers
excluded for missing sleep telemetry)? Redo the V1→V6 meal-window TING with a CLOCK-daytime proxy
(09:00–22:00, transition window 18 Jun–12 Jul, season-controlled) applied consistently to ALL 7 users.
Validate the proxy: the 5-telemetry-user clock result should ≈ the telemetry result (−5.6..−7.5). Then
the 7-user clock number tells us whether H/E dilute it. Per-user, median across users. Standalone.
"""
import numpy as np, psycopg2
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
USERS = ['tim', 'F', 'B', 'A', 'C', 'H', 'E']; TEL5 = ['tim', 'F', 'B', 'A', 'C']
WIN = "ts_utc at time zone 'Europe/London' between '2026-06-18' and '2026-07-12'"
DAY = "extract(hour from ts_utc at time zone 'Europe/London') between 9 and 21"
def ting(where):
    cur.execute(f"select cgm_mgdl from boost_decisions where {where} and cgm_mgdl is not null and {DAY} and {WIN}")
    g = np.array([r[0] for r in cur.fetchall()], float)
    return (100 * np.mean((g >= 63) & (g <= 140)), len(g)) if len(g) >= 150 else (np.nan, len(g))
print(f"{'user':<5}{'V1 dayTING':>12}{'V6 dayTING':>12}{'Δ':>7}{'  (nV1/nV6)':>16}")
deltas = {}
for u in USERS:
    v1, n1 = ting(f"user_id='{u}' and variant in ('v1','v1-silent')")
    v6, n6 = ting(f"user_id='{u}' and variant='boost-other'")
    d = v6 - v1 if not (np.isnan(v1) or np.isnan(v6)) else np.nan
    deltas[u] = d
    print(f"{u:<5}{v1:>12.1f}{v6:>12.1f}{d:>+7.1f}   ({n1}/{n6})")
d5 = [deltas[u] for u in TEL5 if not np.isnan(deltas[u])]
d7 = [deltas[u] for u in USERS if not np.isnan(deltas[u])]
print(f"\n5 telemetry users — median Δ TING = {np.median(d5):+.1f}  (mean {np.mean(d5):+.1f})")
print(f"ALL 7 users        — median Δ TING = {np.median(d7):+.1f}  (mean {np.mean(d7):+.1f})   [{len(d7)} with data]")
print("H/E deltas:", {u: round(deltas[u], 1) for u in ['H', 'E'] if not np.isnan(deltas[u])})
print("\nREAD: if 5-user clock Δ ≈ the telemetry −5.6..−7.5, the proxy is fair. If ALL-7 median shrinks")
print("toward 0, H/E dilute the regression (it was partly selection); if it holds, the finding survives.")
conn.close()
