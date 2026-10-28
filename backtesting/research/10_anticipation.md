# Anticipation of meals and exercise, and retractable action

Where anticipation transfers between people and where it does not, and why a detector that is wrong a
third of the time is usable when the dose can be withdrawn.

## Abstract

Reactive dosing is close to exhausted in this cohort, since glucose trajectory and dose magnitude
carry essentially all the available short-horizon signal, so further improvement requires acting
before an event rather than after it. Anticipation transfers in opposite directions for the two
events that matter. Per-participant temporal prediction of exercise onset at forty five minutes
reaches an area under the curve of 0.78, with all eight participants between 0.72 and 0.83, against
0.67 for the cross-participant model. Meal onset reverses this, at 0.72 cross-participant against
0.68 per participant, with the per-participant form collapsing where data is thin. Habitual structure
is strong enough to arm on: time of day and day of week predict activity at 0.73 to 0.85, roughly 30
per cent of activity falls in a participant's top three hours, and a habit prior pre-arms 55 per cent
of episodes about 55 minutes ahead at 0.85 with precision 0.63. A precision of 0.63 is unusable when
the committed insulin cannot be recovered and usable when arming commits a small retractable quantity
that unwinds on failure to confirm, which moves the safety argument from accuracy to design.
Confirmation after arming reaches 0.83 to 0.87 on the crux participant with a false back-out rate of
about 11 per cent.

## Introduction

Every lever examined elsewhere in this series is reactive: the algorithm observes glucose move and
responds. The forecasting work establishes that the reactive problem has little headroom left,
because the trajectory and the quantity of insulin already present account for nearly all the signal
recoverable at short horizon.

What remains is to act before the event, which requires predicting the event rather than the glucose.
That is a different problem with a different data requirement, and a negative result on the reactive
cross-participant question does not bound it.

Two obstacles stand in the way. The first is whether events are regular enough to anticipate, which
may differ between meals and exercise and between people. The second is that any early predictor will
be imprecise, and committing insulin on an imprecise signal is exactly the behaviour the rest of the
programme exists to prevent.

## Methods

Recorded under `backtesting/scripts/2026-07-peruser-anticipation/` and
`backtesting/scripts/2026-07-anticipation-backout/`.

Prediction was scored temporally for the per-participant models, so each is fitted on a participant's
earlier data and tested on their later data, and with participants held out for the cross-participant
models. The two scoring schemes answer different questions and are not comparable except in the
direction reported here, where the same event is scored both ways on the same participants.

The safety question was addressed by designing a state machine that arms on the weak signal, requires
confirmation within a bounded window from a signal independent of the one that armed it, and unwinds
if confirmation does not arrive. That design was shadow-logged rather than allowed to dose.

## Results

Exercise is anticipable and idiosyncratic. Per-participant prediction of onset at forty five minutes
reaches 0.78, with all eight participants between 0.72 and 0.83, against 0.67 cross-participant.

Meals reverse the ordering. Cross-participant prediction of meal onset reaches 0.72 against 0.68 per
participant, the latter winning only for participants with substantial data and collapsing where data
is thin.

Habitual structure is strong. Time of day and day of week predict activity at 0.73 to 0.85, about 30
per cent of activity falls in a participant's top three hours, and a habit prior pre-arms 55 per cent
of episodes about 55 minutes ahead at 0.85 with precision 0.63.

The retractable design validates on the crux participant. Confirmation after arming reaches 0.83 to
0.87, with a false back-out rate of about 11 per cent.

Meal-time anticipation in the aggregate, as distinct from the per-participant and hybrid forms, is
close to chance, with onsets roughly uniform.

## Discussion

The transferability result determines the architecture rather than merely describing the data.
Exercise anticipation belongs per participant because exercise timing is personal; meal anticipation
belongs in a hybrid form, with a cross-participant prior adapted per person, because meal times are
semi-universal and per-participant data is thin. Neither choice is a modelling preference and both
follow from where the transfer sits.

The consequence for safety is the more general one. Accuracy and safety are usually treated as the
same axis, so that a detector must be accurate enough to be safe to act on. Retractability separates
them. If arming commits a small quantity, confirmation is required from an independent signal within
a bounded window, and failure to confirm withdraws it, then the cost of a false positive falls from a
delivered dose to a brief and reversed one. The accuracy bar drops to what the data can meet, and the
safety argument moves into the design of the action.

The false back-out rate of 11 per cent is benign for the same reason and should not be read as an
error rate in the usual sense. Backing out withdraws insulin that had only just been committed, so
the failure mode is a small quantity of insulin briefly present, which is the condition the
participant was already in before arming.

Nothing in this area doses. The detection is validated and the dosing benefit is not, and the
components in the engine are shadow-logging. The distinction matters because a validated detector is
routinely mistaken for a validated intervention, and the identification constraint means the second
requires a design the first does not.
