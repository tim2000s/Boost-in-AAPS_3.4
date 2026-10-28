#!/usr/bin/env python3
"""Figures + tables for the post-meal exercise report (2026-07-28).
Combines the segmented-performance and carb-counterweight-mechanism studies. DB refreshed to now.
Palette: Okabe-Ito (CVD-safe). Semantic: vermillion=lows, orange=highs, blue=in-range."""
import os
import numpy as np, pandas as pd, psycopg2
import matplotlib as mpl; mpl.use("Agg")
import matplotlib.pyplot as plt

OUT = os.path.dirname(os.path.abspath(__file__))
RNG = np.random.default_rng(20260728)
# Okabe-Ito
BLUE, ORANGE, GREEN, VERM, SKY, GREY = "#0072B2", "#E69F00", "#009E73", "#D55E00", "#56B4E9", "#8a8f98"
RED_DEEP = "#9b1d20"
mpl.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    "font.size": 11, "axes.titlesize": 13, "axes.titleweight": "bold", "axes.labelsize": 10.5,
    "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#4a4f57",
    "xtick.labelsize": 10, "ytick.labelsize": 9.5, "figure.dpi": 150,
    "axes.grid": True, "grid.color": "#e6e8 eb".replace(" ", ""), "grid.linewidth": 0.8,
})

conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
d = pd.read_sql("""
 SELECT user_id user, ts_epoch, cgm_mgdl bg, iob_iob iob, steps_30m steps,
        boostv5_finaldose smb, boostv5_state st, sug_cob cob
 FROM boost_decisions WHERE ts_utc >= now() - interval '30 days' AND cgm_mgdl IS NOT NULL
 ORDER BY user_id, ts_epoch
""", conn).drop_duplicates(subset=['user','ts_epoch']).reset_index(drop=True)

# ---- tag post-meal / post-meal-exercise per cycle (8 users w/ step feed) ----
d['pm']=False; d['pmx']=False; d['has_steps']=False
for uid,g in d.groupby('user'):
    idx=g.index; ts=g.ts_epoch.values
    base=g.steps[g.steps>0].median() if (g.steps>0).any() else np.nan
    hs=not np.isnan(base); d.loc[idx,'has_steps']=hs
    st=g.st.values; cob=np.nan_to_num(g.cob.values); steps=g.steps.values
    onset=np.where((st=='CONFIRMED')&(np.concatenate([['x'],st[:-1]])!='CONFIRMED')&(cob==0))[0]
    pm=np.zeros(len(g),bool); pmx=np.zeros(len(g),bool)
    for o in onset:
        win=(ts>=ts[o])&(ts<=ts[o]+180*60); pm|=win
        if hs and ((ts>=ts[o])&(ts<=ts[o]+120*60)&(steps>2*base)).any(): pmx|=win
    d.loc[idx,'pm']=pm; d.loc[idx,'pmx']=pmx
S=d[d.has_steps]

def zones(b):
    return dict(b54=100*(b<54).mean(), b70=100*((b>=54)&(b<70)).mean(),
               tir=100*((b>=70)&(b<=180)).mean(), a180=100*(b>180).mean(),
               ting=100*((b>=63)&(b<=140)).mean(), tbr70=100*(b<70).mean(), mmol=b.mean()/18.016)
segs={'Background\n(non-meal)':S[~S.pm].bg,'Post-meal,\nno exercise':S[S.pm&~S.pmx].bg,'Post-meal,\nwith exercise':S[S.pmx].bg}
segstats={k:zones(v) for k,v in segs.items()}
pct={k:100*len(v)/len(S) for k,v in segs.items()}

# ---- meal-onset events: exercise vs not, low<70 within 3h ----
ev=[]
for uid,g in S.groupby('user'):
    g=g.reset_index(drop=True); ts=g.ts_epoch.values; bg=g.bg.values
    base=g.steps[g.steps>0].median()
    conf=g.index[(g.st=='CONFIRMED')&(g.st.shift()!='CONFIRMED')&(np.nan_to_num(g.cob)==0)]
    for i in conf:
        post=g.iloc[i:min(len(g),i+24)]; fw=g.iloc[i:min(len(g),i+36)]
        if len(fw)<18: continue
        exd=post[post.steps>2*base]
        ex=len(exd)>0
        low=int(fw.bg.min()<70)
        iob_ex=exd.iob.iloc[0] if ex else np.nan
        ev.append(dict(user=uid,ex=ex,low=low,iob_ex=iob_ex,burst=post.smb.fillna(0).iloc[:6].sum(),bg_ex=(exd.bg.iloc[0] if ex else np.nan)))
E=pd.DataFrame(ev)
def rate_ci(mask):
    x=E[mask].low.values
    if len(x)<5: return np.nan,np.nan,np.nan,len(x)
    bs=[100*np.mean(RNG.choice(x,len(x))) for _ in range(3000)]
    return 100*x.mean(), np.percentile(bs,2.5), np.percentile(bs,97.5), len(x)
r_ex=rate_ci(E.ex); r_nox=rate_ci(~E.ex)

# IOB tertiles among exercisers
Ex=E[E.ex].copy(); Ex['ter']=pd.qcut(Ex.iob_ex.rank(method='first'),3,labels=['low','mid','high'])
tert={t:(100*Ex[Ex.ter==t].low.mean(), Ex[Ex.ter==t].iob_ex.median(), len(Ex[Ex.ter==t])) for t in ['low','mid','high']}
crash=Ex[Ex.low==1]; noc=Ex[Ex.low==0]

# per-user: pm-no-ex TAR vs pm-with-ex TBR
pu=[]
for uid,g in S.groupby('user'):
    a=g[g.pm&~g.pmx].bg; b=g[g.pmx].bg
    if len(a)>30 and len(b)>30:
        pu.append(dict(user=uid, tar=100*(a>180).mean(), tbr=100*(b<70).mean()))
PU=pd.DataFrame(pu)

# ================= FIGURES =================
def styleax(ax):
    ax.set_axisbelow(True); ax.grid(axis='y', color="#e7e9ec"); ax.grid(axis='x', visible=False)
    ax.tick_params(length=0)

# Fig 1 — headline contrast
fig,ax=plt.subplots(figsize=(5.4,4.1)); styleax(ax)
xs=[0,1]; vals=[r_nox[0],r_ex[0]]; cols=[BLUE,VERM]
lo=[vals[0]-r_nox[1],vals[1]-r_ex[1]]; hi=[r_nox[2]-vals[0],r_ex[2]-vals[1]]
ax.bar(xs,vals,width=0.62,color=cols,zorder=3)
ax.errorbar(xs,vals,yerr=[lo,hi],fmt='none',ecolor="#2a2d33",elinewidth=1.6,capsize=5,zorder=4)
for x,v,h in zip(xs,vals,hi):
    ax.text(x,v+h+0.9,f"{v:.0f}%",ha='center',va='bottom',fontweight='bold',fontsize=14)
ax.set_xticks(xs); ax.set_xticklabels([f"Meal,\nno exercise\nn={r_nox[3]}",f"Meal +\nexercise\nn={r_ex[3]}"])
ax.set_ylim(0,30); ax.set_ylabel("Low <70 mg/dL within 3 h  (%)")
ax.set_title("Post-meal exercise nearly doubles the low rate")
ax.text(0.5,27.5,"95% CIs do not overlap",ha='center',fontsize=8.5,style='italic',color=GREY)
plt.tight_layout(); plt.savefig(f"{OUT}/fig1_contrast.png",bbox_inches='tight'); plt.close()

# Fig 2 — dose refutation (IOB tertile crash)
fig,ax=plt.subplots(figsize=(5.8,4.1)); styleax(ax)
seq=["#c6dbef","#5b9bd5","#08519c"]  # light->dark blue = low->high IOB
labs=[f"Low\n(~{tert['low'][1]:.1f} U)",f"Mid\n(~{tert['mid'][1]:.1f} U)",f"High\n(~{tert['high'][1]:.1f} U)"]
vals=[tert['low'][0],tert['mid'][0],tert['high'][0]]
ax.bar([0,1,2],vals,width=0.62,color=seq,zorder=3)
for x,v in zip([0,1,2],vals):
    ax.text(x,v+0.8,f"{v:.0f}%",ha='center',va='bottom',fontweight='bold',fontsize=14)
ax.annotate("",xy=(2,vals[2]+4),xytext=(0,vals[0]+4),arrowprops=dict(arrowstyle="->",color=VERM,lw=1.8))
ax.text(1,max(vals)+5.2,r"more insulin on board $\rightarrow$ FEWER crashes",ha='center',color=VERM,fontsize=9.5,fontweight='bold')
nlabs=[f"{l}\nn={tert[t][2]}" for l,t in zip(labs,['low','mid','high'])]
ax.set_xticks([0,1,2]); ax.set_xticklabels(nlabs)
ax.set_xlabel("Insulin on board at the start of exercise")
ax.set_ylim(0,42); ax.set_ylabel("Crash to <70 mg/dL within 3 h  (%)")
ax.set_title("The crash is NOT dose-driven")
plt.tight_layout(); plt.savefig(f"{OUT}/fig2_dose.png",bbox_inches='tight'); plt.close()

# Fig 3 — AGP-style stacked glucose zones per regime
fig,ax=plt.subplots(figsize=(7.6,3.2))
order=list(segs.keys()); y=np.arange(len(order))[::-1]
zc=[('b54',RED_DEEP,'<54'),('b70',VERM,'54–70'),('tir',BLUE,'70–180 (in range)'),('a180',ORANGE,'>180')]
left=np.zeros(len(order))
for key,col,lab in zc:
    w=np.array([segstats[k][key] for k in order])
    ax.barh(y,w,left=left,color=col,height=0.62,label=lab,zorder=3)
    for yi,(wi,li) in enumerate(zip(w,left)):
        if wi>=6: ax.text(li+wi/2,y[yi],f"{wi:.0f}",ha='center',va='center',color='white',fontsize=9,fontweight='bold')
    left+=w
ax.set_yticks(y); ax.set_yticklabels([k+f"\n{pct[k]:.0f}% of time" for k in order],fontsize=9.5)
ax.set_xlim(0,100); ax.set_xlabel("Share of time in glucose zone  (%)")
ax.set_title("Where the loop actually loses ground — by regime")
ax.grid(False); ax.spines['left'].set_visible(False); ax.tick_params(length=0)
ax.legend(ncol=4,loc='upper center',bbox_to_anchor=(0.5,-0.22),frameon=False,fontsize=9,handlelength=1.1)
plt.tight_layout(); plt.savefig(f"{OUT}/fig3_zones.png",bbox_inches='tight'); plt.close()

# Fig 4 — bimodal scatter: disjoint populations
fig,ax=plt.subplots(figsize=(6.4,4.6)); styleax(ax)
ax.axhspan(4,PU.tbr.max()+3,xmin=0,xmax=0.42,color=VERM,alpha=0.06,zorder=0)
ax.axvspan(20,PU.tar.max()+4,ymin=0,ymax=0.35,color=BLUE,alpha=0.06,zorder=0)
ax.scatter(PU.tar,PU.tbr,s=120,color=BLUE,edgecolor='white',linewidth=1.4,zorder=4)
for _,r in PU.iterrows():
    ax.annotate(r.user,(r.tar,r.tbr),xytext=(6,4),textcoords='offset points',fontsize=10,fontweight='bold')
ax.set_xlabel("Post-meal time HIGH (>180) — no exercise  (%)")
ax.set_ylabel("Post-meal time LOW (<70) — with exercise  (%)")
ax.set_title("Two disjoint problems, opposite fixes")
ax.text(PU.tar.max()*0.62,1.2,"HIGH-runners\n(more / earlier meal insulin)",fontsize=9,color=BLUE,fontweight='bold',ha='center')
ax.text(6,PU.tbr.max()*0.86,"TIGHT-runners\n(exercise protection)",fontsize=9,color=VERM,fontweight='bold',ha='left')
ax.set_ylim(-1,PU.tbr.max()+3); ax.set_xlim(-2,PU.tar.max()+6)
plt.tight_layout(); plt.savefig(f"{OUT}/fig4_bimodal.png",bbox_inches='tight'); plt.close()

# ================= TABLES / NUMBERS =================
print("=== SEGMENT TABLE ===")
for k in order:
    s=segstats[k]; print(f"{k.replace(chr(10),' '):28} time%={pct[k]:4.1f} mmol={s['mmol']:.1f} TIR={s['tir']:.1f} TING={s['ting']:.1f} TBR70={s['tbr70']:.1f} TBR54={s['b54']:.2f} TAR180={s['a180']:.1f}")
print(f"\n=== CONTRAST === meal+ex {r_ex[0]:.0f}% CI[{r_ex[1]:.0f},{r_ex[2]:.0f}] n={r_ex[3]} | meal-noex {r_nox[0]:.0f}% CI[{r_nox[1]:.0f},{r_nox[2]:.0f}] n={r_nox[3]}")
print("=== DOSE === IOB tertile crash:", {t:f"{tert[t][0]:.0f}% (IOB~{tert[t][1]:.2f}, n{tert[t][2]})" for t in ['low','mid','high']})
print(f"crashers: IOB={crash.iob_ex.median():.2f} burst={crash.burst.median():.2f} bg={crash.bg_ex.median():.0f} | non: IOB={noc.iob_ex.median():.2f} burst={noc.burst.median():.2f} bg={noc.bg_ex.median():.0f}")
print("=== PER-USER ===\n", PU.round(1).to_string(index=False))
print("figures written to", OUT)
