#!/usr/bin/env python3
"""FIDELITY GATE for the Twin harness: does the REAL TwinShadow, driven from Python via kengine, reproduce
the on-device logged twin telemetry (boosttwin_fc30 / boosttwin_ra)? Replays a user's cycles through the
harness with the same insulin inputs the plugin uses (delivered SMB + basal this cycle; scheduled basal
for the forecast) and compares to the logged values after a warmup (the EnKF re-converges in ~30 min).
PASS = the harness tracks the on-device Twin (MAE small, correlation high). Run: python3 fidelity_twin.py [user]
"""
import sys, os, numpy as np, psycopg2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kengine import run_engine

U = sys.argv[1] if len(sys.argv) > 1 else "tim"
WARMUP = 24  # cycles to let the fresh filter converge before scoring

conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
cur.execute("""select ts_epoch, cgm_mgdl, boostv5_finaldose, sug_rate, boosttwin_fc30, boosttwin_ra
   from boost_decisions where user_id=%s and variant='boost-other' and cgm_mgdl is not null
   and boosttwin_fc30 is not null order by ts_epoch""", (U,))
r = cur.fetchall(); conn.close()
if len(r) < 100:
    print(f"{U}: too few logged-twin rows ({len(r)})"); sys.exit(0)
ep = np.array([x[0] for x in r], float)
cgm = np.array([x[1] for x in r], float)
smb = np.array([x[2] or 0.0 for x in r], float)
rate = np.array([x[3] or 0.0 for x in r], float)     # temp basal U/hr
fc30_log = np.array([x[4] for x in r], float)
ra_log = np.array([x[5] if x[5] is not None else np.nan for x in r], float)
# logged twin values may be mmol on some users -> mg/dL for fc30
if np.nanmedian(fc30_log) < 30: fc30_log = fc30_log * 18.0

# reconstruct the plugin's per-cycle insulin: delivered this cycle = SMB + basal*(dt/60); forecast basal =
# scheduled basal per 5-min. dt = minutes to next cycle (capped 6). (Scheduled basal ~ the temp rate here.)
dt = np.clip(np.diff(ep, append=ep[-1] + 300) / 60.0, 0, 6)
ins_this = smb + rate * dt / 60.0
basal_fwd = rate * 5.0 / 60.0
cycles = [{"cgm": float(cgm[i]), "insulinThisCycleU": float(ins_this[i]),
           "expectedBasalPerCycleU": float(basal_fwd[i])} for i in range(len(r))]

print(f"[fidelity] replaying {len(cycles)} cycles for {U} through the REAL TwinShadow harness ...")
res = run_engine("twin", cycles)
fc30_h = np.array([x.get("fc30", np.nan) for x in res], float)
ra_h = np.array([x.get("raMean", np.nan) for x in res], float)

m = np.arange(len(r)) >= WARMUP
mfc = m & np.isfinite(fc30_h) & np.isfinite(fc30_log)
mae = np.mean(np.abs(fc30_h[mfc] - fc30_log[mfc]))
corr = np.corrcoef(fc30_h[mfc], fc30_log[mfc])[0, 1]
mra = m & np.isfinite(ra_h) & np.isfinite(ra_log)
ra_mae = np.mean(np.abs(ra_h[mra] - ra_log[mra])) if mra.sum() > 10 else np.nan
ra_corr = np.corrcoef(ra_h[mra], ra_log[mra])[0, 1] if mra.sum() > 10 else np.nan

print(f"\n=== Twin harness fidelity ({U}, n={mfc.sum()} post-warmup) ===")
print(f"  fc30:  MAE {mae:5.1f} mg/dL   corr {corr:.3f}")
print(f"  raMean: MAE {ra_mae:5.2f}       corr {ra_corr:.3f}")
verdict = "PASS — harness reproduces the on-device Twin" if corr > 0.9 and mae < 12 else \
          ("MARGINAL — tracks but with offset (RNG/insulin-input differences)" if corr > 0.75 else
           "FAIL — harness diverges from the logged Twin; investigate inputs/seed")
print(f"  → {verdict}")
print("  (note: the on-device filter has its own long-running ensemble + seed; exact bit-match is not")
print("   expected — the gate is that the harness Twin TRACKS the shipped one after convergence.)")
