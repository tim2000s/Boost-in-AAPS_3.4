# Why post-meal exercise raises hypo risk — the mechanism (2026-07-27)

The fully-closed-loop review found post-meal exercise is the sharpest failure mode (low rate
23% vs 14%) and reached for the obvious mechanism: meal-time insulin, then a sensitised body —
a **dose / stacking** story. That story is wrong, and the data says so plainly.

## What the data shows

Among 686 unannounced-meal confirmations followed by activity within 2 h, 24% ended in a low
< 70 within 3 h. Contrasting the crashers with the non-crashers **refutes the dose story**:

| at exercise onset | crashed | didn't crash |
|---|---|---|
| **IOB on board** | **0.96 U** | **1.61 U** |
| meal SMB burst (0–30 min) | 2.40 U | 2.10 U |
| **BG** | **114 mg/dL** | **136 mg/dL** |

Crashers carried **less** insulin, not more, on an identical meal bolus. And crash risk falls
**monotonically as insulin-on-board rises**:

    IOB at exercise onset:   low (~0.0 U)   mid (~1.5 U)   high (~4.2 U)
    crash rate:                 32%            22%            18%

If the low were driven by committed meal insulin, this would slope the other way. It doesn't.
In the post-meal window, more insulin on board is *protective*.

## The mechanism (stipulated)

**Post-meal exercise lows are carbohydrate-counterweight failures, not insulin excess.**
Exercise recruits a largely fixed downward glucose flux — contraction-mediated (insulin-
independent) muscle uptake plus amplified insulin sensitivity. Whether that flux tips into hypo
depends on the counterweight present at that moment: the residual rate of carbohydrate
appearance from the meal, and the starting BG. The evidence assembles cleanly:

- **Insulin-on-board is a proxy for the protective carb flux.** In the post-meal window, high
  IOB marks a large meal still actively absorbing — a strong upward carbohydrate flux that
  offsets the exercise. Low IOB marks a small or finished meal (or a loop that has already
  withdrawn insulin) — no offset — so the exercise flux is unopposed and BG falls through 70.
  This is why crash risk *falls* with IOB.
- **Crashers start with less headroom** (BG 114 vs 136) — closer to the floor when the fixed
  exercise drain begins.
- **The dose itself is not the culprit** — the meal boluses are the same size in both groups.

So the collision is: a largely insulin-independent glucose drain from exercise, landing when
the meal's carbohydrate counterweight is thin, from an already-lower BG.

## Why the loop cannot save it (and what would)

The defence this situation needs is *glucose in*. The loop's only lever is *insulin out*
(zero-temp basal) — and in exactly the crashing cases it has usually already spent that lever
(the low IOB is partly the loop having withdrawn on a falling BG). The controller is
structurally on the wrong side of the problem: it cannot add carbohydrate, and it has no
remaining insulin to remove.

That reframes the fix. It is **not** "dose the meal less for exercisers" — they are not
over-dosed, and cutting the meal bolus would only trade the rare exercise low for a routine
post-meal high. The only loop-side levers are (a) *anticipatory* withdrawal before the bolus is
committed, when exercise is habitually expected — which needs the per-person anticipation model
the review argues for, made safe by retractability; or (b) prompting carbohydrate. The
disturbance is exogenous (the decision to exercise) and the true remedy is exogenous
(carbohydrate, or a counter-regulatory hormone). This is the same wall as the efficacy blind
spot: the loop lacks not a better algorithm but a lever on the right variable.

## Confidence and caveats

- **SOLID** that the low is not dose-driven (monotone IOB→crash relationship, refuted stacking
  story, matched boluses; cohort, 686 events).
- **PROVISIONAL** on the precise physiology (insulin-independent uptake vs sensitivity
  amplification vs blunted hepatic output) — we infer it; we do not measure muscle uptake.
- **Identification caveat:** low IOB is partly a *consequence* of the loop zero-temping on an
  already-falling BG, so "low IOB → crash" and "already-falling → crash" cannot be fully
  separated observationally. Both readings converge on the same conclusion — the driver is not
  insulin excess, and the loop's insulin lever is already spent — so the mechanistic claim
  holds under either.

*Reproduce: `postmeal_exercise_mechanism.py` (DB refreshed to t=now). Eight users with a step
feed, 50-day window, 686 meal+exercise events.*
