# Meal-shape-at-confirm prediction (`meal_shape.py`)

**Date:** 2026-07-20 · **Question:** at the CONFIRMED cycle, can we predict a meal's
eventual *shape* — which need opposite handling — from features available at confirm?

Identification-clean (keep observed BG, ask what follows). 2,117 confirmed meals, 9 users,
May–Jul. GroupKFold by **user** (no cross-user leakage); LightGBM; bootstrap 95% CI.

Shapes from the forward trajectory (anchor = CONFIRMED cycle): **CRASH** = min BG after peak
< 70 within 3h (needs restraint); **TAIL** = not crash AND median BG in the 2–3.5h window > 150
(under-recovery, needs sustain/plateau-nudge); **CLEAN** = otherwise. Base rates CLEAN 55%,
TAIL 26%, CRASH 19%. Confirm-time features: bg, delta(5), rise(15), acceleration, boostv5_score,
IOB, eventualBG-offset, UAM-offset, ml_meal_likely, budget, time-of-day (sin/cos).

## Result

| shape | needs | OOS AUC [95% CI] | verdict |
|---|---|---|---|
| **CRASH** | restraint | 0.518 [0.485, 0.549] | **chance — not predictable** |
| **TAIL** | sustain / plateau-nudge | 0.604 [0.577, 0.631] | weakly separable (real) |
| CLEAN | — | 0.533 [0.509, 0.558] | marginal |

Feature importance is flat and diffuse — acceleration, ml_meal_likely, IOB, UAM-offset, score
and time-of-day all contribute similarly; no dominant cue.

## Reading

**The crash shape is not predictable at confirm — the decisive finding.** AUC 0.52 = chance.
There is no confirm-time signal to pre-identify which confirmed meals spike-and-crash (consistent
with the per-cycle plateau low being unforecastable, dr3 AUC 0.55). This **rules out
predict-and-restrain** and **vindicates the retractable-action architecture**
([[anticipation-backout-controller-2026-07-20]]): since crashers can't be foreseen, the only
viable crash defence is an action you *unwind after the fact*, not one you withhold ahead of time.

**The tail shape is weakly predictable (AUC 0.60, CI clear of chance — PROVISIONAL).** Real but
modest, diffuse, with a circadian component. Two caveats keep it modest: (1) at 0.60 you'd
mis-route heavily — too weak to gate anything aggressive; (2) some "TAIL" is likely a *second
unannounced meal* in the 2–3.5h window (habitual back-to-back eating), which the time-of-day
feature partly picks up — meal-clustering, not absorption tail. Only safe use: a weak prior to
bring the already-floor-guarded `plateau-nudge` on a little earlier for likely-tail meals. A
nice-to-have on an existing shadow, not a headline.

## Implication for the unannounced-meal programme

Shape prediction opens **no** new lever but sharpens the map: crashes are unpredictable → the
next meal-response step is to make the retractable back-out fire on the *best* onset detector
(wire `accelMeal → antBackout` ARM — see `../2026-07-anticipation-backout/ACCELMEAL_ARM_SPEC.md`),
not to build a shape-gated restraint. Tails are weakly foreseeable → an optional low-priority
tail-prior for plateau-nudge timing. Detection itself remains at ceiling.

## Reproduce
`python3 meal_shape.py`  (needs local oref DB refreshed to t=now)
