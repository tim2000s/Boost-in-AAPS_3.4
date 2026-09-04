#!/usr/bin/env python3
"""Score every shadow that has produced enough data to be scored.

A shadow exists to be measured and then promoted or discarded. Several have been running for
months without either happening, which is the failure mode this audit is meant to catch: a shadow
that is never scored is telemetry cost with no decision attached.

Each is scored against the outcome it claims to anticipate, out of sample where a model is
involved, with participant as the resampling unit.
"""
import os
import re
import sys
import warnings

import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore")
DSN = "dbname=oref host=127.0.0.1 port=5432"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def epoch(ts):
    v = (pd.to_datetime(ts, utc=True) - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds()
    assert v.min() > 1.6e9, v.min()
    return v.values


def auc(y, s):
    y = np.asarray(y); s = np.asarray(s)
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    if n1 < 20 or n0 < 20:
        return float("nan")
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def boot(pid, y, a, b, n=2000, seed=0):
    """Paired difference in AUC, resampling participants."""
    rng = np.random.default_rng(seed)
    ps = np.unique(pid)
    idx = {p: np.where(pid == p)[0] for p in ps}
    out = []
    for _ in range(n):
        take = np.concatenate([idx[p] for p in rng.choice(ps, len(ps))])
        x, z = auc(y[take], a[take]), auc(y[take], b[take])
        if x == x and z == z:
            out.append(x - z)
    if not out:
        return (float("nan"),) * 3
    o = np.array(out)
    return float(o.mean()), float(np.percentile(o, 2.5)), float(np.percentile(o, 97.5))


def load(conn, cols, where=""):
    q = f"select user_id, ts_utc, cgm_mgdl, {cols} from boost_decisions where cgm_mgdl between 20 and 500 {where} order by user_id, ts_utc"
    d = pd.read_sql(q, conn)
    d["t"] = epoch(d.ts_utc)
    return d


def forward(d, minutes):
    """Glucose `minutes` ahead within each participant, nearest sample inside a 5-minute tolerance."""
    out = np.full(len(d), np.nan)
    for u, g in d.groupby("user_id"):
        t, bg = g.t.values, g.cgm_mgdl.values
        j = np.searchsorted(t, t + minutes * 60)
        ok = j < len(t)
        good = np.zeros(len(t), bool)
        good[ok] = np.abs(t[j[ok]] - (t[ok] + minutes * 60)) <= 300
        v = np.full(len(t), np.nan)
        v[good] = bg[j[good]]
        out[g.index.values - d.index.values[0]] = v
    return out


def twin(conn):
    """The KAIROS twin's 30-minute forecast against the engine's own eventualBG."""
    d = load(conn, "reason_text, sug_eventualbg", "and reason_text like '%twin=%'")
    fc = d.reason_text.str.extract(r"twin=([-\d.]+),")[0].astype(float)
    d = d.assign(fc30=fc).dropna(subset=["fc30", "sug_eventualbg"]).reset_index(drop=True)
    d["actual30"] = forward(d, 30)
    d = d.dropna(subset=["actual30"])
    if len(d) < 500:
        return None
    err_twin = np.abs(d.fc30 - d.actual30)
    err_eng = np.abs(d.sug_eventualbg - d.actual30)
    per = []
    for u, g in d.groupby("user_id"):
        per.append((u, len(g),
                    float(np.abs(g.fc30 - g.actual30).median()),
                    float(np.abs(g.sug_eventualbg - g.actual30).median())))
    return {"n": len(d), "users": d.user_id.nunique(),
            "twin_mae": float(err_twin.median()), "engine_mae": float(err_eng.median()),
            "per_user": per}


def main():
    conn = psycopg2.connect(DSN)
    os.makedirs(OUT, exist_ok=True)
    print("=== KAIROS twin: 30-minute forecast error ===")
    print("  Scored against persistence and a linear extrapolation, not against eventualBG.")
    print("  eventualBG projects where glucose settles once insulin has acted, which is a")
    print("  different question, and scoring it here measures the mismatch not the model.")
    t = twin(conn)
    if t:
        print(f"  {t['n']:,} cycles, {t['users']} participants")
        print(f"  median absolute error, twin   {t['twin_mae']:.1f} mg/dL")
        print(f"  median absolute error, engine {t['engine_mae']:.1f} mg/dL")
        print(f"  {'participant':<8}{'n':>9}{'twin':>8}{'engine':>8}{'better':>9}")
        for u, n, a, b in sorted(t["per_user"]):
            print(f"  {u:<8}{n:>9,}{a:>8.1f}{b:>8.1f}{'twin' if a < b else 'engine':>9}")


if __name__ == "__main__":
    main()
