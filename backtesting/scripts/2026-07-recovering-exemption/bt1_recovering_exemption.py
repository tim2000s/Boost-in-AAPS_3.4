#!/usr/bin/env python3
"""BT1 — RECOVERING v1-bound exemption for the composed brake-floor (ADDS insulin).

Candidate: let ONLY the floor bypass the non-meal v1-bound in RECOVERING, gated on
the floor's existing conditions PLUS delta>=0 (still rising, not bouncing):
    state=RECOVERING & BG>160 & (eventualBG-target)>20 & awake(07-22 local)
    & !postRescue(min45>=75) & budget>0 & delta5>=0
Added dose per eligible cycle = min(budget*F, committedCap) - current_delivered,
where current_delivered on RECOVERING = min(fd, v1_units) (the non-meal cap;
= 0 when v1_units=0, which is the whole point).

Priced by the full two-test bar; delta>=0 vs the re-engage-rejected population
(sustained-delta re-engage: delta>3 for >=3 consecutive) checked on IOB.
"""
import numpy as np, pandas as pd, psycopg2, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"); os.makedirs(OUT, exist_ok=True)

CAP_ERAS = {
    "tim":[("2026-06-01",.25),("2026-06-12",.5),("2026-06-14",.4),("2026-07-02",.5),("2026-07-07",1.0)],
    "A":[("2026-06-17",.25),("2026-07-01",.5)],"B":[("2026-06-18",.25),("2026-07-01",.5),("2026-07-02",.6)],
    "C":[("2026-06-19",.25)],"D":[("2026-06-17",.25)],"E":[("2026-06-17",.25),("2026-06-30",.5)],
    "F":[("2026-06-18",.25),("2026-06-29",.5)],"H":[("2026-06-30",.8),("2026-07-06",1.8)]}
# 14d TBR baselines (07-07 re-review; tim updated incl. last night)
TBR14 = {"tim":(3.11,0.51),"A":(1.11,0.22),"B":(3.83,1.01),"C":(3.82,0.60),
         "D":(10.14,1.81),"E":(1.04,0.00),"F":(2.99,0.35),"H":(1.35,0.28)}
def op_cap(u,d):
    c=None
    for s,v in CAP_ERAS.get(u,[]):
        if d>=pd.to_datetime(s).date(): c=v
    return c

conn=psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df=pd.read_sql("""
SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
 user_id, ts_epoch, ts_utc, cgm_mgdl bg, boostv5_state state, boostv5_finaldose fd,
 boostv5_budget budget, v1_units, sug_eventualbg ev, sug_current_target tgt,
 iob_iob iob, variable_sens isf, tdd
FROM boost_decisions WHERE boostv5_state IS NOT NULL
ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
""",conn).sort_values(["user_id","ts_epoch"]).reset_index(drop=True)
conn.close()
dtc=pd.to_datetime(df.ts_utc,utc=True,format="mixed")
df["hour"]=(dtc.dt.hour+1)%24; df["date"]=dtc.dt.date
df["dt"]=df.groupby("user_id").ts_epoch.diff()/60
df["delta5"]=df.groupby("user_id").bg.diff()/df.dt*5
df.loc[(df.dt>7.6)|(df.dt<2.0),"delta5"]=np.nan
df["cap"]=[op_cap(u,d) for u,d in zip(df.user_id,df.date)]
# rolling min45 + forward low70/low54
n=len(df); min45=np.full(n,np.nan); low70=np.zeros(n,bool); low54=np.zeros(n,bool)
for _,g in df.groupby("user_id",sort=False):
    ts=g.ts_epoch.values; bg=g.bg.values; idx=g.index.values; m=len(g); j=0
    for i in range(m):
        while ts[i]-ts[j]>2700: j+=1
        min45[idx[i]]=np.nanmin(bg[j:i+1])
    for i in range(m):
        k=i+1
        while k<m and ts[k]-ts[i]<=10800: k+=1
        w=bg[i+1:k]; low70[idx[i]]=(w<70).any(); low54[idx[i]]=(w<54).any()
df["min45"]=min45; df["low70"]=low70; df["low54"]=low54

ce=df[df.cap.notna()].copy()
udays={u:ce[ce.user_id==u].date.nunique() for u in ce.user_id.unique()}
# floor gate for RECOVERING (with delta>=0), v1-bound currently zeroing it
ce["cur_deliv"]=np.minimum(ce.fd, ce.v1_units.fillna(0))
gate=((ce.state=="RECOVERING")&(ce.bg>160)&((ce.ev-ce.tgt)>20)&(ce.hour.between(7,22))
      &(ce.min45>=75)&(ce.budget>0)&(ce.delta5>=0))
print("=== BT1: RECOVERING floor-exemption ===")
print(f"capped-era cycles {len(ce)}; RECOVERING-gate cycles (delta>=0) {int(gate.sum())}")

for F in (0.15,0.25,0.35):
    g=ce[gate].copy()
    g["floored"]=np.minimum(g.budget*F, g.cap)
    g["added"]=(g.floored-g.cur_deliv).clip(lower=0)
    tot=g[g.added>0]
    print(f"\n--- F={F} ---")
    print(f"cycles with added>0: {len(tot)} | added total {g.added.sum():.1f}U")
    rows=[]
    for u,gu in g.groupby("user_id"):
        add=gu.added.sum(); d=udays[u]; isf=1800/df[df.user_id==u].tdd.median()
        pre70=gu.loc[gu.low70,"added"].sum(); pre54=gu.loc[gu.low54,"added"].sum()
        # dTBR<70 bracket [0.15,0.6]*ISF min per pre-low U
        lo=100*pre70*0.15*isf/(d*1440); hi=100*pre70*0.6*isf/(d*1440)
        lo54=100*pre54*0.15*isf/(d*1440); hi54=100*pre54*0.6*isf/(d*1440)
        b70,b54=TBR14.get(u,(np.nan,np.nan))
        testA=("PASS" if (b70+hi<=3.5 and b54+hi54<=0.8) else ("MARG" if b70+lo<=3.5 and b54+lo54<=0.8 else "FAIL"))
        rows.append(dict(user=u,cyc=len(gu[gu.added>0]),addU=round(add,2),U_day=round(add/d,3),
            pre70U=round(pre70,2),pre54U=round(pre54,2),
            dTBR70=f"{lo:.2f}-{hi:.2f}",dTBR54=f"{lo54:.2f}-{hi54:.2f}",
            base70=b70,base54=b54,testA=testA,med_iob_pctTDD=round(100*gu.iob.median()/df[df.user_id==u].tdd.median(),1)))
    R=pd.DataFrame(rows); print(R.to_string(index=False))
    if F==0.25: R.to_csv(f"{OUT}/bt1_testA_F025.csv",index=False); g.to_csv(f"{OUT}/bt1_eligible_F025.csv",index=False)

# IOB distinction vs re-engage-rejected population
print("\n=== IOB distinction: floor-exemption (delta>=0) vs re-engage-rejected (delta>3 x3) ===")
gset=ce[gate]
# re-engage set: RECOVERING, ev-tgt>20, delta5>3 for >=3 consecutive
reeng=[]
for u,gu in ce[ce.state=="RECOVERING"].groupby("user_id"):
    gu=gu.sort_values("ts_epoch").reset_index(); c=0
    for i in range(len(gu)):
        c=c+1 if (pd.notna(gu.delta5.iloc[i]) and gu.delta5.iloc[i]>3) else 0
        if c>=3 and (gu.ev.iloc[i]-gu.tgt.iloc[i])>20: reeng.append(gu["index"].iloc[i])
reeng_iob=ce.loc[reeng,"iob"]/ce.loc[reeng,"user_id"].map(df.groupby("user_id").tdd.median())
gset_iob=gset.iob/gset.user_id.map(df.groupby("user_id").tdd.median())
print(f"floor-exemption cycles: n={len(gset)}, IOB %TDD p25/50/75 = {np.nanpercentile(gset_iob,[25,50,75]).round(1)}")
print(f"re-engage-rejected cycles: n={len(reeng)}, IOB %TDD p25/50/75 = {np.nanpercentile(reeng_iob,[25,50,75]).round(1) if len(reeng) else 'n/a'}")
print(f"floor added dose med {gset.assign(a=np.minimum(gset.budget*0.25,gset.cap)).a.median():.2f}U vs re-engage full-COMMITTED (budget*1.0) med {ce.loc[reeng,'budget'].median():.2f}U")

# Benefit: tim 07-07 15:14 stretch + cohort climbing-RECOVERING >180 episodes
print("\n=== Benefit: Episode-B-class stretches ===")
t=df[(df.user_id=='tim')]
tt=pd.to_datetime(t.ts_utc,utc=True,format="mixed")
st=t[(tt>=pd.Timestamp('2026-07-07 15:10',tz='UTC'))&(tt<=pd.Timestamp('2026-07-07 15:55',tz='UTC'))]
st=st.assign(floored25=np.minimum(st.budget*0.25, 0.5), elig=((st.state=='RECOVERING')&(st.bg>160)&((st.ev-st.tgt)>20)&(st.delta5>=0)))
print("tim 07-07 15:10-15:55Z stretch (F=0.25 exemption):")
print(st.assign(t=st.ts_utc.astype(str).str[11:16])[["t","bg","state","budget","fd","v1_units","floored25","elig"]].round(2).to_string(index=False))
print(f"  extra delivered by exemption on this stretch: {st.loc[st.elig,'floored25'].sum():.2f}U over {int(st.elig.sum())} cycles (vs 0.00 today)")
