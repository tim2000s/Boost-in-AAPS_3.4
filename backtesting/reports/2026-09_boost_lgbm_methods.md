# Gradient-boosted trees on the Boost dose path: construction, parameter selection and deployment

A methods account of the two LightGBM models that ship inside the Boost AndroidAPS fork, covering
how they were built, how their parameters were chosen, how they are validated, how a Kotlin plugin
evaluates them on a phone, and what is known about their behaviour in the field.

Sources are the shipped model assets and their metadata, the plugin source on `dev`, the commit
record, the surviving training scripts, and the field audit under
`backtesting/scripts/2026-08-ml-field-audit/`. Measurements made fresh while writing this are marked
as such. Claims carry a confidence tier: SOLID for out-of-sample results with an interval that
survived a challenge, PROVISIONAL for a single test or an unknown interval, SPECULATIVE for reasoning
alone.

## Summary

Boost's shipping controller is deterministic apart from two gradient-boosted tree models applied at
inference. One estimates the probability of sustained hypoglycaemia within 90 minutes and can only
reduce the delivered dose. The other estimates the probability of an unannounced meal rise and can
only increase it. Both were trained offline on roughly three million decision cycles from a foreign
Nightscout cohort, exported as JSON trees, and are evaluated on the phone by about fifty lines of
Kotlin.

The hyperparameters were not selected by a search. The meal model's values appear as literals in its
training script, the hypoglycaemia model's survive only as a five-key block in a metadata file, and
the one optimisation study the programme ran targeted neither of them. That study reported a fourteen
point gain that turned out to be participant leakage, and its result was rejected. What discipline
the programme has went into the validation scheme rather than into the model, which is a reasonable
allocation given the failure that produced the rule, but a reader should not imagine a tuning study
underneath these numbers.

The provenance is worse than the validation. The training code sits in a directory that is not under
version control, and the script that produced the currently deployed hypoglycaemia model no longer
exists anywhere on the machine. The model that doses today cannot be regenerated.

## What the two models predict

Read from the metadata assets rather than from the code comments, which are stale in several places.

| | hypo risk (v12) | meal likelihood |
|---|---|---|
| asset | `app/src/main/assets/boost/hypo_risk_model.json` | `app/src/main/assets/boost/meal_likelihood_model.json` |
| size | 368 KB | 151 KB |
| trees | 100 | 50 |
| leaves per tree | 31 | 15 |
| features | 53 | 8 |
| label | CGM below 70 mg/dL sustained for at least 15 min | peak at least 50 mg/dL above current |
| horizon | 90 min | 90 min |
| training rows | 3,007,589 | 2,978,062 |
| training participants | 32 | 28 |
| positive rate in training | not recorded | 0.179 |
| GroupKFold AUC | 0.8391 | 0.7342 |
| leave-one-participant-out AUC | 0.8317 | 0.7375 |
| training date | 2026-06-06 | 2026-05-02 |

The 28-participant cohort that appears throughout the documentation belongs to the meal model and to
the retired eight-feature hypoglycaemia model. The model that ships today was trained on 32.

Three documentation sources describe the hypoglycaemia model as predicting an event within four
hours, defined as two consecutive readings below 70. That was the target of the model retired on
2026-06-06. The consuming code's KDoc in `BoostRiskModel.kt`, `docs/boost-v3ml-reader.md` and
`docs/boost-v1-settings.md` all still carry it. Anyone reasoning about the consumption thresholds
from the documentation is reasoning about a different quantity from the one the engine computes.
Confidence SOLID: the metadata asset, the commit that shipped the model and the field audit agree.

## Why gradient boosting, and why these features

The proposition that produced the first model was narrow. The algorithm had inherited a binary safety
gate that suspended delivery when a projected minimum glucose fell below a threshold. A gate of that
shape is a single-feature classifier with a hand-placed cut, and on the programme's data it separated
dangerous cycles from safe ones at an area under the curve of 0.62, suspending unnecessarily on 66
per cent of the occasions it fired and missing a third of the events it existed to catch. A small
learned model over features the algorithm had already computed reached 0.80 on the same data. The
claim being tested was that this particular gate was a weak classifier, not that machine learning
improves dosing in general.

Model class was settled by a factorial comparison over 1,491,790 decision points from 21
participants: two targets, two architectures being gradient-boosted trees and logistic regression,
and two subgroups split on whether dynamic sensitivity was active. All eight models used the same 28
features, the same folds and the same cost-sensitive weighting, so architecture was the only quantity
varying. Boosting led logistic regression by 10 to 21 points in every stratum, the largest gap being
0.910 against 0.701 on hypoglycaemia under static sensitivity. Confidence PROVISIONAL: the result is
recorded in `backtesting/research/15_learned_components_in_the_dose_path.md`, and the script that
produced it could not be located, so it was not re-run.

The feature set was chosen for a deployment reason rather than a statistical one. The eight base
features are already arguments of the dosing function, so computing them costs nothing and adds no
coupling between the model and the rest of the engine's state. They are current glucose, total
insulin on board, the basal component of insulin on board, glucose above target, a numeric trend
bucket, hour of day, insulin activity, and the algorithm's own insulin requirement for the cycle.

Version 10 added nine more, all of them already present in the suggestion record: carbohydrates on
board, eventual glucose, expected delta, minimum delta, total daily dose, bolus insulin on board, net
basal insulin, microbolus units in the last 60 minutes, and minutes since the last microbolus.
Version 12 added a six-cycle lookback over six of those seventeen, giving 36 lag features and 53 in
total.

## Feature usage in the shipped models

Counting splits in the exported trees, which is what LightGBM's default importance reports:

| model | total splits | most used features |
|---|---|---|
| hypo risk | 3,000 | cgm_mgdl 437, sug_TDD 245, iob_bolusiob 225, hour 207, iob_basaliob 202 |
| meal likelihood | 700 | cgm_mgdl 160, bg_above_target 129, hour 103, iob_iob 96, direction_num 77 |

Six of the 53 hypoglycaemia features are never split on: the six lag0 entries. That follows from the
schema, since lag0 duplicates the current-cycle value that already appears as a static feature, so
the training data contained pairs of identical columns and the learner used one of each. The count
was made fresh for this paper by walking the shipped JSON; confidence SOLID and trivially
reproducible.

This has one operational consequence. `BoostRiskModel.predictAtProjectedIob` adjusts `iob_iob_lag0`
and `recent_smb_units_60m_lag0` alongside their static twins, on the stated grounds that the vector
would otherwise be internally inconsistent. That reasoning is right in principle and inert in
practice: the shipped model never reads those entries, so those two assignments cannot move the
score.

## Where the training code lives

The training scripts are in `/Users/timstreet/oref-investigations/`, which is not a git repository and
has no history. The shipped assets are byte-identical to files in that directory, verified by MD5, so
the mapping from artefact to producing directory is certain even though the production runs are not.

`investigations/train_meal_model.py` produced the meal model and survives. `investigations/train_risk_model.py`
produced the original eight-feature hypoglycaemia model and survives. The script that produced the
53-feature model that ships today does not, and could not be found by searching for its feature names,
its label name, its output path or its metadata keys anywhere under the user's home directory. What
survives from that build is a ladder of metadata files dated 2026-06-06, running v9, v9-90m, v10-90m,
v10.2, v10.3, v10.4, v10.5, v11.1, v11-90m, v12 and v12b, with no scripts behind any of them. The
composition string in the shipped metadata, "v10 extended features + v10.1 sustained labels + v10.3
6-cycle flat-window lookback", refers to stages whose definitions are not written down.

The commit that shipped the current model, `baeb022409` on 2026-06-06, has an empty body. The model it
replaced six hours earlier, `8415452161`, carries the fullest commit message in the model history,
with per-participant validation figures and a stated rationale. Confidence SOLID on all of this,
established by search and by checksum.

## Hyperparameters, and how they were chosen

For the meal model and the retired eight-feature hypoglycaemia model the parameters are literals in
the surviving scripts, and the two configurations are identical apart from the label:

| parameter | value |
|---|---|
| objective / metric | binary / binary_logloss |
| num_leaves | 15 |
| max_depth | 4 |
| learning_rate | 0.05 |
| n_estimators | 50 |
| min_child_samples | 100 |
| subsample / colsample_bytree | 0.8 / 0.8 |
| scale_pos_weight | n_neg / n_pos |
| random_state | 42 |

For the 53-feature hypoglycaemia model, five values survive in the metadata asset and nothing else:
100 estimators, max depth 5, 31 leaves, learning rate 0.05, minimum 200 samples per leaf. Sampling
fractions, class weighting, the random seed and the LightGBM version are unrecorded. Somebody
therefore roughly doubled the capacity between v9 and v12, from 50 trees of 15 leaves to 100 of 31,
and no rationale for that was written down.

None of these values came from a search. The programme ran one hyperparameter study, a 66-trial
Optuna optimisation on 2026-04-08, and it targeted a different configuration from either shipped
model: 500 trees, 63 leaves, depth 8, 30 samples per leaf. It reported a gain of 13.98 percentage
points under five-fold stratified cross-validation. The folds were stratified rather than grouped by
participant, so the same person appeared on both sides of a split and the gain was largely the model
recognising individuals. Under leave-one-participant-out the honest gain was 0.68 points. The tuned
parameters were not adopted, and the episode is why grouping folds by participant is treated as
non-negotiable everywhere else in the programme. Confidence SOLID as a statement about the record.

Three structural facts follow from the artefacts and constrain how the shipped values should be read.
Every one of the 100 hypoglycaemia trees has exactly 31 leaves and every one of the 50 meal trees has
exactly 15, so the leaf cap bound at every iteration and it, rather than the sample floor, is what
limits capacity. The tree count matches `n_estimators` exactly in both models, and neither surviving
script passes an evaluation set or an early-stopping callback, so boosting ran a fixed number of
rounds with nothing watching. And 200 samples per leaf against 3,007,589 rows is a floor of roughly
one part in fifteen thousand, a mild constraint at that sample size.

Class weighting deserves its own paragraph, because it interacts with how the output is consumed.
Both surviving scripts set `scale_pos_weight` to the negative-to-positive ratio, which equalises the
classes and inflates the predicted probabilities away from the true base rate. Nothing downstream
corrects for it: there is no isotonic or Platt stage in either script, and the Kotlin walker applies a
plain logistic transform to the summed leaf values. A weighted, uncalibrated model consumed through a
probability threshold is a known way to get a threshold that does not mean what it appears to mean.

That said, weighting does not explain the miscalibration actually observed in the field, and the test
was run for this paper. The single odds-scale correction that maps the top decile's predicted 0.392
onto its observed 0.072 is a factor of 8.31. Applying that same correction to the nine deciles beneath
it drives every one of them roughly an order of magnitude below its observed rate: the lowest decile
would go from a predicted 0.013 to 0.0016 against an observed 0.017. A global weighting artefact would
have to distort the whole range, and the lower nine deciles track their observed rates closely.
Confidence SOLID on the negative, being arithmetic on the published decile table.

## Validation

Splits hold participants out throughout, by GroupKFold with the participant as the group and by
leave-one-participant-out. Both figures are reported in the metadata for both models and they agree to
within a point, which is the expected pattern when no single participant dominates. The meal model
carried a pre-registered acceptance gate of 0.65 on the leave-one-participant-out mean, written into
its training script, with instructions to abort the feature if the model fell below it. It returned
0.7375 and the metadata records the status as accepted.

The out-of-cohort transfer test on 2026-05-12 took six participants outside the training cohort over
72 days and roughly 110,000 cycles. The meal model returned 0.771 against a leave-one-participant-out
baseline of 0.738. The eight-feature hypoglycaemia model returned 0.679 against a baseline of 0.680,
which is transfer without improvement. A before-and-after comparison on an in-cohort participant gave
0.642 against 0.633, indicating no drift from closing the loop around the model.

Per participant the transfer was not uniform, and `RELATIONSHIPS_REGISTER.md` records the split: one
new participant scored 0.708, close to the GroupKFold figure, and another scored 0.628, below the
leave-one-participant-out baseline. The register's conclusion was per-user calibration for outliers
and no retrain. Confidence PROVISIONAL: two participants at the tails of a six-participant test, with
no interval reported.

The hypoglycaemia model's revision was checked before shipping. The v9 commit records a 21-day
real-world backtest on three participants giving AUC changes of +0.003, +0.022 and +0.018, and
reductions in damper activation at risk at or above 0.3 of 59, 87 and 75 per cent. The four
participants added to the training cohort for v9 improved from a mean leave-one-participant-out of
0.674 to 0.817 when the horizon moved from four hours to 90 minutes. That is the single largest change
in the model's history, and it came from redefining the label rather than from anything about the
learner.

Version 12 was scored against the same four held-out participants and beat v9 on three, 0.7847 against
0.7586, 0.8654 against 0.8218 and 0.8875 against 0.8538, while losing on the fourth, 0.8306 against
0.8759.

No probability calibration step was applied at any stage of either pipeline.

## How the model reaches the phone

The trees are exported as JSON by a function present in both surviving scripts, which calls LightGBM's
own `dump_model` and rewrites each `tree_structure` into nested nodes carrying either a leaf value or a
feature index, a threshold and two children. `BoostRiskModel.kt` parses that into a recursive
`TreeNode`, walks every tree, sums the leaf values and applies a logistic transform. Nothing about
LightGBM is present at runtime.

The format was chosen against two alternatives, the LightGBM C library through the Java native
interface and a portable inference runtime. The JSON walk needs about fifty lines, has no native
dependency, and costs roughly five milliseconds against a five-minute cycle. That is the whole
argument, and at this model size it is a sound one.

Loading is lazy and latched. The first inference triggers `ensureLoaded`, which reads the asset once
and sets `loadAttempted` whether or not the load succeeded, so a failure is never retried for the life
of the process. Inference guards on the feature vector's length matching the model's declared
`feature_names`, returning null on a mismatch, which is what makes the dual-path routing in
`DetermineBasalBoost` safe: an eight-entry schema takes the legacy call and anything else takes the
53-feature builder.

`BoostMlFeatureBuilder` assembles the vector. Static features come from a map keyed by name and default
to zero when absent. Lag features are resolved by parsing the `_lagN` suffix and indexing backwards
into a ring buffer of the last six cycle snapshots. The buffer is serialised to a preference string,
`StringKey.ApsBoostMlRingBuffer`, and restored on process start, so the lookback survives a restart.

One guard exists because the loop can now run faster than the model was trained for. The lags are
five-minute steps in the training data, and the lag count is part of the model, so on a one-minute
sensor feed an unguarded push would make a six-entry buffer span six minutes instead of thirty. `push`
admits a snapshot only once per five-minute interval and replaces the newest entry when called again
too soon, so the buffer keeps five-minute spacing whatever the loop cycles at. This is the one
count-based window in the one-minute work that was resampled at the input rather than retimed.

## From score to dose

The hypoglycaemia score reaches the delivered quantity through four paths, and every one of them can
only remove insulin.

In the V1 engine the score becomes a graduated damper. Below 0.30 the scale is exactly 1.0. Above it
the scale falls linearly, `max(0, 1 - (risk - 0.3) / 0.7)`, reaching 0.5 at risk 0.65 and zero at risk
1.0. It is applied to the microbolus after tier selection, inside an `if (riskScale < 1.0)` guard that
makes it structurally impossible for the block to raise a dose. A second, binary gate blocks the four
aggressive tiers when the score exceeds 0.60.

In V5 and V6 the same score enters the aggression budget, which is
`max(0.30 x baseInsulinReq, baseInsulinReq x mlHypoRiskScale x postExerciseRecoveryModifier)`. The
damper has the same 0.30 threshold and a floor of 0.50 at the default setting. A user-facing Hypo
Caution knob between 1.0 and 2.0 deepens the cut and lowers the floor to 0.25 at its maximum; it
cannot disable the damper, because the knob is coerced to at least 1.0. The composed budget floor holds
the whole stack at 30 per cent of the baseline requirement.

A third path re-scores the model at the projected post-microbolus state and damps if projected risk
exceeds both the current score by 0.15 and an absolute threshold of 0.40. It is expected never to fire.
Probing the shipped trees directly for this paper, with all other features held fixed at glucose 120
mg/dL, the score runs 0.0289 at zero insulin on board, 0.0175 at 1 U and 0.0222 at 5 U: flat and mildly
inverted rather than increasing. Insulin on board is confounded with meals in the training data, so the
model learned that carrying insulin co-occurs with fewer subsequent lows. The gate is wired anyway
because a lower projection passes through unchanged, and it becomes live if a model with a causally
correct response is ever trained. Confidence SOLID on the flatness, being a direct probe of the shipped
artefact that reproduces the 2026-07-02 offline backtest.

Reading the same probe across glucose confirms the model is otherwise sanely shaped: 0.838 at 45 mg/dL,
0.711 at 65, 0.266 at 75, 0.074 at 90, 0.028 at 110 and 0.020 at 250, monotone through the region that
matters.

The meal model is not a restraint, and the framing that Boost's learned components can only remove
insulin holds for the hypoglycaemia model alone. A meal score above 0.50 releases the V1 pre-meal
uncertainty hold, unlocking four tiers that were being suppressed. In V5 and V6 it carries a weight of
0.20 in the meal signal score that drives the state machine, and the state selects a dose multiplier
running from 0.3 while observing to 1.8 once confirmed. A score at or above 0.30 also blocks the
sleeping classification in the sleep detector, which disables overnight microbolus restraint. Each of
those is a dose increase. The safety argument for them rests on the deterministic caps and the state
machine downstream, not on the model's direction.

When either model is unavailable the engine fails open. A null hypoglycaemia score gives a damper of
1.0, no tier downgrade, and a pass-through at the post-action gate. A null meal score is handled by
renormalising the meal signal weights after three consecutive nulls, redistributing the missing 0.20
across the remaining six terms. There is no preference key gating either model. Selecting a Boost
plugin means running them.

## A deployment defect and how it presented

The ring-buffer fault is worth setting out in full, because its shape generalises to any feature
pipeline carrying history across a process boundary.

The symptom was a calibration failure confined to one decile. Scored over ten participants on the
current model's era, the top decile predicted 0.392 and observed 0.072 against a base rate of 0.036,
while the nine deciles beneath it tracked their predictions closely. That is the only part of the range
the consumption thresholds touch. Discrimination was unaffected and respectable, 0.655 pooled with an
interval from 0.606 to 0.701, and the damper applied within that decile averaged 0.934, a seven per
cent reduction that cannot take a genuine 39 per cent event rate down to 7. The on-policy confound was
ruled out arithmetically before anything else was considered.

Probing the trees directly located the anomalous region rather than explaining it. Cycles scoring above
0.60 sat at a mean glucose of 66.4 mg/dL, which is where the probe says those scores belong. The band
that did not fit was 0.30 to 0.45, at a mean glucose of 122.9 with 1.27 U on board, where the probe says
the model should return about 0.10. A model that ranks correctly and scores too high in a region it
should not be scoring at all is being fed something other than what it was trained on.

The mechanism was found by replay rather than by inspection, and the distinction matters because
inspection had already been done and had produced a plausible wrong answer. `feature_replay.py` rebuilds
the 53-feature vector offline from the decision record and scores it with the same exported model. On
contiguous cycles the reconstruction reproduces the engine's own published score to a median absolute
error between 0.0028 and 0.0060 per participant, which licenses treating the replay as the engine. Three
candidate histories were then scored on cycles following a break in the decision series: the snapshots
carried across the break, a cleared buffer falling back to the current cycle, and the true contiguous
history. The carried snapshots won for all nine participants tested, by the widest margin for the two
whose damper fires most.

`RingBuffer.push` appended and trimmed to six entries. It never read the timestamp it stored on each
snapshot, and the buffer was persisted to preferences and reloaded on start. After any break in the
decision series it therefore still held the six snapshots from before the break and handed them to the
model as the preceding five cycles. A cycle arriving two hours after the last one was scored against a
trajectory two hours old.

The cost at the operating point was measured rather than asserted. A third of scored cycles follow such
a break. Restricted to glucose between 100 and 160 mg/dL, where the probe places the model well below
the cut, those cycles crossed the 0.30 threshold on 8.61 per cent of cycles against 3.92 per cent for
the rest, a difference of 4.69 points with an interval from 4.11 to 5.27. Discrimination was identical
either side, 0.654 against 0.651, which is the signature of a calibration defect rather than a broken
model: an error in a feature carrying history moves the level of a score without disturbing its ranking.

The fix, in commit `750be759a2` on 2026-08-14, drops entries older than 35 minutes on push, being the
six-cycle window plus one cycle of slack so an ordinary late reading does not discard usable history.
Entries outside that window resolve to null in `lagged`, which the caller already rendered as a fall
back to the current cycle. Six regression tests in `BoostMlRingBufferStalenessTest.kt` pin the
behaviour, including the restart case and the 35-minute boundary.

Two things about this episode are worth carrying forward. The defect was invisible to every test that
existed, because the buffer was correct in isolation and wrong only in the presence of a gap it had no
way to see. And the diagnostic that worked was reconstructing the engine's input offline and scoring
it, which is a capability worth having before it is needed rather than after.

A second, cruder defect from the same model's deployment belongs beside it. When the 53-feature model
first shipped on 2026-06-06 it failed to load on the developer's device and returned null on every
cycle, silently, because the load path logged at error level and the app's log export captures only
debug and info. The engine fails open, so nothing looked wrong. The recovery was to roll the asset back
to the previous model, mirror every diagnostic to info level with a DIAG prefix, and re-ship two days
later. A component that fails open needs its failures visible in whatever log a user can actually send.

## Field behaviour

The models were scored against the telemetry of the people running them on 2026-08-13, over ten
participants, with intervals from a cluster bootstrap resampling participants.

| | pooled AUC | 95% CI | training LOUO |
|---|---|---|---|
| hypo risk, current model | 0.655 | 0.606 to 0.701 | 0.8317 |
| hypo risk, previous model | 0.606 | 0.493 to 0.729 | 0.6796 |
| meal likelihood | 0.722 | 0.684 to 0.757 | 0.7375 |

Against trivial predictors on identical rows, the current hypoglycaemia model beats the negated glucose
reading by 0.068 with an interval from 0.046 to 0.104, and the meal model beats the algorithm's own
eventual glucose by 0.144 with an interval from 0.054 to 0.233. The eight-feature predecessor did not
beat glucose, at +0.018 with an interval from minus 0.037 to plus 0.113, so the revision achieved what
it was for. Confidence SOLID for both verdicts, each robust to the horizon and to the choice of
baseline.

The meal model replicates its training figure in the field, which after three separate out-of-cohort
tests makes it the cleanest positive result the programme has. The hypoglycaemia model's field figure of
0.655 against a training 0.8317 is a larger gap than the on-policy measurement bias, the cohort
difference and the limits of a within-population cross-validation estimate comfortably explain, and the
residual is an open question.

## Limitations

The consumption thresholds at 0.30 and 0.60 were placed against the output distribution of the model
retired in June 2026, in which the cohort median score was 0.364. They were not moved when the median
fell to 0.038. The damper now engages on between 0.49 and 27.7 per cent of scored cycles depending on
the participant, a fifty-fold spread that nobody selected. That spread correlates with each
participant's own hypoglycaemia rate at +0.820, which would make it correct behaviour, and it also
correlates at +0.907 with how much that participant's scores were distorted by stale history. The same
two participants dominate both correlations, and nine participants cannot separate them.

The field audit predates the ring-buffer fix and no re-audit has been run since. The commit that fixed
the buffer says the thresholds should be re-placed afterwards, because fixing the imputation moves the
distribution again, and that has not happened. Everything in the field-behaviour section above therefore
describes an engine with a defect that has since been corrected, and the corrected engine has not been
measured.

There is no test of any kind on `BoostRiskModel`, `BoostMealModel`, model loading, JSON parsing or the
size-mismatch path. The only ML tests in the tree cover the ring buffer's staleness behaviour and the
direction of the V5 damper.

The stored telemetry column carries the outputs of three model generations under one name with nothing
marking the boundary. Any analysis that does not impose an era filter averages quantities on different
scales with different targets. A learned component in a control loop needs its generation recorded
alongside its output, and that has not been done.

The document cited as the source of the 0.30 threshold and the meal signal weights,
`boost_v5_constants_calibration.md`, is referenced from three source files, is not in the repository,
and never has been.

The reproducibility gap is the largest limitation and is not statistical. Training data came from a
direct database connection with no snapshot retained, the training directory is outside version control,
and the script for the deployed hypoglycaemia model is gone. The exported JSON is committed, so what
doses is fixed and auditable, and the model can be probed, replayed and measured. It cannot be rebuilt,
retrained on the same basis, or corrected in the one way the evidence points to, which is retraining with
a causally correct response to insulin on board.

## Confidence tiers

| claim | tier |
|---|---|
| Model architecture, size, features, labels and horizons as tabulated | SOLID |
| Meal model hyperparameters, including class weighting and no early stopping | SOLID |
| The deployed hypoglycaemia model's hyperparameters were not searched, and its training script is lost | SOLID |
| Class weighting does not explain the top-decile miscalibration | SOLID |
| Six lag0 features carry no splits in the shipped model | SOLID |
| The hypoglycaemia score can only reduce the dose, on all four paths | SOLID |
| The meal score can increase the dose, on three paths | SOLID |
| Model responds monotonically to glucose and flat-to-inverted to insulin on board | SOLID |
| Current hypo model adds 0.068 over the glucose reading in the field | SOLID |
| Meal model replicates its training figure out of cohort | SOLID |
| Stale ring-buffer history caused the top-decile miscalibration | SOLID |
| Gradient boosting beats logistic regression by 10 to 21 points on this problem | PROVISIONAL |
| Per-participant transfer of the eight-feature models is bimodal | PROVISIONAL |
| The deployed hypoglycaemia model used the same class weighting as its predecessors | SPECULATIVE |
| The residual gap from 0.83 to 0.66 is cohort difference rather than pipeline mismatch | SPECULATIVE |
