#!/usr/bin/env python3
"""KAIROS Twin — assemble one person's aligned physiological record on a 5-min grid.
CGM + oref baselines from the DB; insulin delivered (SMB + integrated temp-basal) from Nightscout.
Saves twin_data_tim.npz. Personal — scratchpad only."""
import os
import json, urllib.request, urllib.parse, ssl, time, datetime
import numpy as np, psycopg2

site=[s for s in json.load(open(os.path.expanduser('~/.config/boost_backtest/sites.json')))['sites'] if s['tag']=='self'][0]
BASE,TOKEN=site['base'],site['token']
CTX=ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
DT=300  # 5-min grid (seconds)
DAYS=45

def ns(path,params,retries=4):
    params=dict(params); params['token']=TOKEN
    url=f"{BASE}/api/v1/{path}?"+urllib.parse.urlencode(params)
    for a in range(retries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'x'}),timeout=90,context=CTX))
        except Exception:
            if a==retries-1: raise
            time.sleep(2*(a+1))
def iso(dt): return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
def parse(s): return datetime.datetime.fromisoformat(s.replace('Z','').split('.')[0]).replace(tzinfo=datetime.timezone.utc).timestamp()

now=datetime.datetime.now(datetime.timezone.utc); start=now-datetime.timedelta(days=DAYS)
t0=int(start.timestamp()//DT*DT); t1=int(now.timestamp()//DT*DT); grid=np.arange(t0,t1,DT); n=len(grid)
gi={t:i for i,t in enumerate(grid)}

# ---- insulin delivered per 5-min bin (Nightscout treatments, chunked) ----
ins=np.zeros(n)
chunks=[]; c=start
while c<now:
    b=min(c+datetime.timedelta(days=7),now); chunks.append((c,b)); c=b
tb=[]  # temp basals (t, rate, dur)
for a,b in chunks:
    tr=ns('treatments.json',{'find[created_at][$gte]':iso(a),'find[created_at][$lt]':iso(b),'count':'20000'})
    for x in tr:
        ca=x.get('created_at')
        if not ca: continue
        ts=parse(ca)
        amt=x.get('insulin')
        if amt and amt>0:                       # boluses / SMBs
            k=int((ts//DT*DT-t0)//DT)
            if 0<=k<n: ins[k]+=amt
        if x.get('eventType') in ('Temp Basal','Temporary Basal'):
            rate=x.get('rate'); rate=(x.get('absolute') if rate is None else rate) or 0.0
            tb.append((ts,float(rate),float(x.get('duration') or 30)))
    print(f"  insulin {a.date()}..{b.date()} ok")
# integrate temp basals: each active until next event (cap at duration), split onto 1-min then bin
tb.sort()
for i,(ts,rate,dur) in enumerate(tb):
    end=ts+dur*60
    if i+1<len(tb): end=min(end,tb[i+1][0])
    m=ts
    while m<end:
        k=int((m//DT*DT-t0)//DT)
        if 0<=k<n: ins[k]+=rate*(min(end,(int(m//DT)+1)*DT)-m)/3600.0
        m=(int(m//DT)+1)*DT
print(f"insulin: total {ins.sum():.0f}U over {DAYS}d ({ins.sum()/DAYS:.1f} U/day)")

# ---- CGM + oref baselines per bin (DB, 5-min dedupe; take last in bin) ----
conn=psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur=conn.cursor()
cur.execute("""select ts_epoch, cgm_mgdl, sug_eventualbg, reason_iobpredbg, reason_minguardbg
               from boost_decisions where user_id='tim' and cgm_mgdl is not null
               and ts_utc > now() - interval '%s days' order by ts_epoch""",(DAYS+1,))
cgm=np.full(n,np.nan); eventual=np.full(n,np.nan); iobpred=np.full(n,np.nan)
for ep,g,ev,ip,mg in cur.fetchall():
    k=int((ep//DT*DT-t0)//DT)
    if 0<=k<n and g and g>0:
        cgm[k]=g
        if ev: eventual[k]=ev
        if ip: iobpred[k]=ip
cov=np.mean(~np.isnan(cgm))
print(f"CGM coverage: {cov*100:.0f}% of {n} bins ({np.sum(~np.isnan(cgm))} readings)")

np.savez('twin_data_tim.npz', grid=grid, ins=ins, cgm=cgm, eventual=eventual, iobpred=iobpred, dt=DT)
print("saved twin_data_tim.npz")
