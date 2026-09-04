# Meal information in continuous glucose traces: what is present, and when it arrives

## Abstract

An automated insulin delivery system that does not require carbohydrate announcement must read
whatever it can about a meal from the glucose trace alone. We asked what is in that trace, and at
what point after a rise begins it becomes available. Across 492,440 announced meals from 839
participants, with a second corpus of 71,761 meals from 189 participants on different therapy, a
meal is separable from an undeclared rise at 0.843 (95 per cent interval 0.841 to 0.846) ten
minutes after onset, and this holds for every participant with sufficient data. Meal size is not
separable: with the clock and the person held constant, the trace adds 0.002 at ten minutes and
0.008 at sixty, against a pre-registered decision margin of 0.05 by twenty minutes, and as a
quantity a model given everything predicts 13.12 g mean absolute error where the participant's own
median predicts 13.02 g. What appeared in smaller studies to be size read from the trajectory was
the identity of the person and the time of day. Whether a rise will be consequential is predictable
at 0.72 to 0.86, but almost entirely from the glucose at which the rise started and the hour of the
clock; the shape of the trajectory adds 0.014 (0.013 to 0.016) at ten minutes and 0.032 (0.030 to
0.035) at twenty, rising to between 0.049 and 0.082 by thirty minutes. That growth is the signature
of information genuinely arriving from the excursion, and it arrives after the point at which a
controller must commit. Across 1,986,123 rise onsets from 1,807 participants in seven studies the
proportion reaching 40 mg/dL above baseline is 0.833 to 0.859, so a rise that has declared itself
is usually consequential whoever is wearing the sensor. In an engine record of 27,619 onsets the
controller's own forward projection discriminates consequential rises at 0.544 against a base rate
of 0.544, while two quantities it already holds reach 0.625. Sampling faster does not move the
arrival time: one-minute and five-minute records of the same person differ by a single scale factor
of 1.602, flat to 6.6 per cent across a twenty-four-fold range of lag, with matching log-log slopes
and no noise floor in either. In four controller instances run in parallel on one shared sensor, a
one-minute cycle reached its first insulin 1.8 minutes (0.8 to 2.9) sooner than a five-minute cycle.
The remaining gain in reading meals from glucose is therefore not in extracting more information but
in acting sooner on information the controller already has.

## The question

Announcing carbohydrate is the largest remaining demand a hybrid closed loop makes of the person
using it. Systems that drop the announcement must recover, from glucose alone, some or all of what
the announcement carried: that food has arrived, how much of it there was, and whether the resulting
excursion warrants insulin. These are three separate questions and they have different answers.

They also have a property that is easy to lose. Each is a question about a moment. A controller
acting fifteen minutes after a meal begins cannot use information that becomes legible at forty. Any
statement about what a glucose trace contains is incomplete without the horizon at which it contains
it, and the horizons that matter are set by insulin rather than by the sensor. Delivery systems commonly
assume peak insulin action between 45 and 75 minutes after a subcutaneous dose, and glucose-derived
estimates within this programme place it earlier still, so a decision taken at thirty minutes has
already ceded much of its influence over the peak.

This work measures all three quantities on public research corpora, with participants held out as
folds throughout and every interval obtained by resampling participants, and then asks what a faster
sensor would add.

## Data

The size and detection analyses use two corpora of announced meals. The larger contributes 492,440
meals from 839 participants using an open-source automated delivery system; the second contributes
71,761 meals from 189 participants on sensor-augmented pump therapy in an earlier era, and serves as
an independent replication across therapy, era and de-identification scheme. Rescue carbohydrate and
entries below 8 g are excluded. Meal onset is inferred from the trace rather than observed.

The consequence analysis uses rise onsets rather than announcements, which frees it from the
requirement that anybody logged anything, and it therefore draws on all seven studies available:
1,986,123 onsets from 1,807 participants. A rise onset is a climb of at least 25 mg/dL within thirty
minutes beginning above the hypoglycaemia threshold, which is approximately the set of events a
detector fires on.

The analysis plan, including the decision margin of 0.05 in area under the curve at a horizon of
twenty minutes or less, was fixed before these measurements were made.

## Detection is available early and is not the constraint

A declared meal separates from an undeclared rise at 0.843 (0.841 to 0.846) ten minutes after
onset, rising to 0.873 by thirty. The comparison must be built carefully. If the undeclared class is
required to reach 25 mg/dL in thirty minutes while meals are admitted however flat their trace, the
two classes are separated partly by the inclusion rule rather than by physiology, and the artefact
grows with horizon: on that construction the thirty-minute figure reads 0.952. Holding both classes
to the same bar removes it, and the matched figures are the ones quoted here.

Three quantities carry most of it. Glucose value and its short-window delta reach 0.809 of an
eventual 0.843 at ten minutes, and adding curvature reaches 0.821. A detector therefore needs
nothing a controller does not already compute on every cycle.

The property that makes this usable is its uniformity. Scored within each of 815 participants
contributing at least twenty of each class, the tenth centile at ten minutes is 0.778, the median
0.839 and the ninetieth 0.887, and no participant falls below 0.60. Fitted on the larger corpus and
scored on the second without refitting, detection gives 0.807 at ten minutes against 0.818 for a
model fitted within that corpus, so crossing therapy and era costs about a hundredth of a point.

Discrimination is silent about how often a detector fires when nobody ate. Meals meeting the matched
bar occur 0.55 times per participant-day and undeclared rises 1.74 times, so at ten minutes and 70
per cent sensitivity the detector produces 0.35 false alarms and 0.39 true detections per day, and
is right about half the times it fires. At 90 per cent sensitivity it produces more false alarms
than true detections. Waiting to thirty minutes improves this to roughly two true detections per
false alarm, at the cost of twenty minutes. Some undeclared rises are meals nobody logged, and every
one is counted here as a false alarm, so the true operating point is better than the table by an
unknown margin.

## Size is not in the trace

On trajectory features alone, with no clock and nothing about the person, a large meal separates
from a small one at 0.519 (0.510 to 0.528) at ten minutes, reaching 0.608 by sixty. Adding the clock
lifts the ten-minute figure to 0.594, and the clock by itself, with no glucose whatsoever, gives
0.586. Adding the participant's own earlier announced meals gives 0.812 from history alone and 0.830
with the clock.

Set each arm against the arm carrying the same information with the glucose trace removed, and the
trace is worth very little.

| baseline | horizon | with the trace | without it | difference |
|---|---|---|---|---|
| clock only | 10 min | 0.594 (0.586 to 0.601) | 0.586 (0.578 to 0.594) | +0.007 |
| clock only | 60 min | 0.639 (0.631 to 0.648) | 0.586 (0.578 to 0.594) | +0.053 |
| person and clock | 10 min | 0.833 (0.822 to 0.843) | 0.830 (0.819 to 0.841) | +0.002 |
| person and clock | 60 min | 0.838 (0.827 to 0.848) | 0.830 (0.819 to 0.841) | +0.008 |

The diagnosis is in the horizons. Arms carrying participant information sit at 0.833 at ten minutes
and 0.838 at sixty, barely moving as an hour of glucose arrives, while the trajectory-only arm
climbs from 0.519 to 0.608 because it has nothing else to work with. Information that does not
improve as the excursion unfolds did not come from the excursion. A model scoring 0.833 is reading
the diner.

As a quantity the picture is the same. Predicting the participant's own median meal and stopping
gives 13.02 g mean absolute error. A model given the trajectory, the clock, the participant's scale
and their announcement history gives 13.12 g at ten minutes and 13.01 g at sixty. The trajectory arm
alone, at 15.97 g, is worse than predicting the population median.

The relationship between carbohydrate and early glucose is not absent, and it does not need to be
absent for the conclusion to hold. Within participants, comparing their own bolused meals against
their own unbolused ones, carbohydrate is associated with a rising trace when no insulin was given
and a falling one when it was, a difference of +0.0175 (0.0038 to 0.0317) in slope at ten minutes
across 561 participants. In unbolused meals the relationship runs the way physiology says it should,
at +0.0209 mg/dL per gram at ten minutes. Forty grams of difference then moves the ten-minute rise
by 0.83 mg/dL, against a between-meal spread of 9.71 mg/dL. The quantity a controller would have to
resolve is about a twelfth of the noise it sits in, reaching somewhat over a quarter by sixty
minutes, which is why separability appears late and weakly. Dose sizing to an inferred meal is
closed by this, at the horizons at which a dose is sized.

## Consequence is readable, and arrives after the decision

A controller at the moment it must act needs neither the fact of the meal nor its mass. It needs to
know whether the rise in front of it is going somewhere that matters.

Once a rise has cleared 25 mg/dL in thirty minutes, the share going on to reach 40 mg/dL above
baseline is between 0.833 and 0.859 in all seven studies, which differ in therapy, era and age. Five
in six declared rises are consequential on that definition whoever is wearing the sensor, which is
why the thresholds examined here begin at 60 mg/dL.

Where the rise started carries most of what is predictable. Glucose at the onset, a single number
the controller already holds, reaches 0.812 for whether the excursion will exceed 180 mg/dL (10.0 mmol/L) and
0.677 for whether the peak rise will reach 60 mg/dL. Adding the hour of the clock, which is free,
gives 0.829 and 0.717.

What the shape of the trajectory adds must be tested as a paired difference, since both arms score
the same events from the same participants and their errors move together.

| outcome | horizon | baseline | with shape | difference | 95 per cent interval |
|---|---|---|---|---|---|
| peak rise 60 mg/dL or more | 10 min | 0.717 | 0.731 | +0.0142 | +0.0126 to +0.0157 |
| peak rise 60 mg/dL or more | 20 min | 0.717 | 0.750 | +0.0323 | +0.0300 to +0.0347 |
| glucose exceeds 180 mg/dL | 10 min | 0.829 | 0.843 | +0.0140 | +0.0126 to +0.0156 |
| glucose exceeds 180 mg/dL | 20 min | 0.829 | 0.855 | +0.0267 | +0.0245 to +0.0288 |

Every interval excludes zero. The gains are real and they are small, and their shape differs from
the size result in the way that matters. For size the trace was worth 0.002 at ten minutes and 0.008
at sixty, and the flatness was the diagnosis. Here the contribution grows monotonically, +0.014 at
ten minutes, +0.020 at fifteen, +0.027 to +0.032 at twenty, and +0.049 to +0.082 at thirty, on every
one of five outcomes. Information is genuinely arriving from the trajectory. Applying the
pre-registered margin of 0.05 by twenty minutes, nothing clears it; the largest twenty-minute gain
is +0.032. The bar is cleared at thirty minutes, by which time the decision that mattered has been
taken.

## Signals held but unused by the controller

The two quantities that carry the consequence signal, onset glucose and the clock, are available to
any controller without either a detector or a model. Joining an engine record to the outcomes
gives 27,619 rise onsets from 36 participants on which what the loop computed can be scored directly
against what happened.

| what is scored | area under the curve |
|---|---|
| base rate | 0.544 |
| the loop's forward projection | 0.544 |
| the loop's projection and insulin on board | 0.543 |
| onset glucose and the clock | 0.625 |
| the loop record added to onset glucose and the clock | 0.625 |

The forward projection, the quantity on which dosing decisions rest, is at chance for whether the
excursion it is projecting will be consequential. Two numbers the loop holds at the same instant
reach 0.625, and adding the entire loop record to them contributes 0.001. This is not new signal. It
is an unused reading of signal already in hand, and it is the one lever in this programme that
survived a control designed to kill it.

The arm scoring delivered insulin reaches 0.426, below chance, and is uninterpretable: insulin
delivered in response to a rise changes the outcome against which it is scored.

## Sampling faster does not move the arrival time

If the useful information about a consequential rise arrives at around thirty minutes, the obvious
remedy is to sample more often. It does not work, and the reason is a property of the glucose signal
rather than of any particular sensor.

One participant wore a five-minute sensor for 83 days and then a one-minute sensor for 61. Compared
through the variogram, which is expressed in minutes of lag and therefore places both cadences on
one axis without resampling either, the two records differ by a single number. The ratio of their
variograms is 1.602, varying by 6.6 per cent of its mean across a twenty-four-fold range of lag,
with no bend at the short end. The log-log slope is 1.35 (1.30 to 1.39) against 1.35 (1.28 to 1.39)
in the shared bands, and below five minutes, where only the faster sensor can see, it is 1.49 (1.13
to 1.70), containing the value above. The same power law runs from one minute to sixty. Neither
record shows the flattening at small lag that additive measurement noise would impose, so both
sensors report already-filtered values and smoothing rather than sampling interval sets how clean a
trace is.

There is consequently nothing below five minutes for a detector to find. What a faster feed does
supply is scheduling: a decision cycle that runs every minute waits less for its next opportunity to
act. Four controller instances were run in parallel on one person, three of them sharing a single
sensor and reporting identical glucose at identical timestamps. Timed from a rise onset in that
shared trace, the one-minute instance reached its first insulin 1.8 minutes sooner than the
five-minute instance (0.8 to 2.9), and a second one-minute instance with wider bolus spacing 1.2
minutes sooner (0.7 to 2.0). On falls, the suspension already in force when glucose began to drop
was 2.6 minutes older (1.1 to 3.0). Each of these is of the order of the sampling interval it came
from, which is what a scheduling effect looks like and is not what new information looks like.

## Consequences

Three findings sit together. Detection is solved and is not where the difficulty lies. Size is not
recoverable from the trace at any horizon at which a dose would be sized, and the apparent ability
to recover it in smaller studies was the person and the clock. Consequence is recoverable, is
genuinely arriving from the trajectory, and arrives after the moment of commitment.

The design consequence is that effort spent on richer inference from the excursion is likely to be
wasted, while two changes are available immediately. The first is to price consequence at onset from
glucose and the clock, which the controller holds and does not currently combine, and which
outperforms its own forward projection on that question by 0.08. The second is to reduce the delay
between information and action, since the information the controller will eventually act on is
already determined by the time it acts. A faster decision cycle buys one to three minutes of that,
and buys nothing else.

Neither of these is a claim that acting differently would improve any outcome. That question is not
answerable from observational corpora and requires the within-participant randomised comparison that
the programme's evidence bar demands before a dosing change ships.

## Limitations

Announced carbohydrate is an estimate made by the person eating, and its error places a ceiling on
measured accuracy that this design cannot separate from the ceiling imposed by physiology. Meal
onset is inferred from the trace rather than observed, so a meal announced far from the eating is
anchored imprecisely. The undeclared class contains dawn phenomenon, stress responses and rebounds,
which differ in shape for reasons other than carbohydrate, so the detection comparison bounds what a
detector can achieve rather than isolating carbohydrate. Outcomes in the consequence analysis are
read from traces produced under active insulin therapy, so what is predicted is the excursion that
occurred given the treatment given. The consequence modelling uses 200 of the 1,807 available
participants; intervals are narrow and effect sizes stable across the sweep, but a full-corpus run
has not been done. The cadence comparison rests on one participant, in two sensor eras that are not
glycaemically matched and in four parallel instances of which three commanded a virtual pump, and
its magnitudes should be read as describing what controllers propose rather than what they would
achieve. Participants in the corpora are not users of the system this programme develops, so what
transfers is a statement about the information in a glucose trace and not about any controller's
response to it.
