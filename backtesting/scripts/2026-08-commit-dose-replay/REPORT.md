# Pricing a smaller committed dose against the record (2026-08-13)

*Reproduce: `commit_dose_replay.py`, `target_detector.py`, `combined_policy.py`. 1,718 commits
carrying a delivered dose across nine participants, five hours of trajectory each, sensitivity
taken per commit from the record.*

## What cannot be done

A replay that assigns a dose and then reads the recorded glucose is not a counterfactual. The
glucose that followed each commit followed the dose actually given, and randomising the assigned
label does not change that. The observational dose response in this cohort comes out near
6 mg/dL per unit against a dithering estimate of about minus 45, because the dose is chosen by the
policy whose effect is in question. The trial for this is prospective for that reason.

## What is bounded here

Reducing the committed dose does not change the meal, so the carbohydrate side of the trajectory
is held exactly as observed and only the insulin side recomputed. Insulin not given never acts, so
the counterfactual glucose is above the recorded glucose by

    delta_bg(t) = ISF x removed_dose x fraction of that dose that had acted by t

with sensitivity per commit from the record and the activity curve the app uses.

The bound is one-sided in a known direction. The recorded trajectory already contains whatever
counter-regulation the low provoked, so lows avoided is a ceiling while the exposure cost is not.
The loop's own subsequent decisions are unmodelled.

Cost is measured as added glucose exposure above 180 mg/dL, in mg/dL hours. Insulin removed is not
a cost: what a reduction actually spends is the hyperglycaemia accepted in exchange, and that
differs by a factor of eight between commits.

## Where the harm sits

| cell | n | low rate | severe | median dose |
|---|---|---|---|---|
| late peak, large dose | 81 | 0.457 | 0.136 | 2.25 |
| late peak, small dose | 80 | 0.375 | 0.163 | 0.65 |
| normal peak, large dose | 776 | 0.325 | 0.107 | 2.35 |
| normal peak, small dose | 781 | 0.335 | 0.104 | 0.75 |

Late commits carry a 37 to 46 per cent low rate against 32 to 34 for the rest. Dose separates the
outcome only when the commit is late, which is the signature of insulin delivered into a meal that
is already over.

## What a cut costs, by where it lands

Scaling to 0.85, per commit treated:

| | lows avoided each | exposure cost each |
|---|---|---|
| a late commit | 0.099 | 1.00 mg/dL.h |
| a normal commit | 0.119 | 8.48 mg/dL.h |

The benefit is comparable and the cost differs 8.5-fold. That is the whole of the case for
targeting: withholding insulin from a commit whose excursion has finished is nearly free, and
withholding it from a live meal forfeits real coverage.

At matched multiplier, treating only late commits costs 10.0 mg/dL hours per low prevented against
66.5 for treating everything, a factor of 6.6.

## What a buildable detector reaches

The cost of cutting is partially predictable at the commit, at a correlation of 0.429 out of sample
with participants held out, though its absolute error of 8.10 is no better than the 7.65 obtained
by predicting the median. The ranking carries signal; the level does not.

Treating the cheapest predicted fraction, scored on realised outcomes so a wrong prediction is
charged what it actually cost:

| treated | lows avoided | mg/dL.h | per low | against uniform |
|---|---|---|---|---|
| 5% | 9 | 294 | 32.7 | 2.04x |
| 10% | 13 | 414 | 31.8 | 2.09x |
| 20% | 22 | 821 | 37.3 | 1.78x |
| 30% | 31 | 1,429 | 46.1 | 1.44x |
| all | 201 | 13,357 | 66.5 | 1.00x |

The detector doubles efficiency and reaches little of the problem, 13 lows against 201. Its
enrichment for lateness is weak, lifting the share from 0.094 to 0.135 at its best operating point,
which is consistent with lateness itself being unpredictable. It finds cheap commits by other
routes.

## The combined policy, at matched benefit

Efficiency per low is the wrong comparison between policies of different reach. The question is
what it costs to prevent a given number of lows. Against the pure uniform frontier interpolated to
the same benefit:

| uniform | targeted | treated | lows avoided | mg/dL.h | uniform at same benefit | saving |
|---|---|---|---|---|---|---|
| 1.00 | 0.70 | 10% | 19 | 874 | 963 | 9.2% |
| 0.95 | 0.70 | 10% | 94 | 4,594 | 4,970 | 7.6% |
| 0.90 | 0.70 | 10% | 160 | 8,862 | 9,486 | 6.6% |
| 0.90 | 0.70 | 20% | 167 | 9,470 | 10,147 | 6.7% |
| 0.90 | 0.50 | 20% | 182 | 11,014 | 11,563 | 4.7% |
| 0.90 | 0.30 | 20% | 193 | 12,986 | 12,602 | -3.0% |
| 1.00 | 0.30 | 10% | 28 | 2,747 | 1,419 | -93.5% |

With perfect targeting the same structure saves 23 to 67 per cent. With the buildable detector it
saves between 2 and 9, and deep targeted cuts are worse than uniform because a prediction error is
charged at the full cost of a deep cut on a live meal.

## Conclusion

Targeting is worth doing in principle and the headroom is large: a commit whose excursion is
finished can be cut almost for free, and perfect selection would cut the cost of a given benefit by
a quarter to two thirds. The buildable version captures a small part of that, around 6 to 9 per
cent at matched benefit, and only with a shallow targeted cut. A deep cut on an imperfect
prediction is worse than doing nothing selective at all.

The practical reading is that the registered uniform trial remains the right first experiment,
because it is the policy whose benefit is large enough to measure and whose failure modes are
understood. A shallow targeted overlay is a second-order refinement worth perhaps a tenth of the
exposure cost, and it should not be bundled into the first trial, where it would add a factor
without the power to resolve it.

Confidence: PROVISIONAL throughout. A one-armed bound with the loop's response unmodelled is not a
substitute for the trial, the benefit side is optimistic by construction, and the targeting figures
rest on a detector whose absolute calibration is no better than a constant.

## Per participant, uniform arm at 0.70

| user | commits | observed lows | avoided | share | U removed |
|---|---|---|---|---|---|
| A | 260 | 42 | 24 | 0.57 | 183.4 |
| B | 348 | 90 | 51 | 0.57 | 194.5 |
| C | 273 | 121 | 59 | 0.49 | 98.3 |
| D | 177 | 88 | 21 | 0.24 | 72.2 |
| E | 39 | 11 | 7 | 0.64 | 14.0 |
| F | 211 | 53 | 30 | 0.57 | 99.4 |
| H | 56 | 13 | 9 | 0.69 | 35.9 |
| I | 16 | 7 | 3 | 0.43 | 4.7 |
| tim | 338 | 156 | 109 | 0.70 | 126.0 |

D is both the participant the reduction reaches least and the one with the highest commit-related
low rate, which is worth knowing before randomising rather than after.
