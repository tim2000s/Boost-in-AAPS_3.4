# A per-person state estimator as forecaster and as controller substrate

Why insulin gain is not identifiable inside a filter fitted to observational glucose, and what
survives of a model predictive controller once it is not.

## Abstract

The most ambitious proposition in the programme was that a per-person physiological model, fitted
continuously to a participant's glucose and insulin, could serve as the substrate for a
forecast-optimising controller. Two things had to hold: the forecaster had to be accurate and
calibrated, and its response to insulin had to be correct, since a controller works by asking what
happens if it doses differently. The first holds. After calibration the thirty minute band achieves 85
per cent coverage and the sixty minute band 91, and as a detector of falls it beats the incumbent
predictors, firing on one third to one half the false alarms at equal catch, where the
incumbent cannot reach a false alarm rate below about 0.26 and 0.36 whatever threshold is chosen. As a
detector of rises it is worse than what already exists, at false alarm rates of 0.24 against 0.14 for
the incumbent's eventual glucose figure and 0.10 for the naive trend, across 146 rises in seven
participants. The second does not hold. Scaling insulin sensitivity across an eightfold range inside
the filter leaves calibration and error unchanged, because the latent meal appearance term absorbs any
change in insulin gain, and a direct estimate from clean insulin-driven falls swings from minus 1.4 to
39 times the prior depending on specification with a coefficient of determination at or below zero
throughout. The planner is degenerate in consequence, prescribing between 135 and 202 units a day open
loop, or 65 to 70 with an anti-windup correction, against 19 actually delivered.

## Introduction

Model predictive control is standard practice in other fields and the reasoning transfers cleanly on
its face: a model that predicts glucose thirty and sixty minutes ahead can be rolled forward under
candidate dosing plans, and the plan with the best predicted trajectory chosen. It promised to attack
the variance that separates ordinary time in range from tight time in range, which is the quantity
this programme most wants to move.

The proposition has two requirements and they are separable. Accuracy and calibration make the model a
sensor. Correct insulin response makes it a controller substrate. A model can satisfy the first
completely while failing the second, and the failure is not visible in any accuracy measure, because
accuracy is evaluated under the policy that generated the data and a controller by construction
operates away from it.

## Methods

The forecaster was built as an ensemble Kalman filter over a compartmental model, fitted per person,
and calibrated so that its stated uncertainty band matched observed coverage. It was evaluated as a
detector against the predictors the incumbent algorithm already carries, separately for falls and for
rises.

Detection was scored by requiring a predictor to fire between sixty and ten minutes before a real
onset, so that a fire with less than ten minutes of lead does not count. Predictors were compared at
matched sensitivity with false alarm rate as the discriminating axis, because sensitivity saturates
high and comparing on it alone flatters everything. The rise comparison used 146 rises across seven
participants.

The insulin response was investigated two independent ways. The first varied insulin sensitivity across
an eightfold range inside the filter and asked whether accuracy or calibration changed. The second
attempted a direct, model-light estimate from episodes of clean insulin-driven falls, where meal
absorption should be least confounding.

The planner was then run offline against the calibrated forecast to see what it would prescribe.

Recorded under `backtesting/scripts/2026-07-kairos-twin/`, principally `TWIN_HYPO_LEAD.md`,
`TWIN_RISE_LEAD.md`, `TWIN_OFFPOLICY.md` and `KAIROS_DECISION.md`, with the identification work in
`twin_identify.py` and the planner in `twin_ting.py`.

## Results

As a forecaster the estimator is good. After calibration the thirty minute band achieves 85 per cent
coverage and the sixty minute band 91.

As a detector of falls it beats the incumbent's own predictors. At equal catch of real lows
it fires on one third to one half the false alarms, and the incumbent cannot reach a false alarm rate
below about 0.26 for one of its predictors and 0.36 for the other whatever threshold is chosen.

As a detector of rises it is worse than what already exists. Its thirty minute forecast is beaten both
by the incumbent's eventual glucose figure and by the naive trend, at false alarm rates of 0.24 against
0.14 and 0.10 respectively, and with less lead.

The insulin response is not identifiable. Scaling sensitivity across an eightfold range inside the
filter leaves calibration and error unchanged. The direct estimate from clean falls swings from minus
1.4 to 39 times the prior depending on specification, with the coefficient of determination at or below
zero throughout. The direction is robust, in that the previous prior was an order of magnitude too low,
but the magnitude cannot be recovered from observation.

The planner is degenerate. Fed the calibrated forecast and its floor, it respects the floor perfectly
and is smoother than what was delivered, and it prescribes between 135 and 202 units a day open loop,
or 65 to 70 with an anti-windup correction, against 19 actually delivered. It chases a target below
where glucose physically sits, and open loop its forecast never falls in response to its own doses.

Two general results sit alongside. The incumbent's eventual glucose figure is not a forecast, with a
coefficient of determination of minus 2.32 against actual outcomes, and should be read as an artefact
of the control calculation. Its insulin projection at thirty minutes is trustworthy, with a mean
absolute error of 21 mg/dL, negligible overnight bias and 98.9 per cent of points in the clinically
acceptable zones.

## Discussion

The controller line was stopped, and the reason is worth stating precisely because it is not a failure
of the model. Any policy that adds net insulin to chase a lower glucose has to be validated against a
trajectory that did not occur. This is the best forecaster available here and it is untrustworthy far
from the policy that generated its training data, which is precisely where a controller improving on
the incumbent must operate. Characterising the planner's prescription correctly would require rolling
the model forward under doses three and a half times off policy, which is the thing the identification
result says it cannot do. This is a wall rather than a tuning problem, and no amount of additional
modelling moves it.

Anchoring sensitivity to the participant's clinical figure, which is external knowledge rather than
something inferred, makes the forward response physiological at about minus 4 mg/dL per unit at sixty
minutes. It does not fix the underlying problem, because calibration still decays away from the modal
policy and the uncertainty band does not widen to signal that it has, which is the property that would
have made the degradation detectable at runtime.

What survives is the estimator as a sensor, and the asymmetry between falls and rises is
interpretable rather than incidental. A rise is directly visible in the trend and there is no hidden
state to infer, whereas a fall depends on insulin already given and absorption already under way,
which is exactly what a state estimator is for.

Two uses need no off-policy counterfactual, because neither adds net insulin and both merely re-time
insulin the incumbent would give anyway. Withdrawing earlier on a predicted fall removes insulin, and
removing insulin cannot cause the harm the validation would need to bound, so it is checkable against
observed outcomes. The same logic applies at the other end of an excursion.

The related question of whether insulin sensitivity itself could be learned from continuous glucose is
answered the same way and for the same reason. It is not identifiable observationally, and recovering
it would need a within-participant micro-bolus probe rather than a better model. That is a study
someone could run, and it is not something the passive record can supply.
