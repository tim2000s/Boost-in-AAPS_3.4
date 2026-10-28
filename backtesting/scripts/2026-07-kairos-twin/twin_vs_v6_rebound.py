#!/usr/bin/env python3
"""
KAIROS Twin vs V6 — is the Twin's extra conservatism REBOUND AVOIDANCE? (identifiable)

From twin_vs_v6_roc: at equal false-alarm rate the Twin fires on fewer non-meal rising
cycles than V6. This script asks whether the ones it SHEDS are the harmful ones.

For every non-meal rising cycle (delta>3, outside any objective onset window) where a
detector fires (= would treat the rise as a meal), classify the forward 60-min BG path:
  reaches_fall  BG drops >=20 mg/dL below current within 60 min  -> a meal shot here stacks
                into a fall (harmful place to dose)
  real_climb    BG net-rises >=20 over 60 min AND no >=20 fall    -> genuine appearance the
                onset detector was too strict to log (dosing justified)
  flat          neither
Compares V6 (shipped confirm gate) vs Twin Ra at the V6-matched threshold (jump 0.8).
Cross-user then pooled. Raw traces stay in scratchpad; only aggregates reported.
"""
import numpy as np, psycopg2, json
from twin_vs_v6_detection import run_filter, pull, onsets, PRIOR, USERS

OUT="/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/fb7b1560-69f3-4fc6-a769-04e7236eda2f/scratchpad"
WIN_PRE, WIN_POST = 3, 13
JUMP = 0.8            # Twin threshold matched to V6 false-alarm rate (from twin_vs_v6_roc)
FWD = 12             # 60-min forward window
FALL, CLIMB = 20, 20 # mg/dL

def ra_fire_t(ra,t):
    base=np.nanmedian(ra[max(0,t-6):t]) if t>=2 else 0.0
    return ra[t]-base>=JUMP and ra[t]>0.8

def classify_forward(cgm,t):
    fwd=cgm[t+1:t+1+FWD]
    if len(fwd)<6 or np.mean(np.isnan(fwd))>0.4: return None
    nadir=np.nanmin(fwd); net=(np.nanmean(cgm[t+FWD-2:t+FWD+1]) if t+FWD<len(cgm) else np.nanmax(fwd))-cgm[t]
    drop=cgm[t]-nadir
    if drop>=FALL: return 'reaches_fall'
    if net>=CLIMB: return 'real_climb'
    return 'flat'

JUMP_C=1.2           # conservative Twin threshold for the differential (rebound-avoidance) test
def ra_fire_c(ra,t):
    base=np.nanmedian(ra[max(0,t-6):t]) if t>=2 else 0.0
    return ra[t]-base>=JUMP_C and ra[t]>0.8

def main():
    conn=psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur=conn.cursor()
    agg={'V6':{'reaches_fall':0,'real_climb':0,'flat':0}, 'Twin':{'reaches_fall':0,'real_climb':0,'flat':0}}
    # differential: V6 fires but conservative Twin declines ("saved" by the Twin) vs Twin-only
    diff={'v6_only_saved':{'reaches_fall':0,'real_climb':0,'flat':0},
          'twin_c_only':{'reaches_fall':0,'real_climb':0,'flat':0}}
    days_total=0; per_user={}
    for uid in USERS:
        d=pull(cur,uid)
        if d is None: continue
        cgm=d['cgm']; n=len(cgm); days=(d['grid'][-1]-d['grid'][0])/86400.0; days_total+=days
        P=dict(PRIOR); P['Gb']=float(np.nanmedian(cgm)); est=run_filter(cgm,d['ins'],P); ra=est[:,3]
        ons=onsets(cgm); onset_mask=np.zeros(n,bool)
        for t in ons: onset_mask[max(0,t-WIN_PRE):min(n,t+WIN_POST)]=True
        u={'V6':{'reaches_fall':0,'real_climb':0,'flat':0}, 'Twin':{'reaches_fall':0,'real_climb':0,'flat':0}}
        for t in range(1,n-FWD):
            if np.isnan(cgm[t]) or np.isnan(cgm[t-1]) or cgm[t]-cgm[t-1]<=3 or cgm[t]>200: continue
            if onset_mask[t]: continue                       # non-meal rising cycles only
            cls=classify_forward(cgm,t)
            if cls is None: continue
            v6f=d['state'][t] in ('CONFIRMED','COMMITTED')
            if v6f: u['V6'][cls]+=1
            if ra_fire_t(ra,t): u['Twin'][cls]+=1
            # differential at the conservative Twin threshold
            tc=ra_fire_c(ra,t)
            if v6f and not tc: diff['v6_only_saved'][cls]+=1
            if tc and not v6f: diff['twin_c_only'][cls]+=1
        for det in ('V6','Twin'):
            for k in cls_keys(): agg[det][k]+=u[det][k]
        def share(x):
            tot=sum(x.values()); return {k:round(100*v/max(1,tot),1) for k,v in x.items()}|{'n':tot}
        per_user[uid]=dict(V6=share(u['V6']), Twin=share(u['Twin']), days=round(days,1))
        print(f"{uid}: V6 fa={sum(u['V6'].values())} (fall {per_user[uid]['V6']['reaches_fall']}%) | "
              f"Twin fa={sum(u['Twin'].values())} (fall {per_user[uid]['Twin']['reaches_fall']}%)")
    def summ(x):
        tot=sum(x.values())
        return dict(n=tot, per_day=round(tot/max(1,days_total),2),
                    reaches_fall_pct=round(100*x['reaches_fall']/max(1,tot),1),
                    real_climb_pct=round(100*x['real_climb']/max(1,tot),1),
                    flat_pct=round(100*x['flat']/max(1,tot),1),
                    harmful_per_day=round(x['reaches_fall']/max(1,days_total),2))
    out=dict(V6=summ(agg['V6']), Twin=summ(agg['Twin']),
             differential=dict(v6_only_saved=summ(diff['v6_only_saved']), twin_c_only=summ(diff['twin_c_only']),
                               jump_conservative=JUMP_C), per_user=per_user,
             defn=dict(fall=FALL,climb=CLIMB,fwd_min=60,jump=JUMP,universe='non-meal rising cycles (delta>3, outside onset windows)'))
    json.dump(out, open(f"{OUT}/twin_vs_v6_rebound.json","w"), indent=2)
    print("\n=== POOLED (non-meal-rise false alarms, matched FA jump=0.8) ===")
    for det in ('V6','Twin'):
        s=out[det]; print(f"  {det:5} n={s['n']:4} ({s['per_day']}/day)  reaches_fall={s['reaches_fall_pct']}%  "
                           f"real_climb={s['real_climb_pct']}%  flat={s['flat_pct']}%  HARMFUL/day={s['harmful_per_day']}")
    print(f"\n=== DIFFERENTIAL (conservative Twin jump={JUMP_C}) — does the Twin selectively shed harmful rebounds? ===")
    vs=out['differential']['v6_only_saved']; tc=out['differential']['twin_c_only']
    print(f"  V6-fires-Twin-declines ('saved'): n={vs['n']}  reaches_fall={vs['reaches_fall_pct']}%  real_climb={vs['real_climb_pct']}%  flat={vs['flat_pct']}%")
    print(f"  Twin-fires-V6-declines:           n={tc['n']}  reaches_fall={tc['reaches_fall_pct']}%  real_climb={tc['real_climb_pct']}%  flat={tc['flat_pct']}%")
    print(f"  (baseline: V6's overall false-alarm reaches_fall = {out['V6']['reaches_fall_pct']}%)")
    conn.close()

def cls_keys(): return ('reaches_fall','real_climb','flat')
if __name__=='__main__': main()
