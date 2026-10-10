#!/usr/bin/env python3
"""Backtest of the auto-config per-knob migration (user-H migration fix, b2c0705e5e) for users tim + E.

Read-only. Sources:
  - NS treatments/entries (14d/28d windows anchored at pull time 2026-07-06)
  - TimescaleDB oref exports (mig_<u>_decisions.csv deduped last-per-5min, mig_<u>_cgm.csv, mig_<u>_tdd.csv)
Formulas replicated 1:1 from Boost-AAPS-core BoostV5AutoConfig.kt (verified this session):
  committedCap = clamp(max(p75 SMB>0, TDDmed/40), 0.25, 2.5)          [round2]
  confirmedCap = clamp(max(p90 NORMAL, p95 SMB), 1.5, 7.5)            [round2]
  cumulative   = clamp(conf + 2*comm, 1.0, max(5.0, conf))            [round1]
  hypoCaution  = clamp(1 + max(0,TBR70-4)/4 + max(0,TBR54-1)*0.5, 1, 2) [round1]
  aggression   = 0.85 if (TBR54>1.5 or TBR70>6) else 0.92 if TBR70>4 else 1.0
  fastCarbConfirm = not hypoProne
Percentile = Kotlin linear-interp over values >0.
Engine constants (DetermineBasalBoostV5.kt / MealActionMultiplier.kt):
  confirm floor = min(committedCap, 0.8*confirmedCap); gate passes iff prospective > floor
  prospective confirm shot = budget * 1.8 * aggroKnob * vf, vf in [0.4, 1.0]
  committed dose = min(budget * 1.0 * vf, committedCap)
"""
import csv, json, math, sys, datetime as dt
from bisect import bisect_left, bisect_right
from collections import deque

SCRATCH = "/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad"
NOW = dt.datetime(2026, 7, 6, 11, 0, tzinfo=dt.timezone.utc)  # NS pull time
ERA_START = dt.datetime(2026, 6, 17, tzinfo=dt.timezone.utc)   # caps operative

# per-user current knob config (from cap telemetry + known user facts)
CFG = {
    "tim": dict(
        committed_cur=0.5, committed_at_factory=True,          # telemetry 0.5 == factory
        confirmed_cur=3.0, confirmed_at_factory=False,         # telemetry 3.0
        cumulative_cur=2.5, cumulative_at_factory=False,       # user-set (known fact)
        aggro_cur=1.3, aggro_at_factory=False,                 # user-set (known fact)
        fastcarb_at_factory=True,
    ),
    "E": dict(
        committed_cur=0.5, committed_at_factory=True,          # telemetry 0.5 == factory
        confirmed_cur=2.0, confirmed_at_factory=False,         # user set 2.0 on 07-03 (was factory 2.5)
        confirmed_era=2.5,                                     # operative during most of replay era
        cumulative_cur=10.0, cumulative_at_factory=True,       # no evidence of change (assumed)
        aggro_cur=1.0, aggro_at_factory=True,                  # telemetry column null; assumed factory
        fastcarb_at_factory=True,
    ),
}
FACTORY = dict(committed=0.5, confirmed=2.5, cumulative=10.0, aggro=1.0, hypocaution=1.0, fastcarb=True)

def r1(x): return round(x * 10) / 10.0
def r2(x): return round(x * 100) / 100.0

def kpercentile(vals, p):
    v = sorted(x for x in vals if x is not None and math.isfinite(x) and x > 0)
    if not v: return 0.0
    if len(v) == 1: return v[0]
    rank = p / 100.0 * (len(v) - 1)
    lo = int(rank); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (rank - lo)

def median(v):
    v = sorted(v); n = len(v)
    if n == 0: return 0.0
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

def parse_ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))

def load_ns(user):
    tr = json.load(open(f"{SCRATCH}/mig_{user}_treatments_28d.json"))
    ent = json.load(open(f"{SCRATCH}/mig_{user}_entries_28d.json"))
    boluses = []
    for t in tr:
        if t.get("insulin"):
            boluses.append((parse_ts(t["created_at"]), float(t["insulin"]), t.get("type")))
    sgv = [(e["date"] / 1000.0, float(e["sgv"])) for e in ent if e.get("sgv")]
    sgv.sort()
    return boluses, sgv

def window_stats(boluses, sgv, days):
    start = NOW - dt.timedelta(days=days)
    smb = [u for ts, u, ty in boluses if ty == "SMB" and ts >= start]
    man = [u for ts, u, ty in boluses if ty == "NORMAL" and ts >= start]
    s0 = start.timestamp()
    bg = [v for t, v in sgv if t >= s0]
    n = len(bg)
    tbr70 = 100.0 * sum(1 for v in bg if 1.0 <= v <= 69.9) / n if n else 0.0
    tbr54 = 100.0 * sum(1 for v in bg if 1.0 <= v <= 53.9) / n if n else 0.0
    meanbg = sum(bg) / n if n else 0.0
    return smb, man, tbr70, tbr54, meanbg, n

def derive(smb, man, tbr70, tbr54, tdd_med):
    hypo_prone = tbr54 > 1.5 or tbr70 > 6.0
    hc = r1(min(2.0, max(1.0, 1.0 + max(0.0, tbr70 - 4.0) / 4.0 + max(0.0, tbr54 - 1.0) * 0.5)))
    aggro = 0.85 if hypo_prone else (0.92 if tbr70 > 4.0 else 1.0)
    p75s, p95s = kpercentile(smb, 75), kpercentile(smb, 95)
    p90m = kpercentile(man, 90)
    conf = r2(min(7.5, max(1.5, max(p90m, p95s))))
    comm = r2(min(2.5, max(0.25, max(p75s, tdd_med / 40.0))))
    cum = r1(min(max(5.0, conf), max(1.0, conf + 2.0 * comm)))
    return dict(committed=comm, confirmed=conf, cumulative=cum, hypocaution=hc, aggro=aggro,
                fastcarb=not hypo_prone, hypo_prone=hypo_prone,
                inputs=dict(p75_smb=round(p75s, 3), p95_smb=round(p95s, 3), p90_manual=round(p90m, 3),
                            n_smb=len(smb), n_manual=len(man), tdd_median=round(tdd_med, 2),
                            tdd_over_40=round(tdd_med / 40.0, 3), tbr70=round(tbr70, 2), tbr54=round(tbr54, 2)))

def load_decisions(user):
    rows = []
    with open(f"{SCRATCH}/mig_{user}_decisions.csv") as f:
        for r in csv.DictReader(f):
            rows.append(dict(
                epoch=int(r["epoch"]), s=r["s"], f=float(r["f"] or 0),
                b=float(r["b"]) if r["b"] else None, v1=float(r["v1"] or 0),
                cgm=float(r["cgm_mgdl"]) if r["cgm_mgdl"] else None))
    rows.sort(key=lambda x: x["epoch"])
    return rows

def load_cgm(user):
    t, v = [], []
    with open(f"{SCRATCH}/mig_{user}_cgm.csv") as f:
        for r in csv.DictReader(f):
            if r["cgm_mgdl"]:
                t.append(int(r["epoch"])); v.append(float(r["cgm_mgdl"]))
    return t, v

def cgm_window(tarr, varr, t0, hours=3):
    i, j = bisect_right(tarr, t0), bisect_right(tarr, t0 + hours * 3600)
    seg = varr[i:j]
    if len(seg) < 12: return None  # need reasonable coverage (~1h of 5-min)
    return min(seg), max(seg)

def tdd_median_db(user, days):
    vals = []
    with open(f"{SCRATCH}/mig_{user}_tdd.csv") as f:
        rows = list(csv.DictReader(f))
    last = max(r["d"] for r in rows)
    cutoff = (dt.date.fromisoformat(last) - dt.timedelta(days=days - 1)).isoformat()
    for r in rows:
        if r["d"] >= cutoff and r["tdd1d"]:
            vals.append(float(r["tdd1d"]))
    return median(vals), len(vals)

def analyse(user):
    cfg = CFG[user]
    boluses, sgv = load_ns(user)
    out = {"user": user}

    # ── 1. formula values 14d + 28d ─────────────────────────────────────────
    for days in (14, 28):
        smb, man, tbr70, tbr54, meanbg, nbg = window_stats(boluses, sgv, days)
        tddm, tdd_days = tdd_median_db(user, days)
        d = derive(smb, man, tbr70, tbr54, tddm)
        d["inputs"]["mean_bg"] = round(meanbg, 1); d["inputs"]["n_bg"] = nbg
        d["inputs"]["tdd_days_used"] = tdd_days
        out[f"derived_{days}d"] = d
    der = out["derived_14d"]

    # ── 2/3. migration prediction ───────────────────────────────────────────
    mig = {}
    mig["committedCap"] = dict(now=cfg["committed_cur"], at_factory=cfg["committed_at_factory"],
                               after=der["committed"] if cfg["committed_at_factory"] else cfg["committed_cur"])
    mig["confirmedCap"] = dict(now=cfg["confirmed_cur"], at_factory=cfg["confirmed_at_factory"],
                               after=der["confirmed"] if cfg["confirmed_at_factory"] else cfg["confirmed_cur"])
    mig["cumulative60"] = dict(now=cfg["cumulative_cur"], at_factory=cfg["cumulative_at_factory"],
                               after=der["cumulative"] if cfg["cumulative_at_factory"] else cfg["cumulative_cur"])
    mig["aggression"] = dict(now=cfg["aggro_cur"], at_factory=cfg["aggro_at_factory"],
                             after=der["aggro"] if cfg["aggro_at_factory"] else cfg["aggro_cur"])
    mig["hypoCaution"] = dict(now=1.0, at_factory=True, after=der["hypocaution"])
    mig["fastCarbConfirm"] = dict(now=True, at_factory=cfg["fastcarb_at_factory"],
                                  after=der["fastcarb"] if cfg["fastcarb_at_factory"] else True)
    out["migration"] = mig

    old_comm = cfg["committed_cur"]
    new_comm = mig["committedCap"]["after"]
    conf_kept = mig["confirmedCap"]["after"]
    conf_era = cfg.get("confirmed_era", cfg["confirmed_cur"])
    old_floor = min(old_comm, 0.8 * conf_era)
    new_floor = min(new_comm, 0.8 * conf_kept)
    aggro_new = mig["aggression"]["after"]
    aggro_era = cfg["aggro_cur"]

    # ── 4. impact replay over capped era ────────────────────────────────────
    rows = load_decisions(user)
    era = [r for r in rows if r["epoch"] >= ERA_START.timestamp()]
    days_seen = len({dt.datetime.fromtimestamp(r["epoch"], dt.timezone.utc).date() for r in era})
    tarr, varr = load_cgm(user)

    # base hypo rate over all era cycles
    base_n = base_h = 0
    for r in era[::3]:  # 15-min stride is plenty for a base rate
        w = cgm_window(tarr, varr, r["epoch"])
        if w: base_n += 1; base_h += (w[0] < 70)
    base_rate = base_h / base_n if base_n else float("nan")

    # 4a. committedCap change on COMMITTED-state doses
    pinned = [r for r in era if r["s"] == "COMMITTED" and abs(r["f"] - old_comm) <= 0.005
              and r["b"] is not None and r["b"] > 0]
    rc = dict(era_days=days_seen, old_cap=old_comm, new_cap=new_comm, pinned_cycles=len(pinned),
              base_cycle_hypo3h_rate_pct=round(100 * base_rate, 1))
    if new_comm > old_comm + 1e-9:
        # RAISE: only formerly-pinned cycles can gain; vf unobserved -> [0.4, 1.0] bounds
        add_lo = add_hi = 0.0
        added_hypo_u = {0.4: [0.0, 0.0], 1.0: [0.0, 0.0]}
        for r in pinned:
            b = r["b"]
            for vf in (0.4, 1.0):
                vf_eff = max(vf, old_comm / b)               # pinned => budget*vf >= old cap
                add = max(0.0, min(b * vf_eff, new_comm) - old_comm)
                if vf == 0.4: add_lo += add
                else: add_hi += add
                w = cgm_window(tarr, varr, r["epoch"])
                added_hypo_u[vf][0] += add
                if w and w[0] < 70: added_hypo_u[vf][1] += add
        rc.update(direction="raise",
                  added_U_total=[round(add_lo, 2), round(add_hi, 2)],
                  added_U_per_day=[round(add_lo / days_seen, 3), round(add_hi / days_seen, 3)],
                  pct_added_U_ahead_of_hypo3h={str(vf): (round(100 * h / u, 1) if u else None)
                                               for vf, (u, h) in added_hypo_u.items()})
    elif new_comm < old_comm - 1e-9:
        # LOWER: every COMMITTED dose above the new cap is deterministically trimmed to it
        # (delivered d = min(shot, old_cap) > new_cap => shot > new_cap => new dose = new_cap)
        trimmed = [r for r in era if r["s"] == "COMMITTED" and r["f"] > new_comm + 0.005]
        rem = prot = costly = neut = 0.0
        for r in trimmed:
            u = r["f"] - new_comm
            rem += u
            w = cgm_window(tarr, varr, r["epoch"])
            if not w: neut += u
            elif w[0] < 70: prot += u
            elif w[1] >= 180: costly += u
            else: neut += u
        rc.update(direction="lower", trimmed_cycles=len(trimmed),
                  removed_U_total=round(rem, 2), removed_U_per_day=round(rem / days_seen, 3),
                  removed_pct_protective=round(100 * prot / rem, 1) if rem else None,
                  removed_pct_costly_high180=round(100 * costly / rem, 1) if rem else None,
                  removed_pct_neutral=round(100 * neut / rem, 1) if rem else None)
    else:
        rc.update(direction="none")
    out["replay_committed"] = rc

    # 4b. confirm-floor flip (delivered-dose lower-bound method + budget-range check)
    confirmed = [r for r in era if r["s"] == "CONFIRMED" and r["f"] > 0]
    # first cycle of each CONFIRMED episode = the gate-passing entry
    entries, prev_e = [], None
    for r in era:
        if r["s"] == "CONFIRMED":
            if prev_e is None or prev_e != "CONFIRMED": entries.append(r)
        prev_e = r["s"]
    rf = dict(old_floor=round(old_floor, 2), new_floor=round(new_floor, 2),
              confirm_entries=len(entries), confirmed_dose_cycles=len(confirmed),
              confirmed_dose_p50=round(kpercentile([r["f"] for r in confirmed], 50), 2) if confirmed else None,
              confirmed_dose_p90=round(kpercentile([r["f"] for r in confirmed], 90), 2) if confirmed else None)
    m_new = 1.8 * aggro_new
    if new_floor > old_floor + 1e-9:
        # RISING floor: some historical confirm entries would now be blocked.
        # Delivered dose is a LOWER bound on the prospective shot -> 'possibly_blocked' is an upper bound.
        still_pass = maybe_block = def_block = 0
        at_risk_u = 0.0
        for r in entries:
            d = r["f"]
            if d > new_floor:
                still_pass += 1; continue
            if r["b"] and r["b"] * m_new <= new_floor:      # even vf=1.0 can't clear the floor
                def_block += 1; at_risk_u += d; continue
            maybe_block += 1; at_risk_u += d
        rf.update(direction="rise", still_pass_definite=still_pass, possibly_blocked=maybe_block,
                  definitely_blocked=def_block, entry_U_at_risk=round(at_risk_u, 2),
                  note="delivered-dose lower-bound method; possibly_blocked is an UPPER bound on flips")
    elif new_floor < old_floor - 1e-9:
        # FALLING floor: nothing newly blocked (a shot that cleared the old, higher floor clears the
        # new one). Newly UNBLOCKED cycles are OBSERVING cycles whose prospective shot fell in
        # (new_floor, old_floor]. vf unobserved -> count cycles whose range straddles the band
        # (upper bound: score/age eligibility also unobserved).
        m_era = 1.8 * aggro_era
        definite = possible = 0
        for r in era:
            if r["s"] != "OBSERVING" or not r["b"] or r["b"] <= 0: continue
            lo_p, hi_p = r["b"] * m_era * 0.4, r["b"] * m_era * 1.0
            if lo_p > new_floor and hi_p <= old_floor: definite += 1     # whole range in band
            elif hi_p > new_floor and lo_p <= old_floor: possible += 1   # range intersects band
        rf.update(direction="fall", newly_blocked=0,
                  unblock_candidates_range_fully_in_band=definite,
                  unblock_candidates_range_intersects_band=possible,
                  note="unblock counts are UPPER bounds (gate eligibility + vf unobserved)")
    else:
        rf.update(direction="none")
    out["replay_confirm_floor"] = rf

    # 4c. cumulative 60-min cap change (tightening if factory 10 -> derived).
    # REAL semantics (DetermineBasalBoost.kt:1653): threshold-SUSPEND — if SMB U delivered in the
    # last 60 min >= cap, this cycle's SMB is zeroed entirely (no trim-to-headroom). Rolling sums
    # can therefore legitimately overshoot the cap.
    old_cum = cfg["cumulative_cur"]
    new_cum = mig["cumulative60"]["after"]
    supp = []
    if abs(new_cum - old_cum) > 1e-9:
        dq = deque()  # (epoch, delivered_new)
        for r in era:
            if r["f"] <= 0: continue
            t = r["epoch"]
            while dq and dq[0][0] <= t - 3600: dq.popleft()
            win = sum(u for _, u in dq)
            if win >= new_cum:                      # suspend: whole dose suppressed
                supp.append((t, r["f"]))
                dq.append((t, 0.0))
            else:
                dq.append((t, r["f"]))
        # observed old-regime max rolling sum (ceiling inference)
    roll_max, dq = 0.0, deque()
    for r in era:
        if r["f"] <= 0: continue
        t = r["epoch"]
        while dq and dq[0][0] <= t - 3600: dq.popleft()
        dq.append((t, r["f"]))
        roll_max = max(roll_max, sum(u for _, u in dq))
    prot = costly = neut = 0.0
    for t, u in supp:
        w = cgm_window(tarr, varr, t)
        if not w: neut += u
        elif w[0] < 70: prot += u
        elif w[1] >= 180: costly += u
        else: neut += u
    tot_supp = sum(u for _, u in supp)
    out["replay_cumulative"] = dict(
        old_cap=old_cum, new_cap=new_cum, changes=abs(new_cum - old_cum) > 1e-9,
        observed_max_rolling60_U=round(roll_max, 2),
        suppressed_cycles=len(supp), suppressed_U_total=round(tot_supp, 2),
        suppressed_U_per_day=round(tot_supp / days_seen, 3) if days_seen else None,
        removed_pct_protective=round(100 * prot / tot_supp, 1) if tot_supp else None,
        removed_pct_costly_high180=round(100 * costly / tot_supp, 1) if tot_supp else None,
        removed_pct_neutral=round(100 * neut / tot_supp, 1) if tot_supp else None,
    )

    # ── 6. formula-design: does one confirm shot exhaust the hour? ──────────
    # Suspend semantics: follow-on shots keep flowing while window sum < cumulative cap; the shot
    # that crosses is still delivered in full. Follow-on committed shots after a confirm S:
    #   ceil((cum - S) / comm) if S < cum else 0.
    conf_hist = [r["f"] for r in confirmed]
    max_conf = max(conf_hist) if conf_hist else 0.0
    p90_conf = kpercentile(conf_hist, 90) if conf_hist else 0.0
    def followons(cum, shot, comm):
        if shot >= cum: return 0
        return math.ceil((cum - shot) / comm) if comm > 0 else None
    # operative post-migration values (kept or derived)
    cum_op, conf_op, comm_op = mig["cumulative60"]["after"], mig["confirmedCap"]["after"], mig["committedCap"]["after"]
    out["design_q"] = dict(
        derived_cumulative=der["cumulative"], derived_confirmed=der["confirmed"], derived_committed=der["committed"],
        one_derived_confirm_exhausts_hour=der["confirmed"] >= der["cumulative"],
        followons_after_derived_confirm_pureformula=followons(der["cumulative"], der["confirmed"], der["committed"]),
        operative_post_migration=dict(cumulative=cum_op, confirmed=conf_op, committed=comm_op),
        hist_confirm_p90=round(p90_conf, 2), hist_confirm_max=round(max_conf, 2),
        one_max_hist_confirm_exhausts_hour_postmig=max_conf >= cum_op,
        followons_after_hist_p90_confirm_postmig=followons(cum_op, p90_conf, comm_op) if conf_hist else None,
    )

    # V6 dosing volume context
    v5u = sum(r["f"] for r in era)
    v1u = sum(r["v1"] for r in era)
    out["context"] = dict(era_v5_U_per_day=round(v5u / days_seen, 2), era_v1_U_per_day=round(v1u / days_seen, 2),
                          era_days=days_seen, era_dosing_cycles=sum(1 for r in era if r["f"] > 0))
    return out

if __name__ == "__main__":
    for u in (sys.argv[1:] or ["tim", "E"]):
        res = analyse(u)
        with open(f"{SCRATCH}/mig_{u}_report.json", "w") as f:
            json.dump(res, f, indent=1)
        print(json.dumps(res, indent=1))
