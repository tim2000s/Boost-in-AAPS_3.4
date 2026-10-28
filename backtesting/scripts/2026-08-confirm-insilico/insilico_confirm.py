#!/usr/bin/env python3
"""
In-silico trial of the confirm dose, run as a continuous time series with randomised assignment.

For each entry into CONFIRMED the delivered dose is scaled by a multiplier drawn at random from a
declared range, and the whole thirty-day glucose series is recomputed once with every draw in
place. Overlapping confirms therefore accumulate: a confirm two hours after another is scored
against a trajectory that already carries the first one's change, which per-event windows cannot
represent.

The counterfactual is one-armed. Reducing a dose does not change the meal, so the carbohydrate
side of the trajectory is held exactly as recorded and only the insulin side recomputed. Insulin
not delivered never acts, so at any later time

    glucose_counterfactual(t) = glucose_observed(t) + sum over confirms of
                                ISF_i x removed_i x fraction of that bolus acted by (t - t_i)

with the sensitivity in force at each confirm taken from the record, and the activity curve the
app itself uses.

Three things this cannot do, stated because the result is easy to over-read.

  The recorded trajectory already contains whatever counter-regulation each low provoked, and a
  smaller dose would have provoked less, so hypoglycaemia avoided is a ceiling.

  The loop is not re-run. Under a smaller confirm the algorithm would have seen higher glucose
  afterwards and dosed more, which would claw back part of both the benefit and the cost. The
  direction is known and the magnitude is not.

  A single participant over thirty days is a small sample of confirms, and the replicate spread
  reported here is the spread of the assignment, not of the person.

What the replication does buy is the distribution of outcomes under random assignment, which is
what a real trial would draw from once. That is the quantity needed to size it.

Usage:  python3 insilico_confirm.py [--user tim] [--days 30] [--lo 0.5] [--hi 1.0]
                                    [--reps 400] [--json out.json]
"""

import argparse
import bisect
import json
import sys

import numpy as np
import psycopg2

LOW = 70.0
SEVERE = 54.0
HIGH = 180.0
SUSTAIN_MIN = 10
PEAK_MIN = 55.0
DIA_MIN = 360.0
ISF_MIN, ISF_MAX = 5.0, 400.0


def acted(minutes, peak=PEAK_MIN, dia=DIA_MIN):
    """Fraction of a bolus that has acted by `minutes`, from the app's exponential curve."""
    m = np.asarray(minutes, float)
    tp, td = peak, dia
    tau = tp * (1 - tp / td) / (1 - 2 * tp / td)
    a = 2 * tau / td
    S = 1 / (1 - a + (1 + a) * np.exp(-td / tau))
    iob = 1 - S * (1 - a) * ((m ** 2 / (tau * td * (1 - a)) - m / tau - 1) * np.exp(-m / tau) + 1)
    iob = np.clip(iob, 0.0, 1.0)
    out = 1.0 - iob
    out = np.where(m < 0, 0.0, out)
    out = np.where(m >= td, 1.0, out)
    return out


def fetch(conn, user, days):
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (to_timestamp(floor(extract(epoch FROM ts_utc)/300)*300))
               extract(epoch FROM ts_utc), boostv5_state, cgm_mgdl,
               boostv5_finaldose, variable_sens, sug_iob
        FROM boost_decisions
        WHERE user_id = %s AND ts_utc >= now() - make_interval(days => %s)
          AND boostv5_state IS NOT NULL
        ORDER BY to_timestamp(floor(extract(epoch FROM ts_utc)/300)*300), ts_utc
    """, (user, days))
    rows = [dict(t=float(r[0]), state=r[1],
                 bg=None if r[2] is None else float(r[2]),
                 dose=None if r[3] is None else float(r[3]),
                 isf=None if r[4] is None else float(r[4]),
                 iob=None if r[5] is None else float(r[5])) for r in cur.fetchall()]
    cur.execute("""SELECT extract(epoch FROM ts_utc), cgm_mgdl FROM boost_cgm
                   WHERE user_id = %s AND ts_utc >= now() - make_interval(days => %s)
                     AND cgm_mgdl IS NOT NULL ORDER BY ts_utc""", (user, days))
    c = cur.fetchall()
    return rows, np.array([float(x[0]) for x in c]), np.array([float(x[1]) for x in c])


def confirms(rows, isf_default):
    out = []
    for k in range(1, len(rows)):
        if rows[k]["state"] != "CONFIRMED" or rows[k - 1]["state"] == "CONFIRMED":
            continue
        r = rows[k]
        if r["dose"] is None or r["dose"] <= 0:
            continue
        isf = r["isf"] if (r["isf"] is not None and ISF_MIN < r["isf"] < ISF_MAX) else isf_default
        out.append(dict(t=r["t"], dose=r["dose"], isf=isf, bg=r["bg"], iob=r["iob"]))
    return out


def outcomes(ts, bg):
    """Sensor-time-weighted outcomes over the whole series, plus episode counts."""
    if len(ts) < 2:
        return {}
    dt = np.diff(ts, append=ts[-1] + 300) / 60.0
    dt = np.clip(dt, 0, 15)
    tot = dt.sum()
    ep = 0
    i = 0
    while i < len(bg):
        if bg[i] < LOW:
            j = i
            while j + 1 < len(bg) and bg[j + 1] < LOW and ts[j + 1] - ts[j] <= 900:
                j += 1
            if ts[j] - ts[i] >= SUSTAIN_MIN * 60:
                ep += 1
            i = j + 1
        else:
            i += 1
    return dict(
        tbr70=float(100 * dt[bg < LOW].sum() / tot),
        tbr54=float(100 * dt[bg < SEVERE].sum() / tot),
        tir=float(100 * dt[(bg >= LOW) & (bg <= HIGH)].sum() / tot),
        tar=float(100 * dt[bg > HIGH].sum() / tot),
        mean=float(np.average(bg, weights=dt)),
        episodes=int(ep),
        hours=float(tot / 60.0))


WINDOW_MIN = 300     # the bound holds only while the removed insulin is still acting


def lift_series(cts, ev, mults, window=WINDOW_MIN):
    """Glucose lift from reduced confirms, and the mask over which the bound applies.

    A confirm contributes only for `window` minutes after it. Beyond that the loop and the
    physiology have re-equilibrated and the difference is no longer attributable to the dose,
    so carrying it forward accumulates error rather than signal. Overlapping confirms inside
    the window add, which is the reason for computing this on the series rather than per event.
    """
    lift = np.zeros(len(cts))
    mask = np.zeros(len(cts), bool)
    for e, m in zip(ev, mults):
        i = bisect.bisect_left(cts, e["t"])
        j = bisect.bisect_right(cts, e["t"] + window * 60)
        if i >= len(cts) or j <= i:
            continue
        mask[i:j] = True
        if m >= 1.0:
            continue
        removed = e["dose"] * (1.0 - m)
        if removed <= 0:
            continue
        mins = (cts[i:j] - e["t"]) / 60.0
        lift[i:j] += e["isf"] * removed * acted(mins)
    return lift, mask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="tim")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--lo", type=float, default=0.5)
    ap.add_argument("--hi", type=float, default=1.0)
    ap.add_argument("--reps", type=int, default=400)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    rows, cts, cbg = fetch(conn, args.user, args.days)
    isf_all = [r["isf"] for r in rows if r["isf"] and ISF_MIN < r["isf"] < ISF_MAX]
    isf_default = float(np.median(isf_all)) if isf_all else 50.0
    ev = confirms(rows, isf_default)
    _, in_window = lift_series(cts, ev, np.ones(len(ev)))
    base = outcomes(cts[in_window], cbg[in_window])
    whole = outcomes(cts, cbg)
    print(f"{args.user}, last {args.days} days: {len(cts)} sensor readings over "
          f"{whole['hours']/24:.1f} days, {len(ev)} confirms")
    print(f"  whole period     TBR<70 {whole['tbr70']:.2f}%  TIR {whole['tir']:.1f}%  "
          f"mean {whole['mean']:.0f}")
    print(f"  the {WINDOW_MIN//60}h after a confirm is {100*in_window.mean():.0f}% of the record, "
          "and everything below is computed on it")
    print(f"  in window TBR<70 {base['tbr70']:.2f}%  TBR<54 {base['tbr54']:.2f}%  "
          f"TIR {base['tir']:.1f}%  TAR {base['tar']:.1f}%  mean {base['mean']:.0f}  "
          f"episodes {base['episodes']}")
    print(f"  confirm dose: median {np.median([e['dose'] for e in ev]):.2f} U, "
          f"total {sum(e['dose'] for e in ev):.1f} U")
    print(f"  sensitivity at confirm: median {np.median([e['isf'] for e in ev]):.0f} mg/dL/U, "
          f"range {min(e['isf'] for e in ev):.0f} to {max(e['isf'] for e in ev):.0f}")
    print(f"  multiplier drawn uniformly on [{args.lo}, {args.hi}], {args.reps} replicates\n")
    res = dict(user=args.user, days=args.days, n_confirms=len(ev),
               lo=args.lo, hi=args.hi, reps=args.reps, observed=base)

    print("=" * 84)
    print("1. THE TRIAL, REPLICATED")
    print("=" * 84)
    rng = np.random.default_rng(20260813)
    keys = ("tbr70", "tbr54", "tir", "tar", "mean", "episodes")
    acc = {k: [] for k in keys}
    removed_tot = []
    for _ in range(args.reps):
        m = rng.uniform(args.lo, args.hi, len(ev))
        lf, mk = lift_series(cts, ev, m)
        o = outcomes(cts[mk], (cbg + lf)[mk])
        for k in keys:
            acc[k].append(o[k])
        removed_tot.append(sum(e["dose"] * (1 - mm) for e, mm in zip(ev, m)))
    print(f"  {'measure':>10s} {'observed':>9s} {'median':>9s} {'2.5%':>8s} {'97.5%':>8s} "
          f"{'change':>9s}")
    for k in keys:
        a = np.array(acc[k], float)
        lo_, hi_ = np.percentile(a, [2.5, 97.5])
        print(f"  {k:>10s} {base[k]:9.2f} {np.median(a):9.2f} {lo_:8.2f} {hi_:8.2f} "
              f"{np.median(a)-base[k]:+9.2f}")
        res.setdefault("trial", {})[k] = dict(observed=base[k], median=float(np.median(a)),
                                              lo=float(lo_), hi=float(hi_))
    print(f"\n  insulin withheld per replicate: median {np.median(removed_tot):.1f} U "
          f"of {sum(e['dose'] for e in ev):.1f} U committed "
          f"({100*np.median(removed_tot)/sum(e['dose'] for e in ev):.0f}%)")
    res["insulin_removed_median"] = float(np.median(removed_tot))

    print()
    print("=" * 84)
    print("2. DOSE-RESPONSE, EACH MULTIPLIER APPLIED TO EVERY CONFIRM")
    print("=" * 84)
    print("  Deterministic, so no replication is needed.\n")
    print(f"  {'mult':>6s} {'U withheld':>11s} {'TBR<70':>8s} {'TBR<54':>8s} {'TIR':>7s} "
          f"{'TAR':>7s} {'mean':>6s} {'episodes':>9s}")
    print(f"  {'1.00':>6s} {0.0:11.1f} {base['tbr70']:8.2f} {base['tbr54']:8.2f} "
          f"{base['tir']:7.1f} {base['tar']:7.1f} {base['mean']:6.0f} {base['episodes']:9d}")
    res["dose_response"] = []
    for m in (0.9, 0.8, 0.7, 0.6, 0.5, 0.3, 0.0):
        lf, mk = lift_series(cts, ev, np.full(len(ev), m))
        o = outcomes(cts[mk], (cbg + lf)[mk])
        u = sum(e["dose"] for e in ev) * (1 - m)
        print(f"  {m:6.2f} {u:11.1f} {o['tbr70']:8.2f} {o['tbr54']:8.2f} {o['tir']:7.1f} "
              f"{o['tar']:7.1f} {o['mean']:6.0f} {o['episodes']:9d}")
        res["dose_response"].append(dict(mult=m, removed=float(u), **o))

    print()
    print("=" * 84)
    print("3. THE COST OF EACH CONFIRM, ONE AT A TIME")
    print("=" * 84)
    print("  Each confirm scaled to 0.5 with every other left alone, so the effect is that")
    print("  confirm's own. Sorted by hypoglycaemia removed. Times are local.\n")
    per = []
    for e in ev:
        _, mk1 = lift_series(cts, [e], [1.0])
        b1 = outcomes(cts[mk1], cbg[mk1])
        lf, mk = lift_series(cts, [e], [0.5])
        o = outcomes(cts[mk], (cbg + lf)[mk])
        per.append(dict(t=e["t"], dose=e["dose"], isf=e["isf"], bg=e["bg"], iob=e["iob"],
                        d_tbr70=o["tbr70"] - b1["tbr70"], d_tbr54=o["tbr54"] - b1["tbr54"],
                        d_tar=o["tar"] - b1["tar"], d_ep=o["episodes"] - b1["episodes"],
                        obs_tbr70=b1["tbr70"], removed=e["dose"] * 0.5))
    per.sort(key=lambda x: x["d_tbr70"])
    import datetime as dt
    print(f"  {'when':>16s} {'dose':>5s} {'ISF':>5s} {'BG':>4s} {'IOB':>5s} {'U off':>6s} "
          f"{'dTBR70':>8s} {'dTBR54':>8s} {'dTAR':>7s} {'dEp':>4s}")
    for p in per[:12]:
        w = dt.datetime.fromtimestamp(p["t"]).strftime("%a %d %H:%M")
        print(f"  {w:>16s} {p['dose']:5.2f} {p['isf']:5.0f} "
              f"{(p['bg'] or 0):4.0f} {(p['iob'] or 0):5.2f} {p['removed']:6.2f} "
              f"{p['d_tbr70']:+8.3f} {p['d_tbr54']:+8.3f} {p['d_tar']:+7.3f} {p['d_ep']:+4d}")
    n_help = sum(1 for p in per if p["d_tbr70"] < -0.001)
    n_none = sum(1 for p in per if abs(p["d_tbr70"]) <= 0.001)
    print(f"\n  confirms whose reduction removes hypoglycaemia: {n_help} of {len(per)}")
    print(f"  confirms where it changes nothing below range:   {n_none} of {len(per)}")
    tot_tar = sum(p["d_tar"] for p in per)
    tot_tbr = sum(p["d_tbr70"] for p in per)
    print(f"  summed over all confirms at 0.5: TBR<70 {tot_tbr:+.3f} pp, TAR {tot_tar:+.3f} pp")
    res["per_confirm"] = per
    res["n_help"] = n_help

    print()
    print("=" * 84)
    print("4. HOW MUCH OF EACH EFFECT ARRIVES EARLY")
    print("=" * 84)
    print("  The loop is not re-run, so the longer the window the more the estimate assumes the")
    print("  algorithm sat still while glucose climbed. Hypoglycaemia lands early and")
    print("  hyperglycaemia accrues late, so the two sides are not equally trustworthy.\n")
    print(f"  {'window':>8s} {'covers':>8s} {'dTBR<70':>9s} {'dTBR<54':>9s} {'dTAR':>8s} "
          f"{'TAR per TBR':>12s}")
    res["windows"] = []
    for w in (60, 120, 180, 300):
        _, mk = lift_series(cts, ev, np.ones(len(ev)), window=w)
        b = outcomes(cts[mk], cbg[mk])
        lf, mk2 = lift_series(cts, ev, np.full(len(ev), 0.7), window=w)
        o = outcomes(cts[mk2], (cbg + lf)[mk2])
        dtbr, dtar = o["tbr70"] - b["tbr70"], o["tar"] - b["tar"]
        print(f"  {w:6d}m {100*mk.mean():7.0f}% {dtbr:+9.2f} {o['tbr54']-b['tbr54']:+9.2f} "
              f"{dtar:+8.2f} {(dtar/-dtbr if dtbr < 0 else float('nan')):12.1f}")
        res["windows"].append(dict(window=w, d_tbr70=dtbr, d_tar=dtar))
    print("\n  A rising ratio with window length is the unmodelled loop response showing up as")
    print("  hyperglycaemia the algorithm would in fact have corrected.")

    if args.json:
        json.dump(res, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
