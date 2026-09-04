# One-minute and five-minute continuous glucose sensing compared on real records from the same person

*[Author name(s) and affiliation to be added. Prepared from an anonymised single-subject
analysis; the analysis code is open and the processing steps are reproducible.]*

## Abstract

#### Background

Continuous glucose monitors have historically reported every five minutes and
sensors reporting every minute are now in ordinary use. The assumption is that the faster feed
carries more information. Earlier work, including our own first attempt at this question,
tested that by decimating a one-minute record to simulate a five-minute one. That is not the
same experiment: a real five-minute sensor filters internally before reporting, so a
decimated stand-in may be a poor model of it.

Methods. One adult with type 1 diabetes wore a five-minute sensor for 83 days
(2026-03-01 to 05-22, 24,012 readings) and then a one-minute sensor for 61 days (2026-05-23
to 07-30, 82,691 readings), with a five-day return to the five-minute sensor in between.
Nothing here is decimated, interpolated or simulated. We compare the two records with the
variogram D(τ) = E[(x(t+τ) − x(t))²], which is expressed in minutes of lag and is therefore
directly comparable between cadences with no resampling. For a process observed with additive
noise, D has a floor of twice the noise variance at every lag; a filtered, noise-free
rendering has no such floor. Uncertainty is a day-level block bootstrap.

Results. Across every lag both sensors can see. 5 to 120 minutes, a 24-fold range, the
ratio D₁ₘᵢₙ(τ) / D₅ₘᵢₙ(τ) is flat at 1.602, varying by only 6.6 per cent of its mean. The
log-log slope of D is identical in both shared bands: 1.35 [1.30, 1.39] against 1.35 [1.28,
1.40] over 5 to 20 minutes, and 1.29 [1.25, 1.32] against 1.29 [1.24, 1.34] over 20 to 60 minutes.
Neither record shows a noise floor. D falls smoothly to 4.44 mg/dL² [2.92, 7.34] at a
one-minute lag, which is 22 per cent of the 20.4 mg/dL² that a sensor adding independent noise
of the published magnitude would impose at every lag. Below five minutes, where only the
faster sensor can see, the slope is 1.49 [1.13, 1.70], statistically indistinguishable from
the 1.35 it shows just above, so no new regime appears.

Put to the tasks a CGM is actually used for, three of the four, display, retrospective
metrics and reactive alarms, depend only on the newest sample or on an average of thousands,
and cadence changes when they arrive rather than how good they are. The fourth, prediction,
shows no measurable benefit: normalised forecast RMSE is 0.344 against 0.345 at fifteen
minutes and 0.814 against 0.824 at sixty, with overlapping intervals and an alternating sign,
and top-decile lift for a predictive hypoglycaemia alarm is 9.14x against 9.18x at fifteen
minutes and 7.46x against 7.57x at thirty.

#### Conclusion

The two sensors record the same process, with the same relative noise, and
differ by a single scale factor that is the glycaemic variability of the period. Neither
cadence is noisier than the other. The one-minute sensor does not reveal any behaviour below
five minutes that the five-minute record fails to imply; its extra samples continue the same
power law and are a finer rendering of the same curve rather than new measurements. Both
sensors report values that are already filtered, which is why neither shows the measurement
noise that error models attribute to the raw transducer.

## 1. Rationale for this comparison

The question is whether one-minute continuous glucose data contains anything a five-minute
record does not. The obvious way to test it, and the way we first tested it, is to take a
one-minute record and throw away four samples in five. That is convenient and it is wrong in
a specific way: it assumes a real five-minute sensor is the same signal with samples removed.

It is not. Manufacturers apply internal filtering before a value is reported, and the
filtering is chosen for the reporting rate. A decimated one-minute record inherits the fast
sensor's rendering, not the slow sensor's. Comparing a record against a decimated copy of
itself therefore measures what a *consumer* would lose by sampling more slowly. It does not
measure how the two *sensors* differ, which is the question actually being asked.

This subject wore both, one after the other, which allows the real comparison. The obvious
objection is that the periods differ, and they do, materially. The later period is more
volatile. But glycaemic variability is a property of the person and the fortnight, not of the
sensor. If it is the only thing that differs, it will show up as a single multiplicative
constant and nothing else, and that is a testable claim rather than an excuse.

## 2. Data

| Era | Dates | Days | Readings | Median gap | Mean | SD | CV |
|---|---|---|---|---|---|---|---|
| Five-minute | 2026-03-01 – 05-22 | 83 | 24,012 | 5.00 min | 122.6 | 31.8 | 25.9% |
| One-minute | 2026-05-23 – 07-30 | 61 | 82,691 | 1.00 min | 127.4 | 39.6 | 31.1% |
| Five-minute interlude | 2026-06-08 – 06-12 | 5 | 1,897 | 5.00 min | — | — | — |

The five-day return to the five-minute sensor sits inside the one-minute era and serves as a
partial control for season and therapy.

## 3. Method: the variogram

The variogram, or structure function, is

  D(τ) = E[ (x(t+τ) − x(t))² ]

the mean squared change over a lag of τ minutes. It has three properties that make it the
right tool here and that a spectrum or an autocorrelation does not share.

It is expressed in time, not in samples, so a five-minute record and a one-minute record
can be placed on the same axis without resampling either. No decimation, no interpolation, no
assumption about what happens between samples.

It separates noise from signal by construction. If a sensor adds independent measurement
noise of variance s², then every difference x(t+τ) − x(t) contains two independent noise
draws, so D is lifted by 2s² *at every lag including the shortest*. Real signal structure, by
contrast, vanishes as τ to 0 because glucose is continuous. So a noise floor appears as a
flattening of D at small lag, the "nugget" of the geostatistical literature, and its height
is twice the noise variance.

Its shape is scale-free. The log-log slope of D distinguishes regimes: a slope of 2 is a
smooth differentiable signal, a slope of 0 is white noise, and intermediate slopes describe
rougher processes. Comparing slopes compares the character of two records without reference to
how large their excursions were.

Uncertainty throughout is a block bootstrap resampling whole days with replacement, which
respects the strong autocorrelation of glucose. Intervals are 95 per cent.

## 4. Results

### 4.1 The two records differ by one number

| Lag | Five-minute era D | One-minute era D | Ratio |
|---|---|---|---|
| 5 min | 30.0 [27.3, 32.8] | 47.5 [42.7, 52.9] | 1.584 |
| 10 min | 79.5 [73.1, 86.6] | 121.8 [108.9, 135.3] | 1.533 |
| 15 min | 133.4 [122.4, 144.1] | 210.7 [187.4, 234.5] | 1.579 |
| 20 min | 195.7 [181.0, 212.3] | 315.1 [279.6, 353.9] | 1.610 |
| 25 min | 267.1 [246.1, 289.9] | 430.6 [384.5, 481.3] | 1.612 |
| 30 min | 339.6 [313.1, 368.9] | 556.3 [496.8, 622.7] | 1.638 |
| 40 min | 506.7 [463.1, 554.3] | 810.6 [716.1, 904.8] | 1.600 |
| 50 min | 658.4 [600.3, 720.8] | 1063.0 [937.9, 1186.0] | 1.615 |
| 60 min | 794.1 [722.4, 872.4] | 1283.9 [1133.4, 1449.1] | 1.617 |
| 90 min | 1112.1 [994.2, 1237.4] | 1787.5 [1580.1, 2027.9] | 1.607 |
| 120 min | 1320.9 [1163.4, 1501.7] | 2144.9 [1873.6, 2424.8] | 1.624 |

Across a twenty-four-fold range of lag the ratio is 1.602, with a total spread of 6.6 per
cent of its mean. It does not trend, and in particular it does not bend at the short end,
which is the only place the two sensors could differ.

This is the central result. Two records made by different hardware, three months apart, on a
person whose control changed materially in between, are related by a single multiplicative
constant. Everything else about them, the shape of the structure at every timescale from five
minutes to two hours, is the same.

The constant is roughly the change in variability. The ratio of squared coefficients of
variation, (31.1 / 25.9)², is 1.438, which accounts for most though not all of the 1.602; the
remainder reflects that the later period's excursions were not merely larger but somewhat
differently distributed. The point does not rest on the two numbers matching exactly. It rests
on the ratio being flat, because a cadence effect could not be.

### 4.2 Neither sensor shows a measurement-noise floor

The one-minute record can be examined at lags no five-minute sensor can reach.

| Lag | One-minute era D | σ if this were pure white noise |
|---|---|---|
| 1 min | 4.44 [2.92, 7.34] | 1.49 mg/dL |
| 2 min | 12.24 [10.01, 15.74] | 2.47 |
| 3 min | 23.24 [20.03, 27.53] | 3.41 |
| 4 min | 36.16 [31.76, 41.81] | 4.25 |
| 5 min | 47.52 [42.78, 52.70] | 4.87 |
| 10 min | 121.78 [108.81, 135.08] | 7.80 |

D declines smoothly to 4.44 mg/dL² at one minute and shows no sign of levelling off. That is
the signature of a record with essentially no independent per-sample noise.

The comparison worth making is with the published error models. Vettoretti and colleagues fit
a measurement-noise standard deviation of 3.19 mg/dL to a factory-calibrated sensor [4]. Noise
of that size would hold D at 2 x 3.19² = 20.4 mg/dL² *at every lag, including the shortest*.
The measured D at one minute is 4.44, which is 22 per cent of that floor.

The reading is that the values these sensors report are not raw transducer output. They have
been filtered before they leave the device, and the filtering has removed most of the noise
the error models describe, which is exactly what those models are for, since they are fit to
reconstruct the raw signal behind the reported one. The practical consequence is that a
consumer of either feed is receiving an already-smoothed estimate, and that the smoothing, not
the reporting interval, is what determines how noisy the series looks.

Neither cadence is noisier than the other. Section 4.1 establishes that directly for every lag
they share; there is no lag at which the faster sensor's record sits proportionally higher.

### 4.3 Nothing new appears below five minutes

If the one-minute sensor were resolving structure the five-minute sensor cannot, the character
of D would change as the lag drops below five minutes. It does not.

| Record | Lag band | Log-log slope of D |
|---|---|---|
| Five-minute era | 5–20 min | 1.35 [1.30, 1.39] |
| One-minute era | 5–20 min | **1.35 [1.28, 1.40]** |
| Five-minute era | 20–60 min | 1.29 [1.25, 1.32] |
| One-minute era | 20–60 min | **1.29 [1.24, 1.34]** |
| One-minute era | 1–5 min | 1.49 [1.13, 1.70] |

In both bands the two sensors agree to two decimal places, with overlapping intervals. That is
a strong statement: the two records are not merely similar in magnitude after scaling, they
have the same roughness at every timescale they share.

Below five minutes, where only the faster sensor can see, the slope is 1.49 with an interval
of [1.13, 1.70]. That interval contains the 1.35 measured just above it. There is no
detectable break, the same power law continues from one minute to sixty. The extra samples
are not a window onto a different regime; they are a finer rendering of the curve the slower
sensor was already tracing.

Two null hypotheses can be rejected outright with these slopes. A slope near 0 at short lag
would indicate white measurement noise, and there is none. A slope near 2 would indicate a
smooth differentiable signal, and it is not that either. The observed exponent near 1.3 to 1.5
describes a rough, fractional-Brownian-like process, and it describes both sensors equally.

### 4.4 A within-season check

The five-day return to the five-minute sensor sits inside the one-minute era and so shares its
season and therapy. Its variogram has the same shape as the other two, normalised to its own
60-minute level, it gives 0.006, 0.053, 0.110, 0.186, 0.368 and 0.586 at 5, 10, 15, 20, 30 and
40 minutes, against 0.016, 0.076, 0.146, 0.229, 0.421 and 0.623 for the one-minute era over
the same window. Five days is too little to carry weight on its own, and we report it only as
a consistency check that does not contradict the main comparison.

## 5. Uses of a CGM, and the subset that could benefit

The variogram results say the two records contain the same information. It is worth checking
that against the tasks the signal is actually put to, because a null in a general statistic
does not always survive contact with a specific use.

The uses divide into four kinds, and only one of them could plausibly be made *more accurate*
by a faster cadence rather than merely delivered sooner.

| Use | Depends on | Could a faster cadence help accuracy? |
|---|---|---|
| Display: current value, trend arrow | the newest sample | No — a scheduling question only |
| Retrospective metrics: mean, CV, time in range, GMI | an average over thousands of samples | No |
| Reactive alarm: glucose is below 70 now | the newest sample | No — a scheduling question only |
| **Predictive alarm, and an automated insulin delivery (AID) dosing against a forecast** | **the shape of recent history** | **Possibly — tested here** |

Each era was analysed at its own native cadence, validated out of sample against itself with
GroupKFold over whole days, and given the same look-back in *minutes*, the one-minute record
simply has five times as many samples inside that window. Metrics are scale-free so that the
difference in glycaemic variability between the eras cannot manufacture a result: normalised
RMSE is RMSE divided by the standard deviation of the target, where 1.0 means no skill, and
lift is precision in the top risk decile divided by that era's own base rate.

### 5.1 Forecast accuracy, the AID case

Normalised RMSE, with day-level block-bootstrap intervals:

| Horizon | Five-minute era | One-minute era |
|---|---|---|
| +15 min | 0.344 [0.323, 0.367] | 0.345 [0.327, 0.370] |
| +30 min | 0.570 [0.543, 0.599] | 0.556 [0.525, 0.593] |
| +45 min | 0.717 [0.692, 0.749] | 0.720 [0.683, 0.771] |
| +60 min | 0.814 [0.785, 0.847] | 0.824 [0.786, 0.872] |
| +90 min | 0.910 [0.885, 0.934] | 0.923 [0.896, 0.954] |

The intervals overlap heavily at every horizon and the direction of the point estimate
alternates, the one-minute record is nominally better at 30 minutes and nominally worse at
15, 45, 60 and 90. There is no forecast advantage to detect. The intervals bound any advantage
at roughly five per cent in relative terms, in either direction.

### 5.2 Predictive hypoglycaemia alarms

Will glucose drop below 70 within H minutes, evaluated only from starting points at or above
70:

| Horizon | Era | Base rate | AUC | Top-decile lift |
|---|---|---|---|---|
| 15 min | 5-min | 1.21% | 0.9621 [0.9474, 0.9752] | 9.14× [8.55, 9.56] |
| 15 min | 1-min | 1.89% | 0.9716 [0.9622, 0.9810] | 9.18× [8.72, 9.56] |
| 20 min | 5-min | 1.72% | 0.9412 [0.9246, 0.9562] | 8.43× [7.98, 8.82] |
| 20 min | 1-min | 2.38% | 0.9599 [0.9464, 0.9717] | 8.63× [8.12, 9.12] |
| 30 min | 5-min | 2.36% | 0.8962 [0.8690, 0.9202] | 7.46× [6.93, 8.08] |
| 30 min | 1-min | 3.38% | 0.9257 [0.9074, 0.9459] | 7.57× [7.03, 8.26] |
| 45 min | 5-min | 3.31% | 0.8290 [0.7912, 0.8658] | 6.19× [5.63, 6.85] |
| 45 min | 1-min | 4.81% | 0.8595 [0.8286, 0.8942] | 6.31× [5.76, 6.98] |
| 60 min | 5-min | 4.28% | 0.7672 [0.7225, 0.8082] | 5.05× [4.57, 5.64] |
| 60 min | 1-min | 6.22% | 0.7951 [0.7545, 0.8351] | 5.42× [4.93, 6.04] |

Lift is the metric to read, because it divides out each era's own base rate, and the base
rates differ by about forty per cent at every horizon, the later period simply had more
hypoglycaemia. On lift the two records are indistinguishable: 9.14 against 9.18 at fifteen
minutes, 7.46 against 7.57 at thirty, 5.05 against 5.42 at sixty, with intervals overlapping
almost completely throughout.

AUC does run about 0.02 to 0.03 higher for the one-minute era at every horizon, and it is worth
saying why we do not read that as a cadence effect. The gap is smallest at the shortest horizon
(0.0095 at fifteen minutes) and grows with horizon (0.0295 at thirty, 0.0279 at sixty). A
genuine benefit from finer sampling would do the opposite: fine-grained recent detail matters
most for near-term prediction and washes out as the horizon lengthens. A gap that grows with
horizon is the signature of a difference between the *periods*, more hypoglycaemia, more
volatility, more predictable excursions, not between the sensors. At the one horizon where a
cadence effect should be largest, the two records are separated by 0.0095 of AUC and 0.04 of
lift.

### 5.3 Reading

Of the four things a CGM is used for, three are answered by the newest sample or by an average
over thousands of them, and are untouched by cadence except in when they arrive. The fourth, prediction, which is what a future-low alarm and an AID both rest on, shows no measurable
benefit at any horizon from fifteen to ninety minutes, on either a regression or a
classification framing, with the era-difficulty confound removed by construction.

This is what the variogram predicted. Predictive skill is a property of the process, and
section 4 established that both sensors record the same process at the same relative noise.

## 6. The shared upstream filter

That two cadences record the same process is not a coincidence of this dataset. It follows
from where the measurement is taken.

Glucose reaches the subcutaneous interstitium from blood by diffusion, which to first order is
a single-pole low-pass filter. Vettoretti and colleagues estimated its time constant at a
median of 3.8 minutes [4]. The attenuation of a sinusoid of period P through such a filter is
1/√(1 + (2πτ/P)²):

| Period | Gain | Attenuation | Blood amplitude needed to reach 1 SD of published sensor noise |
|---|---|---|---|
| 2 min | 0.083 | −21.6 dB | 38.2 mg/dL |
| 5 min | 0.205 | −13.8 dB | 15.6 mg/dL |
| 10 min | 0.386 | −8.3 dB | 8.3 mg/dL |
| 20 min | 0.642 | −3.8 dB | 5.0 mg/dL |
| 36 min | 0.833 | −1.6 dB | 3.8 mg/dL |
| 60 min | 0.929 | −0.6 dB | 3.4 mg/dL |

Four-fifths of the amplitude of any five-minute-period oscillation in blood is destroyed
before the sensor transduces it. For such an oscillation to reach even one standard deviation
of the published noise, blood glucose would have to swing by ±15.6 mg/dL every five minutes,
which does not occur physiologically.

This filter sits upstream of both devices and is a property of physiology and sensor
placement, not of electronics. Faster sampling cannot recover what diffusion has already
removed, which is why the two records in section 4.1 differ by a scale factor and nothing
else. It also explains why the reported series have no noise floor: with no fast content to
preserve, a manufacturer can filter aggressively at no cost to fidelity, and evidently does.

## 7. Relation to the literature

The result agrees with a body of work that predates both of these devices.

Gough, Kreutz-Delgado and Bremer characterised blood glucose directly and placed its band edge
near 1x10⁻³ Hz, a period of about seventeen minutes, recommending a sampling period of roughly
ten minutes and noting that faster sampling captures noise rather than physiology [1].

Breton, Shields and Kovatchev asked what happens in the compartment a subcutaneous sensor
measures, and found no patterns of period shorter than about thirty-six minutes, concluding
that interstitial glucose can be characterised with an eighteen-minute sampling period. They
also observed that sampling *blood* faster would be detrimental in a subcutaneously sensed
system, because the fast blood dynamics are simply not present at the sensor [2].

Fico and colleagues characterised the spectrum of continuous monitor signals and found 75 per
cent of power accumulated by a period of about 1.4 hours, with a 3 dB bandwidth reaching only
about 4x10⁻⁵ Hz [3].

Russon and colleagues approached the same asymmetry from the other direction, coarsening
five-minute records to fifteen minutes. Mean glucose, coefficient of variation and time in
range were unchanged; detection of glycaemic episodes fell, hypoglycaemic episodes by 19.2
per cent, level-two hypoglycaemia by 27.9 per cent, hyperglycaemia by 7.5 per cent [5]. The
sampling interval is a parameter of event detection, not of signal content.

We searched for a head-to-head evaluation of one-minute against five-minute continuous glucose
sampling and did not find one. We do not claim none exists.

What this paper adds is a direct measurement on real records from both cadences on the same
person, rather than an inference from one cadence about the other, and a noise result the
earlier literature could not obtain: that the reported values at both cadences are already
filtered to well below the noise level that error models attribute to the transducer.

## 8. Scope of the conclusion

It does not follow that a one-minute sensor is worse. Nothing here shows a cost to the
faster feed. The two records are the same process at the same relative noise.

It does follow that the extra samples carry no additional information about glucose. The
variogram ratio is flat across every shared lag, the slopes match in both shared bands, and
the sub-five-minute band continues the same law rather than opening a new one.

What a faster feed still changes is when you are told. A consumer of five-minute data
waits, on average over grid phases, two minutes for news that a one-minute consumer has
immediately. That is a scheduling property and requires no extra information; it is worth
whatever two minutes is worth to whatever acts on it. This paper does not price that, and a
companion analysis that attempts to should be read with the caution that it rests on decimation
rather than on the two real records used here.

Anyone estimating rate of change from a one-minute feed should be careful. With a
variogram exponent near 1.3 and no noise floor, consecutive one-minute values are strongly
dependent, and an estimator that assumes independent samples, ordinary least squares over a
short window, for instance, will weight them as though they were independent when they are
not.

## 9. Limitations

One subject. The comparison is observational and between eras: sensor hardware, season,
therapy and glycaemic control all change at the boundary. The design of the analysis is chosen
to be robust to exactly that, the variogram ratio and the log-log slopes are scale-free, so a
change in variability cannot produce the flatness reported in section 4.1, but a single
person cannot establish that the finding generalises across devices or people.

The sensor makes and models are not recorded in the data available to us. We can say the two
eras were different devices with different reporting intervals; we cannot attribute the
filtering behaviour of section 4.2 to a named manufacturer.

The noise conclusion is about the *reported* series. It says the values a consumer receives
carry almost no independent per-sample noise. It says nothing about the raw transducer signal
behind them, which the published error models address and which is not available here.

The five-day within-season control is too short to carry weight and is presented only as a
consistency check.

No outcome data is analysed and none is needed for the question asked, which is about what the
two records contain.

## 10. Conclusion

Compared directly, and without simulating either from the other, a real five-minute record and
a real one-minute record from the same person are the same signal scaled by one number. The
ratio of their variograms is flat at 1.602 across a twenty-four-fold range of lag; their
log-log slopes agree to two decimal places in both bands they share; and below five minutes,
where only the faster sensor can see, the same power law continues with no break.

Neither cadence is noisier. Both report values already filtered to about a fifth of the noise
power that published error models attribute to the transducer, so the smoothing rather than
the sampling interval is what governs how clean the series looks.

Tested on the uses that could plausibly benefit, a predictive low alarm and an automated
insulin delivery forecast, the faster record is not better at any horizon between fifteen and
ninety minutes once the difference in period difficulty is divided out.

The extra samples in a one-minute record are a finer rendering of a curve the five-minute
sensor was already tracing. What the faster feed changes is when you hear about it, not what
there is to hear.

## References

1. Gough DA, Kreutz-Delgado K, Bremer TM. Frequency characterization of blood glucose
   dynamics. *Annals of Biomedical Engineering*. 2003;31(1):91 to 97.
2. Breton MD, Shields DP, Kovatchev BP. Optimum subcutaneous glucose sampling and Fourier
   analysis of continuous glucose monitors. *Journal of Diabetes Science and Technology*.
   2008;2(3):495 to 500.
3. Fico G, Hernanz L, Cancela J, et al. Exploring the frequency domain of continuous glucose
   monitoring signals to improve characterization of glucose variability and of diabetic
   profiles. *Journal of Diabetes Science and Technology*. 2017;11(4):773 to 779.
   doi:10.1177/1932296816685717
4. Vettoretti M, Battocchio C, Sparacino G, Facchinetti A. Development of an error model for a
   factory-calibrated continuous glucose monitoring sensor with 10-day lifetime. *Sensors*.
   2019;19(23):5320. doi:10.3390/s19235320
5. Russon CL, Pulsford RM, Allen MJ, et al. Impact of recording interval in continuous glucose
   monitoring on calculating the metrics of glycemic control. *Journal of Diabetes Science and
   Technology*. 2025;19(2):590 to 592. doi:10.1177/19322968241310892

## Appendix: reproducibility

Analyses are in `backtesting/scripts/2026-07-onemin-cadence/`:

| Script | What it does |
|---|---|
| 20_real_eras_noise_and_signal.py | variograms of both real eras, nugget fits, signal-shape normalisation |
| 21_real_eras_verdict.py | the three variogram tests, with day-level block-bootstrap intervals |
| 22_what_cgms_are_used_for.py | the four categories of use, and forecast/alarm skill at each era's native cadence |
| 23_predictive_horizon.py | the horizon sweep, normalised RMSE and base-rate-free lift with bootstrap intervals |

Scripts `10` to `19` are the earlier decimation-based study. They answer a different question, what a consumer of this signal would lose by sampling it more slowly, and should not be read
as a comparison between sensors. `19` documents the difference between a real five-minute
sensor and a decimated stand-in that motivated the present analysis.
