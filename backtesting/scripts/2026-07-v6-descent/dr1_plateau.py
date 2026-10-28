#!/usr/bin/env python3
"""
DESCENT 1 — is the post-meal plateau a SAFE dosing opportunity, or is V6 correctly restrained?
The under-recovery: V6 parks glucose at 145-150 for hours after a meal. The register warns that dosing
into recovering highs feeds lows. So the make-or-break question is HEADROOM: in the plateau window
(BG>140, +90..+210 min post-onset), when V6 is dosing ~0, is a low actually coming (V6 right to hold)
or not (a safe nudge available)?

For each plateau cycle we record: V6 dose, IOB, minGuardBG (V6's own low forecast), trend, and the
FORWARD nadir over the next 3h (ground-truth: does it actually go low?). The dosable-and-safe cell =
BG>140, V6 dose ~0, minGuard not low, IOB moderate — and among those, how often a low follows.
Usage: python3 dr1_plateau.py <user>  (writes dr1_<user>.json)
"""
import sys, json, numpy as np, psycopg2
U = sys.argv[1]
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
cur.execute("""select ts_epoch,cgm_mgdl,iob_iob,boostv5_finaldose,reason_minguardbg from boost_decisions
   where user_id=%s and variant='boost-other' and cgm_mgdl is not null order by ts_epoch""", (U,))
r = cur.fetchall()
EP = np.array([x[0] for x in r], float); G = np.array([x[1] for x in r], float)
IOB = np.array([x[2] if x[2] is not None else np.nan for x in r], float)
FD = np.array([x[3] if x[3] is not None else 0.0 for x in r], float)
MG = np.array([x[4] if x[4] is not None else np.nan for x in r], float)
if np.nanmedian(MG) < 30: MG *= 18.0                                # mmol→mgdl guard
def bg(e, tol=400):
    i = np.searchsorted(EP, e); c = [j for j in (i - 1, i, i + 1) if 0 <= j < len(EP) and abs(EP[j] - e) < tol]
    return G[min(c, key=lambda j: abs(EP[j] - e))] if c else np.nan
def fwd_nadir(e, h=180): return np.nanmin([bg(e + m * 60) for m in range(10, h + 1, 5)])
# meal onsets
onsets = []; last = -1e9
for i in range(6, len(EP)):
    if EP[i] - EP[i - 1] > 400: continue
    if G[i] > 140 and G[i - 1] <= 140 and np.nanmin(G[max(0, i - 6):i + 1]) <= 130 and (EP[i] - last) > 5400:
        onsets.append(EP[i]); last = EP[i]
# plateau cycles: within +90..+210 min of an onset, BG still >140, glucose flat/falling
plat = []
for e0 in onsets:
    for m in range(90, 211, 5):
        j = np.searchsorted(EP, e0 + m * 60)
        if not (0 <= j < len(EP)) or abs(EP[j] - (e0 + m * 60)) > 300: continue
        if G[j] <= 140: continue
        d15 = G[j] - bg(EP[j] - 900)
        if np.isnan(d15) or d15 > 8: continue                       # flat or falling (in the plateau, not still rising)
        na = fwd_nadir(EP[j])
        if np.isnan(na): continue
        plat.append(dict(bg=G[j], iob=float(IOB[j]) if not np.isnan(IOB[j]) else -1,
                         dose=float(FD[j]), mg=float(MG[j]) if not np.isnan(MG[j]) else -1,
                         d15=d15, fwd_nadir=na))
out = dict(user=U, n_meals=len(onsets), n_plateau=len(plat), plat=plat)
json.dump(out, open(f"dr1_{U}.json", "w"))
if plat:
    dosez = [p for p in plat if p['dose'] < 0.05]
    safe = [p for p in dosez if p['mg'] >= 80]                        # V6 holding, no low forecast
    print(f"{U}: {len(onsets)} meals, {len(plat)} plateau cycles (BG>140, flat/falling) | "
          f"V6 dosing~0: {100*len(dosez)/len(plat):.0f}% | of those, minGuard>=80 (no low fcast): {100*len(safe)/max(1,len(dosez)):.0f}%")
    if safe:
        na = np.array([p['fwd_nadir'] for p in safe])
        print(f"      SAFE-looking dosable cells (n={len(safe)}): forward nadir median {np.median(na):.0f}, "
              f"goes <70 {100*np.mean(na<70):.0f}%, <80 {100*np.mean(na<80):.0f}%  | mean IOB {np.mean([p['iob'] for p in safe if p['iob']>=0]):.1f}")
conn.close()
