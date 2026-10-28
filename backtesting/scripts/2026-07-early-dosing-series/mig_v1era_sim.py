#!/usr/bin/env python3
"""Cascaded cap sim (6.0 vs 10.0) on the V1-era delivered SMB stream — the best proxy for what
flows once per-shot caps stop under-dosing (H raised to 1.8/6.0 on 07-05/06).
Outcomes: CGM min/max 2h after each suppressed shot; episode grouping."""
import json
from datetime import datetime, timedelta, timezone
import psycopg2

S = "/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad"
conn = psycopg2.connect(host="127.0.0.1", port=5432, dbname="oref")
cur = conn.cursor()

def ts(t): return datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))

def sim(events, cap):
    delivered, suppressed = [], []
    for t, a in events:
        vol = sum(x for tt, x in delivered if tt > t - timedelta(minutes=60))
        if cap > 0 and vol >= cap:
            suppressed.append((t, a, vol))
        else:
            delivered.append((t, a))
    return delivered, suppressed

def cgm_win(user, t0, t1):
    cur.execute("""SELECT min(cgm_mgdl), max(cgm_mgdl) FROM boost_cgm
                   WHERE user_id=%s AND ts_utc > %s AND ts_utc <= %s AND cgm_mgdl >= 1""", (user, t0, t1))
    return cur.fetchone()

ERA = {"F": datetime(2026,6,29,13,47, tzinfo=timezone.utc), "H": datetime(2026,6,30,12,28, tzinfo=timezone.utc)}
for tag in ("F", "H"):
    tr = json.load(open(f"{S}/mig_{tag}_treatments_28d.json"))
    smbs = sorted([(ts(t), t["insulin"]) for t in tr if t.get("insulin") and t.get("type") == "SMB" and t["insulin"] > 0])
    seen, ded = set(), []
    for t, a in smbs:
        k = (t.replace(second=0, microsecond=0), a)
        if k in seen: continue
        seen.add(k); ded.append((t, a))
    v1era = [e for e in ded if e[0] < ERA[tag]]
    total = sum(a for _, a in v1era)
    days = (v1era[-1][0] - v1era[0][0]).total_seconds()/86400 if v1era else 0
    print(f"\n============ {tag} V1-era stream ({v1era[0][0].date()} -> {ERA[tag].date()}, {days:.1f}d, {len(v1era)} SMBs, {total:.1f}U) ============")
    for cap in (10.0, 6.0):
        d, s = sim(v1era, cap)
        print(f" cap {cap}: suppressed {len(s)} shots, {sum(a for _,a,_ in s):.2f}U ({100*sum(a for _,a,_ in s)/total:.1f}% of SMB insulin)")
        if cap == 6.0:
            # group into episodes (gap > 90 min = new episode)
            eps, curep = [], []
            for t, a, vol in s:
                if curep and (t - curep[-1][0]).total_seconds() > 5400:
                    eps.append(curep); curep = []
                curep.append((t, a, vol))
            if curep: eps.append(curep)
            prot = cost = neut = 0
            for ep in eps:
                t0, t1 = ep[0][0], ep[-1][0]
                u = sum(a for _, a, _ in ep)
                mn, mx = cgm_win(tag, t0, t1 + timedelta(hours=2))
                mn0, mx0 = cgm_win(tag, t0 - timedelta(minutes=15), t0)
                cls = "PROTECTIVE(low followed)" if (mn or 999) < 70 else ("COSTLY(stayed high)" if (mn or 0) > 140 else "neutral")
                if "PROT" in cls: prot += 1
                elif "COST" in cls: cost += 1
                else: neut += 1
                print(f"   episode {t0:%m-%d %H:%M}Z..{t1:%H:%M}Z: {len(ep)} shots {u:.2f}U suppressed | BG at start ~{mx0} | next-2h min/max {mn}/{mx} [{cls}]")
            print(f"   episode split: protective={prot} costly={cost} neutral={neut}")
conn.close()
