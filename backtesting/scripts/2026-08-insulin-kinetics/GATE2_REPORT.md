# Gate 2 — insulin action peak from observed glucose

User **G**. 112 isolated fasting windows of 4 h (tz America/Chicago; NO step data - exercise uncontrolled) (448 h total). DIA held at 600 min.


**Pooled peak estimate: 59.4 min**, window-bootstrap 95% CI [46.2, 71.5] (80 draws).


Per-window estimates: n=108, median 61.6, SD 34.1 min, IQR [38.6, 93.5].


## How big a shift could we detect?

| post-change windows | detectable shift (min, 80% power, alpha 0.05) |
|---|---|
| 5 | 43.6 |
| 10 | 31.5 |
| 20 | 23.2 |
| 40 | 17.6 |

Based on the observed between-window SD, so it already includes ordinary night-to-night variation rather than assuming it away. At roughly one usable window per night, the left column is also days of data.


**Read the absolute value with care:** sensor lag biases it late by a few minutes and that is not corrected here. The comparison this is built for — before vs after a change, same user, same sensor generation — cancels that offset.
