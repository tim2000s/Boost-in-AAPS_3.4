# Dose timing and dose size at meals

Whether the advantage of a more reactive dosing algorithm lies in acting sooner or in acting harder,
and what separates the two empirically.

## Abstract

Almost every proposed change to a meal-dosing algorithm either moves insulin earlier within a meal
or adds insulin that was not previously given, and the two are routinely conflated in discussion.
Classifying every dosing difference between the shipped algorithm and its predecessor into those two
categories and pricing each against the glucose that followed separates them: movement is
harm-neutral, while addition carries approximately fifteen percentage points of additional
hypoglycaemia. The gate holding the algorithm in its observing state before commitment blocks
between 26 and 29 per cent of commitments that preceded a glucose above 180 mg/dL, which is the
signature of a block with a cost, though the identification constraint means this bounds where to
look rather than what to do. Relaxing the age requirement by one cycle where the confidence score is
already sufficient is harm-neutral and shifts about 1.5 U per day. Raising the observing-state dose
is defensible only where glucose is at or above 140 mg/dL and insulin on board is below five per
cent of total daily dose; applied more broadly it is contraindicated. A retired acceleration
detector leads the current commitment by a median of fifteen minutes at 98 per cent recall and 15
per cent precision, which makes it unusable for an irreversible dose and usable for a small
retractable one.

## Introduction

The V6 generation was built on the belief that its advantage over the preceding oref-derived
behaviour lies in acting sooner at a meal rather than acting harder. The belief has a testable
consequence. If it is right, insulin moved earlier within a meal is roughly harm-neutral, because
the same insulin is delivered against the same meal on a different schedule, whereas insulin added
to a meal carries a cost in subsequent lows, because there is more of it.

The distinction matters beyond this one comparison. Levers proposed in this programme almost all
take one of the two forms, and the evidence required to justify them differs accordingly. A lever
that moves insulin inherits a harm-neutral prior; a lever that adds it inherits a measured penalty
and must clear a correspondingly higher bar.

A second question concerns the gate that holds the algorithm in its observing state until a
commitment is warranted. A gate that is too conservative blocks insulin that should have been given,
and the excursions that follow a block are the place to look for evidence of that.

## Methods

Dosing cycles were drawn from the local analysis database, which holds one row per decision per
participant carrying the algorithm's internal state and the glucose that followed. The early-dosing
audit covers the record to 3 July 2026, recorded under `backtesting/scripts/2026-07-early-dosing-series/`.
The gate work uses the same source over the same period. The acceleration comparison covers 14,430
gate fires and is recorded under `backtesting/scripts/2026-07-v1-acceleration/`.

Outcomes were taken forward from each cycle rather than aggregated by day, because the question
concerns individual dosing decisions and a daily summary averages away the events of interest.

Levers were priced by the share of the insulin they would remove or add that sits in the window
before a hypoglycaemic event, rather than by how often the lever fires. Pricing by firing rate
rewards a mechanism for being busy; pricing by the insulin at stake near an event asks what the
mechanism is actually worth.

The classification of a dosing difference as movement or addition was made cycle by cycle against
the meal it belonged to, so that insulin given earlier and then not given later counts as movement,
while insulin given earlier and also given later counts as addition.

## Results

Movement was harm-neutral. Addition carried approximately fifteen percentage points of additional
lows. The two forms are therefore not interchangeable, and evidence sufficient to support a lever
that moves insulin is not sufficient to support one that adds it.

The commitment gate blocks more than it should, though the margin is narrow and it is not uniform
across participants. Between 26 and 29 per cent of blocked commitments preceded a glucose above
180 mg/dL. Relaxing the age requirement by one cycle where the confidence score is already sufficient
was harm-neutral and shifted about 1.5 U per day.

Raising the observing-state dose was defensible only inside a narrow cell, specifically glucose at or
above 140 mg/dL with insulin on board below five per cent of total daily dose. Outside that cell a
blanket raise is contraindicated on the addition penalty alone.

The retired acceleration detector leads the current commitment by a median of fifteen minutes, at 98
per cent recall and 15 per cent precision.

## Discussion

The distinction between moving and adding insulin has done more work in this programme than any
individual lever, because it converts an argument about aggression into a testable claim about which
insulin is in question. It also explains why several later proposals were rejected quickly: a lever
adding insulin where insulin is already present inherits the fifteen point penalty, and the burden of
evidence on it rises accordingly.

The acceleration detector illustrates how the same measurement supports opposite decisions depending
on what the action costs. A detector firing wrongly six times in seven is unusable when each fire
commits insulin that cannot be withdrawn. The same detector is usable when each fire commits a small
retractable amount netted off the later commitment, because the cost of a false positive falls to the
cost of a brief and reversible delivery. This is the design recorded under
`2026-07-v1-acceleration/REINTEGRATION_SPEC.md` and shipped in part as the primer, and it is the same
reasoning that makes weak anticipation safe elsewhere in the series.

The gate result is the weakest of the three and stands as a candidate rather than a conclusion.
Between 26 and 29 per cent of blocked commitments preceding a high is a statement about what followed
a block, not about what a different decision would have produced. The identification constraint
applies in full and the figure justifies looking rather than acting.

What none of this addresses is the size of the dose once the algorithm commits, which is where the
residual harm concentrates and which is the subject of the paper on the committed state.
