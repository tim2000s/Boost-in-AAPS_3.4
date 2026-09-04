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
| Insulin sensitivity shadow | 355,482 | 13 | Scored: at chance, and worse than the engine's own ratio |
| Anticipatory backout | 136,529 | 11 | Scored: lift 1.11x, no usable signal |
| Plateau | 37,080 | 11 | Scored: flags highs that are already resolving, lift 0.85x |
| Tranche | 4,785 | 1 | Too thin to score, needs the cohort |
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

## The four that had never been asked

All four have now been scored. Three can be discarded and the fourth cannot yet be judged.

The insulin sensitivity shadow computes an alternative sensitivity ratio on every cycle and has done
since February. Its output was never extracted, because no column existed for it, so 355,482 cycles
of it sat unparsed in the console text the app already uploads. Recovered and scored against
sustained hypoglycaemia within four hours, it reaches an area under the curve of 0.5002, which is
chance, against 0.5151 for the sensitivity the engine actually applied. It is worse than the engine
for eight of the nine participants where both can be computed. Seven months of running has produced
a component that does not beat what it was proposed to replace.

Recovering it turned up a data-quality problem worth naming. The app formats these debug numbers
with the device's locale, so a participant on a European locale writes `raw=0,890` where an English
one writes `raw=0.890`. A pattern matching digits and full stops stops at the comma and silently
reads zero, which is what a first pass did on 61 per cent of rows and which produced a plausible
looking median of 0.000. Any parse of these console lines has to accept both separators.

The anticipatory backout arms on 23,000 of 136,529 cycles. Cycles where it is armed are followed by
a fall of at least 30 mg/dL within the hour 26.4 per cent of the time against a base rate of 23.8,
a lift of 1.11, with a per-participant median of 1.07 and a range from 0.69 to 1.41. For a component
whose purpose is to anticipate a fall, that is not a signal.

The plateau rule selects glucose between 145 and 250 mg/dL (8.1 to 13.9 mmol/L) with insulin on
board above 0.5 U and a trend that is neither rising nor falling fast, then applies a safety floor.
Its claim is that such a high is stuck and will not come down on its own.

Nothing here can measure whether nudging one would help. The shadow delivers nothing, so that is a
counterfactual and there is no glucodynamic simulator to produce it. What is measurable is whether
the rule picks out the cycles it says it picks out, and a detector that selects the wrong cycles
cannot be useful whatever the action would do.

Within its own window, 37,080 cycles across eleven participants, a third fail to come down by even
10 mg/dL in the following hour. The cycles the rule flags are stalled 28.8 per cent of the time
against that base rate of 33.7, a lift of 0.85, and they fall by a median of 28.8 mg/dL against 26.3
for the window as a whole.

So the highs it flags come down slightly better than the ones it does not. It is not finding stalled
highs; it is finding highs that are already resolving, which is the population this programme has
repeatedly documented as the wrong one to add insulin to.

Two things had to be read before this measured anything. The tag's first field is whether the safety
floor permitted a nudge rather than whether a plateau was detected. And the comparison group has to
be the rule's own window rather than every cycle above 140 mg/dL (7.8 mmol/L), because comparing against
everything above 140 mixes in the fast risers and fast fallers the rule excludes by construction and
reports its selection rather than its detection.

The tranche controller has 4,785 cycles on one participant, which is too thin for a verdict either
way. It needs the cohort.

## The three producing nothing

The fall-consequence shadow scores no cycle because every rejection in its path returned a bare
null. A build that reports which test rejected each cycle is waiting to be flashed.

The volume-weighted total daily dose shadow produces nothing anywhere: no rows in the decision
table, no fields in the Nightscout payload, and no trace in the console text on any participant.
Its `compute()` returns null on every cycle. Eight columns are declared for it and all are empty.

Both of those, and the insulin sensitivity shadow, sit inside the `useTdd` branch, so they stop
entirely for anyone who turns off total-daily-dose-driven sensitivity. That is one participant
today and it is worth knowing before a shadow's silence is read as a quiet period.

## The position

Of thirteen shadow components, one is earning its place, one is real and clinically negligible, five
can be discarded on evidence, one cannot yet be judged, three produce nothing, and two are the
recent models that have not run long enough. The programme's discipline about not letting anything
reach the dose path until it is measured has held. What has not held is the other half of the same
discipline, which is measuring it and then acting.
