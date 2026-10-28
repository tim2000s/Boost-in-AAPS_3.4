#!/usr/bin/env python3
"""Follow-up: base outcome rates, refined confirm-floor counts, combined net sims, U-weighted pricing."""
import csv, math, statistics, bisect
from datetime import datetime, timedelta, timezone

SP = "/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad"
def pts(s): return datetime.fromisoformat(s.replace('Z','+00:00'))

rows=[r for r in csv.DictReader(open(f'{SP}/mig_CD_cycles.csv'))]
for r in rows:
    r['ts']=pts(r['ts_utc'])
    for k in ('boostv5_finaldose','boostv5_budget','boostv5_actionmult','v1_units','ml_hypo_risk'):
        r[k]=float(r[k]) if r[k] else None
cgm={'C':[],'D':[]}
for r in csv.DictReader(open(f'{SP}/mig_CD_cgm.csv')):
    cgm[r['user_id']].append((pts(r['ts_utc']),float(r['cgm_mgdl'])))
for u in cgm: cgm[u].sort()
keys={u:[t for t,_ in cgm[u]] for u in cgm}
def outc(u,t0,mins=120):
    i=bisect.bisect_right(keys[u],t0); j=bisect.bisect_right(keys[u],t0+timedelta(minutes=mins))
    seg=[v for _,v in cgm[u][i:j]]
    return (min(seg),max(seg)) if len(seg)>=4 else None

PIN={'C':datetime(2026,6,19,tzinfo=timezone.utc),'D':datetime(2026,6,17,tzinfo=timezone.utc)}
DER={'C':dict(cc=1.2,cf=4.0,cum=5.0,ag=1.0,hc=1.0),'D':dict(cc=0.72,cf=1.5,cum=2.9,ag=0.85,hc=2.0)}
UPLIFT={'C':0.458,'D':0.379}
EPS=1e-6
def hscale(rk,knob):
    if rk is None or rk<=0.30: return 1.0
    red=min(1.0,(rk-0.30)/0.70*max(1.0,knob)); return max(0.5/max(1.0,knob),1.0-red)

for u in 'CD':
    era=[r for r in rows if r['user_id']==u and r['ts']>=PIN[u]]
    d=DER[u]; floor_new=min(d['cc'],0.8*d['cf'])
    pos=[r for r in era if (r['boostv5_finaldose'] or 0)>0]
    tot=sum(r['boostv5_finaldose'] for r in pos)
    print("="*90); print(f"USER {u}  era cycles={len(era)} dosing={len(pos)} total={tot:.1f}U")
    # base outcome rates over ALL dosing cycles
    oo=[o for o in (outc(u,r['ts']) for r in pos) if o]
    bl=sum(1 for mn,mx in oo if mn<70); bh=sum(1 for mn,mx in oo if mx>180 and mn>=70)
    print(f" BASE rates (all dosing cycles): pre-low(<70 in 2h) {bl}/{len(oo)} ({100*bl/len(oo):.1f}%)  "
          f"pre-high-only(>180) {bh}/{len(oo)} ({100*bh/len(oo):.1f}%)")
    # refined confirm-floor
    conf=[r for r in era if r['boostv5_state']=='CONFIRMED' and (r['boostv5_finaldose'] or 0)>0]
    unp=[r for r in conf if r['boostv5_finaldose']<1.0-EPS]     # uncapped ⇒ delivered == gate quantity
    pin=[r for r in conf if abs(r['boostv5_finaldose']-1.0)<EPS]
    held_cert=[r for r in unp if r['boostv5_finaldose']<floor_new-EPS]
    # pinned shots: gate qty = b*am*vf >= delivered 1.0; passes if b*am >= floor (some vf)
    pin_maybe=[r for r in pin if floor_new>1.0 and (r['boostv5_budget'] or 0)*(r['boostv5_actionmult'] or 0)>=floor_new]
    pin_held=[r for r in pin if floor_new>1.0 and (r['boostv5_budget'] or 0)*(r['boostv5_actionmult'] or 0)<floor_new]
    hu=sum(r['boostv5_finaldose'] for r in held_cert)
    print(f" confirm-floor {floor_new:.2f}: certainly-held {len(held_cert)}/{len(conf)} shots ({hu:.1f}U deferred)"
          + (f"; pinned@1.0: {len(pin_held)} certainly-held, {len(pin_maybe)} vf-dependent" if floor_new>1.0 else f"; pinned@1.0 all pass (floor<1.0)"))
    oo=[o for o in (outc(u,r['ts']) for r in held_cert) if o]
    hl=sum(1 for mn,mx in oo if mn<70); hh=sum(1 for mn,mx in oo if mx>180 and mn>=70)
    print(f"   held-shot outcomes: pre-low {hl}/{len(oo)}  pre-high-only {hh}/{len(oo)}")

    # combined counterfactual stream sim
    #   committed pinned -> 0.25+uplift (capped at new cc); confirmed: keep observed (conservative), D: aggression+HC scaling; then cumulative(new)
    hist=[]; add=0.0; rem_scale=0.0; rem_cum=0.0; added_cycles=[]; removed_cycles=[]
    for r in era:
        dose=r['boostv5_finaldose'] or 0.0; st=r['boostv5_state']; cf_dose=dose
        if st=='COMMITTED' and abs(dose-0.25)<EPS:
            cf_dose=min(0.25+UPLIFT[u],d['cc'])
        if dose>0 and d['hc']>1.0:
            s=hscale(r['ml_hypo_risk'],d['hc'])/hscale(r['ml_hypo_risk'],1.0); cf_dose*=s
        if st=='CONFIRMED' and d['ag']<1.0: cf_dose*=d['ag']
        if cf_dose>0:
            t0=r['ts']-timedelta(minutes=60)
            recent=sum(dv for tt,dv in hist if tt>t0)
            allowed=max(0.0,d['cum']-recent)
            if cf_dose>allowed+EPS: rem_cum+=cf_dose-allowed; cf_dose=allowed
        hist.append((r['ts'],cf_dose))
        delta=cf_dose-dose
        if delta>EPS: add+=delta; added_cycles.append((r['ts'],delta))
        elif delta<-EPS: rem_scale+=-delta; removed_cycles.append((r['ts'],-delta))
    net=sum(dv for _,dv in hist)-tot
    print(f" COMBINED sim (uplift+knobs+cumulative{d['cum']}): counterfactual total {tot+net:.1f}U vs shadow {tot:.1f}U → NET {net:+.1f}U ({100*net/tot:+.1f}%)")
    print(f"   gross ADDED {add:.1f}U on {len(added_cycles)} cycles; gross REMOVED {rem_scale+0:.1f}U scale/floor + (cum trim included) — removed cycles {len(removed_cycles)}")
    # U-weighted harm pricing
    for name,lst in (("ADDED",added_cycles),("REMOVED",removed_cycles)):
        if not lst: continue
        wl=wh=wn=0.0
        for t0,amt in lst:
            o=outc(u,t0)
            if not o: continue
            mn,mx=o
            if mn<70: wl+=amt
            elif mx>180: wh+=amt
            else: wn+=amt
        s=wl+wh+wn
        if s>0:
            tag={"ADDED":"pre-low=risky / pre-high=useful","REMOVED":"pre-low=protective / pre-high=costly"}[name]
            print(f"   {name} insulin: {s:.1f}U priced → pre-low {wl:.1f}U ({100*wl/s:.0f}%) | pre-high-only {wh:.1f}U ({100*wh/s:.0f}%) | in-range {wn:.1f}U ({100*wn/s:.0f}%)   [{tag}]")
print("="*90)
