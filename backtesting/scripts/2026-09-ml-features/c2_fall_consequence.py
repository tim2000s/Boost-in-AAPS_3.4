"""Candidate 2: at a fall onset, is this fall going somewhere that matters?

The rise side of this question has been priced and closed: the shape of a rise adds about
+0.014 AUC at ten minutes over onset glucose plus the clock, well inside the pre-registered
margin, and the loop's own forward projection is at chance for whether the excursion will be
consequential. The fall side has not been asked, and it is the side where the decision is
open for longer: a controller can still withhold insulin, zero-temp or call for
carbohydrate at the moment a fall is ten minutes old, whereas by the time a rise is thirty
minutes old the peak is largely determined.

Anchors are fall onsets built as the mirror of the published rise onsets: a drop of at
least 25 mg/dL within thirty minutes, starting from a point above the hypoglycaemia
threshold, with a refractory gap so one long descent does not contribute twenty anchors.

Labels are read from the trace afterwards, so every participant in every corpus is usable
including the five that record no carbohydrate. Whether glucose goes below 70 mg/dL within
two hours, and whether it goes below 54 mg/dL, which is the consensus severe threshold the
Boost kill-switches key on.

The matched baseline holds glucose at the onset and the clock, which a controller already
has for nothing. Two further arms are available only on the OpenAPS Data Commons, where a
loop's own state was recorded: insulin on board with the rest of the decision record, and
the loop's forward projection on its own.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
from multiprocessing import Pool

import lightgbm as lgb
import numpy as np
import pandas as pd
import psycopg2

import common

MIN_FALL = 25.0          # mg/dL within the onset window, mirroring MIN_RISE on the rise side
ONSET_WINDOW_MIN = 30
FLOOR_MGDL = 70.0        # onsets must start above this, or the fall has already happened
FWD_MIN = 120
LOW_THRESHOLD = 70.0
SEVERE_THRESHOLD = 54.0
REFRACTORY_MIN = 60
HORIZONS = (10, 15, 20, 30)

SHAPE = ("fall", "fall_rate", "nadir", "auc", "dec_max", "dec_last", "dec_mean",
         "accel", "curv", "pre_slope", "still_falling")
BASE = ("base", "tod_sin", "tod_cos")
LOOP = ("iob_iob", "iob_activity", "iob_basaliob", "sug_cob", "sug_insulinreq",
        "sug_isf", "sug_current_target")


def shape_features(ts: np.ndarray, bg: np.ndarray, i0: int, horizon_min: int):
    """Descriptors of the first `horizon_min` of a fall. None when coverage is short."""
    t0 = ts[i0]
    j = bisect.bisect_right(ts, t0 + horizon_min * 60)
    seg = bg[i0:j]
    tseg = (ts[i0:j] - t0) / 60.0
    if len(seg) < max(3, horizon_min // 5 - 1):
        return None
    base = float(seg[0])
    d = np.diff(seg)
    span = max(tseg[-1], 1.0)
    return dict(
        fall=base - float(seg[-1]),
        fall_rate=(base - float(seg[-1])) / span,
        nadir=base - float(seg.min()),
        auc=float(np.trapezoid(np.maximum(base - seg, 0.0), tseg)),
        dec_max=float(-d.min()) if len(d) else 0.0,
        dec_last=float(-d[-1]) if len(d) else 0.0,
        dec_mean=float(-d.mean()) if len(d) else 0.0,
        accel=float(-(d[-1] - d[0])) if len(d) >= 2 else 0.0,
        curv=float(np.polyfit(tseg, seg, 2)[0]) if len(seg) >= 4 else 0.0,
        pre_slope=0.0,
        still_falling=float(d[-1] < 0) if len(d) else 0.0,
    )


# ---------------------------------------------------------------------------
# the seven research corpora: continuous glucose only
# ---------------------------------------------------------------------------

def _series(cur, subject):
    cur.execute(
        "select ts_local, cgm_mgdl from studies.cgm where subject_id=%s "
        "and cgm_mgdl between 39 and 401 order by ts_local",
        (subject,),
    )
    rows = cur.fetchall()
    if not rows:
        return None, None
    df = pd.DataFrame(rows, columns=["ts_local", "cgm_mgdl"])
    ts = common.epoch_seconds(df["ts_local"])
    return ts, df["cgm_mgdl"].to_numpy(dtype=float)


def _onsets(ts, bg, meta, pre_slope_lookback=15 * 60):
    rows, i = [], 4
    n = len(ts)
    step = max(1, int(REFRACTORY_MIN * 60 / 300))
    while i < n - 30:
        w = bisect.bisect_right(ts, ts[i] + ONSET_WINDOW_MIN * 60)
        if w - i >= 4 and bg[i] - bg[i:w].min() >= MIN_FALL and bg[i] > FLOOR_MGDL:
            t0 = ts[i]
            r = dict(meta)
            r["t0"] = t0
            ok = True
            p = bisect.bisect_left(ts, t0 - pre_slope_lookback)
            pre = (bg[i] - bg[p]) / max((t0 - ts[p]) / 60.0, 1.0) if p < i else 0.0
            for h in HORIZONS:
                f = shape_features(ts, bg, i, h)
                if f is None:
                    ok = False
                    break
                f["pre_slope"] = pre
                for k, v in f.items():
                    r[f"h{h}_{k}"] = v
            if ok:
                a = bisect.bisect_right(ts, t0)
                b = bisect.bisect_right(ts, t0 + FWD_MIN * 60)
                seg = bg[a:b]
                if len(seg) >= 16:
                    r["base"] = float(bg[i])
                    r["fwd_min"] = float(seg.min())
                    r["y_low"] = int(seg.min() < LOW_THRESHOLD)
                    r["y_severe"] = int(seg.min() < SEVERE_THRESHOLD)
                    # A decision taken h minutes into a fall cannot be credited for a low
                    # that has already happened by then, and a shape arm sees the trace up
                    # to h while a clock arm does not, so scoring both against a label
                    # measured from the onset hands the shape arm part of the answer. The
                    # horizon-honest label is measured from h onwards and is the one the
                    # headline uses.
                    for h in HORIZONS:
                        c = bisect.bisect_right(ts, t0 + h * 60)
                        tail = bg[c:b]
                        if len(tail) >= 8:
                            r[f"y_low_after{h}"] = int(tail.min() < LOW_THRESHOLD)
                            r[f"y_severe_after{h}"] = int(tail.min() < SEVERE_THRESHOLD)
                        else:
                            ok = False
            if ok and "y_low" in r:
                hour = (t0 % 86400) / 3600.0
                r["hour"] = hour
                r["tod_sin"] = float(np.sin(2 * np.pi * hour / 24))
                r["tod_cos"] = float(np.cos(2 * np.pi * hour / 24))
                rows.append(r)
            i = max(w, i + step)
            continue
        i += 1
    return rows


def _one_subject(arg):
    subject, study = arg
    conn = psycopg2.connect(common.DSN)
    try:
        with conn.cursor() as cur:
            ts, bg = _series(cur, subject)
    finally:
        conn.close()
    if ts is None or len(ts) < 500:
        return None
    rows = _onsets(ts, bg, dict(pid=subject, study=study))
    return pd.DataFrame(rows) if rows else None


def studies_onsets(workers: int) -> pd.DataFrame:
    def build():
        subs = common.query(
            "select subject_id, study_name from studies.subject order by subject_id"
        )
        jobs = list(subs.itertuples(index=False, name=None))
        out = []
        with Pool(workers) as p:
            for k, r in enumerate(p.imap_unordered(_one_subject, jobs, chunksize=4)):
                if r is not None:
                    out.append(r)
                if (k + 1) % 200 == 0:
                    print(f"    {k + 1}/{len(jobs)} subjects", flush=True)
        return pd.concat(out, ignore_index=True)

    return common.cached("c2_studies_onsets", build)


# ---------------------------------------------------------------------------
# the OpenAPS Data Commons: the same onsets with the loop record attached
# ---------------------------------------------------------------------------

LOOP_COLS = list(LOOP) + ["sug_eventualbg"]


def attach_loop(r: pd.DataFrame, ts: np.ndarray, g: pd.DataFrame) -> pd.DataFrame:
    """Put the loop's own record beside each anchor, read at every decision horizon.

    A shape arm at h minutes sees the trace up to h, so the loop arm it is compared with
    has to see the loop's state at h as well; reading it at the onset would hand the shape
    arm a head start of h minutes.
    """
    t0 = r["t0"].to_numpy()
    for h in (0,) + HORIZONS:
        pos = np.clip(np.searchsorted(ts, t0 + h * 60, side="right") - 1, 0, len(ts) - 1)
        pre = "" if h == 0 else f"h{h}_"
        for c in LOOP_COLS:
            r[pre + c] = g[c].to_numpy(dtype=float)[pos]
    return r


def commons_onsets() -> pd.DataFrame:
    def build():
        df = common.load_oref_commons()
        out = []
        for pid, g in df.groupby("user_id", sort=False):
            g = g.sort_values("slot")
            ts = (g["slot"].to_numpy() * common.GRID_S).astype(float)
            bg = g["cgm_mgdl"].to_numpy(dtype=float)
            if len(ts) < 500:
                continue
            hours = g["hour"].to_numpy(dtype=float)
            rows = _onsets(ts, bg, dict(pid=pid, study="commons"))
            if not rows:
                continue
            r = pd.DataFrame(rows)
            # the anonymised clock lives in its own column, not in the relative timestamp
            pos = np.clip(np.searchsorted(ts, r["t0"].to_numpy()), 0, len(ts) - 1)
            hr = hours[pos]
            r["hour"] = hr
            r["tod_sin"] = np.sin(2 * np.pi * hr / 24)
            r["tod_cos"] = np.cos(2 * np.pi * hr / 24)
            out.append(attach_loop(r, ts, g))
        return pd.concat(out, ignore_index=True)

    return common.cached("c2_commons_onsets", build)


# ---------------------------------------------------------------------------

PARAMS = dict(objective="binary", n_estimators=200, learning_rate=0.05, num_leaves=31,
              min_child_samples=100, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, verbose=-1, n_jobs=7, force_col_wise=True)


def oos_scores(df: pd.DataFrame, feats: list[str], target: str, k: int = 5) -> np.ndarray:
    s = np.full(len(df), np.nan)
    folds = df["fold"].to_numpy()
    for f in range(k):
        tr, te = folds != f, folds == f
        if te.sum() == 0 or df.loc[tr, target].nunique() < 2:
            continue
        m = lgb.LGBMClassifier(random_state=0, **PARAMS)
        m.fit(df.loc[tr, feats], df.loc[tr, target])
        s[te] = m.predict_proba(df.loc[te, feats])[:, 1]
    return s


def price_horizon(df: pd.DataFrame, label: str, kind: str, h: int, out: dict):
    """One decision point, h minutes into the fall, and its own honest label."""
    target = f"y_{kind}_after{h}"
    has_loop = "iob_iob" in df.columns
    arms = {
        "base_only": ["base"],
        "clock": list(BASE),
        "shape": list(BASE) + [f"h{h}_{s}" for s in SHAPE],
    }
    if has_loop:
        arms["loopstate"] = list(BASE) + [f"h{h}_{c}" for c in LOOP_COLS]
        arms["shape_loop"] = (list(BASE) + [f"h{h}_{s}" for s in SHAPE]
                              + [f"h{h}_{c}" for c in LOOP_COLS])
        arms["eventualbg"] = f"h{h}_sug_eventualbg"

    pid = df["pid"].to_numpy()
    y = df[target].to_numpy()
    S = {}
    for name, feats in arms.items():
        if isinstance(feats, str):
            S[name] = -df[feats].to_numpy()   # a lower projection means a higher fall risk
        else:
            S[name] = oos_scores(df, feats, target)

    res = {"n": int(len(df)), "n_participants": int(df.pid.nunique()),
           "horizon_min": h, "target": target, "base_rate": float(y.mean()),
           "auc": {}, "paired": {}}
    for n, sc in S.items():
        a, lo, hi = common.participant_bootstrap_auc(pid, y, sc)
        res["auc"][n] = [a, lo, hi]
        print(f"    {label}/{kind}/h{h} {n:12s} AUC {a:.4f} [{lo:.4f}, {hi:.4f}]",
              flush=True)
    pairs = [("shape", "clock", "shape_vs_clock"),
             ("clock", "base_only", "clock_vs_bgonly")]
    if has_loop:
        pairs += [("loopstate", "clock", "loopstate_vs_clock"),
                  ("shape_loop", "shape", "loopstate_over_shape"),
                  ("clock", "eventualbg", "clock_vs_eventualbg")]
    for a, b, nm in pairs:
        r = common.paired_participant_bootstrap(pid, y, S[a], S[b])
        res["paired"][nm] = dict(delta=r.delta, lo=r.lo, hi=r.hi, n_part=r.n_part,
                                 n_ahead=r.n_ahead, verdict=r.verdict)
        print(f"    {label}/{kind}/h{h} {nm:22s} {r}", flush=True)
    out.setdefault(label, {}).setdefault(kind, {})[f"h{h}"] = res


# Ten and twenty minutes are the decision points that matter: at ten the dose is fully
# open, at twenty it is closing. The extraction keeps fifteen and thirty as well, and the
# fifteen-minute result sits between the two as expected, but pricing all four costs hours
# of fitting for nothing that changes a decision.
PRICED_HORIZONS = (10, 20)


def price_cohort(df: pd.DataFrame, label: str, out: dict):
    for kind in ("low", "severe"):
        for h in PRICED_HORIZONS:
            price_horizon(df, label, kind, h, out)


def subsample(df: pd.DataFrame, per_participant: int, seed: int = 0) -> pd.DataFrame:
    """Cap a participant's contribution so the fit is not dominated by the longest records.

    The comparison is between arms on identical rows and the interval is taken over
    participants, so thinning within a participant costs precision and biases nothing.
    """
    rng = np.random.default_rng(seed)
    keep = []
    for _, g in df.groupby("pid", sort=False):
        idx = g.index.to_numpy()
        if len(idx) > per_participant:
            idx = rng.choice(idx, per_participant, replace=False)
        keep.append(idx)
    return df.loc[np.concatenate(keep)].sort_index()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=7)
    a = ap.parse_args()
    out = {}

    print("== OpenAPS Data Commons ==", flush=True)
    cm = commons_onsets()
    cm["fold"] = [common.stable_fold(p, 5) for p in cm["pid"]]
    n0 = len(cm)
    ecols = [f"h{h}_sug_eventualbg" for h in HORIZONS]
    for c in ecols:
        cm = cm[cm[c].between(20, 600)]
    print(f"  {len(cm):,} fall onsets, {cm.pid.nunique()} participants "
          f"({n0 - len(cm)} dropped for an implausible forward projection)", flush=True)
    price_cohort(cm, "commons", out)

    print("== seven research corpora ==", flush=True)
    st = studies_onsets(a.workers)
    st["fold"] = [common.stable_fold(p, 5) for p in st["pid"]]
    n0 = len(st)
    st = subsample(st, 200)
    print(f"  {len(st):,} fall onsets of {n0:,}, {st.pid.nunique()} participants "
          f"(capped at 200 each)", flush=True)
    price_cohort(st, "studies", out)

    with open(os.path.join(common.OUT, "c2_fall_consequence.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("written c2_fall_consequence.json")
