#!/usr/bin/env python3
"""
Per-user extraction (run in parallel). Pulls every ACTUAL V6 CONFIRMED cycle (the confirm shots) on
the meal-dosing window, with the telemetry needed to reconstruct the gate (budget, aggressionKnob,
committed/confirmed caps, stored velocityFactor), recomputes the rise from CGM, and measures the
meal's ACTUAL forward outcome (peak, nadir/crash, recovery plateau). Also validates the recomputed
rise against the stored velocityFactor (faithfulness check). Writes bt_confirms_<user>.json to OUT.

Usage: python3 bt_extract.py <user> <out_dir>
"""
import sys, json, numpy as np, psycopg2
from bt_common import velocity_factor, SCENARIOS

USER = sys.argv[1]; OUT = sys.argv[2]
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()

# full CGM series for rise + forward outcome
cur.execute("select ts_epoch,cgm_mgdl from boost_decisions where user_id=%s and cgm_mgdl is not null order by ts_epoch", (USER,))
arr = np.array(cur.fetchall(), float)
EP, G = arr[:, 0], arr[:, 1]
def bg_at(e, tol=400):
    i = np.searchsorted(EP, e); c = [j for j in (i - 1, i, i + 1) if 0 <= j < len(EP) and abs(EP[j] - e) < tol]
    return G[min(c, key=lambda j: abs(EP[j] - e))] if c else np.nan

# actual CONFIRMED cycles, meal window, with telemetry
cur.execute("""select ts_epoch, cgm_mgdl, iob_iob, boostv5_budget, boostv5_aggressionknob,
   boostv5_committedcap, boostv5_confirmedcap, boostv5_velocityfactor, boostv5_finaldose
   from boost_decisions where user_id=%s and variant='boost-other'
   and reason_text ~ 'sleep=AWAKE' and reason_text !~ 'suppressed \\(SLEEPING\\)'
   and boostv5_state='CONFIRMED' and boostv5_budget is not null and cgm_mgdl is not null order by ts_epoch""", (USER,))
recs = []
vf_err = []
for e, bg, iob, budget, knob, ccap, fcap, vf_stored, fd in cur.fetchall():
    if budget is None or knob is None or ccap is None or fcap is None: continue
    rise = max(0.0, 2.0 * (bg - bg_at(e - 900)))          # cumulativeRise30min ≈ 2×(15-min delta)
    if np.isnan(rise): continue
    if vf_stored is not None:                              # faithfulness: recomputed vs stored vf
        vf_err.append(velocity_factor(rise, **SCENARIOS['baseline']) - vf_stored)
    nadir = np.nanmin([bg_at(e + m * 60) for m in range(20, 151, 5)])
    peak = np.nanmax([bg_at(e + m * 60) for m in range(-10, 41, 5)])
    plat = np.nanmean([bg_at(e + m * 60) for m in (120, 150, 180)])
    if np.isnan(nadir) or np.isnan(plat): continue
    recs.append(dict(user=USER, bg=bg, iob=iob or 0, budget=budget, knob=knob,
                     committed_cap=ccap, confirmed_cap=fcap, vf_stored=vf_stored, actual_dose=fd or 0,
                     rise=rise, nadir=nadir, peak=peak, plateau=plat,
                     crash=int(nadir < 70), deep=int(nadir < 54), plateau_high=int(plat > 140)))
json.dump(dict(user=USER, n=len(recs),
               vf_recompute_bias=float(np.mean(vf_err)) if vf_err else None,
               vf_recompute_mae=float(np.mean(np.abs(vf_err))) if vf_err else None,
               recs=recs),
          open(f"{OUT}/bt_confirms_{USER}.json", "w"))
print(f"{USER}: {len(recs)} confirm cycles, vf-recompute MAE {np.mean(np.abs(vf_err)):.3f}" if vf_err else f"{USER}: {len(recs)} confirm cycles")
conn.close()
