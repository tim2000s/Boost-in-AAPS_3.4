#!/usr/bin/env python3
"""Backtest of the per-knob auto-config migration (b2c0705e5e) for users C and D.

C and D run v1-format Boost-ML-Beta builds (V1-acting + V5-shadow, NO auto-config on device).
Old-era factory defaults (their operative shadow knobs since the mid-June upgrade):
  committedCap 0.25, confirmedCap 1.0, cumulative60 6.0, Aggression 1.0, HypoCaution 1.0, FCC ON.
New-build factory: committedCap 0.5, confirmedCap 2.5, cumulative60 10.0, Aggr 1.0, HC 1.0, FCC ON.
Migration is PROSPECTIVE: applies when they upgrade to the V6 build.
"""
import json, csv, math, statistics
from datetime import datetime, timedelta, timezone

SP = "/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad"

def pctl(vals, p):  # linear-interpolated percentile, mirrors BoostV5AutoConfig.percentile
    v = sorted(x for x in vals if x and x > 0 and math.isfinite(x))
    if not v: return 0.0
    if len(v) == 1: return v[0]
    rank = p/100.0*(len(v)-1); lo = int(rank); hi = min(lo+1, len(v)-1)
    return v[lo] + (v[hi]-v[lo])*(rank-lo)

def r1(x): return round(x*10)/10
def r2(x): return round(x*100)/100

def derive(tdd, manual, smb, tbr70, sev54):
    hypo_prone = sev54 > 1.5 or tbr70 > 6.0
    hc = r1(min(2.0, max(1.0, 1.0 + max(0.0, tbr70-4.0)/4.0 + max(0.0, sev54-1.0)*0.5)))
    aggr = 0.85 if hypo_prone else (0.92 if tbr70 > 4.0 else 1.0)
    cf = r2(min(7.5, max(1.5, max(pctl(manual,90), pctl(smb,95)))))
    cc = r2(min(2.5, max(0.25, max(pctl(smb,75), tdd/40.0))))
    cum = r1(min(max(5.0, cf), max(1.0, cf + 2.0*cc)))
    return dict(hypoProne=hypo_prone, hypoCaution=hc, aggression=aggr, confirmedCap=cf,
                committedCap=cc, cumulative=cum, fastCarbConfirm=not hypo_prone,
                p75smb=r2(pctl(smb,75)), p95smb=r2(pctl(smb,95)), p90man=r2(pctl(manual,90)),
                tdd40=r2(tdd/40.0), nSMB=len([x for x in smb if x>0]), nMan=len([x for x in manual if x>0]))

def parse_ts(s):
    s = s.replace('Z','+00:00')
    return datetime.fromisoformat(s)

# ---------- load ----------
cycles = {'C':[], 'D':[]}
with open(f"{SP}/mig_CD_cycles.csv") as f:
    for row in csv.DictReader(f):
        row['ts'] = parse_ts(row['ts_utc'])
        for k in ('boostv5_finaldose','boostv5_budget','boostv5_actionmult','v1_units','cgm_mgdl',
                  'ml_hypo_risk','sug_insulinreq','sug_iob','tdd','tdd_1d','tdd_7d'):
            row[k] = float(row[k]) if row[k] else None
        cycles[row['user_id']].append(row)

cgm = {'C':[], 'D':[]}
with open(f"{SP}/mig_CD_cgm.csv") as f:
    for row in csv.DictReader(f):
        cgm[row['user_id']].append((parse_ts(row['ts_utc']), float(row['cgm_mgdl'])))
for u in cgm: cgm[u].sort()

treats = {}
for u in "CD":
    treats[u] = json.load(open(f"{SP}/mig_{u}_treatments_28d.json"))

ANCHOR = {u: max(r['ts'] for r in cycles[u]) for u in "CD"}
PIN_START = {'C': datetime(2026,6,19,tzinfo=timezone.utc), 'D': datetime(2026,6,17,tzinfo=timezone.utc)}
EPS = 1e-6

import bisect
def bg_window(u, t0, minutes=120):
    """(minBG, maxBG) in (t0, t0+minutes]; None if <4 readings."""
    arr = cgm[u]; keys = cgm_keys[u]
    i = bisect.bisect_right(keys, t0); j = bisect.bisect_right(keys, t0+timedelta(minutes=minutes))
    seg = [v for _, v in arr[i:j]]
    if len(seg) < 4: return None
    return min(seg), max(seg)
cgm_keys = {u: [t for t,_ in cgm[u]] for u in cgm}

def hypo_scale(r, knob):
    if r is None or r <= 0.30: return 1.0
    red = min(1.0, (r-0.30)/0.70*max(1.0,knob)); floor = 0.5/max(1.0,knob)
    return max(floor, 1.0-red)

OLD = dict(committedCap=0.25, confirmedCap=1.0, cumulative=6.0, aggression=1.0, hypoCaution=1.0, fcc=True)
NEWFACT = dict(committedCap=0.5, confirmedCap=2.5, cumulative=10.0, aggression=1.0, hypoCaution=1.0, fcc=True)

for u in "CD":
    print("="*100); print(f"USER {u}   anchor={ANCHOR[u]}   pin-era starts {PIN_START[u].date()}")
    # ---------- 1. formula inputs, 14d and 28d windows ending at anchor ----------
    for days in (14, 28):
        w0 = ANCHOR[u] - timedelta(days=days)
        smb, man = [], []
        for t in treats[u]:
            ins = t.get('insulin')
            if not ins: continue
            ct = parse_ts(t['created_at'])
            if not (w0 < ct <= ANCHOR[u]): continue
            (smb if t.get('type')=='SMB' else man if t.get('type')=='NORMAL' else []).append(float(ins))
        # TDD median: last tdd_1d per calendar day from decisions
        byday = {}
        for r in cycles[u]:
            if w0 < r['ts'] <= ANCHOR[u] and r['tdd_1d']:
                byday[r['ts'].date()] = r['tdd_1d']
        tdd_med = statistics.median(byday.values()) if byday else float('nan')
        tdd7_last = next((r['tdd_7d'] for r in reversed(cycles[u]) if r['tdd_7d']), None)
        # NS-treatment TDD cross-check (boluses + temp-basal integration)
        tb = sorted([(parse_ts(t['created_at']), float(t.get('rate') or 0), float(t.get('duration') or 0))
                     for t in treats[u] if t.get('eventType')=='Temp Basal' and w0 < parse_ts(t['created_at']) <= ANCHOR[u]])
        basal_u = 0.0
        for i,(ts, rate, dur) in enumerate(tb):
            end = ts + timedelta(minutes=dur)
            if i+1 < len(tb): end = min(end, tb[i+1][0])
            basal_u += rate * max(0.0,(end-ts).total_seconds())/3600.0
        bolus_u = sum(float(t.get('insulin') or 0) for t in treats[u]
                      if t.get('insulin') and w0 < parse_ts(t['created_at']) <= ANCHOR[u])
        ns_tdd = (basal_u + bolus_u)/days
        # TBR from boost_cgm
        bgs = [v for t,v in cgm[u] if w0 < t <= ANCHOR[u] and v >= 1.0]
        tbr70 = 100.0*sum(1 for v in bgs if v<70)/len(bgs)
        sev54 = 100.0*sum(1 for v in bgs if v<54)/len(bgs)
        d = derive(tdd_med, man, smb, tbr70, sev54)
        floor_new = min(d['committedCap'], 0.8*d['confirmedCap'])
        print(f"\n--- window {days}d ({w0.date()} → {ANCHOR[u].date()}) ---")
        print(f" inputs: TDDmed(tdd_1d/day)={tdd_med:.1f}U  [tdd_7d last={tdd7_last:.1f}; NS-treatments TDD≈{ns_tdd:.1f} (basal {basal_u/days:.1f} + bolus {bolus_u/days:.1f})]")
        print(f"         SMB n={d['nSMB']} p75={d['p75smb']} p95={d['p95smb']}   manual n={d['nMan']} p90={d['p90man']}   TDD/40={d['tdd40']}")
        print(f"         TBR<70={tbr70:.2f}%  TBR<54={sev54:.2f}%  (hypo-prone triggers: <54>1.5 → {sev54>1.5}; <70>6.0 → {tbr70>6.0}; <70>4.0 → {tbr70>4.0})")
        print(f" derived: committedCap={d['committedCap']}  confirmedCap={d['confirmedCap']}  cumulative60={d['cumulative']}  "
              f"Aggr={d['aggression']}  HypoCaution={d['hypoCaution']}  FCC={'ON' if d['fastCarbConfirm'] else 'OFF'}  confirmFloor={floor_new:.2f}")
        if days == 14: D14 = d
    d = D14
    floor_old = min(OLD['committedCap'], 0.8*OLD['confirmedCap'])
    floor_new = min(d['committedCap'], 0.8*d['confirmedCap'])

    # ---------- replay on pin-era shadow cycles ----------
    era = [r for r in cycles[u] if r['ts'] >= PIN_START[u]]
    pos = [r for r in era if (r['boostv5_finaldose'] or 0) > 0]
    tot_ins = sum(r['boostv5_finaldose'] for r in pos)
    print(f"\n--- pin-era replay ({PIN_START[u].date()} → {ANCHOR[u].date()}): {len(era)} deduped cycles, "
          f"{len(pos)} with V5 dose>0, shadow total {tot_ins:.1f}U ---")

    # (a) committedCap pin release  — LOOSening (0.25 → derived)
    pinned = [r for r in era if r['boostv5_state']=='COMMITTED' and abs((r['boostv5_finaldose'] or 0)-0.25) < EPS]
    v1_gt = [r for r in pinned if (r['v1_units'] or 0) > 0.25]
    # demand proxy: pre-pin-era COMMITTED dose distribution
    pre = [r['boostv5_finaldose'] for r in cycles[u]
           if r['ts'] < PIN_START[u] and r['boostv5_state']=='COMMITTED' and (r['boostv5_finaldose'] or 0) > 0.25 - EPS]
    if pre:
        uplift = statistics.mean(min(x, d['committedCap']) - min(x, 0.25) for x in pre)
    else:
        uplift = float('nan')
    add_committed = uplift*len(pinned)
    print(f" (a) committedCap 0.25→{d['committedCap']}: pinned COMMITTED cycles={len(pinned)} "
          f"({len(pinned)/max(1,len(era))*100:.1f}% of cycles); v1_units>0.25 on {len(v1_gt)} of them")
    print(f"     pre-pin COMMITTED≥0.25 doses n={len(pre)}: est. uplift E[min(x,new)-min(x,.25)]={uplift:.3f}U/cycle "
          f"→ est. ADDED ≈ {add_committed:.1f}U over era ({add_committed/max(tot_ins,1e-9)*100:.1f}% of shadow total)")
    # harm pricing of ADDED insulin (pin-release cycles)
    outc = [bg_window(u, r['ts']) for r in pinned]
    outc = [o for o in outc if o]
    nlow = sum(1 for mn,mx in outc if mn < 70); nhigh = sum(1 for mn,mx in outc if mx > 180 and mn >= 70)
    print(f"     outcome after pinned cycles (2h): minBG<70 {nlow}/{len(outc)} ({nlow/max(1,len(outc))*100:.1f}%)  "
          f"maxBG>180&no-low {nhigh}/{len(outc)} ({nhigh/max(1,len(outc))*100:.1f}%)")

    # (b) confirmedCap 1.0 → derived — LOOSening; + confirm floor shift
    conf = [r for r in era if r['boostv5_state']=='CONFIRMED' and (r['boostv5_finaldose'] or 0) > 0]
    conf_pin = [r for r in conf if abs(r['boostv5_finaldose']-1.0) < EPS]
    conf_sizes = [r['boostv5_finaldose'] for r in conf]
    below_floor = [r for r in conf if r['boostv5_finaldose'] < floor_new - EPS]
    outc = [o for o in ( bg_window(u, r['ts']) for r in conf_pin) if o]
    nlow = sum(1 for mn,mx in outc if mn < 70); nhigh = sum(1 for mn,mx in outc if mx > 180 and mn >= 70)
    print(f" (b) confirmedCap 1.0→{d['confirmedCap']}: CONFIRMED shots={len(conf)} "
          f"(sizes p50={pctl(conf_sizes,50):.2f} p90={pctl(conf_sizes,90):.2f} max={max(conf_sizes or [0]):.2f}); "
          f"pinned at 1.0: {len(conf_pin)} ({len(conf_pin)/max(1,len(conf))*100:.0f}%)")
    print(f"     outcome after 1.0-pinned confirms (2h): minBG<70 {nlow}/{len(outc)}  maxBG>180&no-low {nhigh}/{len(outc)}")
    print(f"     confirm floor: old min(0.25,0.8×1.0)={floor_old:.2f} → new min({d['committedCap']},0.8×{d['confirmedCap']})={floor_new:.2f}; "
          f"observed confirm shots below new floor: {len(below_floor)}/{len(conf)} "
          f"(these would be HELD by the dose-adequacy gate)")

    # (c) cumulative 60-min cap: operative old 6.0 (their build) / factory 10.0 (new build) → derived
    def cum_sim(rows, cap):
        removed = 0.0; nhit = 0; hist = []  # (ts, delivered)
        for r in rows:
            dose = r['boostv5_finaldose'] or 0
            if dose <= 0: hist.append((r['ts'],0)); continue
            t0 = r['ts'] - timedelta(minutes=60)
            recent = sum(dv for tt,dv in hist if tt > t0)
            allowed = max(0.0, cap - recent)
            deliv = min(dose, allowed)
            if deliv < dose - EPS: nhit += 1; removed += dose - deliv
            hist.append((r['ts'], deliv))
        return removed, nhit
    rem_new, hit_new = cum_sim(era, d['cumulative'])
    rem_old, hit_old = cum_sim(era, OLD['cumulative'])
    print(f" (c) cumulative60 {OLD['cumulative']}(operative)/{NEWFACT['cumulative']}(new factory)→{d['cumulative']}: "
          f"cycles trimmed {hit_old}→{hit_new}, insulin removed {rem_old:.1f}U→{rem_new:.1f}U "
          f"({rem_new/max(tot_ins,1e-9)*100:.2f}% of shadow total) [on 0.25/1.0-capped stream — lower bound]")

    # (d) Aggression (CONFIRMED-only multiplier)
    if d['aggression'] < 1.0:
        rem_ag = sum(r['boostv5_finaldose']*(1-d['aggression']) for r in conf)
        outc = [o for o in (bg_window(u, r['ts']) for r in conf) if o]
        nlow = sum(1 for mn,mx in outc if mn<70); nhigh = sum(1 for mn,mx in outc if mx>180 and mn>=70)
        print(f" (d) Aggression 1.0→{d['aggression']}: scales CONFIRMED only → REMOVES ≈{rem_ag:.1f}U "
              f"({rem_ag/max(tot_ins,1e-9)*100:.1f}% of shadow total; linear approx on capped-at-1.0 shots — lower bound)")
        print(f"     confirm-shot outcomes (2h): minBG<70 {nlow}/{len(outc)} ({nlow/max(1,len(outc))*100:.1f}%, protective) "
              f"vs maxBG>180&no-low {nhigh}/{len(outc)} ({nhigh/max(1,len(outc))*100:.1f}%, costly)")
    else:
        print(f" (d) Aggression stays 1.0 — no change")

    # (e) HypoCaution damper (only bites when ml_hypo_risk > 0.30)
    if d['hypoCaution'] > 1.0:
        risk_rows = [r for r in pos if (r['ml_hypo_risk'] or 0) > 0.30]
        rem_hc, prot, cost, npx = 0.0, 0, 0, 0
        for r in risk_rows:
            s_old = hypo_scale(r['ml_hypo_risk'], 1.0); s_new = hypo_scale(r['ml_hypo_risk'], d['hypoCaution'])
            cut = r['boostv5_finaldose']*(1 - s_new/s_old)
            if cut <= EPS: continue
            rem_hc += cut; npx += 1
            o = bg_window(u, r['ts'])
            if o:
                mn,mx = o
                if mn < 70: prot += 1
                elif mx > 180: cost += 1
        nrisk_all = sum(1 for r in era if (r['ml_hypo_risk'] or 0) > 0.30)
        print(f" (e) HypoCaution 1.0→{d['hypoCaution']}: risk>0.30 on {nrisk_all} cycles; deeper cut on {npx} dosing cycles "
              f"→ REMOVES ≈{rem_hc:.1f}U ({rem_hc/max(tot_ins,1e-9)*100:.2f}%); of those, {prot} preceded a <70 (protective), {cost} preceded >180 w/o low (costly)")
    else:
        print(f" (e) HypoCaution stays 1.0 — no change")

    # (f) FastCarbConfirm
    fcp = {}
    for r in era: fcp[r['fast_carb_protection'] or 'NULL'] = fcp.get(r['fast_carb_protection'] or 'NULL',0)+1
    print(f" (f) FastCarbConfirm {'ON→OFF (hypo-prone)' if not d['fastCarbConfirm'] else 'stays ON'}; "
          f"fast_carb_protection values in era: {fcp}")

    # (g) formula-design check: cumulative vs confirmedCap
    print(f" (g) design check: derived cumulative {d['cumulative']} vs confirmedCap {d['confirmedCap']} "
          f"(ratio {d['cumulative']/d['confirmedCap']:.2f}); one max confirm leaves {d['cumulative']-d['confirmedCap']:.2f}U/hr "
          f"= {(d['cumulative']-d['confirmedCap'])/max(d['committedCap'],1e-9):.1f} committed holds; "
          f"observed confirm p90 {pctl(conf_sizes,90):.2f}U leaves {d['cumulative']-pctl(conf_sizes,90):.2f}U/hr")
print("="*100)
