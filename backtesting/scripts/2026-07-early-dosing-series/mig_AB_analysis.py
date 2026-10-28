#!/usr/bin/env python3
"""
Backtest of the auto-config per-knob migration (user-H migration fix, b2c0705e5e) for users A and B.

Mirrors BoostV5AutoConfig.kt (verified in Boost-AAPS-core @ b2c0705e5e):
  committedCap = round2(clamp(max(p75(SMB>0), TDDmed/40), 0.25, 2.5))
  confirmedCap = round2(clamp(max(p90(NORMAL boluses), p95(SMB)), 1.5, 7.5))
  cumulative   = round1(clamp(conf + 2*ccap, 1.0, max(5.0, conf)))
  HypoCaution  = round1(clamp(1 + max(0,TBR70-4)/4 + max(0,TBR54-1)*0.5, 1, 2))
  Aggression   = 0.85 if hypoProne(TBR54>1.5 or TBR70>6) else 0.92 if TBR70>4 else 1.0
  FastCarbConfirm = not hypoProne
  confirm-gate floor = min(committedCap, 0.8*confirmedCap)   [MealHypothesis/DetermineBasal]
  velocityScaledDoseFactor floor = 0.40 (rise<=25) .. 1.0 (rise>=50)
  mealActionMultiplier: COMMITTED 1.0, CONFIRMED 1.8*aggr
Factory defaults (DoubleKey.kt): ccap 0.5, conf 2.5, cumulative 10.0, aggr 1.0, hypoCaution 1.0,
maxIob 1.0, bolusCap 2.5; FastCarbConfirm true.
"""
import json, math, os, bisect
from datetime import datetime, timedelta, timezone
import psycopg2

S = os.path.dirname(os.path.abspath(__file__))
CON = psycopg2.connect(dbname="oref")
NOW = datetime.now(timezone.utc)

# ---------- Kotlin-mirror helpers ----------
def percentile(vals, p):
    v = sorted(x for x in vals if x is not None and math.isfinite(x) and x > 0.0)
    if not v: return 0.0
    if len(v) == 1: return v[0]
    rank = (p / 100.0) * (len(v) - 1)
    lo = int(rank); hi = min(lo + 1, len(v) - 1); frac = rank - lo
    return v[lo] + (v[hi] - v[lo]) * frac

r1 = lambda x: round(x * 10.0) / 10.0
r2 = lambda x: round(x * 100.0) / 100.0
clamp = lambda x, a, b: min(max(x, a), b)

def suggestion(tdd_med, manual, smb, tbr70, tbr54):
    hypo_prone = tbr54 > 1.5 or tbr70 > 6.0
    hc = r1(clamp(1.0 + max(0.0, tbr70 - 4.0) / 4.0 + max(0.0, tbr54 - 1.0) * 0.5, 1.0, 2.0))
    aggr = 0.85 if hypo_prone else (0.92 if tbr70 > 4.0 else 1.0)
    conf = r2(clamp(max(percentile(manual, 90), percentile(smb, 95)), 1.5, 7.5))
    ccap = r2(clamp(max(percentile(smb, 75), tdd_med / 40.0), 0.25, 2.5))
    cum = r1(clamp(conf + 2.0 * ccap, 1.0, max(5.0, conf)))
    return dict(aggr=aggr, hypoCaution=hc, conf=conf, ccap=ccap, cum=cum,
                fastCarb=not hypo_prone, hypo_prone=hypo_prone,
                floor=min(ccap, 0.8 * conf),
                inputs=dict(tdd_med=round(tdd_med,1), p75smb=round(percentile(smb,75),3),
                            p95smb=round(percentile(smb,95),3), p90man=round(percentile(manual,90),3),
                            n_smb=len(smb), n_manual=len(manual),
                            tbr70=round(tbr70,2), tbr54=round(tbr54,2)))

def q(sql, args=()):
    cur = CON.cursor(); cur.execute(sql, args); rows = cur.fetchall(); cur.close(); return rows

OUT = {}
for tag in ("A", "B"):
    R = {}
    tr = json.load(open(f"{S}/mig_{tag}_treatments28d.json"))
    for t in tr:
        t["_dt"] = datetime.strptime(t["created_at"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)

    for wd in (14, 28):
        cut = NOW - timedelta(days=wd)
        smb    = [t["insulin"] for t in tr if t["_dt"] >= cut and t.get("insulin") and t.get("type") == "SMB"]
        manual = [t["insulin"] for t in tr if t["_dt"] >= cut and t.get("insulin") and t.get("type") == "NORMAL"]
        # TDD median: median of loop-reported tdd_24h over deduped decision rows in window
        tdd = q("""SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY tdd_24h)
                   FROM (SELECT DISTINCT ON (floor(extract(epoch FROM ts_utc)/300))
                                tdd_24h FROM boost_decisions
                         WHERE user_id=%s AND ts_utc >= %s AND tdd_24h IS NOT NULL
                         ORDER BY floor(extract(epoch FROM ts_utc)/300), ts_utc DESC) d""",
                (tag, cut))[0][0]
        cg = q("""SELECT count(*), count(*) FILTER (WHERE cgm_mgdl<70),
                         count(*) FILTER (WHERE cgm_mgdl<54), avg(cgm_mgdl),
                         count(DISTINCT date_trunc('day', ts_utc))
                  FROM boost_cgm WHERE user_id=%s AND ts_utc >= %s""", (tag, cut))[0]
        n, n70, n54, meanbg, days = cg
        tbr70 = 100.0 * n70 / n; tbr54 = 100.0 * n54 / n
        sug = suggestion(tdd, manual, smb, tbr70, tbr54)
        sug["inputs"]["bg_n"] = n; sug["inputs"]["bg_days"] = days
        sug["inputs"]["mean_bg"] = round(meanbg, 1)
        sug["eligible"] = days >= 7 and n >= 1500
        R[f"formula_{wd}d"] = sug

    # ---------- era-aware operative values ----------
    R["prior_era_ceilings"] = q("""
        SELECT to_char(date_trunc('week', ts_utc),'MM-DD') wk,
               round(max(boostv5_finaldose) FILTER (WHERE boostv5_state='COMMITTED')::numeric,3),
               count(*) FILTER (WHERE boostv5_state='COMMITTED'
                                AND boostv5_finaldose >= 0.249 AND boostv5_finaldose <= 0.251),
               count(*) FILTER (WHERE boostv5_state='COMMITTED'
                                AND boostv5_finaldose >= 0.499 AND boostv5_finaldose <= 0.501),
               count(*) FILTER (WHERE boostv5_state='COMMITTED'),
               round(max(boostv5_finaldose) FILTER (WHERE boostv5_state='CONFIRMED')::numeric,3)
        FROM boost_decisions
        WHERE user_id=%s AND variant='v1' AND ts_utc >= %s AND boostv5_finaldose IS NOT NULL
        GROUP BY 1 ORDER BY 1""", (tag, NOW - timedelta(days=35)))

    # ---------- deduped capped-era rows (boost-other) ----------
    rows = q("""SELECT DISTINCT ON (floor(extract(epoch FROM ts_utc)/300))
                       ts_utc, boostv5_state, boostv5_finaldose, boostv5_budget,
                       boostv5_committedcap, boostv5_confirmedcap, cgm_mgdl,
                       COALESCE(v1_units,0)
                FROM boost_decisions
                WHERE user_id=%s AND variant='boost-other' AND boostv5_finaldose IS NOT NULL
                ORDER BY floor(extract(epoch FROM ts_utc)/300), ts_utc DESC""", (tag,))
    rows.sort(key=lambda r: r[0])
    raw_n = q("SELECT count(*) FROM boost_decisions WHERE user_id=%s AND variant='boost-other'", (tag,))[0][0]
    era_days = (rows[-1][0] - rows[0][0]).total_seconds() / 86400.0
    R["era"] = dict(raw_rows=raw_n, dedup_rows=len(rows), days=round(era_days, 2),
                    start=str(rows[0][0]), end=str(rows[-1][0]))

    # CGM lookup for outcome pricing
    cgm = q("SELECT ts_utc, cgm_mgdl FROM boost_cgm WHERE user_id=%s AND ts_utc >= %s ORDER BY ts_utc",
            (tag, NOW - timedelta(days=10)))
    cts = [c[0] for c in cgm]; cvs = [c[1] for c in cgm]
    def min_bg_next(ts, hours=3):
        i = bisect.bisect_right(cts, ts); j = bisect.bisect_right(cts, ts + timedelta(hours=hours))
        seg = cvs[i:j]
        return min(seg) if seg else None

    new14 = R["formula_14d"]
    ccap_new, conf_new, cum_new = new14["ccap"], new14["conf"], new14["cum"]
    floor_new = new14["floor"]

    # ---------- (4a) committedCap-pinned replay ----------
    pinned = []
    for ts, st, dose, bud, cc, cf, bg, v1u in rows:
        cc_eff = cc if cc is not None else 0.5
        if st == "COMMITTED" and dose is not None and dose >= cc_eff - 0.005 and dose > 0:
            pinned.append((ts, dose, bud, cc_eff, bg))
    def replay_added(vf_mode):
        add = 0.0; per = []
        for ts, dose, bud, cc_eff, bg in pinned:
            if bud is None or bud <= 0: continue
            vf = 1.0 if vf_mode == "hi" else max(0.4, min(1.0, dose / bud))  # lo: least vf consistent w/ pinning
            new = min(bud * 1.0 * vf, ccap_new)   # COMMITTED mult = 1.0
            d = max(0.0, new - dose)
            add += d; per.append((ts, d, bg))
        return add, per
    add_lo, per_lo = replay_added("lo")
    add_hi, per_hi = replay_added("hi")
    R["replay_committed"] = dict(
        pinned_cycles=len(pinned), pinned_perday=round(len(pinned)/era_days,1),
        added_U_lo=round(add_lo,2), added_U_hi=round(add_hi,2),
        added_Uday_lo=round(add_lo/era_days,3), added_Uday_hi=round(add_hi/era_days,3))

    # harm pricing of ADDED insulin (vf=1.0 upper bound)
    add_pre_low = sum(d for ts, d, bg in per_hi if d > 0 and (m := min_bg_next(ts)) is not None and m < 70)
    R["replay_committed"]["added_prelow_pct_hi"] = round(100*add_pre_low/add_hi, 1) if add_hi > 0 else None
    tot_dose = sum(r[2] for r in rows if r[2]); tot_prelow = sum(
        r[2] for r in rows if r[2] and (m := min_bg_next(r[0])) is not None and m < 70)
    R["base_prelow_pct"] = round(100*tot_prelow/tot_dose, 1) if tot_dose else None

    # ---------- (4b) confirm-floor shift (delivered-dose lower-bound) ----------
    confirms = []
    prev_st, prev_ts = None, None
    for ts, st, dose, bud, cc, cf, bg, v1u in rows:
        if st == "CONFIRMED" and (prev_st != "CONFIRMED" or (ts - prev_ts) > timedelta(minutes=12)):
            confirms.append((ts, dose or 0.0, cc if cc is not None else 0.5,
                             cf if cf is not None else 2.5, bg))
        prev_st, prev_ts = st, ts
    flips = [(ts, d) for ts, d, cc, cf, bg in confirms
             if d > 0 and d <= floor_new and d < (cf - 0.01)]   # not conf-cap-clipped => delivered ~= shot
    kept  = [(ts, d) for ts, d, cc, cf, bg in confirms if d > floor_new or d >= (cf - 0.01)]
    floor_olds = sorted({round(min(cc, 0.8*cf), 3) for _, _, cc, cf, _ in confirms})
    R["confirm_floor"] = dict(
        floor_old_values=floor_olds, floor_new=round(floor_new, 3),
        confirm_entries=len(confirms), at_risk_flips=len(flips),
        flip_U=round(sum(d for _, d in flips), 2),
        flip_doses=[round(d, 2) for _, d in flips][:20],
        confirm_dose_p50=round(percentile([d for _, d, *_ in confirms], 50), 2) if confirms else None,
        confirm_dose_p90=round(percentile([d for _, d, *_ in confirms], 90), 2) if confirms else None)

    # ---------- (4c) cumulative 10 -> cum_new sequential replay ----------
    hist = []  # (ts, delivered_new)
    removed = []; suppressed_states = {}
    old_binding = 0
    for ts, st, dose, bud, cc, cf, bg, v1u in rows:
        while hist and (ts - hist[0][0]) > timedelta(minutes=60):
            hist.pop(0)
        trail = sum(h[1] for h in hist)
        # what actually happened under old cap 10 (observed doses; verify old cap never bound)
        trail_obs = trail  # approximation only used for counting; observed history is the real trail
        if dose and dose > 0:
            allowed = max(0.0, cum_new - trail)
            dn = min(dose, allowed)
            if dose - dn > 1e-9:
                removed.append((ts, st, dose - dn, dose, bg))
                suppressed_states[st] = suppressed_states.get(st, 0) + 1
            hist.append((ts, dn))
        else:
            hist.append((ts, 0.0))
    # old-cap-10 check on OBSERVED doses
    hist2 = []
    for ts, st, dose, *_ in rows:
        while hist2 and (ts - hist2[0][0]) > timedelta(minutes=60):
            hist2.pop(0)
        if sum(h[1] for h in hist2) + (dose or 0) > 10.0: old_binding += 1
        hist2.append((ts, dose or 0.0))
    rem_U = sum(x[2] for x in removed)
    rem_prot = sum(x[2] for x in removed if (m := min_bg_next(x[0])) is not None and m < 70)
    rem_cost = sum(x[2] for x in removed if (m := min_bg_next(x[0])) is not None and m >= 100)
    R["cumulative_tighten"] = dict(
        cum_new=cum_new, old_cap_ever_binding_cycles=old_binding,
        suppressed_cycles=len(removed), removed_U=round(rem_U, 2),
        removed_Uday=round(rem_U/era_days, 3),
        states=suppressed_states,
        removed_protective_pct=round(100*rem_prot/rem_U, 1) if rem_U else None,
        removed_costly_pct=round(100*rem_cost/rem_U, 1) if rem_U else None,
        mean_bg_at_suppression=round(sum(x[4] for x in removed if x[4])/max(1,sum(1 for x in removed if x[4])),0) if removed else None)

    # ---------- (6) formula-design check: one max confirm exhausts the hour? ----------
    exhausted = 0; followups = []
    for ts, d, cc, cf, bg in confirms:
        fu = sum(r[2] for r in rows if r[2] and ts < r[0] <= ts + timedelta(minutes=60))
        followups.append(fu)
        if d + fu > cum_new: exhausted += 1
    R["design_check"] = dict(
        cum_vs_conf=round(cum_new - conf_new, 2),
        confirms_n=len(confirms),
        confirm_plus_60min_exceeds_newcum=exhausted,
        followup_60min_p50=round(percentile(followups, 50), 2) if followups else None,
        headroom_after_max_confirm=round(cum_new - conf_new, 2))

    OUT[tag] = R

print(json.dumps(OUT, indent=1, default=str))
json.dump(OUT, open(f"{S}/mig_AB_results.json", "w"), indent=1, default=str)
