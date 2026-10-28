# Telling that food arrived: detection on 850 participants (2026-08-25)

*Reproduce: `detection.py`, `detection_diagnostics.py` and `accel_vs_model_v2.py` and `streaming_detection.py` against the `studies` schema of the local
TimescaleDB, sharing the extraction built by `extract_meals.py`. 492,440 announced meals from 839
participants against 562,564 undeclared rises from 850, spanning 323,965 participant-days, with a
second corpus of 71,761 meals and 92,050 rises from 189 participants on different therapy.
Participants are held out as folds and intervals come from resampling participants. Protocol:
`backtesting/protocols/2026-08_meal_size_readability_PREREG.md`, secondary analysis.*

## What is being measured

A controller without carbohydrate announcement has to decide, from glucose alone, that food has
arrived. The comparison that answers this is a declared meal against a rise nobody declared. The
undeclared class is built as rises of at least 25 mg/dL within thirty minutes, above the
hypoglycaemia threshold, with no carbohydrate entered within two hours either side.

That rule admits an undeclared rise only when it is substantial, while admitting a meal however
flat its trace. The two classes are then separated partly by the inclusion criterion rather than by
physiology, and the effect grows with horizon, because a meal that never rises becomes steadily
easier to distinguish from a rise that had to reach 25 mg/dL. Holding both classes to the same bar
removes it.

| Horizon after onset | Both classes held to the same bar | 95% CI | Meals admitted without the bar |
|---|---|---|---|
| 10 min | 0.843 | 0.841 to 0.846 | 0.833 |
| 15 min | 0.851 | 0.848 to 0.853 | 0.855 |
| 20 min | 0.865 | 0.862 to 0.867 | 0.896 |
| 30 min | 0.873 | 0.871 to 0.875 | 0.952 |
| 45 min | 0.865 | 0.863 to 0.867 | 0.930 |
| 60 min | 0.861 | 0.859 to 0.864 | 0.918 |

The left column is the one to quote. Detection is available at ten minutes and gains about three
points over the following twenty, then falls back. The second corpus gives 0.818 at ten minutes and
0.863 at thirty on the matched comparison, close enough across a different therapy and era to treat
the figure as a property of glucose traces rather than of one population.

## What carries it

| Horizon | Value and delta | With curvature | All twelve shape features |
|---|---|---|---|
| 10 min | 0.809 | 0.821 | 0.843 |
| 30 min | 0.815 | 0.851 | 0.873 |

Three features reach 0.809 of an eventual 0.843 at ten minutes, and five reach 0.821. This agrees
with the programme's standing finding that glucose value, delta and curvature carry essentially all
of the short-horizon information, and it means a detector needs nothing the loop does not already
compute every cycle.

## Whether it works for everybody

Scored within each participant who contributes at least twenty of each class, at ten minutes the
tenth centile is 0.778, the median 0.839 and the ninetieth 0.887, across 815 participants. None
falls below 0.60. At thirty minutes the same figures are 0.823, 0.873 and 0.907. There is no
subgroup for whom detection fails, which is unusual in this programme and is the strongest practical
property the measurement has.

## Whether it transfers

Fitted on the larger corpus and scored on the second without any refitting, detection gives 0.807
at ten minutes and 0.855 at thirty. Fitted and scored within the second corpus it gives 0.818 and
0.863. Crossing therapy, era and de-identification scheme costs about a hundredth of a point, so a
detector trained on one population is very nearly as good on another as one trained on that
population.

## What it would cost to run

An area under the curve is silent about how often a detector fires when nothing was eaten. Meals
meeting the matched bar occur 0.55 times per participant-day and undeclared rises 1.74 times, so
the negative class outnumbers the positive by about three to one and the operating point is where
the practical answer lives.

| Horizon | Sensitivity | False positive rate | False alarms per day | True detections per day |
|---|---|---|---|---|
| 10 min | 70% | 0.202 | 0.35 | 0.39 |
| 10 min | 80% | 0.294 | 0.51 | 0.44 |
| 10 min | 90% | 0.442 | 0.77 | 0.50 |
| 30 min | 70% | 0.126 | 0.22 | 0.39 |
| 30 min | 80% | 0.221 | 0.38 | 0.44 |
| 30 min | 90% | 0.409 | 0.71 | 0.50 |

At ten minutes and 70 per cent sensitivity the detector is right about half the times it fires. Push
it to 90 per cent and it produces more false alarms than true detections. Waiting to thirty minutes
improves the economics, to roughly two true detections for every one false alarm at 70 per cent, at
the cost of twenty minutes.

One caveat runs the other way and cannot be resolved from these data. Some undeclared rises are
meals somebody forgot to log, and every one of those is counted as a false alarm here. The false
alarm figures are therefore an upper bound, and the true operating point is somewhere better than
the table says by an unknown margin.

## The shipped shadow against a corpus-trained detector

The accelMeal shadow is a fixed threshold on glucose curvature, `accel = shortAvgDelta -
longAvgDelta`, firing when `accel > 2.0` with the trace rising and the engine not yet confirmed. It
reads the second derivative of glucose rather than an accelerometer, so it sits inside the same
information class as the fitted detector and the two can be compared on identical inputs.

The comparison can only be made where the shadow runs and carbohydrate is announced, which is two
participants, E and F, contributing 37 and 34 meal onsets over 22 and 21 days. Both detectors are
run over the whole timeline and their firings collapsed into episodes, since the shadow is a
per-cycle flag and one rise sets it on many consecutive cycles. An episode is credited when it
begins within 15 minutes before or 45 minutes after an announced onset.

| participant | detector | meals caught | false alarms per day |
|---|---|---|---|
| E | shadow | 35.1% | 5.94 |
| E | model at 10 min, same false alarms | 27.0% | 5.94 |
| E | model at 30 min, same false alarms | 43.2% | 5.94 |
| E | model at 30 min, same sensitivity | 35.1% | 4.05 |
| F | shadow | 38.2% | 6.08 |
| F | model at 10 min, same false alarms | 41.2% | 6.08 |
| F | model at 20 min, same false alarms | 44.1% | 6.08 |
| F | model at 30 min, same sensitivity | 38.2% | 6.69 |

The model wins some cells and loses others, by margins of a few points on 34 to 37 meals, where a
difference of fifteen points would not be distinguishable. On this evidence a detector fitted on 839
participants does not beat two lines of arithmetic on the same signal.

That is consistent with the ablation. Value and delta alone reach 0.809 of an eventual 0.843, and
adding curvature reaches 0.821, so a threshold on curvature and direction is already close to the
ceiling of what this feature class supports. The shadow is not leaving much on the table.

Two things distort the absolute numbers and both should be read as bounds rather than measurements.
E announced 58 meals of which 37 survive the rescue and separation rules, and F 53 of which 34
survive, over three-week windows; at fewer than two surviving meals a day, a substantial share of
what is scored as a false alarm is food. And the fitted model is handicapped in this form: it was
trained on windows anchored at a detected onset, and streaming it means asking it to read windows
anchored at arbitrary points. A deployment would pair onset detection with the model rather than
scoring every cycle, and this comparison does not measure that arrangement.

Confidence: PROVISIONAL. Two participants, 71 meals, differences inside the noise, and a ground
truth known to be incomplete.

## Continuous operation, which is what a controller does

The figures above rank a curated set: meal onsets against undeclared rises of at least 25 mg/dL. A
controller never receives that set. It gets a reading every five minutes, must decide each time,
and is charged for every firing. Measuring both detectors that way, on 200 participants, 121,334
meal onsets and 78,268 participant-days, gives a different picture from 0.843.

Both run on the same cycles. The shadow is the shipped rule reproduced from source, with the oref
delta windows and the threshold of 2.0. The model is fitted on the same features in the same
streaming form, on training participants and scored on held-out ones, which removes the handicap of
training on onset-anchored windows and then serving arbitrary ones. Firings are collapsed into
episodes and an episode is credited when it begins within 15 minutes before or 45 minutes after an
onset.

| detector | meals caught | false alarms per day | precision |
|---|---|---|---|
| shadow, as shipped | 55.1% | 7.51 | 11.4% |
| model, at its best operating point | 47.1% | 4.19 | 16.5% |
| model, at 2.90 false alarms per day | 41.5% | 2.90 | 20.0% |

Meal onsets occur 1.75 times per participant-day, so at the shadow's operating point roughly one
firing in nine is a meal, and at the model's best roughly one in six, rising to one in five if it is tightened to 2.90. Neither detector dominates:
the shadow catches more meals, the model is right more often when it fires, and the model's curve
never reaches the shadow's sensitivity at any threshold. Across participants the shadow ranges from
35.8 to 68.2 per cent.

The model curve is not monotonic in its threshold, and the reason is worth stating because it is a
property of continuous operation rather than of the model. Lowered far enough, a detector fires
almost always, its firings merge into a few long episodes, and an episode that began hours before a
meal earns no credit. Sensitivity and false alarms fall together. An always-on detector is
indistinguishable from a silent one under any crediting rule that asks when the alarm started.

So the gap between 0.843 and eleven per cent precision is not a modelling failure. It is what the
same discrimination looks like when the negative class is every five minutes of the day rather than
a curated set of rises, and it is the reason detection quality is not the lever it appears to be.
The same caveat applies as elsewhere: some undeclared rises are meals nobody logged, so precision
is understated by an unknown margin.

What follows is an architectural point rather than a modelling one. If a detection is right between
one time in nine and one time in six, then committing a full dose on detection is the wrong
response regardless of which detector produced it, and a small initial commitment that escalates
only once the excursion declares itself is the right shape. That is the staged design, reached here
from a different direction than the size result reached it.

## What this supports

Detection is not the constraint on an unannounced-meal controller. It is available within ten
minutes at 0.843, it needs three to five features the loop already has, it works for every
participant measured, and it transfers between populations at a cost of about 0.01. Against that,
size is not readable from the same traces: 0.519 at ten minutes on the trajectory alone, and 0.007
above a model that knows only who is eating and at what hour.

The honest bar for the accelerometer meal shadow is 0.843 at ten minutes and 0.873 at thirty.

The operating point is the part that bears on whether a better detector would help. A false
detection commits insulin into a rise that no food caused, and the high-IOB tail is where this
programme's lows repeatedly originate. Moving along this curve towards higher sensitivity buys
detections at a rate of roughly one false alarm each, so the question a controller faces is not how
to detect better but what to do about the fact that at any useful sensitivity a material share of
detections are wrong.

Confidence: SOLID. Out of sample with participants held out, intervals from resampling
participants, replicated in an independent corpus, and the headline is quoted from the construction
that removes the inclusion asymmetry rather than the one that flatters it.

## Limitations

A declared meal is one the participant chose to declare, and the undeclared class contains dawn
phenomenon, stress responses and rebounds, which differ in shape for reasons other than
carbohydrate. The comparison bounds what a detector can achieve rather than isolating carbohydrate.
Onset is inferred from the trace rather than observed. These participants are not users of this
fork, so what transfers is a statement about the information in a glucose trace and not about any
controller's response to it. Nothing here measures the detector this fork currently ships, because
its users do not announce carbohydrate and no ground truth exists on their records.
