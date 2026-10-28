# Boost cohort: outcomes and shadow coverage


Last 28 days, 11 participants. A day enters only if it carries at least 250 readings spanning at least 20 hours, so a day still in progress is excluded rather than counted as unusually good.


## Glycaemic outcomes


| user | days | TIR | TING | TBR<70 (95% CI) | TBR<54 (95% CI) | CV |
|---|---|---|---|---|---|---|
| A | 27 | 75.5% | 54.0% | 1.2% [0.6, 1.8] | 0.1% [0.0, 0.2] | 29.9% |
| B | 27 | 75.5% | 57.8% | 3.1% [1.9, 4.4] | 0.8% [0.4, 1.3] | 34.7% |
| C | 27 | 91.8% | 77.0% | 4.7% [3.6, 5.8] | 0.6% [0.3, 1.1] | 25.8% |
| D | 27 | 93.3% | 90.3% | 5.1% [3.4, 7.1] | 0.5% [0.3, 0.8] | 21.1% |
| E | 23 | 98.4% | 85.9% | 0.9% [0.3, 1.5] | 0.0% [0.0, 0.0] | 16.7% |
| F | 27 | 87.8% | 66.1% | 1.7% [1.0, 2.5] | 0.2% [0.1, 0.3] | 24.9% |
| G | 17 | 87.1% | 72.3% | 3.4% [2.1, 4.7] | 0.5% [0.2, 0.8] | 29.8% |
| H | 27 | 90.8% | 74.4% | 3.0% [1.7, 4.5] | 0.4% [0.1, 0.8] | 25.2% |
| I | 19 | 80.2% | 60.8% | 3.2% [1.2, 5.7] | 0.3% [0.0, 0.7] | 28.9% |
| J | 22 | 75.1% | 49.1% | 4.3% [2.5, 6.6] | 1.2% [0.6, 2.0] | 30.7% |
| tim | 26 | 84.7% | 71.3% | 4.3% [3.0, 5.8] | 0.7% [0.4, 1.1] | 32.6% |

## Standing against the safety floors


The consensus absolutes are 4 per cent for time below 70 mg/dL and 1 per cent for time below 54 mg/dL. A participant is counted as breaching only where the whole interval sits above the floor, and as compliant only where the whole interval sits below it. An interval spanning the floor is neither, and is reported as undetermined at this sample size rather than resolved in either direction.


| user | TBR<70 verdict | TBR<54 verdict |
|---|---|---|
| A | compliant | compliant |
| B | undetermined | undetermined |
| C | undetermined | undetermined |
| D | undetermined | compliant |
| E | compliant | compliant |
| F | compliant | compliant |
| G | undetermined | compliant |
| H | undetermined | compliant |
| I | undetermined | compliant |
| J | undetermined | undetermined |
| tim | undetermined | undetermined |

On time below 70 mg/dL that is 0 breaching, 3 compliant and 8 undetermined across 11 participants.


## Shadow layer coverage


Each layer computes what it would have done and records it without acting. Coverage is the share of decision cycles in the window carrying a value for that layer, which is what determines whether the layer can be analysed for a given participant at all.


| user | cycles | V7 sizer | Twin forecaster | Plateau nudge | Accel meal detect |
|---|---|---|---|---|---|
| A | 10,284 | 18% | 28% | 28% | none |
| B | 10,558 | 21% | 32% | 32% | none |
| C | 11,939 | 12% | 21% | 21% | none |
| D | 10,248 | none | none | none | none |
| E | 7,994 | 11% | 16% | 16% | none |
| F | 11,998 | 17% | 27% | 27% | none |
| G | 8,951 | none | none | none | none |
| H | 12,805 | none | none | none | none |
| I | 15,618 | 30% | 46% | 46% | none |
| J | 10,068 | none | none | none | none |
| tim | 10,476 | 71% | 75% | 70% | 3% |

## What the shadow layers recorded


V7 sizer: recorded by A (1,863 cycles), B (2,201 cycles), C (1,492 cycles), E (854 cycles), F (2,093 cycles), I (4,669 cycles), tim (7,393 cycles).


Twin forecaster: recorded by A (2,882 cycles), B (3,338 cycles), C (2,560 cycles), E (1,315 cycles), F (3,209 cycles), I (7,121 cycles), tim (7,840 cycles).


Plateau nudge: recorded by A (2,882 cycles), B (3,338 cycles), C (2,560 cycles), E (1,315 cycles), F (3,209 cycles), I (7,121 cycles), tim (7,318 cycles).


Accel meal detect: recorded by tim (262 cycles).


A layer present on one participant only can still be read, but nothing about it generalises, and it should be reported as a single-participant observation.
