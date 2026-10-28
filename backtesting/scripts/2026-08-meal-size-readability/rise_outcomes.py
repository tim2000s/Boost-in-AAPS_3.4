#!/usr/bin/env python3
"""At a rise onset, will the excursion be worth treating?

Detection answers whether food arrived and size answers how much, and neither is the question a
controller faces at the moment it must act. That question is whether this particular rise is going
somewhere that matters, and it has a property the other two lack: the answer is written in the
glucose trace afterwards, so it needs no announcement. Every participant in the corpus can be used,
including the five studies that ship no carbohydrate at all, which is 963 people previously
unusable for anything here.

Anchors are rise onsets built as the detection negatives were built, a rise of at least 25 mg/dL
within thirty minutes from a point above the hypoglycaemia threshold. That is approximately the set
of events a detector fires on, so the question asked of each one is the operational one: of the
roughly six firings a day, which warrant insulin.

Two labels, both read from the trace after the fact. The excursion label is whether the peak rise
over the onset baseline reaches 40 mg/dL within three hours. The absolute label is whether glucose
exceeds 180 mg/dL within two hours, which is closer to what a controller is actually trying to
prevent but is largely settled by where the rise started.

Baselines are the discipline here as everywhere. Glucose at the onset, on its own, already predicts
both labels to some degree, and the only quantity of interest is what the shape of the rise adds on
top of it.

Protocol: backtesting/protocols/2026-08_meal_size_readability_PREREG.md, extension.
"""

import argparse
import bisect
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

from extract_meals import RESCUE_BG, _connect, _series, shape_features

HORIZONS = (10, 15, 20, 30)
SHAPE = ("base", "rise", "rise_rate", "peak_so_far", "auc", "inc_max", "inc_last",
         "inc_mean", "accel", "curv", "pre_slope", "still_rising")
MIN_RISE = 25.0
EXCURSION_FWD_MIN = 180
ABSOLUTE_FWD_MIN = 120
EXCURSION_THRESHOLD = 40.0
ABSOLUTE_THRESHOLD = 180.0


def one_subject(arg):
    subject, study = arg
    conn = _connect()
    with conn.cursor() as cur:
        ts, bg = _series(cur, "cgm", "cgm_mgdl", subject)
    if len(ts) < 500:
        return None
    rows, i = [], 4
    while i < len(ts) - 40:
        w = bisect.bisect_right(ts, ts[i] + 30 * 60)
        if w - i >= 4 and bg[i:w].max() - bg[i] >= MIN_RISE and bg[i] > RESCUE_BG:
            t0 = ts[i]
            r = dict(subject_id=subject, study=study, t0=t0)
            ok = True
            for h in HORIZONS:
                f = shape_features(ts, bg, t0, h)
                if f is None:
                    ok = False
                    break
                for k, v in f.items():
                    r[f"h{h}_{k}"] = v
            if ok:
                a = bisect.bisect_right(ts, t0)
                b3 = bisect.bisect_right(ts, t0 + EXCURSION_FWD_MIN * 60)
                b2 = bisect.bisect_right(ts, t0 + ABSOLUTE_FWD_MIN * 60)
                seg3, seg2 = bg[a:b3], bg[a:b2]
                if len(seg3) >= 12 and len(seg2) >= 8:
                    r["peak_rise"] = float(seg3.max() - bg[i])
                    r["max_bg"] = float(seg2.max())
                    r["y_excursion"] = int(r["peak_rise"] >= EXCURSION_THRESHOLD)
                    r["y_absolute"] = int(r["max_bg"] > ABSOLUTE_THRESHOLD)
                    hour = (t0 % 86400) / 3600.0
                    r["hour"] = hour
                    r["tod_sin"] = float(np.sin(2 * np.pi * hour / 24))
                    r["tod_cos"] = float(np.cos(2 * np.pi * hour / 24))
                    rows.append(r)
            i = w + 12
            continue
        i += 1
    return pd.DataFrame(rows) if rows else None


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--out", default=os.path.join(here, "out"))
    ap.add_argument("--workers", type=int, default=max(1, os.cpu_count() // 2))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    conn = _connect()
    with conn.cursor() as cur:
        cur.execute("select subject_id, study_name from studies.subject order by subject_id")
        subs = cur.fetchall()
    if args.limit:
        subs = subs[: args.limit]
    print(f"{len(subs)} participants across 7 studies, {args.workers} workers", flush=True)

    t0 = time.time()
    frames, done = [], 0
    with Pool(args.workers) as pool:
        for df in pool.imap_unordered(one_subject, subs, chunksize=4):
            done += 1
            if df is not None:
                frames.append(df)
            if done % 200 == 0:
                print(f"  {done}/{len(subs)}, {sum(len(f) for f in frames):,} rises, "
                      f"{time.time() - t0:.0f}s", flush=True)
    out = pd.concat(frames, ignore_index=True)
    p = os.path.join(args.out, "rise_outcomes.parquet")
    out.to_parquet(p, index=False)
    print(f"\n{len(out):,} rise onsets from {out.subject_id.nunique()} participants -> {p}",
          flush=True)
    print(out.groupby("study").agg(rises=("t0", "size"),
                                   subjects=("subject_id", "nunique"),
                                   excursion_rate=("y_excursion", "mean"),
                                   absolute_rate=("y_absolute", "mean")).round(3).to_string(),
          flush=True)


if __name__ == "__main__":
    sys.exit(main())
