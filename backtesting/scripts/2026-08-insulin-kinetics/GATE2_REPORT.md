# Gate 2 — insulin action peak from observed glucose

User **tim**, windows before 2026-08-04. 121 isolated fasting windows of 4 h (484 h total). DIA held at 600 min.


**Pooled peak estimate: 35.3 min**, window-bootstrap 95% CI [29.5, 46.1] (200 draws).


Per-window estimates: n=95, median 54.6, SD 37.2 min, IQR [29.9, 86.7].


## How big a shift could we detect?

| post-change windows | detectable shift (min, 80% power, alpha 0.05) |
|---|---|
| 5 | 47.8 |
| 10 | 34.6 |
| 20 | 25.6 |
| 40 | 19.6 |

Based on the observed between-window SD, so it already includes ordinary night-to-night variation rather than assuming it away. At roughly one usable window per night, the left column is also days of data.


**Read the absolute value with care:** sensor lag biases it late by a few minutes and that is not corrected here. The comparison this is built for — before vs after a change, same user, same sensor generation — cancels that offset.
