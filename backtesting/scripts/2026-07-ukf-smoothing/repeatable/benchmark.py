#!/usr/bin/env python3
"""
benchmark.py -- reproducible comparison of four CGM smoothers.

    python benchmark.py                          # Mode A synthetic, 20 seeds (default)
    python benchmark.py --mode synthetic --seeds 40 --days 3
    python benchmark.py --mode real --csv mydata.csv
    python benchmark.py --mode real --db         # local TimescaleDB (optional)

Deterministic: Mode A is seeded (numpy default_rng), so anyone cloning the repo
reproduces identical numbers with zero private data. Writes results.md + results.json.

ESTIMATOR QUALITY ONLY. No TIR / dosing / BG-outcome claim is made anywhere.

The two evaluation stances (documented, honest):
  * ONE-STEP-AHEAD prediction uses each smoother's CAUSAL (forward-only) estimate at
    t to predict the next raw reading -- fair to all four; penalizes lag AND
    noise-chasing. This is the two-sided metric available in BOTH modes.
  * GROUND-TRUTH curve RMSE (Mode A only) compares each smoother's actual SHIPPED
    output curve to known truth. For the v4 UKF that output includes the backward
    RTS pass (it uses data > t -- that is what a *smoother*, as opposed to a filter,
    does). tsunami has no RTS, so this metric is exactly where the v4-vs-tsunami
    architectural difference shows up.
"""

import os
import sys
import json
import math
import argparse

import numpy as np

import synthetic_cgm as sc
from smoothers import smooth_series, SMOOTHERS, selftest_v4

OUTDIR = os.path.dirname(os.path.abspath(__file__))


# ----------------------------------------------------------------------------
# metric helpers
# ----------------------------------------------------------------------------

def rmse(errs):
    errs = [e for e in errs if e == e]  # drop NaN
    if not errs:
        return float('nan')
    return math.sqrt(sum(e * e for e in errs) / len(errs))


def _reversals(seq):
    c, prev = 0, 0
    for i in range(len(seq) - 1):
        d = seq[i + 1] - seq[i]
        s = 1 if d > 0 else (-1 if d < 0 else 0)
        if s != 0 and prev != 0 and s != prev:
            c += 1
        if s != 0:
            prev = s
    return c


# ----------------------------------------------------------------------------
# per-series accumulation
# ----------------------------------------------------------------------------

class Acc:
    """Pooled accumulators for one smoother."""
    def __init__(self):
        self.onestep = []       # |pred - raw[t+1]|
        self.gt = []            # |offline - true|
        self.lag = []           # signed tracking offset (mg/dL) on fast transitions
        self.jit_var = []       # within-window variance in stable windows
        self.reversals = 0
        self.art_absorbed = []  # fraction of artifact dip absorbed (0=reject,1=follow)
        self.art_abserr = []    # |offline - true| at artifact samples


def accumulate_onestep(acc, ts, raw, out):
    lvl = out['level_online']
    rate = out['rate_online']
    M = len(ts)
    for t in range(1, M - 1):
        dt = (ts[t + 1] - ts[t]) / 60000.0
        dt_prev = (ts[t] - ts[t - 1]) / 60000.0
        # both the forward step AND the step the rate was formed from must be a sane
        # 5-min cadence: guards against sub-minute duplicate timestamps in real data
        # exploding any finite-difference velocity (mirrors the parent backtest).
        if not (1.0 <= dt <= 15.0) or not (1.0 <= dt_prev <= 15.0):
            continue
        pred = lvl[t] + rate[t] * dt
        acc.onestep.append(abs(pred - raw[t + 1]))


def accumulate_stable_and_lag(acc, ts, ref, out, slope_stable=0.3, slope_fast=2.0):
    """ref = the reference signal for slope windows: TRUE in mode A, raw in mode B.
    Jitter & lag are measured on the shipped offline curve."""
    lvl = out['level_offline']
    M = len(ts)
    # stable windows (jitter)
    w = 6
    k = 0
    while k + w <= M:
        span = (ts[k + w - 1] - ts[k]) / 60000.0
        if span <= 0:
            k += 1; continue
        slope = (ref[k + w - 1] - ref[k]) / span
        if abs(slope) < slope_stable:
            seg = lvl[k:k + w]
            mean = sum(seg) / w
            acc.jit_var.append(sum((v - mean) ** 2 for v in seg) / w)
            acc.reversals += _reversals(seg)
            k += w
        else:
            k += 1
    # fast-transition windows (lag = signed offset vs ref direction)
    w = 8
    k = 0
    while k + w <= M:
        span = (ts[k + w - 1] - ts[k]) / 60000.0
        if span <= 0:
            k += 1; continue
        slope = (ref[k + w - 1] - ref[k]) / span
        if abs(slope) > slope_fast:
            sgn = 1.0 if slope > 0 else -1.0
            offs = [sgn * (ref[k + j] - lvl[k + j]) for j in range(w)]
            acc.lag.append(sum(offs) / w)
            k += w
        else:
            k += 1


def accumulate_gt_and_artifacts(acc, true, is_artifact, raw, out):
    lvl = out['level_offline']
    M = len(true)
    for t in range(M):
        acc.gt.append(abs(lvl[t] - true[t]))
    for t in range(M):
        if is_artifact[t]:
            depth = true[t] - raw[t]   # raw dips below truth
            acc.art_abserr.append(abs(lvl[t] - true[t]))
            if depth > 5.0:            # only meaningful dips
                acc.art_absorbed.append((true[t] - lvl[t]) / depth)


# ----------------------------------------------------------------------------
# Mode A -- synthetic
# ----------------------------------------------------------------------------

def run_synthetic(seeds, n_days, noise_sd):
    accs = {name: Acc() for name in SMOOTHERS}
    total_samples = 0
    total_valid = 0
    total_art = 0
    for seed in range(seeds):
        d = sc.generate(seed, n_days=n_days, noise_sd=noise_sd)
        raw = d['raw']; true = d['true']; ts = d['ts']; art = d['is_artifact']
        valid = ~np.isnan(raw)
        total_samples += len(raw)
        total_valid += int(valid.sum())
        # valid-only chronological arrays (smoothers segment internally on time gaps)
        vts = ts[valid].tolist()
        vraw = raw[valid].tolist()
        vtrue = true[valid].tolist()
        vart = art[valid].tolist()
        total_art += int(np.sum(vart))
        for name in SMOOTHERS:
            out = smooth_series(name, vts, vraw)
            acc = accs[name]
            accumulate_onestep(acc, vts, vraw, out)
            accumulate_gt_and_artifacts(acc, vtrue, vart, vraw, out)
            accumulate_stable_and_lag(acc, vts, vtrue, out)
    meta = dict(seeds=seeds, n_days=n_days, noise_sd=noise_sd,
                total_samples=total_samples, total_valid=total_valid,
                total_artifacts=total_art)
    return accs, meta


# ----------------------------------------------------------------------------
# Mode B -- real (CSV or DB), no ground truth
# ----------------------------------------------------------------------------

def _parse_ts(s):
    s = s.strip()
    try:
        v = float(s)
        return v * 1000.0 if v < 1e12 else v  # seconds -> ms if needed
    except ValueError:
        pass
    import datetime
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M:%S%z", "%m/%d/%Y %H:%M"):
        try:
            return datetime.datetime.strptime(s, fmt).timestamp() * 1000.0
        except ValueError:
            continue
    raise ValueError(f"cannot parse timestamp: {s!r}")


def load_csv(path):
    import csv
    rows = []
    with open(path) as f:
        reader = csv.reader(f)
        header = next(reader)
        # locate columns
        cols = [c.strip().lower() for c in header]
        ti = next((i for i, c in enumerate(cols) if 'time' in c or 'ts' in c or 'date' in c), 0)
        gi = next((i for i, c in enumerate(cols) if 'gluc' in c or 'mgdl' in c or 'sgv' in c or 'bg' in c), 1)
        for r in reader:
            if len(r) <= max(ti, gi):
                continue
            try:
                rows.append((_parse_ts(r[ti]), float(r[gi])))
            except (ValueError, IndexError):
                continue
    rows.sort(key=lambda x: x[0])
    ts = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    return [("csv", ts, vals)]


def load_db():
    """Load every distinct user_id from the local boost_cgm table, relabelled to
    anonymous cohort tags U1..Un (no personal identifiers reach the output)."""
    import psycopg2
    conn = psycopg2.connect("dbname=oref")
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT user_id FROM boost_cgm ORDER BY user_id")
    user_ids = [r[0] for r in cur.fetchall()]
    series = []
    for i, uid in enumerate(user_ids, start=1):
        cur.execute(
            "SELECT extract(epoch from ts_utc)*1000.0, cgm_mgdl "
            "FROM boost_cgm WHERE user_id=%s ORDER BY ts_utc ASC", (uid,))
        rows = cur.fetchall()
        if not rows:
            continue
        ts = [float(r[0]) for r in rows]
        vals = [float(r[1]) for r in rows]
        series.append((f"U{i}", ts, vals))  # anonymous tag only
    cur.close(); conn.close()
    return series


def load_db_sensor(sensor_type):
    """Load every user on a given CGM sensor_type from the sensor-labelled
    oref_phase2_sites_v2 table, relabelled to anonymous tags U1..Un. For G7/One+
    the transmitter sends a single value (no separate filtered stream), so
    cgm_mgdl is the raw sensor signal. One+ shares G7 hardware/firmware and is
    reported as G7; there is no separate One+ label."""
    import psycopg2
    conn = psycopg2.connect("dbname=oref")
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT user_id FROM oref_phase2_sites_v2 "
                "WHERE sensor_type=%s ORDER BY user_id", (sensor_type,))
    user_ids = [r[0] for r in cur.fetchall()]
    series = []
    for i, uid in enumerate(user_ids, start=1):
        # DEDUP to one reading per 5-min bucket (last per bucket) -- the raw phase2 export
        # interleaves multiple upload streams (~1-min spacing), which the pipeline collapses
        # via floor(ts/300) elsewhere. Without this the series is a spurious sawtooth.
        cur.execute(
            "SELECT DISTINCT ON (floor(ts_utc_ms/300000)) ts_utc_ms, cgm_mgdl "
            "FROM oref_phase2_sites_v2 "
            "WHERE user_id=%s AND sensor_type=%s AND cgm_mgdl IS NOT NULL "
            "ORDER BY floor(ts_utc_ms/300000), ts_utc_ms DESC", (uid, sensor_type))
        rows = sorted(cur.fetchall(), key=lambda r: r[0])
        if not rows:
            continue
        ts = [float(r[0]) for r in rows]
        vals = [float(r[1]) for r in rows]
        series.append((f"U{i}", ts, vals))  # anonymous tag only
    cur.close(); conn.close()
    return series


def run_real(series):
    accs = {name: Acc() for name in SMOOTHERS}
    per_series = {}
    for (label, ts, vals) in series:
        local = {name: Acc() for name in SMOOTHERS}
        for name in SMOOTHERS:
            out = smooth_series(name, ts, vals)
            accumulate_onestep(local[name], ts, vals, out)
            accumulate_stable_and_lag(local[name], ts, vals, out)  # ref = raw
            accs[name].onestep.extend(local[name].onestep)
            accs[name].lag.extend(local[name].lag)
            accs[name].jit_var.extend(local[name].jit_var)
            accs[name].reversals += local[name].reversals
        per_series[label] = {name: rmse(local[name].onestep) for name in SMOOTHERS}
    return accs, per_series


# ----------------------------------------------------------------------------
# reporting
# ----------------------------------------------------------------------------

def _mean(xs):
    xs = [x for x in xs if x == x]
    return sum(xs) / len(xs) if xs else float('nan')


def fmt_pct(a, b):
    """% reduction of a below b (positive = a better/lower than b)."""
    if b == 0 or b != b:
        return "n/a"
    return f"{100 * (b - a) / b:+.1f}%"


def summarize_synthetic(accs, meta):
    return dict(
        ground_truth_rmse={n: rmse(accs[n].gt) for n in SMOOTHERS},
        onestep_rmse={n: rmse(accs[n].onestep) for n in SMOOTHERS},
        artifact_absorbed={n: _mean(accs[n].art_absorbed) for n in SMOOTHERS},
        artifact_abserr={n: _mean(accs[n].art_abserr) for n in SMOOTHERS},
        lag={n: _mean(accs[n].lag) for n in SMOOTHERS},
        jitter_var={n: _mean(accs[n].jit_var) for n in SMOOTHERS},
        reversals={n: accs[n].reversals for n in SMOOTHERS},
        meta=meta)


def render_synthetic(data):
    meta = data['meta']
    gt = data['ground_truth_rmse']
    os_ = data['onestep_rmse']
    base_gt = gt['persistence']
    base_os = os_['persistence']
    L = []
    A = L.append
    A("## Mode A -- SYNTHETIC (known ground truth)\n")
    A(f"Seeds: {meta['seeds']} x {meta['n_days']} days, sensor noise SD={meta['noise_sd']} mg/dL. "
      f"{meta['total_valid']} valid samples ({meta['total_samples']-meta['total_valid']} dropouts), "
      f"{meta['total_artifacts']} injected compression-artifact samples. "
      f"Regenerate identically with `--seeds {meta['seeds']} --days {meta['n_days']}`.\n")

    A("### Headline (lower = better)\n")
    A("| smoother | ground-truth RMSE (vs TRUE) | one-step RMSE (vs next raw) | GT %vs persist | 1-step %vs persist |")
    A("|----------|-----------------------------|-----------------------------|----------------|--------------------|")
    for n in SMOOTHERS:
        A(f"| {n} | {gt[n]:.3f} | {os_[n]:.3f} | {fmt_pct(gt[n], base_gt)} | {fmt_pct(os_[n], base_os)} |")
    A("")
    A("- Ground-truth RMSE is the cleanest statement: how far the shipped smoothed "
      "curve sits from the *actual* glucose. The v4 curve includes its RTS backward pass.\n")

    A("### Artifact handling (injected compression dips)\n")
    A("`absorbed fraction` = how much of each artifact dip the smoother followed "
      "(0.0 = fully rejected/held at truth, 1.0 = tracked the false dip). Lower is safer.\n")
    absorbed = data['artifact_absorbed']
    abserr = data['artifact_abserr']
    lag = data['lag']
    jit = data['jitter_var']
    A("| smoother | mean absorbed fraction | mean |err| at artifact (mg/dL) |")
    A("|----------|------------------------|-------------------------------|")
    for n in SMOOTHERS:
        A(f"| {n} | {absorbed[n]:.3f} | {abserr[n]:.2f} |")
    A("")

    A("### Lag & jitter\n")
    A("Lag = signed tracking offset on |true slope|>2 windows (mg/dL; + = trails the "
      "move). Jitter = within-window variance on |true slope|<0.3 windows (mg/dL^2; "
      "lower = smoother).\n")
    A("| smoother | lag offset (mg/dL) | jitter var (mg/dL^2) | reversals |")
    A("|----------|--------------------|-----------------------|-----------|")
    for n in SMOOTHERS:
        A(f"| {n} | {lag[n]:+.2f} | {jit[n]:.2f} | {data['reversals'][n]} |")
    A("")

    # explicit v4 vs tsunami
    A("### v4-UKF vs tsunami-UKF (the head-to-head)\n")
    A("| metric | v4 | tsunami | v4 improvement |")
    A("|--------|----|---------|----------------|")
    A(f"| ground-truth RMSE | {gt['v4']:.3f} | {gt['tsunami']:.3f} | {fmt_pct(gt['v4'], gt['tsunami'])} |")
    A(f"| one-step RMSE | {os_['v4']:.3f} | {os_['tsunami']:.3f} | {fmt_pct(os_['v4'], os_['tsunami'])} |")
    A(f"| artifact absorbed | {absorbed['v4']:.3f} | {absorbed['tsunami']:.3f} | "
      f"{fmt_pct(absorbed['v4'], absorbed['tsunami'])} |")
    A(f"| lag offset | {lag['v4']:+.2f} | {lag['tsunami']:+.2f} | "
      f"{fmt_pct(abs(lag['v4']), abs(lag['tsunami']))} |")
    A(f"| jitter var | {jit['v4']:.2f} | {jit['tsunami']:.2f} | "
      f"{fmt_pct(jit['v4'], jit['tsunami'])} |")
    A("")
    return "\n".join(L)


def summarize_real(accs, per_series, meta):
    return dict(
        onestep_rmse={n: rmse(accs[n].onestep) for n in SMOOTHERS},
        per_series=per_series,
        lag={n: _mean(accs[n].lag) for n in SMOOTHERS},
        jitter_var={n: _mean(accs[n].jit_var) for n in SMOOTHERS},
        reversals={n: accs[n].reversals for n in SMOOTHERS},
        meta=meta)


def render_real(data):
    os_ = data['onestep_rmse']
    per_series = data['per_series']
    lag = data['lag']
    jit = data['jitter_var']
    base = os_['persistence']
    L = []
    A = L.append
    A("## Mode B -- REAL CGM (no ground truth)\n")
    src = data['meta'].get('source', 'real')
    A(f"Source: {src}. Metrics available without truth: one-step-ahead predictive RMSE "
      "(vs next raw), lag (vs raw), jitter (vs raw stable windows). Cohort labels only.\n")
    A("### One-step-ahead predictive RMSE (pooled, mg/dL)\n")
    A("| smoother | one-step RMSE | %vs persistence |")
    A("|----------|---------------|-----------------|")
    for n in SMOOTHERS:
        A(f"| {n} | {os_[n]:.3f} | {fmt_pct(os_[n], base)} |")
    A("")
    A("### Per-series one-step RMSE\n")
    labels = list(per_series.keys())
    A("| series | " + " | ".join(SMOOTHERS) + " |")
    A("|--------|" + "|".join(["---"] * len(SMOOTHERS)) + "|")
    for lb in labels:
        A(f"| {lb} | " + " | ".join(f"{per_series[lb][n]:.3f}" for n in SMOOTHERS) + " |")
    A("")
    A("### Lag & jitter (vs raw)\n")
    A("| smoother | lag offset (mg/dL) | jitter var (mg/dL^2) | reversals |")
    A("|----------|--------------------|-----------------------|-----------|")
    for n in SMOOTHERS:
        A(f"| {n} | {lag[n]:+.2f} | {jit[n]:.2f} | {data['reversals'][n]} |")
    A("")
    return "\n".join(L)


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Four-way CGM smoother benchmark (estimator quality only).")
    ap.add_argument("--mode", choices=["synthetic", "real"], default="synthetic")
    ap.add_argument("--seeds", type=int, default=20, help="synthetic: number of seeds (default 20)")
    ap.add_argument("--days", type=int, default=3, help="synthetic: days per seed (default 3)")
    ap.add_argument("--noise-sd", type=float, default=6.0, help="synthetic: sensor noise SD mg/dL")
    ap.add_argument("--csv", type=str, default=None, help="real: path to timestamp,glucose_mgdl CSV")
    ap.add_argument("--db", action="store_true", help="real: use local TimescaleDB dbname=oref")
    ap.add_argument("--sensor", type=str, default=None,
                    help="real+--db: restrict to a CGM sensor_type from oref_phase2_sites_v2 "
                         "(e.g. G7 for the G7/One+ cohort); default uses boost_cgm (all sensors)")
    ap.add_argument("--no-selftest", action="store_true", help="skip the v4 parity self-test")
    args = ap.parse_args()

    # accumulate across invocations: load prior results.json so running synthetic then
    # real yields one comprehensive results.md with both sections.
    json_path = os.path.join(OUTDIR, "results.json")
    json_out = {}
    if os.path.exists(json_path):
        try:
            with open(json_path) as f:
                json_out = json.load(f)
        except (ValueError, OSError):
            json_out = {}

    if not args.no_selftest:
        print("=== v4 parity self-test (oracle: UnscentedKalmanFilterPluginTest.kt) ===")
        ok = selftest_v4()
        if not ok:
            print("PARITY FAILED -- aborting.")
            sys.exit(1)
        json_out['parity_pass'] = True

    if args.mode == "synthetic":
        print(f"\nRunning Mode A synthetic: {args.seeds} seeds x {args.days} days ...")
        accs, meta = run_synthetic(args.seeds, args.days, args.noise_sd)
        json_out['synthetic'] = summarize_synthetic(accs, meta)
    else:
        if args.csv:
            print(f"\nRunning Mode B real from CSV: {args.csv} ...")
            series = load_csv(args.csv)
            src = f"CSV {os.path.basename(args.csv)} ({len(series[0][1])} readings)"
        elif args.db:
            print("\nRunning Mode B real from TimescaleDB (dbname=oref) ...")
            try:
                if args.sensor:
                    series = load_db_sensor(args.sensor)
                else:
                    series = load_db()
            except Exception as e:
                print(f"DB unavailable ({e}). Provide --csv instead.")
                sys.exit(1)
            if args.sensor:
                src = f"local TimescaleDB oref_phase2_sites_v2 sensor={args.sensor} ({len(series)} users)"
            else:
                src = f"local TimescaleDB boost_cgm ({len(series)} cohort series)"
        else:
            print("Mode real requires --csv <file> or --db")
            sys.exit(1)
        accs, per_series = run_real(series)
        json_out['real'] = summarize_real(accs, per_series, dict(source=src))

    # render comprehensive markdown from whatever sections are present
    md_parts = ["# Four-way CGM smoother benchmark -- results\n",
                "Estimator quality ONLY. No TIR / dosing / BG-outcome claim is made.\n",
                "Smoothers: persistence (baseline), exponential (AAPS today), tsunami-UKF "
                "(v7-shadow), v4-UKF (forward UKF + backward RTS + chi-squared outlier).\n"]
    if json_out.get('parity_pass') is not None:
        md_parts.append(f"\n**v4 parity self-test:** {'PASS (9/9)' if json_out['parity_pass'] else 'FAIL'} "
                        "-- reproduces the 9 behaviours of UnscentedKalmanFilterPluginTest.kt.\n")
    if 'synthetic' in json_out:
        md_parts.append(render_synthetic(json_out['synthetic']))
    if 'real' in json_out:
        md_parts.append(render_real(json_out['real']))

    with open(os.path.join(OUTDIR, "results.md"), "w") as f:
        f.write("\n".join(md_parts) + "\n")
    with open(json_path, "w") as f:
        json.dump(json_out, f, indent=2)

    section = render_synthetic(json_out['synthetic']) if args.mode == 'synthetic' else render_real(json_out['real'])
    print("\n" + section)
    print(f"\nWrote results.md + results.json to {OUTDIR}")


if __name__ == "__main__":
    main()
