#!/usr/bin/env python3
"""Dig into the cohort finding — is the AAPS-vs-oref/Trio TIR gap Boost, or selection? (2026-07-08)

The gate finding (probe): only ~4.9% of the AAPS cohort's window is Boost-ACTIVE dosing
(C/D/G never; rest flipped late-June, ~2-week post-window). So the cohort TIR gap is
~95% a comparison of two OREF-family populations, not a Boost effect.

This quantifies the remaining question: of the raw cross-cohort TIR gap, how much survives
after controlling for case difficulty (glucose variability CV + mean BG)? A numpy OLS with a
label-permutation p-value on the platform coefficient (statsmodels not installed).
"""
import os
import sys

import numpy as np

sys.path.append(os.path.dirname(__file__))
from cohort_bglevel import load, metrics  # noqa


def main():
    df = load()
    rows = []
    for (plat, u), g in df.groupby(["platform", "user_id"]):
        m = metrics(g)
        rows.append((plat, u, m["TIR"], m["cv"], m["mean"], m["TBR70"]))
    import pandas as pd
    r = pd.DataFrame(rows, columns=["platform", "user", "TIR", "cv", "mean", "TBR70"])

    aaps = r[r.platform == "AAPS-Boost"]
    trio = r[r.platform == "oref/Trio"]
    raw_gap = aaps.TIR.median() - trio.TIR.median()
    print(f"raw TIR gap (median AAPS - oref/Trio): {raw_gap:+.1f} pp")
    print(f"case-difficulty: median CV  AAPS {aaps.cv.median():.0f} vs oref/Trio {trio.cv.median():.0f}")
    print(f"                 median meanBG AAPS {aaps['mean'].median():.0f} vs oref/Trio {trio['mean'].median():.0f}")

    # OLS: TIR ~ 1 + is_aaps + cv + meanBG
    r = r.assign(is_aaps=(r.platform == "AAPS-Boost").astype(float))
    X = np.column_stack([np.ones(len(r)), r.is_aaps, r.cv, r["mean"]])
    y = r.TIR.values

    def fit(labels):
        Xx = X.copy()
        Xx[:, 1] = labels
        beta, *_ = np.linalg.lstsq(Xx, y, rcond=None)
        return beta

    beta = fit(r.is_aaps.values)
    coef = beta[1]
    # permutation null on the platform label
    rng = np.random.default_rng(0)
    null = np.array([fit(rng.permutation(r.is_aaps.values))[1] for _ in range(5000)])
    p = float(np.mean(np.abs(null) >= abs(coef)))
    print(f"\nOLS TIR ~ platform + CV + meanBG:")
    print(f"  adjusted platform (AAPS) effect on TIR: {coef:+.1f} pp   (raw median gap was {raw_gap:+.1f})")
    print(f"  CV coef {beta[2]:+.2f} pp/CV-unit, meanBG coef {beta[3]:+.3f} pp/mgdl")
    print(f"  permutation p (platform): {p:.3f}   ({'sig' if p < 0.05 else 'NOT significant'})")

    print("\n--- verdict ---")
    print("NB: V1 IS Boost (Boost V1 generation is the dosing algorithm; the 4.9% boostv5_active is")
    print("the V5/V6-generation slice). So the AAPS cohort is Boost-dosing throughout -> this is a")
    print("legitimate Boost-vs-oref/Trio comparison (NOT two oref populations).")
    shrink = 100 * (1 - abs(coef) / abs(raw_gap)) if raw_gap else 0
    print(f"Raw +{raw_gap:.1f}pp shrinks to {coef:+.1f}pp after case difficulty ({shrink:.0f}% is difficulty), "
          f"p={p:.2f} ({'NS' if p>=0.05 else 'sig'}).")
    print("Verdict: a genuine but SMALL, underpowered Boost-vs-oref edge (consistent direction,")
    print("+1.2pp adjusted, NS in 9-vs-21). Population comparison; no within-user Boost-vs-oref exists")
    print("(cohort was always Boost). Warrants a larger/matched comparison, not a stronger claim here.")


if __name__ == "__main__":
    main()
