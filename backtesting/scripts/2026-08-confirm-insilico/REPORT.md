# In-silico trial of the confirm dose, one participant, thirty days (2026-08-13)

*Reproduce: `insilico_v2.py`. Self, 30 days to 2026-08-13 21:15. 84 confirms carrying 165.9 U,
median 1.70 U. Sensitivity taken from the record at each confirm, median 111 mg/dL/U. Outcomes are
counted per confirm over a four-hour window. `insilico_confirm.py` is the earlier construction and
is retained only because its diagnostics are cited below.*

## The counterfactual, and where it stops being valid

Reducing a confirm does not change the meal, so the carbohydrate side of the trajectory is held as
recorded and only the insulin side recomputed: insulin not delivered never acts, so glucose is
higher by the sensitivity at that confirm times the removed dose times the fraction of that bolus
which would have acted by then.

That fraction rises to one and stays there, which makes the modelled lift a permanent step. Summed
across a thirty-day record it does not converge: eighty-four steps of roughly a hundred mg/dL each
drive the modelled mean glucose into the thousands. Glucose is regulated and returns toward a set
point, so the approximation holds for one event over a few hours and cannot be carried across the
record. Masking the series to windows does not repair it either, because it puts a discontinuity at
each boundary and any time-weighted percentage computed over the masked set inherits it.

Everything here is therefore counted per confirm, as whether the nadir in that window cleared 70
and whether the peak crossed 180. No quantity is summed across the record.

## What the record cannot tell us

The model assumes removing d units raises glucose by ISF x d x acted(t). Across 80 confirms the
lowering it predicts by the nadir correlates with the observed peak-to-nadir fall at minus 0.03. A
larger confirm accompanies a larger meal, and the two move together, so the record contains no
usable check on the insulin effect. This is the confounding that puts the observational dose
response near 6 mg/dL per unit against a dithered estimate near 45.

Absolute effect sizes below are therefore uncalibrated. The insulin effect is scaled from half to
double so that the sensitivity of each conclusion to that assumption is visible.

## The record

Of 84 confirms, 42 are followed by a glucose below 70 within four hours and 12 by one below 54.
Half of all confirms sit in front of a low.

## Randomised assignment

Multiplier drawn per confirm, 400 replicates, at the recorded sensitivity.

| range | windows with a low | severe | newly above 180 | U withheld |
|---|---|---|---|---|
| observed | 42 | 12 | 0 | 0 |
| [0.85, 1.00] | 25 [21, 30] | 5 [3, 8] | 7 [4, 10] | 12.5 |
| [0.70, 1.00] | 18 [14, 23] | 3 [1, 6] | 12 [8, 15] | 24.8 |
| [0.50, 1.00] | 13 [9, 18] | 2 [0, 5] | 17 [13, 21] | 41.2 |
| [0.50, 0.90] | 8 [6, 11] | 1 [0, 2] | 20 [16, 23] | 49.7 |

The interval is the spread of the random assignment, which is what a single trial would draw from
once. It is not the uncertainty in the effect.

## Fixed multiplier, against the assumed insulin effect

Lows / severe / newly above 180.

| multiplier | U withheld | effect x0.5 | effect x1.0 | effect x2.0 |
|---|---|---|---|---|
| 1.00 | 0.0 | 42 / 12 / 0 | 42 / 12 / 0 | 42 / 12 / 0 |
| 0.95 | 8.3 | 38 / 10 / 4 | 29 / 8 / 5 | 20 / 3 / 9 |
| 0.90 | 16.6 | 29 / 8 / 5 | 20 / 3 / 9 | 11 / 1 / 16 |
| 0.85 | 24.9 | 20 / 3 / 7 | 15 / 3 / 13 | 8 / 0 / 22 |
| 0.80 | 33.2 | 20 / 3 / 9 | 11 / 1 / 16 | 5 / 0 / 24 |
| 0.70 | 49.8 | 15 / 3 / 13 | 8 / 0 / 22 | 0 / 0 / 26 |
| 0.50 | 83.0 | 9 / 0 / 18 | 4 / 0 / 25 | 0 / 0 / 26 |

Two things hold across the whole grid and one does not.

The direction holds. At every assumed insulin effect, reducing the confirm removes lows and adds
highs, and severe lows fall faster than lows.

The magnitude does not. At a multiplier of 0.90 the lows remaining are 29, 20 or 11 depending on
whether the insulin effect is half, as recorded, or double. That is the uncertainty the record
cannot close.

There is no knee in the curve. Benefit declines smoothly, at 29, 20, 15, 11, 8, 4 across the
column, and the cost rises smoothly against it. Nothing about the shape marks out a natural
stopping point, and the registered 0.70 is as defensible as any other value on it.

## The confirms that carry it

Halved individually at the recorded sensitivity, ranked by how far the nadir moves.

| when | dose | ISF | BG | IOB | nadir | becomes | peak | becomes |
|---|---|---|---|---|---|---|---|---|
| Thu 23 14:45 | 1.45 | 198 | 136 | −0.09 | 62 | 183 | 279 | 290 |
| Mon 03 09:26 | 1.95 | 147 | 148 | 0.27 | 51 | 150 | 179 | 274 |
| Mon 20 16:17 | 3.00 | 95 | 142 | 0.72 | 56 | 153 | 260 | 315 |
| Mon 10 17:46 | 3.75 | 68 | 137 | 0.96 | 59 | 154 | 183 | 214 |
| Sat 25 19:30 | 1.55 | 126 | 164 | 0.17 | 67 | 161 | 247 | 276 |
| Thu 30 09:55 | 1.30 | 179 | 165 | 0.61 | 65 | 158 | 221 | 248 |
| Mon 10 10:06 | 4.50 | 59 | 204 | 2.41 | 63 | 152 | 266 | 322 |

Halving every confirm individually rescues 38 of the 42 windows containing a low and creates 25
newly above 180. The recurring shape is a confirm at ordinary glucose, 122 to 165, with little
insulin already present, which is the small-meal signature identified separately.

The nadirs in the counterfactual column, at 150 to 183, are where the uncalibrated insulin effect
shows itself most plainly. A shift of 90 to 120 mg/dL from halving a single bolus is at the limit
of what is credible and is a direct consequence of a sensitivity of 100 to 200 mg/dL/U combined
with a linear model that never washes out.

## Conclusion

Half of this participant's confirms precede a low, which is the finding that does not depend on any
modelling: it is counted from the record.

Reducing the confirm dose removes lows and adds highs in a smooth trade with no natural stopping
point, and severe lows fall faster than lows across every assumption tested. That supports running
the registered trial and gives no reason to prefer a different multiplier.

The absolute numbers should not be quoted. They rest on an insulin-effect model that the record
cannot check, and they move by a factor of two to three across a plausible range for it.

Confidence: SOLID for the observation that 42 of 84 confirm windows contain a low. SPECULATIVE for
every counterfactual quantity, on a one-armed bound with an uncalibrated insulin effect, the loop's
response unmodelled, and one participant.
