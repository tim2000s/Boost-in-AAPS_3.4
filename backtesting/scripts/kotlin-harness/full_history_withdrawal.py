#!/usr/bin/env python3
"""Full-history validation of the Twin-forecast insulin WITHDRAWAL, driven by the REAL Kotlin engine.

Framing (developer, 2026-07-20): NOT "is it better than X". Run ALL the data we have from Boost users, across
whatever version was live, through the new withdrawal logic; COMPARE the insulin it would deliver to what
ACTUALLY happened; and POSTULATE the glucose consequence of the different IOB.

Method: per user, build a continuous CGM + DELIVERED-insulin stream across all variants (delivered =
finaldose for the V5/V6 era, v1_units for the V1 era; live-engine priority on dedup). Run the harness
`twinwithdraw` (real TwinShadow + real TwinWithdrawalShadow.decide) over the whole stream → per-cycle lo30
+ wouldWithholdU. Then project glucose from the IOB difference: BG_new(t) = BG_actual(t) + ISF ×
Σ_{s in (t-DIA, t]} wouldWithholdU(s) × acted(t-s)  (withheld insulin no longer lowers BG; bounded to the
insulin action window DIA=5h so it washes out — no unbounded drift). ISF = per-user winsorised DynISF.

Descriptive outputs (not a superiority test): span, cycles, withdrawal events, insulin withheld/day, and
the postulated glucose change — focused on ACTUAL low events (did removing insulin lift the nadir?) and the
cost (highs introduced when no low actually came). Run: python3 full_history_withdrawal.py [user]
"""
import sys, os, numpy as np, psycopg2, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kengine import run_engine

# oref exponential insulin ACTION (cumulative acted fraction), peak 75 / dia 300 — same as the loop
_PEAK, _DIA = 75.0, 300.0
_t = np.arange(0, _DIA + 5, 5.0)
_tau = _PEAK * (1 - _PEAK / _DIA) / (1 - 2 * _PEAK / _DIA)
_a = 2 * _tau / _DIA
_S = 1 / (1 - _a + (1 + _a) * np.exp(-_DIA / _tau))
_iob = np.clip(1 - _S * (1 - _a) * ((_t**2 / (_tau * _DIA * (1 - _a)) - _t / _tau - 1) * np.exp(-_t / _tau) + 1), 0, 1)
_ACTED = 1 - _iob
def acted(dtmin): return float(np.interp(dtmin, _t, _ACTED)) if 0 < dtmin < _DIA else (1.0 if dtmin >= _DIA else 0.0)

VARPRIO = {"boost-other": 0, "trio-shadow": 1, "v1": 2, "v2": 3, "v3": 4, "v1-silent": 5}


def load_stream(u):
    with psycopg2.connect("dbname=oref host=127.0.0.1 port=5432") as conn:
        df = pd.read_sql("""select ts_epoch, cgm_mgdl, boostv5_finaldose, v1_units, sug_rate, variable_sens, variant
            from boost_decisions where user_id=%s and cgm_mgdl is not null order by ts_epoch""", conn, params=(u,))
    df["prio"] = df.variant.map(VARPRIO).fillna(9)
    df["bucket"] = (df.ts_epoch // 300).astype(np.int64)
    df = df.sort_values(["bucket", "prio"]).drop_duplicates("bucket", keep="first").sort_values("ts_epoch")
    df["smb"] = df.boostv5_finaldose.fillna(df.v1_units).fillna(0.0)          # DELIVERED SMB (live engine)
    df["basal"] = df.sug_rate.fillna(0.0)
    return df.reset_index(drop=True)


def run_user(u):
    df = load_stream(u)
    if len(df) < 500:
        return None
    ep = df.ts_epoch.to_numpy(float); cgm = df.cgm_mgdl.to_numpy(float)
    smb = df.smb.to_numpy(float); rate = df.basal.to_numpy(float)
    isf = df.variable_sens.to_numpy(float)
    if np.nanmedian(isf) < 15: isf = isf * 18.0
    isf = float(np.clip(np.nanmedian(isf), 20, 250))                          # per-user winsorised DynISF
    dt = np.clip(np.diff(ep, append=ep[-1] + 300) / 60.0, 0, 6)
    deliv = smb + rate * dt / 60.0                                            # delivered this cycle (withholdable)
    ins_this = deliv.copy()
    basal_fwd = rate * 5.0 / 60.0
    cycles = [{"cgm": float(cgm[i]), "bg": float(cgm[i]), "insulinThisCycleU": float(ins_this[i]),
               "expectedBasalPerCycleU": float(basal_fwd[i]), "deliverableU": float(deliv[i])} for i in range(len(df))]
    res = run_engine("twinwithdraw", cycles, params={"lo30Threshold": float(os.environ.get("LO30_THR","70"))})
    wh = np.nan_to_num(np.array([r.get("wouldWithholdU", 0.0) for r in res], float))
    n = len(df); days = (ep[-1] - ep[0]) / 86400.0

    # EVENT-BASED (no continuous accumulation): dedup withdrawals into BOUTS (≥30 min apart)
    ev = np.where(wh > 1e-6)[0]
    bouts, last = [], -1e9
    for i in ev:
        if ep[i] - last > 1800: bouts.append(i)
        last = ep[i]
    def has_low(i, a, b, thr=70):                 # actual BG<thr in (t+a, t+b] minutes
        m = (ep > ep[i] + a * 60) & (ep <= ep[i] + b * 60)
        return m.any() and np.nanmin(cgm[m]) < thr
    # of the withdrawal BOUTS, how many are followed by a real low within 90 min (justified) vs not (cost)?
    justified = sum(1 for i in bouts if has_low(i, 0, 90))
    tp_rate = 100 * justified / max(1, len(bouts))
    # actual low ONSETS (cross <70 from >=70), and whether a withdrawal fired in the preceding 90 min (coverage)
    onsets = [i for i in range(1, n) if cgm[i] < 70 and cgm[i-1] >= 70]
    def wh_before(i):
        m = (ep >= ep[i] - 90 * 60) & (ep < ep[i]); return float(wh[m].sum())
    covered = sum(1 for i in onsets if wh_before(i) > 1e-6)
    # projected nadir lift at covered lows (bounded to the preceding withdrawals only)
    lifts = []
    for i in onsets:
        m = np.where((ep >= ep[i] - _DIA * 60) & (ep < ep[i]) & (wh > 1e-6))[0]
        if len(m):
            lifts.append(isf * float(np.sum(wh[m] * np.array([acted((ep[i]-ep[j])/60.0) for j in m]))))
    return dict(user=u, first=pd.to_datetime(ep[0], unit="s").strftime("%Y-%m-%d"),
                last=pd.to_datetime(ep[-1], unit="s").strftime("%Y-%m-%d"), days=round(days),
                cycles=n, isf=round(isf), withhold_bouts=len(bouts),
                bouts_per_day=round(len(bouts) / days, 1), withheld_U_day=round(float(wh.sum() / days), 2),
                pct_bouts_justified=round(tp_rate, 1),                       # ← selectivity: % followed by a real low
                actual_low_onsets=len(onsets), pct_lows_covered=round(100 * covered / max(1, len(onsets)), 1),
                median_lift_at_covered=round(float(np.median(lifts)) if lifts else 0.0, 0))


if __name__ == "__main__":
    users = [sys.argv[1]] if len(sys.argv) > 1 else ["tim", "B", "A", "F", "H", "E", "C", "D"]
    rows = []
    print(f"{'user':>4} {'span (days)':>26} {'cyc':>6} {'ISF':>4} | {'bouts/d':>7} {'U/d':>5} "
          f"{'%justified':>10} | {'lowOns':>6} {'%covered':>8} {'lift':>5}")
    for u in users:
        try:
            r = run_user(u)
        except Exception as e:
            print(f"{u:>4}  ERR {str(e)[:60]}"); continue
        if r is None:
            print(f"{u:>4}  (too little data)"); continue
        rows.append(r)
        print(f"{u:>4} {r['first']}..{r['last']} ({r['days']:>3}) {r['cycles']:>6} {r['isf']:>4} | "
              f"{r['bouts_per_day']:>7.1f} {r['withheld_U_day']:>5.2f} {r['pct_bouts_justified']:>9.1f}% | "
              f"{r['actual_low_onsets']:>6} {r['pct_lows_covered']:>7.1f}% {r['median_lift_at_covered']:>+5.0f}")
    if rows:
        import json
        json.dump(rows, open("full_history_withdrawal.json", "w"), indent=2, default=str)
        print(f"\n  COHORT: {len(rows)} users, {sum(r['days'] for r in rows)} user-days across all Boost versions.")
        print(f"  median bouts/day {np.median([r['bouts_per_day'] for r in rows]):.1f}, "
              f"median % of withdrawals FOLLOWED BY A REAL LOW {np.median([r['pct_bouts_justified'] for r in rows]):.0f}% "
              f"(selectivity), median % of actual lows COVERED {np.median([r['pct_lows_covered'] for r in rows]):.0f}%")
        print("  (descriptive; event-based so no accumulation artifact; projected lift first-order DynISF-anchored)")
