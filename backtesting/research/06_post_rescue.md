# Rebound after treated hypoglycaemia, and where restraint has to be applied

Why demoting an algorithm's response tier fails to restrain a dose, and what has to be scaled
instead.

## Abstract

A participant treating a low with carbohydrate produces a sharp rise from a low starting point,
which presents to a meal-detecting algorithm as the onset of a meal. Forensic reconstruction of two
incidents in which a loop was disabled after dosing into such a rebound shows that demoting the
response tier does not restrain the delivered quantity: the upper tiers are not bound by the
fast-carbohydrate scale, and a delta-weighted sensitivity term inflates the underlying insulin
requirement during a sharp rise, the composition producing a 3.55 U delivery at a glucose of
97 mg/dL immediately after a hypoglycaemic event. Pricing candidate guards across roughly 103,000
dosing cycles by the share of removed insulin sitting in the window before a low, a graduated scale
applied to the final microbolus inside the post-rescue window prices at 34 per cent, with an
interval from 32 to 37 and a leave-one-participant-out floor of 27, at a cost of about 9 per cent of
genuine meals restrained at a median of 0.80 U. This is the best-priced guard in the programme. A
simpler variant suppressing the meal-state exemption in the presence of a recent low prices at 27
per cent.

## Introduction

Rescue carbohydrate creates the one glucose trajectory that is both unambiguous in origin and
maximally provocative to a meal detector. It rises fast, it rises from a low starting point, and
the participant taking it has just demonstrated that they are prone to going low. An algorithm that
responds to it as an unannounced meal doses into a rebound and returns the participant to the state
they treated.

The natural restraint is to demote the algorithm's response tier during a post-rescue window, on
the reasoning that a lower tier commands a smaller multiplier. Whether that reasoning holds depends
on whether the tier actually gates the quantity delivered, which is a question about the composition
of the dose rather than about the policy.

## Methods

The forensic reconstruction traced a delivered dose through every stage of its composition, from the
underlying insulin requirement through each multiplier to the quantity sent to the pump, to locate
the stage at which restraint failed to apply.

The pricing exercise is recorded under `backtesting/scripts/2026-07-postrescue-rebound-guard/` over
roughly 103,000 dosing cycles. Candidate guards were scored by the share of the insulin each would
remove that sits in the window before a hypoglycaemic event, and costed by the genuine meals each
would also restrain, reported as both a proportion and a median quantity.

Pricing by removed-insulin-before-a-low rather than by firing rate is the substantive methodological
choice. A guard firing constantly and removing insulin that was harmless is worse than one firing
rarely and removing insulin that was about to cause a low, and a firing rate cannot distinguish the
two. The measure remains associational, since the counterfactual trajectory is unavailable, and its
interval comes from resampling participants.

A leave-one-participant-out floor was computed for the winning candidate by dropping the strongest
contributor, so that the headline could not rest on one person.

## Results

Tier demotion does not restrain the dose. The upper tiers are not capped by the fast-carbohydrate
scale, and a delta-weighted sensitivity term inflates the underlying requirement during a sharp
rise. Their composition produced 3.55 U at a glucose of 97 mg/dL immediately following a
hypoglycaemic event.

A graduated scale applied to the final microbolus within the post-rescue window prices at 34 per cent
of removed insulin sitting before a low, with an interval from 32 to 37. The leave-one-participant-out
floor is 27 per cent. The cost is about 9 per cent of genuine meals restrained, at a median of 0.80 U.

Suppressing the meal-state exemption in the presence of a recent low prices at 27 per cent.

A velocity escape within the window was evaluated and rejected. A rebound is by definition fast, so
exempting fast rises exempts the case the guard exists for.

## Discussion

The mechanism finding generalises further than the guard. A tier is a label attached to a state, and
restraining a label does not restrain a quantity when the quantity reaches the pump through terms the
label does not gate. Restraint has to be applied at the point where the final quantity is determined,
which is why the shipped guard scales the microbolus rather than anything upstream of it. The same
reasoning appears in the composed floor, where a product of individually reasonable multipliers
reaches a value none of them implies.

The pricing method is the transferable part of the design. Between candidate guards it gives a
comparison that survives, because it values a guard by the harm it plausibly prevents and states the
cost in the same units. It does not establish that the removed insulin would have caused the low it
preceded, and the identification constraint applies in full.

The 34 per cent figure is the highest in the programme, and the reason is that the population is
narrow. Post-rescue cycles are a small, well-defined and genuinely dangerous set, so a guard aimed at
them is operating where the base rate of harm is high. Guards aimed at broader populations price
lower because most of what they touch was never going to hurt anyone, which is the pattern visible
throughout the work on restraint.
