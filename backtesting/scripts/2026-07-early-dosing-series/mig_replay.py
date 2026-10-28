#!/usr/bin/env python3
"""Cumulative-cap tightening replay (10 -> 6.0) for F and H over their V6-ACTIVE eras.
Cascaded rolling-60min simulation on the actual delivered SMB stream (NS treatments),
with decision-row context + CGM outcomes for every newly-suppressed delivery."""
import json
from datetime import datetime, timedelta, timezone
import psycopg2

S = "/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad"
ERA = {"F": datetime(2026, 6, 29, 13, 47, 1, tzinfo=timezone.utc),
       "H": datetime(2026, 6, 30, 12, 28, 58, tzinfo=timezone.utc)}
NEWCAP = {"F": 6.0, "H": 6.0}
OLDCAP = 10.0

conn = psycopg2.connect(host="127.0.0.1", port=5432, dbname="oref")
cur = conn.cursor()

def ts(t):
    return datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))

def sim(events, cap):
    """events: list of (t, amount). Gate: if sum delivered in (t-60m, t) >= cap -> suppress.
    Returns (delivered, suppressed) lists."""
    delivered, suppressed = [], []
    for t, a in events:
        vol = sum(x for tt, x in delivered if tt > t - timedelta(minutes=60))
        if cap > 0 and vol >= cap:
            suppressed.append((t, a, vol))
        else:
            delivered.append((t, a))
    return delivered, suppressed

def cgm_window(user, t0, t1):
    cur.execute("""SELECT min(cgm_mgdl), max(cgm_mgdl) FROM boost_cgm
                   WHERE user_id=%s AND ts_utc > %s AND ts_utc <= %s AND cgm_mgdl >= 1""",
                (user, t0, t1))
    return cur.fetchone()

def ctx(user, t):
    cur.execute("""SELECT boostv5_state, cgm_mgdl, sug_eventualbg, sug_iob, sug_cob
                   FROM boost_decisions WHERE user_id=%s AND ts_utc BETWEEN %s AND %s
                   ORDER BY abs(extract(epoch from ts_utc - %s)) LIMIT 1""",
                (user, t - timedelta(minutes=8), t + timedelta(minutes=8), t))
    return cur.fetchone() or (None,)*5

for tag in ("F", "H"):
    tr = json.load(open(f"{S}/mig_{tag}_treatments_28d.json"))
    smbs = sorted([(ts(t), t["insulin"]) for t in tr
                   if t.get("insulin") and t.get("type") == "SMB" and t["insulin"] > 0
                   and ts(t) >= ERA[tag]])
    # dedup exact duplicates (same minute+amount)
    seen, ded = set(), []
    for t, a in smbs:
        k = (t.replace(second=0, microsecond=0), a)
        if k in seen: continue
        seen.add(k); ded.append((t, a))
    smbs = ded
    total_u = sum(a for _, a in smbs)
    days = (smbs[-1][0] - smbs[0][0]).total_seconds() / 86400 if smbs else 0

    # actual rolling-60 volume stats
    vols = []
    for i, (t, a) in enumerate(smbs):
        vol = sum(x for tt, x in smbs if t - timedelta(minutes=60) < tt <= t)
        vols.append(vol)
    over6 = sum(1 for v in vols if v > 6.0)
    over10 = sum(1 for v in vols if v > 10.0)

    del_old, sup_old = sim(smbs, OLDCAP)
    del_new, sup_new = sim(smbs, NEWCAP[tag])

    print(f"\n================ {tag} — V6-ACTIVE era {ERA[tag].date()} → now ({days:.1f} d) ================")
    print(f"SMB deliveries: n={len(smbs)}  total={total_u:.1f}U  ({total_u/max(days,0.01):.1f} U/day via SMB)")
    print(f"Actual rolling-60min volume: max={max(vols) if vols else 0:.2f}U  cycles with trailing-60 vol>6: {over6}  >10: {over10}")
    print(f"Sim cap {OLDCAP}: suppressed {len(sup_old)} ({sum(a for _,a,_ in sup_old):.2f}U)")
    print(f"Sim cap {NEWCAP[tag]}: suppressed {len(sup_new)} ({sum(a for _,a,_ in sup_new):.2f}U)"
          f" = {100*sum(a for _,a,_ in sup_new)/total_u:.1f}% of era SMB insulin")

    # classify each newly suppressed delivery
    print("Newly suppressed deliveries (cap 6 sim), context + outcome:")
    prot, costly, neutral = 0, 0, 0
    sup_detail = []
    for t, a, vol in sup_new:
        state, cgm, ebg, iob, cob = ctx(tag, t)
        mn2, mx2 = cgm_window(tag, t, t + timedelta(hours=2))
        cls = "protective" if (mn2 or 999) < 70 else ("costly" if (mn2 or 0) > 140 and (mx2 or 0) > 180 else "neutral")
        if cls == "protective": prot += 1
        elif cls == "costly": costly += 1
        else: neutral += 1
        sup_detail.append((t, a, vol, state, cgm, mn2, mx2, cls))
        print(f"  {t:%m-%d %H:%M}Z  {a:.2f}U (vol60={vol:.2f}) state={state} BG={cgm} -> 2h min/max {mn2}/{mx2}  [{cls}]")
    print(f"Split: protective={prot} costly={costly} neutral={neutral}")

    # follow-on starvation: suppressions within 60 min after a 'big' shot (>=1.5U)
    bigs = [(t, a) for t, a in smbs if a >= 1.5]
    print(f"\nBig shots >=1.5U: n={len(bigs)} (max {max((a for _,a in bigs), default=0):.2f}U)")
    n_starve = 0
    for t, a, vol, *_ in sup_new:
        if any(t - timedelta(minutes=60) < tb <= t for tb, ab in bigs if ab >= 1.5):
            n_starve += 1
    print(f"Suppressed-cycles within 60min after a >=1.5U shot: {n_starve}/{len(sup_new)}")

    # hours after big shots: how much SMB flowed in the next 60 min historically
    for thr in (1.5, 2.0):
        follows = []
        for tb, ab in [(t, a) for t, a in smbs if a >= thr]:
            f = sum(x for tt, x in smbs if tb < tt <= tb + timedelta(minutes=60))
            follows.append((ab, f))
        if follows:
            import statistics as st
            fs = [f for _, f in follows]
            print(f"After shots >={thr}U (n={len(follows)}): follow-on SMB next 60min "
                  f"mean={st.mean(fs):.2f}U median={st.median(fs):.2f}U max={max(fs):.2f}U; "
                  f"hours where shot+follow-on > 6.0: {sum(1 for a, f in follows if a + f > 6.0)}")
conn.close()
