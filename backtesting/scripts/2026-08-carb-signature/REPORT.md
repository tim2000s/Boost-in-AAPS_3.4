# Reading food from the glucose trace: what is there and what is not (2026-08-13)

*Reproduce: `carb_signature.py` and `link_to_commits.py` against the local TimescaleDB refreshed
to t=now. 592 announced meals across six participants after excluding rescue carbohydrate, 2,883
unannounced rises as the comparison class, 2,505 commits for the linking analysis. Participants
are held out as folds throughout, and intervals come from resampling participants.*

## Why this exists

The commit-timing work found that commits followed by hypoglycaemia are those whose glucose peak
arrives soonest, that this is not anticipable from the state at the commit, and that the one
variant hinting at a mechanism was a small eventual excursion. That points at meal size, and meal
size has ground truth: six participants announce carbohydrate, 3,308 entries between 2 and 150 g.

Carbohydrate entered to treat a low is not a meal and is excluded, since its signature is a
recovery rather than an absorption. That leaves 592 meals with a median of 20 g and quartiles at
13 and 30.

## A meal is distinguishable from an unannounced rise, and early

Both classes are rises. The question is whether a declared meal looks different from a rise nobody
declared.

| horizon after onset | AUC | 95% CI |
|---|---|---|
| 10 min | 0.805 | [0.748, 0.850] |
| 15 min | 0.866 | [0.774, 0.905] |
| 20 min | 0.917 | [0.840, 0.947] |
| 30 min | 0.975 | [0.946, 0.985] |
| 45 min | 0.947 | [0.895, 0.965] |
| 60 min | 0.934 | [0.871, 0.957] |

Ten minutes after onset a meal is separable at 0.805, and by thirty minutes at 0.975. Detection is
not the constraint on this algorithm, and this is consistent with the existing detector working.

The figure should be read with one reservation. A declared meal is one the participant chose to
declare, and the undeclared rises include dawn phenomenon, stress and rebounds, which differ in
shape for reasons other than carbohydrate. The comparison bounds what a detector can do rather
than isolating carbohydrate as such.

## The amount is not readable

Small is under 20 g and large over 40, with the middle dropped so that the classes genuinely
differ.

| horizon | AUC, held out by participant | 95% CI | the rise alone |
|---|---|---|---|
| 10 min | 0.267 | [0.167, 0.553] | 0.587 |
| 15 min | 0.275 | [0.183, 0.511] | 0.589 |
| 20 min | 0.364 | [0.263, 0.577] | 0.582 |
| 30 min | 0.398 | [0.316, 0.569] | 0.564 |
| 45 min | 0.508 | [0.414, 0.643] | 0.616 |
| 60 min | 0.505 | [0.443, 0.681] | 0.654 |

A model held out by participant is worse than chance at the early horizons, which is what a
relationship that inverts between people looks like rather than one that is merely absent. The raw
rise carries a little, at 0.587 to 0.654, and the multivariate fit destroys it.

As a quantity the result is the same. Correlation between predicted and announced carbohydrate is
negative at every horizon, from −0.326 at ten minutes to −0.062 at sixty, and the mean absolute
error of 18 to 21 g is worse than the 13.2 g obtained by predicting the median and stopping.

Within a participant, fitting on their earlier meals and scoring the later ones against their own
median, the picture does not improve where it is best powered.

| user | meals | test | 10 min | 15 min | 20 min | 30 min | 45 min | 60 min |
|---|---|---|---|---|---|---|---|---|
| A | 54 | 22 | 0.517 | 0.291 | 0.624 | 0.581 | 0.483 | 0.423 |
| E | 372 | 149 | 0.541 | 0.492 | 0.500 | 0.515 | 0.452 | 0.549 |
| F | 82 | 33 | 0.769 | 0.635 | 0.750 | 0.619 | 0.662 | 0.662 |

E carries by far the most data and sits at chance across every horizon. F is consistently above
0.5 on 33 test meals, which is suggestive and not enough on its own.

## The eventual excursion is readable, and too late

The peak rise over the onset needs no announcement, so a model for it could be trained on
everybody.

| horizon | correlation | MAE mg/dL | MAE of predicting the median |
|---|---|---|---|
| 10 min | −0.100 | 32.0 | 25.6 |
| 15 min | −0.033 | 31.1 | 25.6 |
| 20 min | −0.007 | 30.3 | 25.6 |
| 30 min | 0.095 | 29.8 | 25.6 |
| 45 min | 0.391 | 25.8 | 25.6 |
| 60 min | 0.515 | 23.0 | 25.6 |

Nothing beats predicting the median until forty five minutes after onset. Glucose peaks a median
of fifty four minutes after a commit, so the excursion becomes estimable at about the moment it
stops mattering.

## The two findings are one finding

Linking back to the commits, the interval to the peak and the size of the excursion correlate at
+0.416, and the size is the better predictor of the low, at 0.599 against 0.582.

| cell | n | low rate | median rise | median glucose |
|---|---|---|---|---|
| short interval and small excursion | 318 | 0.270 | 6 | 152 |
| short interval, large excursion | 3 | | | |
| long interval, small excursion | 928 | 0.196 | 26 | 130 |
| long interval, large excursion | 1,256 | 0.134 | 72 | 121 |

The second cell is empty, which is the point: a commit cannot peak early and go high. The interval
is a consequence of the size.

Sorting on the excursion directly shows what the algorithm is doing.

| eventual excursion | n | low rate | median dose |
|---|---|---|---|
| under 10 mg/dL | 325 | 0.243 | 0.40 |
| 10 to 25 | 436 | 0.206 | 0.85 |
| 25 to 50 | 633 | 0.202 | 0.95 |
| 50 to 80 | 578 | 0.152 | 0.90 |
| over 80 | 533 | 0.096 | 0.75 |

The low rate falls from 24 per cent to 10 across the range. The dose is between 0.85 and 0.95 U
throughout the middle four bands. The algorithm delivers about the same quantity whether the
excursion turns out to be 15 mg/dL or 80, because at the moment it decides it cannot tell which it
is facing.

## Conclusion

There is a food signal in the trace and it is a strong one, but it answers the question the
algorithm already answers. Whether this is a meal is separable at 0.805 within ten minutes. How
large a meal is not separable at any horizon that would allow the dose to be sized, and the model
that tries it is worse than chance out of sample because the mapping from carbohydrate to early
glucose differs between people.

That completes the account of the commit problem. The commits that end in hypoglycaemia are
commits into small meals; small meals are not distinguishable from large ones when the commitment
is made; and so the same dose goes to both.

Two consequences follow and neither requires the dangerous commit to be identified in advance. A
uniformly smaller committed dose trades peak height for hypoglycaemia across the whole
distribution, which is what the pre-registered within-participant trial measures. Or the dose is
staged, with a smaller initial commitment and a second tranche released once the excursion has
declared itself, which the evidence here says takes about forty five minutes.

Confidence: SOLID for meal detection and for the null on size, both being out of sample with
participants held out and consistent across horizons. SOLID for the association between excursion
size and the subsequent low. SPECULATIVE for staged dosing, which is an inference from these
measurements and has not been tested.

## Limitations

E contributes 372 of 592 meals, so the pooled figures are self-dominated, which is why the
per-participant table is given. The participant this fork is developed on announces essentially
nothing and appears in none of the meal analysis, so the size result reaches him only through
cross-participant transfer, which is the thing that fails. Announced carbohydrate is itself an
estimate made by the person eating. And the linking analysis is observational: that small
excursions carry more lows at a similar dose does not establish that a smaller dose at those
commits would have prevented them.
