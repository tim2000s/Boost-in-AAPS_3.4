# The fully closed loop, read from its own data

*Where it is hard, where the community already had it right, and one mistake almost everyone
makes about exercise. Everything below is measured from one small cohort's own records. Nothing
is quoted from the literature, and nothing is a simulation.*

A fully closed loop takes no meal announcement and no carb entry. You eat, and the system finds
out only when your glucose starts to move. For the cohort behind this piece that is not a thought
experiment but ordinary behaviour: across roughly 103,000 decision cycles from nine people over a
month, 92% carried no carbs on board at all. So when the data below talks about "the loop", it
means a system doing the hardest version of the job, reacting to unannounced food and unannounced
exercise with insulin alone.

One honesty note shapes everything that follows. There is no glucodynamic simulator here, so we
cannot generate the counterfactual glucose trace for a dosing change. Detection and mechanism
findings are validated out of sample and are clean. Anything about policy is priced against what
actually happened, and is associational. The cohort is small and self-selected. Read it as careful
observation, not as a trial.

## Exercise after a meal, and the mistake almost everyone makes

Start with the hardest case, because it is also where the data is most surprising. When a meal is
followed by activity within a couple of hours, the chance of a low over the next three hours is
about 23% (95% confidence interval 19 to 27), against roughly 15% (12 to 18) for meals not
followed by exercise. Two very different intervals; a real, roughly one and a half times increase.
That much matches what every experienced looper already knows: exercise after eating is where the
loop struggles.

The universal explanation is dose stacking. The meal triggered a bolus, exercise amplifies it, and
you crash. If that were the mechanism, the people who crash should be carrying more insulin when
the exercise starts. They carry less.

![Crash rate falls as insulin on board rises](figs_postmeal_exercise/fig2_dose.png)

Split the meal-plus-exercise events into thirds by insulin on board at the moment activity begins,
and the crash rate does not rise with insulin; it falls, from 32% at low insulin to 20% in the
middle to 17% at high insulin. Looking at it per event tells the same story: the people who
crashed carried a median of 1.1 units on board, against 1.8 units for those who did not, on an
essentially identical meal bolus, and they started from a lower glucose (116 against 138 mg/dL).
In the post-meal window, more insulin on board is protective, not dangerous.

The reason is that exercise recruits a largely insulin-independent glucose drain, a roughly fixed
downward pull that arrives whether or not insulin is on board. Whether that pull tips you into a
hypo depends on the counterweight present at that moment: how fast carbohydrate is still appearing
from the meal, and how much glucose headroom you have. High insulin, in this window, is a marker of
a large meal still absorbing, and that upward carbohydrate flux offsets the exercise. Low insulin
marks a small or finished meal, or a loop that has already withdrawn insulin on a falling glucose,
so the drain runs unopposed and you fall through the floor.

The practical consequence is worth stating plainly, because it corrects a common misattribution.
The post-meal exercise low is a missing-carbohydrate problem, not a too-much-insulin problem. The
fix is glucose in, or insulin withheld before the fact. It is not a smaller meal dose, and it is
not the loop being too aggressive. The loop's only lever against this is the wrong one, and by the
time the low arrives it has usually already pulled it.

## Two problems, not one, and they pull in opposite directions

Zoom out from the crash to the whole cohort and a second, more useful pattern appears. The people
who spend too long high after meals and the people whom exercise tips low are, almost entirely,
different people.

![Two disjoint groups: high-runners and tight-runners](figs_postmeal_exercise/fig4_bimodal.png)

Plot each person's post-meal time high against their post-meal-with-exercise time low, and the
cohort splits into two clusters that do not overlap. On one side are the high-runners, who spend a
quarter to a third of post-meal time above range with almost no lows; they are under-treated at
meals, and have measured headroom for more insulin. On the other side are the tight-runners, who
barely run high but whom exercise pushes low, some of them well below target. They have no glucose
buffer, so the exercise drain runs straight through.

The people who need more meal insulin are not the people who need protection from exercise. That is
the single most important thing the data says about tuning: there is no one setting that helps
everyone, because the change that helps one group harms the other. The honest headline is a
distribution, not a number, and the honest fix is per-user, not global.

## The post-meal high is about insulin speed, not the algorithm

The high side deserves its own precise diagnosis, because it is easy to blame the wrong thing.

![Time in each glucose zone, by regime](figs_postmeal_exercise/fig3_zones.png)

Away from meals, for roughly 60% of the day including overnight, control is essentially solved:
around 93% time in range, tight variance, lows no worse than average. The deficit is entirely
post-meal. In the clean post-meal window, with no exercise involved, more than one minute in five is
spent above 180 mg/dL (10.0 mmol/L). But the lows in that same window are flat, the same 2.5% you see in the
background. That flatness is the tell. The loop is not over-dosing meals, and it is not being timid;
it is simply too slow to cover an unannounced meal with insulin that takes the better part of an
hour to act. The post-meal high is a speed problem, and no amount of cleverer dosing logic removes
it, because the information and the pharmacology, not the algorithm, are the bottleneck.

## The wall: the loop cannot tell whether its insulin is working

Underneath all of this sits the deepest limit, and it is the reason "a smarter algorithm" keeps
running out of road. During a stuck high the loop typically has plenty of insulin on board doing
nothing, and then over-corrects once sensitivity returns and the same insulin suddenly bites. The
obvious rejoinder is: build a signal that tells the loop whether its insulin is working. We looked
for one, properly, in the cohort's own telemetry.

![Nothing predicts whether the insulin is working](figs_fcl_article/fig_efficacy.png)

There is nothing to find. Asked to predict, out of sample, whether a stuck high will crash or settle,
the glucose trajectory alone lands below chance, the full set of candidate signals lands exactly on
chance, and the loop's own model-deviation signal sits below chance. Even the one dose-independent
candidate we had, a physiological forecaster's estimate of how fast carbohydrate is appearing, does
not separate the crash from the settle at all: the high-appearance and low-appearance stuck highs
crash at an identical rate. The blind spot is not hiding in the data we already record. Closing it
is a sensing problem, and to a lesser extent a faster-insulin problem, not a modelling one.

This matters for expectations. In this cohort, successive generations of the reactive controller are
statistically indistinguishable on every outcome we measured. The reactive ceiling is close, and it
is not going to be pushed much further by a better rule reading the same glucose curve.

## Settled community practice

It would be dishonest to present this as a set of discoveries against a naive field. On most of the
big questions the data simply confirms what experienced loopers and clinicians already believe, and
that is worth saying clearly, because it is the part that should make the rest credible.

Exercise is the hard case, and the answer there is carbohydrate and anticipation rather than a
dosing adjustment. The community's instinct to raise the target before activity, to eat for it, and
not to expect the loop to rescue you is correct; what the data adds is the reason it is correct.
Unannounced meals have a ceiling, and announcing or pre-bolusing raises it. Almost nine in ten of
the highs began with no carbohydrate entered, so people who count and pre-bolus are working around a
measured limit rather than being fussy.

Faster insulin would do more than any algorithm. The post-meal high is speed-bound and the reactive
ceiling has arrived, which is why the field is right to be more interested in insulin kinetics than
in the next controller. Alongside that sits the case for fewer knobs: background control is
effectively solved, the honest number of dials a person needs is small, and the drift toward
simpler self-tuning settings matches what the data shows. Conservative defaults, low-glucose-suspend
floors and a period of watching before trusting all survive the same test. Nothing here argues to
loosen any of them and a good deal argues to keep them.

The realistic ceiling for a fully closed loop is somewhere around 85 to 90 per cent time in range.
This cohort sits at 87 plus or minus 7, which makes the community's calibration accurate.

## Points of disagreement with the data

Two places, gently. The reflexive "the loop over-dosed" explanation for an exercise low is, on this
evidence, usually a misdiagnosis; the crashers carried less insulin, not more. And the hope that an
AI or a better model will close the meal gap is misplaced, because the gap is not a modelling gap.
The loop cannot see whether its insulin is working, and it cannot make the insulin act faster.

## Position

The state of the fully closed loop, read from its own data, is neither triumphant nor bleak. It has
quietly solved the overnight and fasting problem for most people. Its remaining failures are
structural rather than incidental: the post-meal high is the price of silence and slow insulin, and
exercise is the scenario its reactive design cannot cover because the disturbance it needs to answer
is glucose going out, while its only tool is insulin. The next real gains will not come from a
cleverer reaction to the glucose curve. They will come from anticipating the person, which the data
shows is genuinely per-user (predicting an individual's next walk from their own routine is far more
accurate than any pooled model), from insulin that acts faster, and from sensing that can finally
tell the loop whether the insulin it has already given is doing anything at all.

---

*Method and scope: nine people running a fully closed loop, roughly 103,000 decision cycles and
matched continuous glucose data over 30 days, from a local research database. Anonymised. Detection
and mechanism claims are out of sample; policy and attribution claims are associational, in the
absence of a glucodynamic simulator. One participant on a different pump platform lacks a step feed
and is excluded from the activity analyses. Figures are reproducible from the scripts alongside this
file.*
