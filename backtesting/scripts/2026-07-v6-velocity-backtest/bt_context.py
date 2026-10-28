#!/usr/bin/env python3
"""
What ACTUALLY discriminates the bad confirm shots — velocity, or the confirm CONTEXT (BG + IOB)?
The velocity retune (bt_scenarios) reduces front-load broadly but crash rate is ~flat across rise
bands. The fast-carb finding said the real signal is low-BG + IOB confirm-context. Test it: crash /
high-plateau / deep-low rates binned by BG-at-confirm and IOB-at-confirm (and jointly). Whichever
cleanly separates good from bad is the gate to build. Usage: python3 bt_context.py <out_dir>
"""
import sys, json, glob, numpy as np
OUT = sys.argv[1]
R = []
for f in glob.glob(f"{OUT}/bt_confirms_*.json"): R += json.load(open(f))['recs']
n = len(R)
print(f"confirm shots: {n}  (baseline crash {100*np.mean([r['crash'] for r in R]):.0f}%  "
      f"deep<54 {100*np.mean([r['deep'] for r in R]):.0f}%  high-plateau {100*np.mean([r['plateau_high'] for r in R]):.0f}%)\n")

def band(name, key, edges, labels):
    print(f"by {name}:")
    print(f"  {'band':<14}{'n':>5}{'crash<70%':>11}{'deep<54%':>10}{'high-plat%':>12}{'mean shot':>10}")
    for i, lab in enumerate(labels):
        lo = -1e9 if i == 0 else edges[i - 1]; hi = edges[i] if i < len(edges) else 1e9
        s = [r for r in R if lo <= r[key] < hi]
        if len(s) < 10: continue
        print(f"  {lab:<14}{len(s):>5}{100*np.mean([x['crash'] for x in s]):>10.0f}%"
              f"{100*np.mean([x['deep'] for x in s]):>9.0f}%{100*np.mean([x['plateau_high'] for x in s]):>11.0f}%"
              f"{np.mean([x['actual_dose'] for x in s]):>10.2f}")
    print()

band('BG at confirm', 'bg', [130, 150, 170, 190], ['<130', '130-150', '150-170', '170-190', '>190'])
band('IOB at confirm', 'iob', [1.0, 2.0, 3.5], ['<1', '1-2', '2-3.5', '>3.5'])
band('rise30', 'rise', [25, 50, 90], ['<25', '25-50', '50-90', '>90'])

# joint: the fast-carb "eager confirm" cell = low BG AND meaningful IOB
print("joint confirm-context (the fast-carb 'eager confirm' hypothesis):")
def cell(lab, pred):
    s = [r for r in R if pred(r)]
    if len(s) < 10: print(f"  {lab:<28} n={len(s)} (thin)"); return
    print(f"  {lab:<28} n={len(s):>4}  crash {100*np.mean([x['crash'] for x in s]):>3.0f}%  "
          f"deep {100*np.mean([x['deep'] for x in s]):>3.0f}%  high-plat {100*np.mean([x['plateau_high'] for x in s]):>3.0f}%  "
          f"shot {np.mean([x['actual_dose'] for x in s]):.2f}U")
cell('low BG<150 & IOB>1.5', lambda r: r['bg'] < 150 and r['iob'] > 1.5)
cell('low BG<150 & IOB<1.5', lambda r: r['bg'] < 150 and r['iob'] <= 1.5)
cell('high BG>170 & IOB>1.5', lambda r: r['bg'] > 170 and r['iob'] > 1.5)
cell('high BG>170 & any IOB', lambda r: r['bg'] > 170)
cell('modest rise<50 & low BG<150', lambda r: r['rise'] < 50 and r['bg'] < 150)
cell('modest rise<50 & IOB>2', lambda r: r['rise'] < 50 and r['iob'] > 2.0)

# simple predictive check: AUC-ish separation of crash by each single feature
print("\nrank features by how well they separate CRASH (mean-feature crash vs no-crash):")
for key in ('bg', 'iob', 'rise'):
    cr = [r[key] for r in R if r['crash']]; nc = [r[key] for r in R if not r['crash']]
    print(f"  {key:<6} crash-mean {np.mean(cr):7.1f}   no-crash-mean {np.mean(nc):7.1f}   Δ {np.mean(cr)-np.mean(nc):+7.1f}")
