# Recovering meal information from continuous glucose monitoring: what is available to an automated insulin delivery system, and when

## Abstract

**Background.** Carbohydrate announcement remains the principal demand hybrid closed-loop systems
make of the people using them. Systems that dispense with it must recover from the glucose trace
whatever the announcement carried. It is not established how much of that information the trace
holds, or at what point after a meal begins it becomes available.

**Methods.** Announced meals and undeclared glucose rises were extracted from seven public research
datasets. Meal detection and meal size were assessed on 492,440 announced meals from 839
participants, with independent replication in 71,761 meals from 189 participants on earlier
sensor-augmented pump therapy. A third question, whether a rise will become clinically consequential,
was assessed on 1,986,123 rise onsets from 1,807 participants, since its outcome is readable from
the trace and requires no announcement. Participants were held out as folds throughout and all
intervals derive from resampling participants. The analysis plan and a decision margin of 0.05 in
area under the receiver operating characteristic curve at twenty minutes or less were fixed in
advance.

**Results.** A declared meal was distinguishable from an undeclared rise ten minutes after onset
with an area under the curve of 0.843 (95% CI 0.841 to 0.846), with no participant below 0.60 of 815
assessed. Meal size was not recoverable: against a matched comparator carrying participant identity
and time of day with the glucose trace withheld, the trace contributed 0.002 at ten minutes and
0.008 at sixty, against a pre-registered margin of 0.05. Predicting each participant's own median
meal gave a mean absolute error of 13.02 g, which a model given trajectory, clock, participant scale
and full announcement history did not improve upon (13.12 g at ten minutes). Whether a rise would
exceed 10.0 mmol/L was predictable at 0.812 from onset glucose alone and 0.829 with time of day
added; trajectory shape contributed a further 0.014 (0.013 to 0.016) at ten minutes, rising to
between 0.049 and 0.082 by thirty minutes.

**Conclusions.** The fact of a meal is recoverable from continuous glucose monitoring early and
reliably. Its carbohydrate content is not, at any horizon at which a prandial dose would be sized,
and apparent success at this task reflects knowledge of the individual and the hour rather than of
the meal. The clinically tractable question is whether an excursion will become consequential, which
is answerable at onset from information a controller already holds.

## Background

Automated insulin delivery has reduced but not removed the work of living with type 1 diabetes. The
demand that remains most consistently is carbohydrate announcement: estimating the content of a meal
and entering it before eating. Estimation is difficult, error is substantial, and the burden falls
on the person at every meal for life.

Systems that remove the announcement must obtain the information some other way, or establish that
they do not need it. Unannounced-meal handling is not new, and most current systems respond to a
rise once it is established. What has not been established is the ceiling: how much of what an
announcement carries is present in the glucose trace at all, and at what point after a meal begins it
becomes legible.

That second clause matters more than it may appear. Subcutaneous rapid-acting analogue is commonly
assumed by delivery systems to reach peak action between 45 and 75 minutes after a dose, and
glucose-derived estimates within our own work place it earlier. A decision taken thirty minutes into
an excursion has therefore ceded much of its influence over the peak. Information that becomes
legible at forty minutes is of limited use to a controller that had to act at fifteen.

We separate three questions that are commonly treated as one. Whether food arrived. How much of it
there was. Whether the resulting excursion will matter.

## Methods

### Data

Seven public research datasets contributed. Two carry carbohydrate announcements and support the
detection and size analyses: a large contemporary corpus from an open-source automated delivery
system (492,440 meals, 839 participants) and an earlier sensor-augmented pump cohort (71,761 meals,
189 participants), the latter serving as independent replication across therapy, era and
de-identification scheme. The remaining five record no carbohydrate and contribute to the
consequence analysis only.

Meals below 8 g were excluded, as were entries made at or below 4.4 mmol/L, which are treated as
rescue carbohydrate. Where entries fell within ninety minutes of one another the first was kept
as the meal and the rest were not counted, so a meal entered in parts is recorded at the size of
its first part. Meal onset was inferred from the trace rather than observed.

That rule sets aside 26 per cent of entries and 22 per cent of all carbohydrate. For the 28 per
cent of meals that lose something, the recorded size is a median 25 g against 55 g for the
eating occasion it belongs to. Re-extracting with those entries added to the meal rather than
set aside raises the median meal from 28 g to 34 g and leaves every result below unchanged: the
trace then adds 0.006 at ten minutes over the clock rather than 0.008, and 0.032 rather than
0.021 over the fuller baseline, both still short of the 0.05 margin. On quantity the model
matches each participant's own median on either definition.

What remains is an announcement rather than a meal, and its distribution should be stated because it
conditions everything that follows. Participants announced a median of 2.1 times per day, with a
median announcement of 28 g and an interquartile range of 16 to 44 g. Just under half were 30 g or
more and a fifth were 50 g or more.

Announced carbohydrate totalled a median of 63 g per participant-day, with 92% of participants below
100 g. That is well under typical intake, so a substantial part of what these participants ate was
not announced. Two consequences follow. The undeclared class used as the comparison for detection
contains genuine unannounced meals, which makes the false-alarm figures reported below conservative
by an unknown margin. And the size analysis concerns the size of announced meals, which may differ
systematically from the size of all meals.

### Definitions

A rise onset is a rise of at least 1.4 mmol/L within thirty minutes, beginning above the
hypoglycaemia threshold. This approximates the set of events on which a detector would fire, and it
defines both the negative class for detection and the anchor for the consequence analysis.

For detection, the comparison is a declared meal against a rise nobody declared. An asymmetry
arises here that materially affects the result. If undeclared rises must reach 1.4 mmol/L in thirty
minutes while meals are admitted however flat their trace, the classes are separated partly by the
inclusion rule rather than by physiology, and the artefact grows with horizon. We report the
matched construction, in which both classes face the same bar. The unmatched construction inflates
the thirty-minute figure from 0.873 to 0.952 and should not be quoted.

### Analysis

Discrimination is reported as area under the receiver operating characteristic curve, where 0.5 is
chance. Participants were held out as folds, so every score comes from a model that never saw that
participant. Intervals come from resampling participants rather than observations, since
observations within a participant are not independent.

Where two models score the same events, we report the paired difference and its interval. Two areas
under the curve each carrying their own interval do not establish that they differ, because their
errors are correlated.

The analysis plan and the decision margin of 0.05 at twenty minutes or less were pre-registered.

## Results

### Detection of a meal

Ten minutes after onset, a declared meal was distinguishable from an undeclared rise at 0.843 (0.841
to 0.846). Discrimination improved by approximately three points over the following twenty minutes
and then declined.

Glucose value and its short-window delta reached 0.809 of that figure; adding curvature reached
0.821. No quantity beyond those a controller already computes each cycle is required.

Performance was uniform across individuals. Assessed within each of 815 participants contributing at
least twenty events of each class, the tenth centile was 0.778, the median 0.839 and the ninetieth
0.887. No participant fell below 0.60. Fitted on the larger corpus and applied to the second without
refitting, discrimination was 0.807 at ten minutes against 0.818 for a model fitted within that
corpus, so transfer across therapy and era cost approximately one hundredth.

Discrimination is silent on how often a detector fires when nobody has eaten, which is the quantity
that determines whether it can be deployed. Meals meeting the matched criterion occurred 0.55 times
per participant-day; undeclared rises occurred 1.74 times.

| sensitivity at ten minutes | false positive rate | false alarms per day | true detections per day |
|---|---|---|---|
| 70% | 0.202 | 0.35 | 0.39 |
| 80% | 0.294 | 0.51 | 0.44 |
| 90% | 0.442 | 0.77 | 0.50 |

At 70% sensitivity a detector is correct on approximately half of the occasions it fires. At 90% it
produces more false alarms than true detections. Deferring to thirty minutes improves this to
approximately two true detections per false alarm.

One consideration runs the other way and cannot be resolved within these data. An unknown proportion
of undeclared rises are meals the participant did not record, and each is counted here as a false
alarm. The operating characteristics above are therefore conservative.

### Meal size

Meal size was not recoverable from the trajectory.

Against a matched comparator carrying participant identity and time of day with the glucose trace
withheld, the trace contributed 0.002 at ten minutes and 0.008 at sixty. The pre-registered margin
was 0.05 at twenty minutes or less.

Expressed as a quantity, predicting each participant's own median meal and disregarding glucose
entirely gave a mean absolute error of 13.02 g. A model given the trajectory, the clock, participant
scale and complete announcement history gave 13.12 g at ten minutes and 13.01 g at sixty. A model
given the trajectory alone performed worse than the population median.

The pattern across horizons identifies what the models were reading. Arms carrying participant
information scored 0.833 at ten minutes and 0.838 at sixty, changing little as a full hour of
glucose accrued, while a trajectory-only arm rose from 0.519 to 0.608. Discrimination that does not
improve as an excursion unfolds did not derive from the excursion. A model scoring 0.833 is
identifying the individual, not the meal.

The underlying physiological relationship is present and correctly signed. Compared within
participants, carbohydrate was associated with a rising trace where no insulin preceded the meal and
a falling one where it did, a difference in slope of 0.0175 (0.0038 to 0.0317) at ten minutes across
561 participants. Among unbolused meals the slope was approximately 0.001 mmol/L per gram at ten
minutes. A difference of 40 g therefore displaces the ten-minute rise by 0.05 mmol/L, against a
between-meal standard deviation of 0.54 mmol/L. The signal is approximately one twelfth of the
variability in which it sits, reaching one quarter only by sixty minutes.

Sizing a prandial dose to an inferred meal is therefore not achievable from the glucose trace at any
horizon at which such a dose remains useful.

### Whether an excursion will be consequential

At the moment of decision a controller requires neither preceding answer. It requires an estimate of
whether the excursion before it warrants intervention.

Once a rise has cleared 1.4 mmol/L within thirty minutes, the proportion proceeding to a peak rise
of 2.2 mmol/L above baseline was between 0.833 and 0.859 across all seven datasets, which differ in
therapy, era and age. Five in six established rises are consequential on that definition.

Onset glucose alone predicted whether the excursion would exceed 10.0 mmol/L at 0.812. Adding time
of day gave 0.829.

| additional discrimination from trajectory shape | 10 min | 20 min | 30 min |
|---|---|---|---|
| peak rise of 3.3 mmol/L or more | +0.014 | +0.032 | +0.049 to +0.082 |
| glucose exceeds 10.0 mmol/L | +0.014 | +0.027 | +0.049 to +0.082 |

All intervals excluded zero. The contribution is genuine and it accrues monotonically, which
distinguishes it from the size result, where the flat profile across horizons indicated that the
discrimination never derived from the excursion at all. Here information does arrive from the
trajectory. It arrives after the point of decision: the pre-registered margin is met at thirty
minutes and not before.

### What a controller already encodes

The two quantities carrying most of this discrimination are available without additional sensing or
modelling. To establish whether a controller already exploits them, an engine record was joined to
outcomes across 27,619 rise onsets from 36 participants.

| model | area under the curve |
|---|---|
| base rate | 0.544 |
| controller's forward glucose projection | 0.544 |
| onset glucose and time of day | 0.625 |
| complete engine record added to the above | 0.625 |

The forward projection, on which dosing decisions rest, was at chance for whether the excursion it
projected would prove consequential. Two quantities held at the same instant reached 0.625, and the
remainder of the engine record contributed 0.001.

### Sampling interval

If the useful discrimination accrues at around thirty minutes, a shorter sensor interval is an
obvious remedy. It does not provide one.

One participant wore a five-minute sensor for 83 days and a one-minute sensor for 61. Compared
through the variogram, which is expressed in minutes of lag and therefore places both cadences on a
single axis without resampling, the two records differed by a single scale factor of 1.602, varying
by 6.6% of its mean across a twenty-four-fold range of lag, with no inflection at the short end.
Log-log slopes matched in both shared bands. Below five minutes, where only the faster sensor
observes, the slope contained the value obtained above. Neither record exhibited the flattening at
short lag that additive measurement noise imposes.

No additional structure exists below five minutes. What a shorter interval provides is scheduling.
In four controller instances run in parallel on one participant, three sharing a single sensor, a
one-minute cycle reached its first microbolus 1.8 minutes (0.8 to 2.9) earlier than a five-minute
cycle, and its basal suspension at the onset of a fall was 2.6 minutes (1.1 to 3.0) older. Both
intervals are of the order of the sampling interval from which they derive.

## Discussion

These findings bear directly on how mealtime management might be automated.

The fact of a meal is recoverable early, reliably, and for everyone. A detector requires no
quantities a controller does not already compute, transfers between populations at negligible cost,
and has no identifiable subgroup in which it fails. Detection is not the obstacle to
announcement-free operation.

Meal size is not recoverable, and the strength of the evidence is worth stating plainly. This was
tested on 830 times the meals and 140 times the participants of the preceding study in our own
programme, held out by participant, replicated in an independent cohort on different therapy, and
compared against a matched comparator rather than against chance. The physiological relationship
exists and runs in the expected direction. It is an order of magnitude below the between-meal
variability at the horizons at which a prandial dose would be given. Reports of meal size estimated
from glucose should be interpreted against a comparator that carries participant identity and time
of day, since in our data that comparator accounts for essentially all of the apparent performance.

The practical consequence is that a system cannot replace a carbohydrate entry with an inferred
equivalent. It does not follow that it requires one. The question a controller must answer at the
moment of action is whether the excursion before it will become consequential, and that is
answerable at onset, principally from the glucose at which the rise began and the time of day. In
the engine record examined here the controller's own forward projection performed at the base rate
on that question while those two quantities did not, which suggests an available improvement that
requires no new sensing.

The limits of a shorter sensor interval follow from the same analysis. The glucose signal contains
no structure below five minutes, so a faster feed cannot make the missing information available
earlier. It confers approximately one to three minutes of scheduling advantage, which is smaller
than the onset of any available actuator.

None of this establishes that acting on a consequence estimate would improve glycaemic outcomes. No
observational corpus can establish that, and a change to dosing behaviour requires a
within-participant randomised comparison.

## Limitations

Announced carbohydrate is an estimate made by the person eating. Its error imposes a ceiling on
measurable accuracy that this design cannot separate from the ceiling imposed by physiology. The
announcement is also incomplete: at a median of 63 g per participant-day it accounts for a fraction
of likely intake, so these are the meals people chose to record rather than the meals they ate.

Meal onset was inferred from the trace rather than observed, so a meal announced at some distance
from the eating is anchored imprecisely.

A meal here is the first entry of a cluster rather than the cluster itself, which understates a
quarter of eating occasions by roughly half. The size analyses were re-run against the
corrected definition and did not move, but every size quoted in this paper is a first entry and
not an eating occasion.

The undeclared class contains dawn phenomenon, stress responses and post-hypoglycaemic rebound,
which differ in trajectory for reasons unrelated to carbohydrate. The detection analysis therefore
bounds achievable performance rather than isolating the response to food.

Consequence outcomes were read from traces produced under active insulin therapy. What is predicted
is the excursion that occurred given the treatment given, not the untreated excursion. The
consequence modelling used 200 of the 1,807 available participants; intervals were narrow and effect
sizes stable across the sweep, but a full-corpus analysis has not been performed.

The sampling-interval comparison rests on a single participant across two sensor eras that are not
glycaemically matched, and on four parallel controller instances of which three commanded a virtual
pump. Its magnitudes describe what controllers propose rather than what they achieve.

Participants in these datasets do not use the system under development in this programme. What
transfers is a statement about the information contained in a glucose trace, not about any
particular controller's response to it.

## Data and reproducibility

All corpora are public research datasets. Extraction, modelling and interval estimation are
performed by scripts committed alongside this report, against a local copy of the datasets. The
pre-registered analysis plan is committed separately and predates the measurements.
