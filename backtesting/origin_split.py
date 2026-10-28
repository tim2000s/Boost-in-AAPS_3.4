#!/usr/bin/env python3
"""
Origin-split of V5 fresh-CONFIRMED transitions — the analysis behind the 2026-06-26 dosing fix
(fast-path no longer fires from a cold IDLE; see MealHypothesis.kt / .swift).

Reuses replay.py's NS reconstruction (cached per user). For every fresh CONFIRMED transition in the
logged data it records the ORIGIN state (the prior cycle's state: IDLE vs OBSERVING vs other) and
classifies the outcome from the subsequent BG trajectory:
  - sustained-rise (peak ≥ +15 mg/dL over next 6 cycles)  → genuine meal
  - reversed-transient (fell ≥5 mg/dL below confirm BG within 4 cycles, no material peak) → false fire
  - led-to-undershoot (BG ≤ 80 mg/dL within 12 cycles)    → over-treatment

Finding (30 d × 5 users, 525 confirms): IDLE→CONFIRMED fired exactly ONCE and that fire was the
false-positive that undershot; all 495 OBSERVING-origin confirms unaffected (61% sustained). Hence
dropping the cold-IDLE fast-path branch costs zero real meals.

USAGE: python3 origin_split.py   (run from this directory; uses replay.py + its cache)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json

import replay  # noqa: E402  reuse load() + CONFIG_PATH

WINDOW_DAYS = 30
FOLLOW = 4  # cycles (~20 min)


def classify(cyc, j):
    """Classify an actual fresh CONFIRMED at index j by subsequent BG."""
    bg_c = cyc[j]["bg"]
    if bg_c is None:
        return None
    fwd = [cyc[k]["bg"] for k in range(j + 1, min(j + 7, len(cyc))) if cyc[k]["bg"]]
    if not fwd:
        return None
    peak = max(fwd)
    trough_win = [cyc[k]["bg"] for k in range(j + 1, min(j + 13, len(cyc))) if cyc[k]["bg"]]
    trough = min(trough_win) if trough_win else bg_c
    near = [cyc[k]["bg"] for k in range(j + 1, min(j + 5, len(cyc))) if cyc[k]["bg"]]
    reversed_q = bool(near) and min(near) <= bg_c - 5 and peak - bg_c < 15
    return {
        "sustained": (peak - bg_c) >= 15,
        "reversed": reversed_q,
        "undershoot": trough <= 80,
    }


def analyze(cyc):
    res = {}
    for j in range(len(cyc)):
        if cyc[j]["state"] == "CONFIRMED" and (j == 0 or cyc[j - 1]["state"] != "CONFIRMED"):
            origin = cyc[j - 1]["state"] if j > 0 else "?"
            o = origin if origin in ("IDLE", "OBSERVING") else "other"
            c = classify(cyc, j)
            if c is not None:
                res.setdefault(o, []).append(c)
    return res


def main():
    cfg = json.load(open(replay.CONFIG_PATH))
    pool = {}
    print(f"per-user fresh-CONFIRMED origin split ({WINDOW_DAYS}d):")
    for site in cfg["sites"]:
        tag = site["tag"]
        try:
            data = replay.load(site, WINDOW_DAYS, use_cache=True)
        except Exception as e:  # noqa: BLE001
            print(f"  [{tag}] {e}")
            continue
        r = analyze(data["cyc"])
        print(f"  [{tag}] " + " ".join(f"{o}={len(r.get(o, []))}" for o in ("IDLE", "OBSERVING", "other")))
        for o in ("IDLE", "OBSERVING", "other"):
            pool.setdefault(o, []).extend(r.get(o, []))

    print("\n=== POOLED: classification by origin ===")
    for o in ("IDLE", "OBSERVING", "other"):
        L = pool.get(o, [])
        n = len(L)
        if not n:
            continue
        sus = sum(x["sustained"] for x in L)
        rev = sum(x["reversed"] for x in L)
        under = sum(x["undershoot"] for x in L)
        print(f"  {o:9s} n={n:4d} | sustained {sus:4d} ({sus * 100 // n}%) | "
              f"reversed-transient {rev:4d} ({rev * 100 // n}%) | undershoot {under:4d} ({under * 100 // n}%)")


if __name__ == "__main__":
    main()
