# The simulator we test insulin systems on doesn't look like real life

*A short companion to the preprint "The UVA/Padova simulator versus real-world data: the
case for a new approach to closed-loop testing." The full method, tables and references
are there; this is the argument in brief.*

Almost every automated insulin delivery system you can buy was screened, before it ever
reached a person, on a computer model called the UVA/Padova simulator. Since 2008 that
simulator has been accepted by the FDA as a stand-in for animal trials when testing
closed-loop control algorithms, and it has largely ended animal testing in this field. The
Medtronic 780G, Tandem Control-IQ, Omnipod 5, CamAPS FX and Diabeloop all passed through
it. It is, quietly, one of the most consequential pieces of software in diabetes.

So it is worth asking a plain question: when a controller is judged safe on the simulator,
how much does the simulator actually look like the glucose data of real people on loops?
Until recently that was hard to check, because there was no large body of real-world
closed-loop data to check against. The open-source diabetes community changed that.
Between OpenAPS, AndroidAPS and Trio there are now years of real five-minute glucose data
from hundreds of people, some of it openly shared. We used it.

## Four real datasets, and they agree with each other

We took four independent real-world datasets, each a different loop built by a different
community: a fully closed loop with no meal announcement, an iAPS/Trio cohort, the
OpenAPS/oref0 cohort from the OpenAPS Data Commons, and a pre-dynamic-insulin sensitivity factor (ISF) AndroidAPS
cohort. Close to two hundred people in total, many with more than a year of data.

The first thing we found is the thing that makes everything else meaningful. These four
datasets, built and worn completely independently, agree with each other closely on almost
every measure of glucose behaviour. Variability, the spread of outcomes after a stuck
high, how fast lows recover, how noisy the sensor is: four different systems, one tight
band of numbers. That agreement is a real-world target. It describes closed-loop life in
general, not one quirky group.

## Then we ran the simulator against it, all of it

The simulator ships thirty virtual "personae": ten adults, ten adolescents, ten children.
It would be easy to test only the adults and easy to dismiss a poor result by pointing at
a different age group, so we ran all thirty, with realistic weight-appropriate meals, and
asked for every statistic: does any persona, of any age, reproduce it?

The honest answer has three parts.

The simulator gets the easy things right. The short-term shape of the glucose curve, how
smoothly it moves from one reading to the next, matches real data for every persona. On
calm, announced-meal stretches, which are most of any day, it behaves like real life.

It can reach real-world variability, but only through its child personae. Adults and
adolescents, the ones almost everybody tests on, run persistently smoother than any real
person. The standard test understates how variable real life is.

And on the things that actually make a loop dangerous, no persona of any age comes close.
Real glucose shoots up when someone eats without telling the loop; the simulator's rises
are far gentler, and its controller is told the carbs anyway. Real lows are treated with
food, so they recover in about an hour and often rebound high afterwards; the simulator
has no rescue carbohydrate, so its lows take twice as long and almost never rebound. Real
sensors are noisy and throw sharp false lows from compression; the simulator's sensor is
about half as noisy and never does. And real insulin sensitivity drifts week to week; the
standard model's never changes at all.

Five of the eleven things we measured are matched by none of the personae. A sixth,
sensitivity drift, is zero in the model by design.

## But isn't there a newer version?

There is, and it is a fair objection, so we tested it. The 2013 update added two things that
could plausibly matter: day-to-day variation in insulin sensitivity, and a counter-regulation
model that raises glucose during a low. We built both into the model and re-measured. The
sensitivity change fixed one of our numbers, overall variability, which rose into the real
range, and overshot the daily glucose swing. The counter-regulation sped up recovery from a
low, but only from about 116 minutes to 106, still nearly twice the real 55, because
endogenous glucose release is not the carbohydrate people actually eat. Everything else, the
unannounced-meal spikes, the untreated-low rebound, the sensor artefacts, did not move,
because none of it depends on either change. Refining the physiology helps the physiology and
does little for the disturbances the model still cannot see.

Three things still hold. The newer versions are not what the open community uses; the free
2008 model is, and the algorithms built on it inherit its blind spots. Even with the newer
sensitivity model, every meal is still announced, no low is ever treated with carbohydrate,
and the sensor still has no compression artefact, which are the very things driving most of
our failures. And most importantly, no version has been checked against the real-world numbers
we measured here. "The new version fixes it" is itself a claim that should be measured, not
assumed.

## The case for a different approach

None of this means the simulator is bad, or that its acceptance was a mistake. Replacing
animal trials was a genuine advance, and the model is good at what it is good at. The
problem is narrower and more fixable: we treat the simulator's resemblance to real life as
settled, when it is something we can now measure, and on the numbers that matter for safety
it does not hold.

A controller can pass in silico by mastering the world the simulator represents, and still
meet, completely untested, the world that actually produces the lows and the stuck highs.
That gap is worth naming, because a testing pipeline that leans on one simulator inherits
exactly that simulator's blind spots.

The fix is not to distrust simulation but to measure it and to widen it. Three steps, from
ready-now to further-out. First, make fidelity a reported number: any in-silico safety
result should say how far its test scenarios reach into the real-world range on unannounced
meals, hypo treatment, sensor artefact and sensitivity drift. Second, keep the trusted
physiological model but bolt onto it the specific things we measured to be missing, each
fitted from the real data that now exists. Third, further out, use the real datasets
themselves as the test, replaying the disturbances real people actually meet.

We have years of real-world evidence about how closed loops behave. It is time our testing
used it.

---

*The full analysis, with the method, the complete results table, the figure and the
references, is in the accompanying preprint. All of the code is open and reproducible.*
