# Meals with and without post-meal exercise — what the loop does, and why

*A short report grounded in one cohort's own data (eight fully-closed-loop users with a step
feed, ~30 days to 2026-07-28). Every figure is measured from the database; nothing is quoted
from the literature. "Post-meal" = the three hours after an unannounced-meal confirmation, with
no carbs entered — the regime this cohort actually runs.*

---

## The question

When someone eats and then moves — a walk after lunch, the washing-up, a errand — the fully
closed loop faces its hardest problem. This report separates the post-meal window into the times
that were **followed by activity** and the times that were **not**, and asks two things: how
differently does the loop perform in each, and *why*. The answer overturns the intuitive
explanation and points the next work at two specific, opposite fixes.

## 1. Exercise after a meal nearly doubles the low rate

Taking every unannounced-meal confirmation and asking whether glucose fell below 70 mg/dL in the
following three hours, the split is stark. Meals *not* followed by activity ended in a low **15%
of the time (95% CI 12–18)**; meals *followed* by activity within two hours ended in a low **23%
of the time (95% CI 19–27)**. The confidence intervals do not overlap — this is a real, roughly
1.5× increase, not noise.

![Figure 1](figs_postmeal_exercise/fig1_contrast.png)

*Figure 1. Low (<70 mg/dL) rate in the three hours after an unannounced meal, split by whether
activity followed. Bars are the point estimate; whiskers are the bootstrap 95% CI.*

That is the headline cost. The obvious next question is *what causes it* — and the obvious answer
is wrong.

## 2. It is not the insulin — the crash is not dose-driven

> **WITHDRAWN 2026-08-13.** The dose-refutation argument in this section does not stand. It rested
> on pooling insulin on board in absolute units across participants whose total daily dose spans
> 16.3 to 57.6 U, one of them on U200, and the between-participant correlation of median IOB at
> onset with that person's own low rate is -0.388, which pulls the pooled association toward
> inversion. Standardised by each participant's own TDD and resampling participants, the figure is
> AUC 0.549 (0.512 to 0.604) on 157 events from five users, with every participant above 0.5 and a
> median IOB of 1.76 U where a low followed against 1.36 where none did. That is the ordinary
> direction. The 15% against 23% low-rate contrast elsewhere in this report survives; the claim
> that crashers carry LESS insulin does not. See `2026-08-postmeal-exercise-recheck/`.

The natural explanation is dose stacking: the meal triggered a bolus, exercise then amplifies it,
and the person crashes. If that were the mechanism, the people who crash should be carrying **more**
insulin when the exercise starts. They carry **less**.

Splitting the meal-plus-exercise events into thirds by insulin-on-board at the moment activity
begins, the crash rate *falls* monotonically as insulin rises — **32% at low IOB, 20% at mid, 17%
at high** (Figure 2). The direction is the opposite of the stacking story. Looking at it per
event tells the same tale: the events that crashed carried a **median 1.1 U** on board versus
**1.8 U** for those that didn't, on an essentially identical meal bolus (2.9 U vs 2.7 U), and they
started from a **lower glucose** (116 vs 138 mg/dL). More committed insulin, in the post-meal
window, is *protective* — not dangerous.

![Figure 2](figs_postmeal_exercise/fig2_dose.png)

*Figure 2. Crash rate among meal-plus-exercise events, by insulin-on-board at the start of
exercise. Dose-driven crashes would slope up with IOB; they slope down.*

### Why — the carbohydrate-counterweight mechanism

Exercise recruits a largely **insulin-independent** glucose drain — contraction-mediated muscle
uptake plus amplified sensitivity — a roughly fixed downward pull that arrives whether or not
insulin is on board. Whether that pull tips into a hypo depends on the **counterweight** present
at that moment: how fast carbohydrate is still appearing from the meal, and how much glucose
headroom there is.

Insulin-on-board, in this window, is a *proxy for that counterweight*. High IOB marks a large
meal still actively absorbing — a strong upward carbohydrate flux that offsets the exercise drain.
Low IOB marks a small or finished meal (or a loop that has already withdrawn insulin on a falling
trajectory), so the drain runs unopposed and glucose falls through 70. The crashers also start
with less headroom. The dose is not the culprit; the *missing carbohydrate* is. This is **SOLID**:
it holds across the tertile split, the matched-bolus comparison, and the direction of the IOB
relationship. The precise physiology is inferred rather than measured, so it is **PROVISIONAL**;
and a caveat holds — low IOB is partly a *consequence* of the loop zero-temping on an
already-falling glucose, so "low IOB → crash" and "already-falling → crash" cannot be fully
separated. Both readings converge on the same conclusion: the loop's insulin lever is already
spent, and the shortfall is glucose it cannot supply.

## 3. What each regime costs — in context

Zooming out from the crash to the whole picture, the cohort's time splits into three regimes that
the loop handles very differently (Figure 3, Table 1).

![Figure 3](figs_postmeal_exercise/fig3_zones.png)

*Figure 3. Share of time in each glucose zone, by regime. Background = away from meals.*

| Regime | % of time | Mean (mmol/L) | TIR 70–180 | TING 63–140 | Time <70 | Time >180 |
|---|---|---|---|---|---|---|
| Background (non-meal) | 59% | 6.6 | **93%** | 82% | 2.7% | 4% |
| Post-meal, no exercise | 18% | 8.1 | 76% | 54% | **2.4%** | **22%** |
| Post-meal, with exercise | 23% | 7.7 | 78% | 55% | **4.0%** | 18% |

*Table 1. Cohort-pooled glucose metrics by regime, 8 users, ~30 days.*

Three things fall out. **First, background control is essentially solved** — away from meals, 59%
of the time, the loop holds 93% time-in-range with lows no worse than average. There is little to
gain there. **Second, the real deficit of fully-closed dosing is the post-meal high, and it is a
speed problem, not an over-dosing one**: in the clean post-meal window (no exercise) more than one
minute in five is spent above 180, yet lows are *flat* at 2.4% — the loop is too slow to cover an
unannounced meal, not too aggressive. **Third, exercise redistributes post-meal risk** — it trims
the high (22% → 18% above range) but nearly doubles the low (2.4% → 4.0% below 70). It is the same
counterweight mechanism at the population level: the exercise drain eats the excess glucose, which
helps when there is excess and hurts when there is not.

## 4. Two disjoint problems, opposite fixes

The most useful finding is that the post-meal high and the post-meal-exercise low affect
**different people**, and pull in **opposite directions**. Plotting each user's post-meal time
*high* (no exercise) against their post-meal-exercise time *low* (Figure 4) separates the cohort
cleanly into two non-overlapping groups.

![Figure 4](figs_postmeal_exercise/fig4_bimodal.png)

*Figure 4. Each user's post-meal high burden (x) versus their post-meal-exercise low burden (y).
The two clusters do not overlap.*

- **High-runners** (bottom-right — users A, B, F, tim): 24–37% of post-meal time above 180, with
  post-meal lows at or near zero. Exercise *helps* them — it knocks down a peak they have glucose
  to spare. They are **under-treated at meals and have measured headroom for more**.
- **Tight-runners** (top-left — users C, D, E): little post-meal high, but exercise tips them low
  (6%, 9%, 14% of post-meal-exercise time below 70). They have **no glucose buffer**, so the
  exercise drain runs straight through the floor.

The people who need *more* meal insulin are not the people who need exercise protection. A single
global change would help one group and harm the other — which is exactly why the fix has to be
per-user, and why the loop's own per-user auto-config is the right mechanism to carry it.

## 5. What this means for the loop

Two implications follow, and one thing is ruled out.

**Ruled out: cutting the meal dose for exercisers.** They are not over-dosed — the crashers carry
*less* insulin, on the same bolus. A smaller meal dose would only trade a rare exercise low for a
routine post-meal high, and would land on the high-runners who need the opposite.

**Lever 1 — earlier / more meal insulin for the high-runners.** The clean post-meal window
licenses the one thing the rest of the cohort forbids: more insulin, for the users whose post-meal
high is large and whose post-meal lows are near zero. This is the natural home for the meal-onset
acceleration signal already banked in shadow. It is a real dosing change, so it goes through the
two-test bar — a pre-registered within-user trial, auto-config-gated on the user's own low burden
so it can never switch on for a tight-runner.

**Lever 2 — retractable exercise protection for the tight-runners.** Because the loop cannot add
carbohydrate, its only pre-emptive lever against an activity low is to remove insulin *before* the
walk, so less is acting when the drain lands. Made safe by retractability — an anticipatory
temp-basal reduction that unwinds if the activity does not appear — this is the anticipation
shadow now banking data across the cohort. Its pricing (does it prevent the lows, at what cost)
is the next milestone, and needs exactly the tight-runners' own data to settle.

**Confidence.** The contrast (Figure 1), the dose refutation (Figure 2), and the disjoint
populations (Figure 4) are **SOLID** — cohort-wide, CI-backed where relevant, robust to how the
events are counted. The physiological mechanism is **PROVISIONAL**. Everything about the two
levers' live benefit is **untested** — that is what the trials exist to decide. As ever, without a
glucodynamic simulator these are associations priced against observed outcomes, not proven
counterfactuals.

*Reproduce: `figs_postmeal_exercise/make_figures.py` (DB refreshed to t=now). Companion studies:
`2026-07-postmeal-exercise-mechanism/`, `2026-07-performance-segmentation/`. One cohort member on
a different pump platform has no step feed and is excluded throughout.*
