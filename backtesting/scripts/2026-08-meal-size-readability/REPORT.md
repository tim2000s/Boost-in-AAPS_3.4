# Reading meal size from the glucose trace: 492,440 meals across 839 participants (2026-08-25)

*Reproduce: `run_when_free.sh`, which drives `extract_meals.py`, `size_readability.py`,
`slope_heterogeneity.py`, `detection.py` and `report_tables.py` against the `studies` schema of the local
TimescaleDB. Loop contributes 492,440 meals from 839 participants and REPLACE-BG 71,761 from 189,
after excluding rescue carbohydrate and entries below 8 g. Participants are held out as folds
throughout, and every interval comes from resampling participants. Protocol:
`backtesting/protocols/2026-08_meal_size_readability_PREREG.md`. Tables: `out/TABLES_Loop.md`.*

## Why this exists

The carb-signature study of 2026-08-13 closed dose sizing to the meal. Held out by participant, it
separated large meals from small at 0.267 at ten minutes and 0.508 at forty five, and it explained
the sub-chance figure by saying the mapping from carbohydrate to early glucose differs between
people. It rested on 592 meals from six participants, of whom one contributed 372, and its interval
at ten minutes ran from 0.167 to 0.553, which includes chance. The conclusion was well drawn from
what was available and the sample could not distinguish a relationship that inverts from one that
is merely too small to see.

This is the same question on 830 times the meals and 140 times the participants, with the meal
definition, the exclusions and the thirteen shape features taken across unchanged so that the
comparison is a comparison.

## The trajectory alone

On the prior study's feature set, with no clock and nothing about the person, a large meal is
separated from a small one at 0.519, with an interval of 0.510 to 0.528, ten minutes after onset.
That is above chance and it is nothing anyone can use. By sixty minutes it reaches 0.608.

The sub-chance result does not reproduce. What the six participants showed was the instability of
an out-of-fold estimate on a sample that small, and the inversion it was read as is examined
directly below.

## What is doing the predicting

Adding the clock lifts ten-minute separation from 0.519 to 0.594. The clock on its own, with no
glucose at all, gives 0.586. Adding what can be known about the person without any announcement
gives 0.669 from those features alone. Adding the participant's own earlier announced meals gives
0.812 from history alone, and 0.830 once the clock is included with it.

Set each arm against the arm holding the same information with the glucose trace removed, and the
trace is worth very little.

| stratum | horizon | with the trace | without it | difference |
|---|---|---|---|---|
| all | 10 min | 0.594 [0.586 to 0.601] | 0.586 [0.578 to 0.594] | +0.007 |
| all | 10 min | 0.833 [0.822 to 0.843] | 0.830 [0.819 to 0.841] | +0.002 |
| all | 60 min | 0.639 [0.631 to 0.648] | 0.586 [0.578 to 0.594] | +0.053 |
| all | 60 min | 0.838 [0.827 to 0.848] | 0.830 [0.819 to 0.841] | +0.008 |
| none | 10 min | 0.605 [0.585 to 0.625] | 0.585 [0.564 to 0.604] | +0.020 |
| none | 10 min | 0.840 [0.813 to 0.863] | 0.835 [0.808 to 0.857] | +0.006 |
| none | 60 min | 0.662 [0.638 to 0.686] | 0.585 [0.564 to 0.604] | +0.077 |
| none | 60 min | 0.848 [0.822 to 0.870] | 0.835 [0.808 to 0.857] | +0.013 |

A model that scores 0.833 looks like it can read the meal. It is reading the diner. The tell is in
the horizons: the arms carrying participant information sit at 0.833 at ten minutes and 0.838 at
sixty, barely moving as an hour of glucose data arrives, while the trajectory-only arm climbs from
0.519 to 0.608 because it has nothing else to work with. Information that does not improve as the
excursion unfolds did not come from the excursion.

Pre-registered decision margin: 0.05 in area under the curve at a horizon of twenty minutes or
less, against the matched baseline. Nothing clears it. The largest figure in the table, the +0.077
for the trajectory over the clock in unbolused meals, arrives at sixty minutes, and a size estimate
at sixty minutes is an estimate of something already over.

## Size as a quantity

| arm | information | MAE at 10 min | MAE at 60 min |
|---|---|---|---|
| 1 | trajectory and clock | 15.97 g | 15.73 g |
| 2 | and participant scale | 15.08 g | 14.93 g |
| 3 | and the participant's own history | 13.12 g | 13.01 g |
| baseline | the population median | 15.65 g | 15.65 g |
| baseline | the median at that time of day | 15.53 g | 15.53 g |
| baseline | the participant's own median | 13.02 g | 13.02 g |

Predicting the participant's own median and stopping gives 13.02 g. The full model at ten minutes
gives 13.12 g and at sixty gives 13.01 g. The trajectory arm is worse than predicting the
population median. This is the same result the prior study reported, at 18 to 21 g against 13.2 g,
and the agreement between the two on a quantity measured on different people is close.

## The bolus inverts the sign

An announced meal is usually bolused for in proportion to its size, which damps the early rise.
Within a participant, comparing their own bolused meals against their own unbolused ones, so that
people differing from one another cannot be the cause:

| horizon | participants | unbolused slope | bolused slope | difference | 95% interval |
|---|---|---|---|---|---|
| 10 min | 561 | +0.0118 | −0.0056 | +0.0175 | +0.0038 to +0.0317 |
| 20 min | 561 | +0.0290 | −0.0032 | +0.0322 | +0.0045 to +0.0595 |
| 60 min | 561 | +0.3687 | +0.1741 | +0.1946 | +0.1324 to +0.2554 |

Every interval excludes zero. In the same person, carbohydrate is associated with a rising trace
when no insulin was given for it and with a falling one when insulin was. Across strata the pooled
ten-minute slope is +0.0209 where no bolus was given and −0.0083 where one preceded the meal.

So the hypothesis that the prior null was a property of announced meals is confirmed as a
mechanism. It does not rescue the measurement, which is the next section.

## Why a correctly signed relationship is still unusable

In unbolused meals the relationship runs the way physiology says it should. It is also far below
the variability it would have to be read out of.

| horizon | slope, mg/dL per gram | 20 g against 60 g | spread of the rise | ratio |
|---|---|---|---|---|
| 10 min | +0.0209 | 0.83 mg/dL | 9.71 mg/dL | 0.086 |
| 20 min | +0.0505 | 2.02 mg/dL | 18.44 mg/dL | 0.110 |
| 30 min | +0.0904 | 3.62 mg/dL | 26.28 mg/dL | 0.138 |
| 45 min | +0.1856 | 7.42 mg/dL | 35.86 mg/dL | 0.207 |
| 60 min | +0.3089 | 12.36 mg/dL | 44.20 mg/dL | 0.280 |

Forty grams of difference moves the ten-minute rise by 0.83 mg/dL, against a spread of 9.71. The
quantity a controller would have to resolve is roughly a twelfth of the noise it sits in. By sixty
minutes it has grown to somewhat over a quarter, which is why separability appears late and why it
appears weakly.

This is the account the prior study was reaching for. The relationship is not absent and it does
not have to invert for the conclusion to hold. It is an order of magnitude below the sensor noise
at the horizons where an answer would be worth having.

## Differences between people

The per-participant slopes are genuinely heterogeneous. At ten minutes, across 829 participants
with at least thirty meals each, the standard deviation of the true slopes is 0.028 against a
pooled slope of −0.007, and 69 per cent of the variance in the fitted slopes is real rather than
estimation error. Sixteen per cent of participants are individually below zero and ten per cent
individually above it, so both signs occur in the population and neither is a fluke of one person.

The prior report's mechanism therefore survives as a description, and it is not the binding
constraint. Heterogeneity that size would have to overcome sits on top of a signal that is already
too small.

## The second study

REPLACE-BG reproduces the pattern on 47,939 classifiable meals from 189 participants, in a
different era, on sensor-augmented pump therapy rather than a closed loop, under a different
de-identification scheme. The trajectory-and-clock arm gives 0.634 at ten minutes and 0.653 at
sixty; the arm with the participant's history gives 0.835 at ten and 0.839 at sixty, flat across
the horizon in the same way. Its meals are 71,737 at-meal boluses out of 71,761, so it carries no
weight on the bolus contrast and serves only as external validation.

## Detection, and what its headline figure was resting on

The same extraction answers the other half of the question, on 492,440 announced meals against
562,564 undeclared rises from 850 participants. The negative class is built as before: a rise of
at least 25 mg/dL within thirty minutes, above the rescue threshold, with no carbohydrate entered
within two hours either side.

| horizon | as previously constructed | meals held to the same 25 mg/dL bar |
|---|---|---|
| 10 min | 0.833 [0.830, 0.836] | 0.843 [0.841, 0.846] |
| 15 min | 0.855 [0.852, 0.858] | 0.851 [0.848, 0.853] |
| 20 min | 0.896 [0.894, 0.899] | 0.865 [0.862, 0.867] |
| 30 min | 0.952 [0.950, 0.953] | 0.873 [0.871, 0.875] |
| 45 min | 0.930 [0.928, 0.932] | 0.865 [0.863, 0.867] |
| 60 min | 0.918 [0.916, 0.920] | 0.861 [0.859, 0.864] |

The left column reproduces the six-participant result closely, 0.833 against 0.805 at ten minutes
and 0.952 against 0.975 at thirty. The right column is the one to quote. An undeclared rise must
reach 25 mg/dL to enter the comparison while a meal enters however flat its trace, so the classes
are separated in part by a rule rather than by physiology, and the separation grows with horizon
because a meal that never rises becomes easier to tell from a rise that must. Hold the meals to
the same bar and detection sits between 0.84 and 0.87 across every horizon, high at ten minutes
and close to flat thereafter.

Detection is therefore good, available early, and worth less at thirty minutes than the previous
figure implied. It is also the honest bar for the accelerometer meal shadow, which should be
judged against 0.843 at ten minutes rather than against 0.805, and against 0.873 at thirty rather
than 0.975.

## What follows

Dose sizing to the meal stays closed, on evidence that no longer depends on six participants. The
staged-response design's premise, that the controller commits smaller and waits for the excursion
to declare itself, is what the measurements support, and the forty five to sixty minute figure the
prior study gave for when the excursion becomes estimable is unchanged.

A per-meal size prior worth 0.830 in separation and 13.2 g of error is available from the person's
own history and the clock, without any glucose trace. It is not available to Boost, which has no
announcements to build a history from, and it would answer a different question in any case: what
this person usually eats at this hour, rather than what is in front of them now. A calibration
period in which a user announced their meals would buy that prior and would not buy the ability to
tell today's large breakfast from today's small one.

Two things in the extraction are worth more than they cost. The bolus stratification is a general
tool for any question asked of announced-meal corpora, since it separates physiology from the
therapy applied to it. And the detection question, which shares this extraction entirely, can now
be measured against a thousand participants instead of six.

Confidence: SOLID. Out of sample with participants held out, intervals from resampling
participants, replicated in an independent study, and the apparent positive result survived a
matched baseline that removed it.

## Limitations

Announced carbohydrate is an estimate made by the person eating, and its error places a ceiling on
measured accuracy that this design cannot separate from the ceiling imposed by physiology. The
onset is inferred from the trace rather than observed, so a meal whose announcement is far from the
eating is anchored imprecisely. These are Loop and sensor-augmented pump users rather than Boost
users, and what transfers is a statement about the information in a glucose trace and not about how
any controller responds to it. No policy conclusion is available: whether a dose sized to an
estimated meal would improve any outcome is not addressed here and would need the within-participant
trial the two-test bar demands.
