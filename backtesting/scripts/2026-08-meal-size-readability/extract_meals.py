#!/usr/bin/env python3
"""Build the meal table for the size-readability study.

One row per announced meal, from the JAEB `studies` corpus (Loop and REPLACE-BG, the two
releases that ship carbohydrate). The meal definition, the exclusions and the thirteen shape
features are taken unchanged from backtesting/scripts/2026-08-carb-signature/carb_signature.py
so that the replication arm is a replication and not a new study.

Added here, and absent there: clock time (admissible because the Loop de-identification offset
is a whole number of days), the bolus stratum for each meal, and participant-level scalars that
require no carbohydrate announcement.

No per-meal insulin quantity is written as a feature. Bolus timing is written to stratify on and
the bolus amount is deliberately not carried, because it is computed from the announced
carbohydrate through the participant's ratio and would return the label by arithmetic.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md
"""

import argparse
import bisect
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd
import psycopg2

# --- fixed by the protocol, and by the prior study it replicates -------------------------------
RESCUE_BG = 80.0         # carbohydrate entered at or below this is treated as a rescue
RESCUE_FALLING = -2.0    # or entered while falling this fast, in mg/dL per 5 min
MIN_CARB = 8.0
HORIZONS = (10, 15, 20, 30, 45, 60)
SMALL_G, LARGE_G = 20.0, 40.0
MEAL_SEPARATION_S = 90 * 60
ONSET_LOOKBACK_S = 30 * 60
EXCURSION_FWD_MIN = 180
BOLUS_WINDOW_MIN = 60

_CONN = None


def _connect():
    global _CONN
    if _CONN is None:
        _CONN = psycopg2.connect("dbname=oref")
        _CONN.autocommit = True
    return _CONN


def subjects_of(study):
    conn = _connect()
    with conn.cursor() as cur:
        cur.execute(
            "select subject_id, age_years from studies.subject where study_name=%s order by subject_id",
            (study,),
        )
        return cur.fetchall()


def _series(cur, table, col, subject):
    cur.execute(
        f"select extract(epoch from ts_local), {col} from studies.{table} "
        "where subject_id=%s order by ts_local",
        (subject,),
    )
    rows = cur.fetchall()
    if not rows:
        return np.empty(0), np.empty(0)
    a = np.asarray(rows, dtype=float)
    return a[:, 0], a[:, 1]


def shape_features(ts, bg, t0, horizon_min):
    """Everything computable from the sensor series between onset and onset + horizon.

    Byte-for-byte the prior study's function. Any change here breaks the replication.
    """
    a = bisect.bisect_right(ts, t0 - 20 * 60)
    m = bisect.bisect_right(ts, t0)
    b = bisect.bisect_right(ts, t0 + horizon_min * 60)
    if m - a < 3 or b - m < 2:
        return None
    pre, post = bg[a:m], bg[m:b]
    pt = ts[m:b]
    base = float(pre[-1])
    inc = np.diff(np.concatenate([[base], post]))
    mins = (pt - t0) / 60.0
    rise = float(post[-1] - base)
    auc_ = float(np.trapezoid(post - base, mins)) if len(post) > 1 else 0.0
    return dict(
        base=base,
        rise=rise,
        rise_rate=rise / max(horizon_min, 1) * 5.0,
        peak_so_far=float(post.max() - base),
        auc=auc_,
        inc_max=float(inc.max()) if len(inc) else 0.0,
        inc_last=float(inc[-1]) if len(inc) else 0.0,
        inc_mean=float(inc.mean()) if len(inc) else 0.0,
        accel=float(inc[-1] - inc[0]) if len(inc) > 1 else 0.0,
        curv=float(np.diff(inc).mean()) if len(inc) > 2 else 0.0,
        pre_slope=float(pre[-1] - pre[0]),
        still_rising=float(inc[-1] > 0),
    )


def total_daily_dose(bt, bu, rt, rr):
    """Participant scale, from insulin alone. Never a per-meal quantity.

    Basal is integrated from the rate step function; each rate runs until the next change. Gaps
    longer than a day are dropped rather than carried, since a step function says nothing about
    a period when the pump was not reporting.
    """
    if len(rt) < 2:
        return np.nan
    dt = np.diff(rt)
    keep = (dt > 0) & (dt <= 86400)
    if not keep.any():
        return np.nan
    basal_u = float(np.sum(rr[:-1][keep] * dt[keep] / 3600.0))
    span_s = float(np.sum(dt[keep]))
    bolus_u = float(np.sum(bu)) if len(bu) else 0.0
    days = span_s / 86400.0
    if days < 7:
        return np.nan
    # boluses are summed over the whole record; scale them onto the same covered span
    if len(bt) > 1:
        bolus_span = max(bt[-1] - bt[0], 1.0)
        bolus_u *= min(span_s / bolus_span, 1.0)
    return (basal_u + bolus_u) / days


def bolus_stratum(bt, t_entry):
    """Where the nearest bolus sits relative to the announcement."""
    if len(bt) == 0:
        return "none", np.nan
    i = bisect.bisect_left(bt, t_entry)
    cand = [j for j in (i - 1, i) if 0 <= j < len(bt)]
    if not cand:
        return "none", np.nan
    j = min(cand, key=lambda k: abs(bt[k] - t_entry))
    off_min = (bt[j] - t_entry) / 60.0
    if abs(off_min) > BOLUS_WINDOW_MIN:
        return "none", np.nan
    if off_min < -5:
        return "pre", off_min
    if off_min <= 5:
        return "at_meal", off_min
    if off_min <= 15:
        return "late_5_15", off_min
    return "late_gt15", off_min


def one_subject(arg):
    subject, age = arg
    conn = _connect()
    with conn.cursor() as cur:
        ts, bg = _series(cur, "cgm", "cgm_mgdl", subject)
        ct, cg = _series(cur, "carbs", "carbs_g", subject)
        bt, bu = _series(cur, "bolus", "bolus_u", subject)
        rt, rr = _series(cur, "basal", "rate_u_hr", subject)
    if len(ts) < 100 or len(ct) == 0:
        return None

    tdd = total_daily_dose(bt, bu, rt, rr)

    # participant scale that needs no announcement: the spread of every rise this person shows
    d = np.diff(bg)
    rises = d[d > 0]
    rise_p50 = float(np.percentile(rises, 50)) if len(rises) > 20 else np.nan
    rise_p90 = float(np.percentile(rises, 90)) if len(rises) > 20 else np.nan
    bg_p50 = float(np.percentile(bg, 50))
    bg_sd = float(np.std(bg))

    rows, used = [], []
    for t, g in zip(ct, cg):
        if not np.isfinite(g) or g < MIN_CARB:
            continue
        i = bisect.bisect_right(ts, t) - 1
        if i < 4 or i > len(ts) - 20:
            continue
        recent = bg[max(0, i - 3):i + 1]
        if bg[i] <= RESCUE_BG or (len(recent) > 1 and (recent[-1] - recent[0]) / 3 <= RESCUE_FALLING):
            continue
        if used and t - used[-1] < MEAL_SEPARATION_S:
            continue
        used.append(t)

        j = i
        while j > 0 and ts[i] - ts[j] < ONSET_LOOKBACK_S and bg[j] >= bg[j - 1]:
            j -= 1
        t0 = ts[j]

        row = dict(subject_id=subject, t0=t0, t_entry=t, carbs=float(g))
        ok = True
        for h in HORIZONS:
            f = shape_features(ts, bg, t0, h)
            if f is None:
                ok = False
                break
            for k, v in f.items():
                row[f"h{h}_{k}"] = v
        if not ok:
            continue

        a = bisect.bisect_right(ts, t0)
        b = bisect.bisect_right(ts, t0 + EXCURSION_FWD_MIN * 60)
        seg = bg[a:b]
        row["excursion"] = float(seg.max() - bg[j]) if len(seg) else np.nan

        strat, off = bolus_stratum(bt, t)
        row["bolus_stratum"] = strat
        row["bolus_offset_min"] = off

        hour = (t0 % 86400) / 3600.0
        row["hour"] = hour
        row["tod_sin"] = float(np.sin(2 * np.pi * hour / 24))
        row["tod_cos"] = float(np.cos(2 * np.pi * hour / 24))

        row["p_tdd"] = tdd
        row["p_age"] = float(age) if age is not None else np.nan
        row["p_rise_p50"] = rise_p50
        row["p_rise_p90"] = rise_p90
        row["p_bg_p50"] = bg_p50
        row["p_bg_sd"] = bg_sd
        rows.append(row)

    if not rows:
        return None
    df = pd.DataFrame(rows).sort_values("t0").reset_index(drop=True)

    # arm 3 history features: strictly earlier meals of this participant only
    c = df["carbs"].to_numpy()
    csum = np.concatenate([[0.0], np.cumsum(c)])
    n = np.arange(len(c))
    with np.errstate(invalid="ignore", divide="ignore"):
        df["h_prior_mean"] = np.where(n > 0, csum[:-1] / np.maximum(n, 1), np.nan)
    df["h_prior_median"] = df["carbs"].expanding().median().shift(1)
    df["h_prior_n"] = n
    # running rise-per-gram, from earlier meals only
    r = df["h30_rise"].to_numpy()
    num = np.concatenate([[0.0], np.cumsum(r)])
    df["h_prior_rise_per_g"] = np.where(csum[:-1] > 0, num[:-1] / np.maximum(csum[:-1], 1e-9), np.nan)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--studies", default="Loop,ReplaceBG")
    ap.add_argument("--workers", type=int, default=max(1, os.cpu_count() // 2))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    ap.add_argument("--limit-subjects", type=int, default=0, help="smoke run: cap subjects per study")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    t_start = time.time()
    for study in args.studies.split(","):
        subs = subjects_of(study)
        if args.limit_subjects:
            subs = subs[: args.limit_subjects]
        print(f"[{study}] {len(subs)} subjects, {args.workers} workers", flush=True)
        frames, done = [], 0
        with Pool(args.workers) as pool:
            for df in pool.imap_unordered(one_subject, subs, chunksize=4):
                done += 1
                if df is not None:
                    frames.append(df)
                if done % 100 == 0:
                    print(f"[{study}] {done}/{len(subs)} subjects, "
                          f"{sum(len(f) for f in frames):,} meals, "
                          f"{time.time() - t_start:.0f}s", flush=True)
        if not frames:
            print(f"[{study}] no meals", flush=True)
            continue
        out = pd.concat(frames, ignore_index=True)
        out["study"] = study
        out["size_class"] = np.where(out["carbs"] <= SMALL_G, 0,
                                     np.where(out["carbs"] >= LARGE_G, 1, -1))
        path = os.path.join(args.out, f"meals_{study}.parquet")
        out.to_parquet(path, index=False)
        print(f"[{study}] wrote {len(out):,} meals from {out.subject_id.nunique()} subjects "
              f"-> {path}", flush=True)
        print(out["bolus_stratum"].value_counts().to_string(), flush=True)
    print(f"done in {time.time() - t_start:.0f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
