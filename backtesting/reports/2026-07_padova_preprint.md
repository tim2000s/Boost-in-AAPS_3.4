# The UVA/Padova simulator versus real-world data: the case for a new approach to closed-loop testing

*[Author name(s) and affiliation to be added. Prepared from an anonymised multi-cohort
analysis; the code and data-processing steps are open and reproducible.]*

## Abstract

Background. The UVA/Padova type 1 diabetes simulator has been accepted since 2008 as a
substitute for animal trials in the pre-clinical testing of automated insulin delivery
(AID). Control algorithms bound for regulatory approval are screened on it in place of
animal studies, and it is the standard platform for in-silico work on new controllers, so
its resemblance to real-world glucose data bears directly on which systems are judged safe.
That resemblance has seldom been measured against real-world data at scale.

Methods. We compared the open reference implementation of the simulator
(simglucose, the 2008 model, all thirty virtual personae across three age classes) with
four independent real-world AID datasets covering roughly 192 users, many with more than a
year of five-minute continuous glucose data. The four are a fully closed loop (Boost), an
iAPS/Trio cohort, the OpenAPS/oref0 cohort from the OpenAPS Data Commons, and a
pre-dynamic-ISF AndroidAPS cohort. Eleven statistics of glucose dynamics were computed the
same way on both sides, taken per user and then pooled with bootstrap confidence intervals.
For each statistic we asked whether any persona class reproduced it, not only the adults.

Results. The four real datasets converged closely, which let us treat their spread as a
real-world envelope. The simulator reproduced short-horizon autocorrelation for every
persona class and reached real-world glucose variability only through its child personae.
Five of the eleven statistics were reproduced by no persona at any age: the fat tail of
unannounced-meal rises, the speed of hypoglycaemia recovery and its rebound, sensor
compression artefacts, and high-frequency sensor noise. A sixth, week-to-week
insulin-sensitivity drift, is zero in the 2008 model by construction. We then reconstructed
the later S2013 model as closely as the open literature allows, adding its time-varying
insulin sensitivity and its glucagon counter-regulation to the personae together and
measuring the whole reconstruction. It reached the real range on none of the eleven
signatures for the adult personae. Its additions raised variability part-way without
reaching the real band, pushed the autocorrelation and diurnal amplitude, which the 2008
model had matched, out of range, and left the structural gaps untouched.

Conclusions. Testing on the open 2008 platform exercises a smooth, announced-meal,
stationary, clean-sensor regime, and it is largely blind to the unannounced meals, variable
insulin efficacy, sensor artefacts and drifting sensitivity that shape real-world safety.
We read this not as grounds to distrust simulation but as grounds to change how it is
validated and used, by reporting simulator fidelity as a measured quantity and by moving
towards simulators calibrated against the real-world data that now exists.

Keywords: type 1 diabetes; automated insulin delivery; artificial pancreas; in-silico
testing; UVA/Padova simulator; model validation; regulatory science.

## 1. Introduction

In 2008 the US Food and Drug Administration accepted the University of Virginia and
University of Padova type 1 diabetes simulator as a substitute for animal trials in the
pre-clinical testing of artificial-pancreas control algorithms [1]. The decision changed
the field. Since then very few animal experiments have been run to design an AID
controller, and the commercial systems now in clinical use, among them the Medtronic 670G
and 780G, Tandem Control-IQ, Insulet Omnipod 5, CamAPS FX and Diabeloop, were screened
in silico on this platform on their way to patients [5].

The simulator therefore sits at a decision point. A controller that looks safe in silico
earns a clinical trial, and one that looks dangerous may never be built. That gives its
behaviour real consequences, and it makes a specific question worth answering: how
faithfully does the simulator reproduce the glucose data of the people it stands in for?
The question is not whether the underlying physiology is well modelled, which is not in
doubt, but whether the particular statistics that a safety judgement turns on come out
looking like real-world data.

The question has rarely been put at scale, largely because there was no large multi-system
record of real closed-loop data to put it against. The open-source AID movement has
supplied one. People running OpenAPS, AndroidAPS, Trio and related systems have built up
years of continuous glucose and pump data, and through the OpenAPS Data Commons some of it
is openly shared [8]. With several independent datasets in hand it becomes possible to hold
the simulator against more than one real cohort at a time, and that turns out to be what
makes the comparison credible.

This paper reports that comparison and draws one conclusion from it. We show that
independent real-world AID datasets agree closely enough to serve as a target, we measure
where the open 2008 simulator meets that target and where it does not, and we
argue from the pattern of the misses that fidelity to real data should be measured rather
than assumed.

## 2. The simulator and what "tested in silico" means

The UVA/Padova simulator rests on a validated model of glucose and insulin dynamics whose
meal subsystem comes from tracer studies of glucose turnover [7]. It takes carbohydrate and
insulin as inputs and returns plasma and sensor glucose. The full commercial distribution
carries three hundred in-silico subjects; the freely distributed academic version, and the
open-source simglucose package that reimplements the 2008 model [6], carry the canonical
thirty, ten adults, ten adolescents and ten children.

That distinction sets our scope. The version we test, simglucose, is the open
reimplementation of the 2008 model and the instance of the simulator anyone can run. It is
the common tool in academic and reinforcement-learning work on glucose-control algorithms,
and it shares the model structure and the virtual population of the FDA-accepted version. It
is worth being clear about who does and does not use it. Commercial systems bound for
regulatory approval are tested on the licensed UVA/Padova simulator, so the platform gates
that pathway. The open-source AID systems whose data we use here, by contrast, are for the
most part not developed or validated against any simulator at all; they are iterated on
real-world use. That works in our favour rather than against us, because it means the
real-world data we hold the simulator against was not itself shaped by the simulator.

The simulator has been revised since 2008. The S2013 version [2] added intraday and
interday variability of insulin sensitivity fitted to clinical data, a dawn-phenomenon
model, glucagon kinetics and secretion, and better glucose kinetics in hypoglycaemia. It
was accepted by the FDA in 2013, later extended from single-meal to single-day scenarios
[3], and validated against clinical-trial traces [4]. Physical-activity effects have been
added to the model family in separate work. Section 6 measures what the two most relevant of
these revisions do and do not fix. The point here is narrower: the freely available,
openly runnable version is the 2008 model, and that is what we measure.

## 3. Methods

The comparison rests on one rule. Every statistic is computed the same way on real data and
on the simulator, with the same definitions, thresholds, cadence and aggregation, and
nothing is applied to one side but not the other. The pipeline is open and re-runnable.

### 3.1 Data

The real cohorts are anonymised AID users held in a local research database, each a
different system built by a different community:

- Boost (9 users), a fully closed loop with no meal announcement.
- Trio (29 users), the iAPS and Trio lineage.
- OpenAPS (110 users), the oref0 lineage from the OpenAPS Data Commons, several with
  multiple years of continuous data.
- AndroidAPS classic (44 users), AndroidAPS predating dynamic insulin sensitivity.

All record continuous glucose at a five-minute cadence. A user is included only if they have
at least 500 CGM readings. No trace is smoothed, trimmed or cleaned beyond dropping null
values, so the real sensor noise and its artefacts are left in.

The simulator cohort is all thirty UVA/Padova personae, each run through simglucose for
twenty-one days. Meals are randomised per day in timing and size and announced to the
controller, which is a basal-bolus controller that doses on the scenario carbohydrate using
each patient's own ratios; announcement is necessary because the simulator has no working
unannounced-meal controller. Meal sizes are scaled by body weight (reference 70 kg, clipped
to between 0.5 and 1.15 times) so that a child is not given an adult's dinner. The simulator
records glucose every three minutes, so each trace is resampled onto the same five-minute
grid as the real data before any statistic is taken, and the two sides are never compared at
different cadences. Announcing the meals works in the simulator's favour, since the announced
case is the easier one, and we do this deliberately so the comparison cannot be dismissed as
an unfair scenario.

### 3.2 Signatures

Eleven statistics were computed per user or per persona. Each is defined below so the result
can be read without the source.

- Glucose variability (CV%): 100 times the SD over the mean of the CGM.
- Rise tail: among consecutive samples 4 to 6 minutes apart, the percentage whose rise
  exceeds 10 mg/dL. A fat positive tail marks the onset of an unannounced meal.
- Autocorrelation at 30 and 60 minutes: the Pearson correlation between each CGM value and
  the value 30 or 60 minutes later, matched on the actual timestamps to within 90 seconds. It
  measures how quickly the glucose curve decorrelates.
- Outcome SD at a stuck high: for samples with CGM between 180 and 240 mg/dL, the SD of the
  change over the next 30 minutes. A wide spread means the next half hour is hard to predict
  from a stuck high; a narrow one means it is nearly deterministic. At least 200 in-band
  samples are required.
- Diurnal amplitude: the peak minus the trough of the hour-of-day mean profile, which is
  invariant to time-zone shifts.
- Hypo recovery: for each crossing below 70 mg/dL, the time to return to 100 mg/dL, together
  with the fraction of recoveries that then overshoot above 180 mg/dL within two hours.
- Compression lows: sharp reversing dips below 70, defined as a fall of more than 25 mg/dL
  from a pre-dip level of at least 85 that recovers to within 15 mg/dL of that level inside 30
  minutes. This is the shape of a sensor compression artefact rather than a physiological low,
  reported as events per 30 days.
- Sensor jitter: the SD of the second difference of the five-minute series, taken over
  contiguous five-minute triples only. It captures high-frequency measurement noise.
- ISF drift: the algorithm's insulin-sensitivity value reduced to a weekly median, then the
  coefficient of variation of those weekly medians over at least six weeks.

### 3.3 Aggregation and verdict

Each statistic is computed per user for the real cohorts and per persona for the simulator,
then reported as the median across users with a bootstrap 95% confidence interval from 2000
resamples. Taking each person's own value first, and pooling afterwards, keeps any single
heavy user or unstable persona from carrying the result. The four real cohorts define a
real-world envelope for each statistic, running from the lowest to the highest of their four
medians and padded by 10% of that span. A persona class is counted as matching if its median
falls inside the envelope. The test is deliberately lenient, since a persona need only land
somewhere within the spread of four independent real datasets to pass.

## 4. Real-world data agrees with itself

The first result is what makes the rest interpretable. The four real cohorts, built and worn
independently, sit in a tight band on almost every measure (Table 1, Figure 1). Glucose
variability is between 30 and 34% for all four. The outcome spread 30 minutes after a stuck
high runs from 27 to 34 mg/dL. Hypoglycaemia recovers to 100 mg/dL in 50 to 59 minutes and
then overshoots above 180 mg/dL about a quarter of the time. Sensor jitter runs from 4.5 to
6.7 mg/dL, and week-to-week insulin-sensitivity drift from 8 to 22%.

Nothing forced this agreement, and it is the load-bearing assumption of the method. Because
four different algorithms worn by different people give nearly the same numbers, those
numbers describe closed-loop life in general rather than one idiosyncratic group, and they
provide a target for the simulator to be judged against. Where the real cohorts disagree, as
they do to some degree on the rate of compression lows, the envelope is wider and the test
on that statistic is correspondingly more forgiving.

## 5. Where the simulator holds, and where it fails

Table 1. Each cell is the per-user median with a bootstrap 95% confidence interval. Sim
values outside the real-world envelope are marked with an asterisk.

| Signature | Boost | Trio | OpenAPS | AAPS-classic | Padova adult | Padova adolescent | Padova child |
|---|---|---|---|---|---|---|---|
| Glucose variability (CV%) | 30 | 33 | 34 | 32 | 23* | 24* | 30 |
| Rise tail P(rise>10)/5min (%) | 4.3 | 6.6 | 3.8 | 3.7 | 1.0* | 1.6* | 2.6* |
| Autocorrelation @30 min | 0.8 | 0.8 | 0.9 | 0.8 | 0.8 | 0.9 | 0.8 |
| Autocorrelation @60 min | 0.5 | 0.6 | 0.7 | 0.6 | 0.7 | 0.7 | 0.6 |
| Outcome SD @stuck-high (mg/dL) | 30 | 34 | 27 | 29 | 21* | 22* | 28 |
| Diurnal amplitude (mg/dL) | 35 | 41 | 48 | 56 | 47 | 59* | 52 |
| Hypo recovery to 100 (min) | 59 | 50 | 55 | 50 | 113* | 119* | 110* |
| Hypo rebound >180 (%) | 26 | 23 | 27 | 28 | 0* | 0* | 5* |
| Compression lows (/30d) | 4.6 | 5.3 | 1.9 | 3.0 | 0* | 0* | 0* |
| Sensor jitter (mg/dL) | 4.5 | 6.7 | 5.5 | 4.7 | 2.4* | 2.4* | 2.5* |
| ISF drift (weekly %CV) | 22 | 15 | 12 | 8 | 0* | 0* | 0* |

![Figure 1. Real-world AID cohorts in blue and UVA/Padova personae in warm colours, one
panel per signature, with bootstrap confidence intervals. The shaded band on each panel is
the real-world envelope, the span of the four real medians. The real cohorts sit inside it;
the personae sit inside it for autocorrelation, and for the child on variability, but outside
it for the statistics that make real-world control hard.](../scripts/2026-07-insilico/fidelity_suite/fig_multicohort.png)

The simulator is faithful on the short-horizon shape of the glucose curve. Its
autocorrelation at 30 and 60 minutes falls inside the real range for all three persona
classes, so on the calm, announced-meal stretches that make up most of any day it behaves
like real data and remains useful for controller stability checks and regression testing.

Overall variability is less clear-cut. Given realistic, weight-appropriate meals the
simulator can reach real-world glucose variability, but only in its child personae, which are
the most variable. The adults and adolescents run smoother than any real cohort, at 23 to 24%
against a real 30 to 34%, and their stuck-high outcome spread is likewise too narrow. Since
controllers are almost always evaluated on the adult personae, the usual in-silico test
understates how variable real life is, and reaching realism meant leaning on the personae the
field does not normally use.

The failures carry more weight than the passes, because they land on the situations a safety
test is meant to probe, and because no persona reproduces any of them at any age.

Consider first the fat tail of sudden glucose rises, which is the fingerprint of an
unannounced meal. Real cohorts see a sharp five-minute rise 4 to 7% of the time; every
persona sits at 1 to 3%, and in any case their controllers were told the carbohydrate in
advance.

Hypoglycaemia is different in kind. Real lows recover to 100 mg/dL in roughly 50 to 59
minutes and overshoot above 180 mg/dL about a quarter of the time, because people eat to
treat them. The personae take about twice as long, 110 to 120 minutes, and hardly ever
overshoot, because the simulator has no rescue carbohydrate and can only climb back by
withdrawing insulin. A controller that has learned to look good against the simulator's slow,
one-directional recovery has been tuned against a low that does not occur.

The sensor is also too clean. Real CGM carries roughly twice the high-frequency jitter of the
simulator's sensor model, and it throws sharp reversing compression lows a few times a month
that the model cannot produce at all. A controller that has never had to tell a real low from
a sensor artefact has not been tested against one of the commonest causes of a bad automated
decision overnight.

Finally, the model does not change over time. Real insulin sensitivity drifts 8 to 22% from
week to week and the loops adapt to it, whereas the 2008 model has fixed parameters and so
shows no drift at all. One caveat belongs here. Our drift measure reads the sensitivity the
algorithm itself used, so the AndroidAPS-classic cohort, which predates dynamic sensitivity,
sits at the low end because its algorithm barely adjusts, not because those people are
metabolically steadier. The three adaptive cohorts, and the physiology underneath them,
drift; the simulator does not.

In all, five of the eleven statistics are matched by no persona at any age, and a sixth,
sensitivity drift, is zero by construction.

## 6. Why refinement is not the whole answer

The obvious objection is that we tested the 2008 model and that later versions are better.
It is a fair objection and part of it is correct, so it deserves a measured answer rather
than an argued one.

The main change from 2008 to S2013 is time-varying insulin sensitivity, within and across
days and with a dawn component, fitted from clinical data [2]. S2013 also adds a glucagon
counter-regulation model that raises endogenous glucose production during a low, and it
improves the glucose kinetics of hypoglycaemia. We reconstructed the version as closely as
the open literature allows by adding the first two of these to the 2008 personae together and
measuring the whole reconstruction; we did not implement the improved hypoglycaemia kinetics,
which we note as a caveat. The sensitivity factor scales the insulin-dependent glucose uptake
and the hepatic insulin action with a day-to-day coefficient of variation of 22% and a dawn
amplitude of 20%, and the counter-regulation raises endogenous glucose production in
proportion to how far below 80 mg/dL glucose has fallen and how fast it is falling.
Everything else, the meals, the announcement, the sensor and the controller, is identical to
the 2008 baseline, so any difference is due to the two additions. Their magnitudes are
clinically plausible values rather than the certified per-subject parameters, so the
reconstruction isolates what the additions do rather than reproducing the licensed model
exactly.

Table 2. Adult personae, the 2008 baseline and the reconstructed S2013 with both additions
together, against the real-world envelope. Each entry is the per-persona median.

| Signature | Real range | 2008 | Reconstructed S2013 |
|---|---|---|---|
| Glucose variability (CV%) | 30 to 34 | 23 | 28 |
| Rise tail P(rise>10)/5min (%) | 3.7 to 6.6 | 1.0 | 1.2 |
| Autocorrelation @30 min | 0.78 to 0.87 | 0.84 | 0.90 |
| Autocorrelation @60 min | 0.50 to 0.68 | 0.66 | 0.77 |
| Outcome SD at a stuck high (mg/dL) | 27 to 34 | 21 | 18 |
| Diurnal amplitude (mg/dL) | 35 to 56 | 47 | 60 |
| Hypo recovery to 100 (min) | 50 to 59 | 113 | 106 |
| Hypo rebound above 180 (%) | 23 to 28 | 0 | 0 |
| Compression lows (/30d) | 1.9 to 5.3 | 0 | 1.4 |
| Sensor jitter (mg/dL) | 4.5 to 6.7 | 2.4 | 2.3 |
| ISF drift (weekly %CV) | 8 to 22 | 0 | 0 |

![Figure 2. Adult personae, the 2008 baseline in grey and the reconstructed S2013 in green,
against the real-world range in blue. The reconstruction reaches the real range on none of
the eleven signatures, and it moves the two autocorrelations and the diurnal amplitude, which
2008 had matched, out of range.](../scripts/2026-07-insilico/fidelity_suite/fig_s2013_reconstructed.png)

Taken as one model, the reconstruction matches none of the eleven signatures for the adult
personae, and the reason is instructive. The two additions pull in opposite directions on
variability, since the time-varying sensitivity widens the glucose distribution while the
counter-regulation damps the lows that widen it. Overall variability therefore rises only
from 23 to 28% and stays below the real band, and the stuck-high outcome spread does not
improve but narrows, from 21 to 18 mg/dL against a real 27 to 34. What the additions mainly
do is make the glucose curve smoother and more regular, which moves it the wrong way: the
30- and 60-minute autocorrelations rise above the real range and the diurnal amplitude
overshoots, all three being quantities the 2008 model had reproduced. The
hypoglycaemia-recovery gap narrows, from about 113 to 106 minutes, but stays close to twice
the real 50 to 59, and the rebound is still absent, because endogenous glucose release is not
the carbohydrate a person eats to treat a low. The unannounced-meal rise tail, the sensor
jitter and the sensitivity drift do not move at all. The small non-zero compression reading
is a detector artefact, since a sharp counter-regulatory reversal has the same shape as a
sensor compression low, so the model has gained lows that resemble the artefact rather than
the artefact itself. The exact size of the overshoots depends on the magnitudes we chose,
which are plausible rather than fitted, but the direction, smoother and more regular rather
than more realistic on the disturbances, is intrinsic to what the refinements change.

Two things follow, and neither depends on the reconstruction being exact. The structural
gaps, the unannounced-meal rise, the untreated hypoglycaemia, the sensor behaviour and the
sensitivity drift, do not move under either addition, and they cannot, because none of them
is a matter of insulin sensitivity or counter-regulation; that result is
magnitude-independent. And the refinements live in the licensed S2013, not in the freely
available 2008 model that underpins the open in-silico work and the FDA-accepted family. To
our knowledge no version, before this work, has been benchmarked against a real-world
distributional envelope. The claim that a refinement closes a gap is an empirical one, and
where we could test it the reconstruction reached the real range on nothing and pushed three
matched statistics out of it.

The point is not that one model version is inadequate. It is that fidelity to real data is
treated as settled when it can be measured, statistic by statistic, for the quantities a
safety decision depends on. The failures are not scattered at random. They fall on the
disturbances the model does not represent, and those disturbances are the ones that define
real-world safety.

## 7. A new approach

The constructive reading of these results is not to distrust simulation, which replaced
animal trials for good reasons and is still valuable for what it does well, but to widen it
and to measure it. We suggest three steps, from the readiest to the most speculative.

The first is a fidelity benchmark that could be used now. The signatures here are a first
draft of a standard: an in-silico safety result could state where the scenarios it was tested
on fall relative to a real-world envelope on unannounced-meal rises, hypo treatment, sensor
artefact and sensitivity drift, alongside the usual outcome metrics. This turns fidelity from
an assumption into a reported quantity and does not depend on the model version, applying
equally to the 2008 model, to S2013 and to whatever follows. It needs no new simulator, only
that fidelity be measured and stated, and the real-world envelopes can be drawn from open
corpora such as the OpenAPS Data Commons, so the benchmark can be maintained by the community
that generates the data.

The second is a hybrid, data-calibrated simulator, achievable in the near term. The validated
mechanistic core can be kept and given empirically fitted stochastic layers for the specific
gaps found here: an unannounced-meal onset process, insulin efficacy that varies at the
magnitude the real data shows, a sensor model with both realistic noise and compression
artefacts, and week-scale sensitivity drift. Each layer can be fitted from the corpora that
already exist, and each closes a measured gap rather than adding unquantified realism, so the
work is incremental and testable rather than a rebuild.

The third, further off, is real-disturbance replay and generative modelling. The real
datasets are themselves the most faithful record of the disturbances a controller will meet,
and they can serve directly as scenario libraries, replaying measured sequences of meals,
activity and sensor behaviour so that a controller faces real disturbance trajectories rather
than synthetic ones. Beyond that, a generative model trained on the large real corpora, with
the mechanistic model as a physiological prior, could produce populations that match the
real-world envelope by construction. Both would need validation of their own, but the data to
attempt them exists now at a scale it did not a decade ago.

None of this displaces the mechanistic simulator. A benchmark sits on top of it, a hybrid
extends it, and a generative model would still lean on it as a prior. The argument is not
against the UVA/Padova model but against treating any one simulator as an unmeasured proxy for
reality.

## 8. Limitations

This is an observational, distributional comparison and should be read as one. The real
cohorts are self-selected users of open-source AID systems rather than a representative
sample of the type 1 population, so their agreement is reassuring but does not establish that
they represent everyone. We tested the open 2008 implementation and, in Section 6, measured
the two S2013 refinements most likely to affect our results by reimplementing them on the
personae; we did not run the licensed S2013 model itself, and our reimplementations use
clinically plausible magnitudes rather than the certified per-subject parameters, so they
isolate the mechanisms rather than reproduce the version. The magnitude of the sensitivity
augmentation is a plausible choice rather than a fitted value, and the one gap it closes
scales with that choice, though the untouched structural gaps do not. Announcing the meals
handicaps the simulator on the rise-tail statistic in particular, which we state rather than
hide. The drift statistic reads algorithm-reported sensitivity, so it partly reflects whether
an algorithm adapts and not only whether physiology changes. Finally, the eleven signatures
are a first draft, not a validated or exhaustive fidelity battery, and turning them into a
standard is part of what we are proposing rather than something we claim to have finished.

## 9. Conclusion

The UVA/Padova simulator has served the field well, and replacing animal trials with it was a
genuine advance. But a tool with this much influence over which systems reach patients ought
to be held to an explicit, measured standard of fidelity to the real world, and on the
open 2008 implementation that standard is not met for the statistics that matter most
to safety. The simulator is smoother than real life, its meals arrive announced, its lows go
untreated, its sensor is unrealistically clean, and its physiology holds still while real
sensitivity drifts. A controller can pass in silico by mastering the world the simulator
represents and still meet, untested, the world that produces the real lows and the real stuck
highs.

The remedy is not to abandon simulation but to measure its fidelity and to widen it using the
real-world data that now exists in quantity. What the results argue for is a different way of
testing closed loops, one that reports fidelity to real data as a quantity in its own right
and that builds simulators calibrated against, and validated on, the people they are meant to
stand in for.

## References

*[Citations give author, title, venue and year; exact volume and page numbers should be
verified against the source before submission.]*

1. Kovatchev BP, Breton M, Dalla Man C, Cobelli C. In silico preclinical trials: a proof of
   concept in closed-loop control of type 1 diabetes. Journal of Diabetes Science and
   Technology. 2009.
2. Dalla Man C, Micheletto F, Lv D, Breton M, Kovatchev B, Cobelli C. The UVA/PADOVA Type 1
   Diabetes Simulator: new features. Journal of Diabetes Science and Technology. 2014.
3. Visentin R, Campos-Nanez E, Schiavon M, et al. The UVA/Padova Type 1 Diabetes Simulator
   goes from single meal to single day. Journal of Diabetes Science and Technology. 2018.
4. Visentin R, Dalla Man C, Kovatchev B, Cobelli C. The University of Virginia/Padova Type 1
   Diabetes Simulator matches the glucose traces of a clinical trial. Diabetes Technology and
   Therapeutics. 2014.
5. Cobelli C, Kovatchev B. Developing the UVA/Padova Type 1 Diabetes Simulator: modeling,
   validation, refinements, and utility. Journal of Diabetes Science and Technology. 2023.
6. Xie J. simglucose: a type 1 diabetes simulator implemented in Python (v0.2.1, 2018).
   https://github.com/jxx123/simglucose
7. Dalla Man C, Rizza RA, Cobelli C. Meal simulation model of the glucose-insulin system.
   IEEE Transactions on Biomedical Engineering. 2007.
8. OpenAPS Data Commons, Open Humans Foundation. Openly shared automated-insulin-delivery
   data from the #WeAreNotWaiting community.

---

*Reproducibility: the cohort loaders, the thirty-persona simulator generator, the eleven
signatures, the aggregation and the figures are open and re-runnable. Real cohort data is
anonymised, and the OpenAPS cohort is drawn from an openly shared research commons.*
