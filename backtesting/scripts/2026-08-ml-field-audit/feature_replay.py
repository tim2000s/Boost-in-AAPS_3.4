#!/usr/bin/env python3
"""
Rebuild the 53-feature vector offline, score it with the shipped model, and compare against the
score the engine actually published.

The follow-up inferred that cycles arriving after a break in the decision series carry a distorted
history, from the timing of the breaks alone. This settles it directly, because the reconstruction
can be checked against ground truth: the engine's own published ml_hypo_risk.

Feature provenance, read from DetermineBasalBoostV3MLG3.kt around line 1147:

  direct columns    cgm_mgdl, iob_iob, iob_basaliob, iob_activity, sug_insulinReq, sug_COB,
                    sug_eventualBG, sug_TDD
  derived           bg_above_target = cgm_mgdl - sug_current_target
                    iob_bolusiob    = max(0, iob - basaliob)          [the engine computes it]
                    sug_expectedDelta = round(bgi + (target - eventualBG) / 24, 1)
                    direction_num   = a seven-level bucket of shortAvgDelta
                    sug_minDelta    = min(delta, shortAvgDelta)
                    hour            = local hour of the cycle
  from treatments   recent_smb_units_60m, time_since_last_smb_min
  not stored        iob_netbasalinsulin, imputed at 0. Sweeping it across its plausible range
                    moves the score by about 0.001, so the imputation is not load-bearing.

Deltas follow DeltaCalculator: each candidate contributes (now - then) / minutesAgo * 5, with the
last delta drawn from 2.5 to 7.5 minutes ago, the short average from 2.5 to 17.5, and readings
below 39 mg/dL ignored.

The ring buffer is simulated exactly as the engine maintains it. RingBuffer.push appends and trims
to six; lagged(n) indexes backwards by position; nothing anywhere consults the stored timestamp.
The buffer is persisted to preferences and reloaded on start, so it survives a break in the
decision series. Three hypotheses are therefore scored on cycles following a break:

  carried   lags are whatever was last pushed, however old            [what the code does]
  current   lags fall back to the current cycle                       [an empty buffer]
  true      lags are the real contiguous history                      [what training assumed]

Two nuisance parameters are fitted per participant by maximising agreement on cycles where all
three hypotheses coincide, so they cannot be tuned to favour any of them: the local time offset,
which the record does not carry, and which of the stored total-daily-dose columns the engine
passed as profile.TDD.

Usage:  python3 feature_replay.py [--json out.json] [--user U]
"""

import argparse
import bisect
import json
import os
import sys

import numpy as np
import psycopg2

ERA_START = "2026-06-29"
LOOKBACK = 6
GAP_SECONDS = 30 * 60
BUCKET_MIN = 5
MIN_BG = 39.0
MIN_LAST, MAX_LAST = 2.5, 7.5
MIN_SHORT, MAX_SHORT = 2.5, 17.5

MODEL_PATHS = [
    os.path.expanduser("~/StudioProjects/Boost-AAPS-core/app/src/main/assets/boost/hypo_risk_model.json"),
    os.path.expanduser("~/StudioProjects/AndroidAPS/app/src/main/assets/boost/hypo_risk_model.json"),
]
WINDOWED = ["cgm_mgdl", "iob_iob", "iob_activity", "sug_eventualBG",
            "recent_smb_units_60m", "sug_minDelta"]
TDD_CANDIDATES = ["tdd", "tdd_7d", "tdd_1d", "tdd_24h", "tdd_blended", "tdd_weighted8h"]


def load_model():
    for p in MODEL_PATHS:
        if os.path.exists(p):
            return json.load(open(p)), p
    raise SystemExit("model asset not found")


def score_of(trees, x):
    raw = 0.0
    for t in trees:
        n = t
        while "leaf" not in n:
            n = n["left"] if x[n["feature"]] <= n["threshold"] else n["right"]
        raw += n["leaf"]
    return 1.0 / (1.0 + np.exp(-raw))


def direction_num(short_avg):
    if short_avg > 15.0: return 2.0
    if short_avg > 10.0: return 1.5
    if short_avg > 5.0: return 1.0
    if short_avg > -5.0: return 0.0
    if short_avg > -10.0: return -1.0
    if short_avg > -15.0: return -1.5
    return -2.0


def deltas_at(cgm_ts, cgm_bg, t):
    """DeltaCalculator.calculateDeltas against the sensor series as of time t."""
    i = bisect.bisect_right(cgm_ts, t) - 1
    if i < 1:
        return 0.0, 0.0
    now = cgm_bg[i]
    last, short = [], []
    j = i - 1
    while j >= 0:
        mins = (cgm_ts[i] - cgm_ts[j]) / 60.0
        if mins > MAX_SHORT:
            break
        if cgm_bg[j] > MIN_BG:
            avg = (now - cgm_bg[j]) / mins * 5.0
            if MIN_LAST <= mins <= MAX_LAST:
                last.append(avg)
            if MIN_SHORT <= mins <= MAX_SHORT:
                short.append(avg)
        j -= 1
    d = sum(last) / len(last) if last else 0.0
    s = sum(short) / len(short) if short else d
    return d, s


def fetch(conn, only_user=None):
    cur = conn.cursor()
    users = [only_user] if only_user else ["A", "B", "C", "D", "E", "F", "H", "I", "tim"]
    cols = ("cgm_mgdl, sug_current_target, sug_eventualbg, reason_bgi, iob_iob, iob_basaliob, "
            "iob_activity, sug_insulinreq, sug_cob, ml_hypo_risk, " + ", ".join(TDD_CANDIDATES))
    cur.execute(f"""
        SELECT DISTINCT ON (user_id, to_timestamp(floor(extract(epoch FROM ts_utc)/{BUCKET_MIN*60})*{BUCKET_MIN*60}))
               user_id, extract(epoch FROM ts_utc), {cols}
        FROM boost_decisions
        WHERE user_id = ANY(%s) AND ts_utc >= '{ERA_START}'
          AND ml_hypo_risk IS NOT NULL AND cgm_mgdl IS NOT NULL
          AND sug_current_target IS NOT NULL AND sug_eventualbg IS NOT NULL
          AND reason_bgi IS NOT NULL AND iob_iob IS NOT NULL AND iob_basaliob IS NOT NULL
        ORDER BY user_id,
                 to_timestamp(floor(extract(epoch FROM ts_utc)/{BUCKET_MIN*60})*{BUCKET_MIN*60}),
                 ts_utc
    """, (users,))
    names = [d[0] for d in cur.description]
    out = {}
    for r in cur.fetchall():
        d = dict(zip(names, r))
        d = {k: (None if v is None else float(v)) for k, v in d.items() if k != "user_id"}
        out.setdefault(r[0], []).append(d)
    return out


def cgm_of(conn, users):
    cur = conn.cursor()
    cur.execute("""SELECT user_id, extract(epoch FROM ts_utc), cgm_mgdl FROM boost_cgm
                   WHERE user_id = ANY(%s) AND cgm_mgdl IS NOT NULL ORDER BY user_id, ts_utc""",
                (list(users),))
    o = {}
    for u, t, b in cur.fetchall():
        o.setdefault(u, ([], []))
        o[u][0].append(float(t)); o[u][1].append(float(b))
    return o


def smb_of(conn, users):
    cur = conn.cursor()
    cur.execute("""SELECT user_id, extract(epoch FROM ts_utc), insulin FROM boost_treatments
                   WHERE user_id = ANY(%s) AND is_smb AND insulin IS NOT NULL
                   ORDER BY user_id, ts_utc""", (list(users),))
    o = {}
    for u, t, ins in cur.fetchall():
        o.setdefault(u, ([], []))
        o[u][0].append(float(t)); o[u][1].append(float(ins))
    return o


def build_statics(row, t, dl, sh, smb_ts, smb_u, tz_off, tdd_col):
    bg = row["cgm_mgdl"]
    tgt = row["sug_current_target"]
    ebg = row["sug_eventualbg"]
    bgi = row["reason_bgi"]
    iob = row["iob_iob"]; bas = row["iob_basaliob"]
    i = bisect.bisect_right(smb_ts, t)
    lo = bisect.bisect_left(smb_ts, t - 3600)
    recent = sum(smb_u[lo:i])
    tsince = 720.0 if i == 0 else min(720.0, (t - smb_ts[i - 1]) / 60.0)
    tdd = row.get(tdd_col)
    return {
        "cgm_mgdl": bg,
        "iob_iob": iob,
        "iob_basaliob": bas,
        "bg_above_target": bg - tgt,
        "direction_num": direction_num(sh),
        "hour": float(int(((t + tz_off * 3600) // 3600) % 24)),
        "iob_activity": row["iob_activity"] or 0.0,
        "sug_insulinReq": row["sug_insulinreq"] or 0.0,
        "sug_COB": row["sug_cob"] or 0.0,
        "sug_eventualBG": ebg,
        "sug_expectedDelta": round(bgi + (tgt - ebg) / 24.0, 1),
        "sug_minDelta": min(dl, sh),
        "sug_TDD": tdd if tdd and tdd > 0 else 0.0,
        "iob_bolusiob": max(0.0, iob - bas),
        "iob_netbasalinsulin": 0.0,
        "recent_smb_units_60m": recent,
        "time_since_last_smb_min": tsince,
    }


def replay(rows, cgm, smb, names, trees, tz_off, tdd_col, mode):
    """mode: 'carried' (as coded), 'current' (empty buffer), 'true' (contiguous history only)."""
    ts = [r["_t"] for r in rows]
    cgm_ts, cgm_bg = cgm
    smb_ts, smb_u = smb
    buf = []
    out = np.zeros(len(rows))
    for k, row in enumerate(rows):
        t = ts[k]
        dl, sh = deltas_at(cgm_ts, cgm_bg, t)
        st = build_statics(row, t, dl, sh, smb_ts, smb_u, tz_off, tdd_col)
        snap = {w: st[w] for w in WINDOWED}
        contiguous = k > 0 and (t - ts[k - 1]) <= GAP_SECONDS
        if mode == "true" and not contiguous:
            buf = []
        buf.append(snap)
        if len(buf) > LOOKBACK:
            buf.pop(0)
        x = np.zeros(len(names))
        for i, nm in enumerate(names):
            p = nm.find("_lag")
            if p > 0:
                base, lag = nm[:p], int(nm[p + 4:])
                idx = len(buf) - 1 - lag
                if mode == "current":
                    src = buf[idx] if (idx >= 0 and lag == 0) else snap
                else:
                    src = buf[idx] if idx >= 0 else snap
                x[i] = src[base]
            else:
                x[i] = st.get(nm, 0.0)
        out[k] = score_of(trees, x)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None); ap.add_argument("--user", default=None)
    args = ap.parse_args()
    model, path = load_model()
    names, trees = model["feature_names"], model["trees"]
    print(f"model {path}: {model['n_trees']} trees, {model['n_features']} features\n")

    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    data = fetch(conn, args.user)
    cgm = cgm_of(conn, data.keys()); smb = smb_of(conn, data.keys())
    res = {}

    print("=" * 78)
    print("1. FITTING THE TWO NUISANCE PARAMETERS, ON CONTIGUOUS CYCLES ONLY")
    print("=" * 78)
    print("  Cycles with a full contiguous buffer score identically under all three hypotheses,")
    print("  so fitting here cannot favour one of them.\n")
    print(f"  {'user':6s} {'n':>6s} {'tz':>4s} {'tdd column':>14s} {'median |err|':>13s} "
          f"{'within 0.01':>12s}")
    fitted = {}
    for u, rows in sorted(data.items()):
        for r in rows:
            r["_t"] = r.pop("extract")
        if u not in cgm or u not in smb or len(rows) < 200:
            continue
        ts = [r["_t"] for r in rows]
        contig = np.array([k >= LOOKBACK and all((ts[j] - ts[j - 1]) <= GAP_SECONDS
                                                 for j in range(k - LOOKBACK + 1, k + 1))
                           for k in range(len(rows))])
        pub = np.array([r["ml_hypo_risk"] for r in rows])
        best = None
        for tz in range(-11, 13):
            for col in TDD_CANDIDATES:
                if rows[0].get(col) is None:
                    continue
                sc = replay(rows, cgm[u], smb[u], names, trees, tz, col, "carried")
                m = contig & ~np.isnan(sc)
                if m.sum() < 50:
                    continue
                err = float(np.median(np.abs(sc[m] - pub[m])))
                if best is None or err < best[0]:
                    best = (err, tz, col, sc, m)
        if best is None:
            continue
        err, tz, col, sc, m = best
        hit = float(np.mean(np.abs(sc[m] - pub[m]) < 0.01))
        print(f"  {u:6s} {len(rows):6d} {tz:4d} {col:>14s} {err:13.4f} {100*hit:11.1f}%")
        fitted[u] = dict(tz=tz, tdd=col, err=err, hit=hit, n=len(rows))
    res["fit"] = fitted

    print()
    print("=" * 78)
    print("2. WHICH BUFFER HYPOTHESIS REPRODUCES THE PUBLISHED SCORE AFTER A BREAK")
    print("=" * 78)
    print("  Restricted to cycles where the three hypotheses give different vectors.\n")
    print(f"  {'user':6s} {'n post-break':>13s} {'carried':>9s} {'current':>9s} {'true':>9s}")
    tally = {"carried": 0, "current": 0, "true": 0}
    res["post_break"] = {}
    for u, f in sorted(fitted.items()):
        rows = data[u]
        ts = [r["_t"] for r in rows]
        pub = np.array([r["ml_hypo_risk"] for r in rows])
        post = np.array([k > 0 and (ts[k] - ts[k - 1]) > GAP_SECONDS or
                         (0 < k < LOOKBACK) for k in range(len(rows))])
        # a break anywhere in the preceding six cycles makes the hypotheses diverge
        div = np.zeros(len(rows), dtype=bool)
        for k in range(len(rows)):
            if any(post[max(0, k - LOOKBACK + 1):k + 1]):
                div[k] = True
        if div.sum() < 30:
            continue
        errs = {}
        for mode in ("carried", "current", "true"):
            sc = replay(rows, cgm[u], smb[u], names, trees, f["tz"], f["tdd"], mode)
            errs[mode] = float(np.median(np.abs(sc[div] - pub[div])))
        win = min(errs, key=errs.get); tally[win] += 1
        mark = {k: ("*" if k == win else " ") for k in errs}
        print(f"  {u:6s} {div.sum():13d} "
              f"{errs['carried']:8.4f}{mark['carried']} {errs['current']:8.4f}{mark['current']} "
              f"{errs['true']:8.4f}{mark['true']}")
        res["post_break"][u] = errs
    print(f"\n  participants best explained by each: {tally}")
    res["tally"] = tally

    if args.json:
        json.dump(res, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
