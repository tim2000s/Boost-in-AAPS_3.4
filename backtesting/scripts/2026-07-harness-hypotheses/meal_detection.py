#!/usr/bin/env python3
"""Thread 2 — can any signal DETECT an unannounced meal EARLIER than the loop's reactive BG-rise trigger?
The loop reacts when the BG delta climbs, so insulin is late. If a NON-CGM precursor (HR, activity) or the
curvature leads that trigger, earlier dosing is possible. If the BG rise is the earliest signal, the
meal-timing problem is fundamental.

Per user: meal onsets = a real excursion (BG rises through 130 from a <115 foot, awake, deduped). For each
meal, find the REACTIVE detection time t_react (first cycle in the run-up where the 5-min BG delta > +4).
Then measure when each candidate signal first fires and its LEAD = t_react − t_signal (min; +ve = earlier):
  - HR: hr_avg5m > resting + HR_MARGIN (a non-CGM precursor — the real hope)
  - accel: BG acceleration > A_THR (does curvature beat the delta threshold)
Plus the FALSE-ALARM rate: how often each signal fires with NO meal in the next 60 min.
Full history, all users. Bootstrap CI on the median lead."""
import numpy as np, psycopg2, pandas as pd
RNG = np.random.default_rng(0)
VARPRIO = {"boost-other": 0, "trio-shadow": 1, "v1": 2, "v2": 3, "v3": 4, "v1-silent": 5}
USERS = ["tim", "A", "B", "C", "D", "E", "F", "H", "G"]
HR_MARGIN = 12.0; A_THR = 2.5; DELTA_TRIG = 4.0

rows = []
allead_hr, allead_ac = [], []
with psycopg2.connect("dbname=oref host=127.0.0.1 port=5432") as conn:
    for u in USERS:
        d = pd.read_sql("""select ts_epoch, cgm_mgdl, hr_bpm_avg5m, hr_learned_resting_bpm, sleep_state, variant
            from boost_decisions where user_id=%s and cgm_mgdl is not null order by ts_epoch""", conn, params=(u,))
        d["prio"] = d.variant.map(VARPRIO).fillna(9); d["bucket"] = (d.ts_epoch // 300).astype(np.int64)
        d = d.sort_values(["bucket", "prio"]).drop_duplicates("bucket", keep="first").sort_values("ts_epoch").reset_index(drop=True)
        ep = d.ts_epoch.to_numpy(float); cgm = d.cgm_mgdl.to_numpy(float)
        hr = d.hr_bpm_avg5m.to_numpy(float); rest = d.hr_learned_resting_bpm.to_numpy(float)
        awake = (d.sleep_state.to_numpy() == "AWAKE"); n = len(d)
        rest_med = np.nanmedian(rest) if np.isfinite(np.nanmedian(rest)) else 60.0
        # per-cycle 5-min delta + acceleration
        dl = np.full(n, np.nan); ac = np.full(n, np.nan)
        for i in range(1, n):
            if ep[i]-ep[i-1] < 900: dl[i] = cgm[i]-cgm[i-1]
        for i in range(2, n):
            if np.isfinite(dl[i]) and np.isfinite(dl[i-1]): ac[i] = dl[i]-dl[i-1]
        # meal onsets
        onsets = []; last = -1e9
        for i in range(9, n):
            if ep[i]-ep[i-1] > 900: continue
            foot = np.nanmin(cgm[max(0, i-9):i+1])
            if cgm[i] > 130 and cgm[i-1] <= 130 and foot < 115 and awake[i] and (ep[i]-last) > 7200:
                onsets.append(i); last = ep[i]
        if len(onsets) < 15:
            continue
        leads_hr, leads_ac, hr_avail = [], [], 0
        for o in onsets:
            w = np.where((ep >= ep[o]-45*60) & (ep <= ep[o]))[0]           # 45-min run-up window
            # reactive detection: first cycle in the run-up with delta > DELTA_TRIG
            react = next((j for j in w if np.isfinite(dl[j]) and dl[j] > DELTA_TRIG), o)
            tr = ep[react]
            # HR lead
            hrw = [j for j in w if np.isfinite(hr[j]) and np.isfinite(rest[j] if np.isfinite(rest[j]) else rest_med)]
            if hrw:
                hr_avail += 1
                r = rest[o] if np.isfinite(rest[o]) else rest_med
                hj = next((j for j in w if np.isfinite(hr[j]) and hr[j] > r + HR_MARGIN), None)
                if hj is not None: leads_hr.append((tr - ep[hj]) / 60.0)
            aj = next((j for j in w if np.isfinite(ac[j]) and ac[j] > A_THR), None)
            if aj is not None: leads_ac.append((tr - ep[aj]) / 60.0)
        # false-alarm: HR crosses resting+margin but NO meal (onset) in next 60 min
        fa_fire = fa_meal = 0
        onset_ep = ep[onsets]
        for i in range(n):
            if awake[i] and np.isfinite(hr[i]) and hr[i] > (rest[i] if np.isfinite(rest[i]) else rest_med) + HR_MARGIN:
                fa_fire += 1
                if np.any((onset_ep > ep[i]) & (onset_ep <= ep[i]+60*60)): fa_meal += 1
        fa_rate = 100 * (1 - fa_meal / max(1, fa_fire))
        allead_hr += leads_hr; allead_ac += leads_ac
        rows.append((u, len(onsets), hr_avail,
                     np.median(leads_hr) if leads_hr else np.nan, 100*len(leads_hr)/max(1, hr_avail),
                     np.median(leads_ac) if leads_ac else np.nan, fa_rate))

print(f"{'user':>4} {'meals':>5} {'hrOK':>4} | {'HRlead(min)':>11} {'%HRleads':>8} | {'accLead':>7} {'HR-FA%':>6}")
for u, m, ho, lh, ph, la, fa in rows:
    print(f"{u:>4} {m:>5} {ho:>4} | {lh:>11.1f} {ph:>7.0f}% | {la:>7.1f} {fa:>5.0f}%")
def bootmed(x):
    if len(x) < 20: return (np.nan, np.nan, np.nan)
    b = [np.median(RNG.choice(x, len(x), replace=True)) for _ in range(2000)]
    return np.median(x), np.percentile(b, 2.5), np.percentile(b, 97.5)
mh, lo, hi = bootmed(allead_hr); ma, alo, ahi = bootmed(allead_ac)
print(f"\n  POOLED HR lead: median {mh:.1f} min [{lo:.1f}, {hi:.1f}]  (n={len(allead_hr)}; +ve = HR precedes the BG-rise trigger)")
print(f"  POOLED accel lead: median {ma:.1f} min [{alo:.1f}, {ahi:.1f}]  (n={len(allead_ac)})")
print(f"  → {'HR PRECEDES the meal (earlier detection possible)' if lo > 0 else 'HR does NOT reliably lead — the BG rise is the earliest signal'}")
