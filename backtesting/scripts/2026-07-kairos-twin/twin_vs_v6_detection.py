#!/usr/bin/env python3
"""
KAIROS Twin vs V6 state machine — UNANNOUNCED-MEAL DETECTION TIMING & ATTRIBUTION.

Identifiable (no counterfactual): replay the validated offline EnKF over each user's
historical CGM to recover the latent glucose-appearance state Ra, and compare *when* Ra
flags a meal against *when* V6's logged state machine commits (OBSERVING->CONFIRMED),
both measured relative to a CGM-defined meal onset that NEITHER detector gets to define.

Two questions:
  1. DETECTION LEAD  — minutes by which Ra's meal-flag precedes V6's confirm, per onset.
  2. ATTRIBUTION     — on rising cycles, where Ra says "appearance/meal" vs where V6's
                       guards held/braked (attributed the rise to non-meal), and the
                       converse (V6 dosed where Ra saw no appearance = rebound/sensitivity).

Cross-user: aggregated per-user (the user is the group) then pooled. Per-person Gb only;
all other params at population priors — Ra detection is a CHANGE-POINT on Ra's own trailing
baseline, robust to per-user SI/TDD bias. Raw traces stay in scratchpad; report is aggregate.
"""
import numpy as np, psycopg2, json, sys

OUT = "/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/fb7b1560-69f3-4fc6-a769-04e7236eda2f/scratchpad"
DT = 300; SUB = 5; M = 150
USERS = ['tim','F','H','B','E','A','C']

# ---- physiological model (faithful copy of twin_model.step; Gb per-user) ----
PRIOR = dict(ka1=0.030, ka2=0.022, p2=0.028, SI=0.00055, SG=0.021, Gb=118.0, taui=12.0, kra=0.020)
def step(x, u, P, dt=1.0):
    Isc1,Isc2,X,Ra,G,Gi = x
    Isc1 = Isc1 + dt*(-P['ka1']*Isc1) + u
    Isc2 = Isc2 + dt*(P['ka1']*Isc1 - P['ka2']*Isc2)
    X    = X + dt*(-P['p2']*X + P['p2']*P['SI']*Isc2)
    Ra   = Ra + dt*(-P['kra']*Ra)
    G    = G + dt*(-P['SG']*(G-P['Gb']) - X*np.maximum(G,1.0) + Ra)
    Gi   = Gi + dt*((G-Gi)/P['taui'])
    return np.array([Isc1,Isc2,np.maximum(X,0),Ra,np.maximum(G,10.0),np.maximum(Gi,10.0)])
def forward5(x, u5, P):
    for _ in range(SUB): x = step(x, u5/SUB, P)
    return x

Qsd = np.array([0.02,0.02,1e-4,0.55,2.0,0.6]); Rsd = 6.0
def run_filter(CGM, INS, P, seed=1):
    """Filtering-only EnKF (no forecast). Returns est[N,6]; column 3 = Ra."""
    rng = np.random.default_rng(seed); N = len(CGM)
    g0 = np.nanmedian(CGM[:200]); g0 = 120.0 if np.isnan(g0) else g0
    x = np.zeros((6,M)); x[4]=g0+rng.normal(0,8,M); x[5]=g0+rng.normal(0,8,M); x[3]=rng.normal(0,2,M)
    est = np.full((N,6), np.nan)
    for i in range(N):
        x = forward5(x, INS[i], P) + (Qsd[:,None]*rng.standard_normal((6,M)))
        x[4]=np.maximum(x[4],10); x[5]=np.maximum(x[5],10); x[2]=np.maximum(x[2],0)
        if not np.isnan(CGM[i]):
            y=CGM[i]; hx=x[5]; hm=hx.mean(); xm=x.mean(1,keepdims=True)
            Pxy=((x-xm)*(hx-hm)).mean(1); Pyy=((hx-hm)**2).mean()+Rsd**2; K=Pxy/Pyy
            x=x+K[:,None]*(y+rng.normal(0,Rsd,M)-hx)[None,:]
            x[4]=np.maximum(x[4],10); x[5]=np.maximum(x[5],10); x[2]=np.maximum(x[2],0)
        est[i]=x.mean(1)
    return est

# ---- per-user aligned pull ----
DAYS = 45
def pull(cur, uid):
    cur.execute("""select ts_epoch, cgm_mgdl, boostv5_state, boostv5_score, ml_meal_likely,
                          boostv5_budget, boostv5_finaldose, sug_rate, iob_iob, boostv5_active
                   from boost_decisions where user_id=%s and cgm_mgdl is not null
                     and boostv5_active and ts_utc > now() - interval '%s days'
                   order by ts_epoch""", (uid, DAYS))
    rows = cur.fetchall()
    if not rows: return None
    ep = np.array([r[0] for r in rows], float)
    t0 = int(ep.min()//DT*DT); t1 = int(ep.max()//DT*DT); grid = np.arange(t0, t1+DT, DT); n=len(grid)
    cgm=np.full(n,np.nan); state=np.array(['']*n,dtype=object); score=np.full(n,np.nan)
    meal=np.full(n,np.nan); budget=np.full(n,np.nan); ins=np.zeros(n); iob=np.full(n,np.nan)
    for ts,g,st,sc,ml,bg,fd,sr,ib,act in rows:
        k=int((ts//DT*DT-t0)//DT)
        if not (0<=k<n): continue
        if g and g>0: cgm[k]=g
        state[k]=st or ''; score[k]=sc if sc is not None else np.nan
        meal[k]=ml if ml is not None else np.nan; budget[k]=bg if bg is not None else np.nan
        iob[k]=ib if ib is not None else np.nan
        ins[k]=(fd or 0.0) + (sr or 0.0)/12.0   # SMB + basal (U/hr -> U/5min)
    return dict(grid=grid,cgm=cgm,state=state,score=score,meal=meal,budget=budget,ins=ins,iob=iob)

# ---- objective meal onset from CGM alone (detector-independent) ----
def onsets(cgm):
    n=len(cgm); on=[]; last=-999
    for t in range(n-9):
        if np.isnan(cgm[t]) or not (80 <= cgm[t] <= 170): continue
        fwd = cgm[t:t+10]
        if np.mean(np.isnan(fwd)) > 0.3: continue          # need coverage over the 45-min window
        rise = np.nanmax(fwd) - cgm[t]
        d1 = (cgm[t+1]-cgm[t]) if not np.isnan(cgm[t+1]) else 0
        if rise >= 30 and d1 > 0 and (t-last) > 12:        # >=30 mg/dL rise in 45min, >60min since last
            on.append(t); last=t
    return on

# ---- Ra change-point detector: Ra rises >=RA_JUMP above its trailing-30min median ----
RA_JUMP = 1.2   # mg/dL/min above trailing baseline = "appearance detected"
def ra_fire(ra, t0, t1):
    for t in range(t0, t1):
        base = np.nanmedian(ra[max(0,t-6):t]) if t>=2 else 0.0
        if ra[t] - base >= RA_JUMP and ra[t] > 0.8:
            return t
    return None
def v6_fire(state, t0, t1):
    for t in range(t0, t1):
        if state[t] in ('CONFIRMED','COMMITTED'):
            return t
    return None

def main():
    conn=psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur=conn.cursor()
    per_user={}; all_leads=[]; attrib_pool=dict(agree=0,twin_early=0,v6_only=0,quiet=0)
    for uid in USERS:
        d=pull(cur,uid)
        if d is None: print(f"{uid}: no data"); continue
        cgm=d['cgm']; P=dict(PRIOR); P['Gb']=float(np.nanmedian(cgm))
        est=run_filter(cgm,d['ins'],P); ra=est[:,3]
        # sanity: filter tracks CGM
        m=~np.isnan(cgm); fit=np.sqrt(np.nanmean((est[m,5]-cgm[m])**2))
        ons=onsets(cgm); leads=[]; matched=0
        for t in ons:
            w0=max(0,t-3); w1=min(len(cgm),t+13)          # -15min .. +60min search window
            rt=ra_fire(ra,w0,w1); vt=v6_fire(d['state'],w0,w1)
            if rt is not None and vt is not None:
                leads.append((vt-rt)*5.0); matched+=1      # +ve = Ra earlier (minutes)
        all_leads += leads
        # attribution on rising cycles (delta>3 mg/dL/5min, not already high)
        for t in range(1,len(cgm)):
            if np.isnan(cgm[t]) or np.isnan(cgm[t-1]): continue
            if cgm[t]-cgm[t-1] <= 3 or cgm[t] > 200: continue
            base=np.nanmedian(ra[max(0,t-6):t]) if t>=2 else 0.0
            twin_meal = (ra[t]-base >= RA_JUMP and ra[t] > 0.8)
            v6_meal = d['state'][t] in ('CONFIRMED','COMMITTED')
            if twin_meal and v6_meal: attrib_pool['agree']+=1
            elif twin_meal and not v6_meal: attrib_pool['twin_early']+=1
            elif v6_meal and not twin_meal: attrib_pool['v6_only']+=1
            else: attrib_pool['quiet']+=1
        per_user[uid]=dict(n_onsets=len(ons), matched=matched, fit=round(fit,1),
                           lead_med=round(float(np.median(leads)),1) if leads else None,
                           lead_mean=round(float(np.mean(leads)),1) if leads else None,
                           lead_p25=round(float(np.percentile(leads,25)),1) if leads else None,
                           lead_p75=round(float(np.percentile(leads,75)),1) if leads else None,
                           twin_earlier_pct=round(100*np.mean(np.array(leads)>0),0) if leads else None)
        print(f"{uid}: fit={fit:.1f} onsets={len(ons)} matched={matched} "
              f"lead_med={per_user[uid]['lead_med']}min twin_earlier={per_user[uid]['twin_earlier_pct']}%")
    # per-user-then-pooled lead
    user_meds=[v['lead_med'] for v in per_user.values() if v['lead_med'] is not None]
    summary=dict(per_user=per_user,
                 pooled_lead_median=round(float(np.median(all_leads)),1) if all_leads else None,
                 pooled_lead_mean=round(float(np.mean(all_leads)),1) if all_leads else None,
                 pooled_twin_earlier_pct=round(100*np.mean(np.array(all_leads)>0),0) if all_leads else None,
                 cross_user_median_of_medians=round(float(np.median(user_meds)),1) if user_meds else None,
                 n_matched_onsets=len(all_leads),
                 attribution=attrib_pool,
                 attribution_pct={k:round(100*v/max(1,sum(attrib_pool.values())),1) for k,v in attrib_pool.items()},
                 params=dict(RA_JUMP=RA_JUMP, onset_rise_mgdl=30, window="-15..+60min"))
    json.dump(summary, open(f"{OUT}/twin_vs_v6_detection.json","w"), indent=2)
    print("\n=== POOLED ==="); print(json.dumps(summary, indent=2, default=str)[:1500])
    conn.close()

if __name__=='__main__': main()
