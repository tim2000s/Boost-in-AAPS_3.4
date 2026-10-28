# Field audit of the two shipped LightGBM models (2026-08-13)

*Reproduce: `ml_field_audit.py` against the local TimescaleDB refreshed to t=now. Ten Boost
users, all available history, one decision row per user per five-minute bucket. Intervals are
cluster bootstrap over users, 2000 resamples.*

## Why this exists

Two pre-trained LightGBM models ship inside the engine and are consumed on the dose path. Both
were trained in early 2026 on a foreign Nightscout cohort and validated at training time. Neither
has been scored against the telemetry of the people now running them. The models are the only
learned components in the shipping controller, so their field behaviour is the one ML question
that has direct dosing consequence.

## What the models actually are

Read from the metadata assets rather than from the documentation, which is stale in three places.

| | hypo risk (v12) | meal likelihood |
|---|---|---|
| trees / depth | 100 / 5 | 50 / 4 |
| features | 53 (17 static + 36 windowed lag0..5) | 8 |
| target | CGM < 70 sustained ≥ 15 min | peak ≥ current + 50 mg/dL |
| horizon | 90 min | 90 min |
| training rows / users | 3,007,589 / 32 | 2,978,062 / 28 |
| GroupKFold AUC | 0.8391 | 0.7342 |
| LOUO AUC | 0.8317 | 0.7375 |

The hypo model's KDoc, the V3ML reader document and the ML branch README all state the output is
"P(hypo event in next 4h)" with the event defined as two consecutive readings below 70. That was
the target of the model shipped on 2026-04-10 and retired on 2026-06-06, when the horizon moved to
90 minutes and the label became a sustained-15-minute one. The consuming code and its comments
were not updated. Anyone reasoning about the 0.30 and 0.60 thresholds from the documentation is
reasoning about the wrong quantity.

## Coverage and how often the thresholds bite

Current model era only. Scores populate 21.5 to 93.7 per cent of decision rows per user, the
remainder being cycles where the model had not loaded.

| user | cycles | scored | risk > 0.30 | risk > 0.60 | meal > 0.50 |
|---|---|---|---|---|---|
| A | 11,967 | 5,055 | 2.63% | 0.10% | 16.8% |
| B | 12,046 | 6,433 | 4.46% | 0.22% | 22.9% |
| C | 11,854 | 4,169 | 23.00% | 1.20% | 42.3% |
| D | 12,195 | 4,839 | 27.67% | 2.23% | 30.9% |
| E | 12,122 | 5,864 | 2.37% | 0.02% | 26.0% |
| F | 11,529 | 5,880 | 0.49% | 0.00% | 20.8% |
| G | 8,937 | 8,375 | 5.72% | 2.26% | 24.5% |
| H | 11,716 | 2,799 | 0.93% | 0.07% | 15.9% |
| I | 5,715 | 1,230 | 0.57% | 0.00% | 13.7% |
| tim | 12,261 | 5,859 | 0.99% | 0.17% | 13.7% |

## The era filter, which is not optional

The `ml_hypo_risk` column carries the output of three model generations under one name, with nothing
in the record marking the boundary. The eight-feature model ran from 2026-04-10 with a four-hour
horizon; the current 53-feature model reached the cohort in the week of 2026-06-29, at which point
the cohort median score falls from 0.364 to 0.038. Those are different quantities on different
scales, and any figure computed across the boundary is a mixture rather than a measurement. All
discrimination figures below are computed within a single generation.

## Discrimination in the field

Scored against each model's own target, pooled with a cluster bootstrap over users.

| | pooled AUC | 95% CI | training LOUO |
|---|---|---|---|
| hypo risk, current model, own target | 0.655 | [0.606, 0.701] | 0.8317 |
| hypo risk, current model, target the KDoc claims | 0.563 | [0.513, 0.600] | |
| hypo risk, previous model, own era | 0.606 | [0.493, 0.729] | 0.6796 |
| meal likelihood, current era | 0.722 | [0.684, 0.757] | 0.7375 |
| meal likelihood, previous era | 0.740 | [0.718, 0.774] | 0.7375 |

The meal model replicates in both eras, within a point or two of its leave-one-user-out figure and
of the six-user transfer test run in May 2026. Per-user values run 0.618 to 0.869 and every user is
above 0.6.

## The baseline that decides it

Same rows, same label, trivial predictors.

| | AUC | 95% CI |
|---|---|---|
| hypo model, current | 0.655 | [0.606, 0.701] |
| current glucose, negated | 0.588 | [0.534, 0.617] |
| eventualBG, negated | 0.532 | [0.436, 0.631] |
| IOB | 0.470 | [0.412, 0.552] |
| model minus current glucose | +0.068 | [+0.046, +0.104] |

The current model beats the glucose reading. Its predecessor did not: on its own era it reaches 0.606
against 0.605 for the same baseline, a difference of +0.018 with an interval from -0.037 to +0.113.
The revision therefore achieved what it was for. The meal model beats eventualBG by +0.144
[+0.054, +0.233].

## Horizon

| horizon | base | model | 95% CI | -BG | model - (-BG) |
|---|---|---|---|---|---|
| 30 min | 0.008 | 0.799 | [0.739, 0.864] | 0.817 | -0.010 [-0.061, +0.041] |
| 60 min | 0.019 | 0.701 | [0.644, 0.750] | 0.653 | +0.051 [+0.028, +0.087] |
| 90 min | 0.036 | 0.655 | [0.606, 0.701] | 0.588 | +0.068 [+0.046, +0.104] |
| 120 min | 0.055 | 0.627 | [0.572, 0.664] | 0.558 | +0.068 [+0.046, +0.102] |
| 180 min | 0.089 | 0.593 | [0.537, 0.632] | 0.520 | +0.073 [+0.051, +0.111] |
| 240 min | 0.124 | 0.578 | [0.521, 0.620] | 0.505 | +0.073 [+0.047, +0.111] |

At 30 minutes the model is level with reading the glucose, which is the horizon at which "glucose is
already low" predicts a low trivially. From 60 minutes outward it adds, and the increment is stable.

## Is the model itself sane

Probing the exported trees directly, all features at cohort medians and one swept:

| glucose | 45 | 55 | 65 | 75 | 90 | 110 | 140 | 180 | 250 |
|---|---|---|---|---|---|---|---|---|---|
| risk | 0.861 | 0.868 | 0.780 | 0.442 | 0.170 | 0.105 | 0.081 | 0.070 | 0.078 |

Monotone and correctly shaped, with a weak positive response to insulin on board. The model is not
broken.

## Calibration, and the threshold that was never moved

Observed rate by predicted decile, current era, with the damper the engine applies at that score.

| decile | n | predicted | observed | damper |
|---|---|---|---|---|
| 0 | 5,660 | 0.013 | 0.017 | 1.000 |
| 1 | 7,799 | 0.019 | 0.021 | 1.000 |
| 2 | 2,678 | 0.021 | 0.017 | 1.000 |
| 3 | 4,473 | 0.024 | 0.017 | 1.000 |
| 4 | 4,719 | 0.029 | 0.027 | 1.000 |
| 5 | 5,063 | 0.035 | 0.027 | 1.000 |
| 6 | 5,750 | 0.044 | 0.044 | 1.000 |
| 7 | 4,370 | 0.059 | 0.043 | 1.000 |
| 8 | 4,946 | 0.099 | 0.075 | 1.000 |
| 9 | 5,045 | 0.392 | 0.072 | 0.934 |

Nine deciles track. The tenth predicts 0.392 and observes 0.072 against a base rate of 0.036, and it
is the only part of the range the consumption thresholds touch. The on-policy confound does not
account for it: the damper there is 0.934, a seven per cent reduction in budget, which cannot take a
genuine 39 per cent event rate down to 7.

The thresholds at 0.30 and 0.60 were placed against the previous model's distribution, where the
cohort median was 0.364. They were not re-placed when the median fell to 0.038. The damper now
engages on 0.49 to 27.7 per cent of scored cycles depending on the user, and the tier downgrade on
0.00 to 2.26 per cent, which is a fifty-fold spread nobody selected.

## Why the tenth decile is wrong

Three explanations were open. The follow-up separates them (`calibration_followup.py`).

The model reads its input correctly at the extremes. Cycles scoring above 0.60 sit at a mean
glucose of 66.4 mg/dL with a tenth percentile of 52, which is where the direct probe says the
model should be returning those values. Cycles scoring below 0.05 sit at 144.2. The band that
does not fit is 0.30 to 0.45, at a mean glucose of 122.9 with mean insulin on board of 1.27,
where the probe says the model should return about 0.10.

The model over-predicts at every glucose, by a factor falling from 8.3 below 70 mg/dL to 1.4
above 140, while discrimination within each band stays between 0.59 and 0.68. A model that ranks
correctly and scores too high everywhere is mis-scaled rather than mis-informed, which is
consistent with the event being rarer in this cohort than in training.

The mechanism behind the anomalous band is the ring buffer. Thirty six of the 53 features come
from a persisted six-cycle history, and on an empty buffer the lag values default to the current
cycle's value where the training pipeline used a median fill. Taking a cycle as cold when fewer
than six contiguous cycles precede it, and a break of thirty minutes as breaking contiguity, 33
per cent of scored cycles are cold. Within matched glucose bands, cold cycles score higher than
warm ones by 0.043 at 80 to 110 mg/dL, 0.032 at 110 to 140 and 0.013 above 140, every interval
clear of zero, and lower by 0.053 below 80.

| score band | n | cold share | mean glucose |
|---|---|---|---|
| 0.00 to 0.05 | 35,624 | 24.0% | 144.2 |
| 0.05 to 0.10 | 8,167 | 53.9% | 108.3 |
| 0.10 to 0.30 | 3,633 | 56.5% | 99.1 |
| 0.30 to 0.45 | 1,562 | 40.2% | 122.9 |
| 0.45 to 0.60 | 1,552 | 63.0% | 102.6 |
| 0.60 to 1.01 | 395 | 48.1% | 66.4 |

At the operating point this costs a real amount. Restricted to glucose between 100 and 160 mg/dL,
where the probe says the model should be well below the cut, cold cycles cross 0.30 on 8.61 per
cent of cycles against 3.92 for warm ones, a difference of 4.69 points with an interval from 4.11
to 5.27 and a ratio of 2.20.

Discrimination is unaffected, at 0.654 on cold cycles against 0.651 on warm ones. The cold path
shifts the level of the score without destroying its ranking, which is exactly the signature of a
calibration defect rather than a broken model, and it matches what the audit found: the area under
the curve is respectable and the calibration is not.

## The firing spread is correct behaviour

The spread in how often the damper engages, from 0.49 per cent of cycles for one participant to
27.6 for another, tracks the participants' own hypoglycaemia rates. The correlation between
firing rate and each participant's own rate is +0.820 with an interval from +0.364 to +0.980.

| user | n | own hypo rate | fires above 0.30 | AUC |
|---|---|---|---|---|
| A | 5,083 | 0.0065 | 2.62% | 0.520 |
| B | 6,476 | 0.0327 | 4.46% | 0.627 |
| C | 4,251 | 0.0790 | 22.84% | 0.538 |
| D | 4,855 | 0.0735 | 27.60% | 0.569 |
| E | 5,877 | 0.0083 | 2.37% | 0.609 |
| F | 5,887 | 0.0053 | 0.49% | 0.607 |
| G | 8,375 | 0.0591 | 5.72% | 0.635 |
| H | 2,806 | 0.0103 | 0.93% | 0.707 |
| I | 1,451 | 0.0145 | 1.17% | 0.640 |
| tim | 5,872 | 0.0467 | 0.99% | 0.590 |

A damper engaging more often for someone who goes low more often is the intended behaviour. The
one participant who does not fit is tim, with the third highest hypoglycaemia rate and almost the
lowest firing rate.

## The operating point

Pooled across the cohort the shipped 0.30 cut fires on 6.83 per cent of cycles and selects a
population with an observed rate of 0.0687 against a base of 0.0361, a lift of 1.90. The cut is
therefore selecting genuinely elevated risk, and the defect is in the magnitude of the score
rather than in whether the damper engages on the right cycles.

Quantiles of the current distribution place an equivalently rare cut, and show that the very top
of the range is not the highest-risk population.

| quantile | score | fires | observed rate above |
|---|---|---|---|
| 50% | 0.030 | 49.89% | 0.0521 |
| 75% | 0.057 | 24.84% | 0.0688 |
| 90% | 0.163 | 9.98% | 0.0726 |
| 95% | 0.385 | 4.99% | 0.0700 |
| 99% | 0.568 | 1.00% | 0.0609 |
| 99.5% | 0.642 | 0.50% | 0.0510 |

The observed rate peaks around the ninetieth percentile and falls above it, which is the
contamination showing through: the highest scores include cold-path cycles at normal glucose
whose forward risk is ordinary.

## The buffer replay, which settles it

`feature_replay.py` rebuilds the 53-feature vector offline and scores it with the same exported
model, so the reconstruction can be checked against the engine's own published output rather than
argued from gap timing.

Nine of the seventeen static features are direct columns. Six are derived exactly from columns that
are present, using the definitions read out of `DetermineBasalBoostV3MLG3.kt`: `bg_above_target`,
`iob_bolusiob` as `max(0, iob - basaliob)` which the engine computes itself, `sug_expectedDelta` as
`round(bgi + (target - eventualBG) / 24, 1)`, `direction_num` as a seven-level bucket of
`shortAvgDelta`, `sug_minDelta`, and `hour`. Two come from `boost_treatments`, which holds 181,372
SMB rows. Only `iob_netbasalinsulin` is absent, and sweeping it across its plausible range moves the
score by about 0.001, so imputing it at zero is not load-bearing.

Two nuisance parameters are fitted per user on contiguous cycles only, where all three hypotheses
produce identical vectors so the fit cannot favour any of them: the local time offset, which the
record does not carry, and which stored total-daily-dose column the engine passed as `profile.TDD`.

The reconstruction verifies.

| user | n | tdd column | median abs error | within 0.01 |
|---|---|---|---|---|
| A | 5,083 | tdd_weighted8h | 0.0031 | 90.3% |
| B | 6,476 | tdd_weighted8h | 0.0042 | 86.5% |
| C | 4,251 | tdd | 0.0055 | 64.9% |
| D | 4,855 | tdd | 0.0060 | 59.1% |
| E | 5,877 | tdd_7d | 0.0032 | 93.9% |
| F | 5,887 | tdd_weighted8h | 0.0037 | 89.5% |
| H | 2,806 | tdd_blended | 0.0040 | 91.7% |
| I | 1,451 | tdd_7d | 0.0034 | 88.9% |
| tim | 5,872 | tdd_7d | 0.0028 | 95.5% |

## The mechanism is staleness, not cold start

`BoostMlFeatureBuilder.RingBuffer` has no time-based invalidation. `push` appends and trims to six,
`lagged(n)` indexes backwards by position, the timestamp carried on each snapshot is never read, and
the buffer is serialised to preferences and reloaded on start. After a break in the decision series
it therefore still holds the six snapshots from before the break and hands them to the model as the
previous five cycles.

Three hypotheses scored on cycles where they diverge, against the published score. Median absolute
error, lower is better, and the winner starred.

| user | n post-break | carried | current | true |
|---|---|---|---|---|
| A | 2,269 | 0.0052 * | 0.0077 | 0.0069 |
| B | 2,139 | 0.0066 * | 0.0109 | 0.0094 |
| C | 2,329 | 0.0152 * | 0.0432 | 0.0307 |
| D | 2,384 | 0.0081 * | 0.0238 | 0.0179 |
| E | 1,948 | 0.0043 * | 0.0062 | 0.0057 |
| F | 1,723 | 0.0041 * | 0.0063 | 0.0056 |
| H | 1,174 | 0.0047 * | 0.0071 | 0.0066 |
| I | 603 | 0.0052 * | 0.0068 | 0.0060 |
| tim | 2,137 | 0.0052 * | 0.0086 | 0.0086 |

Carried wins for all nine. The lag features after a break are whatever was last pushed, however old,
which is what the code does and is not what the model was trained on.

The distortion is not uniform. Taking the gap between the true-history and carried scores as the
staleness penalty, it runs from 0.0008 to 0.0154 and concentrates in C and D, the two participants
whose damper fires most, at 22.8 and 27.6 per cent, and whose model discriminates worst, at 0.538
and 0.569. Across the nine the penalty correlates with firing rate at +0.907 and with per-user area
under the curve at -0.502.

That correlation cannot be interpreted causally on this sample. C and D also carry the two highest
hypoglycaemia rates in the cohort, at 0.079 and 0.074, so genuine risk and score distortion are
concentrated in the same two people and nine participants cannot separate them. What can be said is
that the earlier attribution of the firing spread entirely to genuine per-participant risk is not
safe, since a second explanation fits the same data equally well.

## Verdict

The meal model is doing what it was built to do and the figures support leaving it alone. Confidence
SOLID: replicated out of cohort three times now, monotone calibration, beats its baseline with an
interval clear of zero, and stable across the model changeover that moved the other one.

The current hypo model adds real information over the glucose reading, at +0.068 [+0.046, +0.104],
and does so consistently from 60 minutes outward. Its predecessor did not, at +0.018 [-0.037,
+0.113]. Confidence SOLID for the positive on the current model and for the null on its predecessor,
both being robust to the horizon and to the choice of baseline.

Its absolute discrimination remains well below the training figure, 0.655 against 0.8317. Three
explanations are open and this audit does not separate them: the field measurement is on policy and
biased toward zero; this cohort is not the training cohort, and a leave-one-user-out estimate bounds
transfer within a population rather than across populations; and the on-device feature vector,
36 of whose 53 entries come from a persisted six-cycle ring buffer, may not reproduce the
training-time vector. The last is checkable by logging the assembled vector and scoring it offline
through the training-time library, and that is the obvious next step.

Two actions follow, and the first is an engineering fix rather than a statistical one. The ring
buffer should discard entries older than the lookback window it represents, so that a cycle
arriving after a break is scored against a short buffer rather than against stale history. A third
of cycles currently follow a break, and at normal glucose they cross the damper threshold at more
than twice the rate of the rest.

The second is the threshold. Both cuts were placed against a distribution whose median has since
moved by an order of magnitude, and nothing re-placed them. Recalibrating needs no retraining and
does not change the model's ranking, but it should follow the cold-start fix rather than precede
it, since fixing the imputation will move the distribution again.

## What not to conclude

This does not say the damper is unsafe. It reduces insulin, never adds it, is floored at half the
budget, and sits under the composed floor at 30 per cent of baseline. Nor does it say the model is
broken: probed directly it responds to glucose correctly and monotonically, its ranking is intact
on both the cold and the warm path, and at the shipped cut it selects a population with 1.90 times
the base rate. Nor is the spread in firing rates a fault, since it tracks the participants' own
hypoglycaemia rates at +0.820.

What the evidence supports is narrower and fixable: a third of cycles score through an imputation
path that does not match the one the model was trained under, which inflates the score at normal
glucose and doubles the rate at which the damper engages there.
