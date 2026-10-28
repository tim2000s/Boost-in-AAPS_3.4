# Boost v5: teaching the loop to read the meal, not just the moment

*Draft for Diabettech. Festival data 18–22 June 2026.*

Boost began as a fairly direct idea. Take the oref decision, give it a sharper appetite for meals I had not announced, and let it act without waiting for me to enter carbs. Boost v1 does that, and most of the time it does it well. It has also always carried a structural quirk that I have wanted to deal with for a long while, and v5 is where I have finally done something about it.

The quirk is that v1 thinks in single frames. Every five minutes it looks at where glucose is and how fast it is moving, sets that against the insulin already on board, and picks a response. Each of those decisions is reasonable on its own. The trouble is that a meal is not a single frame. It is an arc that builds to a peak and then clears slowly, and a loop that re-decides from a blank slate every cycle has no sense of where it sits on that arc. So it can keep correcting a rise that is already being dealt with, put in a little too much, and then leave you managing the low on the way back down. Anyone who has run an assertive unannounced-meal setup will know the shape of that.

I spent a good while trying to tune my way out of it. You can soften the tiers and bolt on brakes, and you do make progress, but you are still decorating a system that fundamentally has no memory. At some point I decided the honest move was to stop tuning the symptom and change the thing underneath. v5 is the result of that decision. I am skipping over everything that came between v1 and here, because most of it was learning rather than landing, and what matters is where it arrived.

## What v5 actually changes

v5 keeps the whole of Boost that already works. The basal logic, the sensitivity handling, the safety limits, the exercise awareness, all of that is untouched. What it replaces is the part that decides the size and shape of an automatic bolus.

Instead of judging each cycle in isolation, v5 carries a meal hypothesis across cycles. It moves through a small set of states, from quietly watching, to confirming that something meal-like is genuinely under way, to committing to it, and then easing back off as the insulin starts to bite. What drives those transitions is a single confidence score rather than a hard threshold, so a rise that does not quite trip a tier no longer gets ignored. The confidence builds, and the response builds with it.

Sitting underneath that is a budget. v5 works out how much it is willing to give in a burst and will not exceed it, which is what stops the quiet stacking that v1 was prone to. There is also a brake tied to deceleration, so the moment glucose stops accelerating and the insulin already given looks like it is doing its job, v5 backs off rather than topping up. The machine-learning piece, which has been part of Boost for a while as an observer, finally gets a job here. A model trained on the cohort's history produces a hypo-risk score each cycle, and that score quietly tightens the budget when a low looks more likely. It is a brake with a probability behind it, not a driver.

The short version is that v5 reads the meal rather than the moment, and it is cautious about its own enthusiasm in a way v1 never was.

## What the festival looked like

I ran v5 as my live loop across a five-day festival, which is about as unforgiving a test as I can give it. Days of high walking, food at odd times, not much routine, and me paying far less attention than usual. Here is where it landed.

| | five days, pooled |
|---|---|
| Mean glucose | 129 mg/dL (7.1 mmol/L) |
| Time in range 70–180 | 85.9% |
| Time in tight range 70–140 | 65.2% |
| Time below 70 | 2.8% |
| Time below 54 | 0.6% |
| Total daily dose | around 13 to 17 units |
| Activity | roughly 18,000 to 28,000 steps a day |

For a do-it-yourself loop running through that much exercise with very little supervision, I am happy with that. The low numbers in particular are reassuring, because high-activity days are exactly when a loop with too much appetite gets people into trouble.

The more interesting view comes from a comparison I can only make because of how Boost logs. On every cycle, v5 records what plain v1 would have done with the same inputs. Across the festival the two agreed most of the time, and where they parted company it was almost always v5 holding back on a correction into a high while v1 would have pushed harder. On the size of the automatic boluses alone, v5 ran roughly half of what v1 would have asked for on those diverging cycles. I want to be careful here, because that figure has been misread before, including briefly by me. It is the automatic bolus portion only. A large part of the total daily dose is basal, and basal is identical under both. So the honest statement is that v5 is meaningfully gentler with its corrections at the top end, while the total amount of insulin over a day is much the same. It is not halving your insulin. It is choosing to deliver it with more restraint where restraint matters.

## What we were shadowing, and what it implies

Alongside the dosing, Boost has been quietly running a set of observers that change nothing but write down what they would have done. This is the part I am most interested in, because it is how a change earns its way into actually driving the pump rather than being trusted on a hunch.

The main one is activity. Boost learns your personal daily step baseline and watches how far above or below it you are, both over the last day or two and as today accumulates. The idea is straightforward. A big walking day makes you more sensitive for a day or so afterwards through glycogen depletion, and the loop ought to know that and ease off accordingly. Across the festival that observer correctly saw the volume, with days well above baseline, and logged the sensitivity nudge it would have applied. It stayed as a note rather than an action, which is the point of shadowing.

When you turn that logged intent into an expected effect, the picture is what you would hope for and also honest about its limits. For the lows that were genuinely driven by a correction landing into exercise, an active sensitivity response would have trimmed the dose and taken the edge off. For the lows that came from simply burning through glucose faster than basal could keep up, where the loop had already stopped delivering, no amount of sensitivity adjustment would have helped, because there was nothing left to withhold. That is a useful thing to have learned before switching it on, rather than after. It tells me the activity work is worth turning on for one specific failure mode, and that a separate lever is needed for the other.

There is a second observer worth mentioning, which is meal timing. Boost watches when v5 confirms a meal, and over time it learns the points in the day you habitually eat. Where it finds a consistent pattern it will, in shadow, open a gentle low-target window in the hour beforehand, the idea being that a little insulin is already working by the time the food lands. Exercise and recovery override it, because the last thing you want is a lower target pulling insulin in while you are also burning glucose. Across the festival it learned a mid-afternoon and an early-evening slot, and on the days it opened a window a real rise did follow shortly after, so the timing it had learned was sound. I would not read more into it than that yet. A festival is close to the worst case for learning meal times, because almost nothing happens on a schedule, so it only caught my most consistent slots and stayed quiet the rest of the time. Whether nudging the target down ahead of those meals actually improves the peak without trading it for a low afterwards is the next thing to measure, and three days of irregular eating is not the data to settle it on.

I will be straight about the rest of it too. This is shadow and modelling, not a controlled outcome study. One person in the cohort showed essentially no difference between v5 and v1, which is a perfectly fair result. Some of what looked like lows during the festival turned out to be a dying sensor and a pump I had detached and forgotten to reconnect, neither of which is the algorithm's fault and both of which I only untangled by going back through the data carefully. And the heart-rate feed that would sharpen the activity picture has been frustratingly intermittent, which is its own piece of work.

## Where this goes

v5 is running as a silent observer for everyone else on the beta. v1 still does the dosing, v5 logs what it would have done, and getting that running across more people is how the gentler profile gets confirmed on real, messy, varied data before it is ever allowed near anyone's pump but mine. The festival has made me more confident that reading the meal is the right idea and that the restraint is doing real work. It has also been honest with me about the things it cannot fix on its own. That is roughly the balance I want from a change like this.
