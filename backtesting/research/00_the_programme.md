# The programme

What the Boost investigations were able to answer, what they were not, and the standards the
series holds itself to.

## What this is

Boost is a modified automated insulin delivery algorithm running on a fork of AndroidAPS. This
series records the investigations behind its V6 and V7 generations: the questions that were put,
how each was answered, and what was built or abandoned in consequence. Each subsequent document
takes one topic through abstract, introduction, methods, results and discussion, and names the
analysis folder its figures come from.

The population is a self-selected cohort in the single digits to low tens, running the algorithm on
their own settings and their own pumps. Nothing here is a clinical trial, and no result generalises
beyond the people who took part. Several documents report nulls at the same length as the positive
results, because the purpose of the record is to stop questions being asked twice, and that works
only if the negative answers are as findable as the positive ones.

## The identification constraint

There is no glucodynamic simulator for these participants, so the counterfactual glucose trajectory
for a dosing decision that was not taken cannot be produced. The record contains what the algorithm
decided and what glucose then did. It cannot contain what glucose would have done had the algorithm
decided otherwise.

This divides the questions into two kinds, and the division runs through the whole series.

Prediction and detection questions are clean. Whether a rise is visible an hour ahead, whether a
sensor artefact is distinguishable from a real fall, whether exercise is anticipable from habit:
each is answered out of sample with participants held out as folds, so that cross-participant
generalisation rather than per-person memorisation is what gets measured. The answer is a number
with an interval and it means what it says.

Policy questions are not clean. Whether a smaller committed dose would have avoided a low, whether
a bolus given sooner would have flattened a peak: each requires the counterfactual. What the record can
do is price a policy against observed outcomes, which is an association and is labelled as one, and
then strengthen it with within-participant and matched-baseline designs. The word "would" appears
in these documents only where a randomised or within-subject design supports it.

The binding constraint is identification rather than modelling. Where a question needs a better
model, the model is generally available. Where it needs a counterfactual, no model supplies one.
That is why the series contains more discarded levers than shipped ones, and why several of the
discarded ones were discarded with the modelling working correctly.

## What separates a finding from an impression

Three conditions are imposed on every effect size in this series.

An effect size counts only against a matched baseline. Comparison against no comparison at all
rewards any mechanism that fires often, and several large-looking quantities in this programme are
small once the comparison is constructed: a brake credited with a third of time above range is
correct for a reason other than the one attributed to it, a cohort advantage of thirteen percentage
points is one point once selection and basal differences are accounted for, and a doubled
post-exercise hazard is flat once the window length is fixed. Where a figure has a corrected value,
the corrected value is what appears.

An effect size counts only against a leakage-free split. With a population this small, a model
permitted to see the same participant in training and test is rewarded for recognising people
rather than for learning a relationship. Splits therefore hold participants out, and quantities
computed any other way are not reported.

Every effect size carries an interval, and an interval spanning the baseline is reported as unproven
rather than as suggestive. Intervals come from resampling participants rather than observations
wherever the question concerns people rather than cycles, which is the honest unit when one
participant can contribute half the events.

## What is measured against what ships

The shipping controller is deterministic: a state machine, a stack of bounded multipliers, caps, a
composed brake floor, a rule-based sleep detector, and a per-participant configuration derived
offline. Two pre-trained gradient-boosted models are applied at inference and neither learns online.
Everything Bayesian or inferential in this programme is offline decision support whose output is a
decision about what to build, not a number the loop consumes.

That separation is load-bearing rather than stylistic, and it is the reason several otherwise
interesting results were not shipped. A model learning inside the dose path learns the person and
the policy simultaneously, from data the policy generated, with nothing in the record to separate
them. The evidence for the rule is set out in the papers on per-participant configuration, on what
could not be learned, and on forecasting.

## What the series contains

The topics run roughly in the order the algorithm meets them: seeing glucose, deciding to act,
sizing the action, restraining it, and configuring the whole for one person.

Sensing covers cadence, smoothing and compression artefacts. Action covers dose timing and sizing at
meals, the committed state and the hypoglycaemia that follows it, and post-rescue behaviour.
Restraint covers the brakes, the caps and the composed floor. Context covers exercise and activity,
overnight and sleep, and insulin sensitivity and absorption. Modelling covers forecasting, the state
estimator, the two learned components on the dose path, and the results that could not be obtained.
The series closes on per-participant configuration, cohort outcomes, and the methods and tooling
themselves.

Each document names the analysis folder holding the scripts and the raw report, in the form
`backtesting/scripts/2026-07-residency/`, so that any figure can be traced to the code that produced
it. Those folders sit in a private repository alongside the algorithm source and are not reproduced
here, which means a reader of this repository cannot follow a citation through to the code. That is a
real limitation rather than an oversight; the citations are given so that anyone with access can find
the exact script and re-run it, and so that the provenance of every number is recorded even where it
cannot be followed from here.

The underlying data cannot be published in any case. It is the continuous glucose and insulin record
of a small number of identifiable people who consented to its use for this work and not to its
release. Participants are identified by letter throughout.
