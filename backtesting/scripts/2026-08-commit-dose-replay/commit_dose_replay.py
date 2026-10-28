#!/usr/bin/env python3
"""
What a smaller committed dose would have been worth, bounded rather than simulated.

A replay that assigns a dose and then reads the recorded glucose is not a counterfactual. The
glucose in the record followed the dose that was given, and the observational dose response is
confounded by the policy that chose it, which is why the trial for this question is prospective.

What can be done is a first-order bound on one arm. Reducing the committed dose does not change
the meal, so the carbohydrate side of the trajectory can be held at what was observed while the
insulin side is recomputed. The insulin that is not given never acts, so at any later time the
glucose under the smaller dose is higher than the recorded glucose by

    delta_bg(t) = ISF * removed_dose * fraction_of_that_dose_that_had_acted_by_t

using the participant's own sensitivity as recorded at the commit, and the activity curve the app
itself uses. Everything else in the trajectory, meal absorption included, is left exactly as it
happened.

The bound is one-sided in a known direction. The recorded trajectory already contains whatever
counter-regulation the low provoked, and a smaller dose would have provoked less of it, so the
true counterfactual sits somewhat below this estimate and the number of lows avoided here is an
overestimate. It is reported as a ceiling for that reason. It also ignores the loop's own
response: under a smaller dose the algorithm would have made different subsequent decisions, and
those are not modelled.

Three arms are priced.

  uniform      every commit scaled, which is the pre-registered intervention
  oracle-late  only commits whose peak arrives within ten minutes, using knowledge unavailable at
               the time, which upper-bounds any targeting rule that could ever be built
  oracle-small only commits whose eventual excursion is small, the same idea on the other variable

If the oracle arms are not much better than uniform, targeting is not worth pursuing even if it
were possible, and the uniform reduction is the whole of the available benefit.

Usage:  python3 commit_dose_replay.py [--mult 0.7] [--json out.json]
"""

import argparse
import bisect
import json
import os
import sys

import numpy as np
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "2026-08-commit-peak-timing"))
import peak_timing as P                                     # noqa: E402
from peak_timing import cgm_of, low_onsets                  # noqa: E402

LOW_MGDL = 70.0
SEVERE_MGDL = 54.0
HORIZON_MIN = 300
PEAK_EARLY_MIN = 10
DEFAULT_PEAK_MIN = 55.0      # activity peak of the rapid analogues in use
DEFAULT_DIA_MIN = 360.0
ISF_FALLBACK = 50.0


def activity_fraction(minutes, peak=DEFAULT_PEAK_MIN, dia=DEFAULT_DIA_MIN):
    """Fraction of a bolus that has acted by `minutes`, from the exponential curve AAPS uses."""
    m = np.asarray(minutes, dtype=float)
    td, tp = dia, peak
    tau = tp * (1 - tp / td) / (1 - 2 * tp / td)
    a = 2 * tau / td
    S = 1 / (1 - a + (1 + a) * np.exp(-td / tau))
    iob = 1 - S * (1 - a) * ((m ** 2 / (tau * td * (1 - a)) - m / tau - 1) * np.exp(-m / tau) + 1)
    iob = np.clip(iob, 0.0, 1.0)
    iob = np.where(m <= 0, 1.0, iob)
    iob = np.where(m >= td, 0.0, iob)
    return 1.0 - iob


def fetch(conn):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT ON (user_id, to_timestamp(floor(extract(epoch FROM ts_utc)/300)*300))
               user_id, extract(epoch FROM ts_utc), boostv5_state, cgm_mgdl,
               boostv5_finaldose, sug_iob, variable_sens
        FROM boost_decisions
        WHERE user_id = ANY(%s) AND boostv5_state IS NOT NULL AND cgm_mgdl IS NOT NULL
        ORDER BY user_id, to_timestamp(floor(extract(epoch FROM ts_utc)/300)*300), ts_utc
    """, (list(P.USERS),))
    out = {}
    for u, t, st, bg, dose, iob, isf in cur.fetchall():
        f = lambda v: np.nan if v is None else float(v)
        out.setdefault(u, []).append(dict(t=float(t), state=st, bg=float(bg),
                                          dose=f(dose), iob=f(iob), isf=f(isf)))
    for u in out:
        out[u].sort(key=lambda x: x["t"])
    return out


def commits(rows, cgm_ts, cgm_bg):
    """Entry into CONFIRMED, with the delivered dose and the trajectory that followed."""
    out = []
    for k in range(1, len(rows)):
        if rows[k]["state"] != "CONFIRMED" or rows[k - 1]["state"] == "CONFIRMED":
            continue
        r = rows[k]
        if not np.isfinite(r["dose"]) or r["dose"] <= 0:
            continue
        t = r["t"]
        a = bisect.bisect_right(cgm_ts, t)
        b = bisect.bisect_right(cgm_ts, t + HORIZON_MIN * 60)
        if b - a < 12:
            continue
        seg_t, seg_b = cgm_ts[a:b], cgm_bg[a:b]
        pk = int(np.argmax(seg_b))
        isf = r["isf"] if np.isfinite(r["isf"]) and r["isf"] > 5 else ISF_FALLBACK
        out.append(dict(t=t, dose=r["dose"], bg=r["bg"], isf=isf,
                        seg_t=seg_t, seg_b=seg_b,
                        interval=(seg_t[pk] - t) / 60.0,
                        excursion=float(seg_b[pk] - r["bg"])))
    return out


def price(ev, scale, peak_min, dia_min):
    """Counterfactual minimum and peak under a scaled dose, on the insulin arm only."""
    removed = ev["dose"] * (1.0 - scale)
    mins = (ev["seg_t"] - ev["t"]) / 60.0
    lift = ev["isf"] * removed * activity_fraction(mins, peak_min, dia_min)
    cf = ev["seg_b"] + lift
    return dict(
        obs_min=float(ev["seg_b"].min()), cf_min=float(cf.min()),
        obs_peak=float(ev["seg_b"].max()), cf_peak=float(cf.max()),
        obs_low=int(ev["seg_b"].min() < LOW_MGDL),
        cf_low=int(cf.min() < LOW_MGDL),
        obs_sev=int(ev["seg_b"].min() < SEVERE_MGDL),
        cf_sev=int(cf.min() < SEVERE_MGDL),
        removed=float(removed),
        added_auc=float(np.trapezoid(np.clip(cf - 180.0, 0, None), mins)
                        - np.trapezoid(np.clip(ev["seg_b"] - 180.0, 0, None), mins)),
    )


def summarise(name, rows, n_total, insulin_total):
    if not rows:
        print(f"  {name:22s}  (no commits selected)")
        return None
    avoided = sum(r["obs_low"] - r["cf_low"] for r in rows)
    sev_av = sum(r["obs_sev"] - r["cf_sev"] for r in rows)
    ins = sum(r["removed"] for r in rows)
    auc_ = sum(r["added_auc"] for r in rows)
    obs = sum(r["obs_low"] for r in rows)
    print(f"  {name:22s} {len(rows):6d} {obs:8d} {avoided:8d} {sev_av:7d} {ins:9.1f} "
          f"{auc_/60.0/max(n_total,1):10.1f} {(ins/avoided if avoided else float('nan')):9.2f}")
    return dict(n=len(rows), obs_lows=int(obs), avoided=int(avoided), severe_avoided=int(sev_av),
                insulin_removed=float(ins),
                added_mgdl_hours_per_commit=float(auc_ / 60.0 / max(n_total, 1)),
                insulin_per_low_avoided=(float(ins / avoided) if avoided else None))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mult", type=float, default=0.7)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    rows, cgm = fetch(conn), cgm_of(conn)
    ev = []
    for u, r in rows.items():
        if u not in cgm:
            continue
        ct, cb = cgm[u]
        for e in commits(r, ct, cb):
            e["u"] = u
            ev.append(e)
    print(f"commits with a delivered dose: {len(ev)} across {len(set(e['u'] for e in ev))} participants")
    print(f"  observed low within {HORIZON_MIN} min: "
          f"{np.mean([e['seg_b'].min() < LOW_MGDL for e in ev]):.3f}")
    print(f"  median dose {np.median([e['dose'] for e in ev]):.2f} U, "
          f"median sensitivity {np.median([e['isf'] for e in ev]):.0f} mg/dL/U")
    print(f"  scaling to {args.mult:.2f} of the committed dose\n")
    res = {"n": len(ev), "mult": args.mult}

    print("=" * 88)
    print("WHAT THE REDUCTION BUYS, ON THE INSULIN ARM ONLY")
    print("=" * 88)
    print("  Lows avoided is a ceiling: the recorded trajectory already contains the")
    print("  counter-regulation the low provoked, which a smaller dose would have provoked less of.\n")
    print(f"  {'arm':22s} {'commits':>6s} {'obs low':>8s} {'avoided':>8s} {'sev':>7s} "
          f"{'U removed':>9s} {'+mgdl.h':>10s} {'U per low':>9s}")
    priced = [dict(price(e, args.mult, DEFAULT_PEAK_MIN, DEFAULT_DIA_MIN), **{"e": e}) for e in ev]
    arms = {
        "uniform": priced,
        "oracle-late": [p for p in priced if p["e"]["interval"] <= PEAK_EARLY_MIN],
        "oracle-small": [p for p in priced if p["e"]["excursion"] < np.median([q["e"]["excursion"] for q in priced])],
    }
    res["arms"] = {}
    for nm, sel in arms.items():
        res["arms"][nm] = summarise(nm, sel, len(ev), None)

    print()
    print("=" * 88)
    print("SENSITIVITY TO THE INSULIN CURVE AND TO THE SIZE OF THE REDUCTION")
    print("=" * 88)
    print(f"\n  {'peak / DIA':>14s} {'mult':>6s} {'avoided':>8s} {'severe':>8s} {'U per low':>10s}")
    res["sensitivity"] = []
    for pk in (45.0, 55.0, 75.0):
        for mult in (0.5, 0.7, 0.85):
            pr = [price(e, mult, pk, DEFAULT_DIA_MIN) for e in ev]
            av = sum(r["obs_low"] - r["cf_low"] for r in pr)
            sv = sum(r["obs_sev"] - r["cf_sev"] for r in pr)
            ins = sum(r["removed"] for r in pr)
            print(f"  {pk:6.0f} / {DEFAULT_DIA_MIN:<5.0f} {mult:6.2f} {av:8d} {sv:8d} "
                  f"{(ins/av if av else float('nan')):10.2f}")
            res["sensitivity"].append(dict(peak=pk, mult=mult, avoided=int(av),
                                           severe=int(sv), insulin=float(ins)))

    print()
    print("=" * 88)
    print("PER PARTICIPANT, UNIFORM ARM")
    print("=" * 88)
    print(f"\n  {'user':6s} {'commits':>8s} {'obs lows':>9s} {'avoided':>8s} {'share':>7s} "
          f"{'U removed':>10s}")
    res["per_user"] = {}
    for u in sorted(set(e["u"] for e in ev)):
        sel = [p for p in priced if p["e"]["u"] == u]
        ol = sum(p["obs_low"] for p in sel)
        av = sum(p["obs_low"] - p["cf_low"] for p in sel)
        ins = sum(p["removed"] for p in sel)
        print(f"  {u:6s} {len(sel):8d} {ol:9d} {av:8d} "
              f"{(av/ol if ol else float('nan')):7.2f} {ins:10.1f}")
        res["per_user"][u] = dict(n=len(sel), obs_lows=int(ol), avoided=int(av),
                                  insulin=float(ins))

    print()
    print("=" * 88)
    print("COST IN GLUCOSE EXPOSURE, WHICH IS THE CURRENCY THAT MATTERS")
    print("=" * 88)
    print("  Insulin removed is not the cost of an arm. The cost is the hyperglycaemia accepted")
    print("  in exchange, and it differs by a factor of forty between these arms because a late")
    print("  commit delivers into a meal that has already peaked.\n")
    print(f"  {'arm':24s} {'avoided':>8s} {'total mg/dL.h':>14s} {'per low avoided':>16s}")
    for nm, a in res["arms"].items():
        if a is None:
            continue
        tot = a["added_mgdl_hours_per_commit"] * len(ev)
        a["total_mgdl_hours"] = float(tot)
        a["mgdl_hours_per_low_avoided"] = float(tot / a["avoided"]) if a["avoided"] else None
        print(f"  {nm:24s} {a['avoided']:8d} {tot:14.0f} "
              f"{(tot/a['avoided'] if a['avoided'] else float('nan')):16.1f}")

    print()
    print("=" * 88)
    print("IS THE HARM IN THE LARGE BOLUS AT A LATE COMMIT")
    print("=" * 88)
    med_dose = float(np.median([e["dose"] for e in ev]))
    print(f"  Large is above the cohort median committed dose of {med_dose:.2f} U.\n")
    print(f"  {'cell':34s} {'n':>6s} {'obs low':>8s} {'severe':>7s} {'med dose':>9s} "
          f"{'med nadir':>10s}")
    res["cells"] = {}
    for nm, sel in (("late peak, large dose",
                     [e for e in ev if e["interval"] <= PEAK_EARLY_MIN and e["dose"] > med_dose]),
                    ("late peak, small dose",
                     [e for e in ev if e["interval"] <= PEAK_EARLY_MIN and e["dose"] <= med_dose]),
                    ("normal peak, large dose",
                     [e for e in ev if e["interval"] > PEAK_EARLY_MIN and e["dose"] > med_dose]),
                    ("normal peak, small dose",
                     [e for e in ev if e["interval"] > PEAK_EARLY_MIN and e["dose"] <= med_dose])):
        if len(sel) < 20:
            continue
        lo_ = np.mean([e["seg_b"].min() < LOW_MGDL for e in sel])
        sv = np.mean([e["seg_b"].min() < SEVERE_MGDL for e in sel])
        print(f"  {nm:34s} {len(sel):6d} {lo_:8.3f} {sv:7.3f} "
              f"{np.median([e['dose'] for e in sel]):9.2f} "
              f"{np.median([e['seg_b'].min() for e in sel]):10.0f}")
        res["cells"][nm] = dict(n=len(sel), low=float(lo_), severe=float(sv))

    print()
    print("=" * 88)
    print("HOW HARD TO CUT THE LATE COMMIT, AND WHAT IT COSTS")
    print("=" * 88)
    print("  Applied only to commits whose peak arrives within ten minutes, leaving every other")
    print("  commit untouched. The uniform arm at 0.70 is repeated for comparison.\n")
    print(f"  {'policy':34s} {'avoided':>8s} {'severe':>7s} {'mg/dL.h':>9s} {'per low':>9s}")
    res["cut_curve"] = []
    late = [e for e in ev if e["interval"] <= PEAK_EARLY_MIN]
    for m in (0.85, 0.70, 0.50, 0.30, 0.0):
        pr = [price(e, m, DEFAULT_PEAK_MIN, DEFAULT_DIA_MIN) for e in late]
        av = sum(r["obs_low"] - r["cf_low"] for r in pr)
        sv = sum(r["obs_sev"] - r["cf_sev"] for r in pr)
        tot = sum(r["added_auc"] for r in pr) / 60.0
        print(f"  late commits scaled to {m:.2f}          {av:8d} {sv:7d} {tot:9.0f} "
              f"{(tot/av if av else float('nan')):9.1f}")
        res["cut_curve"].append(dict(mult=m, avoided=int(av), severe=int(sv),
                                     mgdl_hours=float(tot)))
    pr = [price(e, 0.70, DEFAULT_PEAK_MIN, DEFAULT_DIA_MIN) for e in ev]
    av = sum(r["obs_low"] - r["cf_low"] for r in pr)
    tot = sum(r["added_auc"] for r in pr) / 60.0
    print(f"  every commit scaled to 0.70        {av:8d} "
          f"{sum(r['obs_sev']-r['cf_sev'] for r in pr):7d} {tot:9.0f} {tot/av:9.1f}")

    if args.json:
        json.dump(res, open(args.json, "w"), indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
