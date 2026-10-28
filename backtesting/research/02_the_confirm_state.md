# The committed state and subsequent hypoglycaemia

Three attempts to identify which commitments are dangerous, and the question underneath them that
went unasked.

## Abstract

Entering the committed state is the moment a meal-dosing algorithm commits a substantial quantity to
a meal it believes is real, and a fall into hypoglycaemia sometimes follows a couple of hours later.
Three hypotheses about which commitments are dangerous all return chance. The excursion shape is not
predictable from the state available at the moment of commitment, at an area under the curve of 0.518
with an interval from 0.485 to 0.549 over 2,117 meals. Continued acceleration after a commitment
predicts a peak some 23 mg/dL higher but carries no room to act, the accelerating group crashing at
about 19 per cent with severe lows at 6.6, which is not lower than the decelerating group. Decaying
acceleration on the approach does not predict the crash either: 24.0 per cent against 22.1, a
difference of 1.9 points with an interval from minus 4.1 to plus 8.1 over 1,268 commitments, with
eight further threshold variants all spanning zero and two pointing the wrong way. The assumption
underneath all three, that the post-commitment low rate is elevated at all, is correct and is the
finding. Against controls matched within participant on hour of day, starting glucose and insulin on
board, commitments are followed by glucose below 70 mg/dL on 22.8 per cent of occasions against 14.0,
and below 54 on 7.6 against 1.9, differences of 8.8 points with an interval from 3.9 to 14.0 and 5.7
points with an interval from 3.0 to 8.5, from 1,074 matched commitments across eleven participants.

## Introduction

A dosing algorithm that detects unannounced meals has to commit at some point, and the commitment is
the largest single quantity it delivers. A recurring clinical observation is that some commitments
are followed by hypoglycaemia.

If the dangerous commitments can be identified at the moment of commitment, the algorithm can
restrain those specifically and leave the others alone, which is much the most attractive outcome
because it costs nothing on the commitments that were fine. Three candidate discriminators were
entertained in turn: that the crash is foreseeable from the state at commitment, that continued
acceleration afterwards marks a meal that will overshoot, and that a commitment arriving as
acceleration decays is a late one firing on a rise that has already peaked.

Underneath all three sits an assumption that was not itself examined, namely that the post-commitment
low rate is elevated rather than simply being what follows any period of rising glucose. A
discriminator is only worth having if there is something to discriminate.

## Methods

Prediction of excursion shape used out-of-sample validation with participants held out as folds, on
2,117 meals, recorded under `backtesting/scripts/2026-07-postconfirm-accel/meal_shape.py`.

The continued-acceleration comparison used 3,879 anchors across nine participants with cluster
bootstrap intervals, supplemented by driving the real engine through reconstructed scenarios.

The decay comparison classified every commitment by the behaviour of acceleration over the approaching
cycles, on 1,268 commitments across twelve participants from 26 June to 12 August 2026, with intervals
from a bootstrap resampling participants, recorded under `backtesting/scripts/2026-08-confirm-decay/`.

The matched-baseline comparison paired each commitment with control windows drawn from the same
participant, matched on hour of day to within an hour, on starting glucose to within 15 mg/dL and on
insulin on board to within 0.5 U, requiring no commitment in the window or the hour preceding it, at a
median of 43 controls per commitment. The outcome was the lowest glucose in the following three hours.

## Results

The crash is not foreseeable at commitment. The area under the curve is 0.518 with an interval from
0.485 to 0.549. Tail shape, meaning under-recovery rather than overshoot, is weakly predictable at
0.60 with an interval from 0.58 to 0.63, diffuse and partly explained by clustering of second meals.

Continued acceleration predicts the size of the excursion, at a peak some 23 mg/dL higher and
distinguishable from noise, and carries no room to act. The accelerating group crashes at about 19 per
cent with severe lows at 6.6 per cent, which is not lower than the decelerating group and for two
participants is higher.

Decaying acceleration does not predict the crash. Commitments approached with decaying acceleration
were followed by a low within three hours on 24.0 per cent of occasions against 22.1 for sustained or
rising, a difference of 1.9 points with an interval from minus 4.1 to plus 8.1. Eight further
threshold variants, including acceleration near zero at the moment of commitment and a fall of twenty
points or more, all span zero, two pointing the wrong way. Dose size does not separate it either.

Against matched controls, commitments are followed by glucose below 70 mg/dL on 22.8 per cent of
occasions against a control rate of 14.0, and below 54 on 7.6 against 1.9. The differences are 8.8
points with an interval from 3.9 to 14.0 and 5.7 points with an interval from 3.0 to 8.5, from 1,074
matched commitments across eleven participants. Nine of the eleven move in the same direction and no
single participant carries the result.

## Discussion

Committing roughly doubles the chance of a subsequent low and quadruples the chance of a severe one,
from the same starting state in the same person at the same time of day. That is the substantive
result of the topic, and it is the one that determines what can be done.

The three failures are not incidental to the fourth success. If the crash cannot be distinguished at
the moment of commitment, then no gate conditioned on the state at that moment can help, and the
available levers reduce to two: give less, or withdraw afterwards. The retractable back-out design
elsewhere in this series is vindicated by exactly this reasoning, and a within-participant randomised
trial on the committed dose is pre-registered under
`backtesting/protocols/2026-08_confirm_dose_PREREG.md`.

One methodological point carries forward. The decay hypothesis was entertained partly because the
acceleration metric appeared to contradict a commitment, reading 1.63 on the event that prompted the
enquiry against 32 four cycles earlier. The metric is one hundred times the difference between the
current change and its short average, divided by that average floored at two. On a steady steep rise
the change converges on its own short average and the metric reads near zero by construction. It is
high at the onset of a rise and decays as the rise establishes itself, so a low value indicates that
the rise is steady rather than that it is failing.

The nine threshold variants tried across these hypotheses are a caution in their own right. One
cleared zero by a tenth of a point, weakened as the threshold tightened, and reversed sign. It is
recorded as noise rather than as a lead, because a discriminator hunted across enough cuts of the same
events will eventually produce one that clears, and the defence is to pre-register the cut or to report
every variant attempted.
