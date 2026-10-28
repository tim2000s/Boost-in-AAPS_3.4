# Will this rise be worth treating? 1,986,123 onsets across seven studies (2026-08-25)

*Reproduce: `rise_outcomes.py`, `rise_consequence.py` and `rise_delta_ci.py` against the `studies`
schema of the local TimescaleDB. 1,986,123 rise onsets extracted from 1,807 participants across all
seven studies; the modelling uses the first 200 participants, which is far more than the fold
structure needs and keeps the run inside the machine. Participants are held out as folds and
intervals come from resampling participants. Protocol:
`backtesting/protocols/2026-08_meal_size_readability_PREREG.md`, extension.*

## Why this question and not the other two

Detection answers whether food arrived and size answers how much. A controller at the moment it must
act needs neither. It needs to know whether the rise in front of it is going somewhere that matters.

That question has a property the other two lack. The answer is written in the trace afterwards, so
no announcement is required, and the five studies that ship no carbohydrate at all become usable.
They contribute 963 participants that have been unavailable to every question in this programme so
far.

Anchors are rise onsets built as the detection negatives were built, a rise of at least 25 mg/dL
within thirty minutes from a point above the hypoglycaemia threshold, which is approximately the set
of events a detector fires on. Outcomes are read from the trace: the peak rise over the onset
baseline within three hours, and the maximum glucose within two hours.

## What happens after a rise begins is close to settled by the fact that it began

| study | participants | rise onsets | reach 40 mg/dL | exceed 180 mg/dL |
|---|---|---|---|---|
| Loop | 850 | 1,251,245 | 0.837 | 0.566 |
| ReplaceBG | 196 | 181,934 | 0.846 | 0.690 |
| IOBP2 | 337 | 142,047 | 0.855 | 0.722 |
| PEDAP | 99 | 140,422 | 0.859 | 0.645 |
| Flair | 113 | 108,777 | 0.833 | 0.714 |
| DCLP5 | 100 | 86,183 | 0.851 | 0.698 |
| DCLP3 | 112 | 75,515 | 0.839 | 0.665 |

Seven populations differing in therapy, era and age agree to within two and a half points on the
share of rises that reach 40 mg/dL. Once a rise clears 25 mg/dL in thirty minutes, roughly five in
six go on to 40 whoever is wearing the sensor. That is why the thresholds swept below start at 60.

## Where the rise started carries most of it

| outcome | onset glucose alone | and the clock | with the shape at 10 min | at 20 min | at 30 min |
|---|---|---|---|---|---|
| peak rise 60 mg/dL or more | 0.677 | 0.717 | 0.731 | 0.750 | 0.799 |
| peak rise 80 or more | 0.664 | 0.702 | 0.715 | 0.729 | 0.771 |
| peak rise 100 or more | 0.657 | 0.692 | 0.704 | 0.718 | 0.756 |
| glucose exceeds 180 | 0.812 | 0.829 | 0.843 | 0.855 | 0.886 |
| glucose exceeds 250 | 0.810 | 0.827 | 0.840 | 0.849 | 0.877 |

Glucose at the onset, one number the controller already holds, reaches 0.812 for whether the
excursion will pass 180. Adding the clock, which is free, takes it to 0.829. Everything the shape of
the rise contributes sits on top of that.

## What the shape adds, tested as a difference

Comparing two areas under the curve that each carry their own interval says nothing about whether
they differ, since both arms score the same events from the same participants and their errors move
together. The interval below is on the difference, from resampling participants once per draw and
scoring both arms on that same resample.

| outcome | horizon | baseline | with shape | difference | 95% interval |
|---|---|---|---|---|---|
| peak rise 60 or more | 10 min | 0.717 | 0.731 | +0.0142 | +0.0126 to +0.0157 |
| peak rise 60 or more | 20 min | 0.717 | 0.750 | +0.0323 | +0.0300 to +0.0347 |
| glucose exceeds 180 | 10 min | 0.829 | 0.843 | +0.0140 | +0.0126 to +0.0156 |
| glucose exceeds 180 | 20 min | 0.829 | 0.855 | +0.0267 | +0.0245 to +0.0288 |

Every draw of a thousand falls above zero. The gains are real and they are small.

## The shape of the answer differs from the size result

For meal size the trace was worth 0.007 at ten minutes and 0.008 at sixty, flat, and flatness was
the diagnosis: information that does not improve as the excursion unfolds did not come from the
excursion. Here the contribution grows monotonically, +0.014 at ten minutes, +0.020 at fifteen,
+0.027 to +0.032 at twenty, and +0.049 to +0.082 at thirty, on every one of the five outcomes. That
is information genuinely arriving from the trajectory.

It arrives too slowly to be worth much where it would be spent. The margin that would change what
gets built was set at 0.05 by twenty minutes for the size question, and applying the same bar here
nothing clears it: the largest twenty-minute gain is +0.032. The bar is cleared at thirty minutes,
by which point the decision that mattered has been taken.

## What this supports

Whether a rise will be consequential is predictable, at 0.72 to 0.86 depending on what counts as
consequential, and almost all of that comes from where the rise started and what time it is. Both
are already in the controller's hand at the moment it acts, and neither requires a detector, a
model, or a trace.

The shape of the first ten to twenty minutes adds something real and adds it consistently across
five outcomes and seven populations, but between one and three points of separation is not what
changes a dosing decision. The remaining information arrives at thirty minutes and beyond, which
matches what the earlier commit-linked work found from the other direction: the excursion becomes
estimable at approximately the moment it ceases to matter.

Confidence: SOLID. Out of sample with participants held out, the differences tested as differences
rather than as two separate intervals, consistent in sign and in slope across five outcomes, and the
base rates replicated across seven independent studies.

## Limitations

The anchor already requires a 25 mg/dL rise, so this measures discrimination among rises that have
declared themselves and says nothing about the earlier question of which nascent rises become rises
at all. The modelling uses 200 of the 1,807 available participants; the intervals are narrow and the
effect sizes stable across the sweep, but a full-corpus run has not been done. Outcomes are read
from traces produced under active insulin therapy, so what is being predicted is the excursion that
occurred given the treatment given, not the excursion that would occur untreated. Nothing here
establishes that acting on such a prediction would improve any outcome, which no observational
corpus can settle.
