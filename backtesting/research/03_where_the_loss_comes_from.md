# Attribution of time outside range to proximate mechanism

Where time outside range actually comes from, which of it was foreseeable, and what a
forward-looking feature does to a causal ranking.

## Abstract

Improving an algorithm requires knowing which of its behaviours costs the most, which had not been
measured. Segmenting each participant's timeline into episodes above 180 mg/dL and below 70, and
attributing each onset to one proximate mechanism from the telemetry in the preceding forty five
minutes, over roughly 87,000 decision cycles and 1,100 episodes from eight participants: time above
range divides into brake suppression at 34 per cent, late commitment at 16, cap clipping at 15,
recovering hold at 11, undersizing at 9, uncoverable at 10 and non-meal highs at 5, with dispersion
between participants far wider than the cohort figure suggests, brake suppression running from 11 to
47 per cent and cap clipping from 0 to 59. A gradient-boosted foreseeability layer with participants
held out predicts forward highs at 0.83 and forward lows at 0.78, and separates the mechanisms
cleanly: brake suppression carries 1.5 times base risk forty five minutes before onset and non-meal
highs 2.4, while cap clipping, undersizing and uncoverable highs carry 0.5 to 0.9 and therefore arrive
unannounced. Time below range is dominated by activity at 48 per cent pooled, then basal and
sensitivity drift at 30, stacking at 16 and rescue overshoot at 7. A rescue antecedent taken from a
forward-looking window rather than a backward-looking one places rescue overshoot second at 37 per
cent, which is close to tautological because the outcome is encoded in the cause.

## Introduction

Effort spent on an algorithm should go where the loss is, and the working assumption in mid 2026 was
that time above range came mainly from dosing too little too late at meals and time below range mainly
from insulin stacking. Neither assumption had evidence behind it.

The question is therefore an attribution one. If every episode outside range can be assigned to the
mechanism that started it, the resulting shares indicate where effort belongs.

A second question follows and changes what the first implies. An episode that a model could see coming
forty five minutes earlier is a candidate for anticipation; one that arrives unannounced needs a faster
or larger response instead. The same share of loss therefore points at different remedies depending on
whether it was foreseeable, and the two have to be measured together.

## Methods

Roughly 87,000 decision cycles and 1,100 episodes from eight participants between February and July
2026, recorded under `backtesting/scripts/2026-07-residency/`.

Each participant's timeline was segmented into episodes above 180 mg/dL and below 70, with brief
interruptions bridged where the gap was under twenty minutes. Each onset was attributed to one
proximate mechanism from the telemetry in the preceding forty five minutes, and the onset owns the
episode's minutes on the reasoning that preventing the onset prevents the episode. Minutes were counted
as cycles multiplied by the sensor interval.

The mechanism assignment uses an ordered chain, so a cycle matching two causes is credited to whichever
appears first. The ordering was fixed before the results were seen.

The foreseeability layer used gradient boosting to predict forward highs and forward lows an hour
ahead, with participants held out as folds so that no within-participant leakage could inflate the
figures, and scored the cycle forty five minutes before each onset. Base rates were 0.09 for forward
highs and 0.04 for forward lows.

The antecedent defining a rescue-related low is taken from the three hours preceding the cycle rather
than the three hours following it. A forward-looking window encodes the outcome into the feature and
makes the resulting bucket close to tautological.

The attribution is descriptive over observed data. No counterfactual glucose is claimed, and assigning
an episode to a mechanism states that the mechanism was proximate, not that fixing it would have
prevented the episode.

## Results

Time above range divides across the cohort into brake suppression at 34 per cent, late commitment at
16, cap clipping at 15, recovering hold at 11, undersizing at 9, uncoverable at 10 and non-meal highs
at 5. Dispersion between participants is wider than the cohort figure suggests: brake suppression runs
from 11 per cent for one participant to 47 for another, and cap clipping from 0 to 59.

Forward highs are predictable at an area under the curve of 0.83 and forward lows at 0.78.
Foreseeability separates the mechanisms. Brake suppression carries 1.5 times base risk forty five
minutes before onset and non-meal highs 2.4, so both are visible in advance. Cap clipping, undersizing
and uncoverable highs carry 0.5 to 0.9 times base risk and therefore arrive unannounced.

Feature importance corroborates the taxonomy. Forward highs are driven by glucose, insulin fraction,
recent meal insulin, hour, score and recent change; forward lows by glucose, recent meal insulin,
eventual glucose, hour, recent change, steps and sensitivity, the prominence of activity independently
supporting its position as the leading low mechanism.

Time below range is dominated by activity at 48 per cent pooled and 36 by participant median, then
basal and sensitivity drift at 30 pooled and 37 by median, stacking at 16 and 17, and rescue overshoot
at 7 pooled and 5 by median.

With a forward-looking rescue antecedent the same analysis places rescue overshoot at 37 per cent
pooled and 44 by median, second among low mechanisms, with basal and sensitivity drift at 1 per cent.

## Discussion

The headline is that lows dominate the addressable loss and are not a dosing-brake problem, while the
addressable part of the highs is sizing and timing rather than restraint. That reoriented the
programme: the exercise protections and the step ingest follow from the activity share, per-participant
cap sizing follows from cap clipping, and the commitment age gate follows from late commitment being
both large and foreseeable.

The dependence of the low-cause ranking on how the rescue antecedent is defined is worth stating
plainly, because the difference is not small and is not visible by inspection. A feature computed over
a window that includes the outcome will rank highly for that reason alone, and the ranking it produces
is an artefact of the construction rather than a property of the data. With the antecedent taken
backwards, meaning a genuine recurring or see-sawing pattern, rescue overshoot ranks fourth and the
time reallocates almost entirely to basal and sensitivity drift. A rescue-handling lever justified by
the second-place ranking would have been built on a feature that partly encoded its own outcome. The
general requirement is that any feature computed with a forward window be checked against the direction
of the question being asked.

The brake share of 34 per cent is the other figure that does not survive scrutiny unchanged, for a
different reason. It is proximate rather than causal: the brake suppressing during a rise is not the
same as the brake being wrong, since some suppression is correct restraint at high insulin on board.
Pricing that properly requires a separate audit, which is the subject of the next paper and which
reduces the apparent opportunity considerably.

Two limitations bound everything here. The ordered chain means a cycle matching two causes is credited
to whichever appears first, and although the ordering was fixed in advance it remains a choice. And the
per-participant spread is wide enough that the cohort column is a poor description of any individual,
which is the argument for per-participant configuration that recurs throughout this programme.
