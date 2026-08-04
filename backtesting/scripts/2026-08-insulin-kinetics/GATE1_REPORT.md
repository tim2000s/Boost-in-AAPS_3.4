# Gate 1 — recovering a known insulin curve

User **tim**, last 45 days: 11847 cycles, 1588 dosing bins (448 U total).


Deconvolves the logged bolus-only IOB series against the delivered boluses. The answer is known by construction — it must return the configured curve.


| | configured | recovered | 95% CI |
|---|---|---|---|
| peak (min) | 38 | **36.3** | [35.8, 36.7] |
| DIA (min)  | 600 | **600** | [600, 600] |

Fit RMSE 0.1917 U against an IOB series of RMS 0.6716 U (relative 0.2854).


**GATE: PASS** — both parameters recovered within tolerance, so the kernel is identifiable under this user's real dose spacing and the method may proceed to observed glucose.


## Peak of ACTION vs peak of IOB decay

For the recovered curve, action peaks at **36 min** — this is the number the loop uses, and the one a glucose-based estimate is comparable to.
