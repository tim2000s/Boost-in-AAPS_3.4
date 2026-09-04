# One-minute continuous glucose data in a closed loop: where the extra samples help, where they do not, and why

*[Author name(s) and affiliation to be added. Prepared from an anonymised single-user
analysis; the code and data-processing steps are open and reproducible.]*

## Abstract

Background. Continuous glucose monitors have historically reported every five minutes, and
the control algorithms built on them inherited that cadence in their arithmetic and in
their timing constants. Sensors reporting every minute are now in ordinary use. It is
widely assumed that more frequent data is straightforwardly better, giving a loop earlier
sight of what glucose is doing. Whether that assumption survives contact with the data has
not, to our knowledge, been measured on a deployed algorithm.

Methods. We took 83,550 continuous glucose readings collected over 66 days from a person
running an open-source automated insulin delivery system on a one-minute sensor, together
with data from eight users of the same system on five-minute sensors. We reimplemented the
algorithm's glucose front end, the bucketing and delta calculation, and verified it against
the shipped implementation. We then asked four questions of the same underlying glucose,
viewed at both cadences: whether the derived rate signals differ, whether the extra samples
predict the end of a carbohydrate rise, whether they predict imminent hypoglycaemia, and
whether they detect a fast fall sooner. Effect sizes carry block-bootstrap confidence
intervals and an explicit verdict.

Results. The one-minute record is not noise. During a climb, 85 per cent of consecutive
non-zero changes agree in sign, and the lag-one autocorrelation of the change series is
0.724. It is, however, quantisation-limited: the sensor reports whole numbers, 33.9 per cent
of minutes show no change at all, and the ratio of trend to residual is 0.58 at one minute
against 0.79 at five. The derived rate signals are indistinguishable between cadences, which
follows from the arithmetic rather than from luck. One-minute data carried no information
about when a rise would end, with an area under the curve of 0.482 against 0.487 for the
five-minute view, and it added 0.001 to the prediction of hypoglycaemia within thirty
minutes, against a five-minute baseline of 0.962. It did detect a five milligram per
decilitre fall a median of three minutes sooner, on 89 per cent of 5,961 sharp falls. We
also found two places where a window expressed as a count of samples silently changed
meaning at the higher cadence, one of them disabling a safety feature.

Conclusion. Faster sensing does not make a loop see a meal sooner, because the quantity a
loop needs at meal onset is smaller than the sensor's own resolution. It does make a loop
see a fall sooner, because a fall is large. The practical consequence is that cadence
belongs in the units of every window in a controller, and that the benefit of faster
sensing accrues to withholding insulin rather than to giving it.

## 1. Introduction

The five-minute reporting interval of continuous glucose monitors is a historical artefact
of the first commercially successful devices, and it became an implicit assumption in the
algorithms built on top of them. Rate of change is expressed per five minutes.
Look-back windows are counted in samples. State machines advance once per loop invocation,
and a loop invocation is triggered by the arrival of a reading. None of this was wrong when
every sensor behaved the same way.

Sensors reporting every minute are now in ordinary use, and a person switching to one
changes several things at once from the algorithm's point of view. The loop runs five times
as often. Windows counted in samples become five times shorter in wall-clock terms. State
machines age five times faster. Whether any of that is beneficial, harmful or simply
different is an empirical question, and the answer bears on a growing number of users.

The intuition in the community is that more data is better, and specifically that a faster
sensor should let a controller respond to a meal sooner. That intuition has a plausible
mechanism behind it. If the sensor tells you every minute rather than every five, you learn
that glucose has started to rise up to four minutes earlier, and in a system where insulin
takes an hour to act, four minutes of head start is not nothing.

We had the opportunity to test this directly. One member of a small cohort running an
open-source automated insulin delivery system moved to a one-minute sensor while the rest
of the cohort remained on five-minute sensors, and the same person's own record spans the
change. That gives both a between-user contrast and, more usefully, a within-user one. This
paper reports what we found, including the results that contradicted our own expectations.

## 2. The theoretical gain from faster sensing

A faster sensor might help by several mechanisms. They are different from one another and they
fail differently.

The first is latency. If a controller acts on the arrival of new information, then
information arriving more often reaches it sooner. This is a pure timing benefit and it
requires nothing of the data beyond its existing this-is-the-glucose content.

The second is precision. Averaging more samples over the same window reduces the variance
of an estimate. A rate of change computed from fifteen one-minute samples should be a
cleaner estimate than one computed from three five-minute samples, and a cleaner estimate
of the rate should support an earlier or more confident decision.

The third is structure. Some features of a glucose trajectory may simply be invisible at
five-minute resolution, in the way that a brief artefact or a sharp inflection can fall
between samples. If such features exist and matter, only a faster sensor can see them.

These are separable, and our results separate them. The first mechanism turns out to be
real but confined to large changes. The second is real but works against the naive
expectation, because the quantity being averaged is dominated by quantisation rather than
by measurement noise. The third we found no evidence for at all.

## 3. Methods

### 3.1 Data

The one-minute record comes from a single person, referred to throughout as the index user,
running the Boost variant of AndroidAPS. Their sensor cadence changed on 23 May 2026, and we
analyse the 83,550 readings across the 66 complete days that follow. The five-minute
comparison group is eight users of the same software, whose median interval between loop
cycles is between 4.80 and 4.91 minutes against the index user's 1.00 minutes.

All glucose values are in milligrams per decilitre. Data were drawn from a local research
database populated from the users' own Nightscout instances. No dosing outcome is analysed
anywhere in this paper, for reasons set out in Section 8.

We note at the outset that the index user's sensor hardware changed at the same time as
their cadence, so any within-user comparison across that date confounds the two. We use the
within-user contrast only where the confound does not bear on the conclusion, and we say so
where it does.

### 3.2 Reproducing the front end

The algorithm does not act on raw readings. It first assigns them to a five-minute grid, a
process the code calls bucketing, and computes rate signals from the bucketed series over
fixed windows: a last-delta window spanning 2.5 to 7.5 minutes, a short-average window
spanning 2.5 to 17.5 minutes, and a long-average window spanning 17.5 to 42.5 minutes. Each
contributing sample is normalised by its own age, so all three are expressed per five
minutes regardless of the interval at which the data arrived.

We reimplemented this front end and verified it against the shipped implementation across
fifteen whole-day traces drawn from the index user at both cadences and from two five-minute
reference users. The reimplementation reproduced the shipped output with no timestamp or
value mismatches. A subsequent vectorised form was checked against the reference
implementation on two hundred randomly chosen cycles and agreed on all of them. We report
this because every result in Sections 4 to 6 depends on the front end being faithful, and an
unverified reimplementation would make the whole exercise worthless.

One property of the implementation deserves separate mention, because it is load-bearing and
undocumented. The grid on which readings are bucketed is anchored to a reference time, and
the intent recorded in the source is that this anchor persists between cycles, giving a
fixed grid. It does not persist. The object holding it is copied on every autosens
calculation, and the copy does not carry the anchor, so the grid re-anchors to the newest
reading on every cycle. At five-minute cadence this is invisible. At one-minute cadence it
is the difference between a working system and a broken one: with a persistent grid, a
one-minute user's readings would collapse into 288 fixed buckets a day and four cycles in
five would re-evaluate glucose the algorithm had already seen. The field data confirms the
behaviour. The median interval between changes in the algorithm's reported glucose is
between 5.00 and 5.08 minutes for every five-minute user and between 1.08 and 1.12 minutes
for the index user. Anyone repairing the copy to match its documented intent would silently
degrade every one-minute user.

### 3.3 Analyses and verdicts

Four analyses are reported. Signal characterisation examines the distribution,
autocorrelation and sign behaviour of one-minute changes, and decomposes their variance into
a local trend and a residual. Signal equivalence recomputes the three rate signals and the
acceleration ratio from the same glucose viewed at both cadences. Prediction asks whether
features derived at each cadence forecast the end of a rise, or hypoglycaemia within thirty
minutes. Detection asks how much sooner a fall of a given size becomes visible.

Uncertainty is estimated by block bootstrap with the day as the resampling unit, because
one-minute glucose is heavily autocorrelated within a day and a per-observation interval
would be far too narrow. Predictive models are fitted with grouped cross-validation, again
by day, so that no day contributes to both training and evaluation. Every effect size is
reported with a 95 per cent interval and an explicit statement of whether it is
distinguishable from the null value. Where an interval overlaps the null we say the result is
unproven rather than describing it as an absence of effect.

## 4. The signal: coherent in sign, quantised in magnitude

The first question is what a one-minute change actually is. If consecutive changes alternate
in sign, the record is dominated by measurement noise and nothing built on it will work. If
they agree, there is structure to exploit.

They agree. Among consecutive non-zero one-minute changes, the proportion that reverse sign
is 15.2 per cent while glucose is climbing at three or more milligrams per decilitre per five
minutes, and 10.0 per cent while it is climbing at eight or more. Independent noise would
give about 50 per cent. The lag-one autocorrelation of the change series is 0.724, decaying
to 0.086 by lag five. During a climb, the one-minute record is strongly coherent.

The picture inverts when glucose is flat. There the sign-reversal rate is 64.5 per cent,
above the 50 per cent that independence would give, which is the signature of a quantised
measurement round-tripping about a level line rather than of a signal.

That quantisation is the limiting factor. The sensor reports whole milligrams per decilitre.
Across 80,690 consecutive one-minute pairs, 33.9 per cent show no change at all and 72.8 per
cent lie within one unit of no change. Decomposing the change into a local fifteen-minute
trend and a residual gives a trend standard deviation of 0.88 and a residual standard
deviation of 1.51, a ratio of 0.58. The same decomposition at five minutes gives 0.79. The
five-minute view of the same glucose has the better ratio of signal to noise, which is the
opposite of what the precision argument in Section 2 would predict, and the reason is that
the extra samples do not average away an independent error term. They resolve a staircase.

The arithmetic makes this concrete. A climb of three milligrams per decilitre per five
minutes is 0.6 per minute, below the sensor's step. A climb only becomes visible from one
minute to the next once it exceeds about five milligrams per decilitre per five minutes.
Most meals begin below that.

We checked whether the one-minute values are genuinely measured rather than interpolated
between five-minute anchors, since an interpolated record would carry no additional
information by construction. Reconstructing the intermediate minutes from five-minute
anchors gives a mean absolute error of 1.11 milligrams per decilitre with only 8.6 per cent
exact agreement, against 4.76 for the analogous control on a five-minute user. The values
are real. The additional information they carry is about one quantisation step, which is
below the residual standard deviation.

The summary is that a one-minute record tells you reliably that glucose is rising, and tells
you very little about how fast. That distinction turns out to explain the rest of the paper,
because a first derivative survives quantisation and a second derivative does not.

## 5. Uses with no measurable gain

### 5.1 The derived rate signals

Because bucketing places readings on a five-minute grid before any rate is computed, the
window membership of the delta calculation is fixed by construction. On an exact grid the
age of bucket k is exactly five k minutes, so the same buckets enter the same windows at
either cadence, and the normalisation reduces each term to a difference divided by k. The
arithmetic cannot depend on how often the sensor reported underneath.

Measurement agrees. Across 66 days at five decimation offsets, the median absolute values of
the last delta, the short average, the long average and the acceleration ratio are all
indistinguishable between cadences. The upper tails of the two average signals are slightly
smaller at one minute, distinguishably so, which runs opposite to the expectation that finer
sampling would produce more extreme values, and reflects buckets being interpolated at exact
offsets rather than at jittered reading times.

This is a positive result of a kind. It means the existing rate arithmetic is safe to run at
any cadence, and it removes an obvious candidate explanation for anything else we found.

### 5.2 The end of a carbohydrate rise

The most attractive hypothesis for one-minute data is that a reduction in the rate of climb
signals that a meal is finishing, and that minute-by-minute this becomes apparent sooner. If
true it would let a controller stop committing insulin earlier.

We tested it first as a threshold rule and then, properly, as a prediction. As a prediction,
the question asked at every minute inside a rise was whether the peak would arrive within
ten minutes, across 452 episodes and 22,258 pre-peak minutes with a base rate of 20.2 per
cent. Acceleration computed at one-minute resolution gave an area under the curve of 0.482,
with an interval of 0.465 to 0.500. Computed at five-minute resolution it gave 0.487, with
an interval of 0.456 to 0.517, which is unproven. A persistence feature counting consecutive
minutes of negative acceleration gave 0.510, also unproven. There is no usable signal at
either cadence, and the one-minute version is not better than the five-minute one.

The threshold form of the test explains why it looked promising at first. A detector
comparing the slope over three minutes with the slope over the preceding three minutes fires
a median of 13.0 minutes before the shipped declining-delta test. At its first firing,
however, a median of 41.0 milligrams per decilitre of climb remains, with 94.1 per cent of
episodes having ten or more still to come. It fires in the middle of a rise rather than at the end of one. Sweeping the window from three to fifteen minutes and the
threshold from one to five shows the remaining climb falling monotonically as the window
lengthens, from 41.0 to 18.0. The only configuration that improves on the shipped detector
uses a longer window than the shipped detector does, and is therefore not faster.

The interpretation follows from Section 4. Acceleration is a second difference, and
differencing amplifies exactly the quantisation that the first difference survives.

### 5.3 Imminent hypoglycaemia

We asked whether features available only at one minute improve the prediction of glucose
below 70 milligrams per decilitre within thirty minutes, over 80,358 observations with a base
rate of 7.0 per cent, using grouped cross-validation by day. A model given the current
glucose and three slope estimates available to a five-minute controller achieved an area
under the curve of 0.962. Adding a three-minute slope and a one-minute acceleration term
raised it to 0.963, a difference of 0.001 with an interval that excludes zero.

We report that as no gain rather than as a positive finding. The interval is tight because
the two models share four of six features, so the bootstrap is resampling a nearly
deterministic difference, and a thousandth of an area under the curve has no operational
meaning. The five-minute view already reaches 0.962 on its own, which is the more useful
observation.

## 6. Fast falls, the one case with a gain

The one place the latency mechanism of Section 2 survives is where the change is large
relative to the sensor's step. Across 5,961 events in which glucose fell by 25 or more
milligrams per decilitre within twenty minutes, a fall of five milligrams per decilitre
became visible a median of 3.0 minutes sooner at one-minute cadence, and sooner on 89 per
cent of events.

This is consistent with everything in Section 4. A fall of that speed is well above the
quantisation floor, so it is visible from minute to minute in a way that the onset of a meal
is not. It is also the direction in which earlier information is most useful, since the
response to a fall is to withhold insulin, and withholding is reversible in a way that
delivering is not.

## 7. Two windows that change meaning with cadence

Separately from the question of benefit, the analysis surfaced two places where a window
expressed as a count of samples silently changes duration with cadence. Both are in code
whose comments state the intended duration in minutes, which is how the discrepancy escaped
notice.

The first is the state machine that tracks a suspected meal. Its ages are counts of loop
invocations, and the thresholds were tuned against a five-minute loop. Measured on live
data, the interval from entering the observing state to reaching the age threshold is 10.0
minutes for every one of the eight five-minute users, with a tenth percentile between 9.7
and 10.0, and 2.0 minutes for the index user. The hysteresis that the design intends is
substantially absent at the higher cadence. We note that this measurement also corrected our
own earlier reading of the source, which implied fifteen minutes rather than ten.

The second is the baseline window of the sensor-artefact damper, which suppresses the
algorithm's response to the abrupt drops characteristic of a compressed sensor. Its baseline
is the maximum of the last five readings, described in the source as approximately
twenty-five minutes, which holds only at five-minute cadence. At one minute it is five
minutes, and a drop of thirty milligrams per decilitre from a five-minute baseline is a
condition glucose rarely meets. Evaluating the shipped rule on the same glucose gives 10
firings at one-minute cadence against 138 at five-minute cadence, and 636 when the window is
expressed as twenty-five minutes. The damper was approximately 98 per cent suppressed for
the user whose cadence would have benefited most from it.

Both are corrected by expressing the window in time. The correction to the artefact damper
is a sensing change with no dosing effect. The correction to the state machine changes dosing
behaviour for one-minute users, restoring the timing the constants were calibrated for, and
we treat it as a change requiring prospective evaluation rather than as a bug fix, for the
reasons in Section 8.

## 8. Limitations

The one-minute arm is a single person. This is a statement about a mechanism, quantisation
against the size of the quantity being measured, exercised on one person's glucose, and it
is not a user comparison. The five-minute users differ from the index user in sensor, pump,
physiology and behaviour, and none of the between-user contrasts should be read as
controlled.

The index user's sensor hardware changed on the same date as their cadence. A within-user
comparison across that date therefore confounds the two, and we have restricted the
within-user contrasts to questions where the confound does not bear on the answer.

Most of the analysis is a faithful simulation of the algorithm's front end over real
one-minute glucose rather than an observation of the algorithm running at one minute. Only
about 2.2 days of the index user's record has both a one-minute sensor and a one-minute loop.
The entry into the observing state is approximated from glucose alone, because the true
transition depends on carbohydrate and model inputs not present in the glucose record, so
all episode-level figures should be read as provisional.

The analysis measures detection and timing. It does not measure dosing outcomes, and it
cannot, because there is no counterfactual glucose trajectory for a controller that behaved
differently. Nothing here establishes that any of the changes discussed would improve
glycaemic control, only that the algorithm's timing and detection would behave as designed
rather than as an accident of cadence.

Finally, one important behaviour, the re-anchoring grid described in Section 3.2, is
undocumented and contradicts the stated intent of the code it lives in. Our results describe
the system as it actually behaves. They would not hold for a system in which that behaviour
were corrected to match its documentation.

## 9. Conclusion

Faster sensing does not do what the community intuition expects it to do. It does not let a
loop see a meal sooner, because the quantity that matters at meal onset, the change in
glucose over one minute, is smaller than the sensor's own resolution. It does not improve
the estimate of how fast glucose is changing, because the extra samples resolve a staircase
rather than average away an independent error. It carries no information about when a rise
will end, at either cadence, because that requires a second derivative and the second
derivative is where quantisation dominates.

It does let a loop see a fast fall about three minutes sooner, because a fast fall is large
enough to clear the sensor's resolution from one minute to the next. That is a real benefit,
and it accrues to the side of the decision where acting early is safest.

The more general lesson concerns how controllers are written rather than how sensors report.
Two of the windows in this system are expressed as counts of samples with their intended
durations recorded only in comments, and both silently changed meaning when the cadence
changed, one of them disabling a safety feature for precisely the users it would have helped
most. Any window in a control algorithm that means a duration should be written as a
duration. That costs nothing at five minutes and it is the difference between working and
not at one.

## References

[1] Kovatchev BP, Breton M, Dalla Man C, Cobelli C. In silico preclinical trials: a proof of
concept in closed-loop control of type 1 diabetes. J Diabetes Sci Technol. 2009.

[2] Facchinetti A, Sparacino G, Cobelli C. Modeling the error of continuous glucose monitoring
sensor data: critical aspects discussed through simulation studies. J Diabetes Sci Technol. 2010.

[3] Bequette BW. Continuous glucose monitoring: real-time algorithms for calibration,
filtering, and alarms. J Diabetes Sci Technol. 2010.

[4] Lewis D. Automated insulin delivery: how artificial pancreas "closed loop" systems can aid
you in living with diabetes. 2019.

[5] Nightscout Foundation. The Nightscout Project. Open-source continuous glucose monitoring
in the cloud.

[6] AndroidAPS contributors. AndroidAPS documentation: the oref1 algorithm and glucose status
calculation.
