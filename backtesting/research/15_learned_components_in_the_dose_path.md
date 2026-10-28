# The two pre-trained models on the dose path

What a pair of pre-trained gradient-boosted models contributes over the glucose reading the algorithm
already has, and what happens to a consumption threshold when the model beneath it is replaced.

## Abstract

The shipping controller is deterministic apart from two gradient-boosted tree models applied at
inference, whose outputs reach the dose. Both were trained on a foreign cohort of roughly three
million cycles and validated before deployment by grouped cross-validation and by an out-of-cohort
transfer test on six participants, and neither had since been scored against the telemetry of the
people running them. Scoring each against the target recorded in its own metadata asset, over ten
participants with intervals from a cluster bootstrap resampling participants, the meal model reaches
an area under the curve of 0.722 with an interval from 0.684 to 0.757, against a training
leave-one-participant-out figure of 0.7375, and beats the strongest trivial alternative available on
the same rows by 0.144 with an interval from 0.054 to 0.233. The hypoglycaemia model reaches 0.655
with an interval from 0.606 to 0.701 against a training figure of 0.8317, and beats the negated
glucose reading by 0.068 with an interval from 0.046 to 0.104. Its predecessor, an eight-feature
model, did not: on its own era it reaches 0.606 against 0.605 for glucose alone, a difference of
0.018 with an interval from minus 0.037 to plus 0.113. Any figure computed across the boundary
between the two is a mixture rather than a measurement, because the score column pools outputs from
models with different targets and different output scales. Calibration holds through nine deciles and
fails in the tenth, which predicts 0.392 and observes 0.072. The mechanism is stale history. Thirty six
of the 53 features come from a persisted six-cycle buffer that is never invalidated by age, so a
cycle arriving after a break in the decision series is scored against snapshots from before the
break. Rebuilding the vector offline reproduces the engine's published score to a median absolute
error of 0.0028 to 0.0060 per participant on contiguous cycles, and on cycles following a break the
carried-history hypothesis beats both a cleared buffer and true contiguous history for all nine
participants. A third of scored cycles follow a break, and at glucose between 100 and 160 mg/dL they
cross the damper threshold on 8.61 per cent of cycles against 3.92 for the rest. Discrimination is
unaffected, at 0.654 against 0.651.

## Introduction

Two questions attach to any learned component inside a control loop, and only the first is usually
asked. The first is whether it was validated. The second is whether it is still doing what it was
validated to do.

These two models are the only statistical objects in the programme permitted to change what the pump
delivers, which makes both questions consequential. The hypoglycaemia model damps the delivered
quantity above a threshold and blocks the more aggressive response tiers above a second one. The meal
model releases a hold on the gentler tiers when an unannounced meal looks likely.

The proposition that produced them was narrow rather than general. The algorithm inherited a binary
safety gate suspending delivery when a projected minimum glucose fell below a threshold. A gate of
that shape is a single-feature classifier with a hand-placed cut, and it separated dangerous cycles
from safe ones at an area under the curve of 0.62, suspending unnecessarily on 66 per cent of the
occasions it fired and missing a third of the events it existed to catch. A small learned model over
features the algorithm had already computed reached 0.80 on the same data. The claim was not that
machine learning would improve dosing in general; it was that this particular gate was a weak
classifier that could be replaced by a stronger one at no cost in inputs.

## Methods

Four design questions were settled before either model was built.

Model class was settled by a factorial comparison over 1,491,790 decision points from 21
participants: two targets, two architectures being gradient-boosted trees and logistic regression,
and two subgroups split on whether dynamic sensitivity was active. All eight models used the same 28
features, the same folds and the same cost-sensitive weighting, so that architecture was the only
quantity varying. Shapley values gave per-feature attribution.

Feature count was settled by preferring an eight-feature subset already present as parameters of the
dosing function, on the grounds that it required no additional data fetch and therefore added no
coupling between the model and the rest of the algorithm's state.

Deployment format was settled between the LightGBM C library through the Java native interface, a
portable inference runtime, and exporting the trees as JSON and walking them in Kotlin. The last
requires about fifty lines, has no native dependency and costs roughly five milliseconds against a
five-minute cycle.

Validation discipline was settled by the failure of an alternative. Tuning the hypoglycaemia model's
hyperparameters with a random rather than a grouped split reported a fourteen point gain; grouped by
participant the honest gain was 0.7 points. Splits hold participants out throughout.

The field audit is recorded under `backtesting/scripts/2026-08-ml-field-audit/`. It takes one
decision row per participant per five-minute bucket, scores each model against the target in its own
metadata asset, and reports the area under the curve per participant and pooled, with intervals from
a bootstrap resampling participants rather than observations. Forward outcomes come from the sensor
series rather than from the decision record, so a label does not depend on the loop having run, and
hypoglycaemia spans are measured in wall-clock time so that the definition means the same thing at
either sensor cadence.

Three additions make the result interpretable. Trivial predictors are scored on identical rows against
identical labels, so that a model's figure is read against what the algorithm already knew rather than
against chance. The same scores are re-scored at horizons from 30 minutes to four hours, to separate a
weak model from a horizon at which nothing is predictable. And the analysis is restricted to a single
model generation, because the stored score column pools the outputs of successive models with
different targets and different output scales, and any quantity computed across that boundary is a
mixture.

The audit is measured on policy: a high score reduces the delivered quantity, which suppresses some of
the events being predicted, biasing the figure toward zero. The calibration table therefore carries the
damper the engine would have applied at each score, so that the confound can be priced rather than
merely conceded.

## Results

The architecture comparison separates the two model classes. Gradient boosting beats logistic regression by 10 to 21
points in every one of the four strata, the largest gap being on hypoglycaemia with static
sensitivity at 0.910 against 0.701, which places the signal firmly in the non-linear part of the
feature space. Outcomes are markedly more predictable under static than under dynamic sensitivity,
0.910 against 0.840, consistent with a dynamic adjustment introducing variation a single decision
point cannot see.

The eight-feature models trained on roughly three million cycles from 28 participants reached 0.7011
grouped and 0.6796 leave-one-participant-out for hypoglycaemia, and 0.7342 and 0.7375 for meals. The
out-of-cohort transfer test on six participants over 72 days and roughly 110,000 cycles returned 0.679
against a leave-one-participant-out baseline of 0.680 for hypoglycaemia and 0.771 against 0.738 for
meals, and a before-and-after comparison on an in-cohort participant gave 0.642 against 0.633,
indicating no drift from closing the loop around the model.

The hypoglycaemia model was subsequently revised. Its horizon moved from four hours to 90 minutes and
its label from two consecutive readings below 70 to a run below 70 sustained for at least fifteen
minutes. Its feature vector grew from 8 to 53, being 17 instantaneous features and 36 formed by
carrying six of them back over six cycles through a persisted ring buffer. Trained on 3,007,589 cycles
from 32 participants it reported 0.8391 grouped and 0.8317 leave-one-participant-out.

In the field, on the era of the current model, the meal model reaches 0.722 with an interval from
0.684 to 0.757, every participant between 0.618 and 0.869, monotone calibration from an observed 3.3
per cent in the lowest decile to 41.5 in the highest, and an advantage of 0.144 with an interval from
0.054 to 0.233 over the algorithm's own eventual glucose figure.

The hypoglycaemia model reaches 0.655 with an interval from 0.606 to 0.701, every participant between
0.520 and 0.707, against a training figure of 0.8317. It beats the negated current glucose by 0.068
with an interval from 0.046 to 0.104.

Its predecessor did not. On its own era the eight-feature model reaches 0.606 against 0.605 for the
negated glucose reading, a difference of 0.018 with an interval from minus 0.037 to plus 0.113, while
the meal model on the same era reaches 0.740 and beats its baseline by 0.129.

The horizon sweep locates where the current model contributes. At 30 minutes it reaches 0.799 against
0.817 for glucose alone, a difference of minus 0.010 with an interval from minus 0.061 to plus 0.041.
From 60 minutes outward it adds consistently, at 0.051, 0.068, 0.068, 0.073 and 0.073 for horizons of
60, 90, 120, 180 and 240 minutes, every interval clear of zero.

Probing the exported trees directly, with all features held at cohort medians and one swept, the model
responds correctly to glucose: 0.86 at 45 mg/dL, 0.78 at 65, 0.44 at 75, 0.17 at 90 and 0.08 at 180,
with a weak positive response to insulin on board.

Calibration holds through nine deciles, from 0.013 predicted against 0.017 observed to 0.099 against
0.075, and fails in the tenth, which predicts 0.392 and observes 0.072 against a base rate of 0.036.
The damper is 1.000 through the first nine deciles and 0.934 in the tenth.

The state the high-scoring cycles occupy locates the failure. Cycles above 0.60 sit at a mean glucose
of 66.4 mg/dL with a tenth percentile of 52, which is where the probe says those scores belong, and
cycles below 0.05 sit at 144.2. The band that does not fit is 0.30 to 0.45, at a mean glucose of 122.9
with 1.27 U on board, where the probe says the model should return about 0.10. Across every glucose
band the model over-predicts, by a factor falling from 8.3 below 70 mg/dL to 1.4 above 140, while
discrimination within each band holds between 0.59 and 0.68.

Taking a cycle as running on a partly-filled buffer when fewer than six contiguous cycles precede it,
and a break of thirty minutes as breaking contiguity, 33 per cent of scored cycles qualify. Within
matched glucose bands those cycles score higher than the rest by 0.043 at 80 to 110 mg/dL, 0.032 at
110 to 140 and 0.013 above 140, every interval clear of zero, and lower by 0.053 below 80. Restricted
to glucose between 100 and 160, where the probe places the model well below the threshold, they cross
it on 8.61 per cent of cycles against 3.92, a difference of 4.69 points with an interval from 4.11 to
5.27. Discrimination is unaffected, at 0.654 against 0.651.

The cohort median score fell from 0.364 to 0.038 in the week of the changeover between the two models.
The damper now engages on between 0.49 and 27.7 per cent of scored cycles depending on the
participant, and that spread tracks each participant's own hypoglycaemia rate, at a correlation of
+0.820 with an interval from +0.364 to +0.980. Pooled, the shipped threshold fires on 6.83 per cent of
cycles and selects a population with an observed rate of 0.0687 against a base of 0.0361.

## Discussion

The meal model is the cleanest positive result in the programme. Trained on a foreign cohort, it
predicts unannounced meal rises for a different set of people months later at the accuracy its
cross-validation advertised, having been validated out of cohort twice by different methods and now a
third time. It earns its place and the appropriate action is to leave it alone.

The revision of the hypoglycaemia model achieved what it was meant to. Its predecessor added nothing
over reading the current glucose, which is the finding that would have justified retiring the
component altogether; the current model adds a real and consistent increment from 60 minutes outward.
That the increment is smaller than the training figure suggested is expected rather than alarming,
since the field measurement is on policy and biased toward zero, this cohort is not the training
cohort, and a leave-one-participant-out estimate bounds transfer within a population rather than
across populations. The gap from 0.83 to 0.66 is larger than those explanations comfortably carry, and
the residual is the honest open question.

The tenth decile is the one place the model should not be believed, and it is where the thresholds
operate. Predicting 0.392 and observing 0.072 in the region that drives the damper means the damper's
magnitude is not proportional to the risk it is responding to, even though its direction is right. The
on-policy confound does not account for it: the damper in that decile is 0.934, a reduction of about
seven per cent of the budget, which cannot take a genuine 39 per cent event rate down to 7.

The mechanism is a difference between the history the model was trained on and the history it is
given. Thirty six of the 53 features are lags drawn from a buffer that is persisted across restarts
and trimmed only by length, never by age, so after a break in the decision series it still holds the
snapshots from before the break and presents them as the preceding five cycles. A cycle arriving two
hours after the last one is scored against a trajectory two hours old.

That this is what happens rather than a plausible story about what might happen is established by
rebuilding the feature vector offline and scoring it with the same exported model. On contiguous
cycles the reconstruction reproduces the engine's own published output to a median absolute error
between 0.0028 and 0.0060 depending on the participant, which licenses treating the replay as the
engine. On cycles following a break, three candidate histories were scored against the published
value: the carried snapshots, a cleared buffer falling back to the current cycle, and the true
contiguous history. The carried snapshots win for all nine participants, and by the widest margin
for the two whose damper fires most.

The signature is diagnostic in a way that was visible before the cause was: an error in a feature
carrying history moves the level of a score without disturbing its ranking, which is exactly the
pattern, with discrimination identical either side and calibration not.

That reorders the recommendations. The buffer should discard entries older than the window it claims
to represent, and only then should the thresholds be re-placed, since fixing it will move the
distribution again. Recalibrating first would fit a threshold to a distorted distribution.

The consumption thresholds do need re-placing on their own account. Both were set against the earlier
model's output distribution, in which the cohort median was 0.364, and were not revisited when the
median fell to 0.038. A threshold is a statement about a distribution rather than about a probability,
and replacing the model moved the distribution while leaving the threshold where it was.

The spread in firing rates has two candidate explanations and this sample cannot separate them. It
correlates with each participant's own hypoglycaemia rate at +0.820 with an interval from +0.364 to
+0.980, which would make a damper engaging on a quarter of cycles for one participant and half a per
cent for another the component doing what it was built to do. It also correlates at +0.907 with how
much that participant's scores are distorted by stale history. The two participants who dominate
both correlations are the same two, and nine participants cannot tell a damper responding to real
risk from one responding to a corrupted feature. At the shipped cut the damper does select a
population with 1.90 times the base rate, so it is not firing at random, but how much of that is
earned is not established.

Two documentation discrepancies sit underneath all of this and are worth recording because they are what
made the audit hard to interpret. The consuming code's own comment, the reader document and the branch
readme all describe the model as predicting hypoglycaemia within four hours from two consecutive low
readings, which is the target of the model that was replaced. And the stored score column carries the
outputs of successive models under a single name, with nothing in the record marking the boundary, so
any analysis that does not impose an era filter silently averages two different quantities. The general
requirement is that a learned component in a control loop needs its generation recorded alongside its
output, and a scheduled re-audit against live outcomes rather than a validation at birth.
