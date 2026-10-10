#!/usr/bin/env python3
"""Forward-looking stress of the 6.0U/60min cumulative cap:
(a) rolling-60 stats of DELIVERED SMBs across full 28d (incl. V1 era, when caps were looser),
(b) rolling-60 of the base-oref DEMAND stream (v1_units, dedup 5-min, NULL->0),
(c) post-cap-raise window for H (1.2->1.8/6.0) and F (0.8/2.5),
(d) budget headroom: how big can a confirm shot get (budget*1.8)."""
import json
from datetime import datetime, timedelta, timezone
import psycopg2

S = "/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad"
NOW = datetime(2026, 7, 6, 10, 15, tzinfo=timezone.utc)
conn = psycopg2.connect(host="127.0.0.1", port=5432, dbname="oref")
cur = conn.cursor()

def ts(t): return datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))

def roll60_stats(events, label):
    if not events:
        print(f"  {label}: no events"); return
    vols = []
    for t, a in events:
        vols.append((t, sum(x for tt, x in events if t - timedelta(minutes=60) < tt <= t)))
    v = sorted(x for _, x in vols)
    import statistics as st
    n = len(v)
    def pct(p):
        i = min(n-1, int(p/100*(n-1))); return v[i]
    over = [(t, vol) for t, vol in vols if vol > 6.0]
    print(f"  {label}: n={n} max={v[-1]:.2f} p99={pct(99):.2f} p95={pct(95):.2f} p75={pct(75):.2f}; hrs>6.0: {len(over)}")
    for t, vol in over[:12]:
        print(f"     >6: {t:%m-%d %H:%M}Z vol={vol:.2f}")

for tag in ("F", "H"):
    print(f"\n================ {tag} ================")
    tr = json.load(open(f"{S}/mig_{tag}_treatments_28d.json"))
    smbs = sorted([(ts(t), t["insulin"]) for t in tr if t.get("insulin") and t.get("type") == "SMB" and t["insulin"] > 0])
    seen, ded = set(), []
    for t, a in smbs:
        k = (t.replace(second=0, microsecond=0), a)
        if k in seen: continue
        seen.add(k); ded.append((t, a))
    smbs = ded
    era = {"F": datetime(2026,6,29,13,47, tzinfo=timezone.utc), "H": datetime(2026,6,30,12,28, tzinfo=timezone.utc)}[tag]
    print("(a) delivered SMB rolling-60:")
    roll60_stats([e for e in smbs if e[0] < era], "V1 era (28d start ->" + str(era.date()) + ")")
    roll60_stats([e for e in smbs if e[0] >= era], "V6-ACTIVE era")
    raisep = {"F": datetime(2026,7,5,9,37, tzinfo=timezone.utc), "H": datetime(2026,7,5,12,19, tzinfo=timezone.utc)}[tag]
    roll60_stats([e for e in smbs if e[0] >= raisep], "post-cap-raise (07-05 ->)")

    # (b) base-oref demand stream from decisions: dedup last per 5-min bucket
    cur.execute("""
      WITH d AS (
        SELECT DISTINCT ON (div(ts_epoch, 300)) ts_utc, coalesce(v1_units, 0) v1u
        FROM boost_decisions WHERE user_id=%s AND ts_utc >= %s
        ORDER BY div(ts_epoch, 300), ts_utc DESC)
      SELECT ts_utc, v1u FROM d WHERE v1u > 0 ORDER BY ts_utc""", (tag, NOW - timedelta(days=28)))
    demand = [(r[0].astimezone(timezone.utc), r[1]) for r in cur.fetchall()]
    print("(b) base-oref DEMAND (v1_units>0, dedup 5-min) rolling-60:")
    roll60_stats([e for e in demand if e[0] < era], "V1 era")
    roll60_stats([e for e in demand if e[0] >= era], "V6-ACTIVE era")

    # (d) budget headroom -> max plausible confirm shot = budget*1.8 (vf<=1)
    cur.execute("""SELECT max(boostv5_budget), percentile_cont(0.99) WITHIN GROUP (ORDER BY boostv5_budget)
                   FROM boost_decisions WHERE user_id=%s AND boostv5_budget IS NOT NULL""", (tag,))
    mx, p99 = cur.fetchone()
    print(f"(d) boostv5_budget: max={mx:.2f} p99={p99:.2f} -> max shot ~= {mx*1.8:.2f}U (x1.8, vf<=1)")
conn.close()
