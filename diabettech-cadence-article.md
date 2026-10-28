# Four loops, one body: what a one minute sensor actually changes

*The usual preamble. Everything here is experimental, runs modified code that is in no released
version of AndroidAPS or Trio, uses insulin off-label, and is not medical advice. It is an n=1,
shared in the #WeAreNotWaiting spirit. Take the ideas rather than the settings.*

---

Sensors that report every minute are here, and the assumption travelling with them is that a closed
loop given five times as much data will control glucose better. I have spent some months trying to
establish whether that is true, and I am now running four copies of my loop at once to find out what
a faster feed changes before asking whether it helps.

## What the offline work said

I had access to a one minute dataset from another person running this system. It is not mine to
publish, so there are no charts of it here.

Three things came out of it. Comparing a real five minute period against a real one minute period,
the two series differ by a single scale factor which is flat across every lag from five minutes out
to two hours, so the faster feed carries the same shape rather than additional structure at short
range. Short horizon forecasting gained nothing measurable from the extra readings. Rate of change
was estimated slightly less accurately at one minute than at five, because a shorter baseline makes
the estimate noisier and differencing amplifies that noise.

The likely reason is physiological. Interstitial fluid lags blood by roughly four minutes and that
lag behaves as a low pass filter. Glucose has already been smoothed by the time the sensor reads it,
and sampling a smoothed signal more often does not recover what the smoothing removed.

## The part that applies to everyone

There is a more prosaic obstacle, and it affects anyone fitting a fast sensor to a stock loop today.

Glucose arriving at AndroidAPS or Trio passes through a bucketing step before the algorithm sees it,
and that step works on a five minute grid regardless of what the sensor does. The loop is then
triggered from the newest entry in that series, with a guard that discards any cycle whose glucose
timestamp has already been used. Fit a one minute sensor to an unmodified loop and you get a five
minute view feeding a five minute decision, with four fifths of the readings discarded during
ingestion.

This is no criticism of oref, which was written around the sensors that existed at the time. It does
mean that anyone expecting an improvement from changing the sensor alone will not get one. Extracting
value from a faster feed requires changing the algorithm, and the first thing that has to change is
the thing that decides how often the algorithm runs at all.

Getting that right took longer than I expected, for a reason worth passing on. The grid the bucketing
works on is anchored to a reference time, and that anchor is held on an object which the calculation
path copies, works on, and copies back. The copy did not carry the anchor. Every cycle therefore
installed a version with no anchor, the next pass re-anchored the grid to the newest reading, and the
five minute grid quietly became a one minute one. At five minute cadence this is invisible, because
re-anchoring to the newest reading and holding a five minute grid are the same thing when readings
arrive every five minutes. It took a sensor faster than the grid to make it visible at all, and the
symptom was an arm of my own experiment running at the wrong cadence while its setting said
otherwise.

## Where a faster feed might still help

If the shape of the signal is unchanged and prediction does not improve, the remaining candidate is
timing. On a five minute grid a reading arrives and the loop waits five minutes for the next one.
Glucose that begins falling thirty seconds after a reading is invisible to the loop for four and a
half minutes. A one minute feed conveys the same information an average of two minutes earlier.

Two minutes is immaterial when glucose is drifting, which describes most of the day. During a rapid
fall it is a larger fraction of the time available to respond, and it is the difference between
reducing insulin promptly and reducing it late. My expectation is that any benefit is confined to
fast movement and is undetectable in aggregate measures, because those measures are dominated by the
periods where nothing is gained.

There is a second candidate I had not expected, which is that some of the loop's internal machinery
is quietly better conditioned on more data. The filter that smooths incoming glucose adapts its
window from the observed spacing, so a window meaning ninety minutes is eighteen readings at five
minute cadence and ninety at one. Estimating the sensor's noise from ninety samples rather than
eighteen is a real improvement, and it has nothing to do with dosing faster. It would be an odd
outcome if the benefit of a fast sensor turned out to be a better noise estimate rather than a
quicker response, but it would not be an uninteresting one.

## Why an outcome trial will not settle it

The obvious experiment is to wear a one minute sensor for a month, wear a five minute sensor for a
month, and compare time in range. I calculated what that could detect before taking it seriously.

My own day to day variability in time in range has a standard deviation of about nine percentage
points, measured over 178 days. With a month in each arm, allowing for the correlation between
consecutive days, the smallest difference detectable at conventional levels is around seven
percentage points against a baseline of eighty five per cent. An improvement of that size would put
me at ninety two per cent on the strength of a two minute timing gain, which no proposed mechanism
supports. Running the trial and reporting no significant difference would be uninformative, because
the result would be indistinguishable from a study too small to detect anything.

This is a specific case of a constraint that governs all of my analysis. I can observe what the loop
decided and what glucose subsequently did. I cannot observe what glucose would have done had the loop
decided otherwise, because that trajectory does not exist and no amount of modelling produces it.

## The study

Rather than asking whether a faster sensor produces better outcomes, I am asking first whether it
produces different decisions, which can be established exactly and without exposing anyone to an
intervention.

Three copies of AndroidAPS run on one phone, fed from a single one minute sensor. A fourth runs on a
second phone with its own five minute sensor, because a five minute view and a one minute view cannot
be taken from the same sensor at the same time. That fourth instance is connected to the pump and is
my ordinary therapy, unchanged. The others use the virtual pump: they run the full algorithm, decide
what they would deliver, record it, and deliver nothing.

| arm | sensor | glucose supplied | decision taken | earliest possible bolus |
|---|---|---|---|---|
| A | its own, on a second phone | every 5 min | every 5 min | 5 min |
| B | the one minute sensor | every 1 min | every 5 min | 5 min |
| C | the same one minute sensor | every 1 min | every 1 min | 1 min |
| D | the same one minute sensor | every 1 min | every 1 min | 3 min |

B, C and D see identical glucose arriving at the same instant and differ only in what the software
does with it, so those comparisons are clean. C and D differ only in how closely spaced automated
boluses may be, with both deciding every minute, which separates delivery frequency from decision
frequency. Without D there would be no way to attribute a difference between B and C to one or the
other, since they vary in both.

A is a control rather than a contrast. It differs from B in sensor, sensor site, phone and cadence
simultaneously, so a difference between them tells me nothing about cadence. What it does tell me is
how much the arms diverge for reasons that have nothing to do with software, because two sensors on
one body disagree through calibration, site and lag alone. That figure is the noise floor for the
whole study. If B and C differ by no more than A and B do, the design is not sensitive enough to
answer the question, and that is the conclusion I would have to report.

One thing worth saying about B, because the arm is easy to misread. B is not a stock loop. It
receives one minute glucose and computes its deltas from one minute data; what it does not do is
decide more than once every five minutes. The comparison between B and C is therefore a comparison of
decision rate with the data held constant, which is the question I want, rather than a comparison
between a fast sensor and a slow one.

Each copy runs its own complete loop and accumulates its own insulin on board from its own decisions.
That matters because a loop dosing more often builds a different insulin trajectory, and the caps and
brakes that respond to insulin on board then engage differently. Restricting the comparison to a
single cycle would miss that interaction, which is a large part of what distinguishes the arms.

## What I expect

I think A and B will be close to identical. I think C and D will differ in the timing and granularity
of delivery rather than in total insulin, because the caps and brakes will absorb the additional
opportunities. I think most of any difference between B and C will turn out to be the extra dosing
opportunities rather than the faster decision.

I am recording that in advance because a prediction made after the fact is not a prediction. The
result I would find most interesting is a difference confined to periods of rapid change, since that
corresponds to the one place the earlier analysis left a signal. My expectation is a null result,
which would indicate that the five minute grid was never the limiting factor and that effort is
better directed elsewhere.

## Limitations

The glucose those three copies observe responds to the insulin my pump delivered rather than to the
insulin they believe they delivered, so their internal state is self consistent but counterfactual.
The gap does not grow without limit, because insulin decays. It settles at roughly the difference in
dosing rate multiplied by the mean time a unit hangs around, which for my curve is about seventy five
minutes, so a copy dosing ten per cent more than reality is carrying about 0.05 U that does not exist
against the 1.6 U I typically have on board. The copies therefore run without resetting. I record the
offset and report it anyway, because that is a prediction about how they will behave and it might not
hold.

The study measures decisions and not outcomes. No time in range figure appears anywhere in it. If the
four copies agree closely then the outcome question is largely answered by implication, and nobody has
been experimented on to learn it. If they disagree, the circumstances of the disagreement indicate
where a properly targeted trial should look.

Three instances share one processor and one battery, so cycle timing is recorded and checked before
any comparison is made. It is a single participant wearing two sensors, and none of it generalises.

I will report what happens.
