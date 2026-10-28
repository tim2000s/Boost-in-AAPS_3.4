#!/usr/bin/env python3
"""
KAIROS Twin — does the forecast FLOOR lead real lows earlier than oref's own hypo
predictors? (identifiable, no counterfactual — this is the make-or-break test for the
"descent-side withdrawal" idea.)

Ground truth = objective low events from CGM alone (BG crosses <70 having descended from
>=90, deduped 60 min). Predictors, each swept over its own threshold to trace an ROC and
compared AT MATCHED FALSE-ALARM RATE:
  Twin lo30 / lo60   5th-percentile forecast band floor (offline EnKF forecast replay,
                     same design as the validated forecaster: roll fwd under delivered
                     insulin + meal-uncertainty process noise)
  oref minGuardBG    reason_minguardbg  (oref's own min-guard forward BG)
  oref minPredBG     reason_minpredbg
A predictor "leads" a low if it fires in [t*-60min, t*-10min] (>=10 min lead so there is
time to act). FA = firing on a descending cycle with NO low in the next 60 min. Cross-user
then pooled. Raw traces stay in scratchpad; only aggregates reported.
"""
import numpy as np, psycopg2, json
OUT="/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/fb7b1560-69f3-4fc6-a769-04e7236eda2f/scratchpad"
DT=300; SUB=5; M=120; DAYS=45
USERS=['tim','F','H','B','E','A','C']
PRIOR=dict(ka1=0.030,ka2=0.022,p2=0.028,SI=0.00055,SG=0.021,Gb=118.0,taui=12.0,kra=0.020)

def step(x,u,P,dt=1.0):
    Isc1,Isc2,X,Ra,G,Gi=x
    Isc1=Isc1+dt*(-P['ka1']*Isc1)+u; Isc2=Isc2+dt*(P['ka1']*Isc1-P['ka2']*Isc2)
    X=X+dt*(-P['p2']*X+P['p2']*P['SI']*Isc2); Ra=Ra+dt*(-P['kra']*Ra)
    G=G+dt*(-P['SG']*(G-P['Gb'])-X*np.maximum(G,1.0)+Ra); Gi=Gi+dt*((G-Gi)/P['taui'])
    return np.array([Isc1,Isc2,np.maximum(X,0),Ra,np.maximum(G,10.0),np.maximum(Gi,10.0)])
def forward5(x,u5,P):
    for _ in range(SUB): x=step(x,u5/SUB,P)
    return x
Qsd=np.array([0.02,0.02,1e-4,0.55,2.0,0.6]); Qf=np.array([0.0,0.0,0.0,0.95,2.2,0.0]); Rsd=6.0

def run_forecast(CGM,INS,P,horizons=(6,12),seed=1):
    """Filtering EnKF + forecast 5th-pct floor at each horizon. Returns lo{h}[N]."""
    rng=np.random.default_rng(seed); N=len(CGM)
    g0=np.nanmedian(CGM[:200]); g0=120.0 if np.isnan(g0) else g0
    x=np.zeros((6,M)); x[4]=g0+rng.normal(0,8,M); x[5]=g0+rng.normal(0,8,M); x[3]=rng.normal(0,2,M)
    lo={h:np.full(N,np.nan) for h in horizons}
    for i in range(N):
        # forecast floor from current posterior, rolling fwd under delivered insulin + meal noise
        xf=x.copy()
        for j in range(1,max(horizons)+1):
            fut=INS[i+j-1] if i+j-1<N else INS[min(i,N-1)]
            xf=forward5(xf,fut,P)+Qf[:,None]*rng.standard_normal((6,M))
            if j in horizons: lo[j][i]=np.percentile(xf[5],5)
        # assimilate i
        x=forward5(x,INS[i],P)+(Qsd[:,None]*rng.standard_normal((6,M)))
        x[4]=np.maximum(x[4],10); x[5]=np.maximum(x[5],10); x[2]=np.maximum(x[2],0)
        if not np.isnan(CGM[i]):
            y=CGM[i]; hx=x[5]; hm=hx.mean(); xm=x.mean(1,keepdims=True)
            Pxy=((x-xm)*(hx-hm)).mean(1); Pyy=((hx-hm)**2).mean()+Rsd**2; K=Pxy/Pyy
            x=x+K[:,None]*(y+rng.normal(0,Rsd,M)-hx)[None,:]
            x[4]=np.maximum(x[4],10); x[5]=np.maximum(x[5],10); x[2]=np.maximum(x[2],0)
    return lo

def pull(cur,uid):
    cur.execute("""select ts_epoch,cgm_mgdl,boostv5_finaldose,sug_rate,reason_minguardbg,
                          reason_minpredbg,iob_iob
                   from boost_decisions where user_id=%s and cgm_mgdl is not null and boostv5_active
                     and ts_utc>now()-interval '%s days' order by ts_epoch""",(uid,DAYS))
    rows=cur.fetchall()
    if not rows: return None
    ep=np.array([r[0] for r in rows],float); t0=int(ep.min()//DT*DT); t1=int(ep.max()//DT*DT)
    grid=np.arange(t0,t1+DT,DT); n=len(grid)
    cgm=np.full(n,np.nan); ins=np.zeros(n); mg=np.full(n,np.nan); mp=np.full(n,np.nan); iob=np.full(n,np.nan)
    for ts,g,fd,sr,mgb,mpb,ib in rows:
        k=int((ts//DT*DT-t0)//DT)
        if not (0<=k<n): continue
        if g and g>0: cgm[k]=g
        ins[k]=(fd or 0.0)+(sr or 0.0)/12.0
        if mgb is not None: mg[k]=mgb
        if mpb is not None: mp[k]=mpb
        if ib is not None: iob[k]=ib
    # unit-normalise oref guard/pred BG to mg/dL — the column is mmol/L for most users
    # (median ~5, can be negative) but mg/dL for some (E, median ~100). Detect by scale.
    for arr in (mg,mp):
        med=np.nanmedian(np.abs(arr))
        if not np.isnan(med) and med<30: arr*=18.0   # mmol/L -> mg/dL
    return dict(grid=grid,cgm=cgm,ins=ins,mg=mg,mp=mp,iob=iob)

def low_events(cgm):
    n=len(cgm); ev=[]; last=-999
    for t in range(6,n):
        if np.isnan(cgm[t]) or np.isnan(cgm[t-1]): continue
        if cgm[t]<70 and cgm[t-1]>=70 and np.nanmax(cgm[max(0,t-6):t])>=90 and (t-last)>12:
            ev.append(t); last=t
    return ev

LEAD_MIN,LEAD_MAX=2,12   # fire window t*-60 .. t*-10 min (>=10min lead)
def eval_predictor(fire, cgm, evs, n):
    """fire[t]=bool. Returns (sens, median_lead_min, fa_rate)."""
    ev_mask=np.zeros(n,bool)
    for t in evs: ev_mask[max(0,t-18):min(n,t+6)]=True   # peri-low exclusion for FA
    # sensitivity + lead
    hit=0; leads=[]
    for t in evs:
        w0=max(0,t-LEAD_MAX); w1=max(0,t-LEAD_MIN+1)
        idx=[k for k in range(w0,w1) if fire[k]]
        if idx: hit+=1; leads.append((t-idx[0])*5.0)
    sens=hit/max(1,len(evs)); medlead=float(np.median(leads)) if leads else None
    # false alarm: descending cycles, no low in next 60min, not peri-low
    elig=fa=0
    for t in range(1,n-12):
        if np.isnan(cgm[t]) or np.isnan(cgm[t-1]) or cgm[t]>=cgm[t-1]: continue
        if ev_mask[t]: continue
        if any(k in evs for k in range(t+1,t+13)): continue
        elig+=1
        if fire[t]: fa+=1
    return sens, medlead, fa/max(1,elig)

def sweep(valfn, thr_grid, cgm, evs, n, below=True):
    """valfn(t)->scalar predictor; fire when value<thr (below) else >thr. Returns ROC list."""
    roc=[]
    for th in thr_grid:
        fire=np.array([ (valfn(t)<th) if below else (valfn(t)>th) for t in range(n)])
        s,l,f=eval_predictor(fire,cgm,evs,n)
        roc.append(dict(thr=th,sens=round(s,3),lead=l,fa=round(f,3)))
    return roc

def main():
    conn=psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur=conn.cursor()
    TH_LO=[55,60,65,70,75,80,85,90]           # forecast-floor / guardBG thresholds (mg/dL)
    agg={k:{th:[0,0,0,0] for th in TH_LO} for k in ('lo30','lo60','minguard','minpred')}  # [hit,nev,fa,elig]
    lead_pool={k:{th:[] for th in TH_LO} for k in ('lo30','lo60','minguard','minpred')}
    per_user={}
    for uid in USERS:
        d=pull(cur,uid)
        if d is None: print(f"{uid}: none"); continue
        cgm=d['cgm']; n=len(cgm); P=dict(PRIOR); P['Gb']=float(np.nanmedian(cgm))
        lo=run_forecast(cgm,d['ins'],P); evs=low_events(cgm)
        preds={'lo30':lambda t:lo[6][t] if not np.isnan(lo[6][t]) else 999,
               'lo60':lambda t:lo[12][t] if not np.isnan(lo[12][t]) else 999,
               'minguard':lambda t:d['mg'][t] if not np.isnan(d['mg'][t]) else 999,
               'minpred':lambda t:d['mp'][t] if not np.isnan(d['mp'][t]) else 999}
        pu={}
        for name,fn in preds.items():
            for th in TH_LO:
                fire=np.array([fn(t)<th for t in range(n)])
                # accumulate raw counts for pooling
                ev_mask=np.zeros(n,bool)
                for t in evs: ev_mask[max(0,t-18):min(n,t+6)]=True
                hit=0
                for t in evs:
                    idx=[k for k in range(max(0,t-LEAD_MAX),max(0,t-LEAD_MIN+1)) if fire[k]]
                    if idx: hit+=1; lead_pool[name][th].append((t-idx[0])*5.0)
                elig=fa=0
                for t in range(1,n-12):
                    if np.isnan(cgm[t]) or np.isnan(cgm[t-1]) or cgm[t]>=cgm[t-1] or ev_mask[t]: continue
                    if any(k in evs for k in range(t+1,t+13)): continue
                    elig+=1; fa+= 1 if fire[t] else 0
                a=agg[name][th]; a[0]+=hit; a[1]+=len(evs); a[2]+=fa; a[3]+=elig
            # per-user op point near fa~0.10 for print
        pu_nev=len(evs)
        per_user[uid]=dict(n_lows=pu_nev)
        print(f"{uid}: lows={pu_nev}  (forecast replay done, n={n})")
    # build pooled ROCs
    def roc(name):
        out=[]
        for th in TH_LO:
            hit,nev,fa,elig=agg[name][th]
            out.append(dict(thr=th,sens=round(hit/max(1,nev),3),fa=round(fa/max(1,elig),3),
                            lead=round(float(np.median(lead_pool[name][th])),1) if lead_pool[name][th] else None))
        return out
    rocs={k:roc(k) for k in ('lo30','lo60','minguard','minpred')}
    # matched-SENSITIVITY comparison: at each target sens, each predictor's LOWEST-FA
    # operating point that still catches >= target (report its fa + lead). Sensitivity
    # saturates high here, so FA is the discriminating axis.
    def best_at_sens(r,tgt):
        ok=[x for x in r if x['sens']>=tgt]
        return min(ok,key=lambda x:x['fa']) if ok else None
    comparisons=[]
    for tgt in (0.86,0.90,0.94):
        row={'target_sens':tgt}
        for name in ('lo30','lo60','minguard','minpred'):
            b=best_at_sens(rocs[name],tgt)
            row[name]=dict(fa=b['fa'],lead=b['lead'],sens=b['sens'],thr=b['thr']) if b else None
        comparisons.append(row)
    out=dict(rocs=rocs, matched_sensitivity=comparisons, per_user=per_user, total_lows=sum(v['n_lows'] for v in per_user.values()))
    json.dump(out,open(f"{OUT}/twin_hypo_lead.json","w"),indent=2)
    print(f"\ntotal low events: {out['total_lows']}")
    for name in ('lo30','lo60','minguard','minpred'):
        print(f"\n{name} ROC:")
        for r in rocs[name]: print(f"  thr={r['thr']:>3}  sens={r['sens']:.2f}  fa={r['fa']:.3f}  lead={r['lead']}min")
    print("\n=== MATCHED-SENSITIVITY (lowest false-alarm to catch >= target; fa/lead) ===")
    for c in comparisons:
        def fmt(k): x=c[k]; return f"{k}: fa={x['fa']:.3f} lead={x['lead']}m" if x else f"{k}: n/a"
        print(f"  catch>={c['target_sens']:.2f}:  {fmt('lo30')}  |  {fmt('minpred')}  |  {fmt('minguard')}  |  {fmt('lo60')}")
    conn.close()

if __name__=='__main__': main()
