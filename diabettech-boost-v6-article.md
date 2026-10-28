# Boost, three years on: how a fully closed loop learned to anticipate

*The usual preamble, because it matters. Everything described here is highly experimental. It uses insulin in an off-label fashion, it isn't in any released, supported version of AndroidAPS or Trio, and nothing here is medical advice. It's an n=1 that has grown into a slightly-larger-than-n=1, shared in the open-source, #WeAreNotWaiting spirit so that the learning is useful to others. If you take anything from it, take the ideas, not the dose settings.*

---

I've written about Boost a few times now. Back when I first described it, I called it a [possibility](https://www.diabettech.com/fully-closed-loop-with-an-open-source-aid-system-a-possibility/) — a modified version of oref1 that tried to recognise the glucose rises linked to food and dose insulin to handle them, with no meal announcement at all. Later I ran a proper [n=1 experiment](https://www.diabettech.com/the-insulin-only-full-closed-loop-an-n1-experiment/) on an insulin-only full closed loop and reported back honestly: 81.2% time in range and 5.6% below over four months, but with lines that were noticeably wider than my hybrid setup, and post-meal highs I wasn't thrilled about. I concluded, more or less, that it worked — but that I personally wasn't sure that hitting the highs after a meal was a trade I wanted to make. And somewhere in between, I wrote about [bringing step counts into the loop](https://www.diabettech.com/everybodys-moving-integrating-stepcounts-into-open-source-automated-insulin-delivery/), and made the point — which I still believe — that activity is more complex than steps alone.

So this is the update. Boost has changed a great deal since those pieces, enough that the version I now run barely resembles the one I wrote about. The headline is that it's moved from being *reactive* to being something much closer to *anticipatory*, and that the central tension I kept bumping into — how aggressive do you dare to be when the downside is an overdose — has been re-architected rather than tuned around. This is the story of how it got there, what's in the current version (V6, running both on AndroidAPS and, now, on a faithful port to Trio on iOS), and why I think it's genuinely better. It's long, because there's a lot to cover. Grab a coffee.

## Where we were, and the awkward juxtaposition

Let me recap the problem, because it frames everything that follows.

A standard oref/AAPS loop is conservative by design. It looks at your glucose, your insulin on board, your carbs-on-board if you've told it about them, and it nudges. When you don't announce meals, that nudging is too slow to deal with the speed of a real-world rise — by the time the loop is confident enough to act hard, you're already at 12 and climbing. The original Boost addressed this by detecting the *shape* of a food-driven rise and allowing additional insulin to go in early. That's the bit that made full closed loop a possibility at all.

But it created what I described at the time as an "awkward juxtaposition." To beat a meal, you have to dose early and reasonably hard. To stay safe, you must never dose so hard that you tip someone into a hypo a couple of hours later, when all that lovely fast insulin is still working. Early Boost handled this with a set of tiers — discrete dosing modes the algorithm picked between each cycle, each more or less aggressive than the last, with a machine-learning hypo-risk model bolted on to pull things back when the predicted risk of a low got high.

The tiered approach worked, and I learned an enormous amount from it. But it had two structural weaknesses that I couldn't tune my way out of. The first is that "pick one of eight modes" is a blunt instrument — the world isn't eight discrete states, and a tier that's right at minute zero of a meal is wrong by minute forty. The second, and more important, is that aggression and safety were tangled together inside each tier. How hard to push and how much to hold back were decided in the same breath, which made the whole thing hard to reason about and hard to trust. Every time I made it braver to chase meals, I made it more dangerous, and I was forever trading one against the other.

The current version takes that knot and cuts it.

## V5: thinking in meals, not modes

The biggest single change is conceptual. Instead of asking "which dosing tier am I in?", Boost now asks a more human question: **"Is a meal happening, how sure am I, how hard should I be acting right now, and what — if anything — is telling me to back off?"**

It does this with a small state machine. There are five states, and at any moment Boost is in exactly one of them:

- **Idle** — nothing of interest is happening. Boost sits back and lets the underlying oref engine do its ordinary job.
- **Observing** — something looks like it might be the start of a meal. Boost leans in *gently*, dosing a small fraction of what it might if it were certain.
- **Confirmed** — yes, this really is a meal. This is where the meaningful, early "meal bite" happens.
- **Committed** — the meal is underway and being covered. Boost settles into a steady, sustained delivery rather than another big hit.
- **Recovering** — the rise has turned, glucose is coming back down, and Boost eases right off so it doesn't keep pushing insulin into a fall.

If you've ever watched yourself eat and then watched your CGM, that sequence will feel familiar, because it's roughly how a thoughtful human would dose by hand: cautious at first, decisive once you're sure, steady through the bulk of it, hands-off as it comes down.

What moves Boost between these states is a single, continuous **meal score** between 0 and 1. Rather than a yes/no rule, the score is a weighted blend of seven signals: the rate of glucose rise, whether that rise is *accelerating*, the output of a separate machine-learning model that estimates the likelihood a meal is actually in progress, whether you've recently been low (which makes it more cautious), the time of day relative to when you usually eat, whether you're exercising, and the cumulative size of the rise over the last half hour. None of those signals is trustworthy on its own — delta spikes from compression lows, the ML model has its off days, time-of-day is only a hint — but blended together they're a far more robust "is this a meal?" estimate than any single trigger. The score has to clear one threshold to start *observing*, and a higher one, sustained, to *confirm*. That hysteresis is deliberate: it's much easier to nudge Boost into paying attention than it is to make it commit.

So that's confidence. Now the part I'm most pleased with: confidence and safety are no longer the same dial.

## Budgets and brakes: separating "how brave" from "how safe"

Here's the architecture that untangles the knot.

Each cycle, Boost computes an **aggression budget** — think of it as the maximum amount of insulin it's willing to consider deploying right now. That budget isn't plucked from a setting; it's derived from the underlying engine's own assessment of how much insulin you need, and then *damped* by two things: the machine-learning hypo-risk model (the higher your modelled risk of a low, the smaller the budget), and a post-exercise factor (because insulin hits differently after you've been moving). The budget is, in effect, the answer to "how much insulin would be reasonable at all, given the whole picture?"

The state machine then spends a *fraction* of that budget depending on which state it's in. Observing spends a little. Confirmed spends the most — this is the early meal bite. Committed spends a moderate, steady amount. Recovering spends almost nothing. So the question "how brave should I be?" is answered by *confidence* (which state am I in, how strong is the meal score), while "how much is it even safe to contemplate?" is answered separately by the budget.

And then, after all that, comes a stack of independent **safety brakes**, each of which can only ever *reduce* the dose, never increase it:

- An **IOB-headroom brake** that eases off as you approach your insulin-on-board ceiling.
- A **deceleration brake** that backs off the moment the rise starts losing steam, so Boost stops pushing into a turn.
- The **ML hypo-risk throttle**, which can clamp the dose hard if the model doesn't like where things are heading.
- A **sensor-quality** check that gets cautious when the CGM data looks unreliable.
- And a set of **hard gates** that are not negotiable: Boost will not dose if the predicted low for the next while is below a floor (it simply will not dose into a forecast hypo), it won't act on an implausible delta, and it sits behind every one of the underlying engine's own safety limits — maximum IOB, per-dose caps, and a rolling cap on how much SMB it can stack inside an hour.

The thing I want to land here is the *separation*. Aggression is driven by how confident Boost is that you're eating. Safety is enforced by a budget and a series of brakes that don't care how confident it is. Making Boost braver at meals no longer makes it more dangerous between them, because the brakes and the hard gates are doing their job regardless of what the state machine wants. That's the difference between tuning around a tension and designing it out, and it's the single biggest reason I trust this version in a way I didn't fully trust the earlier ones.

There's a nice side effect, too. Because Boost is now reasoning in terms of meal states rather than abstract tiers, it can *learn when you tend to eat* and lean very slightly forward in the minutes before — anticipation rather than reaction. In the n=1 piece I noted that "anticipation gets significantly better outcomes than reaction." The state-machine framing is what finally made that practical to act on.

## V6: giving the loop some context

Everything above is the V5 dosing core. V6 is what you get when you wrap that core in *context* — and this is where the step-count work from the earlier article grows up. (One naming note for anyone actually running this: in the app there is no separate "V5" and "V6" to choose between — it's all a single plugin called **Boost V6**. I use "V5" for the dosing core and "V6" for the core-plus-context, but that's me describing the architecture, not two things you select.)

In that piece I argued that steps alone can tell you someone is walking but miss most other forms of exercise, and that the truly useful signals are more subtle: is the person *inactive*, are they *asleep*, are they *active*. V6 leans into exactly that. It ingests heart rate and step data (via Health Connect on Android), and instead of treating them as a crude basal-reduction trigger, it *learns* from them.

The most useful thing it learns is sleep. Rather than asking you to set a night window, V6 watches the combination of a low, flat heart rate, an absence of steps, and the time of day, and decides whether you're awake, drifting off, or genuinely asleep. Over several weeks it builds up a picture of *your* habitual night — when you tend to go down, when you tend to surface — so it isn't fooled by the odd late night or early start. When it's confident you're asleep, **night mode** engages: it suppresses the meal-chasing SMBs and specifically gates the V5 meal override off, so the loop stops reacting to the small, noisy overnight glucose wobbles that aren't meals at all. The wins overnight in full closed loop are quiet ones — fewer 3am corrections chasing a sensor artefact, fewer compression-low scares — but they matter enormously for both control and sleep, and they're the kind of thing you only get by modelling the person rather than the clock.

There's a meal-time learner doing the equivalent job for the daytime — quietly recording when genuine, confirmed meals happen so the pre-meal anticipation has something real to anticipate against. And there's a dynamic ISF layer (Boost's version of the Dynamic Sensitivity idea I've written about before), which anchors your insulin sensitivity to your recent total daily dose so the loop's sense of how strong your insulin is tracks reality rather than a number you set months ago.

The newest piece — and I'm being deliberately honest here, in keeping with how I've always tried to write about this — is an **activity-load** model that's currently running in *shadow only*. It learns your personal step baseline and works out how far above or below it you are, and it logs what it *would* do to your sensitivity if it were acting. It isn't touching dosing yet. I want to watch it through some genuinely high-activity periods first — more on one of those, the Isle of Wight, shortly — and see whether the numbers it produces match what my body actually does, before I let it anywhere near insulin delivery. That's the pattern for all of this, really: build it so it can only observe, watch it for a long time, and only then give it the keys. It's the same caution I described with steps — I think activity is more complex than any single number, and I'd rather under-claim and check than over-claim and apologise.

## A field test: taking it to the Isle of Wight

You can validate an algorithm in shadow on a laptop for as long as you like, but the real exam is a day that flatly refuses to behave. So I took it to a festival.

The Isle of Wight is about as hostile an environment as I can hand a closed loop, and that's the point of going. Days spent on your feet, tens of thousands of steps at a time. Food that arrives whenever a queue is short rather than when you planned it, in portions of unknown size and composition, eaten standing up. Heat. The odd drink. Nights that start late and sleep that's brief, broken and nothing like my usual pattern. And a travel-and-ferry day bolted onto each end for good measure. Every single one of those is a thing that ordinarily trips up a system built for predictable, announced living — and a fully closed loop has to take all of them at once, with no help from me.

It's also precisely why the activity-load model exists, and why it spent the whole weekend running in shadow. The entire reason I built that piece to observe-and-log rather than act was so that an event like this could hand it the data it's hardest to come by: sustained, genuinely high-volume movement, day after day, measured against a baseline it had already learned from my ordinary weeks. A festival is a fortnight's worth of "edge case" compressed into a long weekend. If the model's sense of how much my sensitivity shifts on a big walking day is going to be wrong, this is where it shows up — and because it's only logging, it can be spectacularly wrong without any consequence beyond a note in the data for me to learn from.

So this was a real stress test of the whole stack at once: the meal state machine coping with festival eating it was never told about, night mode trying to make sense of sleep that didn't follow the rules, and the activity model quietly recording what it *would* have done to my insulin sensitivity across days of relentless movement.

And it held up. Here's the whole thing, five days of it, Thursday the 18th to Monday the 22nd of June:

![Boost V5 — Festival summary, 18–22 June 2026](Boost-Festival-Summary-2026-06-18_22.png)

The headline numbers, across the entire festival: **85.5% time in range** (70–180 mg/dl), with a mean glucose of **129 mg/dl (7.1 mmol/l)**. Time below 70 was **2.8%**, and below 54 just **0.6%**. Time above 180 was 11.2% — festival food, eaten on no schedule and announced to nothing, still pushed some highs, and I'm not going to pretend otherwise. But the day-by-day line is the part I keep coming back to: **89%, 84%, 88%, 87% and 82%** time in range, Thursday through Monday. Five genuinely chaotic days, and not one of them fell apart. The activity was real, too — somewhere between **13 and 27 thousand steps a day**, with heart rate peaking up into the 120s — and that sustained, day-after-day load is exactly the data the activity-load model is sitting in the background trying to learn from.

Now put that next to where this started. When I ran the insulin-only full closed loop for that earlier [n=1 piece](https://www.diabettech.com/the-insulin-only-full-closed-loop-an-n1-experiment/), in ordinary, predictable life, I reported 81.2% time in range and 5.6% below over four months. The festival — a far harder environment by every measure I can think of — came in at 85.5% in range and 2.8% below. Same person, same fully-closed-loop premise, still no meal announcements; but the current version held *tighter*, with roughly *half* the time low, in precisely the conditions that ought to have broken it. That comparison, more than any single graph, is the evolution I've been trying to describe in this whole piece.

I'm not going to oversell it. It's five days, it's n=1, and that 11.2% above range tells you plainly it isn't magic — there were meals it was late to and highs I simply rode out. *[Tim — worth a sentence or two of colour here if you want it: a meal it nailed, one it didn't, and how the short, broken festival sleep played with night mode.]* But as a stress test of the whole stack at once — meal machine, night mode and activity model, all of it, in the wild — it did the thing I built it to do. And the activity model found its edges in shadow, where it can afford to be wrong, which is exactly where I wanted it to find them.

## Lowering the barrier: it configures itself

One of the quieter problems with the tiered Boost was that it had a *lot* of knobs, and getting them right took both understanding and patience. The state-machine design needs far fewer — there are really only a handful of meaningful levers now (how aggressive, how cautious about lows, how big a single dose can get) — but even a handful is a barrier if you don't know where to start.

So V6 starts for you. The first time you switch Boost into its active dosing mode, it looks back over your last couple of weeks of *your own* dosing and glucose history and derives a sensible starting point for each lever — how big your meal doses typically are, how prone to lows you've been, what your total daily dose implies about cap sizes. It's strictly suggestion-only and one-shot: it only ever fills in a setting you haven't touched yourself, it never overrides a value you've deliberately set, it can't run away with itself because every derived number is bounded, and if there isn't enough history yet it simply waits and tries again later. A new user gets a configuration shaped by their own past, not by mine, and they get it without having to understand the internals first. Importantly, it can tighten a cap towards what your data supports but it's been built so it can never quietly *loosen* a safety limit without you choosing to.

## It isn't just Android any more

For most of its life Boost has been an AndroidAPS thing. That's now changed: the V5 dosing core has been ported, faithfully, to Trio on iOS, sharing the exact same meal-scoring and configuration logic so the two platforms reason about a meal in precisely the same way. That matters for a couple of reasons. It widens who can try this enormously, and it means the iOS port benefits from a clean version of the auto-configuration from day one, derived from standard oref history rather than from a prior Boost install. Keeping the two genuinely in step — to the point of checking the maths line by line across both — has been a piece of work in itself, but it's the right foundation.

## On safety, because you'd be right to ask

I'd be doing this a disservice if I didn't spell out how it's bounded, because "fully closed loop, dosing for unannounced meals" should make you nervous, and it should make me nervous too.

Boost V5 is opt-in. When it's off, you're running the ordinary engine. When it's on, it doesn't replace that engine — it sits on top of it. The underlying oref/AAPS loop still owns your basal, all of your predictions, and every one of its own safety constraints. V5 only ever *substitutes its dose for the SMB* on a cycle where the underlying loop had already decided an SMB was permissible; it can't invent a dosing opportunity the base system wouldn't have allowed. Its dose is bounded by your maximum IOB, by per-dose caps, and by a rolling cap on cumulative SMB within the hour, and it's clamped to the system's own IOB ceiling so it can't exceed the limit the base loop respects. It's suppressed entirely while you're asleep. It will not dose into a predicted low. And if anything inside the V5 logic so much as hiccups, it returns nothing and the underlying loop's own decision stands — Boost failing means Boost gets out of the way, not that anything dangerous happens.

Before any of this drove a single unit on my body, it ran for a long time in *shadow* — computing what it would do, logging it, and never acting — across my own data and a small cohort of other people's loops, so we could see how it would have behaved before letting it behave. I've also recently put the whole thing through a deliberately adversarial review, pulling it apart specifically looking for places where a dose could escape a cap or where the two platforms might disagree. It found a couple of things worth fixing — a place where the hourly cumulative cap wasn't being honoured on the override path, and a configuration edge where a cap could in principle be loosened without consent — and both are now closed. None of that makes it *safe* in the absolute sense; it's experimental software dosing insulin without being told about food. But it does mean the safety isn't an afterthought, and that I'm willing to find the holes and say so.

## So, is V6 actually better?

I think it genuinely is, and I'll try to say why without overclaiming.

The original full-closed-loop experiment landed at decent numbers but wide lines and post-meal highs, and I walked away from it for myself because the trade didn't feel worth it. The version I run now is a different proposition. The meal handling is earlier and better shaped, because it's reasoning about the arc of a meal rather than reacting to a single rise. The overnight behaviour is calmer, because it knows I'm asleep and stops chasing noise. The aggression-versus-safety tension that I used to manage by hand is now handled structurally, which means I can let it chase meals harder *without* the corresponding rise in hypo risk that used to come bundled with it. And the friction of getting started has largely gone, because it sets itself up from your own data.

I've shown you the festival numbers above because they happen to make the point cleanly, but a festival is a deliberately extreme test, and it's only fair to show you the other end of the spectrum too: ordinary life. So here are the first few settled days back home — normal routine, normal sleep, no fields or ferries. Across them, time in range sat at **88.9%**, with a mean of **118 mg/dl (6.5 mmol/l)**, **2.8%** of the time below 70 and just **0.1%** below 54. Ordinary life is a little tighter than the festival, as you'd hope — but the striking thing, to me, is how *little* the festival actually gave away against it. Five days of mayhem cost a few points of time in range and a bit more time spent high, and nothing worse than that.

And both of those — the chaotic weekend and the quiet week — sit comfortably above the 81.2%-in-range, 5.6%-below figures I reported from the original full-closed-loop experiment. Same loop philosophy, no meal announcements, but a generation of algorithm later, and the lows in particular have all but disappeared (0.1% below 54 across an ordinary stretch is a number I'd have struggled to believe a couple of years ago). That, rather than any single headline figure, is the shape of the progress.

What I'll add beyond the numbers is qualitative and, I hope, more useful: the lines are tighter than the full-closed-loop experiment I wrote up, the lows are rarer and shallower, and — the bit I care about most — I've largely stopped thinking about it, which after all is the entire point of the exercise.

That's not to say it's finished. The activity model is still watching from the sidelines. Fast insulin remains non-negotiable — none of this works with slow pharmacokinetics, and the physiology still wins every argument it picks. And it's still firmly in the realm of experiment, off-label, unsupported, and not for everyone. But between the AndroidAPS and Trio versions, more of us are now running it and feeding back, and that collective, real-world experience is exactly the thing that makes open-source AID move faster than it has any right to.

Ultimately, when I wrote the original piece, full closed loop was *a possibility*. Several years and a complete rethink later, it's something I just live with, day to day, without much drama. That, more than any statistic, is the change worth announcing.

*As ever: this is shared in the open so others can learn from it, not as a recommendation to do it. If you're going to experiment at this edge, understand the system, understand the risks, and go slowly. #WeAreNotWaiting.*
