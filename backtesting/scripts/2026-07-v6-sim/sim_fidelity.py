#!/usr/bin/env python3
"""FIDELITY GATE: does the ported V6 confirm shot reproduce the LOGGED doses? Compares
reconstructed shot (budget×1.8×knob×velocityFactor, capped) vs logged boostv5_doseaftercaps
(a) using the STORED velocityFactor (isolates the shot formula) and (b) using rise recomputed
from CGM (end-to-end). If (a) is tight, the port is faithful; (b) shows the rise-recompute cost."""
import sys, numpy as np, psycopg2
sys.path.insert(0, '.')
from sim_lib import CONFIRMED_MULT, velocity_factor
conn=psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur=conn.cursor()
USERS=['tim','F','H','B','E','A','C','D']
print(f"{'user':<5}{'n':>5}{'formula MAE':>13}{'formula bias':>13}{'end2end MAE':>13}{'within 0.05U':>13}")
allf=[]; alle=[]
for u in USERS:
    # cgm series for rise
    cur.execute("select ts_epoch,cgm_mgdl from boost_decisions where user_id=%s and cgm_mgdl is not null order by ts_epoch",(u,))
    a=np.array(cur.fetchall(),float); EP,G=a[:,0],a[:,1]
    def bg_at(e,tol=400):
        i=np.searchsorted(EP,e); c=[j for j in (i-1,i,i+1) if 0<=j<len(EP) and abs(EP[j]-e)<tol]
        return G[min(c,key=lambda j:abs(EP[j]-e))] if c else np.nan
    cur.execute("""select ts_epoch,boostv5_budget,boostv5_aggressionknob,boostv5_confirmedcap,
       boostv5_velocityfactor,boostv5_doseaftercaps from boost_decisions where user_id=%s
       and variant='boost-other' and boostv5_state='CONFIRMED' and boostv5_doseaftercaps is not null
       and boostv5_budget is not null and boostv5_velocityfactor is not null""",(u,))
    fe=[]; ee=[]; near=0; n=0
    for e,budget,knob,ccap,vf_stored,dac in cur.fetchall():
        if None in (budget,knob,ccap): continue
        recon_formula=min(budget*CONFIRMED_MULT*knob*vf_stored, ccap)
        rise=max(0.0,2.0*(bg_at(e)-bg_at(e-900)))
        if np.isnan(rise): continue
        recon_e2e=min(budget*CONFIRMED_MULT*knob*velocity_factor(rise), ccap)
        fe.append(abs(recon_formula-dac)); ee.append(abs(recon_e2e-dac)); n+=1
        if abs(recon_formula-dac)<0.05: near+=1
    if n<5: print(f"{u:<5}{n:>5}   (thin)"); continue
    allf+=fe; alle+=ee
    print(f"{u:<5}{n:>5}{np.mean(fe):>13.3f}{np.mean([r for r in fe]):>13.3f}{np.mean(ee):>13.3f}{100*near/n:>12.0f}%")
print(f"\nPOOLED formula MAE {np.mean(allf):.3f}U   end-to-end MAE {np.mean(alle):.3f}U")
print("GATE: formula MAE << 0.05U => the confirm-shot port faithfully reproduces logged doses (pre-brake);")
print("end-to-end MAE is formula + the rise-recompute error. If formula is tight, the sim is trustworthy")
print("for the confirm mechanism the fix touches.")
conn.close()
