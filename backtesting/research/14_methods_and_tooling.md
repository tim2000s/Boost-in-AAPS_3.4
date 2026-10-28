# Simulator fidelity and the analysis harness

A simulator that fails in one direction, an evaluation that conditioned on survival, and a harness
that runs the shipped engine from analysis code.

## Abstract

The absence of a glucodynamic simulator is the binding constraint on this programme, and two lines of
work attempted to relax it. Assessing an existing published simulator against a registry of
signatures measured on real data, graded across six levels rather than pooled, it fails consistently
in one direction: too smooth, no unannounced meals, insulin that always works, no sensor drift and no
exercise. Two of its three signature failures were exposed by the weakest checks in the registry, the
carbohydrate ratio and correction factor in the published configuration having been drawn rather than
measured, at a published-to-generated ratio of 1.10 against 0.63, alongside a zero-insulin opening
step; correcting those was worth three signatures. The gaps described as structural proved to be the
person and the loop rather than the physiology, and adding a behaviour layer and a loop layer moved
the suite from three signatures of eleven to six. An assessment that drops runs in which the virtual
participant died measures performance among survivors, and a physiology-only run kills two or three
in ten. A harness driving the shipped Kotlin components from analysis code reproduces the forecaster
at a fidelity of 0.991. Neither instrument supplies a counterfactual, and the bottleneck remains
identification rather than modelling.

## Introduction

Every policy question in this programme is limited by the same thing: the record contains what the
algorithm did and what glucose then did, and not what glucose would have done otherwise. Two
instruments could in principle relax that.

A validated simulator would supply counterfactual trajectories directly, which would convert the
policy questions into the same clean form as the prediction questions. Whether a published simulator
can stand in for these participants is an empirical question about how closely its output resembles
theirs, and it has to be asked in a way that distinguishes matching a distribution from matching a
structure, because a simulator can do the first while failing the second and the two have different
consequences for what may be concluded from it.

A harness that drives the shipped algorithm from analysis code does not supply a counterfactual, but
it removes a different obstacle: evaluating a proposed change against real inputs without deploying
it to a person.

## Methods

Recorded under `backtesting/scripts/2026-07-insilico/` with the fidelity suite, and
`backtesting/scripts/kotlin-harness/`.

Fidelity signatures are graded across six levels, of which distributional agreement is the weakest and
structural agreement the strongest. Grading rather than pooling is the substantive choice: a single
aggregate score allows a simulator to compensate for a structural failure with several distributional
passes, and the levels prevent that.

Evaluation counts runs in which the virtual participant reached a fatal state rather than excluding
them, because an evaluation that drops those runs reports performance conditional on survival and the
conditioning leaves no trace in the output.

The harness runs the real Kotlin engine components from Python, so that the forecaster, the back-out
state machine and the sleep detector respond to reconstructed histories exactly as they would in the
field. Its fidelity is measured against the shipped components on identical inputs.

## Results

The simulator fails in one direction, consistently: too smooth, no unannounced meals, insulin that
always works, no sensor drift, no exercise. The original assessment scored three failures, two
structural gaps and one pass.

Two of the three failures were exposed by the weakest checks. The carbohydrate ratio and correction
factor in the published configuration were drawn rather than measured, giving a published-to-generated
ratio of 1.10 against 0.63, and there was a zero-insulin opening step. Correcting both was worth three
signatures.

The structural gaps were the person and the loop rather than the physiology. Adding a behaviour layer
and a loop layer moved the suite from three signatures of eleven to six.

A physiology-only run kills two or three virtual participants in ten.

The harness reproduces the shipped forecaster at a fidelity of 0.991. Driving the dose calculation
itself was deferred.

## Discussion

The simulator is not a substitute for the counterfactual and is not used as one. It is useful for
bounding a proposal's behaviour in circumstances the real record does not contain, and for exposing
failures that are structural rather than statistical. The direction of its failure is what governs how
far it can be trusted: a simulator that is uniformly too easy makes any controller look good, and a
controller tuned against it is tuned against the absence of the events that make the problem hard.

The survival-conditioning result is the most transferable finding here. Performance measured among
survivors is not performance, and the distortion is invisible because the excluded runs leave nothing
in the output to notice. Any evaluation whose subject can fail catastrophically needs its failures
counted rather than dropped, and the requirement applies well beyond simulation.

That the weakest checks in the registry found two of the three failures is worth stating against the
intuition that structural checks are the valuable ones. A configuration error that makes the simulated
person more insulin-sensitive than the published parameters claim is a distributional problem and is
caught distributionally. The levels are useful for knowing what a pass means, not for deciding which
checks to run.

The harness has a bounded scope that should not be overstated. A fidelity of 0.991 licenses treating
harness results as engine results for the components it covers, and it says nothing about the dose
calculation, which was not ported. Results obtained through it are engine behaviour under
reconstructed inputs, not outcomes.

Neither instrument moves the binding constraint. They make the answerable questions cheaper to ask and
make it clearer which questions are not answerable, and the identification wall stands where it stood.
