#!/usr/bin/env python3
"""Render the result JSONs as the markdown tables the report carries.

Every number in the report comes from here, so that none of them is typed by hand.
"""
import argparse, json, os

def f(x, n=3):
    return "n/a" if x is None or x != x else f"{x:.{n}f}"

def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--data", default=os.path.join(here, "out"))
    ap.add_argument("--study", default="Loop")
    a = ap.parse_args()
    R = json.load(open(os.path.join(a.data, f"results_{a.study}.json")))
    S = json.load(open(os.path.join(a.data, f"slopes_{a.study}.json")))

    print(f"## Primary endpoint: large against small, participants held out ({a.study})\n")
    for arm in sorted({r["arm"] for r in R["classification"]}):
        print(f"\n### Arm {arm}\n")
        print("| stratum | horizon | meals | participants | AUC | 95% interval | raw rise alone | model minus raw | caught at 10% FPR |")
        print("|---|---|---|---|---|---|---|---|---|")
        for r in R["classification"]:
            if r["arm"] != arm:
                continue
            print(f"| {r['stratum']} | {r['horizon']} min | {r['n']:,} | {r['subjects']} | "
                  f"{f(r['auc'])} | {f(r['lo'])} to {f(r['hi'])} | {f(r['auc_raw_rise'])} | "
                  f"{r['delta_vs_raw']:+.3f} | {f(r['tpr_at_10fpr'],2)} |")

    print("\n## Size as a quantity, against the baseline ladder\n")
    print("| arm | horizon | meals | MAE g | population median | time-of-day median | participant median | correlation |")
    print("|---|---|---|---|---|---|---|---|")
    for q in R["quantity"]:
        print(f"| {q['arm']} | {q['horizon']} min | {q['n']:,} | {f(q['mae'],1)} | "
              f"{f(q['mae_median'],1)} | {f(q['mae_tod_median'],1)} | {f(q['mae_subject_median'],1)} | "
              f"{q['corr']:+.3f} |")

    print("\n## Per-participant slope of glucose rise on announced carbohydrate\n")
    print("| stratum | horizon | participants | pooled slope | 95% interval | tau | I squared | true slopes below zero | individually below zero |")
    print("|---|---|---|---|---|---|---|---|---|")
    for p in S["pooled"]:
        if "mu" not in p:
            continue
        print(f"| {p['stratum']} | {p['horizon']} min | {p['k']} | {p['mu']:+.4f} | "
              f"{p['ci_lo']:+.4f} to {p['ci_hi']:+.4f} | {f(p['tau'],4)} | {p['i2']:.0f}% | "
              f"{p['share_true_negative']*100:.0f}% | {p['share_sig_negative']*100:.0f}% |")

    if S.get("within"):
        print("\n## Within participant: slope on unbolused meals minus slope on bolused meals\n")
        print("| horizon | participants | difference | 95% interval | unbolused | bolused | share positive |")
        print("|---|---|---|---|---|---|---|")
        for w in S["within"]:
            print(f"| {w['horizon']} min | {w['n_subjects']} | {w['mean_diff']:+.4f} | "
                  f"{w['ci_lo']:+.4f} to {w['ci_hi']:+.4f} | {w['mean_b_unbolused']:+.4f} | "
                  f"{w['mean_b_bolused']:+.4f} | {w['share_unbolused_gt_bolused']*100:.0f}% |")

    decomposition(a.data, a.study)
    signal_to_noise(a.data, a.study)




def decomposition(data, study="Loop"):
    """What the glucose trace adds once the person and the clock are already known.

    Each trajectory arm is matched to the arm carrying the same information about the person and
    the clock with the trace removed. The difference is the only quantity that speaks to whether
    a controller can size the meal in front of it.
    """
    import itertools
    R = json.load(open(os.path.join(data, f"results_{study}.json")))
    B = json.load(open(os.path.join(data, f"results_{study}_baselines.json")))
    idx = {}
    for r in itertools.chain(R["classification"], B["classification"]):
        idx[(r["arm"], r["stratum"], r["horizon"])] = r
    pairs = [(1, 10, "trajectory and clock", "clock alone"),
             (3, 13, "everything", "person, history and clock")]
    print("\n## What the glucose trace adds once the person and the clock are known\n")
    print("| stratum | horizon | with the trace | without it | difference |")
    print("|---|---|---|---|---|")
    for st in ("all", "none"):
        for h in (10, 60):
            for arm, base, _, _ in pairs:
                a, b = idx.get((arm, st, h)), idx.get((base, st, h))
                if not a or not b:
                    continue
                print(f"| {st} | {h} min | {a['auc']:.3f} [{a['lo']:.3f} to {a['hi']:.3f}] | "
                      f"{b['auc']:.3f} [{b['lo']:.3f} to {b['hi']:.3f}] | "
                      f"{a['auc'] - b['auc']:+.3f} |")


def signal_to_noise(data, study="Loop"):
    """The size signal against the variability of the rise it has to be read out of."""
    import pandas as pd
    S = json.load(open(os.path.join(data, f"slopes_{study}.json")))
    d = pd.read_parquet(os.path.join(data, f"meals_{study}.parquet"),
                        columns=["bolus_stratum"] + [f"h{h}_rise" for h in (10, 15, 20, 30, 45, 60)])
    u = d[d.bolus_stratum == "none"]
    print("\n## The size signal against the spread of the rise, unbolused meals\n")
    print("| horizon | slope, mg/dL per gram | 20 g against 60 g | spread of the rise | ratio |")
    print("|---|---|---|---|---|")
    for p in S["pooled"]:
        if p.get("stratum") != "none" or "mu" not in p:
            continue
        h = p["horizon"]
        sd = float(u[f"h{h}_rise"].std())
        sep = p["mu"] * 40
        print(f"| {h} min | {p['mu']:+.4f} | {sep:.2f} mg/dL | {sd:.2f} mg/dL | {sep / sd:.3f} |")


if __name__ == "__main__":
    main()
