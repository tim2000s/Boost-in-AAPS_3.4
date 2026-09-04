# The shadow layers, and what each has delivered

Boost carries thirteen shadow components. Each computes what it would have done and logs it without
touching a dose, which is the mechanism by which anything reaches the dose path here. A shadow that
is never scored is telemetry cost with no decision attached, and several have been running for
months without a verdict.

This is that verdict, taken on 2026-09-04 against the outcome each shadow claims to anticipate,
with the participant as the resampling unit.

## Summary

| Shadow | Cycles | Participants | Verdict |
|---|---|---|---|
| Accelerating-meal trigger | 154,379 | 11 | Useful. 2.07x lift, fires on 8.8 per cent of cycles |
| KAIROS twin forecast | 146,459 | 11 | Real but small. 1.08 mg/dL better than assuming no change |
| Hypoglycaemia refit (v13) | 611 | 1 | Promising, needs the cohort |
| V7 substrate | 115,976 | 11 | Calibration measured, sizer not yet priced |
| Activity load | 305,297 | 13 | Priced at roughly break-even, unchanged |
| Consequence prior | 7,914 | 1 | Loses to reading the current glucose |
| Anticipation | 159,197 | 11 | Discarded, lost to the hour of day |
| Insulin sensitivity shadow | 332,338 | 9 | Running since February, never scored |
| Anticipatory backout | 137,045 | 11 | Never scored |
| Plateau | 155,418 | 11 | Never scored |
| Tranche | 4,785 | 1 | Never scored |
| Fall consequence | 0 | 0 | Faulty, diagnostic build pending |
| Volume-weighted total daily dose | 0 | 0 | Declared but never populated |

## The one that works

The accelerating-meal trigger fires on 8.8 per cent of cycles. Of those, 40.6 per cent are followed
by a rise of at least 30 mg/dL (1.7 mmol/L) within 45 minutes, against a base rate of 19.6 per cent across all
cycles: a lift of 2.07 measured on 154,379 cycles from eleven participants. For a detector whose job
is to notice a meal starting without anyone announcing it, that is a usable signal at a usable
firing rate, and it is the strongest result any shadow here has produced.

## The one that is real but small

The KAIROS twin is a physiological ensemble forecaster and its 30-minute prediction was compared
against the engine's own eventualBG, where it looked decisive: a median absolute error of 13.7
mg/dL against 31.3. That comparison is not fair. eventualBG projects where glucose settles once
insulin has finished acting, which is a different question from where glucose will be in half an
hour, and scoring it against a 30-minute outcome measures the mismatch rather than the model.

Against baselines that answer the same question the result is much smaller:

| Predictor | Median absolute error | Mean | RMSE |
|---|---|---|---|
| KAIROS twin | 13.7 | 19.2 | 26.7 |
| Persistence, glucose stays where it is | 13.7 | 20.3 | 28.6 |
| Linear extrapolation from delta | 16.4 | 24.4 | 35.0 |
| Engine eventualBG | 31.3 | 50.6 | 80.2 |

The twin beats persistence by 1.08 mg/dL of mean absolute error (95 per cent interval 1.48 to 0.64
better), which is distinguishable from zero and better for nine of eleven participants. It is also
about one twentieth of the error itself. A forecaster of this construction should be doing more than
that, and the useful thing the comparison reveals is how strong persistence is at thirty minutes.

## The one that loses to a simpler answer

The consequence prior estimates whether a rise now under way ends above 180 mg/dL (10.0 mmol/L) within two hours.
On 7,914 cycles from one participant it reaches 0.730, against 0.667 for glucose at the onset. But
the current glucose reading alone reaches 0.785. The shadow is worse than the number the controller
already has, and on this evidence it should be discarded rather than developed.

## The two producing nothing

The fall-consequence shadow has scored no cycle in two days of running, where its own onset rule
qualifies about 6.8 times a day on this participant. The cause is that every rejection in its path
returned a bare null, so a model that failed to load and an uneventful trace were indistinguishable
from outside. A build that reports which test rejected each cycle is waiting to be flashed.

The volume-weighted total daily dose shadow has produced no rows at all, on any participant, despite
eight columns declared for it in the decision table. It is either not wired or not reaching the
extractor, and until that is established the columns are misleading.

## The four never scored

The insulin sensitivity shadow has been running since February and has 332,338 rows across nine
participants. The anticipatory backout has 137,045 across eleven, the plateau detector 155,418, and
the tranche controller 4,785 on one. None has been scored against an outcome.

That is the finding this audit is really for. Thirteen shadow components produce telemetry on every
cycle; four have never been asked whether they work, two produce nothing, and one has been running
long enough to be discarded on evidence that was already available.
