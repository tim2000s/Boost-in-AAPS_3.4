#!/usr/bin/env python3
"""
Boost episode-anchored impact estimate — "what would V5's dosing changes have DONE?"
====================================================================================

shadow_equivalence.py answers how much V5's *decisions* differ from V1. This script takes the
next step the data allows: for every real LOW and HIGH episode in the history, it attributes the
V5-vs-V1 dose difference in the run-up and translates it into an *estimated* BG impact, using the
user's own logged ISF and a standard insulin-activity curve.

MODEL (first-order, open-loop — stated plainly because it is NOT a simulation):
  The real BG trajectory was produced by V1 (acting). On each shadow cycle we also have what V5
  WOULD have dosed (`boostV5_finalDose`). The dose V5 would have withheld vs V1 in the run-up to an
  episode, weighted by how much of that insulin would already have ACTED by the episode's extreme,
  times ISF, estimates how the episode's extreme would shift under V5:

      ΔBG_est = ISF × Σ_i (dose_V1,i − dose_V5,i) × activatedFraction(t_extreme − t_i)

  activatedFraction = 1 − IOB_fraction (oref exponential model, peak 75 min, DIA 300 min).
  • LOW episode  (nadir): +ΔBG_est = how much SHALLOWER the low would be (V5 typically doses less).
  • HIGH episode (peak):  +ΔBG_est = how much HIGHER the peak would run (the cost of dosing less).

WHAT THIS IS NOT: a glucose simulation. It assumes the rest of the trajectory (carbs, counter-
regulation, basal, subsequent loop reactions) is unchanged and simply adds the marginal insulin
effect. It is a transparent order-of-magnitude estimate grounded in each user's real ISF, not a
clinical claim. Only SHADOW cycles (V1 actually drove the real BG) are used for attribution.

PRIVACY: identical to the other backtesting scripts. URLs/tokens in $BOOST_BACKTEST_SITES (outside
repo), raw cache outside repo, report shows only anonymous tags + aggregate stats. Safe to commit.

USAGE:  python3 episode_impact.py [--window-days 90] [--low 70] [--high 180] [--no-cache]
"""

import argparse
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CONFIG_PATH = os.environ.get("BOOST_BACKTEST_SITES", os.path.expanduser("~/.config/boost_backtest/sites.json"))
CACHE_DIR = os.environ.get("BOOST_BACKTEST_CACHE", os.path.expanduser("~/.cache/boost_backtest"))
REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "EPISODE_IMPACT_REPORT.md")
CHUNK_DAYS = 7
DAY_MS = 86_400_000
LOOKBACK_MIN = 150          # insulin run-up window before an episode extreme (≈ SMB action span)
CAP_MGDL = 90.0             # physiologic clamp per episode (~5 mmol). Beyond this the first-order
                            # additive model is meaningless (a single dose delta cannot plausibly
                            # move one episode's extreme by more), so we cap to avoid outlier inflation.
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


def _num(v):
    return float(v) if isinstance(v, (int, float)) else None


def iob_fraction(minutes_since, dia_min=300.0, peak_min=75.0):
    """oref exponential insulin model — fraction of a dose still on board (not yet acted)."""
    t = float(minutes_since)
    if t <= 0:
        return 1.0
    if t >= dia_min:
        return 0.0
    tau = peak_min * (1 - peak_min / dia_min) / (1 - 2 * peak_min / dia_min)
    a = 2 * tau / dia_min
    S = 1 / (1 - a + (1 + a) * math.exp(-dia_min / tau))
    iob = 1 - S * (1 - a) * ((t * t / (tau * dia_min * (1 - a)) - t / tau - 1) * math.exp(-t / tau) + 1)
    return max(0.0, min(1.0, iob))


def load(site, window_days, use_cache):
    base, token, tag = site["base"], site["token"], site["tag"]
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, f"impact_{tag}_{window_days}d.json")
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
        if not ts or "boostV5_state" not in s:
            continue
        reason = str(s.get("reason", ""))
        active = "V5-ACTIVE drove" in reason
        m = V1_WOULD_RE.search(reason)
        isf = _num(s.get("variable_sens")) or _num(s.get("sens")) or _num(s.get("ISF"))
        cyc.append({
            "ts": ts,
            "bg": _num(s.get("bg")),
            "units": _num(s.get("units")) or 0.0,
            "finalDose": _num(s.get("boostV5_finalDose")) or 0.0,
            "v1would": float(m.group(1)) if m else None,
            "active": active,
            "isf": isf,
        })
    cyc.sort(key=lambda c: c["ts"])
    data = {"tag": tag, "cyc": cyc}
    with open(cache, "w") as f:
        json.dump(data, f)
    return data


def find_episodes(cyc, low_th, high_th):
    """Contiguous runs below low_th (nadir) / above high_th (peak). Returns (lows, highs)."""
    lows, highs = [], []
    def runs(is_in, pick):
        out, cur = [], []
        for c in cyc:
            if c["bg"] is None:
                if cur: out.append(cur); cur = []
                continue
            if is_in(c["bg"]):
                cur.append(c)
            elif cur:
                out.append(cur); cur = []
        if cur: out.append(cur)
        return [pick(r) for r in out if r]
    lows = runs(lambda b: b < low_th, lambda r: min(r, key=lambda c: c["bg"]))
    highs = runs(lambda b: b > high_th, lambda r: max(r, key=lambda c: c["bg"]))
    return lows, highs


def estimate_delta_bg(cyc, idx_by_ts, extreme, isf_fallback):
    """ΔBG estimate at an episode extreme from the V1−V5 dose delta in the run-up. Shadow cycles only."""
    t_ext = extreme["ts"]
    isf = extreme["isf"] or isf_fallback
    if not isf:
        return None, 0.0
    withheld = 0.0  # Σ (v1 − v5) × activatedFraction  (units of "effective insulin")
    for c in cyc:
        if c["active"]:           # real BG here was driven by V5, not V1 — skip for V1-trajectory attribution
            continue
        dt = (t_ext - c["ts"]) / 60000.0
        if dt < 0 or dt > LOOKBACK_MIN:
            continue
        v1 = c["units"]
        v5 = c["finalDose"]
        withheld += (v1 - v5) * (1.0 - iob_fraction(dt))
    return withheld * isf, withheld


def pctl(xs, p):
    if not xs: return None
    s = sorted(xs); k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def analyse(data, low_th, high_th):
    cyc = data["cyc"]
    shadow = [c for c in cyc if not c["active"]]
    if len(shadow) < 50:
        return None
    span_days = (cyc[-1]["ts"] - cyc[0]["ts"]) / DAY_MS
    isfs = [c["isf"] for c in cyc if c["isf"]]
    isf_fallback = (sorted(isfs)[len(isfs) // 2]) if isfs else None
    lows, highs = find_episodes(cyc, low_th, high_th)

    low_rows = []
    for ep in lows:
        dbg, withheld = estimate_delta_bg(cyc, None, ep, isf_fallback)
        if dbg is None: continue
        dbg = max(-CAP_MGDL, min(CAP_MGDL, dbg))     # physiologic clamp (see CAP_MGDL)
        low_rows.append({"nadir": ep["bg"], "dbg": dbg, "lifted": (ep["bg"] + dbg) >= low_th})
    high_rows = []
    for ep in highs:
        dbg, withheld = estimate_delta_bg(cyc, None, ep, isf_fallback)
        if dbg is None: continue
        dbg = max(-CAP_MGDL, min(CAP_MGDL, dbg))     # physiologic clamp
        high_rows.append({"peak": ep["bg"], "dbg": dbg})

    low_dbg = [r["dbg"] for r in low_rows]
    high_dbg = [r["dbg"] for r in high_rows]
    return {
        "tag": data["tag"], "span_days": span_days,
        "isf_used": isf_fallback,
        "n_low": len(low_rows),
        "low_med_dbg": pctl(low_dbg, 50), "low_p75_dbg": pctl(low_dbg, 75),
        "low_lifted": sum(1 for r in low_rows if r["lifted"]),
        "low_med_nadir": pctl([r["nadir"] for r in low_rows], 50),
        "n_high": len(high_rows),
        "high_med_dbg": pctl(high_dbg, 50), "high_p75_dbg": pctl(high_dbg, 75),
        "high_med_peak": pctl([r["peak"] for r in high_rows], 50),
    }


def mmol(x):
    return None if x is None else x / 18.0


def build_report(results, window_days, low_th, high_th):
    R = []
    R.append("# Boost episode-anchored impact estimate")
    R.append("")
    R.append(f"_What V5's dosing changes would have done at real LOW/HIGH episodes. Window: last "
             f"**{window_days} days**. Low <{low_th}, High >{high_th} mg/dL. Users anonymised. "
             f"Generated by `episode_impact.py`._")
    R.append("")
    R.append("## Method (and its limits — read first)")
    R.append("")
    R.append("The real BG was driven by **V1**. For each episode we sum the dose V5 would have "
             "withheld vs V1 over the prior %d min, weight each by how much of it would already "
             "have *acted* by the episode extreme (oref exponential insulin curve), and multiply by "
             "the user's logged **ISF**:" % LOOKBACK_MIN)
    R.append("")
    R.append("> ΔBG ≈ ISF × Σ (dose_V1 − dose_V5) × activatedFraction(t_extreme − t_dose)")
    R.append("")
    R.append("- **Low episodes:** +ΔBG = how much **shallower** the low would be under V5.")
    R.append("- **High episodes:** +ΔBG = how much **higher** the peak would run under V5 (the cost).")
    R.append("- **First-order, open-loop estimate — NOT a glucose simulation.** It adds only the "
             "marginal insulin effect and assumes carbs/counter-regulation/subsequent loop reactions "
             "are unchanged. Only shadow cycles (V1 drove the real BG) are attributed. Treat as "
             "order-of-magnitude, grounded in each user's real ISF.")
    R.append("")
    R.append("## Estimated impact at LOW episodes (V5 = gentler dosing → shallower lows)")
    R.append("")
    R.append("| user | days | ISF | lows | median nadir | median ΔBG | p75 ΔBG | lows lifted ≥ threshold |")
    R.append("|---|--:|--:|--:|--:|--:|--:|--:|")
    for r in results:
        if not r: continue
        R.append(f"| {r['tag']} | {r['span_days']:.0f} | {r['isf_used']:.0f} | {r['n_low']} | "
                 f"{r['low_med_nadir']:.0f} ({mmol(r['low_med_nadir']):.1f}) | "
                 f"**+{r['low_med_dbg']:.0f}** (+{mmol(r['low_med_dbg']):.1f}) | "
                 f"+{r['low_p75_dbg']:.0f} (+{mmol(r['low_p75_dbg']):.1f}) | "
                 f"{r['low_lifted']}/{r['n_low']} ({100.0*r['low_lifted']/r['n_low']:.0f}%) |")
    R.append("")
    R.append("_ΔBG in mg/dL (mmol/L). “lifted” = nadir + estimated ΔBG would reach/exceed the low "
             "threshold — i.e. the episode would likely not have been a low under V5._")
    R.append("")
    R.append("## Estimated cost at HIGH episodes (V5 dosing less → higher peaks)")
    R.append("")
    R.append("| user | highs | median peak | median ΔBG (higher) | p75 ΔBG |")
    R.append("|---|--:|--:|--:|--:|")
    for r in results:
        if not r: continue
        R.append(f"| {r['tag']} | {r['n_high']} | {r['high_med_peak']:.0f} ({mmol(r['high_med_peak']):.1f}) | "
                 f"+{r['high_med_dbg']:.0f} (+{mmol(r['high_med_dbg']):.1f}) | "
                 f"+{r['high_p75_dbg']:.0f} (+{mmol(r['high_p75_dbg']):.1f}) |")
    R.append("")
    R.append("## Reading it")
    R.append("")
    R.append("The trade V5 makes is visible directly: at lows it would have withheld insulin → a "
             "positive ΔBG (shallower / averted lows); at highs the same gentleness costs a positive "
             "ΔBG (higher peaks). If low-side ΔBG is materially larger than high-side ΔBG, V5 is "
             "trading a lot of low-risk for a little high — the intended behaviour. These are "
             "estimates; live multi-user shadow data is how we confirm them.")
    R.append("")
    return "\n".join(R)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=90)
    ap.add_argument("--low", type=float, default=70.0)
    ap.add_argument("--high", type=float, default=180.0)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    with open(CONFIG_PATH) as f:
        sites = json.load(f)["sites"]

    results = []
    for site in sites:
        try:
            data = load(site, args.window_days, not args.no_cache)
            r = analyse(data, args.low, args.high)
            results.append(r)
            if r:
                print(f"[{r['tag']}] {r['n_low']} lows (med ΔBG +{r['low_med_dbg']:.0f}), "
                      f"{r['n_high']} highs (med ΔBG +{r['high_med_dbg']:.0f})", flush=True)
            else:
                print(f"[{site['tag']}] insufficient shadow cycles", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{site['tag']}] failed: {e}", flush=True)

    report = build_report(results, args.window_days, args.low, args.high)
    with open(REPORT_PATH, "w") as f:
        f.write(report)
    print(f"\nReport → {REPORT_PATH}")


if __name__ == "__main__":
    main()
