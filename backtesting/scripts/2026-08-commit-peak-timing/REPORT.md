# Commit-to-peak interval and the low that follows (2026-08-13)

*Reproduce: `peak_timing.py` against the local TimescaleDB refreshed to t=now. 2,505 commits
across nine participants, one decision row per five-minute bucket, intervals from a cluster
bootstrap over participants.*

## Why this exists

A separate analysis asked whether a commit approached with decaying `delta_accl` predicts the
crash that sometimes follows, and returned a null across nine threshold variants. That metric is
one hundred times the difference between the current change and its short average, divided by
that average floored at two, so on a steady or steepening rise it converges on zero by
construction.

An event on 2026-08-13 shows what that costs. Across the approach `delta_accl` read −2.4, −1.4,
−1.9 and −0.6 while the raw five-minute increments were +12, +14 and +21. The metric called the
approach flat; the glucose was making its steepest increment yet. The commit fired 4.50 U at
183 mg/dL, glucose peaked five minutes later at 199, and fell 116 mg/dL over the next thirty
minutes with 4.33 U still on board at 83.

This asks the question the metric could not: how long after the commit does glucose peak, and
does a short interval predict the low.

## Design

The event is entry into the CONFIRMED state, which is where the committed dose fires. The peak is
the maximum sensor value in the three hours from the commit. The outcome is a glucose below
70 mg/dL sustained at least ten minutes within three hours of the commit.

The primary comparison was fixed before running: peak at or within ten minutes of the commit
against peak later. Every other cut examined is listed below rather than in a footnote.

## Results

Glucose peaks a median of 54 minutes after a commit, and within ten minutes on 12.8 per cent of
occasions.

| interval to peak | n | low rate | median dose | median glucose |
|---|---|---|---|---|
| at or before the commit | 104 | 0.288 | 0.28 | 166 |
| 0 to 10 min | 217 | 0.258 | 1.00 | 149 |
| 10 to 20 min | 288 | 0.274 | 1.00 | 136 |
| 20 to 40 min | 449 | 0.163 | 1.00 | 132 |
| 40 to 80 min | 527 | 0.114 | 0.70 | 127 |
| over 80 min | 920 | 0.150 | 0.65 | 117 |

On the primary comparison, commits whose peak falls within ten minutes are followed by a low on
26.8 per cent of occasions against 16.0 per cent for the rest, a difference of 10.8 points with an
interval from 5.5 to 14.7.

Scored as a continuous predictor against everything else available at the moment of commit:

| predictor | AUC | 95% CI |
|---|---|---|
| shorter interval to peak | 0.582 | [0.548, 0.631] |
| delta_accl, the retired metric | 0.498 | [0.449, 0.543] |
| committed dose | 0.492 | [0.458, 0.529] |
| insulin on board | 0.435 | [0.403, 0.515] |
| glucose at commit | 0.422 | [0.361, 0.499] |

The interval is the only quantity clear of chance in the expected direction. Glucose at commit is
clear of chance in the inverted direction, meaning commits at higher glucose are followed by fewer
lows, which is consistent with the recovering-high context found elsewhere in the programme.

Every cut examined, with the primary marked:

| variant | n | difference | 95% CI |
|---|---|---|---|
| peak at or before the commit | 104 | +0.119 | [+0.039, +0.211] |
| peak within 5 min | 206 | +0.112 | [+0.055, +0.159] |
| peak within 10 min (primary) | 321 | +0.108 | [+0.055, +0.147] |
| peak within 15 min | 464 | +0.138 | [+0.086, +0.191] |
| peak within 20 min | 609 | +0.128 | [+0.089, +0.164] |
| peak within 30 min | 851 | +0.121 | [+0.096, +0.139] |
| peak within 10 min and dose at least 2 U | 68 | +0.139 | [+0.039, +0.261] |
| peak rise over the commit under 20 mg/dL | 593 | +0.072 | [+0.022, +0.116] |
| peak within 10 min and glucose at least 180 | 93 | +0.031 | [−0.092, +0.159] |
| last increment was the largest of the approach | 1,426 | −0.030 | [−0.053, +0.007] |

The effect is stable from 0.112 to 0.138 across every threshold from zero to thirty minutes rather
than clearing zero at one cut and weakening either side, which is the signature that separates this
from the nine dead variants on the adjacent hypothesis.

That the approach shape does not carry it is worth stating: whether the last increment was the
largest of the approach makes no difference, at −0.030 with an interval spanning zero. The signal
is in when the peak arrives, not in how hard glucose was rising into the commit.

Eight of nine participants move in the same direction.

| user | commits | early | rate early | rate late | difference |
|---|---|---|---|---|---|
| A | 352 | 31 | 0.161 | 0.053 | +0.108 |
| B | 424 | 51 | 0.275 | 0.107 | +0.167 |
| C | 377 | 38 | 0.263 | 0.212 | +0.051 |
| D | 272 | 41 | 0.463 | 0.316 | +0.147 |
| E | 127 | 18 | 0.000 | 0.138 | −0.138 |
| F | 375 | 55 | 0.218 | 0.100 | +0.118 |
| H | 78 | 11 | 0.182 | 0.060 | +0.122 |
| I | 19 | 4 | 0.250 | 0.067 | +0.183 |
| tim | 481 | 72 | 0.319 | 0.235 | +0.085 |

E is the exception, on eighteen early commits with no lows among them.

## The limitation that governs what can be done with this

The interval is measured using data from after the commit. It is not available at the moment of
commit and cannot gate one. Nothing here is a lever.

What it establishes is that the mechanism is real and correctly identified: a commit that lands at
or near the peak delivers insulin against carbohydrate that has largely been absorbed, and is
followed by a low half again as often as one that lands early in a rise. It also confirms the
earlier null on the same events, since `delta_accl` scores 0.498 here.

The actionable question is therefore a prediction problem rather than a gating rule, and it is
answered below.

Two further caveats bound this. The association is observational, and nothing here shows that a
smaller dose at those commits would have avoided the low. And for the longer intervals the
causation may run partly the other way, since a large dose can bring a peak forward; that
possibility does not touch the short-interval cells, where insulin has not had time to act.

Confidence: SOLID for the association and its direction, being stable across nine cuts, consistent
across eight of nine participants, and clear of the alternatives on the same events. SPECULATIVE
for anything built on it, since the discriminating quantity is not observable at decision time.

## Can the peak timing be anticipated (`predict_peak.py`)

A gradient-boosted model over 29 features drawn strictly from before the commit, scored out of
sample with participants held out as folds, predicts an early peak at an area under the curve of
0.731 with an interval from 0.701 to 0.770. A logistic model on the same features and folds
reaches 0.697, so the result is not a flexible model fitting noise.

The prediction does not help.

| | AUC | 95% CI |
|---|---|---|
| predicted early peak, against the low | 0.448 | [0.404, 0.499] |
| the true interval, against the low | 0.581 | [0.548, 0.629] |

The out-of-sample probability of an early peak does not separate the low, and points the wrong
way. Its top decile carries a low rate of 0.116 against 0.181 elsewhere, on a base of 0.175.

The reason is a decomposition rather than a failure of the model. Glucose at the commit alone
predicts an early peak at 0.720, against 0.731 for the full model, and the predicted probability
correlates with glucose at +0.595. The model is close to a glucose detector, and glucose at commit
is inversely associated with the low.

| cell | n | low rate | median glucose |
|---|---|---|---|
| truly early, model predicted it | 172 | 0.198 | 166 |
| truly early, model missed it | 145 | 0.352 | 131 |
| not early, model predicted early | 450 | 0.133 | 154 |
| not early, model agreed | 1,719 | 0.168 | 118 |

The early peaks the model catches arrive at high glucose and are followed by a low on 19.8 per cent
of occasions, barely above the base rate. The early peaks it misses arrive at ordinary glucose,
around 131 mg/dL, and are followed by a low on 35.2 per cent. The harmful cases are precisely the
ones a predictor keyed on glucose cannot see.

The interval is not merely a restatement of the glucose, which is what makes this a real
decomposition rather than a tautology. Within bands of glucose at the commit it continues to
separate the outcome, and does so more strongly at higher glucose.

| glucose at commit | n | AUC of the interval | low rate |
|---|---|---|---|
| under 120 | 994 | 0.559 | 0.223 |
| 120 to 150 | 838 | 0.613 | 0.147 |
| 150 to 180 | 395 | 0.694 | 0.137 |
| over 180 | 259 | 0.689 | 0.135 |

## Where this leaves it

The interval from commit to peak carries real information about the low, beyond glucose and beyond
everything else observable at the commit. The component of it that can be anticipated is the
component driven by glucose, and that component is benign. The component that is harmful, an early
peak arriving at ordinary glucose, is the residual, and the residual is what a cross-participant
model cannot reach.

This is the identification constraint in an unfamiliar place. The usual form is that the outcome of
an untaken action is unavailable. Here the discriminating quantity is observable, and only after the
moment at which it would have to be used.

The consequence is that no gate conditioned on the state at the commit will separate these cases,
which is the same conclusion three earlier attempts reached by different routes. The levers remain
the two the programme already has: give less at the commit, which the pre-registered
within-participant trial tests, or withdraw afterwards, which is what the retractable back-out was
designed for and which does not require the dangerous commits to be identifiable in advance.

Confidence: SOLID for the null on anticipation, being robust across two model classes with
participants held out, and explained by a decomposition rather than merely observed.

## Does the state estimator see it at the commit (`twin_at_commit.py`)

The estimator is the one instrument with a reason to reach the residual rather than more features
to throw at it. Its inferred glucose appearance rate estimates how much carbohydrate is still
arriving, which is dose-independent and is the quantity that separates a meal still climbing from
one nearly absorbed. If appearance has turned over at the commit, the peak is imminent whatever the
glucose reads.

It does not, and the reason is structural rather than statistical.

Across 221 commits with estimator fields, appearance is at its own maximum over the preceding
thirty minutes on 93.2 per cent of commits, and at 95 per cent of it or above on 96.4. The median
ratio is 1.000. At the moment of commit the inferred appearance has essentially never turned over,
so the discriminator has no spread and there is nothing for a test to separate.

That is not an accident of this sample. Appearance is inferred from glucose by the filter, so it
cannot lead glucose. There is no independent observation of carbohydrate anywhere in the estimator,
and the state it reports is a smoothed reading of the same signal the interval is computed from.
Asking it to know that absorption has peaked before glucose peaks is asking it to carry information
it was never given. This is the same conclusion the identification work reached about insulin gain,
arrived at from the other end.

The areas under the curve on this subsample should not be read as a test of anything. There are 221
commits across seven participants, and glucose at commit scores 0.589 against the low here against
0.422 on the full 2,505. Restricting the full sample to the estimator era gives 0.464 and to the
estimator participants gives 0.452, so only the intersection moves, which is what small-sample noise
looks like rather than a real difference between eras.

What would be needed is an observation of carbohydrate that does not come from glucose. Announced
carbohydrate is the obvious one and is absent by design here, since the premise is unannounced
meals. Failing that, the conclusion is unchanged: the dangerous commits are not identifiable at the
moment of commitment, by any instrument the programme currently has.
