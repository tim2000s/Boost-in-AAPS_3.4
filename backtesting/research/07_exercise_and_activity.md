# Activity, hypoglycaemia, and exercise taken soon after a meal

The dose-response between recent movement and subsequent hypoglycaemia, whether it transfers
between people, and what can and cannot be said about the insulin carried at the onset of
post-meal exercise.

## Abstract

Activity accounts for approximately 48 per cent of pooled time below range, making it the largest
low-side mechanism in the cohort. Recent step count is a strong monotone leading indicator:
forward hypoglycaemia within three hours rises from 13.1 per cent at no recent steps through 17.1,
18.5, 25.9 and 31.8 to 38.5 per cent above 1,200 steps in the preceding hour, against a cohort
base of 19.1. The relationship does not transfer between people. A hypoglycaemia predictor with
participants held out scores 0.739 without activity features and 0.717 with them, a
cross-participant lift of minus 0.02 within fold noise, which supports per-participant thresholds
rather than a global model. On the narrower question of what insulin is carried when exercise
begins soon after a meal, the direction of the association is not established. Across 157 events
in five participants, with insulin on board expressed as a fraction of each participant's own
total daily dose and discrimination pooled by resampling participants, more insulin at onset is
associated with more subsequent lows, at an area under the curve of 0.549 with an interval from
0.512 to 0.604, and every participant sits above 0.5. A separate construction over 686 events
reported the opposite. Total daily dose spans 16 to 58 U across these participants and the
between-participant correlation between median insulin at onset and low rate is minus 0.388, so a
pooled comparison in absolute units mixes a within-person question with a between-person one.

## Introduction

Time below range dominates the addressable loss in this cohort, and activity dominates time below
range. Two questions follow and they have different shapes.

The first is whether recent movement is a usable leading indicator, and whether a protective
response built on it should be tuned per participant or globally. That is settled by whether the
relationship generalises across people.

The second concerns exercise taken soon after a meal, where a low sometimes follows. The
quantities available at the onset of exercise are the glucose, the insulin on board and the
carbohydrate still to absorb, and the question is whether any of them distinguishes the occasions
that end low.

That question is harder to ask than it appears, because insulin units are not comparable between
these participants. Total daily dose varies severalfold, at least one participant uses a 200 U/mL
concentration so that a unit carries twice the mass, and body size and carbohydrate ratio vary
alongside. A comparison of absolute units pooled across participants therefore answers a mixture
of two questions: whether a person carried less insulin on the occasions they went low, and
whether the people who go low are the people who run less insulin. Only the first bears on
mechanism.

## Methods

The leading-indicator work is recorded under
`backtesting/scripts/2026-07-residency/ACTIVITY_HYPO_REPORT.md` over roughly 89,500 cycles. It was
approached first as a dose-response, measuring forward hypoglycaemia rate against recent step
count, and then as a prediction problem with participants held out as folds, so that the transfer
question is answered by cross-participant generalisation rather than by pooled association or by
feature importance.

The post-meal exercise question is recorded under
`backtesting/scripts/2026-08-postmeal-exercise-recheck/`. An exercise onset is a crossing of 400
steps in the preceding thirty minutes from below 100, with one event admitted per hour so that a
long session is not counted repeatedly. It qualifies as post-meal when it falls within three hours
of a glucose rise of at least 40 mg/dL within ninety minutes. The outcome is a glucose below
70 mg/dL sustained at least ten minutes within the following three hours. This yields 157 events
across five participants with a step feed, at a low rate of 0.229.

Insulin on board is reported three ways: in absolute units pooled, as a fraction of the
participant's own total daily dose pooled, and per participant. The fraction is dimensionless and
concentration-free, so a participant on 200 U/mL is comparable with one on 100. Intervals come
from resampling participants rather than events.

Heart rate was evaluated alongside steps throughout. It is 76 per cent absent from the record, so
its verdict is one of data sparsity rather than of usefulness.

## Results

Steps are a strong, monotone leading indicator. Forward hypoglycaemia within three hours runs
13.1, 17.1, 18.5, 25.9, 31.8 and 38.5 per cent across increasing bands of steps in the preceding
hour, against a cohort base of 19.1. Sedentary to very active nearly triples the rate.

The relationship does not transfer. With participants held out, the predictor scores 0.739 on the
baseline block and 0.717 with activity added, a lift of minus 0.02 within fold noise, while the
same features rank fifth and sixth on importance in-sample.

On post-meal exercise, insulin on board at onset is associated with more subsequent lows rather
than fewer.

| construction | AUC | 95% CI |
|---|---|---|
| pooled, absolute units | 0.588 | [0.518, 0.656] |
| pooled, fraction of own total daily dose | 0.549 | [0.512, 0.604] |

Every participant sits above 0.5 individually, from 0.509 to 0.750 on the standardised measure.
Median insulin on board was 1.76 U on the occasions a low followed and 1.36 U when none did.

Total daily dose spans 16 to 58 U across these participants, a factor of 3.5. Across participants,
median insulin at onset correlates with that participant's own low rate at minus 0.388.

A separate construction over 686 events in eight participants reports the opposite direction, with
a median of 0.96 U on the occasions that ended low against 1.61 U on those that did not, and a
pooled area under the curve of 0.463.

The post-exercise recovery tail is real and modest, at about 1.2 times baseline hazard, flat
across the first five hours.

A rolling day-scale step load does not predict insulin sensitivity. Matched-insulin forward-low
rates differ by a factor of 1.06, the residual slope carries the wrong sign, and the correlation
with the sensitivity ratio is minus 0.06.

## Discussion

The activity result is the solid one and it determines where the protection belongs. A
relationship that is strong pooled and absent across held-out participants says that people differ
in the parameter rather than in the phenomenon, and the response is to estimate the parameter per
person offline. The activity thresholds in the shipping configuration are derived that way.

The post-meal exercise question is unresolved and should be treated as such. Two constructions of
the same question disagree in direction, and the disagreement is instructive rather than merely
inconvenient. The between-participant correlation of minus 0.388 means that in this cohort the
participants who carry less insulin at exercise onset are also the participants who go low more
often, so pooling absolute units across people pulls the association toward inversion whatever is
happening within any individual. Standardising by each participant's own total daily dose, and
resampling participants rather than events, removes that pull and the association points the
ordinary way.

Neither construction supports a mechanistic claim, and in particular neither licenses reading the
contrast as a carbohydrate shortfall rather than an insulin excess. Insulin on board at a moment in
time is not a measure of dose adequacy. It falls as time passes from the bolus, so it is
partly a clock, and it is confounded with how far through the meal the participant is, with what
they ate, and with whether they had already taken carbohydrate in anticipation. Reading a
difference in it as evidence about which of insulin or carbohydrate was at fault requires an
assumption about the counterfactual that the record cannot supply.

What can be said is narrower. Exercise increases glucose disposal by an insulin-independent route
and raises insulin sensitivity for hours afterwards, so the same insulin does more work during and
after it. A low following post-meal exercise is therefore consistent with a dose that was correct
for the meal and incorrect for the meal plus the exercise, and nothing in this record distinguishes
that from a dose that was too large to begin with. The available responses are anticipatory
withdrawal well before the exercise, or carbohydrate taken at its onset, and choosing between them
needs a within-participant trial rather than a further pass over the observational record.

Three limitations bound the post-meal analysis. The event definition is a step-feed proxy for
exercise and will miss activity that does not register as steps. There are 157 events and 36 lows
across five participants, which is small enough that a single participant moves the pooled figure.
And the two constructions differ in their event definitions as well as their standardisation, so
the disagreement is not attributable to standardisation alone.
