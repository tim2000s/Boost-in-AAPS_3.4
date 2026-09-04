# The fully closed loop in type 1 diabetes, the good, the bad and the ugly

*A critical review grounded entirely in one cohort's own data. Nothing here is quoted from
the literature; every number is measured from the cohort described below.*

## The definition of "fully closed loop", and the test applied

A fully closed loop takes no meal announcement and no carb entry. The person eats; the
system finds out only when glucose starts to move. That is not a thought experiment for this
cohort, it is how they actually run. Across roughly 103,000 decision cycles from nine
people over 30 days, 92% carried no carbs on board at all, and for most individuals the
figure is 96 to 100%. A couple of people announce some meals; the rest announce essentially
nothing. So when we talk about the fully closed loop, we are describing observed behaviour,
not an ideal.

Two honesty constraints shape everything below:

The first is that there is no glucodynamic simulator. The counterfactual glucose trace for a dosing
change cannot be generated, so no policy claim here is proved. Detection and prediction claims are
validated out of sample and are clean; policy claims are priced against what actually happened and
stay associational unless a within-subject or randomised design backs them.

The second is that effect sizes carry uncertainty. Where it matters, figures come with a bootstrap
95 per cent interval and an explicit verdict on whether they are distinguishable from baseline, with
the participant as the resampling unit.

The controller under review is deterministic, a state machine with multipliers, caps and a
composed brake, plus two small pre-trained models applied at inference. Nothing learns and
doses inside the loop.

---

## The good

It works, and mostly it works without being told anything. Over 30 days the cohort
sat at a mean Time in Range (70 to 180 mg/dL, 3.9 to 10.0 mmol/L) of 87% (±7) and Time in Normoglycaemia
(TING, 63 to 140 mg/dL, 3.5 to 7.8 mmol/L) of 72% (±11), with time below 54 mg/dL (3.0 mmol/L) of just 0.62%, all of
that achieved with no carb counting and no pre-bolusing. For a system reacting to
unannounced food, this is a genuinely good result, and the best-controlled individual reached
98% TIR and 88% TING fully closed. That is close to the ceiling of what any therapy
delivers, achieved by someone who tells the loop nothing about their meals. *(SOLID, descriptive cohort measurement.)*

Overnight is where it shines. With no meals to chase, the loop's reactive strength is
exactly matched to the problem: glucose is tight, variance is low, and the safety floors do
the rest. The controller is at its best precisely when the disturbance is small and slow.

It genuinely sees unannounced meals, through the CGM alone. The one signal that reliably
precedes the loop's own meal-confirmation is glucose acceleration, which leads the
delta-based confirmation by around 5 to 15 minutes on this cohort's data. The loop is not blind
to food; it is simply looking at the only window it has. *(SOLID, out-of-sample, prior
signal study.)*

The safety architecture holds. Severe lows are rare (time below 54 mg/dL under 1% for
seven of nine), and, crucially, most lows are *not* the loop's fault (see below). The
composed brake that restrains dosing into recovering highs audits as roughly 90% correct, and
absolute time-below floors sit beneath every statistical decision and can only tighten.

---

## The bad

"Fully closed loop" is not one thing. The same controller, the same guards, the same
defaults produced a TIR spread of 77% to 98% and a TING spread of 58% to 89% across nine
people. The determinant is not the algorithm; it is the physiology and behaviour it is pointed
at. Any claim that a closed loop "achieves X%" is nearly meaningless without saying *for
whom*. The honest headline is a distribution, not a number.

The price of saying nothing is the post-meal high. Of 480 excursions above 180 mg/dL in
the month, 89% began with no carbs announced. This is the structural cost of the fully
closed design: you cannot out-run meal absorption while reacting to a CGM that lags the meal
by design. Most excursions are short, median 70 minutes, but the tail is long: the 75th
percentile is nearly two and a half hours, and the worst ran over ten. A loop that is told
nothing spends real time high after real meals, and no amount of reactive tuning removes that;
it is baked into the information available.

What the loop is actually chasing, it mostly cannot see. When we went looking for
predictive signal, the finding was uncomfortable: glucose trajectory, value, delta and
curvature, is essentially all of it. Adding richer inputs (insulin on board, total daily
dose, heart rate, sensitivity, the ML meal-likelihood term) *degraded* short-horizon
prediction rather than helping, and no observable meal precursor exists before the CGM itself
turns. *(SOLID, leakage-controlled, cross-user out-of-sample.)* The residual error is
therefore not a modelling failure to be engineered away; it is unobserved meals and unobserved
exercise. The loop is always reacting to shadows.

---

## The ugly

Exercise is where the fully closed loop meets its limits. 48% of all low-glucose
episodes in the cohort were attributable to activity (elevated steps or heart rate in the
90 minutes before onset), against just 21% attributable to insulin the loop had recently
delivered. And the loop's only lever against an activity low is the wrong one: it can withhold
insulin, but at the onset of these lows the median insulin on board was already 0.48 U, there is frequently nothing left to withdraw. Basal is at zero; a bolus already given cannot
be recalled. The controller watches the fall it cannot stop. *(SOLID, cohort attribution;
associational by construction.)*

Post-meal exercise is the single sharpest failure mode. When a meal is followed by
activity within two hours, the low rate over the next three hours is 23% (95% CI 20 to 26),
against 14% (12 to 17) for meals not followed by exercise, the confidence intervals do not
overlap.

The obvious explanation, committed meal insulin landing into a sensitised body, is,
on this cohort's data, wrong. If the low were dose-driven, the crashers would carry more
insulin; they carry less (median 0.96 U on board at exercise onset, against 1.61 U for those
who don't crash), on an identical meal bolus, and crash risk falls monotonically as insulin
rises. 32% at low IOB, 22% at mid, 18% at high. In the post-meal window, more insulin on
board is *protective*, not dangerous. *(SOLID, cohort, 686 meal+exercise events.)*

The mechanism is a carbohydrate-counterweight failure, not insulin excess. Exercise
recruits a largely fixed, insulin-independent glucose drain, contraction-mediated muscle
uptake plus amplified sensitivity. Whether it tips into hypo depends on the counterweight
present: how fast carbohydrate is still appearing from the meal, and the starting BG. Insulin
on board tracks that counterweight, high IOB marks a big meal still actively absorbing, which
offsets the drain; low IOB marks a small or finished meal (or a loop that has already withdrawn
insulin), so the drain runs unopposed and BG falls through 70. Crashers also start with less
headroom (BG 114 vs 136). The dose is not the culprit; the missing carbohydrate is. And the
loop cannot supply it: the defence this needs is *glucose in*, while the loop's only lever is
*insulin out*, which, in exactly these cases, it has usually already spent. The controller is
on the wrong side of the problem.

The danger outlasts the exercise, and outlasts the loop's memory of it. After an activity
bout ends, the low hazard stays elevated at around 19 to 20% for a full five hours (0 to 2 h:
19% [17 to 21]; 2 to 5 h: 20% [18 to 22]), only easing toward baseline after that (5 to 8 h: 16%
[15 to 18]). Reactive control is structurally blind to this tail: the insulin responsible was
delivered hours earlier, and by the time the delayed low arrives there is nothing to withdraw.
*(SOLID, cohort, de-artefacted windows.)*

Insulin efficacy is invisible to the loop. This is the deepest structural problem. During
excursions above 180 mg/dL, the median insulin on board was 4.4 U, and 97% of
high-glucose time carried more than 1 U on board, insulin was present, and glucose was
stuck anyway. The controller keeps a correct-looking insulin ledger while nothing happens,
because insulin-on-board is a record of *delivery*, not a meter of *effect*. It cannot
distinguish "the insulin has not worked yet" from "there is not enough insulin." When
sensitivity finally returns, the same blindness produces the mirror-image failure: the loop
over-treats a modest, unannounced fast-carb rise and the glucose then crashes, an overshoot
we measure at 20 to 39% in that specific context. The loop is not badly tuned here; it is
being asked to control a system through a sensor that does not report the variable that
matters. *(SOLID / PROVISIONAL, efficacy-deficit is measured; the crash figure is a
context-specific prior study.)*

---

## Drivers of the insulin response

Pulling the threads together, the fully closed loop is a CGM-trajectory machine. All of
its exploitable information lives in the shape of the glucose curve, and it is driven by two
latent processes it can only partly observe:

1. Meals, seen only *after* absorption has begun to bend the curve. There is no earlier
   observable precursor in this cohort's data.
2. Activity and the sensitivity change it causes, seen partially, and too late, through
   steps and heart rate, but with an effect that outlasts the signal by hours.

Everything the loop does is downstream of glucose movement it did not cause and cannot
anticipate. And the one internal quantity it *does* know precisely, insulin on board, is a
delivery ledger, not an efficacy meter. That single gap between *insulin given* and *insulin
working* is the root of both the stuck high and the rebound crash. It is the defining
limitation of reacting to glucose alone.

---

## The attainable position

The reactive ceiling is close. Successive generations of this controller are, on the
cohort's outcomes, statistically indistinguishable, every pairwise difference overlaps
zero. *(SOLID, within the cohort.)* We should stop expecting a smarter reactive rule to move
the numbers much; the honest estimate of remaining headroom from reactive tuning is a couple
of percentage points of TIR, no more. The interesting frontier is not a better reaction.

The frontier is anticipation, and it means learning the person, not the policy. The
places the loop fails are the places it is *surprised*: the meal it did not expect, the walk
it did not see coming, the sensitised evening after exercise. Those events are not random;
they are habitual. The one anticipation target that is unambiguously real in our data is the
delayed post-exercise tail, universal, delayed and predictable, followed by habitual
meal timing. The lever is not a cleverer controller; it is a per-person model of *when this
person tends to eat and move.* *(SPECULATIVE, the direction is evidenced; the dosing action
is not yet proven.)*

Anticipation can be made safe by making it retractable. The objection to anticipatory
dosing is obvious: anticipate wrong and you cause the low you meant to prevent. The way
through is to pre-position insulin as a temp-basal that automatically unwinds if the
expected event does not confirm, so the anticipation need not be accurate, only reversible.
In live shadow this already half-works: the retraction machinery fires cleanly (nearly all
back-outs are benign low-trips caught early), while the *arming* is still too eager. That is a
tractable problem, not a dead end.

Dose against the distribution, not the point estimate. A low costs far more than an
equivalent high. A risk-aware sizer that doses against the whole predicted spread of glucose,
with an asymmetric cost, would systematically dose *less* into uncertainty, and in shadow
this variant delivers roughly half the correction volume of the current controller while
concentrating the reductions ahead of lows. *(PROVISIONAL, shadow-measured, not yet
outcome-validated; its own risk estimate needed recalibration first.)*

And the honest limits on all of it. We cannot prove any of these ex ante, there is no
simulator to generate the counterfactual, the cohort is small and self-selected, and the only
real test is within-person over time. Two things would help more than any algorithm we could
write: faster insulin, which would shrink the meal-lag the whole design fights, and a true
efficacy signal, some way to know that delivered insulin is or is not working, which
would close the one blind spot underneath both the stuck high and the rebound crash.

We went looking for that efficacy signal in this cohort's own data, and did not find it.
Out-of-sample and cohort-wide, we asked whether anything observable at a stuck high, the
loop's own model deviation, the insulin's activity, recent dosing, or even the Twin's inferred
carb-appearance rate, could tell, *beyond the glucose curve and the dose already given*,
whether the insulin would work (the high settles) or would not (it stalls, or over-corrects
into a crash). Nothing beat the trajectory: a linear model on the full feature set lands
exactly on chance for the crash, the loop's deviation signal sits *below* chance, and the only
features that flicker at all are measures of *how much* insulin is on board, not whether it is
acting. The one dose-independent candidate that could in principle separate masking carbs from
genuine resistance did not discriminate at all. *(SOLID for the crash; PROVISIONAL overall, single dataset; the one dose-independent candidate is young rather than refuted.)* The blind spot is not hiding in
the telemetry we have; closing it is a sensing problem, not a modelling one. Until faster
insulin or a real efficacy sensor arrives, the fully closed loop will remain what this data
shows it to be: quietly excellent overnight and for well-matched physiologies, honest but
imperfect against unannounced meals, and at its most vulnerable around exercise, where its only
lever is the one it has already spent.

---

## Verdict

The fully closed loop is a real and underrated achievement: most of this cohort maintain
around 87% time in range having told their system nothing about their food, and the best do
far better than that. But "fully closed" is a distribution, not a number, and its failures are
structural rather than incidental, the post-meal high is the price of silence, and exercise
is the scenario its reactive design cannot cover, because the insulin is already committed and
its effect is invisible. The next real gains will not come from a cleverer reaction to
glucose. They will come from *anticipating the person*, safely, retractably, and from the
two things no algorithm can supply: faster insulin, and a way to see whether the insulin is
working at all.

---

*Evidence base: nine loopers, ~103,000 decision cycles and matched CGM, 30 days to
2026-07-27, from a local research database; supporting figures from committed out-of-sample
studies in this repository. Anonymised; individual identifiers removed. One participant on a
different pump platform lacks a step feed and is excluded from the activity attributions.
Method notes and the identification constraint are stated at the top.*
