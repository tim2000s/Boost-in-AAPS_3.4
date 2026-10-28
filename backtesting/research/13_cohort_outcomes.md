# Cohort outcomes across a change of algorithm generation

Three approaches to the same migration comparison, and the two measurement choices that change the
answer.

## Abstract

A cohort of volunteers migrated from the V1 generation of the algorithm to the V5 and V6 generation
through mid 2026. Three approaches to the comparison converge on outcome-neutral. The unadjusted
cohort difference is about thirteen percentage points of time in range; adjusted for selection and
for basal differences it is 1.2 points with a permutation p of about 0.27, most of what remains being
overnight. A within-participant comparison over twenty days each side, on the five participants with
sufficient data in both eras, moves time in range by 0.2 points with an interval from minus 6.3 to
plus 4.7, and every other outcome measure also spans zero. A participant spanning both windows without
migrating moved 4.8 points over the same calendar, further than the migrated group, which makes the
calendar the more economical explanation. Two measurement choices change the answer materially:
establishing era membership from the algorithm's own telemetry rather than from calendar dates, since
a window of days is not a window of one algorithm, and taking glucose from the sensor series rather
than from decision cycles, since between a sixth and a third of decision rows arrive under a minute
after the previous one. Current cohort performance over the seven days to 11 August 2026 across eight
participants weighted equally is 87.4 per cent time in range with an interval from 84.0 to 90.8.

## Introduction

A programme of individual improvements should eventually appear in the aggregate outcome, and whether
it does is the question this comparison exists to answer. The obvious hypothesis is that the newer
generation produces better glycaemic outcomes and that the difference is visible in the record.

The comparison is harder than it looks for reasons specific to a volunteer cohort running modified
software. Participants who migrated are not a random sample of those who could have. Basal settings
changed alongside the algorithm. And the record does not partition cleanly by date, because at any
given time some participants are running a different loop entirely, a silent earlier generation, or a
build that changed mid-window.

## Methods

Recorded under `backtesting/scripts/2026-07-user-comparison/`,
`backtesting/scripts/2026-07-boost-review/` and `backtesting/scripts/2026-08-boost-cohort/`.

Era membership is established from the algorithm's own telemetry rather than from calendar dates. A
window of days is not a window of one algorithm: across this cohort the record contains a participant
on a shadow build of a different loop, one running a silent earlier generation, one who moved to a
different closed loop part way through, and two who changed build mid-window. Selecting by date pools
those together.

Days are admitted only where the intended engine accounts for at least ninety per cent of that day's
cycles, the day carries at least 250 readings, and those readings span at least twenty hours.

Glucose is taken from the sensor series rather than from the decision cycles. Between a sixth and a
third of decision rows arrive under a minute after the previous one, which is the loop running again
on the same reading, and averaging over cycles counts those moments twice. The bias this introduces is
participant-specific in direction and reaches two points of time in range.

The within-participant comparison uses twenty days each side of each participant's own migration, which
removes between-participant differences entirely.

Cohort figures weight participants equally rather than pooling cycles, so that the most prolific
contributor does not carry the result.

## Results

The unadjusted cohort difference is about thirteen percentage points. Adjusted for selection and basal
differences it is 1.2 points, with a permutation p of about 0.27, and most of the remainder is
overnight.

The within-participant comparison finds nothing distinguishable. Time in range moves 0.2 points with an
interval from minus 6.3 to plus 4.7, and every other outcome measure spans zero. Two participants move
in opposite directions by comparable amounts and three do not move.

A participant spanning both windows without migrating moved 4.8 points over the same calendar.

Cohort performance over the seven days to 11 August 2026, across eight participants weighted equally,
is 87.4 per cent time in range with an interval from 84.0 to 90.8, 73.6 per cent in the tighter band,
4.0 per cent below 70 mg/dL and 0.4 per cent below 54.

## Discussion

The migration is outcome-neutral on the available evidence. Three approaches converge on it, and the
third is a within-participant design that removes the confound the first is vulnerable to.

What the within-participant design cannot remove is the calendar. Nobody held one algorithm across both
windows, so generation, season, settings and the participants' own accumulating experience all move
together. The non-migrating participant who moved further than the migrated group is the closest
available comparator and points the same way, which makes calendar effects the more economical
explanation for both movements.

This determines how the rest of the series should be read. Several individual levers have measured
effects and the aggregate of those effects is not visible in the cohort outcome. That is not a
contradiction. The levers are small, the cohort is in single digits, day-to-day variation in time in
range has a standard deviation of about nine percentage points, and the smallest difference a
month-long comparison could detect is around seven points. An aggregate null over this sample is what a
collection of small true effects looks like, and the correct inference is that the design lacks the
power to resolve them rather than that they are absent.

The two measurement choices are worth separating from the result because both produce confident wrong
answers rather than obvious failures. Selecting a window by calendar date pools four different
algorithms into one comparison. Averaging glucose over decision cycles rather than over the sensor
series biases each participant's time in range in a participant-specific direction. Neither is visible
by inspection, and both were found by constructing the same quantity a second way and comparing.
