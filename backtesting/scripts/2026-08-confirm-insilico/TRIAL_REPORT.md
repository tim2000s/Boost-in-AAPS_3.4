# Randomised in-silico trial of the confirm bolus: one participant, thirty days

*Reproduce: `confirm_trial.py --reps 3000`. Self, 30 days to 2026-08-13. 84 confirms carrying
165.9 U, median 1.70 U. Sensitivity from the record at each confirm, median 111 mg/dL/U, range 41
to 216. Multiplier drawn uniformly on [0.4, 1.0] per confirm, 3,000 replicates across 14 cores.
Charts in `figs/`.*

## Design

Every entry into CONFIRMED has its bolus scaled by a randomly drawn multiplier. The withheld
insulin is priced through the sensitivity recorded at that confirm and the app's own insulin
curve, and the four hours that followed are re-read: if they contained a low, how much less deep
it becomes; if they contained a high, how much worse.

Each confirm is evaluated inside its own window and nothing is summed across the record. The
fraction of a bolus that has acted rises to one and stays there, so a modelled lift is a permanent
step; carried across thirty days, eighty-four such steps drive the modelled mean glucose into the
thousands. The approximation is usable for one bolus over a few hours and nowhere else.

The insulin curve was checked rather than assumed. Fitting the app's own recorded insulin on board
after each confirm prefers a 40-minute peak and a 240-minute duration over the 55 and 360 first
used, at a median error of 0.42 U against 0.60. The fit is contaminated by the basal arm and is
indicative rather than exact, and curve uncertainty is in any case subsumed by the sensitivity
sweep, since the modelled lift is sensitivity times removed dose times acted fraction and scaling
either scales the product.

The sensitivity itself cannot be calibrated from this record. The lowering the model predicts
correlates with the observed peak-to-nadir fall at about minus 0.03 across these confirms, because
larger confirms accompany larger meals and the two move together. Everything is therefore reported
at half, one and double the recorded sensitivity, and a conclusion that does not hold across that
range is not treated as one.

## What the confirm contributes

The recorded insulin on board is a net figure, negative on 27 per cent of cycles when basal is
suppressed below profile, so it cannot serve as the denominator of a share. What is well defined
is the confirm's own bolus still present at the nadir and the glucose deficit the model attributes
to it, set against the fall from the peak of the excursion, since insulin works against the meal.

| | median | quartiles |
|---|---|---|
| confirm's own bolus still on board at the nadir | 0.15 U | 0.00 to 0.58 |
| glucose deficit attributed to it by then | 163 mg/dL | 103 to 229 |
| observed fall, peak to nadir | 124 mg/dL | 85 to 153 |
| net insulin on board at the nadir | 0.35 U | 0.09 to 0.79 |

The ratio of attributed deficit to observed fall has a median of 1.34. For 59 of 84 confirms the
model already accounts for the entire fall, which makes the confirm a plausible cause of what
followed. For 25 it does not, and for those the low was substantially somebody else's work: other
insulin, or the meal simply ending, and reducing the confirm would not have prevented it.

That ratio also bounds the model's optimism. A value above one is expected, since the meal is
pushing upward over the same interval, but a median of 1.34 with a quarter of confirms above two
says the linear model is generous rather than conservative.

## The record

Of 84 confirms, 42 are followed by a glucose below 70 within four hours and 12 by one below 54.
Half of every confirm this participant makes sits in front of a low. That figure is counted, not
modelled, and does not depend on anything above.

## The trial

Counts are per replicate across all 84 confirms, median and the central 95 per cent of draws.

| insulin effect | windows with a low | severe | newly above 180 |
|---|---|---|---|
| observed | 42 | 12 | 0 |
| half | 15 [11, 20] | 2 [0, 5] | 13 [10, 17] |
| as recorded | 8 [4, 13] | 1 [0, 3] | 19 [15, 23] |
| double | 4 [1, 8] | 0 [0, 2] | 23 [19, 25] |

A median of 49.7 U withheld of the 165.9 committed, or 30 per cent. The interval is the spread of
the random assignment, which is what a single trial would draw once; it is not the uncertainty in
the effect, which is the row-to-row spread.

## How much less bad, how much worse

Depth is the area outside range within the window, in mg/dL minutes, pooled across replicates at
the recorded sensitivity.

For the 42 windows that contained a low, the nadir rises by a median of 35.1 mg/dL, with a tenth
to ninetieth percentile of 6 to 87, and the depth below 70 falls by a median of 125 mg/dL minutes.
Every draw improves it: there is no replicate in which reducing a confirm deepens a low, which
follows from the model's structure rather than from the data.

Across all 84 windows the peak rises by a median of 23.6 mg/dL, with a tenth to ninetieth
percentile of 1 to 95, and the depth above 180 rises by a median of 1,407 mg/dL minutes.

The asymmetry is the finding. The benefit is concentrated and bounded, since a nadir can only rise
so far before it stops being a low, while the cost is diffuse and unbounded, since a peak can keep
climbing. That is visible in the trade chart as a curve that turns over: the first units withheld
buy lows cheaply and the last ones buy almost nothing while still costing exposure.

## Charts

`01_dose_response.png` sets hypoglycaemia and hyperglycaemia against the multiplier, with the
sensitivity sweep as dotted bounds. `02_trade.png` plots windows rescued against windows newly
taken above 180. `03_per_confirm.png` shows each confirm halved individually, insulin withheld
against nadir gained, sized by how much of the fall the confirm accounts for. `04_nadir.png`
compares the distribution of nadirs observed and at a 0.8 multiplier. `05_bgi.png` is the
confirm's own glucose impact over time at three multipliers. `06_attribution.png` sets the benefit
against the attribution ratio.

## Does this justify running it against the other participants

Yes, with one change to the design.

The case for it is that the headline is not a modelled quantity. Half of this participant's
confirms precede a low and a sixth precede a severe one, and that is arithmetic on the record. If
the other participants show anything close to it, the confirm is the single largest identified
source of hypoglycaemia in the cohort and the registered trial is aimed at the right thing.

The change is that the ratio of attributed deficit to observed fall should be computed first and
used to exclude confirms the model cannot explain. Twenty-five of these 84 have a low that the
confirm cannot account for, and including them makes the intervention look effective at events it
could not have altered. Reporting the trial on the 59 it can explain, with the other 25 shown
separately, is the honest split and it is cheap to produce.

Two things should not be carried across. The absolute counts depend on a sensitivity the record
cannot calibrate and move by a factor of three across a plausible range for it. And the cost side
is understated throughout, because the loop is not re-run and would have dosed into the higher
glucose these counterfactuals produce.

Confidence: SOLID for the observation that 42 of 84 confirm windows contain a low, which is
counted. PROVISIONAL for the direction and the ordering of confirms by benefit. SPECULATIVE for
every absolute counterfactual count.
