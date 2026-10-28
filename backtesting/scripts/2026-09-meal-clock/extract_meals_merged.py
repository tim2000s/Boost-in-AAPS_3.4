#!/usr/bin/env python3
"""Re-extract meals with split entries MERGED rather than discarded.

The readability extraction keeps the first entry of a cluster and skips anything within 90 minutes
of it, recording that first entry's grams as the meal. Measured against the raw table, that
discards 26 per cent of entries and 22 per cent of all carbohydrate, and for the 28 per cent of
meals that lose something the recorded size is a median 25 g against an actual 55 g occasion.

If the glucose trace responds to what was eaten, the model was being scored against a target that
understates a quarter of its cases by about half. That is a reason the size result might change,
and the only way to find out is to fix the target and re-run the identical model.

Everything else is held constant deliberately. The filters, the onset rule, the shape features, the
horizons and the participant features are imported from the original extraction rather than
reimplemented, so the only difference between the two parquets is how a meal's grams are counted.

Usage:
  python3 extract_meals_merged.py [--studies Loop,ReplaceBG] [--out out_merged]
  python3 ../2026-08-meal-size-readability/size_readability.py --data out_merged --study Loop \
      --arms 1,3,10,12
"""
from __future__ import annotations

import argparse
import bisect
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "2026-08-meal-size-readability")
sys.path.insert(0, SRC)
import extract_meals as em            # noqa: E402


def one_subject_merged(arg):
    """The original per-subject extraction, with one change: entries that fall inside the
    separation window are added to the meal they belong to instead of being dropped."""
    subject, age = arg
    conn = em._connect()
    with conn.cursor() as cur:
        ts, bg = em._series(cur, "cgm", "cgm_mgdl", subject)
        ct, cg = em._series(cur, "carbs", "carbs_g", subject)
        bt, bu = em._series(cur, "bolus", "bolus_u", subject)
        rt, rr = em._series(cur, "basal", "rate_u_hr", subject)
    if len(ts) < 100 or len(ct) == 0:
        return None

    tdd = em.total_daily_dose(bt, bu, rt, rr)
    d = np.diff(bg)
    rises = d[d > 0]
    rise_p50 = float(np.percentile(rises, 50)) if len(rises) > 20 else np.nan
    rise_p90 = float(np.percentile(rises, 90)) if len(rises) > 20 else np.nan
    bg_p50 = float(np.percentile(bg, 50))
    bg_sd = float(np.std(bg))

    # Pass one: keep the entries that clear the filters, with the index they were found at.
    # The rescue test is per entry and uses the glucose at that entry, so it has to happen
    # before any merging or a rescue would be folded into the meal beside it.
    keep = []
    for t, g in zip(ct, cg):
        if not np.isfinite(g) or g < em.MIN_CARB:
            continue
        i = bisect.bisect_right(ts, t) - 1
        if i < 4 or i > len(ts) - 20:
            continue
        recent = bg[max(0, i - 3):i + 1]
        if bg[i] <= em.RESCUE_BG or (len(recent) > 1
                                     and (recent[-1] - recent[0]) / 3 <= em.RESCUE_FALLING):
            continue
        keep.append((t, float(g), i))

    # Pass two: chain survivors that fall within the separation window and sum their grams.
    # The meal takes the FIRST entry's time and index, so onset and every shape feature are
    # computed at exactly the moment the original extraction would have used.
    meals = []
    for t, g, i in keep:
        if meals and t - meals[-1][0] < em.MEAL_SEPARATION_S:
            meals[-1][1] += g
            meals[-1][3] += 1
        else:
            meals.append([t, g, i, 1])

    rows = []
    for t, g, i, n_parts in meals:
        j = i
        while j > 0 and ts[i] - ts[j] < em.ONSET_LOOKBACK_S and bg[j] >= bg[j - 1]:
            j -= 1
        t0 = ts[j]

        row = dict(subject_id=subject, t0=t0, t_entry=t, carbs=float(g), n_parts=int(n_parts))
        ok = True
        for h in em.HORIZONS:
            f = em.shape_features(ts, bg, t0, h)
            if f is None:
                ok = False
                break
            for k, v in f.items():
                row[f"h{h}_{k}"] = v
        if not ok:
            continue

        a = bisect.bisect_right(ts, t0)
        b = bisect.bisect_right(ts, t0 + em.EXCURSION_FWD_MIN * 60)
        seg = bg[a:b]
        row["excursion"] = float(seg.max() - bg[j]) if len(seg) else np.nan

        strat, off = em.bolus_stratum(bt, t)
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
    c = df["carbs"].to_numpy()
    csum = np.concatenate([[0.0], np.cumsum(c)])
    n = np.arange(len(c))
    with np.errstate(invalid="ignore", divide="ignore"):
        df["h_prior_mean"] = np.where(n > 0, csum[:-1] / np.maximum(n, 1), np.nan)
    df["h_prior_median"] = df["carbs"].expanding().median().shift(1)
    df["h_prior_n"] = n
    r = df["h30_rise"].to_numpy()
    num = np.concatenate([[0.0], np.cumsum(r)])
    df["h_prior_rise_per_g"] = np.where(csum[:-1] > 0, num[:-1] / np.maximum(csum[:-1], 1e-9),
                                        np.nan)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--studies", default="Loop,ReplaceBG")
    ap.add_argument("--workers", type=int, default=max(1, os.cpu_count() // 2))
    ap.add_argument("--out", default=os.path.join(HERE, "out_merged"))
    ap.add_argument("--limit-subjects", type=int, default=0)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    t_start = time.time()
    for study in a.studies.split(","):
        subs = em.subjects_of(study)
        if a.limit_subjects:
            subs = subs[: a.limit_subjects]
        print(f"[{study}] {len(subs)} subjects, {a.workers} workers", flush=True)
        frames = []
        with Pool(a.workers) as pool:
            for df in pool.imap_unordered(one_subject_merged, subs, chunksize=4):
                if df is not None:
                    frames.append(df)
        if not frames:
            continue
        out = pd.concat(frames, ignore_index=True)
        out["study"] = study
        out["size_class"] = np.where(out["carbs"] <= em.SMALL_G, 0,
                                     np.where(out["carbs"] >= em.LARGE_G, 1, -1))
        path = os.path.join(a.out, f"meals_{study}.parquet")
        out.to_parquet(path, index=False)
        multi = out.n_parts > 1
        print(f"[{study}] {len(out):,} meals from {out.subject_id.nunique()} subjects -> {path}")
        print(f"   merged from more than one entry: {100*multi.mean():.0f}% of meals; "
              f"median size {out.carbs.median():.0f} g "
              f"(multi-entry meals {out.carbs[multi].median():.0f} g)")
        print(f"   size_class balance: {out.size_class.value_counts().to_dict()}")
    print(f"done in {time.time() - t_start:.0f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
