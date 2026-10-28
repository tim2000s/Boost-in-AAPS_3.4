#!/usr/bin/env python3
"""
Boost shadow-equivalence report — Method 1 of arXiv 2606.13882v1 ("Safe Algorithm Updates in
Automated Insulin Delivery Systems"), applied to Boost's Nightscout timeseries.
================================================================================================

The paper validates an AID algorithm change (oref JS→Swift) with three methods:
  1. SHADOW EXECUTION  — run both versions per-cycle, compare component outputs, report mismatch %.
  2. DATA-DRIVEN REPLAY — re-run both versions over historical traces, Parkes-grid the glucose.
  3. IN-SILICO          — UVA/Padova virtual patients.

THIS SCRIPT IS METHOD 1, which we can run directly because Boost's devicestatus is ALREADY a
shadow-execution log carrying paired outputs every cycle:
  - determineBasal:  V1 `units` (acting SMB)  vs  V5 `boostV5_finalDose`  (and the `V1 would=Y`
                     counterfactual that V5-active cycles log — used as V1 when V5 drove the dose).
  - ISF overlay:     `isfShadow_deltaPct` — the V4.4.2 EMA(τ=3h) sensitivity overlay's deviation
                     from the instantaneous ratio actually used (a genuine same-algo two-path shadow).
  - meal:            `boostV5_state` distribution.
  - context:         bg, iob.

It reports, per component and per user (anonymised):
  - AGREEMENT within tolerance (the paper's headline metric), and the divergence distribution.
NOTE on framing:
  - ISF-overlay is an EQUIVALENCE question (same algo, two computations — "is the EMA overlay
    clinically equivalent to instant?"). Mismatch should be small/bounded.
  - V1-vs-V5 SMB is a DIVERGENCE question (two DIFFERENT algorithms — divergence is EXPECTED and
    intentional). Here the mismatch rate quantifies HOW different V5 is from V1 and WHERE — the
    rigorous version of the beta-readiness question.

LIMITATION: full glucose-outcome clinical equivalence (Parkes Error Grid on counterfactual glucose)
needs Method 2 (a replay harness — the V6 Phase-0 `replay.py`), which is NOT built. Method 1 covers
DECISION divergence, not simulated glucose outcomes.

PRIVACY: identical to v5_shadow_backtest.py — URLs/tokens in $BOOST_BACKTEST_SITES (outside repo),
raw cache outside repo, report shows only anonymous tags + aggregate stats. Safe to commit.

USAGE:  python3 shadow_equivalence.py [--window-days 30] [--no-cache]
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CONFIG_PATH = os.environ.get("BOOST_BACKTEST_SITES", os.path.expanduser("~/.config/boost_backtest/sites.json"))
CACHE_DIR = os.environ.get("BOOST_BACKTEST_CACHE", os.path.expanduser("~/.cache/boost_backtest"))
REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SHADOW_EQUIVALENCE_REPORT.md")
CHUNK_DAYS = 7
DAY_MS = 86_400_000
SMB_TOL_U = 0.05            # doses within this are "agreement" (≈ a pump increment)
ISF_TOL_PCT = 5.0          # ISF overlay within ±5% = clinically equivalent
V1_WOULD_RE = re.compile(r"V1 would=([0-9.]+)U")


def _get(base, token, path, params, attempts=4, backoff=15):
    p = dict(params); p["token"] = token
    url = f"{base}/api/v1/{path}.json?" + urllib.parse.urlencode(p, safe="[]$<>")
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            if i < attempts - 1:
                time.sleep(backoff); continue
            raise
    raise last


def _iso(ms): return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _ts(d):
    s = d.get("openaps", {}).get("suggested", {})
    for v in (s.get("date"), d.get("mills")):
        if isinstance(v, (int, float)) and v > 1e11:
            return int(v)
    ca = d.get("created_at")
    if ca:
        try:
            return int(datetime.strptime(ca[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)
        except ValueError:
            return None
    return None


def load(site, window_days, use_cache):
    base, token, tag = site["base"], site["token"], site["tag"]
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, f"equiv_{tag}_{window_days}d.json")
    if use_cache and os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)
    now = int(time.time() * 1000); start = now - window_days * DAY_MS
    ds, win_end = [], now
    while win_end > start:
        win_start = max(start, win_end - CHUNK_DAYS * DAY_MS)
        try:
            ds += _get(base, token, "devicestatus", {"count": 200000, "find[created_at][$gte]": _iso(win_start), "find[created_at][$lte]": _iso(win_end)})
        except Exception as e:  # noqa: BLE001
            print(f"  [{tag}] chunk failed: {e}", flush=True)
        win_end = win_start - 1
    cyc = []
    for d in ds:
        s = d.get("openaps", {}).get("suggested", {})
        ts = _ts(d)
        if not ts or "boostV5_state" not in s:    # only genuine Boost-V5 cycles
            continue
        reason = str(s.get("reason", ""))
        active = "V5-ACTIVE drove" in reason
        m = V1_WOULD_RE.search(reason)
        cyc.append({
            "ts": ts,
            "bg": s.get("bg"),
            "units": s.get("units") if isinstance(s.get("units"), (int, float)) else 0.0,
            "finalDose": s.get("boostV5_finalDose") if isinstance(s.get("boostV5_finalDose"), (int, float)) else 0.0,
            "v1would": float(m.group(1)) if m else None,
            "active": active,
            "state": s.get("boostV5_state"),
            "isfDeltaPct": s.get("isfShadow_deltaPct") if isinstance(s.get("isfShadow_deltaPct"), (int, float)) else None,
        })
    cyc.sort(key=lambda c: c["ts"])
    data = {"tag": tag, "cyc": cyc}
    with open(cache, "w") as f:
        json.dump(data, f)
    return data


def analyse(data):
    cyc = data["cyc"]
    if not cyc:
        return None
    span_days = (cyc[-1]["ts"] - cyc[0]["ts"]) / DAY_MS

    # ---- determineBasal: V1 vs V5 SMB per cycle ----
    # V1 SMB = `units` on shadow cycles; the `V1 would=` counterfactual on V5-active cycles.
    pairs = []
    for c in cyc:
        v5 = c["finalDose"]
        v1 = c["v1would"] if (c["active"] and c["v1would"] is not None) else c["units"]
        pairs.append((v1, v5, c))
    n = len(pairs)
    agree = sum(1 for v1, v5, _ in pairs if abs(v5 - v1) <= SMB_TOL_U)
    deltas = [v5 - v1 for v1, v5, _ in pairs]
    v5_more = sum(1 for d in deltas if d > SMB_TOL_U)
    v5_less = sum(1 for d in deltas if d < -SMB_TOL_U)
    big = sorted((abs(d) for d in deltas), reverse=True)
    p95 = big[int(len(big) * 0.05)] if big else 0.0
    tot_v1 = sum(v1 for v1, _, _ in pairs); tot_v5 = sum(v5 for _, v5, _ in pairs)

    # ---- ISF EMA overlay equivalence (same algo, two computations) ----
    isf = [c["isfDeltaPct"] for c in cyc if c["isfDeltaPct"] is not None]
    isf_within = sum(1 for d in isf if abs(d) <= ISF_TOL_PCT)
    isf_abs_sorted = sorted((abs(d) for d in isf), reverse=True)
    isf_p95 = isf_abs_sorted[int(len(isf_abs_sorted) * 0.05)] if isf_abs_sorted else None

    # ---- meal state distribution ----
    states = {}
    for c in cyc:
        states[c["state"]] = states.get(c["state"], 0) + 1

    return {
        "tag": data["tag"], "span_days": span_days, "n": n,
        "smb_agree_pct": 100.0 * agree / n if n else 0,
        "smb_mismatch_pct": 100.0 * (n - agree) / n if n else 0,
        "smb_v5_more_pct": 100.0 * v5_more / n if n else 0,
        "smb_v5_less_pct": 100.0 * v5_less / n if n else 0,
        "smb_p95_abs_delta": p95,
        "smb_mean_delta": (sum(deltas) / n) if n else 0,
        "net_v1": tot_v1, "net_v5": tot_v5,
        "isf_n": len(isf),
        "isf_within_pct": (100.0 * isf_within / len(isf)) if isf else None,
        "isf_p95_abs": isf_p95,
        "isf_mean": (sum(isf) / len(isf)) if isf else None,
        "states": states,
    }


def build_report(results, window_days):
    R = []
    R.append("# Boost shadow-equivalence report")
    R.append("")
    R.append(f"_Method 1 (shadow execution) of arXiv 2606.13882v1, on Boost's Nightscout devicestatus. "
             f"Window: last **{window_days} days**. Users anonymised. Generated by `shadow_equivalence.py`._")
    R.append("")
    R.append("## What this measures (and what it doesn't)")
    R.append("")
    R.append("Boost logs paired per-cycle outputs, so we can compute the paper's per-component agreement directly:")
    R.append("- **determineBasal (SMB): a DIVERGENCE metric.** V1 (acting) vs V5 — these are *different* "
             "algorithms, so divergence is intentional. The mismatch rate quantifies how different V5 is "
             "from V1 and where — the rigorous version of beta-readiness. (V1 SMB = `units` on shadow "
             "cycles; the `V1 would=` counterfactual on V5-active cycles. Tolerance ±%.2fU.)" % SMB_TOL_U)
    R.append("- **ISF EMA overlay: an EQUIVALENCE metric.** `isfShadow_deltaPct` is the V4.4.2 EMA(τ=3h) "
             "sensitivity overlay vs the instantaneous ratio actually used — same algorithm, two "
             f"computations. Should be small/bounded (±{ISF_TOL_PCT:.0f}%).")
    R.append("- **NOT covered:** glucose-outcome clinical equivalence (Parkes Error Grid on counterfactual "
             "glucose) needs the replay harness (Method 2 — the V6 Phase-0 `replay.py`), not yet built. "
             "This is decision divergence, not simulated outcomes.")
    R.append("")
    R.append("## determineBasal — V1 vs V5 SMB divergence")
    R.append("")
    R.append("| user | days | cycles | agree ≤0.05U | V5 doses more | V5 doses less | p95 |Δ| | mean Δ | net V1→V5 |")
    R.append("|---|--:|--:|--:|--:|--:|--:|--:|--:|")
    for a in results:
        R.append(f"| {a['tag']} | {a['span_days']:.0f} | {a['n']:,} | {a['smb_agree_pct']:.0f}% | "
                 f"{a['smb_v5_more_pct']:.0f}% | {a['smb_v5_less_pct']:.0f}% | {a['smb_p95_abs_delta']:.2f}U | "
                 f"{a['smb_mean_delta']:+.3f}U | {a['net_v1']:.0f}→{a['net_v5']:.0f}U |")
    R.append("")
    R.append("_High agreement = V5 mostly matches V1 (most cycles neither doses); the divergence concentrates "
             "in the meal cycles. 'p95 |Δ|' is the 95th-percentile absolute per-cycle SMB difference — the "
             "size of the biggest routine disagreements._")
    R.append("")
    R.append("## ISF EMA-overlay — equivalence")
    R.append("")
    R.append("| user | cycles w/ ISF shadow | within ±5% | p95 |Δ%| | mean Δ% |")
    R.append("|---|--:|--:|--:|--:|")
    for a in results:
        if a["isf_within_pct"] is None:
            R.append(f"| {a['tag']} | 0 | — | — | — |")
        else:
            R.append(f"| {a['tag']} | {a['isf_n']:,} | {a['isf_within_pct']:.0f}% | {a['isf_p95_abs']:.1f}% | {a['isf_mean']:+.1f}% |")
    R.append("")
    R.append("_If the EMA overlay is within ±5% on ~all cycles it's clinically equivalent to instant ISF "
             "(safe to adopt as a 'computational/heuristic' change per the paper's taxonomy); large/ "
             "systematic deltas mean it's a behavioural change needing gradual transition._")
    R.append("")
    R.append("## meal-state distribution")
    R.append("")
    for a in results:
        tot = sum(a["states"].values()) or 1
        dist = ", ".join(f"{k} {100*v/tot:.0f}%" for k, v in sorted(a["states"].items(), key=lambda kv: -kv[1]) if k)
        R.append(f"- **{a['tag']}**: {dist}")
    R.append("")
    R.append("## Reading it (bug taxonomy — paper Part I)")
    R.append("")
    R.append("- **Factual** bugs (objective, fix immediately): already done — HypoCaution inversion, "
             "getGlucoseStatusData-null, constraint gaps.")
    R.append("- **Heuristic** (co-adapted with the user — transition GRADUALLY): V5 aggression/dose "
             "calibration, the fast-carb confirm timing. The SMB-divergence columns above quantify how far "
             "V5 has moved from the V1 the user co-adapted to — large moves argue for shadow-first + gradual.")
    R.append("- **Computational** (numeric equivalence): cross-repo port (3.4 Kotlin → V4 Compose). Validate "
             "with the SMB + ISF agreement metrics here once the V4 build emits shadow data.")
    R.append("")
    R.append("## Next: Method 2 (replay) for true clinical equivalence")
    R.append("")
    R.append("Build `replay.py` (V6 Phase 0): re-run determine_basal over historical NS inputs under two "
             "algorithm versions, then Parkes-Error-Grid the resulting dosing/predicted-glucose. That gives "
             "the paper's clinical-equivalence gate (≥99% Parkes A/B, TIR within tolerance) — the acceptance "
             "test for the fast-carb fix, the V5 beta decision, and the V4 port.")
    return "\n".join(R)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=30)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(CONFIG_PATH):
        sys.exit(f"Config not found: {CONFIG_PATH} (set $BOOST_BACKTEST_SITES)")
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    results = []
    for site in cfg["sites"]:
        print(f"[{site['tag']}] loading {args.window_days}d ...", flush=True)
        try:
            data = load(site, args.window_days, use_cache=not args.no_cache)
        except Exception as e:  # noqa: BLE001
            print(f"  [{site['tag']}] FAILED: {e}", flush=True); continue
        a = analyse(data)
        if a:
            results.append(a)
            print(f"  [{site['tag']}] {a['n']} V5 cycles, SMB agree {a['smb_agree_pct']:.0f}%", flush=True)
    if not results:
        sys.exit("No data.")
    report = build_report(results, args.window_days)
    with open(REPORT_PATH, "w") as f:
        f.write(report)
    print(f"\nReport: {REPORT_PATH}\n")
    print(report)


if __name__ == "__main__":
    main()
