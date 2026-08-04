#!/usr/bin/env python3
"""GATE 2 — estimate the insulin ACTION peak from observed glucose (2026-08-04).

Gate 1 established that the peak is identifiable from this user's real dose spacing, by recovering
a curve that was known by construction. This estimates the peak from what glucose actually did,
which is the physiological quantity.

MODEL. In a window where insulin is the only thing moving glucose:

    dBG_i  =  -k * conv(dose, activity(.; peak, DIA))_i  +  c  +  e_i

`k` absorbs ISF and any unit scaling; `c` absorbs endogenous production and drift. Both are fitted
PER WINDOW and profiled out analytically (an OLS of dBG on the convolved-activity regressor with an
intercept), so only `peak` is estimated globally. This matters:

  * ISF LEVEL differences between nights — dynamic ISF, site, hormones — cannot bias the peak,
    because each window gets its own amplitude.
  * A concentration change (U200 -> diluted U100) is a pure amplitude change, so it lands entirely
    in `k` and leaves the shape estimate alone. That is what makes a before/after peak comparison
    meaningful across the 2026-08-04 dilution.

DIA is HELD FIXED, not fitted. Gate 1 showed it carries essentially no signal at these dose sizes
(holding it at the configured value left RMSE unchanged at 0.1917 vs 0.1916), and fitting it drags
the peak with it.

WINDOW SELECTION is the whole ballgame — the estimate is only as good as the isolation:
  COB == 0 throughout, and no carbs recorded in the window or the 3 h before it
  overnight, when unannounced eating is least likely
  steps below a threshold throughout (exercise moves glucose and changes absorption)
  not inside a post-rescue window (rescue carbs are unannounced by definition)
  no CGM gap longer than 15 min, and BG in a plausible range
  at least some insulin delivered, or there is no input to identify anything from

DRIFT IS MODELLED AS A RAMP, NOT A CONSTANT, and this is not cosmetic. Overnight windows sit
across dawn, and an unmodelled rising trend late in a window looks exactly like insulin action
ending early. With only an intercept the pooled estimate is 30.9 min [20.4, 36.9]; adding the
per-window time trend moves it to 35.3 [29.2, 44.2]. The first number invited the conclusion that
the configured peak was too late; it was an artefact of the drift model. A pre-dawn-only cut
(00:00-04:00) independently gives 34.8, agreeing with the trend-controlled figure.

WHAT THIS CANNOT DO. Sensor lag (~4 min interstitial plus filter delay) biases every estimate LATE
by roughly a constant. That offset is not removed here: it very nearly cancels in a before/after
comparison, which is how this is meant to be used, but an ABSOLUTE peak from this script should be
read as "action peak as seen through the sensor", a few minutes later than the true one.

Usage:
  python3 gate2_peak_from_glucose.py --user tim                     # whole history, per-window
  python3 gate2_peak_from_glucose.py --user tim --before 2026-08-04 # pre-change baseline only
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
import psycopg2
from scipy.optimize import minimize_scalar

from gate1_recover_known_curve import activity

DSN = "dbname=oref host=127.0.0.1 port=5432"
HERE = os.path.dirname(os.path.abspath(__file__))
STEP_S = 300.0


def load(user: str):
    conn = psycopg2.connect(DSN)
    dec = pd.read_sql("""
        SELECT DISTINCT ON (floor(ts_epoch/300.0))
          ts_utc, ts_epoch, cgm_mgdl, sug_cob, steps_60m, boostv5_postrescuewindow AS postrescue,
          reason_dev, variable_sens
        FROM boost_decisions WHERE user_id = %s AND cgm_mgdl > 1
        ORDER BY floor(ts_epoch/300.0), ts_epoch DESC""", conn, params=(user,))
    tre = pd.read_sql("""
        SELECT ts_utc, insulin, carbs, event_type FROM boost_treatments
        WHERE user_id = %s ORDER BY ts_utc""", conn, params=(user,))
    conn.close()
    for d in (dec, tre):
        d["ts"] = pd.to_datetime(d.ts_utc, utc=True)
    dec = dec.sort_values("ts").reset_index(drop=True)
    dec["local_hour"] = dec.ts.dt.tz_convert("Europe/London").dt.hour
    return dec, tre


def build_windows(dec, tre, hours=4.0, night=(0, 7), max_steps=200, min_insulin=0.3):
    """Yield (times_s, dBG, dose_grid_slice_start_idx) for each isolated fasting window."""
    carbs = tre[(tre.carbs.fillna(0) > 0)].ts.values.astype("datetime64[s]").astype(float)
    bol = tre[(tre.insulin.fillna(0) > 0)]
    b_s = bol.ts.values.astype("datetime64[s]").astype(float)
    b_u = bol.insulin.values.astype(float)

    t = dec.ts_epoch.values.astype(float)
    bg = dec.cgm_mgdl.values.astype(float)
    ok = ((dec.sug_cob.fillna(1) == 0).values
          & (dec.steps_60m.fillna(9999) <= max_steps).values
          & (~dec.postrescue.fillna(False).astype(bool)).values
          & (dec.local_hour.between(night[0], night[1] - 1)).values
          & (bg > 40) & (bg < 350))

    win = int(hours * 3600 / STEP_S)
    out = []
    i = 0
    n = len(t)
    while i + win < n:
        sl = slice(i, i + win)
        if not ok[sl].all():
            i += 1; continue
        ts = t[sl]
        if np.max(np.diff(ts)) > 900:                       # CGM gap > 15 min
            i += 1; continue
        t_start, t_end = ts[0], ts[-1]
        if ((carbs >= t_start - 3 * 3600) & (carbs <= t_end)).any():
            i += 1; continue                                # carbs in or shortly before window
        m = (b_s >= t_start - 6 * 3600) & (b_s <= t_end)     # doses that can still be acting
        if b_u[m].sum() < min_insulin:
            i += 1; continue
        out.append((ts, bg[sl], b_s[m], b_u[m]))
        i += win                                            # non-overlapping windows
    return out


def window_regressor(ts, d_s, d_u, peak, dia):
    """Convolved insulin ACTION sampled at the window's observation times."""
    x = np.zeros(len(ts))
    for s, u in zip(d_s, d_u):
        dt = (ts - s) / 60.0
        x += u * activity(dt, peak, dia)
    return x


def sse_for_peak(peak, windows, dia, linear_drift=False):
    """Total residual SSE with per-window amplitude and drift profiled out.

    linear_drift adds a per-window TIME TREND alongside the intercept. Dawn phenomenon is a rising
    ramp, not a constant offset, and an unmodelled late rise inside a window mimics insulin action
    ending early — which would bias the peak estimate EARLY. With the trend absorbed, that route to
    bias is closed.
    """
    tot = 0.0
    for ts, bg, d_s, d_u in windows:
        x = window_regressor(ts, d_s, d_u, peak, dia)[:-1]
        y = np.diff(bg)
        if np.std(x) < 1e-12:
            continue
        cols = [x, np.ones(len(x))]
        if linear_drift:
            cols.append((ts[:-1] - ts[0]) / 3600.0)
        A = np.column_stack(cols)
        beta, *_ = np.linalg.lstsq(A, y, rcond=None)
        tot += float(np.sum((y - A @ beta) ** 2))
    return tot


def fit_peak(windows, dia, lo=10.0, hi=150.0, linear_drift=False):
    r = minimize_scalar(sse_for_peak, bounds=(lo, hi), args=(windows, dia, linear_drift), method="bounded",
                        options={"xatol": 0.25})
    return float(r.x), float(r.fun)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="tim")
    ap.add_argument("--dia", type=float, default=600.0)
    ap.add_argument("--hours", type=float, default=4.0)
    ap.add_argument("--before", help="only use windows before this date (YYYY-MM-DD)")
    ap.add_argument("--boot", type=int, default=300)
    ap.add_argument("--no-linear-drift", dest="linear_drift", action="store_false",
                    help="drop the per-window time trend (leaves the dawn-ramp bias in place)")
    ap.set_defaults(linear_drift=True)
    ap.add_argument("--night", default="0,7", help="local-hour window, e.g. 0,4 to sit before dawn")
    ap.add_argument("--min-insulin", type=float, default=0.3,
                    help="minimum U acting in the window — raises signal-to-noise, cuts sample")
    a = ap.parse_args()

    dec, tre = load(a.user)
    if a.before:
        cut = pd.Timestamp(a.before, tz="UTC")
        dec = dec[dec.ts < cut]; tre = tre[tre.ts < cut]
    nh = tuple(int(v) for v in a.night.split(","))
    wins = build_windows(dec, tre, hours=a.hours, min_insulin=a.min_insulin, night=nh)
    if len(wins) < 5:
        print(f"only {len(wins)} usable windows — not enough"); return

    peak, sse = fit_peak(wins, a.dia, linear_drift=a.linear_drift)

    # Window bootstrap: resample WINDOWS, which is the independent unit here.
    rng = np.random.default_rng(20260804)
    boots = []
    for _ in range(a.boot):
        idx = rng.integers(0, len(wins), len(wins))
        pk, _ = fit_peak([wins[j] for j in idx], a.dia, linear_drift=a.linear_drift)
        boots.append(pk)
    lo, hi = np.percentile(boots, [2.5, 97.5])

    # Per-window estimates: gives the BETWEEN-window spread, which sets how big a real shift must
    # be before it can be told apart from ordinary night-to-night wander.
    per = []
    for w in wins:
        try:
            pk, _ = fit_peak([w], a.dia, linear_drift=a.linear_drift)
            if 12 < pk < 148:                                # drop windows pinned at a bound
                per.append(pk)
        except Exception:                                    # noqa: BLE001
            pass
    per = np.array(per)

    L = []
    P = L.append
    P("# Gate 2 — insulin action peak from observed glucose\n")
    P(f"User **{a.user}**{f', windows before {a.before}' if a.before else ''}. "
      f"{len(wins)} isolated fasting windows of {a.hours:g} h "
      f"({len(wins) * a.hours:.0f} h total). DIA held at {a.dia:.0f} min.\n")
    P(f"\n**Pooled peak estimate: {peak:.1f} min**, window-bootstrap 95% CI "
      f"[{lo:.1f}, {hi:.1f}] ({a.boot} draws).\n")
    if len(per) >= 5:
        P(f"\nPer-window estimates: n={len(per)}, median {np.median(per):.1f}, "
          f"SD {per.std(ddof=1):.1f} min, IQR [{np.percentile(per,25):.1f}, {np.percentile(per,75):.1f}].\n")
        sd = per.std(ddof=1)
        P("\n## How big a shift could we detect?\n")
        P("| post-change windows | detectable shift (min, 80% power, alpha 0.05) |")
        P("|---|---|")
        for n in (5, 10, 20, 40):
            mdd = 2.8 * sd * np.sqrt(1.0 / n + 1.0 / max(len(per), 1))
            P(f"| {n} | {mdd:.1f} |")
        P("\nBased on the observed between-window SD, so it already includes ordinary night-to-night "
          "variation rather than assuming it away. At roughly one usable window per night, the "
          "left column is also days of data.\n")
    P("\n**Read the absolute value with care:** sensor lag biases it late by a few minutes and that "
      "is not corrected here. The comparison this is built for — before vs after a change, same "
      "user, same sensor generation — cancels that offset.\n")

    open(os.path.join(HERE, "GATE2_REPORT.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
