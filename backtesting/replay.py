#!/usr/bin/env python3
"""
Boost replay harness — Method 2 of arXiv 2606.13882v1, first use: validate the fast-carb fix.
================================================================================================
The paper's "data-driven replay" re-runs a CANDIDATE algorithm change over real historical inputs
and compares behaviour, BEFORE shipping it. This is that, applied to the #1 V5 priority — the
fast-carb confirm fast-path ([[boost_v5_fastcarb_confirm_latency_2026-06-16]]).

PROBLEM being validated: V5's observe→confirm latency commits ~1 cycle late on fast carbs (2026-06-16
meal: V5 dribbled 0.3U in OBSERVING at BG 120 while V1 would've dosed 1.7U; committed 1.95U a cycle
late → peak 185 then crash 54). Proposed fix: promote OBSERVING→CONFIRMED in a SINGLE cycle when
acceleration is extreme. The risk is FALSE POSITIVES (firing on compression spikes / exercise rises).

This replay reconstructs each cycle's signals from logged NS devicestatus (`deltaAcceleration` is
logged; 5-min `delta` is derived from the BG sequence) and replays a candidate fast-path rule
  FAST-CONFIRM if (state in IDLE/OBSERVING) and delta >= Dt and deltaAccl >= At
over history, classifying each firing:
  - TRUE  : V5 actually reached CONFIRMED/COMMITTED within the next [FOLLOW_CYCLES] cycles
            → a real meal; the fast-path would just have committed EARLIER (lead-time measured).
  - FALSE : no real confirm/sustained-rise followed → it would have committed on a non-meal.
  - SLEEP : fired while sleepState=SLEEPING (compression-artifact risk — should be ~0).
Reports, per candidate threshold set: meals caught earlier, median lead-time, false-positive rate,
sleep fires. Lets us pick thresholds that catch fast carbs early WITHOUT over-firing — before any
Kotlin change.

NOT a glucose simulation (that needs a physiologic model / Method 3). It's a faithful replay of the
DECISION GATE over real inputs — the paper's replay methodology for a gate change.

PRIVACY: same as the other backtesting scripts (config/cache outside repo; anonymised tags;
aggregate stats; no URLs). Safe to commit.

USAGE: python3 replay.py [--window-days 30] [--no-cache]
"""
import argparse, base64, json, os, statistics, time, urllib.parse, urllib.request
from datetime import datetime, timezone

CONFIG_PATH = os.environ.get("BOOST_BACKTEST_SITES", os.path.expanduser("~/.config/boost_backtest/sites.json"))
CACHE_DIR = os.environ.get("BOOST_BACKTEST_CACHE", os.path.expanduser("~/.cache/boost_backtest"))
HERE = os.path.dirname(os.path.abspath(__file__))
CHUNK_DAYS, DAY_MS = 7, 86_400_000
FOLLOW_CYCLES = 4           # a fast-path fire is TRUE if a real CONFIRMED/COMMITTED occurs within this many cycles
CYCLE_MS = 5 * 60_000
# candidate fast-path rules: (name, delta mg/dL/5min, deltaAccl %, score_min or None, exclude_sleep)
# Raw delta+accl rules first; then "corroborated" variants that also require the V5 meal score and
# exclude sleep (to cut the false/compression fires the raw rules produce).
CANDIDATES = [
    ("loose", 8, 15, None, False),
    ("mid", 10, 20, None, False),
    ("tight", 12, 30, None, False),
    ("loose+score+awake", 8, 15, 0.60, True),
    ("mid+score+awake", 10, 20, 0.55, True),
]


def _get(base, token, path, params, attempts=4, backoff=15):
    p = dict(params); p["token"] = token
    url = f"{base}/api/v1/{path}.json?" + urllib.parse.urlencode(p, safe="[]$<>")
    # Browser-ish User-Agent: some hosts (e.g. *.nightscoutpro.com behind Cloudflare) 403 the bare
    # Python-urllib UA. Tokens still authorise; this just gets us past the bot filter.
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (boost-backtest)"})
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            if i < attempts - 1: time.sleep(backoff); continue
            raise
    raise last


def _iso(ms): return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def load(site, window_days, use_cache):
    base, token, tag = site["base"], site["token"], site["tag"]
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, f"replay_{tag}_{window_days}d.json")
    if use_cache and os.path.exists(cache):
        with open(cache) as f: return json.load(f)
    now = int(time.time() * 1000); start = now - window_days * DAY_MS
    ds, we = [], now
    while we > start:
        ws = max(start, we - CHUNK_DAYS * DAY_MS)
        try:
            ds += _get(base, token, "devicestatus", {"count": 200000, "find[created_at][$gte]": _iso(ws), "find[created_at][$lte]": _iso(we)})
        except Exception as e:  # noqa: BLE001
            print(f"  [{tag}] chunk failed: {e}", flush=True)
        we = ws - 1
    seen, cyc = set(), []
    for d in ds:
        s = d.get("openaps", {}).get("suggested", {})
        ca = d.get("created_at", "")
        if "boostV5_state" not in s:
            continue
        try:
            ts = int(datetime.strptime(ca[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)
        except ValueError:
            continue
        if (ts, s.get("bg")) in seen:
            continue
        seen.add((ts, s.get("bg")))
        cyc.append({
            "ts": ts, "bg": s.get("bg"),
            "accl": s.get("deltaAcceleration"),
            "score": s.get("boostV5_score"), "state": s.get("boostV5_state"),
            "finalDose": s.get("boostV5_finalDose") or 0.0, "units": s.get("units") or 0.0,
            "sleep": (s.get("sleepState") == "SLEEPING"),
        })
    cyc.sort(key=lambda c: c["ts"])
    # derive 5-min delta from consecutive in-cadence cycles
    for i, c in enumerate(cyc):
        c["delta"] = None
        if i > 0 and c["bg"] and cyc[i - 1]["bg"]:
            dt = c["ts"] - cyc[i - 1]["ts"]
            if CYCLE_MS * 0.6 <= dt <= CYCLE_MS * 1.8:
                c["delta"] = c["bg"] - cyc[i - 1]["bg"]
    data = {"tag": tag, "cyc": cyc}
    with open(cache, "w") as f: json.dump(data, f)
    return data


def replay_candidate(cyc, dt_thresh, at_thresh, score_min=None, exclude_sleep=False):
    """Replay one threshold set. Returns dict of metrics."""
    n_meals_total = 0          # actual CONFIRMED transitions (fresh confirms)
    fires = {"true": 0, "false": 0, "sleep": 0}
    lead_cycles = []           # for true fires, cycles earlier than the actual confirm
    caught_meals = set()
    # index of fresh CONFIRMED transitions
    confirm_idx = [i for i in range(len(cyc))
                   if cyc[i]["state"] == "CONFIRMED" and (i == 0 or cyc[i - 1]["state"] != "CONFIRMED")]
    n_meals_total = len(confirm_idx)
    confirm_set = set(confirm_idx)

    for i, c in enumerate(cyc):
        if c["state"] not in ("IDLE", "OBSERVING"):
            continue
        if c["delta"] is None or c["accl"] is None:
            continue
        if exclude_sleep and c["sleep"]:
            continue
        if score_min is not None and (c["score"] is None or c["score"] < score_min):
            continue
        if c["delta"] >= dt_thresh and c["accl"] >= at_thresh:
            # candidate fast-path would fire here
            if c["sleep"]:
                fires["sleep"] += 1
            # does a real confirm follow within FOLLOW_CYCLES?
            nxt = [j for j in confirm_idx if i < j <= i + FOLLOW_CYCLES]
            if nxt:
                fires["true"] += 1
                j = nxt[0]
                lead_cycles.append(j - i)
                caught_meals.add(j)
            else:
                # also count as true-ish if BG kept rising strongly (sustained) even if state logic lagged
                if not c["sleep"]:
                    fires["false"] += 1
    return {
        "n_meals": n_meals_total,
        "fires": fires,
        "meals_caught_early": len(caught_meals),
        "median_lead_cycles": statistics.median(lead_cycles) if lead_cycles else 0,
        "lead_cycles": lead_cycles,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=30)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    with open(CONFIG_PATH) as f: cfg = json.load(f)

    all_cyc = []
    per_user = {}
    for site in cfg["sites"]:
        print(f"[{site['tag']}] loading {args.window_days}d ...", flush=True)
        try:
            data = load(site, args.window_days, use_cache=not args.no_cache)
        except Exception as e:  # noqa: BLE001
            print(f"  [{site['tag']}] FAILED: {e}", flush=True); continue
        per_user[site["tag"]] = data["cyc"]
        all_cyc.append((site["tag"], data["cyc"]))
        print(f"  [{site['tag']}] {len(data['cyc'])} V5 cycles", flush=True)

    # pooled candidate sweep
    print("\n=== candidate fast-path sweep (pooled) ===")
    sweep = {}
    for name, dt, at, smin, exsleep in CANDIDATES:
        agg = {"n_meals": 0, "true": 0, "false": 0, "sleep": 0, "caught": 0, "leads": [], "dt": dt, "at": at, "smin": smin, "exsleep": exsleep}
        for tag, cyc in all_cyc:
            r = replay_candidate(cyc, dt, at, smin, exsleep)
            agg["n_meals"] += r["n_meals"]; agg["true"] += r["fires"]["true"]
            agg["false"] += r["fires"]["false"]; agg["sleep"] += r["fires"]["sleep"]
            agg["caught"] += r["meals_caught_early"]; agg["leads"] += r["lead_cycles"]
        med = statistics.median(agg["leads"]) if agg["leads"] else 0
        sweep[name] = {**agg, "med_lead_min": med * 5,
                       "caught_pct": 100 * agg["caught"] / agg["n_meals"] if agg["n_meals"] else 0,
                       "fp_per_day": agg["false"] / (args.window_days * max(1, len(all_cyc)))}
        print(f"  {name:18s} Δ≥{dt},accl≥{at}{',score≥'+str(smin) if smin else ''}{',awake' if exsleep else ''}: "
              f"caught {agg['caught']}/{agg['n_meals']} ({sweep[name]['caught_pct']:.0f}%), "
              f"lead {med*5:.0f}min, false {agg['false']} ({sweep[name]['fp_per_day']:.2f}/day), sleep {agg['sleep']}")

    # ── PDF ──
    def srow(name):
        s = sweep[name]
        cond = f"Δ≥{s['dt']}, accl≥{s['at']}" + (f", score≥{s['smin']}" if s['smin'] else "") + (", awake" if s['exsleep'] else "")
        return (f"<tr><td>{name}<br><small>{cond}</small></td><td>{s['caught']}/{s['n_meals']} ({s['caught_pct']:.0f}%)</td>"
                f"<td>{s['med_lead_min']:.0f} min</td><td>{s['false']}</td><td>{s['fp_per_day']:.2f}/day</td><td>{s['sleep']}</td></tr>")
    rows = "".join(srow(n) for n, *_ in CANDIDATES)
    html = f"""<html><head><meta charset='utf-8'><style>
    @page {{ size:A4; margin:16mm; }} body {{ font-family:-apple-system,Arial,sans-serif; font-size:10.5pt; color:#1a1a1a; line-height:1.45; }}
    h1 {{ color:#0b3d91; font-size:18pt; border-bottom:2px solid #0b3d91; }} h2 {{ color:#0b3d91; font-size:13pt; }}
    table {{ border-collapse:collapse; width:100%; font-size:9.5pt; margin:8px 0; }}
    th {{ background:#0b3d91; color:#fff; padding:4px 6px; }} td {{ border:1px solid #cdd5e0; padding:3px 6px; text-align:center; }}
    td:first-child {{ text-align:left; }} em {{ color:#555; }} code {{ background:#eef1f6; padding:1px 4px; }}
    </style></head><body>
    <h1>Boost replay — fast-carb confirm fast-path</h1>
    <em>Method 2 (data-driven replay) of arXiv 2606.13882v1, on {args.window_days}d of NS history across
    {len(all_cyc)} users (anonymised). Generated by <code>replay.py</code>.</em>
    <h2>What this validates</h2>
    <p>V5's observe→confirm latency commits ~1 cycle late on fast carbs (the 2026-06-16 meal: dribbled 0.3U
    in OBSERVING at BG 120 while V1 would've dosed 1.7U; committed late → peak 185 then crash 54). The fix:
    promote OBSERVING→CONFIRMED in a single cycle when acceleration is extreme. The risk is false fires on
    compression / exercise. This replays candidate rules <code>delta ≥ Dt AND deltaAccl ≥ At</code> over real
    history and scores each firing as a real meal caught earlier vs a false positive.</p>
    <h2>Candidate threshold sweep (pooled)</h2>
    <table><tr><th>candidate</th><th>meals caught earlier</th><th>median lead</th><th>false fires</th><th>false rate</th><th>sleep fires</th></tr>{rows}</table>
    <p><em>"meals caught earlier" = of the real CONFIRMED meals, how many a fast-path fire preceded within
    {FOLLOW_CYCLES} cycles (so they'd commit sooner). "lead" = how much earlier. "false fires" = fires with no
    real meal in the next {FOLLOW_CYCLES} cycles (would commit on a non-meal). "sleep fires" should be ~0
    (compression risk). Pick the threshold that maximises lead + catch while keeping false/sleep fires low.</em></p>
    <h2>Reading it / next step</h2>
    <p>Looser thresholds catch more meals earlier but fire more falsely; tighter ones are safer but slower.
    The build decision: choose the knee of this tradeoff, implement it in <code>MealHypothesis.step()</code>
    (OBSERVING→CONFIRMED gate), then re-run this replay + the shadow-equivalence report to confirm. This is
    decision-gate replay; full glucose-outcome Parkes needs a physiologic model (Method 3).</p>
    </body></html>"""
    import weasyprint
    pdf = os.path.join(HERE, "Boost-Replay-FastCarb-2026-06-16.pdf")
    weasyprint.HTML(string=html).write_pdf(pdf)
    print(f"\nPDF: {pdf}")


if __name__ == "__main__":
    main()
