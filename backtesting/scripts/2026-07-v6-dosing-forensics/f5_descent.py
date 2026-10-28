#!/usr/bin/env python3
"""
FORENSIC 5 — is V1's plateau advantage generated in the DESCENT (through-peak, high-IOB), and does
V6's composed brake cut it there? Two views:

(A) SAME-CYCLE (cleanest — identical trajectory): on V6 descent cycles (falling, IOB present),
    compare finalDose vs v1_units (what V1 would dose on this exact state) by BG band, and show the
    brake cut (doseAfterCaps → doseAfterBrakes). If v1_units > finalDose and the gap = the brake cut,
    V6 is under-dosing the descent BECAUSE of the brake — the fix target.
(B) MEAL-ALIGNED (transition window, both algorithms): delivered insulin in t0–30 (rise/front-load)
    vs t30–90 (descent) for V1-onset vs V6-onset meals. Confirms V1 delivers more in the DESCENT
    window, not the rise.
"""
import numpy as np, psycopg2
from collections import defaultdict
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
USERS = ['tim', 'F', 'B', 'A', 'C', 'H']
MEAL = "reason_text ~ 'sleep=AWAKE' and reason_text !~ 'suppressed \\(SLEEPING\\)'"

# ---- (A) same-cycle descent, by BG band ----
cur.execute(f"""with c as (
  select d.*, d.cgm_mgdl - lag(d.cgm_mgdl,3) over (partition by d.user_id order by d.ts_epoch) as d15
  from boost_decisions d where d.user_id=any(%s) and variant='boost-other' and {MEAL} and cgm_mgdl is not null)
  select cgm_mgdl, iob_iob, boostv5_finaldose, v1_units, boostv5_doseaftercaps, boostv5_doseafterbrakes, d15
  from c where d15 < -1 and iob_iob > 1.5 and boostv5_finaldose is not null and v1_units is not null""", (USERS,))
rows = cur.fetchall()
print(f"(A) SAME-CYCLE descent (falling, IOB>1.5): {len(rows)} cycles")
print(f"{'BG band':<12}{'n':>6}{'V1 would':>10}{'V6 dosed':>10}{'V1−V6':>8}{'brake cut':>11}{'%V6<V1':>8}")
for lab, lo, hi in [('135-150', 135, 150), ('150-165', 150, 165), ('165-180', 165, 180), ('>180', 180, 400)]:
    s = [r for r in rows if lo <= r[0] < hi]
    if len(s) < 25: continue
    v1 = np.mean([r[3] for r in s]); v6 = np.mean([r[2] for r in s])
    cut = np.nanmean([(r[4] - r[5]) for r in s if r[4] is not None and r[5] is not None])
    below = 100 * np.mean([r[2] < r[3] - 0.02 for r in s])
    print(f"{lab:<12}{len(s):>6}{v1:>10.3f}{v6:>10.3f}{v1-v6:>+8.3f}{cut:>11.3f}{below:>7.0f}%")

# ---- (B) meal-aligned rise vs descent delivery ----
WIN = "ts_utc at time zone 'Europe/London' between '2026-06-18' and '2026-07-12'"
cur.execute("select user_id,ts_epoch,cgm_mgdl from boost_decisions where user_id=any(%s) and cgm_mgdl is not null order by 1,2", (USERS,))
tmp = defaultdict(list)
for u, e, g in cur.fetchall(): tmp[u].append((e, g))
S = {u: (np.array([x[0] for x in v], float), np.array([x[1] for x in v], float)) for u, v in tmp.items()}
def bg_at(u, e, tol=400):
    ep, g = S[u]; i = np.searchsorted(ep, e)
    cand = [j for j in (i - 1, i, i + 1) if 0 <= j < len(ep) and abs(ep[j] - e) < tol]
    return g[min(cand, key=lambda j: abs(ep[j] - e))] if cand else np.nan
cur.execute(f"""select user_id,ts_epoch, case when variant='boost-other' then 'V6' else 'V1' end alg,
   case when variant='boost-other' then boostv5_finaldose else v1_units end dose
   from boost_decisions where user_id=any(%s) and (variant='boost-other' or variant in ('v1','v1-silent'))
   and {MEAL} and {WIN} order by 1,2""", (USERS,))
dser = defaultdict(list)
for u, e, a, d in cur.fetchall(): dser[u].append((e, a, d or 0.0))
DS = {u: (np.array([x[0] for x in v], float), np.array([x[1] for x in v], object), np.array([x[2] for x in v], float)) for u, v in dser.items()}
def dose_sum(u, e0, e1):
    ep, a, d = DS[u]; m = (ep >= e0) & (ep < e1); return d[m].sum(), (a[m][0] if m.any() else None)
def alg_at(u, e, tol=400):
    ep, a, d = DS[u]; i = np.searchsorted(ep, e)
    c = [j for j in (i - 1, i, i + 1) if 0 <= j < len(ep) and abs(ep[j] - e) < tol]
    return a[min(c, key=lambda j: abs(ep[j] - e))] if c else None
res = {'V1': {'rise': [], 'desc': []}, 'V6': {'rise': [], 'desc': []}}
for u in USERS:
    ep, g = S[u]; last = -1e9
    for i in range(6, len(ep)):
        if ep[i] - ep[i - 1] > 400: continue
        if g[i] > 140 and g[i - 1] <= 140 and np.nanmin(g[max(0, i - 6):i + 1]) <= 130 and (ep[i] - last) > 5400:
            e = ep[i]; last = e; a = alg_at(u, e)
            if a is None: continue
            rise, _ = dose_sum(u, e, e + 1800)         # t0-30
            desc, _ = dose_sum(u, e + 1800, e + 5400)  # t30-90 (through-peak + descent)
            res[a]['rise'].append(rise); res[a]['desc'].append(desc)
print(f"\n(B) MEAL-ALIGNED delivered insulin (transition window):")
print(f"{'algo':<5}{'n':>5}{'rise t0-30':>12}{'descent t30-90':>16}")
for a in ('V1', 'V6'):
    print(f"{a:<5}{len(res[a]['rise']):>5}{np.mean(res[a]['rise']):>12.2f}{np.mean(res[a]['desc']):>16.2f}")
dv = np.mean(res['V1']['desc']) - np.mean(res['V6']['desc']); rv = np.mean(res['V1']['rise']) - np.mean(res['V6']['rise'])
print(f"V1−V6  rise {rv:+.2f}U   descent {dv:+.2f}U   -> V1's extra insulin is in the {'DESCENT' if dv>rv else 'RISE'}")
print("\nREAD: if v1_units>finalDose in the descent bands AND the gap ~ the brake cut, the fix is to relax")
print("the composed brake in the falling-with-IOB descent; (B) confirms V1's edge is descent, not rise.")
conn.close()
