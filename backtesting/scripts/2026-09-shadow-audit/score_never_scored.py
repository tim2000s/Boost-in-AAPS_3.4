#!/usr/bin/env python3
"""Score the four shadows that had been running without ever being asked whether they work.

Each is scored against the outcome its own name claims, on the cohort, with the participant
reported alongside the pooled figure. Read the emitting code before choosing the field: the
plateau tag's first element is whether the safety floor permitted a nudge, not whether a plateau
was detected, and scoring it as the latter reports a component as anti-predictive when it is
merely being read wrong.
"""
import numpy as np
import pandas as pd
import psycopg2
import warnings

warnings.filterwarnings("ignore")
DSN = "dbname=oref host=127.0.0.1 port=5432"


def epoch(s):
    v = (pd.to_datetime(s, utc=True) - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds()
    assert v.min() > 1.6e9, v.min()
    return v.values


def forward(d, minutes, how):
    out = np.full(len(d), np.nan)
    for _, g in d.groupby("user_id"):
        t, bg = g.t.values, g.cgm_mgdl.values
        j = np.searchsorted(t, t + minutes * 60)
        ok = j < len(t)
        v = np.full(len(t), np.nan)
        for i in np.where(ok)[0]:
            seg = bg[i:j[i] + 1]
            if len(seg) > 4:
                v[i] = how(seg, bg[i])
        out[g.index.values] = v
    return out


def auc(y, s):
    m = ~pd.isna(s)
    y = np.asarray(y)[m]; s = np.asarray(s)[m]
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    return float("nan") if n1 < 50 or n0 < 50 else (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def lift(d, fired, y):
    base = d[y].mean()
    return d[y][fired].mean() / base if base else float("nan"), base


def isf_shadow(c):
    d = pd.read_sql("""select user_id, ts_utc, cgm_mgdl, isf_shadow_bounded, variable_sens,
        isf_profile_sens from boost_decisions where isf_shadow_bounded is not null
        and cgm_mgdl between 20 and 500 order by user_id, ts_utc""", c)
    d["t"] = epoch(d.ts_utc)
    y = np.zeros(len(d), int)
    for _, g in d.groupby("user_id"):
        t, bg = g.t.values, g.cgm_mgdl.values
        low = bg < 70; starts = []; i = 0
        while i < len(bg):
            if low[i]:
                j = i
                while j + 1 < len(bg) and low[j + 1] and t[j + 1] - t[j] <= 20 * 60:
                    j += 1
                if t[j] - t[i] >= 15 * 60:
                    starts.append(t[i])
                i = j + 1
            else:
                i += 1
        st = np.array(starts); yy = np.zeros(len(bg), int)
        for k in range(len(bg)):
            idx = np.searchsorted(st, t[k], "left")
            if idx < len(st) and st[idx] <= t[k] + 4 * 3600:
                yy[k] = 1
        y[g.index.values] = yy
    d["y"] = y
    d["engine"] = d.isf_profile_sens / d.variable_sens
    print(f"\n=== ISF shadow: does its ratio anticipate hypoglycaemia better than the engine's? ===")
    print(f"  {len(d):,} cycles, {d.user_id.nunique()} participants, base rate {d.y.mean():.4f}")
    print(f"  shadow bounded ratio  AUC {auc(d.y.values, d.isf_shadow_bounded.values):.4f}")
    print(f"  engine effective      AUC {auc(d.y.values, d.engine.values):.4f}")


def backout(c):
    d = pd.read_sql("""select user_id, ts_utc, cgm_mgdl, antbackout_state from boost_decisions
        where antbackout_state is not null and cgm_mgdl between 20 and 500
        order by user_id, ts_utc""", c)
    d["t"] = epoch(d.ts_utc)
    d["fall60"] = forward(d, 60, lambda seg, b: b - seg.min())
    d = d.dropna(subset=["fall60"])
    d["y"] = (d.fall60 >= 30).astype(int)
    l, base = lift(d, d.antbackout_state == "ARMED", "y")
    print(f"\n=== Anticipatory backout: does ARMED anticipate a 30 mg/dL fall within an hour? ===")
    print(f"  {len(d):,} cycles, {d.user_id.nunique()} participants, base rate {base:.3f}, lift {l:.2f}x")


def plateau(c):
    d = pd.read_sql("""select user_id, ts_utc, cgm_mgdl, reason_text from boost_decisions
        where reason_text like '%%plateau=%%' and cgm_mgdl between 20 and 500
        order by user_id, ts_utc""", c)
    d["t"] = epoch(d.ts_utc)
    f = d.reason_text.str.extract(r"plateau=([^;]+);")[0].str.split(",")
    d["would"] = f.str[1].astype(float)
    d["min60"] = forward(d, 60, lambda seg, b: seg.min())
    d = d.dropna(subset=["min60", "would"])
    hi = d[d.cgm_mgdl > 140].copy()
    hi["y"] = (hi.min60 > 140).astype(int)
    l, base = lift(hi, hi.would > 0, "y")
    print(f"\n=== Plateau: does a would-nudge mark a high that stays high for an hour? ===")
    print(f"  {len(hi):,} cycles above 140 mg/dL, {hi.user_id.nunique()} participants, "
          f"base rate {base:.3f}, lift {l:.2f}x")


def tranche(c):
    n = pd.read_sql("select count(tranche_state) n, count(distinct user_id) "
                    "filter (where tranche_state is not null) u from boost_decisions", c)
    print(f"\n=== Tranche: {int(n.n[0]):,} cycles on {int(n.u[0])} participant(s) ===")
    print("  Too thin to score. It needs the cohort before a verdict is possible.")


def main():
    c = psycopg2.connect(DSN)
    isf_shadow(c); backout(c); plateau(c); tranche(c)


if __name__ == "__main__":
    main()
