# Boost: what it was, what it became, and where the machine learning actually sits

*The usual preamble, because it matters. Everything described here is highly experimental. It uses insulin in an off-label fashion, it isn't in any released, supported version of AndroidAPS or Trio, and nothing here is medical advice. It's an n=1 that has grown into a slightly-larger-than-n=1, shared in the open-source, #WeAreNotWaiting spirit so the learning is useful to others. Take the ideas, not the dose settings.*

---

I get asked what Boost actually is often enough that it's worth setting out properly: what it was built to do, how it changed, what's in it now, where machine learning fits, and what's coming. Some of what follows is less flattering than the last time I wrote about it, because a good deal of measurement has happened since, and measurement has a habit of retiring things you were fond of.

## 1. The original design

Boost has one job: run a closed loop without announcing meals.

That sounds like a small ask and it isn't. Every automated insulin delivery system on the market assumes you tell it about food, and the ones that tolerate an unannounced meal do so by correcting after the fact. Correcting after the fact is exactly what the physics won't let you do well. Insulin injected under the skin takes the best part of an hour to do most of its work, and a meal is largely absorbed inside that window. If you start dosing when the rise is already obvious, you are always behind.

The original Boost kept the entire AndroidAPS engine and replaced exactly one thing: the decision about how big the next microbolus should be. Basal, dynamic sensitivity, the glucose predictions and every safety gate stayed as they were. That constraint was deliberate and it still holds. It means the parts of AndroidAPS that stop you coming to harm are the same parts that have been stopping people coming to harm for years, and the experimental surface is small enough to reason about.

What went in its place, in the first version, was a ladder. Eight tiers, each one a set of conditions about glucose, its rate of change and its acceleration, and each one licensing a more aggressive microbolus than the last. Alongside it went a small machine-learning model that estimated the probability of going low in the next four hours, whose only power was to shrink the dose the ladder had just chosen. The shape of the idea was: be braver than stock into a rise, and put something in the way that can pull you back.

It worked, in the sense that it produced a usable fully closed loop. I reported 81.2 per cent time in range and 5.6 per cent below over four months, with wider lines than my hybrid setup and post-meal highs I wasn't thrilled about.

## 2. The evolution

The line runs V1, V2, V3, v4.4, v4.4.2, then V6, with a V7 in shadow now. The version numbers are not interesting. Two changes are.

The first is that the loop grew a memory. The ladder decided everything from scratch every five minutes, which meant it had no way to represent "I think a meal started twenty minutes ago and I have already dosed for it". V6 replaced the ladder with a state machine that carries a meal hypothesis across cycles: idle, then observing while a rise builds, then confirmed when the evidence is good enough, then committed while the meal is clearly running, then recovering.

Recovering is the state that changed the most. Before it existed, a loop watching glucose come down from a meal peak would look at the remaining height, decide it was high, and dose again, having forgotten that it had already put the insulin in. Recovering deliberately winds down instead. It is the single change that did most for the post-meal lows I had been living with.

The second change is that the settings stopped being mine. Early Boost had knobs, and the knobs had defaults, and the defaults were whatever suited me. That does not survive contact with other people: the cohort now spans total daily doses from 16 to 58 units, and one participant on U200 where a unit carries roughly twice the mass. V6 derives its settings for each person from their own history, tightening automatically for anyone whose time below range says it should, and it re-derives periodically rather than once. Anything that adds insulin only switches itself on for someone whose glucose is already sitting comfortably.

Across the cohort as it stands, a fully closed loop with no meal announcement runs at about 87 per cent time in range, plus or minus 7, with severe lows at well under one per cent. That is the honest ceiling as I currently understand it, and it is not far off what the community generally believes it should be.

## 3. The advanced features

The dosing core is the meal hypothesis described above, and around it sit several things worth naming.

There is a composed brake, which is a set of restraints that compound rather than override each other, and which audits at around 90 per cent correct on the occasions it fires. There are absolute floors under everything: time below range limits that can only ever tighten, and which no statistical argument is permitted to loosen. There are caps on how much insulin can be committed to a single meal and on cumulative microbolus volume in a rolling window.

There is a sleep detector, built from heart rate and step activity rather than a clock, which learns your usual sleep and wake times over a rolling window and suppresses the aggressive dosing tiers overnight. Overnight is where a fully closed loop can hurt you, because nobody is watching and a meal-shaped rise at two in the morning is almost never a meal.

Steps are a live input to dosing, blended across the phone and any watch you happen to be wearing, and they withdraw insulin when you are active. Heart rate is live but off by default.

Underneath all of it sits the thing I would most want another developer to copy: nothing reaches the dose path without running as a shadow first. A shadow component computes what it would have done, writes it to the log, and delivers nothing. It runs that way across the cohort for as long as it takes to accumulate evidence, and only then is it argued about.

I audited those shadows properly for the first time this week and the result is worth reporting because it is not flattering. There are thirteen of them. One is clearly earning its place: a detector for accelerating meals that fires on 8.8 per cent of cycles, of which 40.6 per cent are followed by a rise of at least 30 mg/dL (1.7 mmol/L) within 45 minutes against a base rate of 19.6, on 154,000 cycles from eleven people. One is real but small: a physiological forecaster that beats "assume glucose stays where it is" by about 1 mg/dL of error at thirty minutes, which is statistically solid and clinically nothing. One turned out to be worse than simply reading the current glucose and should be dropped. Two are producing no data at all. And four have been running for months without anyone asking whether they work, one of them since February.

A shadow that is never scored is telemetry with no decision attached. That is a process failure rather than a code failure, and it is mine.

## 4. Machine learning on the dose path

Two models are on the dose path today. Both are gradient-boosted trees, trained offline, exported as JSON and walked on the phone by about fifty lines of Kotlin in a few milliseconds. Nothing trains, learns or adapts inside the loop. That is a rule rather than an implementation detail: a system that learns while it doses can learn something wrong while it doses.

The first estimates the probability of sustained hypoglycaemia and its only power is to reduce a dose or block the aggressive tiers. The second estimates the probability that an unannounced meal is starting, and it is the only learned component permitted to increase insulin, which is why it gets the harder scrutiny.

Recent measurement has changed what I think about both.

I refitted the hypoglycaemia model on 183 participants from the OpenAPS Data Commons, roughly eleven million decision cycles, against the 32 it was originally trained on. Scored on 1.7 million rows where both the old and new model were out of sample, the refit reaches 0.861 against 0.847. That is a real improvement and a small one.

Except it isn't small where it matters. The model is only consulted on cycles that survive the low-glucose guard, which is about half of them, and the half it never sees carries most of the hypoglycaemia. Judged on the population it actually acts in, the refit's advantage roughly triples, to 0.046. It also explains something that had been bothering me: the deployed model scores 0.85 on the Commons and between 0.52 and 0.72 on the people running it, and almost all of that gap is being judged on the harder half rather than the model failing.

The thing I got wrong, and had to correct twice, was calibration. The refit ranks better but reads on a different scale: fed to the existing thresholds it would restrain insulin six times as often. My first fix was a conversion table built from the Commons. That was wrong too, because the deployment cohort is not a Commons sample. The rate at which the current model triggers its damper runs from 0.26 per cent of cycles for one person to 39.8 for another, against 6.6 on the Commons. Calibrating a population against a sample is exactly the error it sounds like. The right answer is per-person, from each person's own shadow data, and it needs the cohort running the shadow build for a week.

Two new models are in the pipe. One asks whether a fall already twenty minutes old is going to end below 70 mg/dL (3.9 mmol/L); it reaches 0.780 on the sixteen people who contributed no training data, against 0.746 for glucose plus the clock, and it is better for all sixteen of them. The other is not a model at all but a feature: a person's own hypoglycaemia rate by hour of day is worth more than tripling the training cohort was, where the population's hour-of-day rate is worth nothing at all.

That last result is the one I find most interesting, because it points somewhere unfashionable. The gains left in this system do not look like they are in bigger models or more data. Scaling the training cohort stops paying at around 112 participants. They look like they are in each person's own history.

## 5. Next steps

Immediately: getting the cohort onto the shadow build so the hypoglycaemia refit can be calibrated per person rather than globally, and so the fall model can be scored on people other than me.

After that, the fall-consequence model as a restraint in the safety gates, where it can only ever withhold insulin, and the personal clock as a feature, once it has been replicated with a different split.

Further out there is a pre-meal exercise mode. Exercise close to a meal is where these systems fail people most often, the published guidance on what to do is specific, and almost all the machinery it asks for already exists here wired to other triggers. What's missing is a way to tell the loop that exercise is coming, carrying the four things the protocols depend on: when, what kind, how hard, how long. Every route into the loop today carries a target, a duration and a reason from a list of six, all starting immediately. That gap is the whole build.

The reason it will be a declaration rather than a detector is one contrast. Announced exercise with a reduced bolus, announced with a full bolus, and unannounced give 2.0, 7.0 and 13.0 per cent time below 3.9 mmol/L. Nothing in the detection literature separates two strategies by that much, and a trial of automatic detection from wearables could not be told apart from simply asking the person to confirm.

And one thing I am watching rather than building. I moved to a one-minute loop cycle recently and it delivered 22 per cent more insulin a day, at the same glucose, and roughly doubled my time below 70. The caps that bound cumulative microbolus volume were placed for a loop with a fifth as many chances to fire, and they need re-placing before that cadence is a good idea. Faster is not automatically better, which is the sort of thing you only find out by measuring it on yourself.
