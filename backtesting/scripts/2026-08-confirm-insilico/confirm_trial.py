#!/usr/bin/env python3
"""
Randomised in-silico trial of the confirm bolus, priced per confirm against insulin on board.

For every entry into CONFIRMED the delivered bolus is scaled by a multiplier drawn at random, the
glucose impact of the withheld insulin is priced through the sensitivity recorded at that confirm,
and the four hours that followed are re-read: if they contained a low, how much less deep it
becomes; if they contained a high, how much worse it becomes.

Each confirm is evaluated in its own window and nothing is summed across the record. That is not a
stylistic choice. The fraction of a bolus that has acted rises to one and stays there, so the
modelled glucose lift from withheld insulin is a permanent step; carried across thirty days,
eighty-four such steps drive the modelled mean glucose into the thousands. The linear
approximation is usable for one bolus over a few hours and nowhere else.

Insulin on board is carried through the whole analysis because it decides how much of a low is
attributable to the confirm at all. A low four hours later, at which the confirm contributes a
tenth of the insulin present, is not the confirm's low, and reducing the confirm will not prevent
it. Every benefit figure is therefore reported alongside the confirm's own share of the insulin
present at the nadir.

The insulin effect itself cannot be calibrated from this record. Across these confirms the
lowering the model predicts correlates with the observed peak-to-nadir fall at about minus 0.03,
because larger confirms accompany larger meals. The effect is therefore scaled from half to double
throughout, and any conclusion that does not survive that range is not a conclusion.

Outputs: a set of charts and a JSON summary. Replicates are parallelised across cores.

Usage:  python3 confirm_trial.py [--user tim] [--days 30] [--reps 3000]
                                 [--lo 0.4] [--hi 1.0] [--outdir figs]
"""

import argparse
import bisect
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import psycopg2

# TING is 3.5 to 7.8 mmol/L, so its floor is 63 mg/dL. That is the primary outcome here:
# a nadir below it is a fall out of the tight band rather than a brush with the 70 line, and
# it is less easily flipped by a small modelled lift than 70 is.
TING_LOW = 63.0
LOW, SEVERE, HIGH = TING_LOW, 54.0, 180.0
WINDOW_MIN = 240
# Fitted against the app's own IOB decay after confirms: 40/240 beats 55/360 at 0.42 U
# median error against 0.60. The fit is contaminated by the basal arm, so it is indicative.
# Curve uncertainty is in any case subsumed by the ISF sweep, since the modelled lift is
# ISF x removed x acted and scaling either scales the product.
PEAK_MIN, DIA_MIN = 40.0, 240.0
ISF_MIN, ISF_MAX = 5.0, 400.0
ISF_SCALES = (0.5, 1.0, 2.0)


def iob_fraction(minutes, peak=PEAK_MIN, dia=DIA_MIN):
    """Fraction of a bolus still on board at `minutes`, from the app's exponential curve."""
    m = np.asarray(minutes, float)
    tp, td = peak, dia
    tau = tp * (1 - tp / td) / (1 - 2 * tp / td)
    a = 2 * tau / td
    S = 1 / (1 - a + (1 + a) * np.exp(-td / tau))
    v = 1 - S * (1 - a) * ((m ** 2 / (tau * td * (1 - a)) - m / tau - 1) * np.exp(-m / tau) + 1)
    v = np.clip(v, 0.0, 1.0)
    return np.where(m < 0, 1.0, np.where(m >= td, 0.0, v))


def acted(minutes):
    return 1.0 - iob_fraction(minutes)


def activity(minutes, h=2.5):
    """d(acted)/dt, in per-minute units: the insulin's instantaneous action."""
    m = np.asarray(minutes, float)
    return np.clip((acted(m + h) - acted(m - h)) / (2 * h), 0.0, None)


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
    dec = [(float(r[0]), r[1],
            None if r[2] is None else float(r[2]),
            None if r[3] is None else float(r[3]),
            None if r[4] is None else float(r[4]),
            None if r[5] is None else float(r[5])) for r in cur.fetchall()]
    cur.execute("""SELECT extract(epoch FROM ts_utc), cgm_mgdl FROM boost_cgm
                   WHERE user_id = %s AND ts_utc >= now() - make_interval(days => %s)
                     AND cgm_mgdl IS NOT NULL ORDER BY ts_utc""", (user, days))
    c = cur.fetchall()
    return dec, np.array([float(x[0]) for x in c]), np.array([float(x[1]) for x in c])


def build(dec, cts, cbg):
    """One window per confirm: glucose, elapsed minutes, and the insulin present."""
    isf_all = [d[4] for d in dec if d[4] and ISF_MIN < d[4] < ISF_MAX]
    isf_def = float(np.median(isf_all)) if isf_all else 50.0
    dts = np.array([d[0] for d in dec])
    iobs = np.array([np.nan if d[5] is None else d[5] for d in dec])
    out = []
    for k in range(1, len(dec)):
        if dec[k][1] != "CONFIRMED" or dec[k - 1][1] == "CONFIRMED":
            continue
        t, dose, isf = dec[k][0], dec[k][3], dec[k][4]
        if dose is None or dose <= 0:
            continue
        isf = isf if (isf and ISF_MIN < isf < ISF_MAX) else isf_def
        i = bisect.bisect_left(cts, t)
        j = bisect.bisect_right(cts, t + WINDOW_MIN * 60)
        if j - i < 12:
            continue
        mins = (cts[i:j] - t) / 60.0
        # total insulin on board through the window, from the decision series
        idx = np.searchsorted(dts, cts[i:j])
        idx = np.clip(idx, 0, len(iobs) - 1)
        tot_iob = iobs[idx]
        out.append(dict(t=t, dose=dose, isf=isf, bg_at=dec[k][2], iob_at=dec[k][5],
                        mins=mins, bg=cbg[i:j], tot_iob=tot_iob,
                        own_iob=dose * iob_fraction(mins)))
    return out


def evaluate(w, mult, isf_scale=1.0, low=None):
    """Vectorised over an array of multipliers. Returns per-replicate metrics."""
    low = LOW if low is None else low
    mult = np.atleast_1d(np.asarray(mult, float))
    removed = w["dose"] * (1.0 - mult)                       # (R,)
    lift = removed[:, None] * (w["isf"] * isf_scale) * acted(w["mins"])[None, :]
    cf = w["bg"][None, :] + lift
    dt = np.gradient(w["mins"])
    below = np.clip(low - cf, 0, None) @ dt
    above = np.clip(cf - HIGH, 0, None) @ dt
    obs_below = float(np.clip(low - w["bg"], 0, None) @ dt)
    obs_above = float(np.clip(w["bg"] - HIGH, 0, None) @ dt)
    return dict(
        removed=removed,
        nadir=cf.min(axis=1), peak=cf.max(axis=1),
        low=(cf.min(axis=1) < low).astype(int),
        severe=(cf.min(axis=1) < SEVERE).astype(int),
        below=below, above=above,
        d_below=obs_below - below, d_above=above - obs_above,
        obs_nadir=float(w["bg"].min()), obs_peak=float(w["bg"].max()),
        obs_low=int(w["bg"].min() < low), obs_severe=int(w["bg"].min() < SEVERE),
        obs_below=obs_below, obs_above=obs_above)


def _chunk(payload):
    windows, mults, scale, low = payload
    return [evaluate(w, m, scale, low) for w, m in zip(windows, mults)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="tim"); ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--reps", type=int, default=3000)
    ap.add_argument("--lo", type=float, default=0.4); ap.add_argument("--hi", type=float, default=1.0)
    ap.add_argument("--outdir", default="figs")
    ap.add_argument("--low", type=float, default=TING_LOW,
                    help="nadir threshold; 63 is the TING floor, 70 the conventional one")
    args = ap.parse_args()
    globals()["LOW"] = args.low
    os.makedirs(args.outdir, exist_ok=True)

    conn = psycopg2.connect("dbname=oref"); conn.autocommit = True
    dec, cts, cbg = fetch(conn, args.user, args.days)
    globals()["LOW"] = args.low
    W = build(dec, cts, cbg)
    n = len(W)
    obs_low = sum(w["bg"].min() < LOW for w in W)
    obs_sev = sum(w["bg"].min() < SEVERE for w in W)
    print(f"{args.user}: {n} confirms over {args.days} days, "
          f"{sum(w['dose'] for w in W):.1f} U committed")
    print(f"  windows containing a low {obs_low}, severe {obs_sev}")
    print(f"  sensitivity median {np.median([w['isf'] for w in W]):.0f} mg/dL/U "
          f"({np.min([w['isf'] for w in W]):.0f} to {np.max([w['isf'] for w in W]):.0f})")
    print(f"  multiplier uniform on [{args.lo}, {args.hi}], {args.reps} replicates, "
          f"{os.cpu_count()} cores\n")
    res = dict(user=args.user, days=args.days, n=n, reps=args.reps,
               lo=args.lo, hi=args.hi, obs_low=obs_low, obs_severe=obs_sev,
               committed=float(sum(w["dose"] for w in W)))

    # ---- attribution, in quantities that are actually defined
    # sug_iob is NET insulin on board and is negative on 27% of cycles when basal is
    # suppressed below profile, so it cannot serve as the denominator of a share. What is
    # well defined is the confirm's own bolus still present at the nadir, and the glucose
    # deficit the model attributes to it by then.
    nadir_k = [int(np.argmin(w["bg"])) for w in W]
    own_at_nadir = np.array([w["own_iob"][k] for w, k in zip(W, nadir_k)])
    impact = np.array([w["isf"] * w["dose"] * acted(w["mins"][k]) for w, k in zip(W, nadir_k)])
    net_at_nadir = np.array([w["tot_iob"][k] for w, k in zip(W, nadir_k)])
    # insulin works against the meal, so the fall it has to explain is measured from the
    # peak of the excursion rather than from the glucose at the confirm
    fall = np.array([w["bg"][:int(np.argmin(w["bg"])) + 1].max() - w["bg"].min() for w in W])
    covered = np.clip(impact / np.maximum(fall, 1.0), 0, 3)
    res["attribution"] = dict(own_at_nadir=float(np.median(own_at_nadir)),
                              impact=float(np.median(impact)),
                              covered=float(np.median(covered)))
    print("=" * 78)
    print("1. WHAT THE CONFIRM ITSELF CONTRIBUTES BY THE TIME OF THE NADIR")
    print("=" * 78)
    print("  The recorded insulin on board is a NET figure and is negative on a quarter of")
    print("  cycles, so it cannot be the denominator of a share. Reported instead: the")
    print("  confirm's own bolus still present, and the glucose deficit the model attributes")
    print("  to it, against the fall actually observed.\n")
    print(f"  {'quantity':46s} {'median':>8s} {'quartiles':>18s}")
    for lab, v in (("confirm's own bolus still on board at nadir (U)", own_at_nadir),
                   ("glucose deficit attributed to it by then (mg/dL)", impact),
                   ("observed fall, peak to nadir (mg/dL)", fall),
                   ("net insulin on board at the nadir (U)", net_at_nadir)):
        print(f"  {lab:46s} {np.nanmedian(v):8.2f} "
              f"{np.nanpercentile(v,25):8.2f} to {np.nanpercentile(v,75):.2f}")
    print(f"\n  ratio of attributed deficit to observed fall: median {np.median(covered):.2f}")
    print("  A ratio near or above one means the model already accounts for the whole fall,")
    print("  and the confirm is the plausible cause. Well below one means other insulin,")
    print("  or the meal ending, did most of it and reducing the confirm will not prevent it.")
    for lo_, hi_ in ((0, .5), (.5, 1.0), (1.0, 3.1)):
        m = (covered >= lo_) & (covered < hi_)
        if m.sum() == 0:
            continue
        lows = sum(W[i]["bg"].min() < LOW for i in np.flatnonzero(m))
        print(f"    ratio {lo_:.1f}-{hi_:.1f}: {m.sum():3d} confirms, {lows:3d} with a low")
    print()
    share = covered      # used only for marker size in the charts

    # ---- randomised trial, parallel over confirms
    rng = np.random.default_rng(20260813)
    mults = [rng.uniform(args.lo, args.hi, args.reps) for _ in W]
    per_scale = {}
    with ProcessPoolExecutor(max_workers=min(os.cpu_count(), 14)) as ex:
        for sc in ISF_SCALES:
            k = max(1, n // 14)
            parts = [(W[i:i + k], mults[i:i + k], sc, args.low) for i in range(0, n, k)]
            out = []
            for r in ex.map(_chunk, parts):
                out.extend(r)
            per_scale[sc] = out
    print("=" * 78)
    print("2. THE RANDOMISED TRIAL")
    print("=" * 78)
    print(f"  Counts are per replicate across all {n} confirms.\n")
    print(f"  {'insulin effect':>15s} {'lows':>16s} {'severe':>15s} {'new highs':>13s}")
    res["trial"] = {}
    for sc in ISF_SCALES:
        o = per_scale[sc]
        lows = np.sum([x["low"] for x in o], axis=0)
        sev = np.sum([x["severe"] for x in o], axis=0)
        nh = np.sum([(x["above"] > 0) & (x["obs_above"] == 0) for x in o], axis=0)
        f = lambda a: f"{np.median(a):.0f} [{np.percentile(a,2.5):.0f},{np.percentile(a,97.5):.0f}]"
        print(f"  {'x'+str(sc):>15s} {f(lows):>16s} {f(sev):>15s} {f(nh):>13s}")
        res["trial"][sc] = dict(lows=float(np.median(lows)), severe=float(np.median(sev)),
                                new_highs=float(np.median(nh)))
    print(f"  {'observed':>15s} {obs_low:>16d} {obs_sev:>15d} {0:>13d}")
    removed_tot = np.sum([x["removed"] for x in per_scale[1.0]], axis=0)
    print(f"\n  insulin withheld per replicate: median {np.median(removed_tot):.1f} U of "
          f"{sum(w['dose'] for w in W):.1f} ({100*np.median(removed_tot)/sum(w['dose'] for w in W):.0f}%)")

    # ---- how much less bad / how much worse
    print()
    print("=" * 78)
    print("3. HOW MUCH LESS BAD, AND HOW MUCH WORSE")
    print("=" * 78)
    print("  Depth is the area outside range in mg/dL.min within the window. Pooled over")
    print("  replicates and confirms, at the recorded sensitivity.\n")
    o = per_scale[1.0]
    had_low = [i for i, w in enumerate(W) if w["bg"].min() < LOW]
    had_none = [i for i in range(n) if i not in had_low]
    db = np.concatenate([o[i]["d_below"] for i in had_low])
    dn = np.concatenate([o[i]["nadir"] - o[i]["obs_nadir"] for i in had_low])
    da = np.concatenate([o[i]["d_above"] for i in range(n)])
    dp = np.concatenate([o[i]["peak"] - o[i]["obs_peak"] for i in range(n)])
    print(f"  windows that contained a low ({len(had_low)}):")
    print(f"    nadir rises by      median {np.median(dn):6.1f} mg/dL  "
          f"[{np.percentile(dn,10):.0f}, {np.percentile(dn,90):.0f}]")
    print(f"    depth below 70 falls median {np.median(db):6.0f} mg/dL.min  "
          f"({100*np.mean(db>0):.0f}% of draws improve it)")
    print(f"  all windows ({n}):")
    print(f"    peak rises by       median {np.median(dp):6.1f} mg/dL  "
          f"[{np.percentile(dp,10):.0f}, {np.percentile(dp,90):.0f}]")
    print(f"    depth above 180 rises median {np.median(da):5.0f} mg/dL.min")
    res["severity"] = dict(nadir_gain=float(np.median(dn)), below_gain=float(np.median(db)),
                           peak_gain=float(np.median(dp)), above_gain=float(np.median(da)))

    # ---- charts
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.dpi": 130, "font.size": 9, "axes.grid": True,
                         "grid.alpha": .3, "axes.spines.top": False, "axes.spines.right": False})

    # a: dose response with the sensitivity band
    grid = np.arange(0.40, 1.001, 0.05)
    fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.6))
    for lab, key, a_ in (("windows with a low", "low", ax[0]), ("severe", "severe", ax[0])):
        for sc, style in zip(ISF_SCALES, (":", "-", ":")):
            y = [sum(int(evaluate(w, m, sc, args.low)[key][0]) for w in W) for m in grid]
            a_.plot(grid, y, style, lw=2 if sc == 1.0 else 1,
                    label=f"{lab} x{sc}" if sc == 1.0 else None,
                    color="tab:red" if key == "low" else "tab:purple", alpha=1 if sc == 1 else .5)
    ax[0].axhline(obs_low, color="tab:red", ls="--", lw=.8)
    ax[0].axhline(obs_sev, color="tab:purple", ls="--", lw=.8)
    ax[0].set_xlabel("confirm multiplier"); ax[0].set_ylabel("windows")
    ax[0].set_title("Hypoglycaemia against the reduction\n(dotted: insulin effect halved and doubled)")
    ax[0].legend(frameon=False, fontsize=8)
    for sc, style in zip(ISF_SCALES, (":", "-", ":")):
        y = [sum(int(evaluate(w, m, sc, args.low)["above"][0] > 0) for w in W) for m in grid]
        ax[1].plot(grid, y, style, lw=2 if sc == 1.0 else 1, color="tab:orange",
                   alpha=1 if sc == 1 else .5, label="windows above 180" if sc == 1.0 else None)
    ax[1].axhline(sum(int(w["bg"].max() > HIGH) for w in W), color="tab:orange", ls="--", lw=.8)
    ax[1].set_xlabel("confirm multiplier"); ax[1].set_ylabel("windows")
    ax[1].set_title("Hyperglycaemia against the reduction")
    ax[1].legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(f"{args.outdir}/01_dose_response.png"); plt.close(fig)

    # b: the trade, lows removed against highs added
    fig, ax = plt.subplots(figsize=(5.2, 4))
    for sc, mk in zip(ISF_SCALES, ("^", "o", "v")):
        xs, ys = [], []
        for m in grid:
            xs.append(sum(int(evaluate(w, m, sc, args.low)["above"][0] > 0) for w in W)
                      - sum(int(w["bg"].max() > HIGH) for w in W))
            ys.append(obs_low - sum(int(evaluate(w, m, sc, args.low)["low"][0]) for w in W))
        ax.plot(xs, ys, mk + "-", ms=4, lw=1.2, alpha=1 if sc == 1 else .45,
                label=f"insulin effect x{sc}")
    ax.set_xlabel("extra windows taken above 180"); ax.set_ylabel("windows rescued from a low")
    ax.set_title("What the reduction trades")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(f"{args.outdir}/02_trade.png"); plt.close(fig)

    # c: per confirm, insulin withheld against nadir gained, sized by IOB share
    half = [evaluate(w, 0.5, 1.0, args.low) for w in W]
    fig, ax = plt.subplots(figsize=(6, 4.2))
    gain = np.array([h["nadir"][0] - h["obs_nadir"] for h in half])
    rem = np.array([h["removed"][0] for h in half])
    resc = np.array([bool(h["obs_low"] and not h["low"][0]) for h in half])
    sh = np.clip(np.nan_to_num(share, nan=0.2), 0, 1.5) / 1.5
    sc_ = ax.scatter(rem[~resc], gain[~resc], s=20 + 120 * sh[~resc], c="tab:grey",
                     alpha=.5, label="low remains or none present")
    ax.scatter(rem[resc], gain[resc], s=20 + 120 * sh[resc], c="tab:green",
               alpha=.75, label="low removed")
    ax.set_xlabel("insulin withheld at a 0.5 multiplier (U)")
    ax.set_ylabel("nadir raised (mg/dL)")
    ax.set_title("Per confirm, halved individually\nmarker size is how much of the fall the confirm accounts for")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(f"{args.outdir}/03_per_confirm.png"); plt.close(fig)

    # d: nadir distribution, observed against counterfactual
    fig, ax = plt.subplots(figsize=(5.6, 3.8))
    bins = np.arange(30, 200, 10)
    ax.hist([w["bg"].min() for w in W], bins=bins, alpha=.65, label="observed", color="tab:red")
    ax.hist([h["nadir"][0] for h in [evaluate(w, 0.8, 1.0, args.low) for w in W]], bins=bins, alpha=.6,
            label="at a 0.8 multiplier", color="tab:blue")
    ax.axvline(LOW, color="k", ls="--", lw=.8); ax.axvline(SEVERE, color="k", ls=":", lw=.8)
    ax.set_xlabel("nadir in the four hours after a confirm (mg/dL)"); ax.set_ylabel("confirms")
    ax.set_title("Where the nadir sits"); ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(f"{args.outdir}/04_nadir.png"); plt.close(fig)

    # e: the confirm's own BGI, and what the reduction removes from it
    fig, ax = plt.subplots(figsize=(5.8, 3.8))
    mm = np.arange(0, WINDOW_MIN + 1, 5)
    med_dose = float(np.median([w["dose"] for w in W]))
    med_isf = float(np.median([w["isf"] for w in W]))
    for m, c_ in ((1.0, "tab:red"), (0.8, "tab:orange"), (0.6, "tab:blue")):
        ax.plot(mm, -med_isf * med_dose * m * activity(mm) * 5, color=c_, lw=1.6,
                label=f"multiplier {m:.1f}")
    ax.set_xlabel("minutes after the confirm")
    ax.set_ylabel("glucose impact of the confirm (mg/dL per 5 min)")
    ax.set_title(f"The confirm's own BGI\nmedian confirm {med_dose:.2f} U at {med_isf:.0f} mg/dL/U")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(f"{args.outdir}/05_bgi.png"); plt.close(fig)

    # f: IOB share against benefit
    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    ok = np.isfinite(share)
    ax.scatter(share[ok], gain[ok], s=26, c=["tab:green" if r else "tab:grey" for r in resc[ok]],
               alpha=.7)
    ax.set_xlabel("attributed deficit / observed fall")
    ax.set_ylabel("nadir raised at a 0.5 multiplier (mg/dL)")
    ax.set_title("Attribution: benefit against how much of the fall\nthe confirm can account for")
    fig.tight_layout(); fig.savefig(f"{args.outdir}/06_attribution.png"); plt.close(fig)

    print(f"\n  wrote 6 charts to {args.outdir}/")
    json.dump(res, open(f"{args.outdir}/../trial_summary.json", "w"), indent=2, default=float)
    print(f"  wrote trial_summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
