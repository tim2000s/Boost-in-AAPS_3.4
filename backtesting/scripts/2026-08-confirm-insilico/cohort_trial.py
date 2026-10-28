#!/usr/bin/env python3
"""
The randomised confirm trial across the cohort, split on whether the model can explain the low.

The single-participant run found that half of that participant's confirms are followed by a low
within four hours. This asks whether that holds for anyone else, which decides whether the confirm
is a cohort-level problem or one person's.

The split is the change the single-participant run recommended. For each confirm the model's
attributed glucose deficit by the nadir is compared with the fall actually observed from the peak
of the excursion. Where the ratio is at least one the model accounts for the whole fall and the
confirm is a plausible cause of what followed. Where it is below one, other insulin or the meal
ending did most of the work, and reducing that confirm could not have prevented the low. Reporting
the trial across both together credits the intervention with events it could not have altered, so
the two are reported separately throughout.

G is excluded: that participant runs the engine in shadow under a different loop and logs no
sensitivity, so neither the dose nor its pricing is meaningful.

Everything else follows `confirm_trial.py`: per-confirm windows, nothing summed across the record,
sensitivity from the record, and the whole analysis repeated at half and double the recorded
sensitivity because the record cannot calibrate it.

Usage:  python3 cohort_trial.py [--days 30] [--reps 3000] [--outdir figs_cohort]
"""

import argparse
import json
import os
import sys

import numpy as np
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import confirm_trial as CT
from confirm_trial import (SEVERE, HIGH, ISF_SCALES, TING_LOW, acted, build, evaluate, fetch)

USERS = ("A", "B", "C", "D", "E", "F", "H", "I", "tim")


def attribution(W):
    """Attributed deficit by the nadir over the fall observed from the peak of the excursion."""
    out = []
    for w in W:
        k = int(np.argmin(w["bg"]))
        fall = float(w["bg"][:k + 1].max() - w["bg"].min())
        deficit = float(w["isf"] * w["dose"] * acted(w["mins"][k]))
        out.append(deficit / max(fall, 1.0))
    return np.array(out)


def trial(W, reps, lo, hi, scale, seed, low):
    if not W:
        return None
    rng = np.random.default_rng(seed)
    lows = np.zeros(reps); sev = np.zeros(reps); nh = np.zeros(reps); rem = np.zeros(reps)
    dn, db, dp, da = [], [], [], []
    for w in W:
        o = evaluate(w, rng.uniform(lo, hi, reps), scale, low)
        lows += o["low"]; sev += o["severe"]; rem += o["removed"]
        nh += ((o["above"] > 0) & (o["obs_above"] == 0)).astype(int)
        if o["obs_low"]:
            dn.append(o["nadir"] - o["obs_nadir"]); db.append(o["d_below"])
        dp.append(o["peak"] - o["obs_peak"]); da.append(o["d_above"])
    q = lambda a: (float(np.median(a)), float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5)))
    return dict(n=len(W),
                obs_low=sum(int(w["bg"].min() < low) for w in W),
                obs_sev=sum(int(w["bg"].min() < SEVERE) for w in W),
                lows=q(lows), severe=q(sev), new_high=q(nh),
                removed=float(np.median(rem)),
                committed=float(sum(w["dose"] for w in W)),
                nadir_gain=float(np.median(np.concatenate(dn))) if dn else float("nan"),
                below_gain=float(np.median(np.concatenate(db))) if db else float("nan"),
                peak_gain=float(np.median(np.concatenate(dp))) if dp else float("nan"),
                above_gain=float(np.median(np.concatenate(da))) if da else float("nan"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30); ap.add_argument("--reps", type=int, default=3000)
    ap.add_argument("--lo", type=float, default=0.4); ap.add_argument("--hi", type=float, default=1.0)
    ap.add_argument("--outdir", default="figs_cohort")
    ap.add_argument("--low", type=float, default=TING_LOW)
    args = ap.parse_args()
    CT.LOW = args.low
    globals()["LOW"] = args.low
    os.makedirs(args.outdir, exist_ok=True)
    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True

    per_user, res = {}, {"days": args.days, "reps": args.reps, "users": {}}
    print("=" * 92)
    print("1. THE RECORD, WHICH DEPENDS ON NO MODELLING")
    print("=" * 92)
    print(f"\n  {'user':6s} {'confirms':>9s} {'U committed':>12s} {'median U':>9s} {'ISF':>5s} "
          f"{'with a low':>11s} {'severe':>8s} {'low rate':>9s}")
    for u in USERS:
        dec, cts, cbg = fetch(conn, u, args.days)
        W = build(dec, cts, cbg)
        if len(W) < 10:
            print(f"  {u:6s} {len(W):9d}   (too few, skipped)")
            continue
        per_user[u] = W
        lo_ = sum(int(w["bg"].min() < LOW) for w in W)
        sv = sum(int(w["bg"].min() < SEVERE) for w in W)
        print(f"  {u:6s} {len(W):9d} {sum(w['dose'] for w in W):12.1f} "
              f"{np.median([w['dose'] for w in W]):9.2f} {np.median([w['isf'] for w in W]):5.0f} "
              f"{lo_:11d} {sv:8d} {lo_/len(W):9.2f}")
        res["users"][u] = dict(n=len(W), obs_low=lo_, obs_sev=sv, rate=lo_ / len(W))
    tot = sum(len(v) for v in per_user.values())
    tl = sum(sum(int(w["bg"].min() < LOW) for w in W) for W in per_user.values())
    ts_ = sum(sum(int(w["bg"].min() < SEVERE) for w in W) for W in per_user.values())
    print(f"\n  {'cohort':6s} {tot:9d} {'':12s} {'':9s} {'':5s} {tl:11d} {ts_:8d} {tl/tot:9.2f}")
    res["cohort"] = dict(n=tot, obs_low=tl, obs_sev=ts_, rate=tl / tot)

    print()
    print("=" * 92)
    print("2. CAN THE MODEL EXPLAIN THE FALL, PER PARTICIPANT")
    print("=" * 92)
    print("  Attributed deficit by the nadir over the fall observed from the peak. At or above")
    print("  one the confirm can account for the whole fall; below one it cannot.\n")
    print(f"  {'user':6s} {'median ratio':>13s} {'explained':>10s} {'lows there':>11s} "
          f"{'unexplained':>12s} {'lows there':>11s}")
    split = {}
    for u, W in per_user.items():
        r = attribution(W)
        ex = [w for w, rr in zip(W, r) if rr >= 1.0]
        un = [w for w, rr in zip(W, r) if rr < 1.0]
        split[u] = (ex, un)
        lex = sum(int(w["bg"].min() < LOW) for w in ex)
        lun = sum(int(w["bg"].min() < LOW) for w in un)
        print(f"  {u:6s} {np.median(r):13.2f} {len(ex):10d} {lex:11d} {len(un):12d} {lun:11d}")
        res["users"][u].update(ratio=float(np.median(r)), n_explained=len(ex),
                               low_explained=lex, n_unexplained=len(un), low_unexplained=lun)
    n_ex = sum(len(v[0]) for v in split.values()); n_un = sum(len(v[1]) for v in split.values())
    l_ex = sum(sum(int(w["bg"].min() < LOW) for w in v[0]) for v in split.values())
    l_un = sum(sum(int(w["bg"].min() < LOW) for w in v[1]) for v in split.values())
    print(f"\n  {'cohort':6s} {'':13s} {n_ex:10d} {l_ex:11d} {n_un:12d} {l_un:11d}")
    print(f"  {l_un} of the {l_ex + l_un} lows sit after a confirm the model cannot account for,")
    print("  and no reduction of that confirm would have prevented them.")
    res["split"] = dict(n_explained=n_ex, n_unexplained=n_un,
                        low_explained=l_ex, low_unexplained=l_un)

    print()
    print("=" * 92)
    print("3. THE TRIAL ON THE CONFIRMS THE MODEL CAN EXPLAIN")
    print("=" * 92)
    print(f"  Multiplier uniform on [{args.lo}, {args.hi}], {args.reps} replicates, at the")
    print("  recorded sensitivity. Counts are per replicate.\n")
    print(f"  {'user':6s} {'confirms':>9s} {'observed':>9s} {'lows':>15s} {'severe':>13s} "
          f"{'new highs':>13s} {'U off':>7s}")
    res["trial_explained"] = {}
    for u in per_user:
        t = trial(split[u][0], args.reps, args.lo, args.hi, 1.0, 20260813, args.low)
        if t is None:
            continue
        f = lambda x: f"{x[0]:.0f} [{x[1]:.0f},{x[2]:.0f}]"
        print(f"  {u:6s} {t['n']:9d} {t['obs_low']:9d} {f(t['lows']):>15s} "
              f"{f(t['severe']):>13s} {f(t['new_high']):>13s} {t['removed']:7.1f}")
        res["trial_explained"][u] = t
    allex = [w for v in split.values() for w in v[0]]
    tc = trial(allex, args.reps, args.lo, args.hi, 1.0, 20260813, args.low)
    f = lambda x: f"{x[0]:.0f} [{x[1]:.0f},{x[2]:.0f}]"
    print(f"\n  {'cohort':6s} {tc['n']:9d} {tc['obs_low']:9d} {f(tc['lows']):>15s} "
          f"{f(tc['severe']):>13s} {f(tc['new_high']):>13s} {tc['removed']:7.1f}")
    res["cohort_trial"] = tc

    print()
    print("=" * 92)
    print("4. THE SAME AT HALF AND DOUBLE THE ASSUMED INSULIN EFFECT")
    print("=" * 92)
    print(f"\n  {'effect':>8s} {'lows':>16s} {'severe':>14s} {'new highs':>14s} "
          f"{'nadir gain':>11s} {'peak cost':>10s}")
    res["scales"] = {}
    for sc in ISF_SCALES:
        t = trial(allex, args.reps, args.lo, args.hi, sc, 20260813, args.low)
        print(f"  {'x'+str(sc):>8s} {f(t['lows']):>16s} {f(t['severe']):>14s} "
              f"{f(t['new_high']):>14s} {t['nadir_gain']:10.1f}  {t['peak_gain']:9.1f}")
        res["scales"][sc] = t
    print(f"  {'observed':>8s} {tc['obs_low']:>16d} {tc['obs_sev']:>14d} {0:>14d}")

    print()
    print("=" * 92)
    print("5. AND ON THE CONFIRMS IT CANNOT EXPLAIN, WHICH IS THE CONTROL")
    print("=" * 92)
    print("  If the reduction looks as effective here, the model is crediting itself with")
    print("  events it could not have altered.\n")
    allun = [w for v in split.values() for w in v[1]]
    tu = trial(allun, args.reps, args.lo, args.hi, 1.0, 20260813, args.low)
    if tu:
        print(f"  {'set':>12s} {'confirms':>9s} {'observed lows':>14s} {'after':>15s} "
              f"{'share removed':>14s}")
        for nm, t in (("explained", tc), ("unexplained", tu)):
            sh = 1 - t["lows"][0] / max(t["obs_low"], 1)
            print(f"  {nm:>12s} {t['n']:9d} {t['obs_low']:14d} {f(t['lows']):>15s} {sh:14.2f}")
        res["control"] = tu

    # ---- charts
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.dpi": 130, "font.size": 9, "axes.grid": True,
                         "grid.alpha": .3, "axes.spines.top": False, "axes.spines.right": False})
    us = list(per_user)

    fig, ax = plt.subplots(figsize=(7, 3.8))
    rates = [res["users"][u]["rate"] for u in us]
    sevr = [res["users"][u]["obs_sev"] / res["users"][u]["n"] for u in us]
    x = np.arange(len(us))
    ax.bar(x - .2, rates, .4, label="a low within 4h", color="tab:red", alpha=.85)
    ax.bar(x + .2, sevr, .4, label="severe", color="tab:purple", alpha=.85)
    ax.set_xticks(x); ax.set_xticklabels(us)
    ax.set_ylabel("share of confirms"); ax.set_xlabel("participant")
    ax.set_title("What follows a confirm, counted from the record")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(f"{args.outdir}/01_cohort_rates.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 3.8))
    ex_n = [res["users"][u]["n_explained"] for u in us]
    un_n = [res["users"][u]["n_unexplained"] for u in us]
    ax.bar(x, ex_n, .6, label="model accounts for the fall", color="tab:blue", alpha=.85)
    ax.bar(x, un_n, .6, bottom=ex_n, label="it does not", color="tab:grey", alpha=.7)
    ax.set_xticks(x); ax.set_xticklabels(us); ax.set_ylabel("confirms")
    ax.set_title("Which confirms a dose reduction could plausibly have altered")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(f"{args.outdir}/02_attribution_split.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.4, 4))
    for u in us:
        t = res["trial_explained"].get(u)
        if not t:
            continue
        ax.plot([t["obs_low"] / max(t["n"], 1)], [t["lows"][0] / max(t["n"], 1)], "o", ms=7)
        ax.annotate(u, (t["obs_low"] / max(t["n"], 1), t["lows"][0] / max(t["n"], 1)),
                    textcoords="offset points", xytext=(5, 3), fontsize=8)
    lim = [0, max(0.7, max(res["users"][u]["rate"] for u in us) * 1.1)]
    ax.plot(lim, lim, "k--", lw=.7, label="no change")
    ax.set_xlim(lim); ax.set_ylim(0, lim[1])
    ax.set_xlabel("observed share of confirms followed by a low")
    ax.set_ylabel("share after the randomised reduction")
    ax.set_title("Every participant moves the same way")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(f"{args.outdir}/03_per_user_effect.png"); plt.close(fig)

    json.dump(res, open(f"{args.outdir}/../cohort_summary.json", "w"), indent=2, default=float)
    print(f"\n  wrote 3 charts to {args.outdir}/ and cohort_summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
