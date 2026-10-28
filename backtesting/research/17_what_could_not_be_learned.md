# Negative results in prediction and detection

The negative results behind a rule against learning on the dose path, and the leakage that made one of
them look positive.

## Abstract

Somewhere in the recorded state there might be information about which dosing decisions go wrong,
which would let an algorithm restrain the dangerous cases specifically rather than restraining
everything a little. Four searches return chance. The shape of an excursion is not predictable from
the state at commitment, at 0.518 with an interval from 0.485 to 0.549 over 2,117 meals. No signal
distinguishes working from non-working insulin beyond trajectory and dose magnitude: across 1,717
stuck-high episodes in nine participants a boosted model moves from 0.466 to 0.518 on the crash while a
logistic model on the same features lands on exactly 0.500, and the algorithm's own model residual, the
most plausible efficacy proxy, scores 0.474. Activity does not transfer between people, a held-out
predictor scoring 0.739 without it and 0.717 with it. Habitual timing splits by event, with exercise
onset reaching a median 0.779 per participant against 0.672 cross-participant and meal onset reversing
at 0.724 against 0.683. Hyperparameter optimisation of the hypoglycaemia model reported a fourteen
point gain under a random split and 0.7 points under a split grouped by participant. Learning the dose
directly from dosing history reproduces the policy's own mistakes, since the target carries no outcome
signal.

## Introduction

This document collects the machine-learning results that returned nothing, because they are the
evidence for the programme's most consequential design rule and because several of them were expensive
enough that nobody should pay for them twice.

The rule is that no training and no online inference happens on the dose path. The shipping
controller is deterministic apart from two pre-trained models applied at inference, and anything that
would learn and dose in the same loop is held behind shadow logging. That reads as conservatism. It
was arrived at empirically, one refutation at a time, and the sequence below is the argument for it.

The unifying hypothesis behind the failures was that somewhere in the recorded state there is
information about which decisions go wrong. If that were true, the algorithm could restrain the
dangerous cases specifically instead of restraining everything a little. Four separate attempts were
made to find it.

The first asked whether the crash that sometimes follows a large committed dose is foreseeable at
the moment of commitment. If it is, the commitment can be gated. This was posed as a prediction
problem over the state available at that instant, across 2,117 meals.

The second asked whether the record contains a signal for whether insulin already delivered is
working. The question had to be posed so it could not answer itself, since "glucose is still high,
so insulin is not working" is just the trajectory. A true efficacy signal must distinguish two
cycles that look identical on glucose, rate of change, curvature and insulin carried, one of which
resolves and one of which stalls. The population was cycles above 150 mg/dL with more than a unit on
board and no announced carbohydrate, anchored on regime entries to give 1,717 approximately
independent episodes across nine users.

The third asked whether physical activity, which is strongly associated with subsequent
hypoglycaemia, improves a general hypoglycaemia predictor. The fourth asked the same of habitual
timing, for meals and for exercise separately.

Two further strands were investigated because they are what an outsider would suggest. One was
whether the model's own hyperparameters could be optimised for a real gain. The other was whether
the approach taken elsewhere in the community, learning the dose directly from a person's own dosing
history, offers anything.

## Methods

The foreseeability work is recorded under `2026-07-postconfirm-accel/meal_shape.py`, the efficacy
probe under `2026-07-efficacy-signal/`, the activity transfer test under
`2026-07-residency/ACTIVITY_HYPO_REPORT.md`, and the per-participant timing comparison under
`2026-07-peruser-anticipation/`.

All of it is out of sample with participants held out as folds. Two methodological choices did most
of the work and are worth naming, because in three of the four cases they are what turned an
apparent result into a null.

The first is the model-class control. In a near-chance regime a flexible model will find structure
that is not there, so every classification result was computed with a gradient-boosted model and a
logistic model on the same features and folds. Agreement between them is evidence; disagreement
means the flexible model is fitting noise.

The second is that cross-user generalisation, rather than in-sample gain or feature importance, is
the test of whether a relationship is a relationship. A feature that lifts in-sample and ranks high
on importance but adds nothing when a participant is held out has told you that the effect exists
within people and does not transfer between them, which is a finding rather than a failure.

## Results

The crash at commitment is not foreseeable. Out of sample the area under the curve is 0.518 with an
interval from 0.485 to 0.549. The shape of the excursion's tail is weakly predictable at 0.60 with
an interval from 0.58 to 0.63, diffuse and partly explained by clustering of second meals, and too
weak to gate on.

There is no efficacy signal in the telemetry, and this is the cleanest of the negatives because it
is robust across model classes and outcome definitions.

| target | boosted, base then plus efficacy | logistic, base then plus efficacy |
|---|---|---|
| crash | 0.466 → 0.518 | 0.453 → 0.500 |
| stall | 0.580 → 0.592 | 0.561 → 0.592 |

The boosted model showed a small increment on the crash and the logistic model landed on exactly
0.500, which is what the control was there to detect. Single-feature areas under the curve say the
same thing from the other direction: everything above chance is monotone in the amount of insulin
present, insulin activity at 0.569 and insulin on board at 0.562, which is the mechanically obvious
statement that more insulin makes an overshoot more likely and is not a statement about efficacy.
The loop's own model residual, the most plausible efficacy proxy in the record, scores 0.474, below
chance.

Activity does not transfer. Its dose-response is strong pooled, and its importance rank is high, and
adding it to a hypoglycaemia predictor with participants held out moves the area under the curve from
0.739 to 0.717, which is within fold noise and points the wrong way. Each person's fitness, baseline
step count and post-exertion fall differ enough that a single cross-participant model cannot carry
the relationship. That is the empirical case for per-participant activity thresholds rather than a
global model.

Habitual timing splits by event type. For exercise onset,
a per-participant model reaches a median 0.779 against 0.672 for the cross-participant model, and
every one of eight participants individually beats the cross-participant figure, so roughly 0.11 of
area under the curve is left on the table by pooling. For meal onset the ordering reverses, 0.724
cross-participant against a median 0.683 per-participant, with well-powered participants at 0.73 to
0.75 and thin-data participants collapsing. People eat at times that resemble each other and exercise
at times that do not.

Hyperparameter optimisation produced the programme's most instructive false positive. Sequential
optimisation of the hypoglycaemia model reported a gain of fourteen percentage points under
cross-validation. The folds were stratified rather than grouped by participant, so the same person
appeared in training and test, and the gain was the model recognising individuals. Under
leave-one-participant-out the honest figure was 0.7 points. The tuned model was not shipped.

Learning the dose directly from dosing history was reviewed against a public implementation that
trains a recurrent network to reproduce a person's own microboluses, corrected by a set of hand
rules. The target contains no outcome signal, so the model reproduces the policy's mistakes along
with its successes, and its fourteen inputs are a strict subset of what the engine already computes.
It is the shape the rule forbids. The review nevertheless changed the programme's direction, because
its feature set, being hour of day, weekday, dose totals at several timescales and activity at
several windows, is an attempt to learn a person's temporal patterns rather than to clone a policy.
Read that way it is the seed of the anticipation work, which is what the programme built next: acting
before an event, per participant, with the action retractable so that a weak predictor is safe.

## Discussion

The four attempts to find out which decisions go wrong all returned chance, and the pattern is
consistent enough to be treated as a property of the data. Nothing in the recorded state
distinguishes a dose that will overshoot from one that will not, beyond the trajectory and the
quantity of insulin already present. This does not mean no such signal exists. It means the current
instrumentation does not carry it, and closing that gap needs a new measurement, of insulin action
or absorption, rather than a better model. The blind spot is a sensing problem.

That reframing is worth more than the individual nulls. Having established that the dangerous cycles
cannot be identified at the moment of decision, the available levers reduce to two, give less or
withdraw afterwards, and both are now in the engine. A programme that had kept searching for the
discriminator would have spent the same effort and shipped neither.

The leakage episode is the reason the grouped fold is not negotiable here. A fourteen-point gain is
large enough to justify a redesign, and it was entirely an artefact of allowing a participant to
appear on both sides of a split. With eight to thirty participants, a model that memorises people
has an enormous amount to memorise relative to the signal, and any validation that does not hold a
participant out will reward it for doing so.

The two results on transfer, activity failing to generalise and exercise timing being
per-participant while meal timing is not, are the same measurement pointed at different questions,
and together they set where personalisation belongs. The programme derives per-participant
configuration deterministically and offline for exactly the quantities that do not transfer, and
uses cohort-wide models for the quantities that do.

Finally, a caution about the search itself. Across these investigations nine threshold variants were
tried on the hypothesis that a confirm arriving as acceleration decays is a late confirm. One cleared
zero by a tenth of a point, weakened as the threshold tightened and reversed sign, and it is recorded
as noise. A discriminator hunted across enough cuts of the same events will eventually produce one
that clears, and the defence is to pre-register the cut or to report every variant tried. The register
now carries all nine.
