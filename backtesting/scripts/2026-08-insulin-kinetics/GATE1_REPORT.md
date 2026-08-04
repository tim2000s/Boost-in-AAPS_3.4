# Gate 1 — recovering a known insulin curve

User **G**, last 60 days: 14865 cycles, 5496 dosing bins (1421 U total).


Deconvolves the logged bolus-only IOB series against the delivered boluses. The answer is known by construction — it must return the configured curve.


| | configured | recovered | 95% CI |
|---|---|---|---|
| peak (min) | 38 | **33.9** | [33.2, 35.1] |
| DIA (min)  | 600 | **285** | [242, 340] |

Fit RMSE 0.2074 U against an IOB series of RMS 1.1034 U (relative 0.1879).


**GATE: FAIL** — the estimator did NOT return the configured curve. Since the relationship is an exact identity, this is a defect in the method or an unmodelled term (check: does the logged IOB include basal? is the configured curve actually what we assumed?), NOT a finding about insulin.


## Peak of ACTION vs peak of IOB decay

For the recovered curve, action peaks at **34 min** — this is the number the loop uses, and the one a glucose-based estimate is comparable to.
