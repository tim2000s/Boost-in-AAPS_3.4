# Static against dynamic insulin sensitivity, and 5-minute against 1-minute loop cadence, in one adult on a fully closed loop

## Summary

Two settings on one person's automated insulin delivery system changed within a week of each other.
Because the dates differ, their effects separate.

Switching the insulin sensitivity factor (ISF) from glucose-responsive to fixed, with the loop still
cycling every five minutes, moved time below 70 mg/dL (3.9 mmol/L) from 5.51 to 3.53 per cent. That
is 1.94 percentage points and a relative reduction of about a third, alongside 3.8 points less time
in range and a mean 7.4 mg/dL higher, which is the trade a loop giving slightly less insulin would
be expected to make.

None of it is distinguishable from chance. The interval on the time-below-range difference runs from
4.81 points better to 1.03 worse, and every other measure spans zero as widely. With six days in
that arm the study cannot resolve a difference smaller than roughly eight points of time in range,
so this is underpowered rather than negative, and the point estimate is the more useful thing to
carry forward than the verdict.

Moving the loop from a five-minute to a one-minute cycle raised total insulin delivery by about a
fifth, from 32.7 to 39.9 units per day, and roughly doubled time below 70 mg/dL (3.9 mmol/L) from
3.5 to 8.9 per cent. One of the four days spent 2.5 per cent below 54 mg/dL (3.0 mmol/L). Both
figures sit outside the consensus targets of under 4 per cent and under 1 per cent. Time in range
itself did not separate.

The extra insulin is a property of the faster loop rather than of the conditions it met. Matched on
glucose, the one-minute loop delivered more in every band, and between 110 and 130 mg/dL (6.1 to
7.2 mmol/L), where no correction is called for, it delivered 1.26 units per hour against 0.45.

This is a sequential before-and-after comparison in one adult, with no counterfactual glucose
trajectory available and with carbohydrate intake unrecorded. It prices an association and the
mechanism behind it; it does not establish what a randomised comparison would have shown.

Single participant, tag `self`, 28 days to 2026-09-03. The database was refreshed to the time of
analysis first. Scripts and outputs are in `backtesting/scripts/2026-09-isf-cadence-tir/`.

## Two changes, and why they separate

Two settings changed on different dates, which is what makes them separable rather than confounded
with each other.

ISF stopped moving with glucose on 2026-08-26 at about 09:00 local. `variable_sens` and
`dynamic_isf` became identical to three decimal places within one hour, having differed by 5.7,
12.6 and 44.6 mg/dL/U in the three hours before, and the within-day spread of ISF fell from a
standard deviation of 20 to 60 down to 3 to 5. What is left is the profile value of 61.2 modulated
only by autosens, the recurring 51.0 being 61.2 divided by 1.2. The `running_dynamic_isf` flag
stays true throughout and does not mark this change, so it should not be used to find it. An
independent corroboration is that `tdd_24h` goes null from 2026-08-27, the dynamic-ISF machinery
having stopped computing the total daily dose it needs.

Loop cadence went from 5 minutes to 1 minute on 2026-08-31 at 19:00 local, the median inter-cycle
gap falling from about 280 s to about 60 s inside a single hour. That boundary is 70 hours before
the end of the window.

So arm A against arm B isolates the ISF change with cadence held at 5 minutes, and arm B against
arm C isolates the cadence change with ISF already static.

Every reading is snapped to a common 5-minute grid before any metric is computed. Without that, the
1-minute arm contributes five times the rows per hour and would be weighted five-fold.

## Glucose outcomes

| arm | days | hours | TIR 70-180 | time in normoglycaemia (TING) 63-140 | <70 | <54 | >180 | mean mg/dL | CV % |
|---|---|---|---|---|---|---|---|---|---|
| A dynamic ISF, 5 min | 21 | 456 | 85.0 | 72.4 | 5.51 | 0.40 | 9.5 | 121 | 34.0 |
| B static ISF, 5 min | 6 | 125 | 81.2 | 66.6 | 3.53 | 0.53 | 15.3 | 129 | 38.8 |
| C static ISF, 1 min | 4 | 69 | 78.7 | 68.0 | 8.94 | 0.85 | 12.3 | 120 | 36.8 |

Differences in percentage points, with 95% intervals from a bootstrap that resamples whole local
days, so the effective sample size is the number of days rather than the number of readings.

| comparison | TIR | TING | below 70 | mean mg/dL |
|---|---|---|---|---|
| static minus dynamic, cadence held at 5 min | -3.83 (-11.24 to +4.31) | -5.86 (-14.90 to +2.83) | -1.94 (-4.81 to +1.03) | +7.42 (-2.23 to +18.52) |
| 1 min minus 5 min, ISF held static | -2.74 (-11.23 to +4.91) | +1.37 (-6.58 to +9.46) | +5.25 (+0.92 to +8.92) | -8.26 (-20.49 to +3.86) |

Static against dynamic ISF is unproven on every measure. Each interval spans zero comfortably, and
with six days in arm B the study cannot resolve a difference smaller than roughly eight percentage
points of time in range. Nothing here says the two are equivalent; it says this window cannot tell
them apart.

For the cadence change, time in range is also not distinguishable. Time below 70 mg/dL (3.9 mmol/L) is: it rises
by 5.25 percentage points and the interval excludes zero. That is the one result in this report that
clears its own bar, and it is the one worth acting on.

## Insulin delivery

Reconstructed from the treatment stream, each temporary basal running until the next begins or its
stated duration expires. Arm A reconstructs to 33.2 U per 24 h against the engine's own `tdd_24h`
median of 33.7, which is the check that the integration is doing what it claims.

| arm | SMBs per 24 h | median SMB U | basal U/24h | SMB U/24h | total U/24h | temp basal coverage |
|---|---|---|---|---|---|---|
| A dynamic ISF, 5 min | 47.2 | 0.20 | 13.69 | 19.49 | 33.18 | 89.0% |
| B static ISF, 5 min | 55.6 | 0.20 | 13.20 | 19.48 | 32.68 | 90.2% |
| C static ISF, 1 min | 126.8 | 0.15 | 10.13 | 29.73 | 39.86 | 95.6% |

At 1-minute cadence the loop issues 2.3 times as many microboluses, each slightly smaller, and
delivers 53 per cent more insulin through the SMB path while cutting basal by 23 per cent. Total
delivery rises about 22 per cent, from 32.7 to 39.9 U per 24 h. Uncovered time is counted as zero
basal rather than filled, and since arm A and arm B have more uncovered time than arm C, filling it
would narrow the gap: at a flat 0.72 U/h the totals become 35.1, 34.4 and 40.6, an 18 per cent rise
rather than 22.

## Is the extra insulin a cadence effect, or did conditions call for it?

The 22 per cent rise is compatible with two stories: the loop is more aggressive for a given state,
or it met states that called for more insulin. Matching the arms on glucose separates them.

| glucose mg/dL | 5 min U/hr | 1 min U/hr | difference (95% CI) |
|---|---|---|---|
| <70 | 0.000 | 0.000 | +0.000 (+0.000 to +0.000) |
| 70-90 | 0.015 | 0.031 | +0.015 (-0.027 to +0.069) |
| 90-110 | 0.092 | 0.314 | +0.224 (+0.000 to +0.426) |
| 110-130 | 0.445 | 1.260 | +0.812 (+0.463 to +1.140) |
| 130-160 | 1.644 | 2.155 | +0.461 (-0.770 to +1.458) |
| 160-200 | 1.977 | 3.900 | +1.862 (+0.278 to +2.937) |
| >200 | 2.758 | 3.094 | +0.486 (-0.820 to +2.203) |

The 1-minute arm doses more in every band, and the interval excludes zero in three of them. Applying
its dosing rates to the 5-minute arm's own distribution of glucose gives 33.4 U per 24 h of SMB
against the 20.2 actually delivered, so roughly two thirds more microbolus insulin that is not
explained by where glucose sat. The direction of the mean rules out the alternative story from the
other side: arm C ran at a lower mean glucose than arm B, 120 against 129, so the extra insulin was
not a response to running higher.

The band that matters for hypoglycaemia is 110 to 130 mg/dL, which is 6.1 to 7.2 mmol/L and squarely in
range. There the 1-minute loop delivers 1.26 U/h against 0.45, nearly three times as much insulin at
a glucose that needs none of it. That is the most plausible mechanism for the extra time below 70.

Holding trend as well as glucose leaves the pattern intact in most cells, and one is worth naming.
Between 160 and 200 mg/dL with glucose falling, the 5-minute arm delivers 0.020 U/h and the
1-minute arm 0.309. Dosing into a recovering high is the failure mode this programme has documented
repeatedly as its own commonest route into a low, and the cadence change has made it about fifteen
times more likely per unit time in that state.

This is still a before-and-after on one person with carbohydrate unobserved, so it does not have the
standing of a randomised comparison. What the matching does establish is that the extra insulin is a
property of how the loop behaves at 1-minute cadence rather than of the conditions it happened to
meet.

## Scope of the conclusion

The rise in time below range is not one bad night. Per local day in arm C it runs 1.69, 11.19, 6.29
and 11.65 per cent, so three of the four days sit above 6 per cent. On 2026-09-01, 2.53 per cent of
the day was spent below 54 mg/dL (3.0 mmol/L), which is past the consensus absolute floor of 1 per cent that the
programme treats as a kill-switch criterion. Arm C's 8.94 per cent below 70 is also past the 4 per
cent floor, though it should be noted that arm A sits at 5.51 per cent and is already above it, so
the floor was not being met before the cadence change either.

The comparison is sequential and observational. There is no counterfactual glucose trajectory, so
anything that drifted across these weeks moves with the arm assignment and cannot be separated from
it. Carbohydrate is never recorded on this device, zero entries across all three arms, so intake is
unobserved rather than shown to be equal, and a change in eating would land entirely in the
unannounced-meal path where it would look like a dosing effect.

Arm C is 70 hours and four local days. A day-block bootstrap on four blocks is a weak instrument,
and the interval on time below 70 should be read as the weakest kind of positive result rather than
a settled one. The direction is corroborated by the delivery figures, which do not depend on the
bootstrap at all: 22 per cent more insulin per day is a large change to make without intending it,
and it is the most likely mechanism for the extra time below range.

Tier PROVISIONAL for the cadence result, since it is a single test on one participant with a wide
interval. Tier unproven for the ISF comparison, which is underpowered rather than negative.

## Consequences

The 1-minute arm is delivering about a fifth more insulin per day than the 5-minute arm on the same
settings, and time below 70 mg/dL has roughly doubled. Whether the intended change was the cadence
alone or the dose response that follows from it is a question for the person running it. If the
cadence is to continue, the caps that bound cumulative SMB volume are the levers that would hold
delivery near where it was, and they would need re-placing for a loop that now has five times as
many opportunities to dose.
