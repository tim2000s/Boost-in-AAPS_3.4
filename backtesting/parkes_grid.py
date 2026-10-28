#!/usr/bin/env python3
"""
Parkes (Consensus) Error Grid — Boost prediction accuracy.
================================================================================================
The paper (arXiv 2606.13882v1) uses the Parkes Error Grid in Method 2 (replay) to compare TWO
algorithm versions' resulting glucose. We don't have a replay harness yet, so this does the
legitimate Parkes analysis we CAN do from the timeseries:

    reference (x) = the BG that ACTUALLY occurred  (realized SGV at T + horizon)
    test      (y) = Boost's PREDICTED BG at that horizon  (predBGs.IOB[horizon], made at time T)

i.e. a Parkes grid of Boost's forward FORECAST accuracy — how clinically-safe the prediction the
dosing engine relies on actually is. Zone A = clinically accurate forecast; A+B = acceptable.

This is NOT the paper's two-version equivalence (that needs the replay harness / Method 2). It IS
a real Parkes grid on data we have, and a building block toward replay.

Parkes Type-1 zone boundaries are taken EXACTLY from Table 1 of Pfützner et al., "Technical
Aspects of the Parkes Error Grid", J Diabetes Sci Technol 2013;7(5):1275-1281 (x=reference,
y=test device, mg/dL). Type-1 grid is the regulatory/stricter version.

PRIVACY: same as the other backtesting scripts — URLs/tokens from $BOOST_BACKTEST_SITES (outside
repo), cache outside repo, outputs show only anonymous tags + aggregate stats + a scatter with no
identifying axis labels. Safe to commit.

USAGE: python3 parkes_grid.py [--window-days 14] [--horizon-min 30] [--no-cache]
Outputs: parkes_grid.png + Boost-Parkes-Error-Grid-<date>.pdf (and per-user zone table to stdout).
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

CONFIG_PATH = os.environ.get("BOOST_BACKTEST_SITES", os.path.expanduser("~/.config/boost_backtest/sites.json"))
CACHE_DIR = os.environ.get("BOOST_BACKTEST_CACHE", os.path.expanduser("~/.cache/boost_backtest"))
HERE = os.path.dirname(os.path.abspath(__file__))
CHUNK_DAYS, DAY_MS = 7, 86_400_000

# ── Parkes Type-1 boundaries (Pfützner 2013, Table 1). x=reference, y=test (mg/dL). ──
B_UP = [(0, 50), (30, 50), (140, 170), (280, 380), (430, 550)]
C_UP = [(0, 60), (30, 60), (50, 80), (70, 110), (260, 550)]
D_UP = [(0, 100), (25, 100), (50, 125), (80, 215), (125, 550)]
E_UP = [(0, 150), (35, 155), (50, 550)]
B_LO = [(50, 0), (50, 30), (170, 145), (385, 300), (550, 450)]
C_LO = [(120, 0), (120, 30), (260, 130), (550, 250)]
D_LO = [(250, 0), (250, 40), (550, 150)]
_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}


def _interp_y(pts, x):       # upper boundaries: y as f(x)
    if x <= pts[0][0]: return pts[0][1]
    if x >= pts[-1][0]: return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y1 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def _interp_x(pts, y):       # lower boundaries: x as f(y)  (handles the vertical start segment)
    if y <= pts[0][1]: return pts[0][0]
    if y >= pts[-1][1]: return pts[-1][0]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if y0 <= y <= y1:
            return x1 if y1 == y0 else x0 + (x1 - x0) * (y - y0) / (y1 - y0)
    return pts[-1][0]


def parkes_zone(ref, test):
    """Parkes T1 zone for reference=ref (x), test/predicted=test (y), both mg/dL."""
    z = "A"
    if test >= _interp_y(E_UP, ref):   return "E"
    elif test >= _interp_y(D_UP, ref): z = "D"
    elif test >= _interp_y(C_UP, ref): z = "C"
    elif test >= _interp_y(B_UP, ref): z = "B"
    # under-prediction side (no E zone on the lower side in T1)
    if ref >= _interp_x(D_LO, test):   z = max(z, "D", key=_ORDER.get)
    elif ref >= _interp_x(C_LO, test): z = max(z, "C", key=_ORDER.get)
    elif ref >= _interp_x(B_LO, test): z = max(z, "B", key=_ORDER.get)
    return z


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
            if i < attempts - 1: time.sleep(backoff); continue
            raise
    raise last


def _iso(ms): return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def load(site, window_days, use_cache):
    base, token, tag = site["base"], site["token"], site["tag"]
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, f"parkes_{tag}_{window_days}d.json")
    if use_cache and os.path.exists(cache):
        with open(cache) as f: return json.load(f)
    now = int(time.time() * 1000); start = now - window_days * DAY_MS
    ds, ent, we = [], [], now
    while we > start:
        ws = max(start, we - CHUNK_DAYS * DAY_MS)
        try:
            ds += _get(base, token, "devicestatus", {"count": 200000, "find[created_at][$gte]": _iso(ws), "find[created_at][$lte]": _iso(we)})
            ent += _get(base, token, "entries", {"count": 200000, "find[date][$gte]": int(ws), "find[date][$lte]": int(we)})
        except Exception as e:  # noqa: BLE001
            print(f"  [{tag}] chunk failed: {e}", flush=True)
        we = ws - 1
    sgv = sorted((int(e["date"]), float(e["sgv"])) for e in ent if e.get("sgv") and e.get("date"))
    preds = []
    for d in ds:
        s = d.get("openaps", {}).get("suggested", {})
        ca = d.get("created_at", "")
        try:
            ts = int(datetime.strptime(ca[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)
        except ValueError:
            continue
        pb = s.get("predBGs", {})
        iob = pb.get("IOB") if isinstance(pb, dict) else None
        if isinstance(iob, list) and len(iob) >= 7:
            preds.append({"ts": ts, "iob": iob})
    data = {"tag": tag, "sgv": sgv, "preds": preds}
    with open(cache, "w") as f: json.dump(data, f)
    return data


def realized_at(sgv, t_target, tol_ms=5 * 60_000):
    # nearest SGV within tolerance of t_target
    best = None; bestd = tol_ms + 1
    for ts, v in sgv:
        d = abs(ts - t_target)
        if d < bestd: bestd, best = d, v
        if ts > t_target + tol_ms: break
    return best if bestd <= tol_ms else None


def pairs_for(data, horizon_min):
    idx = horizon_min // 5
    out = []
    sgv = [(int(t), float(v)) for t, v in data["sgv"]]
    for p in data["preds"]:
        if len(p["iob"]) <= idx: continue
        pred = float(p["iob"][idx])
        real = realized_at(sgv, p["ts"] + horizon_min * 60_000)
        if real is None or pred <= 0 or real <= 0: continue
        out.append((real, pred))   # (reference=realized, test=predicted)
    return out


def zone_counts(pairs):
    c = {z: 0 for z in "ABCDE"}
    for ref, test in pairs:
        c[parkes_zone(ref, test)] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=14)
    ap.add_argument("--horizon-min", type=int, default=30)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    with open(CONFIG_PATH) as f: cfg = json.load(f)

    per_user, pooled = {}, []
    for site in cfg["sites"]:
        print(f"[{site['tag']}] loading {args.window_days}d ...", flush=True)
        try:
            data = load(site, args.window_days, use_cache=not args.no_cache)
        except Exception as e:  # noqa: BLE001
            print(f"  [{site['tag']}] FAILED: {e}", flush=True); continue
        pr = pairs_for(data, args.horizon_min)
        per_user[site["tag"]] = {"pairs": pr, "counts": zone_counts(pr)}
        pooled += pr
        n = len(pr); ab = sum(per_user[site['tag']]['counts'][z] for z in "AB")
        print(f"  [{site['tag']}] {n} paired predictions, A+B {100*ab/n:.1f}%" if n else f"  [{site['tag']}] no pairs", flush=True)

    # ── plot ──
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 7))
    for line in (B_UP, C_UP, D_UP, E_UP, B_LO, C_LO, D_LO):
        xs, ys = zip(*line); ax.plot(xs, ys, color="#888", lw=0.8)
    ax.plot([0, 550], [0, 550], "--", color="#444", lw=0.8)
    zc = {"A": "#2ca02c", "B": "#1f77b4", "C": "#ff7f0e", "D": "#d62728", "E": "#7b241c"}
    for ref, test in pooled:
        ax.plot(ref, test, ".", ms=2.0, alpha=0.35, color=zc[parkes_zone(ref, test)])
    for lbl, (x, y) in {"A": (250, 250), "B": (360, 250), "C": (110, 330), "D": (40, 330), "E": (15, 430)}.items():
        ax.text(x, y, lbl, fontsize=13, fontweight="bold", color="#333")
    ax.set_xlim(0, 450); ax.set_ylim(0, 450)
    ax.set_xlabel("Realized BG, mg/dL  (reference)"); ax.set_ylabel("Boost predicted BG, mg/dL  (test)")
    ax.set_title(f"Parkes Error Grid (Type 1) — Boost {args.horizon_min}-min forecast accuracy\n(pooled, anonymised; n={len(pooled)})")
    ax.set_aspect("equal")
    png = os.path.join(HERE, "parkes_grid.png")
    fig.savefig(png, dpi=140, bbox_inches="tight"); plt.close(fig)

    # ── PDF (grid + table + notes) via weasyprint ──
    pc = zone_counts(pooled); tot = len(pooled) or 1
    def row(tag, c):
        n = sum(c.values()) or 1
        return ("<tr><td>%s</td><td>%d</td>" % (tag, sum(c.values()))) + "".join(
            "<td>%.1f%%</td>" % (100 * c[z] / n) for z in "ABCDE") + ("<td><b>%.1f%%</b></td></tr>" % (100 * (c['A'] + c['B']) / n))
    rows = "".join(row(t, per_user[t]["counts"]) for t in per_user if per_user[t]["pairs"])
    rows += row("ALL (pooled)", pc)
    import base64
    b64 = base64.b64encode(open(png, "rb").read()).decode()
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d") if False else "2026-06-16"
    html = f"""<html><head><meta charset='utf-8'><style>
    @page {{ size:A4; margin:16mm; }} body {{ font-family:-apple-system,Arial,sans-serif; font-size:10.5pt; color:#1a1a1a; }}
    h1 {{ color:#0b3d91; font-size:18pt; border-bottom:2px solid #0b3d91; }} h2 {{ color:#0b3d91; font-size:13pt; }}
    table {{ border-collapse:collapse; width:100%; font-size:9.5pt; margin:8px 0; }}
    th {{ background:#0b3d91; color:#fff; padding:4px 6px; }} td {{ border:1px solid #cdd5e0; padding:3px 6px; text-align:center; }}
    td:first-child {{ text-align:left; }} em {{ color:#555; }} img {{ width:120mm; display:block; margin:6px auto; }}
    </style></head><body>
    <h1>Boost — Parkes Error Grid (forecast accuracy)</h1>
    <em>Parkes Consensus Error Grid, <b>Type 1</b> (Pfützner 2013, Table 1). Window {args.window_days} days,
    {args.horizon_min}-min horizon. Anonymised. Generated by <code>parkes_grid.py</code>.</em>
    <h2>What this is</h2>
    <p><b>Reference (x) = the BG that actually occurred</b> {args.horizon_min} min later; <b>test (y) = Boost's
    predicted BG</b> at that horizon (oref <code>predBGs.IOB</code>). So this grids Boost's forward-forecast
    accuracy — the prediction the dosing engine relies on. <b>Zone A</b> = clinically accurate; <b>A+B</b> = acceptable.</p>
    <p><em>This is NOT the paper's two-version equivalence (that needs the replay harness / Method 2). It is a
    real Parkes grid on data we have, and the building block toward replay. IOB-only forecast: during meals the
    COB/UAM curves carry extra rise the IOB curve omits, so expect some legitimate under-prediction on meal climbs.</em></p>
    <img src="data:image/png;base64,{b64}"/>
    <h2>Zone distribution ({args.horizon_min}-min)</h2>
    <table><tr><th>user</th><th>pairs</th><th>A</th><th>B</th><th>C</th><th>D</th><th>E</th><th>A+B</th></tr>{rows}</table>
    <p><em>A clinically-accurate predictor shows ≥95% in A (regulatory bar for BG meters); A+B is the common
    "acceptable" threshold. Read these as forecast quality, not meter accuracy.</em></p>
    </body></html>"""
    import weasyprint
    pdf = os.path.join(HERE, f"Boost-Parkes-Error-Grid-{date}.pdf")
    weasyprint.HTML(string=html).write_pdf(pdf)
    print(f"\nPNG: {png}\nPDF: {pdf}")
    print("\nPooled zones:", {z: f"{100*pc[z]/tot:.1f}%" for z in 'ABCDE'}, f"| A+B {100*(pc['A']+pc['B'])/tot:.1f}%")


if __name__ == "__main__":
    main()
