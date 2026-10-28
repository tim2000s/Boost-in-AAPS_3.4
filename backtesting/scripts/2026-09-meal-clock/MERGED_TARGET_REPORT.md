# Does counting a meal properly make its size readable?

The readability study scored its models against the first entry of a cluster. Anything entered
within ninety minutes of it was skipped, and the meal's grams were that first entry alone. Measured
against the raw table, that discards 26 per cent of entries and 22 per cent of all carbohydrate,
and for the 28 per cent of meals that lose something the recorded size is a median 25 g against an
actual 55 g occasion.

That is a target defect rather than a modelling one, and it had to be tested rather than argued
about. If the glucose trace responds to what was eaten, a model scored against a value that
understates a quarter of its cases by about half is being marked against the wrong answer.

## The comparison

`extract_meals_merged.py` rebuilds the extraction with one change: entries inside the separation
window are added to the meal they belong to instead of dropped. Every filter, the onset rule, the
shape features, the horizons and the participant features are imported from the original rather
than reimplemented, so nothing else can move. The meal boundaries are identical, both extractions
produce exactly 492,440 Loop meals, and only the grams differ.

Loop's median meal goes from 28 g to 34 g. Twenty-two per cent of meals are assembled from more
than one entry and those come out at 55 g.

## Discrimination

Large meals, 40 g or more, against small ones, 20 g or less. The figure is the increment the
glucose trace adds over a matched baseline holding the same non-trace information.

| horizon | over the clock, original | merged | over person, clock and history, original | merged |
|---|---|---|---|---|
| 10 min | +0.008 | +0.006 | +0.021 | +0.032 |
| 20 min | +0.011 | +0.008 | +0.021 | +0.032 |
| 60 min | +0.053 | +0.054 | +0.026 | +0.041 |

The pre-registered margin was 0.05 at twenty minutes or less. Nothing clears it on either target.

Against the fuller baseline the increment does rise by about half, from +0.021 to +0.032 at ten
minutes, which is the direction a less noisy target should move it. It is still under the bar, and
under it by a margin that no amount of the same kind of improvement would close.

## Quantity

Mean absolute error in grams, against predicting each participant's own median meal and looking at
no glucose at all.

| horizon | model, original | own median, original | model, merged | own median, merged |
|---|---|---|---|---|
| 10 min | 13.1 g | 13.0 g | 17.0 g | 17.0 g |
| 60 min | 13.0 g | 13.0 g | 16.8 g | 17.0 g |

The model matches the participant's own median on both targets and beats it on neither. The
absolute error is larger on the merged target only because the target itself is larger and more
spread.

## What this settles

Counting meals properly does not make their size readable from the glucose trace. The reason the
original result held is not that the target was noisy: 40 g of difference moves the ten-minute rise
by under 1 mg/dL against a between-meal spread of about 10, and merging changes the target without
touching that ratio.

The correction still matters for how the work is described. The size distribution everyone has been
quoting was a distribution of first entries, its median was 28 g rather than 34, and the paper's
methods section said entries were merged when the code discards them.

One caveat on the comparison. Merging moves meals across the 40 g boundary, so the class balance is
not identical between the two runs: large meals become the majority. The two discrimination columns
are therefore not scored on exactly the same events, which is unavoidable when the quantity being
classified is the thing being corrected.
