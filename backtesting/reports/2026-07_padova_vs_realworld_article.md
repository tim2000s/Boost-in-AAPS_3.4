# The simulator the FDA trusts, measured against the people it stands in for

*The UVA/Padova type 1 diabetes simulator has stood in for animal trials in the
pre-clinical testing of automated insulin delivery since 2008. Almost every commercial
closed-loop system reached patients through it. We asked a simple question: across four
independent real-world datasets and every one of the simulator's virtual personae, how
closely does it reproduce the glucose data of the people it is meant to represent?
Everything below is measured, and the analysis is reproducible.*

## The simulator in the middle of the field

In 2008 the US Food and Drug Administration accepted the University of Virginia and
University of Padova type 1 diabetes simulator as a substitute for animal trials in the
pre-clinical testing of artificial-pancreas control algorithms. It was a genuine turning
point. In the years since, essentially no animal experiments have been run to design an
automated-insulin-delivery controller, and six systems now in everyday clinical use,
among them Medtronic's 670G and 780G, Tandem's Control-IQ, Insulet's Omnipod 5, CamAPS
FX and Diabeloop, passed through in-silico testing on this platform on their way to
patients.

The simulator represents a virtual population of type 1 subjects with a validated model
of glucose and insulin dynamics. The full version carries three hundred in-silico
subjects across three age classes; the freely distributed academic version, which the
open-source simglucose package reimplements, carries the canonical thirty: ten adults,
ten adolescents, ten children. When a paper or a regulatory submission says a controller
was tested in silico, this population, or its larger sibling, is almost always what it
means.

That gives the platform real leverage over the field. A controller that looks safe here
earns its clinical trial; a controller that looks dangerous here may never be built. So
it matters, concretely, how faithfully the simulator reproduces the data of real people
wearing real loops. Not whether it is a good model in the abstract, but whether the
specific statistics that decide whether a controller is safe come out looking like
reality.

## The comparison and its fairness

We assembled four independent real-world datasets from a local research database, each a
different automated-insulin-delivery system built by a different community:

| Cohort | Participants | Lineage |
|---|---|---|
| Boost | 9 | a fully closed loop with no meal announcement |
| Trio | 29 | an iAPS and Trio-lineage cohort |
| OpenAPS | 110 | the oref0 lineage from the OpenAPS Commons data-sharing project several of them with multiple years of continuous data |
| AndroidAPS classic | 44 | a pre-dynamic-ISF AndroidAPS cohort |

Together, close to two hundred people and, for many, a year or more of five-minute
continuous glucose data. If four different algorithms worn by different people agree with
each other, that agreement is a strong statement about what real closed-loop glucose data
looks like.

Against them we ran all thirty UVA/Padova personae through simglucose, each for three
weeks, with realistically randomised meals scaled to body weight so that a child is not
handed an adult's dinner. Meals are announced to the controller, because the simulator
has no working unannounced-meal controller. That already favours the simulator, since
announced meals are the easier case. We then computed the same battery of statistics on
every real user and every virtual persona, took each individual's own value, and compared
the distributions with a bootstrap confidence interval, so that no single user or persona
carries a result.

Crucially, we tested against all three persona classes, not just the adults. The age
classes have very different physiology, and it would be easy to wave away a poor adult
match by pointing at the adolescents or children. So for every statistic we ask the
sharper question: does any persona class reproduce it?

## Real-world data agrees with itself

The first result is the one that makes the rest worth reading. The four real cohorts,
built and worn independently, land in a tight band on almost every measure. Glucose
variability sits between 30 and 34% for all four. The spread of where a person ends up
half an hour after a stuck high runs from 27 to 33 mg/dL. A low takes 50 to 59 minutes to
recover to 100 mg/dL, and overshoots above 180 afterwards about a quarter of the time.
High-frequency sensor jitter runs 4.5 to 6.7 mg/dL. Week-to-week insulin-sensitivity
drift runs 8 to 22%.

This convergence is not guaranteed and it is the crux of the method. It means these
numbers describe closed-loop life in general, not one quirky group, and it gives us a
real-world envelope to hold the simulator against.

![Real-world AID cohorts in blue, UVA/Padova personae in warm colours, with bootstrap
confidence intervals. The shaded band on each panel is the real-world range. The four
real cohorts cluster inside it; the personae sit inside it for smoothness and, for the
child, variability, and outside it for every mechanism that makes real-world control
hard.](../scripts/2026-07-insilico/fidelity_suite/fig_multicohort.png)

## The simulator's faithful range

The simulator is not wrong everywhere, and the honest account has to say where it is
right. On the shape of the glucose curve over the short horizon, it is faithful. The
autocorrelation of glucose at thirty and sixty minutes lands inside the real range for
all three persona classes. For smooth, benign, announced-meal stretches, which are the
majority of any day, the simulator behaves like real data, and it remains a reasonable
tool for regression testing and sanity checks.

Overall variability is a more interesting case. With realistic, weight-appropriate meals,
the simulator can reach real-world glucose variability, but only through its child
personae, which are the most variable. The adult and adolescent personae run
persistently smoother than any real cohort, at a variability of 23 to 24% against a real
30 to 34%, and the same is true of the stuck-high outcome spread. Since controllers are
almost always evaluated on the adult personae, the default in-silico test understates the
variability of real life. Reaching realism required us to lean on the personae the field
does not usually test.

## The limits of persona matching

The failures matter more than the passes, because they are exactly the situations a
safety test exists to probe, and because no persona reproduces them at any age.

The fat tail of sudden glucose rises, the fingerprint of an unannounced meal, is missing.
Real cohorts see a sharp five-minute rise about 4 to 7% of the time; the personae, all of
them, sit at 1 to 3%, and their controllers were told the carbohydrate in advance in any
case.

Hypoglycaemia behaves like a different phenomenon. Real lows recover to 100 mg/dL in
about 50 to 59 minutes and then overshoot above 180 roughly a quarter of the time,
because people eat to treat them. The personae take around twice as long, 110 to 120
minutes, and almost never overshoot, because the simulator has no rescue carbohydrate and
can only recover by withdrawing insulin. A controller tuned to look good against the
simulator's slow, monotone recovery is being tuned against a hypo that does not happen.

The sensor is too clean. Real continuous glucose data carries about twice the
high-frequency jitter of the simulator's sensor model, and it produces sharp reversing
compression lows, a few times a month, that the model has no mechanism for at all. A
controller that never has to tell a real low from a sensor artefact has not been tested
on one of the commonest causes of a bad automated decision overnight.

And the model never changes. Real insulin sensitivity drifts 8 to 22% from week to week,
and the loops adapt to it. The virtual patient's parameters are fixed, so its drift is
zero by construction. One caveat belongs here in fairness: our drift measure reads the
sensitivity the algorithm itself used, so the AndroidAPS-classic cohort, which predates
dynamic sensitivity, sits at the low end because its algorithm barely adjusts, not
because the person does not change. The three adaptive cohorts, and the underlying
physiology, drift; the simulator does not.

Five of the eleven statistics we measured are matched by none of the personae, and a
sixth, sensitivity drift, is zero in the model by construction.

## Persona matching as a remedy

It is tempting to read the child persona reaching real-world variability as the simulator
passing after all. It is not. Nobody evaluates an adult controller on the child personae,
and even where the child matches on aggregate variability it still fails every mechanism
above: it treats no hypo with carbohydrate, it produces no compression lows, its sensor
is too clean, and its physiology never drifts. Matching a summary number while missing
the mechanism behind it is precisely the failure mode a safety test should not have.

## Implications for testing under FDA guidance

None of this says the UVA/Padova simulator is a bad model, or that its acceptance was a
mistake. Replacing animal trials was a real advance, and for the questions it answers
well, controller stability on smooth announced meals, gross dosing behaviour, safety-floor
plumbing, it remains valuable. The point is narrower and, we think, important.

In-silico testing on this platform exercises the easy regime and is close to blind to the
hard one. The simulator is smooth, its meals are announced, its physiology is stationary
and its sensor is clean. Real-world automated insulin delivery is defined by the
opposite: unannounced meals, variable insulin efficacy, sensor artefact and drifting
sensitivity. A controller can pass in silico by handling the world the simulator can
represent, and still meet, untested, the world that actually produces the lows and the
stuck highs. That is a gap worth naming, because a regulatory pathway that leans on a
single in-silico platform inherits exactly the blind spots of that platform.

The constructive reading is not to distrust simulation but to widen it. The statistics
here, computed identically on real data and in silico, are the beginnings of a fidelity
checklist: a controller's in-silico result could be reported alongside how far the
scenarios it was tested on reach into the real-world envelope on unannounced-meal rises,
hypo treatment, sensor artefact and sensitivity drift. Where the simulator cannot reach,
the honest answer is that the question is still open, and belongs to real-world evidence.

---

*Method: four real cohorts totalling roughly two hundred users from a local research
database, anonymised, at five-minute CGM cadence, against all thirty UVA/Padova personae
via simglucose, the open-source implementation of the 2008 model, three weeks each with
announced weight-scaled meals. Each statistic is a per-user value aggregated to a median
with a bootstrap 95% confidence interval. Autocorrelation, distributional and mechanism
claims are computed identically on both sides. The structural limitations we probe, no
exercise input, deterministic insulin action, fixed parameters, no sensor-compression
model, are architectural and shared across versions of the simulator. All code, the full
signature-by-cohort matrix, and the figure are committed and reproducible.*
