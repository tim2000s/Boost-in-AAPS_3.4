# Per-participant configuration, derived offline and adjusted online

Why a dosing knob adjusted against observed outcomes responds to noise, and what the revert rate
reveals.

## Abstract

Participants differ enough that one set of dosing parameters cannot serve them: cap clipping accounts
for between nothing and 59 per cent of a participant's time above range, and brake suppression for
between 11 and 47 per cent. The parameters can be derived once from a person's own history and held,
or adjusted continuously against outcomes. Derivation works, rescuing three of seven participants
from caps that were clipping them and tightening one protectively. Four online controllers, covering
two caps and two sliders and both directions of adjustment, all fail. Raising the committed cap
online reverts 43 per cent of the time across a sweep from 33 to 50 per cent and produces about four
raises in six weeks; raising the confirmed cap almost never binds, at one to five raises in six weeks
with all reverts from a single participant; an aggression slider raised on highs reverts 45 per cent
of the time and is mis-targeted, since time above range is a sizing and timing problem; a
hypoglycaemia-caution slider raised on lows has a good-to-wrong ratio of 0.74, flat, and ratchets to
its maximum. The static equivalent of the last is well targeted, with removed insulin sitting before
a low at 28 to 32 per cent for hypoglycaemia-prone participants against 1 to 6 per cent for
well-controlled ones. The revert rate is the diagnostic: a controller responding to signal moves and
stays, and one responding to noise moves and returns.

## Introduction

The case for per-participant configuration is settled by the dispersion in the attribution work,
where the mechanism responsible for a participant's time above range varies from nothing to a
majority depending on the person. What is not settled by that dispersion is how the per-person values
should be arrived at.

Deriving them once from the participant's own history and holding them is simple and inspectable, and
it does not adapt. Adjusting them continuously against outcomes adapts, is what an adaptive system is
generally assumed to do, and introduces a feedback path between a parameter and the data used to set
it.

Both were built, so the comparison is empirical rather than a matter of preference.

## Methods

Recorded under `backtesting/scripts/2026-07-cap-stepper/`,
`backtesting/scripts/2026-07-slider-controller/` and `backtesting/scripts/2026-08-autoconfig-redrive/`.
The derivation was validated on a seven-participant migration cohort.

Each online controller was replayed against the record and judged primarily by its revert rate,
meaning the share of adjustments subsequently undone. The reasoning is that a controller raising and
then lowering the same parameter is tracking noise rather than drift, and that this is visible without
requiring the counterfactual outcome the record cannot supply. Firing frequency and direction were
reported alongside.

The periodic re-derivation tracks the movement of each parameter's underlying driver rather than its
absolute value, requires a move to exceed that parameter's own measured noise band, and holds any
raise to a dose cap behind a guard keyed to measured time below range.

## Results

Derivation works. On the migration cohort three participants were rescued from caps that were
clipping them and one was tightened protectively. It ships with five changes arising from the
backtest, covering historical factory defaults, cumulative clamping, resolved rather than nominal
values, a minimum sample size, and the time-below-range raise guard.

All four online controllers fail, in both directions and for both kinds of parameter. The committed
cap reverts 43 per cent of the time across a sweep from 33 to 50 per cent, at about four raises in six
weeks. The confirmed cap almost never binds, at one to five raises in six weeks with all reverts
contributed by a single participant. The aggression slider reverts 45 per cent of the time. The
hypoglycaemia-caution slider has a good-to-wrong ratio of 0.74, flat across its range, and ratchets to
its maximum.

The static equivalent of the hypoglycaemia-caution slider is well targeted. Removed insulin sitting
before a low runs at 28 to 32 per cent for hypoglycaemia-prone participants against 1 to 6 per cent
for well-controlled ones.

Under the periodic re-derivation the ratchet binds in about one window in thirty seven.

## Discussion

The four failures converge on one policy, which is why they are recorded together: never raise
aggression automatically, and key hypoglycaemia caution to measured time below range. That policy
comes out of the derivation work, and four controllers searching for something better arrive back at
it.

The mechanism behind the failures is the same in each case. A parameter adjusted against outcomes is
being fitted to data that the parameter itself generated, on a few events per week, against outcomes
dominated by meals and activity rather than by the parameter. There is very little signal and a great
deal of variance, and the revert rate exposes it directly.

This is the clearest instance of the separation between what is learned and what ships. The derivation
is statistical, uses robust order statistics over a participant's history, and runs offline on a
schedule. What the dose path receives is a number. Nothing in the loop learns, and these four
experiments are the empirical case for that architecture rather than a philosophical preference for
it.

The conservatism of the periodic re-derivation follows from the same evidence. Requiring a move to
exceed the parameter's own noise band is the direct remedy for what the online controllers did wrong,
and the resulting bind rate of about one window in thirty seven is what makes running it
automatically defensible.

One limitation bounds all of this. The controllers were evaluated on revert behaviour rather than on
outcome improvement, because the outcome comparison requires the counterfactual. It remains possible
that a controller with a high revert rate nonetheless improves outcomes, and nothing here excludes it;
what the evidence supports is that these controllers were not tracking a stable quantity.
