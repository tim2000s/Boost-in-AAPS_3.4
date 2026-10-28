# Boost V5/V6: cohort outcomes and shadow layer results


Prepared 2026-08-09 from the local database, covering the 28 days to that date.


## Summary


Across 9 participants running the V5/V6 engine, contributing 203 participant-days, time in range averaged 86.9 per cent (81.6 to 92.0) and time in the tighter band averaged 70.5 per cent (63.1 to 78.1). Time below 70 mg/dL averaged 2.9 per cent (1.9 to 4.0) and time below 54 mg/dL 0.4 per cent (0.2 to 0.6), so the cohort as a whole sits at or under both consensus floors, with individual variation set out below.


Of the shadow layers, the twin forecaster is more accurate than assuming no change for every participant who ran it, by about one milligram per decilitre, which is consistent but too small to act on. The V7 sizer disagrees with the engine in both directions and by a wide margin. The plateau nudge appears never to have been vetoed by its own safety floor, which is not a finding about safety but the signature of a defect in how that floor was read, and it means the plateau shadow data collected on these builds cannot be used.


## Which data enter the analysis


A participant-day is admitted where the V5/V6 engine accounted for at least 90 per cent of that day's decision cycles, the day carried at least 250 glucose readings, and those readings spanned at least 20 hours. The purity requirement is not a formality. Over this window the cohort includes a participant on a Trio shadow build, one running a silent V1, one who moved to a different closed loop part way through, and two who changed build mid-window. Selecting on dates alone would pool all of them.


| participant | days present | days admitted | mean V5/V6 share | reason days were dropped |
|---|---|---|---|---|
| A | 29 | 27 | 100% | 2 incomplete |
| B | 29 | 27 | 100% | 2 incomplete |
| C | 29 | 26 | 99% | 1 not V5/V6, 2 incomplete |
| D | 29 | 27 | 98% | 1 not V5/V6, 2 incomplete |
| E | 25 | 23 | 100% | 2 incomplete |
| F | 29 | 27 | 100% | 2 incomplete |
| G | 21 | 0 | 0% | 21 not V5/V6, 4 incomplete |
| H | 29 | 11 | 45% | 17 not V5/V6, 2 incomplete |
| I | 20 | 9 | 52% | 10 not V5/V6, 1 incomplete |
| J | 24 | 0 | 0% | 24 not V5/V6, 2 incomplete |
| tim | 29 | 26 | 100% | 3 incomplete |

## Glycaemic outcomes by participant


Intervals are from a bootstrap resampling whole days, since readings within a day are not independent.


| participant | days | TIR 70 to 180 | TING 63 to 140 | TAR above 180 | TBR below 70 | TBR below 54 | CV |
|---|---|---|---|---|---|---|---|
| A | 27 | 75.5% [72.0, 78.8] | 54.0% [50.2, 57.7] | 23.3% [20.0, 26.8] | 1.2% [0.6, 1.8] | 0.1% [0.0, 0.2] | 29.9% |
| B | 27 | 75.5% [70.6, 80.5] | 57.8% [52.2, 63.4] | 21.4% [16.5, 26.4] | 3.1% [1.9, 4.3] | 0.8% [0.4, 1.3] | 34.7% |
| C | 26 | 91.5% [89.3, 93.6] | 76.6% [73.2, 79.9] | 3.7% [2.0, 5.5] | 4.8% [3.8, 5.9] | 0.7% [0.3, 1.1] | 25.8% |
| D | 27 | 93.3% [90.7, 95.6] | 90.3% [86.1, 94.1] | 1.6% [0.5, 2.8] | 5.1% [3.4, 7.1] | 0.5% [0.3, 0.8] | 21.1% |
| E | 23 | 98.4% [97.0, 99.4] | 85.9% [81.8, 89.7] | 0.7% [0.1, 1.5] | 0.9% [0.3, 1.5] | 0.0% [0.0, 0.0] | 16.7% |
| F | 27 | 87.8% [84.0, 91.1] | 66.1% [62.7, 69.7] | 10.5% [7.1, 14.2] | 1.7% [1.1, 2.5] | 0.2% [0.1, 0.3] | 24.9% |
| H | 11 | 95.5% [93.7, 97.1] | 72.4% [66.0, 79.2] | 3.3% [1.4, 5.4] | 1.2% [0.4, 2.1] | 0.0% [0.0, 0.0] | 21.4% |
| I | 9 | 79.8% [74.9, 85.0] | 60.4% [50.4, 68.7] | 16.1% [10.7, 21.6] | 4.1% [0.7, 8.2] | 0.6% [0.0, 1.4] | 30.4% |
| tim | 26 | 84.7% [80.0, 88.5] | 71.3% [66.3, 75.6] | 11.1% [7.2, 15.6] | 4.3% [3.0, 5.8] | 0.7% [0.4, 1.1] | 32.6% |

## Cohort


Two summaries, because they answer different questions. The first weights each participant equally and its interval is taken by resampling participants, so it describes the group. The second pools every admitted day and describes the data rather than the group; its interval also resamples participants, since resampling days would treat one person's fortnight as independent evidence about another's.


| outcome | mean across participants | pooled across days |
|---|---|---|
| TIR 70 to 180 | 86.9% [81.6, 92.0] | 86.6% |
| TING 63 to 140 | 70.5% [63.1, 78.1] | 70.9% |
| TAR above 180 | 10.2% [5.2, 15.5] | 10.4% |
| TBR below 70 | 2.9% [1.9, 4.0] | 3.0% |
| TBR below 54 | 0.4% [0.2, 0.6] | 0.4% |
| CV | 26.4% [22.7, 30.0] | 26.6% |

The cohort comprises 9 participants contributing 203 participant-days.


## Standing against the safety floors


The consensus absolutes are 4 per cent below 70 mg/dL and 1 per cent below 54 mg/dL. The estimates above are the finding; this table asks the narrower question of whether a participant's interval clears the floor, which is a stricter test than whether the estimate does.


| participant | TBR below 70 | interval clears 4 per cent | TBR below 54 | interval clears 1 per cent |
|---|---|---|---|---|
| A | 1.2% | yes | 0.1% | yes |
| B | 3.1% | not resolved | 0.8% | not resolved |
| C | 4.8% | not resolved | 0.7% | not resolved |
| D | 5.1% | not resolved | 0.5% | yes |
| E | 0.9% | yes | 0.0% | yes |
| F | 1.7% | yes | 0.2% | yes |
| H | 1.2% | yes | 0.0% | yes |
| I | 4.1% | not resolved | 0.6% | not resolved |
| tim | 4.3% | not resolved | 0.7% | not resolved |

5 of 9 participants have a point estimate below the 4 per cent floor. Where an interval is not resolved the estimate still stands; what is unresolved is only whether the floor is cleared with confidence, and a longer window is the only remedy.


## Shadow layer results


These layers compute what they would have done and record it without acting. Results below are restricted to the same admitted participant-days.


### Plateau nudge


| participant | cycles with the layer | triggered | would have nudged | mean nudge |
|---|---|---|---|---|
| A | 2,882 | 6.9% | 6.9% | 0.10 U |
| B | 3,338 | 4.3% | 4.3% | 0.10 U |
| C | 2,560 | 4.2% | 4.2% | 0.10 U |
| E | 1,315 | 2.8% | 2.8% | 0.10 U |
| F | 3,209 | 7.8% | 7.8% | 0.10 U |
| I | 7,121 | 8.0% | 8.0% | 0.10 U |
| tim | 7,318 | 3.4% | 3.4% | 0.10 U |

On triggered cycles the floor state was ok on 100 per cent.


That figure should not be read as reassurance. The trigger rate and the would-nudge rate are identical for every participant, which means the floor vetoed nothing at all over the window. The floor on these builds read the forward-low forecast out of a formatted string with a pattern that could not match a negative number, so on precisely the cycles where the forecast was worst it failed to match, returned nothing, and passed. A floor that reports itself satisfied on every cycle is reporting that it is not working. The defect is fixed on the current branches, where the typed value is read directly and a missing value vetoes, but the data above predate that fix and the plateau shadow will have to be collected again before it can support any conclusion.


### V7 sizer


| participant | cycles | mean V7 dose at R7 | mean dose actually given | ratio | mean pLow90 |
|---|---|---|---|---|---|
| A | 1,863 | 0.073 U | 0.065 U | 1.12 | 0.086 |
| B | 2,201 | 0.174 U | 0.285 U | 0.61 | 0.111 |
| C | 1,492 | 0.037 U | 0.052 U | 0.70 | 0.082 |
| E | 854 | 0.059 U | 0.101 U | 0.58 | 0.062 |
| F | 2,093 | 0.092 U | 0.084 U | 1.09 | 0.075 |
| I | 4,669 | 0.033 U | 0.029 U | 1.17 | 0.095 |
| tim | 7,386 | 0.045 U | 0.075 U | 0.60 | 0.171 |

A ratio above one means the V7 sizer would have dosed more than the engine did, and below one that it would have dosed less. The sizer acts on nothing; this is the size of the disagreement, not evidence about which is right.


### Twin forecaster


The forecast is checked against what the glucose actually did thirty minutes later, alongside the trivial alternative of assuming no change. A forecaster that cannot beat persistence is not adding anything.


| participant | forecasts checked | twin mean absolute error | persistence | difference |
|---|---|---|---|---|
| A | 2,814 | 17.7 mg/dL | 17.8 mg/dL | -0.2 |
| B | 3,239 | 20.4 mg/dL | 21.8 mg/dL | -1.4 |
| C | 2,428 | 17.0 mg/dL | 18.2 mg/dL | -1.3 |
| E | 1,285 | 11.1 mg/dL | 11.2 mg/dL | -0.2 |
| F | 2,968 | 12.8 mg/dL | 15.1 mg/dL | -2.2 |
| I | 6,633 | 15.4 mg/dL | 17.2 mg/dL | -1.8 |
| tim | 7,537 | 20.5 mg/dL | 20.9 mg/dL | -0.5 |

The twin is more accurate than persistence for 7 of 7 participants. Across the cohort the mean difference is -1.1 mg/dL, where a negative number favours the twin.


Consistency and magnitude point in different directions here. Winning on every participant is unlikely to be chance, but the margin of about one milligram per decilitre against a persistence error of 17 is far too small to change a dosing decision. The earlier reading that the twin had no edge over persistence at thirty minutes is refined rather than overturned: there is an edge, it is reproducible, and it is negligible.


### Accelerometer meal detection


Recorded by tim alone, on 262 cycles, of which 33 triggered (12.6 per cent). A layer present on one participant supports no cohort statement and is reported as a single-participant observation.
