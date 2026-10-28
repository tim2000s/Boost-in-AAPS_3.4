# Sensor cadence, smoothing, and the ingestion path

What five times as many glucose readings actually carry, and the ingestion path that discards four in
five before any algorithm sees them.

## Abstract

Continuous glucose sensors reporting every minute invite the expectation that a closed loop given
five times as many readings will control glucose better. Comparing 83 days of real five-minute data
against 61 days of real one-minute data from the same participant by variogram, the two eras differ
by a single scale factor of 1.602, flat across every lag from five minutes to two hours, with no
noise floor at either cadence because both feeds are pre-filtered. Short-horizon prediction gains
essentially nothing, at a lift of 9.14 against 9.18, and rate of change is estimated slightly worse
at one minute because a shorter baseline makes differencing noisier. Interstitial fluid lags blood by
roughly four minutes and that lag acts as a low-pass filter, so glucose is already smoothed before
the sensor reads it and sampling a smoothed signal more often does not recover what the smoothing
removed. The gain is latency, worth about two minutes, which is the expected wait for the next
reading on a five-minute grid. Sub-twenty-minute structure is autoregressive sensor noise rather than
glucose. Separately, glucose passes through a bucketing step working on a five-minute grid whatever
the sensor does, so fitting a one-minute sensor to an unmodified loop yields a five-minute view
feeding a five-minute decision.

## Introduction

Faster sensors are a hardware change that requires no algorithmic work to adopt, which makes them an
attractive route to better control and a natural subject for an inflated prior. Two separate
questions are involved and they are usually merged.

The first is whether the additional readings carry additional information about glucose. A sensor
sampling faster than the underlying signal varies is adding samples of noise, and whether that is the
case here is answerable from the structure of the two signals rather than from any control outcome.

The second is whether the software can use the extra readings if they exist. That is a question about
the ingestion path and is answerable by reading it.

A third line concerns artefacts. Sensors produce compression lows when a participant lies on the
sensor, and whether a state estimator can distinguish those from real falls determines whether it can
protect against dosing into them.

## Methods

The cadence work is recorded under `backtesting/scripts/2026-07-cgm-cadence/` and the associated
preprint, using 83 days of five-minute data against 61 days of one-minute data. Structure at each lag
was characterised by variogram, which asks how much the signal varies between points separated by a
given interval and therefore separates real structure from measurement noise without assuming a model.

A cadence view must never be selected by timestamp modulo. Arrival-time jitter means that subsampling
a fast feed on a modulo rule discards the readings nearest the grid points, which cripples the
comparison feed and inflates every comparison made against it.

The smoothing work is recorded under `backtesting/scripts/2026-07-ukf-smoothing/` over 45,698
readings, implementing an unscented Kalman filter with a Rauch-Tung-Striebel smoother and adaptive
measurement noise, mirroring the shipped Kotlin implementation operation for operation in Python and
comparing candidates on identical input.

## Results

The two cadence eras differ by a single scale factor of 1.602, flat across every lag from five minutes
to two hours. Neither feed shows a noise floor. Prediction lift is 9.14 against 9.18. Rate of change
is estimated slightly worse at one minute.

Sub-twenty-minute structure is autoregressive sensor noise rather than glucose.

The filter is tuned to be responsive rather than quiet. Adaptive noise falls toward its floor so the
gain stays high and the estimate tracks the raw signal closely, and a kinetic hypoglycaemia guard
reverts the estimate toward the raw value when glucose is low and falling. It absorbs the least of an
injected compression dip among the candidates tested, at 0.71 against 0.90 for an exponential
smoother.

Glucose passes through a bucketing step operating on a five-minute grid whatever the sensor does, and
the loop is triggered from the newest entry in that series with a guard rejecting any cycle whose
glucose timestamp has already been used.

## Discussion

Fast sensors buy latency rather than information, the latency is worth about two minutes, and two
minutes matters only during rapid movement, which occupies a small fraction of the day. That is a
deflationary conclusion reached before the engineering rather than after it, which is the reason it
was worth reaching.

One consequence runs the other way and was not anticipated. Because the smoothing filter sizes its
windows from the observed spacing of readings, a window meaning ninety minutes is eighteen readings at
five-minute cadence and ninety at one. Estimating measurement noise from ninety samples rather than
eighteen is a materially better-conditioned estimate, and it has nothing to do with responding sooner.
If a fast sensor helps here, it may help through the noise estimate rather than through the response
time, and that is a different design question from the one usually asked.

The ingestion finding applies to anyone fitting a fast sensor to a stock loop, not only to this fork.
Changing the sensor alone changes nothing, because the bucketing step reduces the feed to the grid the
decision already ran on. Extracting value requires changing the software, and the first thing to change
is what decides how often the algorithm runs.

Two limitations bound the claims. Bit-exact agreement between the Python mirror of the filter and the
shipped Kotlin was not formally established, so absolute numbers from the mirror should not be relied
on; the relative ranking is robust because every candidate is fed an identical stream and sub-unit
float drift cannot flip a multi-percent gap. And because the filter is tuned for responsiveness rather
than quietness, no jitter-reduction claim is made for it at all: its value, if any, is in trend and in
artefact rejection.
