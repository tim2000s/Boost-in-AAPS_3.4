# V6 velocity-gate backtest — the velocity fix is WRONG; the signal is IOB-context

*2026-07-19. Reproducible meal-by-meal backtest of velocity-gate scenarios over all users
(`bt_common.py` faithful gate port; `bt_extract.py` per-user parallel; `bt_scenarios.py` /
`bt_context.py` distributions). 527 actual V6 confirm shots, 8 users. Faithfulness: recomputed
rise→velocityFactor matches the logged value at MAE ~0.07. Intermediate per-meal JSON in scratchpad
(personal); scripts + aggregates committed.*

## What we can and can't do
The counterfactual glucose under a changed dose CANNOT be simulated (no validated model —
identification wall). So this prices the DOSE-LEVEL decisions per scenario and cross-references each
meal's ACTUAL outcome (crash / high-plateau, under the shot that really fired). It does NOT claim the
retuned trajectory.

## Result 1 — V6 confirm shots go bad a LOT
527 confirm shots: **crash<70 22%, deep<54 8%, high-plateau>140 40%.**

## Result 2 — the velocity retune is a BLUNT instrument (deprecated)
Retuning `velocityScaledDoseFactor` (RISE_HI 50→90, FLOOR 0.40→0.15 = "target") cuts front-load −41%
and blocks 28% of confirms — but **crash rate is ~flat across rise bands** (flat 31%, modest 21%, fast
21%, steep 17%) and ~40% of the confirms it blocks were GOOD meals. Head-to-head crash/deep-low recall:

| gate | blocks | crash-recall | **deep<54 recall** | precision (blocked-were-crash) |
|---|---|---|---|---|
| velocity target | 28% | 35% | 32% | 28% |
| velocity steep | 41% | 47% | 50% | 28% |
| **IOB<1.5 & BG<150** | 47% | 58% | 64% | 28% |
| **IOB<1.0** | 51% | 64% | **77%** | 28% |

Velocity is the *weakest* separator (crash-mean rise 41 vs no-crash 45). This **confirms the prior
fast-carb finding** ([[fastcarb-confirm-crash-2026-07-10]]): deceleration/velocity is the wrong
discriminator.

## Result 3 — the real crash signal is IOB, INVERTED
Crash rate by IOB at confirm: **<1U → 28% crash, 13% deep<54**; 1–2U → 21%/8%; 2–3.5U → 18%/2%;
>3.5U → 11%/2%. IOB is the strongest single feature (crash-mean IOB 0.8 vs no-crash 1.7). The bad
cell is **low-BG (<150) + low-IOB (<1.5): 28% crash, 11% deep<54, n=246** (the biggest cell); the same
low BG with IOB>1.5 only crashes 9%. **V6 fires the full 1.8× confirm shot too eagerly — modest BG,
little insulin yet on board — and overshoots.**

(The opposite tail — high-IOB confirms — don't crash but plateau high 56%: the descent under-recovery
from the dosing forensic. IOB is the key context in BOTH directions.)

## The fix direction (revised)
NOT the velocity gate. **Make the confirm-shot size IOB-aware** — ramp it with insulin-on-board rather
than firing the full 1.8× budget on the first confirm at low IOB. A soft ramp (small first shot,
escalate as IOB/BG prove the meal) prevents the low-IOB overshoot without a hard block. Justified on
**asymmetric cost, not precision** (precision is base-rate ~28% — the crash isn't cleanly predictable):
gating low-IOB confirms prevents **77% of the dangerous deep<54 lows**, and the cost of a blocked good
confirm is a recoverable mild high, not a danger — exactly the project's floors-first philosophy.
Shadow-first + two-test bar; watch the high tail (the ramp mustn't recreate the high-IOB plateau).
