# Insulin sensitivity estimation and the shape of absorption

Why a sensitivity estimate computed from an algorithm's own residuals feeds its failures back into
dosing, and the insulin context that justifies most of the restraint in the controller.

## Abstract

Every dose is scaled by an estimate of how far a unit of insulin will move glucose, and that quantity
drifts within a person. Two estimators are available: one derived from recent deviations between
predicted and observed glucose, and one anchored to the ratio of recent to longer-run total daily
dose. The dose-anchored estimator, an exponentially weighted ratio of twenty four hour to seven day
consumption with a three hour time constant and a database-seeded warm start, is what ships. A
proposed equivalence between that ratio and a separately maintained sensitivity overlay fails at
clinical tolerance: the two agree within five per cent on 28 to 58 per cent of cycles depending on
the participant, so they are not interchangeable in a dose path. Absorption is multi-phase, with
secondary waves at roughly eighty minutes, handled as a soft ceiling rather than modelled explicitly.
The observation underpinning most of the algorithm's restraint is that at recovering-high glucose
with substantial insulin on board approximately 19 per cent of cycles sit before a low, against
approximately 7 per cent at low insulin on board, a contrast of nearly three.

## Introduction

The sensitivity estimate is the least visible quantity in the controller and among the most
consequential, because it multiplies every delivery. It is not constant within a person, so it has to
be estimated continuously from something.

The conventional choice is the algorithm's own prediction error. If glucose is running above what the
insulin on board predicts, the person is treated as resistant. The alternative anchors to
consumption: a person whose total daily dose has risen relative to their own longer-run baseline is
treated as temporarily less sensitive.

The two differ in what they feed back. A deviation-based estimate is partly a measure of the model's
own failure, and routing it into dosing closes a loop between the model being wrong and the dose
changing. A consumption-anchored estimate is computed from what was actually delivered and is not a
function of the model's accuracy.

A separate question concerns absorption. The dose calculation assumes a single-peak absorption curve,
and whether real meals depart from that in a way that matters for dosing is answerable from the
glucose record.

## Methods

The two estimators were compared directly and the deviation-based function withdrawn in April 2026 in
favour of the dose-anchored ratio, with the exponential weighting, time constant and warm start as
described.

The proposed equivalence between the ratio and the sensitivity overlay was tested by the proportion
of cycles on which the two agree within five per cent, per participant. The tolerance was fixed in
advance from what the dose path requires rather than chosen to suit the result, because an
equivalence claim is only as meaningful as the tolerance attached to it.

Absorption shape was read from the glucose record following meals.

The insulin-context contrast compares the forward hypoglycaemia rate at recovering-high glucose
between high and low insulin on board.

## Results

The dose-anchored estimate replaced the deviation function and ships.

The proposed equivalence does not hold. Agreement within five per cent occurs on 28 to 58 per cent of
cycles depending on the participant.

Absorption is multi-phase, with secondary waves at roughly eighty minutes.

At recovering-high glucose with substantial insulin on board, approximately 19 per cent of cycles sit
before a low, against approximately 7 per cent at low insulin on board.

## Discussion

The change of anchor removed a feedback path rather than improved an estimate. A quantity computed
from the algorithm's own residuals and then used to scale the algorithm's own doses will amplify any
systematic error in the model that produced the residuals, and no amount of smoothing on that
quantity addresses the structure. Consumption is external to the model in a way prediction error is
not.

The equivalence test is a negative that prevented a simplification, and its shape recurs. Two
quantities that track each other loosely are frequently proposed as interchangeable, and whether they
are depends on the tolerance the application requires rather than on the correlation between them.
Agreement on between a quarter and a half of cycles is not sufficient to substitute one for the other
where the output is a dose.

The insulin-context contrast deserves its prominence in this series. It converts a general intuition,
that stacking insulin is dangerous, into a specific measured factor of nearly three between two
identifiable states, and several proposals elsewhere in the programme are rejected by pointing at it.
Any lever that adds insulin into a recovering high is operating in the 19 per cent context, and the
burden on it is set accordingly.

Whether sensitivity could be estimated per person directly from continuous glucose, rather than
anchored to consumption, is settled negatively in the paper on the state estimator. It is not
identifiable observationally, because the latent meal appearance term absorbs any change in insulin
gain, and recovering it requires a deliberate within-participant probe rather than a better
estimator.
