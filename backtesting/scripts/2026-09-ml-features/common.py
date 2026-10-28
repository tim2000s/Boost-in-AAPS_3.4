"""Shared loading and evaluation helpers for the 2026-09 ML feature pricing.

Two data sources are used.

The OpenAPS Data Commons (`public.oref_v5`, `oref_v6`, `oref_v7`) holds loop decision
records for 183 participants: what a controller actually computed, joined to the glucose
that followed. It carries insulin on board, the controller's own forward projection and
carbohydrate on board, which is the feature set Boost's shipped models use. Times are
anonymised to seconds relative to each participant's own start, with a separate hour-of-day
column, so the clock survives the anonymisation.

The seven public research corpora in the `studies` schema hold 1,807 participants of
continuous glucose, with insulin delivery for all of them and carbohydrate for two. No
controller state, so anything built there is trace-plus-insulin only.

Timestamp trap: on this pandas `ts.astype("int64") / 1e9` yields microseconds. Every
conversion here goes through `epoch_seconds`, which asserts the result is plausible.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd
import psycopg2

DSN = "dbname=oref host=127.0.0.1 port=5432"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

GRID_S = 300  # the five-minute grid every series is snapped to


def epoch_seconds(ts: pd.Series) -> np.ndarray:
    """Seconds since the epoch, with the microsecond trap asserted away."""
    s = (ts - pd.Timestamp("1970-01-01")).dt.total_seconds().to_numpy()
    finite = s[np.isfinite(s)]
    if finite.size:
        assert finite.max() > 1.0e9, f"epoch conversion looks wrong: max={finite.max()}"
    return s


def query(sql: str, params=None) -> pd.DataFrame:
    with psycopg2.connect(DSN) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def cached(name: str, builder):
    """Parquet-backed memo. Delete the file in cache/ to force a rebuild."""
    path = os.path.join(CACHE, f"{name}.parquet")
    if os.path.exists(path):
        return pd.read_parquet(path)
    df = builder()
    df.to_parquet(path, index=False)
    return df


# ---------------------------------------------------------------------------
# OpenAPS Data Commons
# ---------------------------------------------------------------------------

# The column that carries carbohydrate on board is quoted uppercase in oref_v5 and
# lowercase in v6 and v7, so it is resolved from information_schema rather than assumed.
_OREF_FIELDS = [
    "cgm_mgdl",
    "hour",
    "iob_iob",
    "iob_activity",
    "iob_basaliob",
    "iob_bolusiob",
    "sug_cob",
    "sug_eventualbg",
    "sug_insulinreq",
    "sug_isf",
    "sug_current_target",
    "sug_smb_units",
]


def _resolve_columns(table: str) -> dict[str, str]:
    cols = query(
        "select column_name from information_schema.columns "
        "where table_schema='public' and table_name=%s",
        (table,),
    )["column_name"].tolist()
    lower = {c.lower(): c for c in cols}
    return lower


def load_oref_commons() -> pd.DataFrame:
    """Every Commons decision record, snapped to a five-minute grid.

    One row per participant per grid slot; where a participant's loop ran faster than the
    grid the last record in the slot is kept, which is the one the following interval's
    outcome actually followed. `slot` is an integer index on the grid so lags and forward
    windows are simple arithmetic and gaps stay visible as missing slots.
    """

    def build():
        frames = []
        for table in ("oref_v5", "oref_v6", "oref_v7"):
            lower = _resolve_columns(table)
            sel = []
            for f in _OREF_FIELDS:
                if f in lower:
                    sel.append(f'"{lower[f]}" as {f}')
                else:
                    sel.append(f"null::double precision as {f}")
            sql = (
                f"select user_id, ts_relative_sec, {', '.join(sel)} from public.{table} "
                "where cgm_mgdl between 39 and 401"
            )
            df = query(sql)
            df["table"] = table
            frames.append(df)
        df = pd.concat(frames, ignore_index=True)
        df["slot"] = (df["ts_relative_sec"] // GRID_S).astype("int64")
        df = df.sort_values(["user_id", "slot", "ts_relative_sec"])
        df = df.drop_duplicates(["user_id", "slot"], keep="last")
        df = df.drop(columns=["ts_relative_sec"])
        for c in _OREF_FIELDS:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
        return df.reset_index(drop=True)

    return cached("oref_commons_grid", build)


def load_studies_cgm(study: str | None = None) -> pd.DataFrame:
    """Continuous glucose from the seven research corpora, on the same five-minute grid."""

    def build():
        where = "where c.cgm_mgdl between 39 and 401"
        params = None
        if study:
            where += " and s.study_name = %s"
            params = (study,)
        sql = (
            "select c.subject_id, s.study_name, c.ts_local, c.cgm_mgdl "
            "from studies.cgm c join studies.subject s using(subject_id) " + where
        )
        df = query(sql, params)
        sec = epoch_seconds(df["ts_local"])
        df["slot"] = (sec // GRID_S).astype("int64")
        df["hour"] = df["ts_local"].dt.hour.astype("int16")
        df = df.sort_values(["subject_id", "slot"]).drop_duplicates(
            ["subject_id", "slot"], keep="last"
        )
        df["cgm_mgdl"] = df["cgm_mgdl"].astype("float32")
        return df[["subject_id", "study_name", "slot", "hour", "cgm_mgdl"]].reset_index(
            drop=True
        )

    key = f"studies_cgm_grid_{study or 'all'}"
    return cached(key, build)


# ---------------------------------------------------------------------------
# Grid arithmetic
# ---------------------------------------------------------------------------


def reindex_to_grid(df: pd.DataFrame, group: str, value_cols: list[str]) -> dict:
    """Turn a long frame into per-participant dense arrays indexed by grid slot.

    Returns {participant: (slot0, {col: np.ndarray})}. Missing slots are NaN, which keeps
    a gap in the sensor feed from being silently read as a flat trace.
    """
    out = {}
    for pid, g in df.groupby(group, sort=False):
        s = g["slot"].to_numpy()
        s0, s1 = s.min(), s.max()
        n = int(s1 - s0 + 1)
        if n > 4_000_000:  # a participant with an implausible span
            continue
        idx = (s - s0).astype(np.int64)
        arrs = {}
        for c in value_cols:
            a = np.full(n, np.nan, dtype=np.float32)
            a[idx] = g[c].to_numpy(dtype=np.float32)
            arrs[c] = a
        out[pid] = (int(s0), arrs)
    return out


def forward_window_min(a: np.ndarray, start: int, end: int) -> np.ndarray:
    """Minimum of `a` over slots [i+start, i+end], NaN where the window is not covered."""
    return _forward_window(a, start, end, np.fmin.accumulate, np.nanmin)


def forward_window_max(a: np.ndarray, start: int, end: int) -> np.ndarray:
    return _forward_window(a, start, end, np.fmax.accumulate, np.nanmax)


def _forward_window(a, start, end, _acc, red):
    n = a.shape[0]
    width = end - start + 1
    # Sliding reduction via stride tricks; width is at most a few hundred slots here.
    pad = np.full(width, np.nan, dtype=np.float32)
    ext = np.concatenate([a, pad])
    win = np.lib.stride_tricks.sliding_window_view(ext, width)
    # win[i] covers ext[i : i+width]; we want a[i+start : i+end+1]
    res = np.full(n, np.nan, dtype=np.float32)
    valid = win[start : start + n]
    with np.errstate(invalid="ignore"):
        allnan = np.isnan(valid).all(axis=1)
        r = np.where(allnan, np.nan, red(np.where(np.isnan(valid), np.nan, valid), axis=1))
    res[:] = r[:n]
    return res


def coverage(a: np.ndarray, start: int, end: int) -> np.ndarray:
    """Fraction of slots present in the forward window, so partial windows can be dropped."""
    n = a.shape[0]
    width = end - start + 1
    ext = np.concatenate([a, np.full(width, np.nan, dtype=np.float32)])
    win = np.lib.stride_tricks.sliding_window_view(ext, width)
    present = (~np.isnan(win[start : start + n])).mean(axis=1)
    return present[:n].astype(np.float32)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def stable_fold(pid: str, k: int) -> int:
    """A participant's fold, fixed by a hash of the id so every arm sees the same split."""
    h = hashlib.md5(pid.encode()).hexdigest()
    return int(h, 16) % k


def auc(y: np.ndarray, s: np.ndarray) -> float:
    """Rank AUC. Returns NaN when one class is absent."""
    y = np.asarray(y).astype(bool)
    s = np.asarray(s, dtype=float)
    ok = np.isfinite(s)
    y, s = y[ok], s[ok]
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = pd.Series(s).rank().to_numpy()
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


# Bootstrapping AUC by resampling participants is the expensive step in every candidate
# here, and a naive re-rank of a million scores two thousand times over dominates the run.
# Scores are binned once into quantile bins and each participant's positive and negative
# counts per bin are held as a row of a matrix; a bootstrap draw is then a weighted column
# sum and the AUC follows from cumulative counts. Ties inside a bin are credited a half,
# which is the usual convention, and with four thousand bins the approximation is far below
# the width of any interval reported.

N_BINS = 4096


def _bin_scores(s: np.ndarray, n_bins: int = N_BINS) -> np.ndarray:
    finite = s[np.isfinite(s)]
    if finite.size == 0:
        return np.zeros(len(s), dtype=np.int32)
    q = np.unique(np.quantile(finite, np.linspace(0, 1, n_bins + 1)[1:-1]))
    b = np.searchsorted(q, s, side="left").astype(np.int32)
    b[~np.isfinite(s)] = -1
    return b


class _AucBooster:
    """Per-participant score histograms, ready for repeated resampling."""

    def __init__(self, pid, y, score, n_bins=N_BINS):
        b = _bin_scores(np.asarray(score, dtype=float), n_bins)
        ok = b >= 0
        self.parts, inv = np.unique(np.asarray(pid)[ok], return_inverse=True)
        yb = np.asarray(y).astype(bool)[ok]
        bb = b[ok]
        nb = int(bb.max()) + 1
        self.nb = nb
        flat = inv.astype(np.int64) * nb + bb
        size = len(self.parts) * nb
        self.pos = np.bincount(flat[yb], minlength=size).reshape(len(self.parts), nb)
        self.neg = np.bincount(flat[~yb], minlength=size).reshape(len(self.parts), nb)
        self.pos = self.pos.astype(np.float64)
        self.neg = self.neg.astype(np.float64)

    @staticmethod
    def _auc_from_counts(pos, neg):
        P, N = pos.sum(-1), neg.sum(-1)
        below = np.cumsum(neg, axis=-1) - neg
        num = ((below + 0.5 * neg) * pos).sum(-1)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where((P > 0) & (N > 0), num / (P * N), np.nan)

    def auc(self) -> float:
        return float(self._auc_from_counts(self.pos.sum(0), self.neg.sum(0)))

    def per_participant(self) -> np.ndarray:
        return self._auc_from_counts(self.pos, self.neg)

    def resampled(self, counts: np.ndarray) -> np.ndarray:
        return self._auc_from_counts(counts @ self.pos, counts @ self.neg)


def _draw_counts(n_parts, n_boot, rng):
    picks = rng.integers(0, n_parts, size=(n_boot, n_parts))
    counts = np.zeros((n_boot, n_parts), dtype=np.float64)
    for i in range(n_boot):
        counts[i] = np.bincount(picks[i], minlength=n_parts)
    return counts


@dataclass
class PairedResult:
    delta: float
    lo: float
    hi: float
    n_part: int
    n_ahead: int

    @property
    def verdict(self) -> str:
        if self.lo > 0:
            return "distinguishable, positive"
        if self.hi < 0:
            return "distinguishable, negative"
        return "UNPROVEN"

    def __str__(self):
        return (
            f"{self.delta:+.4f} [{self.lo:+.4f}, {self.hi:+.4f}] "
            f"ahead on {self.n_ahead}/{self.n_part} participants -- {self.verdict}"
        )


def paired_participant_bootstrap(
    pid: np.ndarray,
    y: np.ndarray,
    score_a: np.ndarray,
    score_b: np.ndarray,
    n_boot: int = 2000,
    seed: int = 0,
) -> PairedResult:
    """Bootstrap the paired AUC difference (a minus b) by resampling participants.

    Both arms are scored on exactly the same rows, so the difference is paired at the row
    level; the interval comes from resampling participants because rows within a
    participant are not independent.
    """
    pid = np.asarray(pid)
    y = np.asarray(y)
    ok = np.isfinite(np.asarray(score_a, float)) & np.isfinite(np.asarray(score_b, float))
    pid, y = pid[ok], y[ok]
    A = _AucBooster(pid, y, np.asarray(score_a, float)[ok])
    B = _AucBooster(pid, y, np.asarray(score_b, float)[ok])
    assert np.array_equal(A.parts, B.parts)
    point = A.auc() - B.auc()
    pa, pb = A.per_participant(), B.per_participant()
    ahead = int(np.nansum(pa > pb))
    rng = np.random.default_rng(seed)
    counts = _draw_counts(len(A.parts), n_boot, rng)
    deltas = A.resampled(counts) - B.resampled(counts)
    lo, hi = np.nanpercentile(deltas, [2.5, 97.5])
    return PairedResult(point, float(lo), float(hi), len(A.parts), ahead)


def participant_bootstrap_auc(pid, y, score, n_boot=2000, seed=0):
    """Point AUC with a participant-resampled interval."""
    A = _AucBooster(np.asarray(pid), np.asarray(y), np.asarray(score, float))
    rng = np.random.default_rng(seed)
    counts = _draw_counts(len(A.parts), n_boot, rng)
    vals = A.resampled(counts)
    lo, hi = np.nanpercentile(vals, [2.5, 97.5])
    return A.auc(), float(lo), float(hi)
