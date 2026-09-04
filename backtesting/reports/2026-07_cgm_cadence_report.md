# Sampling rate and information content in continuous glucose monitoring: a within-subject comparison of one-minute and five-minute sensors

*[Authors and affiliation to be added.]*

## Abstract

### Background

Continuous glucose monitors have historically reported at five-minute intervals, and sensors
reporting every minute are now in routine use. It is generally assumed that the faster feed
carries more information about glucose. Existing evidence bears on the question only
indirectly, and the comparisons that have been published derive the slower signal by
decimating a faster one, which conflates the behaviour of a slow sensor with that of a
slowly read fast sensor.

### Method

One adult with type 1 diabetes wore a five-minute sensor for 83 days (24,012 readings) and
subsequently a one-minute sensor for 67 days (84,588 readings). Both records were analysed
as recorded, without decimation or interpolation. The principal instrument was the
variogram, which is expressed in units of lag time and is therefore comparable across
sampling rates, and which separates measurement noise from signal structure by construction.
Forecasting and event prediction were modelled at each sensor's native rate with
cross-validation grouped by day. Uncertainty was estimated by a block bootstrap over whole
days.

### Results

The ratio of the two variograms was constant at 1.602 across all lags observable by both
sensors, from 5 to 120 minutes, with a total spread of 6.6% of the mean and no systematic
trend. Neither record exhibited a measurement-noise floor: at a one-minute lag the variogram
was 4.44 mg/dl^2, which is 22% of the value that a published noise standard deviation of
3.19 mg/dl would impose at every lag. The log-log slope of the variogram was 1.35 (95% CI
1.31 to 1.39) for the five-minute record and 1.35 (1.29 to 1.40) for the one-minute record
over 5 to 20 minutes. Below five minutes the slope was 1.49 (1.18 to 1.71), containing the
value measured above it. Point-to-point acceleration was found to have no rate-independent
value, differing by a factor of 7.65 between the two sensors, close to the factor predicted
from the roughness of the signal. Normalised forecast error was indistinguishable between
records at every horizon from 15 to 90 minutes. Prediction of hypoglycaemia and of
hyperglycaemia was likewise indistinguishable once each record's own base rate was accounted
for. Threshold crossings were reported 2.19 minutes later by the five-minute sensor.

### Conclusion

The two sensors record the same process at the same relative noise, and their records differ
by a single multiplicative constant attributable to glycaemic variability. One-minute
sampling resolves no regime that five-minute sampling fails to imply and confers no
measurable advantage in prediction. Its one demonstrable effect is a reduction of about two
minutes in reporting latency, which is a scheduling property requiring no additional
information. Acceleration computed from consecutive samples is a rate-dependent artefact and
should not be used as a threshold quantity without reference to the interval it was computed
over.

## Introduction

The five-minute reporting interval of continuous glucose monitors is an inheritance from the
first commercially successful devices rather than a considered design choice, and it has
propagated into the systems built upon them. Rate of change is customarily expressed per
five minutes. Look-back windows are frequently specified as counts of samples. Closed-loop
controllers almost universally act on a five-minute cycle.

Sensors reporting at one-minute intervals are now widely worn, and the expectation attached
to them is that a controller or an alarm will see further and sooner. Two distinct claims
are usually conflated in that expectation. The first is informational: that a one-minute
record resolves structure in glucose which a five-minute record does not. This is
falsifiable by sampling theory, since a signal band-limited well below the slower Nyquist
rate cannot contain such structure. The second is a claim about latency: that a system
reading a faster feed learns of an event sooner. This is true by construction and requires
no additional information.

Earlier work bears on the first claim. Gough and colleagues characterised blood glucose
directly and placed its band edge near 1 x 10^-3 Hz, recommending a sampling period of
approximately 10 minutes.1 Breton and colleagues examined the interstitial compartment that
a subcutaneous sensor actually measures, observed attenuation of fast variation relative to
blood, and concluded that interstitial glucose can be characterised with an 18-minute
sampling period.2 Fico and colleagues reported that 75% of spectral power in continuous
monitor signals accumulates by a period of approximately 1.4 hours.3 Russon and colleagues
approached the question from the opposite direction, coarsening five-minute records to
fifteen minutes and finding distributional metrics unchanged while episode detection
deteriorated.5

What has not been reported, to our knowledge, is a direct comparison of records produced by
sensors of differing rate on the same subject. The comparisons available derive the slower
signal by discarding samples from a faster one. That procedure measures the loss incurred by
reading a fast sensor slowly. It does not measure how a slow sensor differs from a fast one,
because commercial devices filter internally before reporting and the filter is matched to
the reporting rate. The present work addresses that gap.

## Methods

### The variogram

The variogram, or structure function, of a signal x observed at time t is

    D(tau) = E[ (x(t + tau) - x(t))^2 ]                                              (1)

the expected squared change over a lag of tau minutes. It is suited to the present question
for two reasons. It is parameterised by elapsed time rather than by sample index, so records
of differing rate may be placed on a common axis without resampling either. It also
separates measurement noise from signal by construction, as follows.

### Separation of noise from signal

Let the observed signal be the sum of a continuous process g and an independent measurement
error of variance s^2. Each difference in equation (1) then contains two independent error
draws, so

    D(tau) = 2 s^2 + D_g(tau)                                                        (2)

Because g is continuous, D_g(tau) tends to zero as tau tends to zero, whereas the noise term
does not. Independent measurement error therefore appears as a floor beneath the variogram
at every lag, including the shortest, and its height is twice the error variance. This floor
is termed the nugget in the geostatistical literature. Its absence is informative: a record
whose variogram descends smoothly to a small value at short lag cannot carry appreciable
independent per-sample error.

### Roughness and its consequences

Over a range of lags the variogram of many natural signals is well described by a power law,

    D(tau) = c tau^alpha                                                             (3)

where alpha characterises the roughness of the signal. A value of 2 corresponds to a smooth
differentiable process and a value of 0 to white noise. The exponent is estimated here as
the slope of log D against log tau, which is invariant to the amplitude of the excursions
and so permits records of differing glycaemic variability to be compared.

The exponent governs the behaviour of finite differences. For any process the mean square of
the second difference over an interval h satisfies the identity

    E[ (x(t+h) - 2 x(t) + x(t-h))^2 ] = 4 D(h) - D(2h)                               (4)

which under equation (3) becomes c h^alpha (4 - 2^alpha). Acceleration estimated from
consecutive samples divides this by h^2, so its magnitude scales as

    a(h) ~ h^(alpha/2 - 2)                                                           (5)

Unless the underlying process is twice differentiable, in which case the leading term of
equation (4) cancels and the next governs, acceleration estimated in this manner does not
converge as the sampling interval is reduced. Its numerical value is then a property of the
interval chosen rather than of the physiology.

### Prediction

Forecasting and event prediction were modelled at each record's native rate. Predictors
comprised the current value together with backward differences over 5, 10, 15, 30 and 45
minutes and ordinary least squares slopes over 15, 30 and 45 minutes. Both records were
therefore afforded identical look-back in elapsed time, the faster record simply containing
five times as many samples within each window. Validation used GroupKFold with whole days as
groups, so that no day contributed to both training and test partitions.

Forecast error is reported as root mean squared error divided by the standard deviation of
the target, for which a value of unity denotes no improvement upon predicting the mean.
Event prediction is reported as area under the receiver operating characteristic curve
together with lift, defined as precision within the highest decile of predicted risk divided
by the base rate of the record. Lift is the appropriate comparator here because the base
rates of the two records differ substantially.

### Reporting delay

A threshold is crossed at an instant lying between two reported samples. The instant was
located by linear interpolation between the bracketing samples and the delay measured to the
next sample the sensor actually reported. No decimation was involved.

### Uncertainty

Glucose is strongly autocorrelated, so intervals computed over individual observations are
inadmissibly narrow. All intervals reported are 95% block bootstraps resampling whole days
with replacement.

### Data

One adult with type 1 diabetes wore a five-minute sensor from 2026-03-01 to 2026-05-23 and a
one-minute sensor from 2026-05-23 to 2026-07-31. The records comprise 24,012 readings over
83 days and 84,588 readings over 67 days respectively. Median inter-sample intervals were
5.00 and 1.00 minutes, with 98.8% and 96.5% of intervals within 30% of nominal.

Glycaemic control differed between the two periods. Mean glucose was 118.4 mg/dl during the
earlier period against 125.6 mg/dl during the later, with coefficients of variation of 25.9%
and 31.1%. Time in the range 70 to 180 mg/dL (3.9 to 10.0 mmol/L) was 93.5% and 86.2%. Time below 70 mg/dl (3.9 mmol/L) was
2.49% and 4.00%, and time above 180 mg/dl 4.00% and 9.80%. The later period was thus the
more volatile, by a factor of approximately 1.44 in variance. Glycaemic variability is a
property of the subject and the period rather than of the sensor, and all comparisons below
are consequently either scale-free or normalised by the base rate of the record concerned.

## Results

### Relationship between the two records

Table 1 gives the variogram of each record at all lags observable by both sensors, together
with their ratio.

Table 1. Variograms and their ratio.

| Lag (min) | Five-minute record (mg/dl^2) | One-minute record (mg/dl^2) | Ratio |
|---|---|---|---|
| 5 | 30.0 (27.3 to 32.7) | 47.5 (42.3 to 52.7) | 1.584 |
| 10 | 79.5 (72.9 to 85.8) | 121.8 (108.8 to 134.1) | 1.533 |
| 15 | 133.4 (123.2 to 143.5) | 210.7 (188.1 to 232.5) | 1.579 |
| 20 | 195.7 (179.3 to 211.1) | 315.1 (282.0 to 348.6) | 1.610 |
| 25 | 267.1 (244.6 to 289.7) | 430.6 (384.0 to 476.5) | 1.612 |
| 30 | 339.6 (310.2 to 369.5) | 556.3 (495.6 to 618.1) | 1.638 |
| 40 | 506.7 (461.7 to 553.5) | 810.6 (716.0 to 902.8) | 1.600 |
| 50 | 658.4 (597.8 to 721.0) | 1063.0 (941.2 to 1185.2) | 1.615 |
| 60 | 794.1 (717.0 to 874.6) | 1283.9 (1130.1 to 1427.8) | 1.617 |
| 90 | 1112.1 (991.5 to 1229.4) | 1787.5 (1560.9 to 1997.7) | 1.607 |
| 120 | 1320.9 (1157.2 to 1485.2) | 2144.9 (1849.7 to 2396.6) | 1.624 |

The ratio averaged 1.602 over a twenty-four-fold range of lag, with a total spread of 6.6%
of the mean. It exhibited no systematic trend, and in particular no departure at the
shortest lags, which are the only lags at which the two sensors could differ. The records
are therefore related by a single multiplicative constant. For comparison the squared ratio
of coefficients of variation was 1.438, so the majority of the constant is attributable to
the change in glycaemic control between the periods.

### Absence of a measurement-noise floor

On the one-minute record the variogram fell to 4.44 mg/dl^2 at a one-minute lag (2.93 to
7.38) and showed no indication of levelling. Vettoretti and colleagues report a measurement
noise standard deviation of 3.19 mg/dl for a factory-calibrated sensor,4 which by equation
(2) would hold the variogram at 20.4 mg/dl^2 at every lag. The observed value is 22% of that
figure, and interpreted as white noise would correspond to a standard deviation of 1.49
mg/dl.

Neither record therefore carries appreciable independent per-sample error. The values these
devices report are not raw transducer output but the product of internal filtering, and it
is that filtering rather than the reporting interval which determines the apparent
smoothness of the series. The preceding section establishes the same point from the other
direction, since there is no lag at which the faster record lies proportionally above the
slower.

### Roughness and the regime below five minutes

Table 2 gives the log-log slope of the variogram by lag band.

Table 2. Variogram exponent by record and lag band.

| Record | Lag band (min) | Exponent alpha (95% CI) |
|---|---|---|
| Five-minute | 5 to 20 | 1.35 (1.31 to 1.39) |
| Five-minute | 20 to 60 | 1.29 (1.24 to 1.33) |
| One-minute | 1 to 5 | 1.49 (1.18 to 1.71) |
| One-minute | 5 to 20 | 1.35 (1.29 to 1.40) |
| One-minute | 20 to 60 | 1.29 (1.24 to 1.33) |

In both bands observable by both sensors the exponents agree to two decimal places with
overlapping intervals. Below five minutes, a region accessible only to the faster sensor,
the exponent was 1.49 (1.18 to 1.71), an interval containing the 1.35 observed immediately
above. The same power law thus extends from one minute to sixty without discontinuity. The
additional samples describe the existing curve more finely rather than revealing a further
regime.

An exponent near 1.3 places the signal well away from either limiting case. It is not a
smooth differentiable process, for which the exponent would approach 2, and it is far from
white noise, for which the exponent would be 0.

### Point-to-point acceleration

On the five-minute record the second difference over one interval had a standard deviation
of 6.32 mg/dl, against 6.36 mg/dl predicted by equation (4) from the variogram with no free
parameters. Acceleration therefore conveys nothing that the variogram has not already
described.

Expressed as mg/dl per 5 min per 5 min so that the two records may be compared, the standard
deviation was 6.32 on the five-minute record and 48.32 on the one-minute record, a ratio of
7.65. Equation (5) predicts 7.53 from the sub-five-minute exponent of 1.49 measured on this
record. A twice differentiable signal would give unity, since acceleration would converge
upon a fixed value as the interval was reduced. It does not converge here. The quantity has
no rate-independent value, and a threshold placed upon it is a threshold at one particular
sampling rate.

The lag-one autocorrelation of the acceleration series was
-0.290 on the five-minute record and -0.049 on the one-minute
record, against a value of -0.667 for twice-differenced white noise. The one-minute series
is accordingly smooth rather than noisy, which follows from the absence of a nugget reported
above and does not by itself imply that the quantity is informative.

Table 3 addresses that last point directly, giving prediction within 30 minutes with and
without acceleration among the predictors.

Table 3. Event prediction with and without acceleration.

| Record | Event | Predictors | AUC (95% CI) | Lift |
|---|---|---|---|---|
| Five-minute | low below 70 | velocity only | 0.8935 (0.8668 to 0.9224) | 7.25 |
| Five-minute | low below 70 | + point to point acceleration | 0.8934 (0.8666 to 0.9223) | 7.22 |
| Five-minute | low below 70 | + controller acceleration | 0.8939 (0.8683 to 0.9220) | 7.29 |
| Five-minute | low below 70 | + both | 0.8938 (0.8681 to 0.9219) | 7.29 |
| Five-minute | high above 180 | velocity only | 0.9283 (0.9058 to 0.9478) | 7.77 |
| Five-minute | high above 180 | + point to point acceleration | 0.9284 (0.9062 to 0.9477) | 7.77 |
| Five-minute | high above 180 | + controller acceleration | 0.9283 (0.9059 to 0.9478) | 7.77 |
| Five-minute | high above 180 | + both | 0.9282 (0.9057 to 0.9477) | 7.77 |
| One-minute | low below 70 | velocity only | 0.9275 (0.9074 to 0.9442) | 7.61 |
| One-minute | low below 70 | + point to point acceleration | 0.9268 (0.9047 to 0.9444) | 7.58 |
| One-minute | low below 70 | + controller acceleration | 0.9276 (0.9070 to 0.9445) | 7.60 |
| One-minute | low below 70 | + both | 0.9268 (0.9042 to 0.9446) | 7.56 |
| One-minute | high above 180 | velocity only | 0.8912 (0.8745 to 0.9069) | 6.39 |
| One-minute | high above 180 | + point to point acceleration | 0.8938 (0.8768 to 0.9091) | 6.44 |
| One-minute | high above 180 | + controller acceleration | 0.8918 (0.8751 to 0.9074) | 6.39 |
| One-minute | high above 180 | + both | 0.8943 (0.8771 to 0.9096) | 6.44 |

Every variant lies within a few thousandths of the velocity-only baseline with overlapping
intervals. Neither the point-to-point form nor the overlapping-window form conveys
predictive information beyond that already carried by the velocity terms, at either sampling
rate.

### Forecasting

Table 4. Normalised forecast error by horizon.

| Horizon (min) | Five-minute record | One-minute record | Intervals |
|---|---|---|---|
| 15 | 0.346 (0.325 to 0.367) | 0.345 (0.322 to 0.369) | overlapping |
| 30 | 0.571 (0.543 to 0.601) | 0.556 (0.519 to 0.600) | overlapping |
| 45 | 0.720 (0.688 to 0.753) | 0.717 (0.676 to 0.767) | overlapping |
| 60 | 0.818 (0.792 to 0.851) | 0.820 (0.780 to 0.868) | overlapping |
| 90 | 0.915 (0.895 to 0.940) | 0.920 (0.891 to 0.954) | overlapping |

Intervals overlap at every horizon examined and the nominally superior record alternates
between horizons. No forecast advantage is detectable in either direction.

### Prediction of hypoglycaemia and hyperglycaemia

Table 5. Event prediction by horizon.

| Event | Horizon (min) | Record | Base rate | AUC (95% CI) | Lift (95% CI) |
|---|---|---|---|---|---|
| below 70 | 15 | 5-min | 1.26% | 0.9581 (0.9428 to 0.9721) | 8.86 (8.23 to 9.43) |
| below 70 | 15 | 1-min | 1.80% | 0.9714 (0.9605 to 0.9801) | 9.16 (8.71 to 9.57) |
| below 70 | 20 | 5-min | 1.75% | 0.9411 (0.9265 to 0.9554) | 8.27 (7.81 to 8.84) |
| below 70 | 20 | 1-min | 2.30% | 0.9595 (0.9450 to 0.9721) | 8.66 (8.06 to 9.11) |
| below 70 | 30 | 5-min | 2.42% | 0.8935 (0.8659 to 0.9226) | 7.25 (6.67 to 7.95) |
| below 70 | 30 | 1-min | 3.30% | 0.9275 (0.9074 to 0.9440) | 7.61 (7.01 to 8.14) |
| below 70 | 45 | 5-min | 3.39% | 0.8232 (0.7895 to 0.8617) | 6.05 (5.44 to 6.73) |
| below 70 | 45 | 1-min | 4.76% | 0.8575 (0.8207 to 0.8857) | 6.23 (5.61 to 6.78) |
| below 70 | 60 | 5-min | 4.37% | 0.7707 (0.7312 to 0.8122) | 5.14 (4.62 to 5.68) |
| below 70 | 60 | 1-min | 6.18% | 0.7925 (0.7487 to 0.8287) | 5.36 (4.79 to 5.93) |
| below 54 | 15 | 5-min | 0.21% | 0.9794 (0.9581 to 0.9972) | 9.62 (8.09 to 10.01) |
| below 54 | 15 | 1-min | 0.14% | not modelled | |
| below 54 | 20 | 5-min | 0.30% | 0.9492 (0.9162 to 0.9776) | 8.43 (7.29 to 9.47) |
| below 54 | 20 | 1-min | 0.17% | not modelled | |
| below 54 | 30 | 5-min | 0.45% | 0.9147 (0.8662 to 0.9674) | 8.08 (7.07 to 9.31) |
| below 54 | 30 | 1-min | 0.24% | 0.9429 (0.9112 to 0.9798) | 8.45 (7.31 to 9.85) |
| below 54 | 45 | 5-min | 0.65% | 0.8319 (0.7758 to 0.9112) | 7.04 (6.17 to 8.22) |
| below 54 | 45 | 1-min | 0.35% | 0.8567 (0.7746 to 0.9480) | 6.84 (5.56 to 8.25) |
| below 54 | 60 | 5-min | 0.88% | 0.7429 (0.6573 to 0.8411) | 5.64 (4.54 to 7.15) |
| below 54 | 60 | 1-min | 0.47% | 0.7744 (0.6592 to 0.9185) | 5.40 (4.17 to 7.09) |
| above 180 | 15 | 5-min | 1.31% | 0.9668 (0.9436 to 0.9842) | 9.35 (8.85 to 9.85) |
| above 180 | 15 | 1-min | 2.85% | 0.9611 (0.9508 to 0.9691) | 8.56 (8.08 to 8.95) |
| above 180 | 20 | 5-min | 1.73% | 0.9525 (0.9336 to 0.9689) | 8.63 (8.14 to 9.12) |
| above 180 | 20 | 1-min | 3.58% | 0.9442 (0.9317 to 0.9543) | 7.80 (7.35 to 8.24) |
| above 180 | 30 | 5-min | 2.39% | 0.9283 (0.9057 to 0.9488) | 7.77 (7.18 to 8.35) |
| above 180 | 30 | 1-min | 5.02% | 0.8912 (0.8731 to 0.9076) | 6.39 (5.99 to 6.80) |
| above 180 | 45 | 5-min | 3.35% | 0.8868 (0.8561 to 0.9135) | 6.65 (6.08 to 7.22) |
| above 180 | 45 | 1-min | 7.07% | 0.8079 (0.7838 to 0.8309) | 4.87 (4.57 to 5.21) |
| above 180 | 60 | 5-min | 4.28% | 0.8413 (0.8086 to 0.8711) | 5.51 (4.97 to 6.06) |
| above 180 | 60 | 1-min | 9.03% | 0.7469 (0.7208 to 0.7709) | 4.04 (3.73 to 4.34) |
| above 250 | 15 | 5-min | 0.05% | not modelled | |
| above 250 | 15 | 1-min | 0.44% | 0.9939 (0.9912 to 0.9968) | 10.00 (9.96 to 10.00) |
| above 250 | 20 | 5-min | 0.07% | not modelled | |
| above 250 | 20 | 1-min | 0.56% | 0.9920 (0.9875 to 0.9962) | 9.93 (9.77 to 10.00) |
| above 250 | 30 | 5-min | 0.11% | not modelled | |
| above 250 | 30 | 1-min | 0.77% | 0.9769 (0.9529 to 0.9939) | 9.53 (8.77 to 10.00) |
| above 250 | 45 | 5-min | 0.16% | not modelled | |
| above 250 | 45 | 1-min | 1.10% | 0.9377 (0.8607 to 0.9890) | 8.91 (7.60 to 9.86) |
| above 250 | 60 | 5-min | 0.21% | 0.9884 (0.9744 to 0.9996) | 10.00 (10.00 to 10.00) |
| above 250 | 60 | 1-min | 1.44% | 0.9003 (0.7964 to 0.9734) | 8.16 (6.59 to 9.40) |

On lift, which is free of the base rate, the two records are indistinguishable throughout.
The area under the curve is nominally higher for the one-minute record in the prediction of
hypoglycaemia and nominally lower in the prediction of hyperglycaemia, the deficit in the
latter widening with horizon. A property of the sampling interval cannot assist prediction
in one direction while impeding it in the other. A genuine advantage of rate would moreover
be greatest at the shortest horizon, where recent detail is most informative, and would
diminish as the horizon lengthened. Neither event behaves in that manner. The differences
track the difficulty of the respective periods.

### Meal climbs

Climbs were defined as a rise of at least 40 mg/dl from a local trough within 90 minutes.
The five-minute record contained 318 such episodes (3.83 per day, median rise 44 mg/dl,
median time to peak 90 minutes) and the one-minute record 318 (4.64 per day, 41 mg/dl, 90
minutes).

Two tasks were posed. The first asks, from a state in which glucose is not currently rising,
whether a climb will begin within the next H minutes. This is anticipation proper, since the
model must fire before the rise is visible. The second asks, once a climb is under way,
whether it will peak within the next H minutes. Both models were trained only on this
subject's own data and are therefore personalised in the fullest sense available.

Table 6. Prediction of climb onset and of climb peak.

| Task | Horizon (min) | Record | Base rate | AUC (95% CI) | Lift |
|---|---|---|---|---|---|
| onset | 10 | 5-min | 2.98% | 0.6741 (0.6415 to 0.7074) | 2.42 |
| onset | 10 | 1-min | 4.28% | 0.6535 (0.6236 to 0.6817) | 2.32 |
| onset | 15 | 5-min | 4.08% | 0.6662 (0.6329 to 0.6964) | 2.30 |
| onset | 15 | 1-min | 6.01% | 0.6269 (0.5959 to 0.6571) | 2.04 |
| onset | 20 | 5-min | 5.20% | 0.6587 (0.6283 to 0.6872) | 2.26 |
| onset | 20 | 1-min | 7.53% | 0.6188 (0.5893 to 0.6456) | 1.84 |
| onset | 30 | 5-min | 7.23% | 0.6334 (0.6064 to 0.6611) | 1.84 |
| onset | 30 | 1-min | 10.61% | 0.6107 (0.5859 to 0.6382) | 1.76 |
| peak | 10 | 5-min | 9.37% | 0.8982 (0.8837 to 0.9121) | 5.09 |
| peak | 10 | 1-min | 12.20% | 0.8821 (0.8688 to 0.8975) | 4.21 |
| peak | 15 | 5-min | 15.40% | 0.8981 (0.8822 to 0.9135) | 4.29 |
| peak | 15 | 1-min | 18.46% | 0.8750 (0.8609 to 0.8920) | 3.64 |
| peak | 20 | 5-min | 21.61% | 0.8922 (0.8715 to 0.9094) | 3.59 |
| peak | 20 | 1-min | 24.66% | 0.8703 (0.8551 to 0.8875) | 3.19 |
| peak | 30 | 5-min | 33.75% | 0.8827 (0.8621 to 0.8979) | 2.64 |
| peak | 30 | 1-min | 37.00% | 0.8594 (0.8457 to 0.8772) | 2.43 |

Onset carries a modest but genuine signal at both rates, with areas under the curve between
0.61 and 0.67 against 0.5 for chance. It is not a strong signal. At the ten-minute horizon
on the five-minute record the highest decile of predicted risk contains 2.42 times the base
rate of 2.98%, which is a precision of approximately 7%.

The approach of the peak is considerably more predictable, with areas under the curve near
0.88 to 0.90 at the ten-minute horizon. This is unsurprising, since the flattening that
precedes a peak is directly observable in the rate of change.

For neither task did the faster record perform better. The difference in area under the
curve favoured the five-minute record at every horizon of both tasks, by between 0.016 and
0.040, with overlapping intervals throughout. Sampling rate is not the constraint on
anticipation.

### Reporting delay

Table 7. Delay from threshold crossing to the next reported sample.

| Crossing | Five-minute record | One-minute record | Difference |
|---|---|---|---|
| below 70 mg/dl | 3.04 min (2.79 to 3.29), n = 110 | 0.86 min (0.80 to 0.91), n = 114 | 2.18 min |
| below 54 mg/dl | 2.27 min (1.72 to 2.95), n = 18 | too few crossings |  |
| above 180 mg/dl | 2.90 min (2.59 to 3.21), n = 101 | 0.71 min (0.66 to 0.76), n = 177 | 2.19 min |
| above 250 mg/dl | too few crossings | 0.64 min (0.54 to 0.72), n = 29 |  |

The mean difference was 2.19 minutes against an arithmetic expectation of 2.00 minutes from
the sample spacing alone.

## Discussion

Two sensors of differing rate worn consecutively by the same subject produced records
related by a single multiplicative constant across every lag they had in common. Neither
carried a measurable noise floor. The faster sensor resolved no regime below the sampling
limit of the slower one, forecast no better at any horizon examined, and predicted neither
hypoglycaemia nor hyperglycaemia better once base rates were accounted for.

These observations are consistent with the earlier literature and supply a direct test of
it. Gough and colleagues placed the band edge of blood glucose near a seventeen-minute
period.1 Breton and colleagues attributed the further attenuation observed in the
interstitium to diffusion between the compartments acting as a low-pass filter, and
estimated that interstitial glucose is fully characterised by an eighteen-minute sampling
period.2 A filter of that kind lies upstream of both devices examined here and is a property
of physiology rather than of electronics. Sampling faster cannot recover content that
diffusion has already removed, which is the mechanism underlying the constancy of the ratio
in Table 1.

The absence of a nugget merits comment, since published error models attribute a noise
standard deviation of approximately 3 mg/dl to these devices.4 Those models describe the raw
transducer signal. What reaches the user has been filtered, and the present data indicate
that the filtering removes the greater part of the error the models describe. A practical
consequence is that the apparent cleanliness of a continuous glucose record is set by the
manufacturer's processing rather than by its reporting rate.

The acceleration result has a bearing on system design. Quantities computed as second
differences of consecutive samples are widely used as inputs to control algorithms and to
alarm logic. Equation (5) establishes that such a quantity has no rate-independent value
unless the underlying signal is twice differentiable, and the exponent measured here places
interstitial glucose firmly outside that class. A threshold calibrated on five-minute data
will be encountered approximately 7.6 times as often, in standardised units, when the same
logic is presented with one-minute data. Constructions that average rates over windows fixed
in elapsed time rather than in samples do not suffer this defect.

The one effect attributable to sampling rate was a reduction of approximately two minutes in
the delay between a threshold being crossed and its being reported, a figure matching the
arithmetic expectation from sample spacing. This is a scheduling property and requires no
additional information about glucose. Its practical value depends upon what consumes it. An
alarm can exploit it in full, as can a subject able to respond immediately. It is small in
relation to the onset of rapid-acting insulin, which is of the order of fifteen minutes.

Several limitations attach to this work. It concerns a single subject, and the comparison is
observational and between periods, so that sensor hardware and glycaemic control both
changed at the boundary. The analysis was designed with that in view, every measure employed
being either scale-free or normalised by base rate, but a single subject cannot establish
generalisation across devices or across people. The makes and models of the sensors were not
recorded in the data available. The conclusion regarding noise concerns the reported series
rather than the transducer signal beneath it. Certain events proved too infrequent to model
in one record or the other and are marked accordingly. No outcome data were analysed, none
being required for the question posed.

The comparison would be strengthened by replication across subjects and across
manufacturers, and by a design in which two sensors of differing rate are worn concurrently,
which would remove the confounding of period with device that is unavoidable in a
consecutive design.

## Abbreviations

AUC, area under the receiver operating characteristic curve; BG, blood glucose; CGM,
continuous glucose monitor; CI, confidence interval; CV, coefficient of variation; IG,
interstitial glucose; RMSE, root mean squared error; SD, standard deviation; T1DM, type 1
diabetes mellitus.

## References

1. Gough DA, Kreutz-Delgado K, Bremer TM. Frequency characterization of blood glucose
dynamics. Ann Biomed Eng. 2003;31(1):91-97.

2. Breton MD, Shields DP, Kovatchev BP. Optimum subcutaneous glucose sampling and Fourier
analysis of continuous glucose monitors. J Diabetes Sci Technol. 2008;2(3):495-500.

3. Fico G, Hernanz L, Cancela J, et al. Exploring the frequency domain of continuous glucose
monitoring signals to improve characterization of glucose variability and of diabetic
profiles. J Diabetes Sci Technol. 2017;11(4):773-779.

4. Vettoretti M, Battocchio C, Sparacino G, Facchinetti A. Development of an error model for
a factory-calibrated continuous glucose monitoring sensor with 10-day lifetime. Sensors
(Basel). 2019;19(23):5320.

5. Russon CL, Pulsford RM, Allen MJ, et al. Impact of recording interval in continuous
glucose monitoring on calculating the metrics of glycemic control. J Diabetes Sci Technol.
2025;19(2):590-592.

## Appendix: reproduction

```
./run_all.sh

01_profile.py          coverage, sampling stability, glycaemic distribution
02_variogram.py        variogram ratio, noise floor, exponents
03_forecast.py         normalised forecast error by horizon
04_events.py           event prediction, AUC and lift
05_reporting_delay.py  delay from an interpolated crossing to the next reported sample
06_acceleration.py     point-to-point acceleration, scale dependence, predictive value
07_meal_climbs.py      prediction of climb onset and of climb peak
08_report.py           regenerates this document from results/*.json
09_style_check.py      house-style gate on the generated document
```

Every figure in this document is read from the stored results. None is transcribed by hand.
