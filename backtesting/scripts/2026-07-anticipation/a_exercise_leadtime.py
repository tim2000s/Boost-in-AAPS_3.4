#!/usr/bin/env python3
"""A — Does a habit prior fire BEFORE the reactive steps signal? (2026-07-09)

The gating question for anticipatory hypo-prep: Boost already reacts to steps (validated leading
indicator ~3h). A clock/weekday habit prior only ADDS value if it fires *before* the person actually
moves — i.e. it can pre-arm the prep at habitual exercise times even when steps are still zero.

Method:
  * Define an activity episode = steps_60m crosses the user's 80th pct (the reactive-fire moment).
  * Fit P(active_next_60min | hour, weekday) on the FIRST 60% of each user's timeline (Beta-Binomial
    empirical-Bayes rate per (weekday, 30-min bin), shrunk toward the user's base rate).
  * On the held-out last 40%: at each pre-onset cycle, does the habit posterior already exceed a
    prep threshold BEFORE steps cross? Measure the LEAD TIME (minutes the habit prior leads the
    reactive signal) and the precision (of prep-armed windows, how many actually saw exercise).

Bayesian: the per-cell Beta posterior gives calibrated rates for sparse (weekday,time) cells and a
lower credible bound to gate the prep on (asymmetric loss: missing exercise → hypo ≫ false prep).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(__file__))
import anticip_common as ac  # noqa

BIN = 30                 # minute bin for the habit prior
PREP_THRESH = 0.35       # posterior-mean threshold to "arm prep"
ALPHA0, BETA0 = 1.0, 1.0  # Beta prior


def beta_rate(k, n, base, strength=20):
    """Empirical-Bayes rate: shrink the cell rate toward the user's base by a pseudo-count."""
    a = ALPHA0 + k + base * strength
    b = BETA0 + (n - k) + (1 - base) * strength
    mean = a / (a + b)
    lo = mean - 1.64 * np.sqrt(mean * (1 - mean) / (a + b))   # ~lower 90% bound
    return mean, max(0.0, lo)


def main():
    df = ac.load()
    print("=== A. Exercise anticipation — does the habit prior LEAD the reactive steps signal? ===\n")
    print(f"{'user':>5} {'thr(st)':>8} {'episodes':>9} {'prior_AUC':>10} {'armed_prec':>11} "
          f"{'lead_med':>9} {'%eps_prearmed':>13}")
    rows = []
    for u, g in df.groupby("user_id"):
        g = g.sort_values("ts_epoch").reset_index(drop=True)
        thr = np.nanpercentile(g.steps_60m.dropna(), 80)
        if not np.isfinite(thr) or thr < 30:
            print(f"{u:>5}  (insufficient step activity)")
            continue
        g["active"] = (g.steps_60m > thr).astype(int)
        # future active within 60 min
        ts = g.ts_epoch.values
        act = g.active.values
        fut = np.zeros(len(g), int)
        k = 0
        for i in range(len(g)):
            while k < len(g) and ts[k] <= ts[i] + 3600:
                k += 1
            fut[i] = 1 if act[i + 1:k].any() else 0
        g["fut_active"] = fut
        cut = int(len(g) * 0.6)
        tr, te = g.iloc[:cut], g.iloc[cut:]
        base = tr.fut_active.mean()
        # habit table: P(fut_active | weekday, 30-min bin) from train
        tr = tr.assign(tb=(tr.minute // BIN))
        cell = tr.groupby(["dow", "tb"]).fut_active.agg(["sum", "count"])
        prior = {idx: beta_rate(r["sum"], r["count"], base) for idx, r in cell.iterrows()}
        # apply to test
        tb_te = (te.minute // BIN).values
        dow_te = te.dow.values
        pm = np.array([prior.get((d, t), (base, 0.0))[0] for d, t in zip(dow_te, tb_te)])
        y = te.fut_active.values
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(y, pm) if len(np.unique(y)) > 1 else float("nan")
        armed = pm >= PREP_THRESH
        prec = y[armed].mean() if armed.any() else float("nan")   # of armed windows, frac that saw exercise

        # LEAD TIME: for each test activity-episode ONSET, how long before it did the prior first exceed
        # threshold (searching back up to 3h)?
        te = te.reset_index(drop=True)
        tsm = te.ts_epoch.values
        acte = te.active.values
        onsets = [i for i in range(len(te)) if acte[i] and (i == 0 or not acte[i - 1])]
        leads = []
        prearmed = 0
        for oi in onsets:
            lead = 0
            j = oi
            while j >= 0 and tsm[oi] - tsm[j] <= 3600:
                if pm[j] >= PREP_THRESH:
                    lead = (tsm[oi] - tsm[j]) / 60
                    j -= 1
                    continue
                break
            if lead > 0:
                prearmed += 1
            leads.append(lead)
        lead_med = np.median([l for l in leads if l > 0]) if any(l > 0 for l in leads) else 0
        pct_pre = 100 * prearmed / len(onsets) if onsets else 0
        rows.append((u, auc, prec, lead_med, pct_pre))
        print(f"{u:>5} {thr:>8.0f} {len(onsets):>9} {auc:>10.2f} "
              f"{prec if not np.isnan(prec) else 0:>11.2f} {lead_med:>7.0f}m {pct_pre:>12.0f}%")

    r = pd.DataFrame(rows, columns=["u", "auc", "prec", "lead", "pct"])
    print("\n--- verdict ---")
    print(f"habit-prior OOS AUC (time only): median {r.auc.median():.2f}")
    print(f"of episodes the prior PRE-ARMED (fired before onset): median {r.pct.median():.0f}%, "
          f"median lead {r.lead.median():.0f} min")
    print(f"armed-window precision: median {r.prec.median():.2f} "
          f"(frac of prep-armed windows that actually saw exercise)")
    print("Read: lead>0 with decent precision ⇒ the habit prior pre-arms hypo-prep BEFORE the person "
          "moves, adding lead over Boost's reactive steps signal. Low precision ⇒ too many false preps.")


if __name__ == "__main__":
    main()
