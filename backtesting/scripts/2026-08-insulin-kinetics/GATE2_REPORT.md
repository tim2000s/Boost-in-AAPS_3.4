# Gate 2 — insulin action peak from observed glucose

User **tim**, windows before 2026-08-04. 110 isolated fasting windows of 4 h (440 h total). DIA held at 600 min.


**Pooled peak estimate: 30.8 min**, window-bootstrap 95% CI [24.3, 38.6] (80 draws).


Per-window estimates: n=77, median 37.2, SD 38.0 min, IQR [22.8, 79.9].


## How big a shift could we detect?

| post-change windows | detectable shift (min, 80% power, alpha 0.05) |
|---|---|
| 5 | 49.1 |
| 10 | 35.7 |
| 20 | 26.7 |
| 40 | 20.7 |

Based on the observed between-window SD, so it already includes ordinary night-to-night variation rather than assuming it away. At roughly one usable window per night, the left column is also days of data.


**Read the absolute value with care:** sensor lag biases it late by a few minutes and that is not corrected here. The comparison this is built for — before vs after a change, same user, same sensor generation — cancels that offset.
