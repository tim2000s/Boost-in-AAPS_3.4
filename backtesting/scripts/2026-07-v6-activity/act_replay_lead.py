#!/usr/bin/env python3
"""
Acute-activity insulin-withdrawal — semi-closed-loop replay, per V6 user, step by step.

Same method as the mealtime work (2026-07-v6-sim): keep the OBSERVED glucose trace; where the lever
CHANGES insulin, perturb the trajectory by the insulin-action difference (oref activity × DynISF-at-
the-time). Here the lever only ever WITHHOLDS insulin (zero-temp the basal + suppress the V6 SMB) for
the activity window, so BG_lever >= BG_actual ALWAYS: it can raise a nadir (prevent a walk-low) but
never create a new low. The only cost is a higher peak when the walk wasn't going to cause a low.

Trigger (observed, reactive): steps_5m >= ONSET (per-user p75 of nonzero steps_5m, floored 80) AND
IOB >= IOB_MIN. Window: from onset while steps_5m >= CONTINUE (per-user p50), tolerating BUFFER-min
gaps, capped at MAX_WINDOW. Withheld per cycle = zero-temp'd basal (sug_rate×dt) + suppressed SMB
(finaldose), capped at MAX_WITHHOLD_U/window.

CRUX: this prices the lever's MARGINAL benefit OVER V6's existing reactive basal reduction — if V6
already zero-temps during the walk (sug_rate≈0), the lever withholds nothing extra and shows no gain.

ISF winsorised at 250 (tim's U200 139 is genuine, outliers to 623 are not); per-user median, NO pooling.
Usage: python3 act_replay.py <user>  (writes act_<user>.json). Run users in parallel.
"""
import sys, json, numpy as np, psycopg2
sys.path.insert(0, '.'); sys.path.insert(0, '../2026-07-v6-sim')
from sim_lib import acted_fraction

U = sys.argv[1]; LEAD = float(sys.argv[2]) if len(sys.argv)>2 else 0.0
IOB_MIN = 0.5; BUFFER_MIN = 15.0; MAX_WINDOW_MIN = 45.0; MAX_WITHHOLD_U = 2.0; HORIZON = 180
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
cur.execute("""select ts_epoch, cgm_mgdl, variable_sens, iob_iob, steps_5m, sug_rate, boostv5_finaldose
   from boost_decisions where user_id=%s and variant='boost-other' and cgm_mgdl is not null
   order by ts_epoch""", (U,))
r = cur.fetchall()
EP = np.array([x[0] for x in r], float); BG = np.array([x[1] for x in r], float)
ISF = np.array([x[2] if x[2] is not None else np.nan for x in r], float)
if np.nanmedian(ISF) < 15: ISF *= 18.0                       # mmol → mg/dL/U
ISF = np.minimum(ISF, 250.0)                                 # winsorise (U200 lesson)
IOB = np.array([x[3] if x[3] is not None else 0.0 for x in r], float)
ST = np.array([x[4] if x[4] is not None else 0.0 for x in r], float)
RATE = np.array([x[5] if x[5] is not None else 0.0 for x in r], float)   # temp basal U/hr
FD = np.array([x[6] or 0.0 for x in r], float)                            # V6 SMB U
N = len(r); isf_med = float(np.nanmedian(ISF))
nz = ST[ST > 0]
ONSET = max(80.0, float(np.percentile(nz, 75))) if len(nz) > 20 else 100.0
CONTINUE = max(30.0, float(np.percentile(nz, 50))) if len(nz) > 20 else 50.0

def idx_at(e, tol=400):
    i = np.searchsorted(EP, e); c = [j for j in (i-1, i, i+1) if 0 <= j < N and abs(EP[j]-e) < tol]
    return min(c, key=lambda j: abs(EP[j]-e)) if c else None
def bg_at(e): j = idx_at(e); return BG[j] if j is not None else np.nan
def cycle_dt(k):                                             # minutes this cycle's basal covers
    if k+1 < N and EP[k+1]-EP[k] < 900: return min(6.0, (EP[k+1]-EP[k])/60.0)
    return 5.0

events = []; k = 0
while k < N:
    if not (ST[k] >= ONSET and IOB[k] >= IOB_MIN):
        k += 1; continue
    # --- new activity bout at k: build the withdrawal window ---
    e0 = EP[k]; win = []; j = k; last_active = e0
    ws = idx_at(e0 - LEAD*60) if LEAD>0 else k
    if ws is None: ws = k
    while j < N and (EP[j]-last_active) <= BUFFER_MIN*60 and (EP[j]-e0) <= MAX_WINDOW_MIN*60:
        if EP[j]-EP[j-1] > 900 and j > k: break              # data gap ends the window
        if ST[j] >= CONTINUE: last_active = EP[j]
        win.append(j); j += 1
    # withheld insulin per cycle (zero-temp basal + suppressed SMB), capped per window
    pre = list(range(ws, k)) if LEAD>0 else []
    dd = []; cum = 0.0
    for w in pre + win:
        wh = RATE[w]*cycle_dt(w)/60.0 + FD[w]
        wh = min(wh, max(0.0, MAX_WITHHOLD_U - cum)); cum += wh
        if wh > 1e-6: dd.append((EP[w], -wh))               # negative = insulin removed
    # --- project the forward trajectory: actual vs lever ---
    ba_path, bl_path = [], []
    for m in range(0, HORIZON+1, 5):
        t = e0 + m*60; ba = bg_at(t)
        if np.isnan(ba): continue
        pert = -isf_med * sum(d*acted_fraction((t-s)/60.0) for s, d in dd)   # >=0 (lever higher)
        ba_path.append(ba); bl_path.append(ba + pert)
    if len(ba_path) < 12: k = j; continue
    ba = np.array(ba_path); bl = np.array(bl_path)
    nadir_a, nadir_l = ba.min(), bl.min()
    peak_a, peak_l = ba.max(), bl.max()
    events.append(dict(withheld=round(cum, 3), steps5m=int(ST[k]), iob0=round(IOB[k], 2), bg0=int(BG[k]),
        win_min=round((EP[win[-1]]-e0)/60.0, 0), n_dd=len(dd),
        nadir_a=round(nadir_a, 1), nadir_l=round(nadir_l, 1), peak_a=round(peak_a, 1), peak_l=round(peak_l, 1),
        low_a=int(nadir_a < 70), low_l=int(nadir_l < 70), deep_a=int(nadir_a < 54), deep_l=int(nadir_l < 54),
        high_a=int(peak_a > 180), high_l=int(peak_l > 180),
        prevented=int(nadir_a < 70 and nadir_l >= 70), deep_prevented=int(nadir_a < 54 and nadir_l >= 54),
        high_caused=int(peak_l > 180 and peak_a <= 180), lift=round(nadir_l-nadir_a, 1)))
    k = j                                                    # skip past this bout

# baseline: activity-onset rate — how often does the loop CURRENTLY zero-temp during these bouts?
json.dump(dict(user=U, lead=LEAD, isf_med=isf_med, onset=round(ONSET), cont=round(CONTINUE), n=len(events),
    events=events), open(f"actL_{U}.json", "w"))
n = len(events); nl = sum(e['low_a'] for e in events)
print(f"{U}: {n} activity+IOB bouts (onset>={ONSET:.0f} steps/5m, ISF {isf_med:.0f}); "
      f"{nl} went low, {sum(e['prevented'] for e in events)} prevented, "
      f"{sum(e['high_caused'] for e in events)} highs caused; mean withheld {np.mean([e['withheld'] for e in events]):.2f}U")
conn.close()
