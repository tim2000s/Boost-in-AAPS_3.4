# Short-horizon glucose forecasting and its feature set

What the physiological state adds to a momentum model, and why the best forecaster available is the
worst possible controller substrate.

## Abstract

If an algorithm knew where glucose was going it could dose for that rather than for where glucose is,
and two claims follow: that a forecast improves materially when given more of what the system already
records, and that a better forecast makes a better controller. A gradient-boosted regressor over nine
participants and roughly 220,000 samples, validated with participants held out, reaches a root mean
squared error of 21.7 mg/dL at thirty minutes from trajectory, insulin state and time of day alone.
Adding feature blocks in turn, only curvature helps, at minus 0.164 with an interval from minus 0.179
to minus 0.150, while the physiological insulin decomposition costs plus 0.111 and the sensitivity and
dose regime plus 0.173. Error concentrates in regimes driven by unrecorded inputs, at 31.9 for rising
and 16.9 overnight. Extending the horizon to two hours does not rescue the slow signals, which hurt
more at plus 0.48. Curvature also detects a meal about five minutes before the reactive trigger, with
an interval from 5.0 to 9.8, whereas heart rate appears to lead by fifteen minutes and false-alarms on
83 to 100 per cent of crossings. Against the physiological state estimator on 308,000 identical rows
the database forecaster wins by 2.05 mg/dL with an interval from minus 2.11 to minus 1.99 and the
estimator adds 0.05 on top of it. Asked what dose response it implies on elevated cycles, the
forecaster answers approximately zero against a sensitivity in force of around 36.

## Introduction

The reasoning behind a forecaster is short enough to state in one line: if the algorithm knew where
glucose was going, it could dose for that rather than for where glucose is. Every model-predictive
scheme in the field rests on it, and the programme spent a substantial part of its modelling effort
testing two claims that follow from it. The first is that a forecast can be materially improved by
giving it more of what the system already records. The second is that a better forecast makes a
better controller.

Both were plausible. The algorithm has access to heart rate, step counts, a decomposed
insulin-on-board figure separating basal from bolus and both from activity, a total daily dose at
three timescales, a sensitivity ratio, carbohydrate state and a meal-state flag, none of which a
simple momentum model uses. If any of that carries information about the next half hour, the
forecast should improve when it is added. And if the forecast improves, the dose should follow.

The first claim turned out to be almost entirely false, and the second turned out to be false in a
way that was worth more than the first being true.

The forecaster was a gradient-boosted regressor over the decision database predicting glucose 30
minutes ahead, trained across the full history of nine users and roughly 220,000 samples, and
validated out of sample with the user as the grouping variable so that no subject appeared in both
training and test. A base model was established first from the trajectory, the insulin state and the
time of day, and its residual error was then mapped by regime, because a mean error over a year of
data conceals where a forecaster is actually failing.

Candidate signals were then added to that base in blocks and scored by the change in root mean
squared error, with bootstrap intervals, so that each block was answering the question "does this
add anything the base does not already have" rather than "is this correlated with glucose". Blocks
were chosen to represent distinct hypotheses rather than individual columns: curvature, volatility,
heart rate, steps, the physiological insulin decomposition, the sensitivity and dose regime,
carbohydrate and meal state, and the outputs of the two shipped classifiers.

Three follow-ups then tested the obvious objections. The horizon was extended to two hours, on the
argument that slow-moving signals like the sensitivity regime cannot help at 30 minutes but should
have a home further out. Meal detection was examined separately from forecasting, since a signal
can be useless for predicting a level and still useful for detecting an onset early. And the
forecaster was compared against the physiological state estimator the programme had built in
parallel, on identical rows, to establish which was the better sensor.

The second claim, that a better forecast makes a better controller, was tested by asking what dose
response each model implies rather than by asking how accurate it is.

## Methods

The forecasting and signal-block work is recorded under
`backtesting/scripts/2026-07-harness-hypotheses/`, principally `SIGNAL_DIGGING.md` and
`HYPOTHESES_FINDINGS.md`, with the meal-detection thread in `meal_detection.py` and the head-to-head
against the state estimator in `h4_hybrid_forecaster.py`. The dose-response work is recorded in the
KAIROS-Lab experiment set, E01 to E05.

Everything is out of sample with users held out as folds. Intervals on the signal blocks come from
a bootstrap over samples, which is appropriate there because the question is about the model's error
rather than about people. The head-to-head against the state estimator ran on 308,000 identical
rows, which is large enough that a difference of 0.05 mg/dL is distinguishable and small enough to
be meaningless, and both figures are reported for that reason.

## Results

The base forecaster achieves a root mean squared error of 21.7 mg/dL at 30 minutes. Its importance
ordering is the recent five-minute change first, then the current level, then insulin on board,
then time of day. It is a momentum, level and circadian model, and the recent trajectory does most
of the work.

Its error is not distributed evenly, and the map of where it fails is more informative than the
headline.

| regime | RMSE | share of cycles |
|---|---|---|
| rising, 15-minute change above +15 | 31.9 | 12% |
| high, above 180 | 30.8 | 9% |
| meal state | 25.9 | 6% |
| active, over 200 steps in an hour | 25.4 | 14% |
| falling | 24.5 | 12% |
| low, below 80 | 23.8 | 9% |
| flat | 18.8 | 72% |
| overnight | 16.9 | 25% |

The forecast is hard exactly when something is happening and nearly solved when nothing is. The
regimes carrying the error are those driven by inputs the system does not observe, being carbohydrate
that was never announced and exercise whose intensity is not recorded.

The signal blocks then answered whether anything available closes that gap.

| block added to the base | change in RMSE | interval |
|---|---|---|
| acceleration, the curvature of the trajectory | −0.164 | [−0.179, −0.150] |
| volatility | −0.056 | [−0.068, −0.041] |
| heart rate | −0.010 | [−0.019, −0.001] |
| steps over 30 minutes | −0.008 | |
| carbohydrates and meal state | +0.016 | |
| the two shipped classifiers | +0.010 | |
| insulin decomposition | +0.111 | |
| sensitivity and dose regime | +0.173 | |

One signal helps, and it helps by about a sixth of a milligram per decilitre. Everything expected to
carry physiological information makes the forecast worse. The insulin decomposition, which
separates what the algorithm believes about basal, bolus and activity, hurts. The sensitivity and
total-dose regime, which is the closest thing the system has to a statement about the person's
current state, hurts most of all. These are not marginal: adding them costs more than the single
useful signal gains.

The interpretation is that they are redundant with the trajectory, too slow, or both. A total daily
dose ratio moves over days and cannot inform a 30-minute forecast; the insulin decomposition is
already summarised by the level and the trend, and its extra dimensions are dimensions to overfit.

The extended horizon refuted its own hypothesis. At two hours the base error is 39.5 mg/dL, and the
sensitivity and dose regime hurts more rather than less, at +0.48. The one signal that changes sign
is heart rate, which becomes real and distinguishable at −0.13, roughly four times its effect at 30
minutes and still negligible against a base of 40.

Meal detection separated cleanly from forecasting and produced the programme's one genuinely useful
new input. Heart rate appears to lead the reactive trigger by fifteen minutes on 86 to 100 per cent
of meals, and that lead is an artefact: crossing the same threshold produces a false alarm on 83 to
100 per cent of occasions, because heart rate sits above resting plus twelve for most of the waking
day. It is sensitive and not specific, which is the same trap that has caught several candidate
signals in this programme. Acceleration leads by about five minutes with an interval from 5.0 to
9.8, is derived from the sensor itself so its specificity is manageable, and is real.

Against the physiological state estimator the forecaster wins on accuracy and the margin is stable.
At 30 minutes the errors are 21.5 against 23.6, a difference of −2.05 with an interval from −2.11 to
−1.99, and combining the two improves on the forecaster alone by −0.05, which is distinguishable
only because the sample is 308,000 rows and is practically zero. A separate run at larger scale gave
−2.41. The database model is the better forecaster by about two milligrams per decilitre and the
physiological model contributes nothing on top of it.

That ordering reverses on the tail. The database classifier beats the shipped hypo model at 30
minutes, 0.88 against 0.81, but the state estimator's physiological low-projection ranks lows better
than either at both horizons. General accuracy and hypoglycaemia ranking are different skills, and
the physiological model owns the second one.

The result that mattered most is not about accuracy at all. Asked what dose response it implies on
elevated cycles, the forecaster answers approximately zero milligrams per decilitre per additional
unit, where the sensitivity in force at those glucose levels is around 36. It learned that insulin
does nothing, because in the observational record large doses are given immediately before glucose
climbs. The same confounding appears in the natural experiment between engine generations, which
conditioned on state implies about 6 mg/dL per unit and for one participant flips sign, against a
synthetic dithering estimator on the same data that recovers −45 to −51 with an interval from −64 to
−39.

## Discussion

For short-horizon prediction the available signals are close to exhausted. The trajectory, meaning the value, its rate of change and its curvature,
is essentially all the signal available. No non-sensor precursor gives specific early warning of an
unannounced meal, and the residual error concentrates in regimes driven by inputs that are not
recorded anywhere, which makes it irreducible rather than merely unsolved. The programme stopped
looking for features after this, which freed the effort that went into the identification work
instead.

The one actionable output was acceleration, and it earned its place twice over: it improves the
forecast, marginally, and it detects a meal about five minutes before the reactive trigger. It is now
in the engine.

The finding that shaped everything afterwards is the split between the sensor and the controller.
The database forecaster is the better sensor and an unusable controller substrate, because a policy
built on a model implying insulin does nothing would increase the dose without limit. Prediction accuracy and correct causal dose response are different
properties, and optimising the first does not deliver the second. That is why the programme learns
freely on the offline record for anything that predicts, detects or estimates, and refuses to let any
of it choose a dose.

The corollary bounds what more data could buy. The dose response cannot be read off the observational
record at all, because the exposure is assigned by the very policy whose effect is being measured.
Recovering it needs deliberate exploration, meaning bounded dose variation that is independent of
state, shadow-logged first and priced on time below range. That is the one thing the existing record
cannot supply, and it is the only route from prediction to identified dosing.

Two limitations bound the forecasting results. The signal blocks were tested by addition to a base
rather than by exhaustive subset search, so a block that helps only in combination with another
would not have been found. And the regime map is descriptive: it says where error concentrates, not
that the concentration is irreducible, although the attribution to unannounced carbohydrate and
unrecorded exercise intensity is well supported by the meal-detection work sitting alongside it.
