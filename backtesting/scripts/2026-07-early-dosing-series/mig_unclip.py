#!/usr/bin/env python3
"""(1) F: confirmedCap 2.5->6.0 unclip — CONFIRMED cycles clipped at 2.5, added-insulin estimate
   (shot = budget*1.8*vf, vf in [0.4,1.0]), pre-low harm pricing vs base rate.
   (2) F: committedCap counterfactuals — cycles pinned at 0.5 (pre-07-05) / 0.8 (post): what the
   formula value (0.93) would have added had migration applied it (it will NOT — user-set 0.8).
   (3) H: confirm-shot tail — budget distribution in CONFIRMED cycles -> how often could a shot
   reach the 6.0 cumulative cap in one go."""
from datetime import timedelta, timezone, datetime
import psycopg2

conn = psycopg2.connect(host="127.0.0.1", port=5432, dbname="oref")
cur = conn.cursor()

def cgm_min_after(user, t, hrs=2):
    cur.execute("""SELECT min(cgm_mgdl) FROM boost_cgm WHERE user_id=%s AND ts_utc > %s
                   AND ts_utc <= %s AND cgm_mgdl >= 1""", (user, t, t + timedelta(hours=hrs)))
    return cur.fetchone()[0]

# ---------- (1) F confirm unclip ----------
cur.execute("""
  WITH d AS (
    SELECT DISTINCT ON (div(ts_epoch,300)) *
    FROM boost_decisions WHERE user_id='F' AND boostv5_active AND boostv5_state='CONFIRMED'
    ORDER BY div(ts_epoch,300), ts_utc DESC)
  SELECT ts_utc, boostv5_finaldose, boostv5_budget, cgm_mgdl, coalesce(v1_units,0)
  FROM d WHERE boostv5_finaldose > 0 ORDER BY ts_utc""")
rows = cur.fetchall()
clipped = [r for r in rows if abs(r[1] - 2.5) < 0.01]
print(f"F CONFIRMED dosed cycles (dedup): {len(rows)}; clipped at 2.5: {len(clipped)}")
add_lo = add_hi = 0.0
pre_low = 0
for t, fd, bud, cgm, v1u in clipped:
    shot_hi = bud * 1.8            # vf=1
    shot_lo = bud * 1.8 * 0.4      # vf=0.4
    a_hi = max(0.0, min(6.0, shot_hi) - 2.5)
    a_lo = max(0.0, min(6.0, shot_lo) - 2.5)
    add_lo += a_lo; add_hi += a_hi
    mn = cgm_min_after('F', t)
    low = (mn or 999) < 70
    pre_low += low
    print(f"  {t}  BG={cgm} budget={bud:.2f} shot∈[{shot_lo:.2f},{shot_hi:.2f}] added∈[{a_lo:.2f},{a_hi:.2f}]U  2h-min={mn} {'<70 !' if low else ''}")
print(f"F unclip totals: added insulin ∈ [{add_lo:.2f}, {add_hi:.2f}]U across {len(clipped)} cycles; followed-by-<70 within 2h: {pre_low}/{len(clipped)}")

# base rate: fraction of ALL dosed V6 cycles followed by <70 in 2h
cur.execute("""
  WITH d AS (
    SELECT DISTINCT ON (div(ts_epoch,300)) ts_utc
    FROM boost_decisions WHERE user_id='F' AND boostv5_active AND boostv5_finaldose > 0
    ORDER BY div(ts_epoch,300), ts_utc DESC)
  SELECT ts_utc FROM d""")
all_dosed = [r[0] for r in cur.fetchall()]
base_low = sum(1 for t in all_dosed if (cgm_min_after('F', t) or 999) < 70)
print(f"F base rate: {base_low}/{len(all_dosed)} dosed cycles followed by <70 within 2h ({100*base_low/len(all_dosed):.1f}%)")

# ---------- (2) F committedCap pin counts ----------
for cap, lo, hi in ((0.5, '2026-06-29', '2026-07-05 09:37+00'), (0.8, '2026-07-05 09:37+00', '2026-07-07')):
    cur.execute("""
      WITH d AS (
        SELECT DISTINCT ON (div(ts_epoch,300)) *
        FROM boost_decisions WHERE user_id='F' AND boostv5_active AND boostv5_state='COMMITTED'
          AND ts_utc >= %s AND ts_utc < %s
        ORDER BY div(ts_epoch,300), ts_utc DESC)
      SELECT count(*) FILTER (WHERE boostv5_finaldose > 0),
             count(*) FILTER (WHERE abs(boostv5_finaldose - %s) < 0.01),
             sum(greatest(0, least(coalesce(v1_units,0), 0.93) - boostv5_finaldose))
               FILTER (WHERE abs(boostv5_finaldose - %s) < 0.01)
      FROM d""", (lo, hi, cap, cap))
    n, pinned, added = cur.fetchone()
    print(f"F COMMITTED era cap={cap}: dosed={n} pinned-at-cap={pinned} extra-if-0.93 (min(v1_units,0.93)-cap, floor 0) = {added or 0:.2f}U")

# ---------- (3) H confirm tail ----------
cur.execute("""
  WITH d AS (
    SELECT DISTINCT ON (div(ts_epoch,300)) *
    FROM boost_decisions WHERE user_id='H' AND boostv5_state='CONFIRMED'
    ORDER BY div(ts_epoch,300), ts_utc DESC)
  SELECT count(*), max(boostv5_budget), percentile_cont(0.95) WITHIN GROUP (ORDER BY boostv5_budget),
         count(*) FILTER (WHERE boostv5_budget*1.8 >= 6.0),
         count(*) FILTER (WHERE boostv5_budget*1.8 >= 4.0)
  FROM d""")
n, mx, p95, ge6, ge4 = cur.fetchone()
print(f"\nH CONFIRMED cycles (dedup, incl. shadow era): n={n} budget max={mx:.2f} p95={p95:.2f}")
print(f"  cycles where uncapped shot (budget*1.8, vf=1) >= 6.0U: {ge6}   >= 4.0U: {ge4}")
conn.close()
