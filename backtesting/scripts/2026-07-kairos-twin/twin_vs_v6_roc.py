#!/usr/bin/env python3
"""
KAIROS Twin vs V6 — OPERATING-POINT-FAIR detection comparison (unannounced meals).

Fixes the apples-to-apples problem: compare the Twin's Ra change-point detector against
V6's confirm gate at EQUAL false-alarm rate. Latency is measured from the OBJECTIVE,
detector-independent CGM meal onset (minutes until each detector first fires in-window).
Non-meal rising cycles (delta>3 not inside any onset window) are the false-alarm universe.

Reuses run_filter/onsets from twin_vs_v6_detection. Sweeps RA_JUMP to trace the Twin ROC;
V6 is a single fixed operating point (its shipped confirm gate). Cross-user then pooled.
"""
import numpy as np, psycopg2, json
from twin_vs_v6_detection import run_filter, pull, onsets, PRIOR, USERS

OUT="/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/fb7b1560-69f3-4fc6-a769-04e7236eda2f/scratchpad"
WIN_PRE, WIN_POST = 3, 13    # search -15..+60 min around onset

def detect_lat(fire_bool, ons, n):
    """fire_bool[t]=detector fired. Return (sensitivity, list of latency-min from onset)."""
    lat=[]; hit=0
    for t in ons:
        w0=max(0,t-WIN_PRE); w1=min(n,t+WIN_POST)
        idx=[k for k in range(w0,w1) if fire_bool[k]]
        if idx: hit+=1; lat.append((idx[0]-t)*5.0)
    return hit/max(1,len(ons)), lat

def fa_rate(fire_bool, cgm, ons, n):
    """False-alarm rate on non-meal rising cycles (delta>3, not within +-60min of an onset)."""
    onset_mask=np.zeros(n,bool)
    for t in ons: onset_mask[max(0,t-WIN_PRE):min(n,t+WIN_POST)]=True
    rise=fa=0
    for t in range(1,n):
        if np.isnan(cgm[t]) or np.isnan(cgm[t-1]) or cgm[t]-cgm[t-1]<=3 or cgm[t]>200: continue
        if onset_mask[t]: continue
        rise+=1
        if fire_bool[t]: fa+=1
    return fa/max(1,rise), rise

RA_GRID=[0.4,0.6,0.8,1.0,1.2,1.5,2.0,2.5,3.0]
def ra_fires(ra,n,jump):
    fb=np.zeros(n,bool)
    for t in range(n):
        base=np.nanmedian(ra[max(0,t-6):t]) if t>=2 else 0.0
        if ra[t]-base>=jump and ra[t]>0.8: fb[t]=True
    return fb

def main():
    conn=psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur=conn.cursor()
    # accumulate pooled TRUE-onset latencies and FA universe across users, per RA threshold + V6
    v6_lat=[]; v6_hit=0; v6_onsets=0; v6_fa=0; v6_rise=0
    twin={j:dict(lat=[],hit=0,onsets=0,fa=0,rise=0) for j in RA_GRID}
    per_user={}
    for uid in USERS:
        d=pull(cur,uid)
        if d is None: continue
        cgm=d['cgm']; n=len(cgm); P=dict(PRIOR); P['Gb']=float(np.nanmedian(cgm))
        est=run_filter(cgm,d['ins'],P); ra=est[:,3]; ons=onsets(cgm)
        v6fb=np.array([s in ('CONFIRMED','COMMITTED') for s in d['state']])
        s6,l6=detect_lat(v6fb,ons,n); f6,r6=fa_rate(v6fb,cgm,ons,n)
        v6_lat+=l6; v6_hit+=round(s6*len(ons)); v6_onsets+=len(ons); v6_fa+=round(f6*r6); v6_rise+=r6
        tu={}
        for j in RA_GRID:
            fb=ra_fires(ra,n,j); s,l=detect_lat(fb,ons,n); f,r=fa_rate(fb,cgm,ons,n)
            twin[j]['lat']+=l; twin[j]['hit']+=round(s*len(ons)); twin[j]['onsets']+=len(ons)
            twin[j]['fa']+=round(f*r); twin[j]['rise']+=r
            tu[j]=dict(sens=round(s,2),fa=round(f,3),lat_med=round(float(np.median(l)),1) if l else None)
        per_user[uid]=dict(v6=dict(sens=round(s6,2),fa=round(f6,3),
                                   lat_med=round(float(np.median(l6)),1) if l6 else None,n_onsets=len(ons)),
                           twin_by_jump=tu)
        print(f"{uid}: V6 sens={s6:.2f} fa={f6:.3f} lat={per_user[uid]['v6']['lat_med']}  |  "
              f"Twin@1.0 sens={tu[1.0]['sens']} fa={tu[1.0]['fa']} lat={tu[1.0]['lat_med']}")
    # pooled ROC
    v6_op=dict(sens=round(v6_hit/max(1,v6_onsets),3), fa=round(v6_fa/max(1,v6_rise),3),
               lat_med=round(float(np.median(v6_lat)),1), lat_mean=round(float(np.mean(v6_lat)),1),
               n_onsets=v6_onsets)
    roc=[]
    for j in RA_GRID:
        t=twin[j]
        roc.append(dict(jump=j, sens=round(t['hit']/max(1,t['onsets']),3), fa=round(t['fa']/max(1,t['rise']),3),
                        lat_med=round(float(np.median(t['lat'])),1) if t['lat'] else None,
                        lat_mean=round(float(np.mean(t['lat'])),1) if t['lat'] else None))
    # find the Twin threshold whose FA is closest to V6's FA (equal-specificity comparison)
    matched=min(roc, key=lambda r: abs(r['fa']-v6_op['fa']))
    out=dict(v6_operating_point=v6_op, twin_roc=roc, twin_at_matched_fa=matched, per_user=per_user)
    json.dump(out, open(f"{OUT}/twin_vs_v6_roc.json","w"), indent=2)
    print("\n=== V6 OPERATING POINT ==="); print(json.dumps(v6_op))
    print("=== TWIN ROC (sweep RA_JUMP) ===")
    for r in roc: print(f"  jump={r['jump']:>4}  sens={r['sens']:.2f}  fa={r['fa']:.3f}  lat_med={r['lat_med']}min")
    print(f"=== TWIN @ V6-matched FA ({v6_op['fa']:.3f}) ===  jump={matched['jump']} sens={matched['sens']} fa={matched['fa']} lat_med={matched['lat_med']}min")
    print(f"    -> V6: sens={v6_op['sens']} lat_med={v6_op['lat_med']}min   Twin(matched): sens={matched['sens']} lat_med={matched['lat_med']}min")
    conn.close()

if __name__=='__main__': main()
