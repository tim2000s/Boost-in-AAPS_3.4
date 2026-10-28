"""Render the tables in REPORT.md from the four result files, so nothing is hand-copied."""

from __future__ import annotations

import json
import os

import common


def load(name):
    p = os.path.join(common.OUT, name)
    return json.load(open(p)) if os.path.exists(p) else None


def ci(v):
    return f"{v[0]:.3f} ({v[1]:.3f} to {v[2]:.3f})"


def delta(d):
    return f"{d['delta']:+.4f} ({d['lo']:+.4f} to {d['hi']:+.4f})"


def c1():
    d = load("c1_hypo_scale.json")
    if not d:
        return
    print("\n### C1 hypo risk, training-set size\n")
    print("| horizon | base rate | clock | loop state | eventualBG | 7 | 28 | 112 | all 146 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for tag in ("1h", "4h"):
        if tag not in d:
            continue
        a = d[tag]["auc"]
        print(f"| {tag} | {d[tag]['base_rate']:.3f} | {a['base_clock'][0]:.3f} | "
              f"{a['base_loop'][0]:.3f} | {a['eventualbg'][0]:.3f} | {a['n7'][0]:.3f} | "
              f"{a['n28'][0]:.3f} | {a['n112'][0]:.3f} | {a['nall'][0]:.3f} |")
    print("\n| horizon | comparison | paired difference (95% CI) | verdict |")
    print("|---|---|---|---|")
    for tag in ("1h", "4h"):
        if tag not in d:
            continue
        for k, v in d[tag]["paired"].items():
            print(f"| {tag} | {k} | {delta(v)} | {v['verdict']} |")


def c2():
    d = load("c2_fall_consequence.json")
    if not d:
        return
    print("\n### C2 fall consequence\n")
    print("| cohort | label | h | n | base rate | onset BG | + clock | + shape | "
          "loop state | eventualBG |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for coh in d:
        for kind in d[coh]:
            for hk, r in d[coh][kind].items():
                a = r["auc"]
                ls = f"{a['loopstate'][0]:.3f}" if "loopstate" in a else "-"
                eb = f"{a['eventualbg'][0]:.3f}" if "eventualbg" in a else "-"
                print(f"| {coh} | {kind} | {r['horizon_min']} | {r['n']:,} | "
                      f"{r['base_rate']:.3f} | {a['base_only'][0]:.3f} | "
                      f"{a['clock'][0]:.3f} | {a['shape'][0]:.3f} | {ls} | {eb} |")
    print("\n| cohort | label | h | comparison | paired difference (95% CI) | verdict |")
    print("|---|---|---|---|---|---|")
    for coh in d:
        for kind in d[coh]:
            for hk, r in d[coh][kind].items():
                for k, v in r["paired"].items():
                    print(f"| {coh} | {kind} | {r['horizon_min']} | {k} | {delta(v)} | "
                          f"{v['verdict']} |")


def c3():
    d = load("c3_post_low_rebound.json")
    if not d:
        return
    print("\n### C3 post-low rebound\n")
    print("| cohort | label | n | base rate | BG at recovery | + clock | + episode | "
          "+ loop state | eventualBG |")
    print("|---|---|---|---|---|---|---|---|---|")
    for coh in d:
        for kind, r in d[coh].items():
            a = r["auc"]
            lp = f"{a['loop'][0]:.3f}" if "loop" in a else "-"
            eb = f"{a['eventualbg'][0]:.3f}" if "eventualbg" in a else "-"
            print(f"| {coh} | {kind} | {r['n']:,} | {r['base_rate']:.3f} | "
                  f"{a['bg_only'][0]:.3f} | {a['clock'][0]:.3f} | {a['episode'][0]:.3f} | "
                  f"{lp} | {eb} |")
    print("\n| cohort | label | comparison | paired difference (95% CI) | verdict |")
    print("|---|---|---|---|---|")
    for coh in d:
        for kind, r in d[coh].items():
            for k, v in r["paired"].items():
                print(f"| {coh} | {kind} | {k} | {delta(v)} | {v['verdict']} |")


def c4():
    d = load("c4_fall_prior_ship.json")
    if not d:
        return
    print("\n### C4 transfer and the shipping form\n")
    print("| cohort | label | h | n | participants | within clock | within shape | "
          "external clock | external shape | external shape, logistic |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for coh in d:
        for kind in d[coh]:
            for hk, r in d[coh][kind].items():
                a = r["auc"]
                print(f"| {coh} | {kind} | {r['horizon_min']} | {r['n']:,} | "
                      f"{r['n_participants']} | {a['within_clock'][0]:.3f} | "
                      f"{a['within_shape'][0]:.3f} | {a['external_clock'][0]:.3f} | "
                      f"{a['external_shape'][0]:.3f} | "
                      f"{a['external_shape_logistic'][0]:.3f} |")
    print("\n| cohort | label | h | comparison | paired difference (95% CI) | verdict |")
    print("|---|---|---|---|---|---|")
    for coh in d:
        for kind in d[coh]:
            for hk, r in d[coh][kind].items():
                for k, v in r["paired"].items():
                    print(f"| {coh} | {kind} | {r['horizon_min']} | {k} | {delta(v)} | "
                          f"{v['verdict']} |")


if __name__ == "__main__":
    for f in (c1, c2, c3, c4):
        f()
