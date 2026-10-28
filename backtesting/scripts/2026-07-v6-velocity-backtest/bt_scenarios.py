#!/usr/bin/env python3
"""
Apply every scenario to every confirm cycle (all users) and produce DISTRIBUTION-based analysis.
Reads bt_confirms_<user>.json from OUT. Cheap (no DB) — the DB work is parallelised in bt_extract.

Because the counterfactual glucose can't be simulated, we cross-reference each meal's ACTUAL outcome
(crash / high-plateau / good, under the baseline shot that really fired) with what each scenario
DECIDES. A scenario "blocks" a confirm when its velocity-scaled prospective shot falls below the
confirm floor. The question: does blocking TARGET the bad meals (crashes + high plateaus) while
KEEPING the good ones?  Usage: python3 bt_scenarios.py <out_dir>
"""
import sys, json, glob, numpy as np
from bt_common import SCENARIOS, eval_scenario

OUT = sys.argv[1]
R = []
print("=== faithfulness: recomputed rise → velocityFactor vs the value V6 actually logged ===")
for f in sorted(glob.glob(f"{OUT}/bt_confirms_*.json")):
    d = json.load(open(f)); R += d['recs']
    print(f"  {d['user']:<5} n={d['n']:<4} vf MAE {d['vf_recompute_mae']}")
n = len(R)
print(f"\nTotal actual V6 confirm shots: {n}")
base_crash = np.mean([r['crash'] for r in R]); base_plat = np.mean([r['plateau_high'] for r in R])
print(f"Baseline confirm-shot outcomes: crash<70 {100*base_crash:.0f}%  high-plateau>140 {100*base_plat:.0f}%  "
      f"deep<54 {100*np.mean([r['deep'] for r in R]):.0f}%")

order = ['baseline', 'mild', 'target', 'steep', 'decoupled_target']
print("\n=== per scenario: confirm decisions + front-load, vs baseline ===")
print(f"{'scenario':<18}{'confirms':>9}{'blocked%':>9}{'front-load U':>14}{'ΔU%':>7}{'shot p50':>9}{'shot p90':>9}")
dec = {}
for scn in order:
    d = [eval_scenario(r, scn) for r in R]
    dec[scn] = d
    conf = [x[0] for x in d]; shots = np.array([x[1] for x in d])
    nb_conf = sum(conf); blocked = 100 * (1 - nb_conf / n)
    fl = shots.sum(); fl_base = np.array([eval_scenario(r, 'baseline')[1] for r in R]).sum()
    nz = shots[shots > 0]
    print(f"{scn:<18}{nb_conf:>9}{blocked:>8.0f}%{fl:>14.1f}{100*(fl/fl_base-1):>+6.0f}%"
          f"{np.percentile(nz,50) if len(nz) else 0:>9.2f}{np.percentile(nz,90) if len(nz) else 0:>9.2f}")

print("\n=== does BLOCKING target the bad meals? (of the confirms each scenario blocks) ===")
print(f"{'scenario':<18}{'blocks n':>9}{'were crash%':>13}{'were high-plat%':>16}{'were GOOD%':>12}  |  recall on crashes")
for scn in order:
    if scn == 'baseline': continue
    blocked = [R[i] for i in range(n) if not dec[scn][i][0]]
    if not blocked:
        print(f"{scn:<18}{0:>9}"); continue
    bc = np.mean([r['crash'] for r in blocked]); bp = np.mean([r['plateau_high'] for r in blocked])
    good = np.mean([(1 - r['crash']) * (1 - r['plateau_high']) for r in blocked])
    all_crash = sum(r['crash'] for r in R)
    recall = sum(r['crash'] for r in blocked) / all_crash if all_crash else 0
    print(f"{scn:<18}{len(blocked):>9}{100*bc:>12.0f}%{100*bp:>15.0f}%{100*good:>11.0f}%  |  {100*recall:>4.0f}% of all crash-confirms blocked")

print("\n=== by rise band: confirm retention + baseline outcome (target scenario) ===")
print(f"{'rise30 band':<16}{'n':>5}{'crash%':>8}{'high-plat%':>12}{'target keeps%':>15}{'mean shot base→target':>24}")
for lab, lo, hi in [('flat <20', 0, 20), ('modest 20-50', 20, 50), ('mod 50-70', 50, 70), ('fast 70-90', 70, 90), ('steep >90', 90, 1e9)]:
    idx = [i for i in range(n) if lo <= R[i]['rise'] < hi]
    if len(idx) < 8: continue
    keep = 100 * np.mean([dec['target'][i][0] for i in idx])
    cr = 100 * np.mean([R[i]['crash'] for i in idx]); hp = 100 * np.mean([R[i]['plateau_high'] for i in idx])
    sb = np.mean([eval_scenario(R[i], 'baseline')[1] for i in idx]); st = np.mean([dec['target'][i][1] for i in idx])
    print(f"{lab:<16}{len(idx):>5}{cr:>7.0f}%{hp:>11.0f}%{keep:>14.0f}%{sb:>16.2f}→{st:.2f}")

print("\nREAD: a good retune BLOCKS a high share of crash/high-plateau confirms (targets the bad meals),")
print("KEEPS the genuinely-good steep-rise confirms, and cuts total front-load. Outcome under the retuned")
print("dose is NOT simulated (identification wall) — this prices the dose decisions vs the ACTUAL outcomes.")
