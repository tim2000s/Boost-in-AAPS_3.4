# Boost: the current design, and what measuring it has changed

*The usual preamble, because it matters. Everything described here is highly experimental. It uses insulin in an off-label fashion, it isn't in any released, supported version of AndroidAPS or Trio, and nothing here is medical advice. It's an n=1 that's grown into a slightly-larger-than-n=1, shared in the open-source, #WeAreNotWaiting spirit so the learning is useful to others. Take the ideas, not the dose settings.*

---

I've written about Boost here a few times: when it was [a possibility](https://www.diabettech.com/fully-closed-loop-with-an-open-source-aid-system-a-possibility/), when I ran it as [an n=1 experiment](https://www.diabettech.com/the-insulin-only-full-closed-loop-an-n1-experiment/) and reported back on four months of it, and when I wrote about [bringing step counts into the loop](https://www.diabettech.com/everybodys-moving-integrating-stepcounts-into-open-source-automated-insulin-delivery/). If that's where you last left it, quite a lot has changed since, and the version I run now doesn't much resemble the one in those pieces.

So this is an update, and a slightly different sort of one. At some point I stopped adding things to Boost and started measuring the things already in it, which is a different activity and tends to retire more than it confirms. What follows is what Boost was for, how it got from tiers to what it does now, what's in it, where the machine learning sits, and which parts of it have earned their place.

## What it was for

Boost has one job, and it's the same job it had at the start: run a closed loop without telling it about food.

That's a harder ask than it sounds, and the reason is insulin, not software. Injected under the skin, insulin takes the best part of an hour to do most of its work. A meal is largely absorbed inside that window. So if you wait until the rise is obvious before you dose — which is what a conservative loop does, quite sensibly — you're always behind it, and no amount of cleverness afterwards gets that time back.

The original Boost kept the whole AndroidAPS engine and replaced exactly one thing: the decision about how big the next micro-bolus should be. Basal, dynamic sensitivity, the predictions and **every safety gate** stayed exactly as they were. That constraint was deliberate, it's still there, and it's the main reason I've been willing to run this on myself for as long as I have. The parts that stop you coming to harm are the parts that have been stopping people coming to harm for years.

What went in place of that one decision, first time round, was a ladder of eight tiers, each licensing a bit more aggression than the last. No machine learning, no models: a set of rules about glucose, its rate of change and its acceleration, and a decision each cycle about which rung to stand on. Be braver into a rise than a stock loop dares to be, and rely on the safety gates underneath to catch anything that went too far.

It worked, in the sense that it produced a usable fully closed loop: 81.2% time in range and 5.6% below over four months. It also produced post-meal highs I wasn't thrilled about and lines noticeably wider than my hybrid setup, and I said so at the time.

## How it got here

The lineage runs V1, V2, V3, v4.4, v4.4.2, then V6, with a V7 in shadow now, and the version numbers matter a lot less than what changed underneath them.

The eight tiers were discrete dosing modes and the algorithm picked one each cycle. That has an obvious problem, which is that the world isn't eight states and a tier that's right at minute zero of a meal is wrong by minute forty. It has a less obvious one too, and that's the one I couldn't tune my way out of: how hard to push and how much to hold back were decided together, inside the same rung. Every time I made Boost braver at chasing a meal I made it more dangerous two hours later, and I spent a long time trading one against the other without ever getting both.

V6 stopped asking which tier it was in. It now carries a meal hypothesis across cycles and scales what it does to how confident it is. Idle, when nothing's happening and the underlying loop just gets on with its job. Observing, when something might be starting, where it leans in gently rather than committing. Confirmed, when the evidence is good enough. Committed, while the meal is clearly running. And recovering, as the insulin takes hold.

Recovering is the state that did the most for me. Before it existed, a loop watching glucose come down from a meal peak would look at a number that was still high, conclude it was still high, and dose again, having no representation at all of the fact that it had already dealt with this. Recovering winds down on purpose instead. The post-meal lows I used to live with mostly went away when that arrived.

The deeper change is that confidence and restraint are now decided in different places. I can make Boost keener at recognising a meal without simultaneously making it more aggressive about acting, because the brakes sit outside the thing that forms the hypothesis. That was never possible with the tiers, and it's why the last year has been a matter of adding and testing components rather than endlessly retuning one knob against another.

The machine learning came later and separately. It went in as a plugin of its own partway through this year, purely as a hypo-risk score whose only power was to shrink a dose the rules had already chosen, and was retrofitted into the earlier engines once it had shown it did no harm. It has never been the thing that decides to dose.

The other significant change is that the settings stopped being mine. Early Boost had knobs, the knobs had defaults, and the defaults were whatever suited me, which is fine for an n=1 and useless for anyone else. The group running it now spans total daily doses from 16 to 58 units, with one person on U200 where a unit carries roughly twice the mass. V6 derives each person's settings from their own history, tightens for anyone whose time below range says it should, and re-derives periodically rather than once at setup. Anything that adds insulin only switches itself on for someone whose glucose is already sitting comfortably.

Across the group, a fully closed loop with no meal announcement currently runs around 87% time in range give or take 7, with severe lows well under 1%. That's the ceiling as far as I can see it, and it's not far off what most experienced loopers would guess it should be.

## What's actually in there

The meal state machine is the core. Around it:

- A **composed brake** — restraints that compound rather than override each other, and which audit at about 90% correct when they fire.
- **Absolute floors** under everything. Time-below-range limits that can only ever tighten, and which no statistical argument is allowed to loosen. That rule has saved me from myself more than once.
- **Caps** on how much insulin can go to a single meal, and on cumulative micro-bolus volume in a rolling window.
- A **sleep detector** built from heart rate and step activity rather than a clock, which learns your usual sleep and wake times and suppresses the aggressive tiers overnight. Overnight is where a fully closed loop can hurt you, because nobody's watching and a meal-shaped rise at 2am is almost never a meal.
- **Steps as a live input**, blended across phone and watch, withdrawing insulin when you're active.
- **Heart rate**, which is wired in and off by default.

Heart rate deserves a note, because it's the one part of this I've built out properly and then left switched off for most people. When it's on, a Garmin or Wear watch feeds heart rate in, and Boost classifies it into Karvonen zones and an exercise state: vigorous aerobic, moderate, light, resistance, stress, resting. Vigorous aerobic pulls the profile back a further 10% and raises the target; resistance and stress raise the target without touching the profile, because those raise glucose rather than lowering it. The reference points for all of that are learned from you rather than assumed, with resting heart rate taken as the median of the tenth percentile during sleep and the daytime figure the same statistic while awake, neither available until you've accumulated about a week of nights.

There's one branch of it I'd keep even if I switched off everything else. Boost has an inactivity behaviour that raises insulin when you've been sitting still, and a heart rate at or above moderate suppresses that entirely. Sitting still with a heart rate of 130 is not the same as sitting still, and steps alone can't tell you which one you're in. Cycling, rowing and lifting all look sedentary to a pedometer.

The reason it's off by default is boring rather than principled: it needs a watch that reports reliably, and overnight heart rate collection on Wear has died on me repeatedly through the OS killing the listener. If you're wearing something that behaves, it's worth turning on. If you're not, the steps path covers most of it.

And underneath all of it, the bit I'd most want anyone else building this sort of thing to copy: nothing reaches the dose path without running as a shadow first. A shadow computes what it *would* have done, writes it to the log, and delivers nothing. It runs like that across everyone for as long as it takes to build up evidence, and only then does anyone argue about it.

That last part is where most of this year's work has gone, so it's worth going into.

## Which of the shadows earn their place

Thirteen components run in shadow at the moment. Scoring them against the outcome each one claims to
predict is how anything gets promoted here, and it's also how things get dropped.

The clear success is the **accelerating-meal detector**. It fires on 8.8% of cycles, and 40.6% of
those are followed by a rise of at least 1.7 mmol/L within 45 minutes, against a background rate of
19.6%. That's measured on 154,000 cycles across eleven people. Roughly double the base rate, at a
firing rate low enough to act on, is exactly what you want from something whose job is to notice a
meal starting when nobody has announced it. It's the strongest detection result anywhere in the
system, and it's the one I'd build on next.

The **physiological forecaster** is the interesting near-miss. It's a proper ensemble Kalman model
of glucose and insulin, and its thirty-minute prediction does beat "assume glucose stays where it
is" by about 0.06 mmol/L of error, consistently and across nearly everyone. That's a real result and
a clinically meaningless one. What it actually taught me is how good "assume nothing changes" is
over half an hour, which I hadn't appreciated and which is worth knowing before anyone builds
another forecaster.

![Four shadow components scored against what each claims to anticipate](backtesting/reports/figs_boost_evolution/fig1_shadow_verdicts.png)

*Four of them against the thing each says it predicts. A lift of 1.0 means it's telling you nothing you didn't already know.*

Three are being dropped. A component estimating whether a rise will end somewhere that matters
scores 0.730, where the current glucose reading on its own scores 0.785. An anticipatory backout
barely separates the cycles it arms on from the ones it doesn't. And a plateau detector, which looks
for a high that's stuck and proposes a small nudge, turns out to flag highs that come down slightly
*better* than the ones it ignores, so it's finding highs that are already resolving rather than
stuck ones. That last one matters more than the other two, because adding insulin to a recovering
high is the specific thing that everything I've learned says not to do.

Two more had faults rather than verdicts. One returned a bare null on every rejection, so a model
that failed to load and a genuinely quiet day looked identical from outside. The other asked for the
day's insulin total through a function that refuses the whole window if any moment in it lacks a
profile, and then gave up silently. Both are fixed and both are now running properly for the first
time, which means they get scored on the next pass rather than this one.

## Where the machine learning actually sits

Two models are on the dose path. Both are gradient-boosted trees, trained offline, exported as JSON and walked on the phone by about fifty lines of Kotlin in a few milliseconds. **Nothing trains, learns or adapts inside the loop.** That's a rule, not an implementation detail. A system that learns while it doses can learn something wrong while it doses.

One estimates the probability of a sustained hypo and can only ever reduce a dose. The other estimates the probability that an unannounced meal is starting, and it's the only learned thing allowed to *add* insulin, which is why it gets the harder look.

I refitted the hypo model on 183 people from the OpenAPS Data Commons — about eleven million decision cycles — against the 32 it was originally trained on. On 1.7 million rows where both old and new are out of sample, the refit scores 0.861 against 0.847, which is a real improvement and a small one.

Except it isn't small where it counts, and working out why explained something that had been nagging at me. The model is only consulted on cycles that get past the low-glucose guard, which is about half of them, and the half it never sees carries most of the hypos. Judged on the population where it actually acts, the refit's advantage roughly triples. It also explains why the shipped model scores 0.85 on the Commons and somewhere between 0.52 and 0.72 on the people running it: it's being marked on the hard half.

![Area under the curve as the highest-risk cycles are removed](backtesting/reports/figs_boost_evolution/fig2_truncation.png)

*Take out the cycles the low-glucose guard already handles and both models fall a long way. The refit's lead over the shipped one widens as they go.*

Then I made a mess of the calibration, twice. The refit ranks better but reads on a completely different scale — fed to the existing thresholds it would restrain insulin six times as often. So I built a conversion table from the Commons data. That was wrong too, because this group isn't a Commons sample. The rate at which the current model triggers its damper runs from 0.26% of cycles for one person to 39.8% for another, against 6.6% on the Commons.

![Each participant's own damper trigger rate against the Commons figure](backtesting/reports/figs_boost_evolution/fig3_firing_rates.png)

*Everyone's own trigger rate, against the population I'd built the conversion from. There's no single threshold that sits sensibly across that.*

You can't calibrate a group against a population that doesn't look like them. It has to be per-person, from each person's own shadow data, and that needs everyone running the shadow build for a week.

Two more are in the pipe. One asks whether a fall that's already twenty minutes old is going to end below 3.9 — it scores 0.780 on the sixteen people who contributed no training data at all, against 0.746 for glucose plus the time of day, and it's better for every one of those sixteen. The other isn't a model, it's a feature: a person's own hypo rate by hour of day turns out to be worth more than tripling the training set was. The *population's* hour-of-day rate is worth nothing at all.

That last one is the result I keep coming back to. Scaling the training data stops paying somewhere around 112 people. Whatever's left in this system looks like it's in each person's own history rather than in bigger models, which is a less interesting answer than I was hoping for but a more practical one.

## What's next

Getting everyone onto the shadow build, so the refit can be calibrated per person and the fall model can be scored on somebody other than me. Then the fall model as a restraint in the safety gates, where it can only ever withhold. Then the personal hour-of-day feature, once it's been replicated with a different split, because one result from one design isn't enough to build on.

Further out, a pre-meal exercise mode. Exercise near a meal is where these systems fail people most often, the published guidance is fairly specific about what to do, and almost all the machinery it asks for already exists here wired to something else. What's missing is any way to tell the loop that exercise is coming, carrying when, what kind, how hard and how long. Everything you can currently tell it carries a target, a duration and a reason from a list of six, and starts immediately, so closing that gap is most of the work.

It'll be a declaration rather than a detector, and that's settled by one number. Announced exercise with a reduced bolus, announced with a full bolus, and unannounced give 2.0%, 7.0% and 13.0% time below 3.9. Nothing in the detection literature separates two approaches by anything like that much, and a trial of automatic detection from wearables couldn't be told apart from simply asking the person to confirm.

Two changes I've made to my own setup are worth reporting, because one of them went badly and the other went nowhere, and both are more informative than they sound.

I moved to a one-minute loop cycle. On the face of it that should be strictly better: more information, faster reaction. It delivered 22% more insulin a day at the same glucose, and my time below 3.9 roughly doubled. Matched on glucose it dosed more in every band, and at 6.1 to 7.2 mmol/L, where nothing needs correcting at all, it was giving 1.26 units an hour against 0.45.

![Delivery and time below range across the three settings](backtesting/reports/figs_boost_evolution/fig4_cadence.png)

*Me, 28 days across the two changes. Fixing sensitivity took two points off time below range. Going to a one-minute cycle put considerably more back on, and raised delivery with it.*

The fix wasn't to cap anything. It was to separate the two rates that had been quietly welded together: the loop now still *decides* every minute, but it can only *deliver* a micro-bolus every three. Faster sensing was never the problem. Dosing at the speed of sensing was, because insulin doesn't arrive at the speed of a decision, so each cycle was correcting a glucose that its own previous dose hadn't had time to move. On the first day of the split, micro-boluses per day dropped from 127 to 46, the insulin they carried from 29.8 units to 17.8, and time in range went from 78.8% to 91.5%. That's one day and I'd want a fortnight before I'd put much weight on it, and the severe-low figure actually went the wrong way over the same period, so I'm still watching. But the direction is unambiguous and the mechanism makes sense.

The other change was switching from dynamic ISF to a fixed one, and that went better than I expected. Time below 3.9 fell from 5.5% to 3.5%, which is two percentage points and about a third less in relative terms, and it came with roughly four points less time in range and a mean about 0.4 mmol/L higher. That trade is exactly the shape you'd expect from a loop giving slightly less insulin, and for someone whose time below range was the thing I actually wanted to shift, it's the right direction.

The honest caveat is that the interval on that runs from 4.8 points better to 1.0 worse, because there are only six days in the fixed arm. So the point estimate is a third less time below range and I can't yet distinguish it from chance. That's underpowered rather than negative, and it's a very different statement from "no effect", which is what a bare significance test would have told you.

It also fits what I found when I went looking at this properly earlier this year, across about 115 looping people and millions of decisions. The finding then was that a well-set static ISF already matches what the loop does and beats the dynamic equations, with the steepest form doing worst. The honest relationship between sensitivity and total daily dose came out gentle, roughly 1/√TDD, not the 1/TDD or 1/TDD² the equations assume.

The part of that I still find most interesting is what happened when carbohydrate was taken out. In genuinely carb-free fasting windows the effective sensitivity doesn't fall as glucose rises at all. If anything it's lowest near target, which is the body defending against a hypo, and flat or rising up high, which is the opposite shape to the one Dynamic ISF applies. The falling pattern lives around food rather than around high glucose, and for someone who doesn't announce carbs it's a daytime effect that mostly disappears overnight.

I offered a candidate explanation then and I'd still offer it carefully now: some of what a glucose-driven ISF does may be compensating for carbohydrate the absorption model hasn't caught, rather than correcting a minute-to-minute loss of sensitivity. That's a suggestion, not a settled finding, and it's not a criticism of Dynamic ISF or anyone's carb model, because the meal tail is genuinely one of the hardest things to estimate from CGM. But it lands awkwardly for a loop like this one. Boost doesn't announce carbohydrate at all, so if the glucose term is partly a proxy for unannounced food, then Boost has been leaning on it for exactly that, and the fact that removing it cost me nothing, and may have taken two points off my time below range, is at least consistent with the meal state machine already doing that job.

None of which is where I expected to be when I started writing this. I sat down to describe a set of features and ended up spending most of it on what happened when I checked whether they worked.
