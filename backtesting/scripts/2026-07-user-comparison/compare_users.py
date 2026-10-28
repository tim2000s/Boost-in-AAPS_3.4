#!/usr/bin/env python3
"""compare_users.py — repeatable, auditable side-by-side of two users' V6 experience.

Usage:
    python3 compare_users.py [USER_A] [USER_B]        # default: tim H
    python3 compare_users.py --out-dir out --report REPORT.md

Deterministic. Dedup = last-invoke row per (user, floor(ts_epoch/300)). V6-ACTIVE era only
(boostv5_active = true — i.e. cycles where V6 actually DROVE the pump, not shadow). This matters:
tim only went V6-active ~2026-06-26; his earlier boost-other history was V1/V3 acting with V6
in shadow, so `boostv5_state IS NOT NULL` overstated his "V6 experience" ~13x. Glycemia from
boost_cgm (dense) over each user's V6-ACTIVE range.
Emits: <out>/comparison_<A>_vs_<B>.csv (machine-readable metric table) + a markdown report.

Field-availability: gateReduction/confirmGate/console-maxIOB telemetry only exist ~post 07-02;
each affected metric declares the sub-window and cycle count it used. Missing fields degrade
gracefully (NaN, excluded from denominators, flagged non-comparable if windows differ materially).

DB: TimescaleDB `oref` @ 127.0.0.1:5432, table public.boost_decisions + boost_cgm.
"""
import sys, os, argparse, re
import numpy as np, pandas as pd, psycopg2

FACTORY = dict(committedcap=0.5, confirmedcap=2.5, knob=1.0, maxiob=1.0)  # Simple-Mode default proxies
MEAL_STATES = ("CONFIRMED", "COMMITTED", "RECOVERING")

def load_decisions(conn, user):
    q = """
    SELECT DISTINCT ON (floor(ts_epoch/300.0))
      ts_epoch, ts_utc, cgm_mgdl bg, boostv5_state state, boostv5_age age,
      boostv5_finaldose fd, boostv5_budget budget, boostv5_score score, v1_units,
      boostv5_committedcap ccap, boostv5_confirmedcap fcap, boostv5_aggressionknob knob,
      boostv5_cumulativecapu cumcap, boostv5_gatereduction gate, boostv5_confirmgate cgate,
      boostv5_prospectiveshot prosp, iob_iob iob,
      boost_profile_switch ps, boostv5_active v5active,
      steps_60m, steps_5m, iob_activity,
      substring(console_error from 'maxIOB: ?([0-9.,]+)') cons_maxiob,
      (console_error ~* 'G3 HOLD|G3-HOLD') g3hold_console,
      (console_error ~* 'SMB suppressed') smbsupp_console,
      variant
    FROM boost_decisions
    WHERE user_id=%s AND boostv5_active = true
    ORDER BY floor(ts_epoch/300.0), ts_epoch DESC
    """
    df = pd.read_sql(q, conn, params=(user,)).sort_values("ts_epoch").reset_index(drop=True)
    df["cons_maxiob"] = pd.to_numeric(df.cons_maxiob.astype(str).str.replace(",", "."), errors="coerce")
    dtc = pd.to_datetime(df.ts_utc, utc=True, format="mixed")
    df["date"] = dtc.dt.date
    df["hour"] = (dtc.dt.hour + 1) % 24  # local ~ UTC+1
    df["delta5"] = df.bg.diff() / (df.ts_epoch.diff()/60) * 5
    df.loc[(df.ts_epoch.diff()/60 > 7.6) | (df.ts_epoch.diff()/60 < 2.0), "delta5"] = np.nan
    return df

def load_cgm(conn, user, t0, t1):
    q = "SELECT cgm_mgdl bg FROM boost_cgm WHERE user_id=%s AND ts_utc BETWEEN %s AND %s AND cgm_mgdl IS NOT NULL"
    return pd.read_sql(q, conn, params=(user, t0, t1))

def pct(s, cond):
    n = len(s)
    return round(100.0*cond.sum()/n, 1) if n else np.nan

def metrics(df, cgm, user):
    m = {}
    days = max(df.date.nunique(), 1)
    span_days = (df.ts_epoch.max()-df.ts_epoch.min())/86400 if len(df) else np.nan
    # A coverage
    m["A.v6_start"] = str(df.date.min()); m["A.v6_end"] = str(df.date.max())
    m["A.deduped_cycles"] = len(df); m["A.days"] = days
    m["A.cycles_per_day"] = round(len(df)/days, 1)
    for f,lbl in [("cons_maxiob","maxIOB_telem"),("gate","gateReduction"),("cgate","confirmGate")]:
        avail = df[df[f].notna()]
        m[f"A.{lbl}_first"] = str(avail.date.min()) if len(avail) else "n/a"
        m[f"A.{lbl}_cycles"] = int(df[f].notna().sum())
    # B glycemia (dense CGM)
    bg = cgm.bg.dropna()
    m["B.cgm_readings"] = len(bg)
    if len(bg):
        m["B.TIR_70_180"] = pct(bg, bg.between(70,180)); m["B.TING_63_140"] = pct(bg, bg.between(63,140))
        m["B.TBR_70"] = pct(bg, bg<70); m["B.TBR_54"] = pct(bg, bg<54); m["B.TAR_180"] = pct(bg, bg>180)
        m["B.mean_bg"] = round(bg.mean(),1)
    # C dosing
    dos = df[df.fd>0].fd
    m["C.dose_freq_pct"] = pct(df.fd, df.fd>0)
    m["C.mean_nonzero"] = round(dos.mean(),3) if len(dos) else 0.0
    m["C.p50_nonzero"] = round(dos.median(),3) if len(dos) else 0.0
    m["C.p95_nonzero"] = round(dos.quantile(.95),3) if len(dos) else 0.0
    m["C.max_shot"] = round(df.fd.max(),2)
    m["C.U_per_day"] = round(df.fd.sum()/days,2)
    m["C.bigshot_gt1_pct"] = pct(df.fd, df.fd>1); m["C.bigshot_gt2_pct"] = pct(df.fd, df.fd>2)
    # D paired V6 vs V1
    v1 = df.v1_units.fillna(0)
    m["D.v6_mean_delivered"] = round(df.fd.mean(),3); m["D.v1_mean_would"] = round(v1.mean(),3)
    m["D.v6_minus_v1_mean"] = round((df.fd-v1).mean(),3)
    m["D.v6_below_v1_pct"] = pct(df.fd, df.fd < v1-0.001)
    for st in ("CONFIRMED","COMMITTED","RECOVERING","IDLE","OBSERVING"):
        g = df[df.state==st]
        if len(g): m[f"D.v6-v1_{st}"] = round((g.fd-g.v1_units.fillna(0)).mean(),3)
    # E state machine
    for st in ("IDLE","OBSERVING","CONFIRMED","COMMITTED","RECOVERING"):
        m[f"E.pct_{st}"] = pct(df.state, df.state==st)
    fresh_conf = ((df.state=="CONFIRMED")&(df.state.shift()!="CONFIRMED")).sum()
    m["E.confirmed_events_per_day"] = round(fresh_conf/days,2)
    m["E.pct_meal_states"] = pct(df.state, df.state.isin(MEAL_STATES))
    band = df[df.bg.between(150,190)].copy()
    if len(band)>1:
        chg = (band.state != band.state.shift()).sum()
        span_h = (band.ts_epoch.max()-band.ts_epoch.min())/3600
        m["E.flap_changes_per_hr_150_190"] = round(chg/max(span_h,1e-9),2)
    # F budget & suppression
    m["F.budget_mean"] = round(df.budget.mean(),2); m["F.budget_p95"] = round(df.budget.quantile(.95),2)
    hib = df[df.budget>2]
    m["F.budget_gt2_cycles"] = len(hib)
    if len(hib):
        supp = hib.fd < 0.10*hib.budget
        m["F.budget_gt2_suppressed_pct"] = pct(hib.fd, supp)  # deliver <10% of a >2U budget
    # gateReduction breakdown on dosing-suppressed cycles (state wants dose: budget>0.3 & fd < 0.5*budget)
    sub = df[(df.gate.notna())]
    m["F.gate_telem_cycles"] = len(sub)
    cand = sub[(sub.budget>0.3) & (sub.fd < 0.5*sub.budget)]
    m["F.suppressed_cycles(gate-era)"] = len(cand)
    def gate_share(pat): return pct(cand.gate, cand.gate.astype(str).str.contains(pat, case=False, na=False)) if len(cand) else np.nan
    m["F.supp_maxIOB_pct"] = gate_share("maxIOB")
    m["F.supp_iobHeadroom_pct"] = gate_share("iobHeadroom")
    m["F.supp_decel_pct"] = gate_share("decel")
    m["F.supp_minGuard_pct"] = gate_share("min_guard|minGuard")
    m["F.supp_g3hold_pct"] = gate_share("G3|g3_hold|hold")
    m["F.supp_none_pct"] = gate_share("^none$")
    m["F.g3hold_console_pct"] = pct(df.g3hold_console.fillna(False), df.g3hold_console.fillna(False))
    cg = df[df.cgate.notna() & (df.cgate.astype(str)!="n/a")]
    m["F.confirmGate_cycles"] = len(cg)
    if len(cg):
        m["F.confirmGate_blocked_pct"] = pct(cg.cgate, cg.cgate.astype(str).str.contains("block",case=False,na=False))
    # G config & masking
    for f,lbl in [("ccap","committedCap"),("fcap","confirmedCap"),("knob","aggressionKnob"),("cumcap","cumulativeCap"),("cons_maxiob","maxIOB")]:
        vals = df[f].dropna()
        m[f"G.{lbl}_mode"] = round(vals.mode().iloc[0],2) if len(vals) else np.nan
        m[f"G.{lbl}_distinct"] = ",".join(sorted({str(round(v,2)) for v in vals.unique()})[:8]) if len(vals) else "n/a"
    # masking proxies
    mask_caps = (df.ccap==FACTORY["committedcap"]) & (df.fcap==FACTORY["confirmedcap"])
    mask_maxiob = df.cons_maxiob==FACTORY["maxiob"]
    m["G.mask_caps_pct"] = pct(df.ccap.notna(), mask_caps & df.ccap.notna())
    m["G.mask_maxIOB_pct(telem-era)"] = pct(df.cons_maxiob.notna(), mask_maxiob & df.cons_maxiob.notna())
    mask_any = mask_caps | mask_maxiob.fillna(False)
    m["G.mask_any_pct"] = pct(pd.Series(True,index=df.index), mask_any)
    # cross-tab masked vs suppression: do masked cycles deliver less?
    hib2 = df[df.budget>1]
    if len(hib2):
        mk = (hib2.ccap==0.5)&(hib2.fcap==2.5) | (hib2.cons_maxiob==1.0).fillna(False)
        m["G.masked_budget>1_deliverpct"] = round(100*hib2[mk].fd.sum()/max(hib2[mk].budget.sum(),1e-9),1) if mk.any() else np.nan
        m["G.unmasked_budget>1_deliverpct"] = round(100*hib2[~mk].fd.sum()/max(hib2[~mk].budget.sum(),1e-9),1) if (~mk).any() else np.nan
    # H activity
    m["H.steps_per_day_mean"] = round(df.groupby("date").steps_60m.max().mean(),0) if df.steps_60m.notna().any() else np.nan
    m["H.activity_mean"] = round(df.iob_activity.mean(),3) if df.iob_activity.notna().any() else np.nan
    m["H.pct_profileswitch_active"] = pct(df.ps.notna(), (df.ps.notna())&(df.ps!=100))
    m["H.pct_v5active_true"] = pct(df.v5active.notna(), df.v5active.fillna(False))
    return m

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("users", nargs="*", default=["tim","H"])
    ap.add_argument("--out-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),"out"))
    ap.add_argument("--report", default=None,
                    help="report path; default derives from the user pair. NOT overwritten if it exists "
                         "(protects analyst-authored §I Synthesis) unless --force.")
    ap.add_argument("--force", action="store_true", help="overwrite an existing report scaffold")
    a = ap.parse_args()
    users = a.users if a.users else ["tim","H"]
    A,B = users[0], users[1]
    os.makedirs(a.out_dir, exist_ok=True)
    conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
    res = {}
    for u in (A,B):
        df = load_decisions(conn, u)
        if not len(df): raise SystemExit(f"no V6-era data for {u}")
        cgm = load_cgm(conn, u, str(df.ts_utc.min()), str(df.ts_utc.max()))
        res[u] = metrics(df, cgm, u)
    conn.close()
    keys = list(res[A].keys())
    rows = []
    for k in keys:
        va, vb = res[A].get(k), res[B].get(k)
        delta = ""
        try:
            fa, fb = float(va), float(vb)
            delta = round(fb-fa,3); ratio = round(fb/fa,2) if fa not in (0,) else ""
        except (TypeError, ValueError):
            ratio = ""
        rows.append(dict(metric=k, **{A:va, B:vb, "B_minus_A":delta, "ratio_B_over_A":ratio}))
    tab = pd.DataFrame(rows)
    csv = os.path.join(a.out_dir, f"comparison_{A}_vs_{B}.csv")
    tab.to_csv(csv, index=False)                      # CSV always (re)written — it's pure data
    print(f"[written] {csv}  ({len(tab)} metrics)")
    print(tab.to_string(index=False))
    # report path: explicit, else the canonical tim/H name, else derived from the pair
    if a.report:
        report = a.report
    elif {A, B} == {"tim", "H"}:
        report = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","..","reports",
                              "2026-07_tim_vs_userH_v6_comparison_REPORT.md")
    else:
        report = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","..","reports",
                              f"2026-07_{A}_vs_{B}_v6_comparison_REPORT.md")
    if os.path.exists(report) and not a.force:
        print(f"[kept]    {report} exists — NOT overwritten (protects analyst §I Synthesis). "
              f"Data is fresh in the CSV; pass --force to regenerate the scaffold.")
    else:
        with open(report, "w") as f:
            f.write(render_report(A,B,res,csv))
        print(f"[written] {report}")

def render_report(A,B,res,csv):
    def g(u,k,d="—"):
        v=res[u].get(k,d); return d if v is None or (isinstance(v,float) and pd.isna(v)) else v
    L=[]
    L.append(f"# V6 Experience Comparison — {A} vs {B} — 2026-07-07\n")
    L.append(f"Generated by `backtesting/scripts/2026-07-user-comparison/compare_users.py {A} {B}`. "
             f"Machine-readable metric table: `{os.path.basename(csv)}`. Deterministic; dedup last-invoke "
             f"per 5-min bucket; V6-era only (boostv5_state present); glycemia from boost_cgm.\n")
    def line(k,unit="",interp=""):
        va,vb=g(A,k),g(B,k)
        return f"| {k} | {va}{unit} | {vb}{unit} | {res_delta(res,A,B,k)} | {interp} |"
    def sec(title,keys_interp):
        L.append(f"\n## {title}\n\n| metric | {A} | {B} | Δ (B−A) | interpretation |\n|---|---|---|---|---|")
        for k,i in keys_interp: L.append(line(k,"",i))
    sec("A. Coverage",[("A.v6_start",""),("A.v6_end",""),("A.deduped_cycles",""),("A.cycles_per_day",""),
        ("A.maxIOB_telem_first","telemetry sub-window start"),("A.gateReduction_first",""),("A.confirmGate_first","")])
    sec("B. Glycemia (dense CGM)",[("B.TIR_70_180",""),("B.TING_63_140",""),("B.TBR_70",""),("B.TBR_54",""),
        ("B.TAR_180",""),("B.mean_bg","")])
    sec("C. Dosing delivered",[("C.dose_freq_pct","% cycles fd>0"),("C.mean_nonzero",""),("C.p95_nonzero",""),
        ("C.max_shot",""),("C.U_per_day",""),("C.bigshot_gt1_pct",""),("C.bigshot_gt2_pct","")])
    sec("D. Paired V6 vs V1-would",[("D.v6_mean_delivered",""),("D.v1_mean_would",""),("D.v6_minus_v1_mean",""),
        ("D.v6_below_v1_pct",""),("D.v6-v1_CONFIRMED",""),("D.v6-v1_COMMITTED","")])
    sec("E. State machine",[("E.pct_meal_states",""),("E.confirmed_events_per_day",""),("E.pct_RECOVERING",""),
        ("E.flap_changes_per_hr_150_190","")])
    sec("F. Budget & SUPPRESSION",[("F.budget_mean",""),("F.budget_gt2_cycles",""),
        ("F.budget_gt2_suppressed_pct","% of >2U budgets delivering <10%"),
        ("F.suppressed_cycles(gate-era)",""),("F.supp_maxIOB_pct",""),("F.supp_iobHeadroom_pct",""),
        ("F.supp_decel_pct",""),("F.supp_g3hold_pct",""),("F.confirmGate_blocked_pct","")])
    sec("G. Config & MASKING",[("G.committedCap_mode",""),("G.confirmedCap_mode",""),("G.maxIOB_mode",""),
        ("G.aggressionKnob_mode",""),("G.mask_caps_pct","% cycles caps==factory 0.5/2.5"),
        ("G.mask_maxIOB_pct(telem-era)","% telem cycles maxIOB==1.0"),("G.mask_any_pct",""),
        ("G.masked_budget>1_deliverpct","% of budget delivered on MASKED cycles"),
        ("G.unmasked_budget>1_deliverpct","% of budget delivered on UNMASKED cycles")])
    sec("H. Activity",[("H.steps_per_day_mean",""),("H.activity_mean",""),("H.pct_profileswitch_active",""),
        ("H.pct_v5active_true","")])
    L.append("\n## I. Synthesis\n\n*(auto-scaffold; fill ranked drivers from the table above — separate "
             "settings-driven [caps/maxIOB/knob/masking §G], algorithm-behavior [suppression/gates §F, "
             "state §E], physiology [glycemia §B, activity §H], data-quality [coverage/sub-windows §A]).*\n")
    L.append("\n## Comparability flags\n\n*(auto-scaffold; flag metrics whose sub-windows or acting mode "
             "differ materially between users — see §A telemetry-first dates and §H v5active.)*\n")
    return "\n".join(L)

def res_delta(res,A,B,k):
    try: return round(float(res[B][k])-float(res[A][k]),3)
    except Exception: return ""

if __name__=="__main__":
    main()
