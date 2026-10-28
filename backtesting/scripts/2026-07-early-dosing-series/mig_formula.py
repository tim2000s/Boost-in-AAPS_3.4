#!/usr/bin/env python3
"""Replicate BoostV5AutoConfig.compute() for users F and H from NS treatments + DB CGM/TDD.
Windows: 14d (the formula's LOOKBACK_DAYS) and 28d sensitivity."""
import json
from datetime import datetime, timedelta, timezone
import psycopg2

S = "/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad"
NOW = datetime(2026, 7, 6, 10, 15, tzinfo=timezone.utc)

def percentile(vals, p):
    """Linear-interpolated percentile, mirrors BoostV5AutoConfig.percentile."""
    if not vals: return 0.0
    v = sorted(vals)
    if len(v) == 1: return v[0]
    idx = (p / 100.0) * (len(v) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(v) - 1)
    frac = idx - lo
    return v[lo] + (v[hi] - v[lo]) * frac

def clamp(x, lo, hi): return max(lo, min(hi, x))

def compute(tdd_median, manual, smb, tbr70, sev54):
    hypo_prone = sev54 > 1.5 or tbr70 > 6.0
    caution = clamp(1.0 + max(0.0, tbr70 - 4.0) / 4.0 + max(0.0, sev54 - 1.0) * 0.5, 1.0, 2.0)
    caution = round(caution, 1)
    if hypo_prone: agg = 0.85
    elif tbr70 > 4.0: agg = 0.92
    else: agg = 1.0
    confirmed = round(clamp(max(percentile(manual, 90), percentile(smb, 95)), 1.5, 7.5), 2)
    committed = round(clamp(max(percentile(smb, 75), tdd_median / 40.0), 0.25, 2.5), 2)
    cumulative = round(clamp(confirmed + 2.0 * committed, 1.0, max(5.0, confirmed)), 1)
    fastcarb = not hypo_prone
    floor = min(committed, 0.8 * confirmed)
    return dict(aggression=agg, hypoCaution=caution, confirmedCap=confirmed,
                committedCap=committed, cumulative=cumulative, fastCarbConfirm=fastcarb,
                confirmFloor=round(floor, 3), hypoProne=hypo_prone)

conn = psycopg2.connect(host="127.0.0.1", port=5432, dbname="oref")
cur = conn.cursor()

for tag in ("F", "H"):
    tr = json.load(open(f"{S}/mig_{tag}_treatments_28d.json"))
    for days in (14, 28):
        t0 = NOW - timedelta(days=days)
        def ts(t):
            s = t["created_at"].replace("Z", "+00:00")
            return datetime.fromisoformat(s)
        window = [t for t in tr if ts(t) >= t0]
        manual = [t["insulin"] for t in window if t.get("insulin") and t.get("type") == "NORMAL" and t["insulin"] > 0]
        smb = [t["insulin"] for t in window if t.get("insulin") and t.get("type") == "SMB" and t["insulin"] > 0]

        # TDD median: daily total from treatments = boluses + temp-basal delivery
        daily = {}
        for t in window:
            d = ts(t).date()
            daily.setdefault(d, [0.0, 0.0])
            if t.get("insulin") and t["insulin"] > 0:
                daily[d][0] += t["insulin"]
        # temp basal: absolute rate × actual duration (next TB truncates; approximate with recorded duration)
        tbs = sorted([t for t in window if t.get("eventType") == "Temp Basal"], key=ts)
        for i, t in enumerate(tbs):
            rate = t.get("absolute", t.get("rate"))
            if rate is None: continue
            dur = t.get("duration") or 0  # minutes
            tstart = ts(t)
            if i + 1 < len(tbs):
                gap = (ts(tbs[i+1]) - tstart).total_seconds() / 60.0
                dur = min(dur, gap)
            daily.setdefault(tstart.date(), [0.0, 0.0])
            daily[tstart.date()][1] += rate * dur / 60.0
        full_days = {d: b + tb for d, (b, tb) in daily.items() if d != NOW.date()}  # drop partial today
        tdd_treat = percentile(list(full_days.values()), 50)

        # TDD from DB column (AAPS-computed, matches TddCalculator input path better)
        cur.execute("""SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY dtdd) FROM (
                         SELECT date_trunc('day', ts_utc) d, percentile_cont(0.5) WITHIN GROUP (ORDER BY tdd) dtdd
                         FROM boost_decisions WHERE user_id=%s AND ts_utc >= %s AND ts_utc < %s AND tdd > 0
                         GROUP BY 1) x""", (tag, t0, NOW))
        tdd_db = cur.fetchone()[0] or 0.0

        # TBR from boost_cgm
        cur.execute("""SELECT count(*), count(*) FILTER (WHERE cgm_mgdl < 70 AND cgm_mgdl >= 1),
                              count(*) FILTER (WHERE cgm_mgdl < 54 AND cgm_mgdl >= 1)
                       FROM boost_cgm WHERE user_id=%s AND ts_utc >= %s AND ts_utc < %s""", (tag, t0, NOW))
        n, n70, n54 = cur.fetchone()
        tbr70 = 100.0 * n70 / n if n else 0.0
        sev54 = 100.0 * n54 / n if n else 0.0

        tdd = tdd_db if tdd_db > 0 else tdd_treat
        res = compute(tdd, manual, smb, tbr70, sev54)
        print(f"\n=== {tag} — {days}d window (to {NOW.isoformat()}) ===")
        print(f"  inputs: TDD_median(db)={tdd_db:.1f}U  TDD(treatments)={tdd_treat:.1f}U  (used {tdd:.1f})")
        print(f"          manual boluses n={len(manual)} p50={percentile(manual,50):.2f} p90={percentile(manual,90):.2f} max={max(manual) if manual else 0:.2f}")
        print(f"          SMBs n={len(smb)} p50={percentile(smb,50):.2f} p75={percentile(smb,75):.2f} p95={percentile(smb,95):.2f} max={max(smb) if smb else 0:.2f}")
        print(f"          CGM n={n}  TBR<70={tbr70:.2f}%  TBR<54={sev54:.2f}%")
        print(f"          TDD/40={tdd/40:.3f}")
        print(f"  derived: {res}")
conn.close()
