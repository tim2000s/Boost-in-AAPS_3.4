#!/usr/bin/env python3
"""
Semi-closed-loop insulin-perturbation replay: V6 (actual) vs the IOB-ramp FIX, per confirm meal.

Model: the fix delivers a smaller first shot (fix_confirm_shot = v6_shot × iob_ramp(IOB)) and holds
the remainder (reserve = S_v6 − S_fix) in a conditional follow-up — delivering committedCap-sized
holds on subsequent cycles ONLY while the (perturbed) BG stays above target+margin, and stopping (not
delivering the rest) once BG normalises. Glucose is projected off the OBSERVED trace by the insulin-
action difference (oref activity × DynISF-at-the-time). Semi-closed: the follow-up decision reads the
perturbed BG. Since the fix delivers ≤ V6 total, BG_fix ≥ BG_actual always → it can PREVENT crashes
(raise the nadir) but never create new lows; the cost is a higher plateau on meals it holds back.

VALIDITY: first-order in the dose delta; DynISF held observed; state approximated as
COMMITTED-while-elevated for the follow-up. FIDELITY-GATED (sim_fidelity: confirm-shot MAE 0.000U).
Usage: python3 sim_replay.py <user>  (writes sim_<user>.json)  — run users in parallel.
"""
import sys, json, numpy as np, psycopg2
sys.path.insert(0, '.')
from sim_lib import v6_confirm_shot, fix_confirm_shot, iob_ramp, acted_fraction, velocity_factor

USER = sys.argv[1]
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
cur.execute("""select ts_epoch, cgm_mgdl, variable_sens, sug_current_target, iob_iob,
   boostv5_state, boostv5_finaldose, boostv5_budget, boostv5_aggressionknob,
   boostv5_confirmedcap, boostv5_committedcap, v1_units
   from boost_decisions where user_id=%s and variant='boost-other' and cgm_mgdl is not null order by ts_epoch""", (USER,))
rows = cur.fetchall()
A = {k: np.array([r[i] for r in rows], dtype=object) for i, k in enumerate(
    ['e', 'bg', 'isf', 'tgt', 'iob', 'state', 'fd', 'budget', 'knob', 'ccap', 'mcap', 'v1'])}
# V1's per-cycle SMB delta vs V6 (logged v1_units − finaldose), for the open-loop V1 arm
V1D = np.array([((r[11] or 0.0) - (r[6] or 0.0)) if r[11] is not None else 0.0 for r in rows], float)
EP = np.array([r[0] for r in rows], float); BG = np.array([r[1] for r in rows], float)
ISF = np.array([r[2] if r[2] is not None else np.nan for r in rows], float)
if np.nanmedian(ISF) < 15: ISF *= 18.0                        # mmol/L/U → mg/dL/U
TGT = np.array([(r[3] if r[3] is not None else 100.0) for r in rows], float)
if np.nanmedian(TGT) < 20: TGT *= 18.0
def idx_at(e, tol=200):
    i = np.searchsorted(EP, e); c = [j for j in (i - 1, i, i + 1) if 0 <= j < len(EP) and abs(EP[j] - e) < tol]
    return min(c, key=lambda j: abs(EP[j] - e)) if c else None
def bg_at(e): j = idx_at(e, 400); return BG[j] if j is not None else np.nan

MARGIN = 20.0; HORIZON = 150  # min
meals = []
for k in range(len(rows)):
    if rows[k][5] != 'CONFIRMED' or rows[k][7] is None or rows[k][8] is None: continue
    budget, knob, ccap, mcap = rows[k][7], rows[k][8], rows[k][9] or 0.25, rows[k][10] or 0.25
    e0 = EP[k]; iob0 = A['iob'][k] or 0.0
    rise = max(0.0, 2.0 * (BG[k] - bg_at(e0 - 900)))
    if np.isnan(rise): continue
    s_v6 = v6_confirm_shot(budget, knob, rise, ccap)
    s_fix = fix_confirm_shot(budget, knob, rise, ccap, iob0)
    reserve = max(0.0, s_v6 - s_fix)
    # walk the meal forward; dd = list of (dose_time, delta_insulin) fix−v6
    dd = [(e0, s_fix - s_v6)]
    delivered_followup = 0.0
    isf_meal = ISF[k] if not np.isnan(ISF[k]) else np.nanmedian(ISF)
    # V1 arm (open-loop): logged per-cycle v1_units−finaldose over the meal window
    wlo, whi = e0, e0 + HORIZON * 60
    v1dd = [(EP[j], V1D[j]) for j in range(k, len(rows)) if EP[j] <= whi and abs(V1D[j]) > 1e-9]
    bg_fix_path, bg_act_path, bg_v1_path = [], [], []
    for m in range(0, HORIZON + 1, 5):
        t = e0 + m * 60
        ba = bg_at(t)
        if np.isnan(ba): continue
        pert = -isf_meal * sum(d * acted_fraction((t - s) / 60.0) for s, d in dd)   # >0 (fix higher)
        pert_v1 = -isf_meal * sum(d * acted_fraction((t - s) / 60.0) for s, d in v1dd if s <= t)
        bf = ba + pert
        bg_act_path.append(ba); bg_fix_path.append(bf); bg_v1_path.append(ba + pert_v1)
        # follow-up hold decision on the PERTURBED bg (semi-closed)
        if 0 < m <= 90 and delivered_followup < reserve - 1e-6:
            j = idx_at(t)
            tgt = TGT[j] if j is not None and not np.isnan(TGT[j]) else 100.0
            if bf > tgt + MARGIN:
                bud = A['budget'][j] if j is not None and A['budget'][j] is not None else budget
                h = min(mcap, budget if bud is None else bud, reserve - delivered_followup)
                dd.append((t, h)); delivered_followup += h
    if len(bg_fix_path) < 10: continue
    ba = np.array(bg_act_path); bf = np.array(bg_fix_path); bv = np.array(bg_v1_path)
    nadir_a, nadir_f, nadir_v = ba.min(), bf.min(), bv.min()
    plat_a, plat_f, plat_v = ba[-6:].mean(), bf[-6:].mean(), bv[-6:].mean()
    meals.append(dict(user=USER, rise=rise, iob0=iob0, s_v6=round(s_v6, 3), s_fix=round(s_fix, 3),
                      reserve=round(reserve, 3), followup=round(delivered_followup, 3),
                      total_v6=round(s_v6, 3), total_fix=round(s_fix + delivered_followup, 3),
                      nadir_a=round(nadir_a, 1), nadir_f=round(nadir_f, 1), nadir_v=round(nadir_v, 1),
                      plat_a=round(plat_a, 1), plat_f=round(plat_f, 1), plat_v=round(plat_v, 1),
                      crash_a=int(nadir_a < 70), crash_f=int(nadir_f < 70), crash_v=int(nadir_v < 70),
                      deep_a=int(nadir_a < 54), deep_f=int(nadir_f < 54), deep_v=int(nadir_v < 54),
                      plateau_high_a=int(plat_a > 160), plateau_high_f=int(plat_f > 160), plateau_high_v=int(plat_v > 160)))
json.dump(dict(user=USER, isf_median=float(np.nanmedian(ISF)), n=len(meals), meals=meals),
          open(f"sim_{USER}.json", "w"))
print(f"{USER}: {len(meals)} confirm meals replayed (median DynISF {np.nanmedian(ISF):.0f} mg/dL/U)")
conn.close()
