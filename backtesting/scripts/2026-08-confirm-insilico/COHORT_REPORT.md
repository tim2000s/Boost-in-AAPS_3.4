# The confirm trial across the cohort, and what the control did to it

*Reproduce: `cohort_trial.py --reps 3000`. Nine participants, 30 days to 2026-08-13, 591 confirms.
G excluded: that participant runs the engine in shadow under a different loop and logs no
sensitivity. Charts in `figs_cohort/`.*

## The phenomenon generalises

| user | confirms | median dose | ISF | followed by a low | severe | rate |
|---|---|---|---|---|---|---|
| A | 72 | 2.67 | 30 | 13 | 3 | 0.18 |
| B | 123 | 2.35 | 25 | 28 | 10 | 0.23 |
| C | 113 | 1.75 | 48 | 56 | 10 | 0.50 |
| D | 75 | 1.50 | 33 | 24 | 13 | 0.32 |
| E | 20 | 1.89 | 39 | 6 | 0 | 0.30 |
| F | 64 | 2.12 | 47 | 14 | 6 | 0.22 |
| H | 24 | 1.30 | 46 | 8 | 0 | 0.33 |
| I | 16 | 0.85 | 59 | 7 | 2 | 0.44 |
| self | 84 | 1.70 | 111 | 42 | 12 | 0.50 |
| **cohort** | **591** | | | **198** | **56** | **0.34** |

A third of every confirm in this cohort is followed by a glucose below 70 within four hours, and
every participant is above 18 per cent. This is counted from the record and depends on nothing
modelled. It is the strongest reason to run the registered trial.

## The attribution split, and what it costs the argument

For each confirm the glucose deficit the model attributes to it by the nadir is set against the
fall observed from the peak of the excursion. At or above one the confirm can account for the whole
fall and a reduction could plausibly have altered the outcome. Below one it cannot.

| user | median ratio | model explains | lows there | it does not | lows there |
|---|---|---|---|---|---|
| A | 0.60 | 20 | 1 | 52 | 12 |
| B | 0.44 | 18 | 2 | 105 | 26 |
| C | 0.74 | 36 | 13 | 77 | 43 |
| D | 0.65 | 26 | 6 | 49 | 18 |
| E | 0.67 | 6 | 3 | 14 | 3 |
| F | 1.13 | 36 | 7 | 28 | 7 |
| H | 0.89 | 10 | 0 | 14 | 8 |
| I | 0.28 | 3 | 0 | 13 | 7 |
| self | 1.34 | 59 | 25 | 25 | 17 |
| **cohort** | | **214** | **57** | **377** | **141** |

Only 214 of 591 confirms are ones the model can account for, and 141 of the 198 lows sit after a
confirm it cannot. For seven of the nine participants the median ratio is below one, meaning the
confirm bolus is not on its own sufficient to explain the fall that followed it.

The exception is instructive rather than reassuring. The two participants whose confirms the model
does explain, self at 1.34 and F at 1.13, are the two with the highest recorded sensitivity, 111
and 47 against 25 to 48 for the rest. The attribution ratio scales directly with sensitivity, so
what separates them may be how much glucose impact the model assigns per unit rather than anything
about their confirms. That is a property of the pricing, not a finding about the participants.

## The trial on the confirms the model can explain

Multiplier uniform on [0.4, 1.0], 3,000 replicates, at the recorded sensitivity. Counts per
replicate.

| user | confirms | observed lows | after | severe after | newly above 180 | U withheld |
|---|---|---|---|---|---|---|
| A | 20 | 1 | 0 [0, 1] | 0 [0, 0] | 2 [1, 3] | 23.5 |
| B | 18 | 2 | 0 [0, 1] | 0 [0, 0] | 3 [2, 5] | 16.6 |
| C | 36 | 13 | 2 [0, 4] | 0 [0, 1] | 15 [10, 19] | 18.7 |
| D | 26 | 6 | 2 [0, 5] | 0 [0, 1] | 2 [0, 4] | 19.2 |
| E | 6 | 3 | 0 [0, 1] | 0 [0, 0] | 2 [1, 4] | 4.2 |
| F | 36 | 7 | 1 [0, 4] | 0 [0, 1] | 10 [7, 13] | 32.7 |
| H | 10 | 0 | 0 [0, 0] | 0 [0, 0] | 3 [1, 4] | 6.6 |
| I | 3 | 0 | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 1.4 |
| self | 59 | 25 | 3 [0, 6] | 0 [0, 2] | 17 [13, 20] | 37.9 |
| **cohort** | **214** | **57** | **9 [4, 14]** | **1 [0, 3]** | **54 [47, 62]** | **160.7** |

Every participant moves the same way. Against the assumed insulin effect the cohort figure runs 17,
9 and 4 lows remaining at half, one and double, with 31, 54 and 82 windows newly taken above 180.

## What the control found

The reduction was applied to the confirms the model says it cannot explain, where by construction
it should do little.

| set | confirms | observed lows | after | share removed |
|---|---|---|---|---|
| explained | 214 | 57 | 9 [4, 14] | 0.84 |
| unexplained | 377 | 141 | 69 [60, 78] | 0.51 |

It removes 51 per cent of the lows it has already declared itself unable to account for. The split
discriminates, at 0.84 against 0.51, so the attribution is carrying real information. But a method
that eliminates half the events it admits it cannot explain is crediting itself with a great deal,
and the honest reading is that the in-silico effect sizes are inflated across both sets rather than
only in the second.

The mechanism is not mysterious. Any reduction raises the whole trajectory by a monotone function
of the withheld insulin, so a low sitting a few mg/dL below 70 will clear the threshold whatever
caused it. The counterfactual has no way to leave an event alone.

## Conclusion

Run the registered trial. The justification is the first table and nothing else in this document:
a third of all confirms across nine participants precede a low, every participant is above 18 per
cent, and two are at 50. That is the largest identified concentration of hypoglycaemia in the
cohort and it is arithmetic on the record.

Do not use the in-silico effect sizes to size it. Three separate results say they are optimistic.
The model can account for the fall in only 214 of 591 confirms, so most of the record is outside
what it can legitimately speak to. It removes half the lows in exactly the set it says it cannot
explain. And the two participants where the attribution does hold are the two with the highest
recorded sensitivity, which is the parameter the ratio is most sensitive to.

The prospective trial is the only instrument that settles this, which is what it was registered
for. What this exercise has produced is a defensible ordering of who to run it on. C and self carry
the highest confirm-related low rates at 0.50, and D the highest severe rate at 13 of 75. Those
three are where an effect, if there is one, will be visible soonest.

Confidence: SOLID for the cohort low rate of 0.34 and its per-participant spread, which are
counted. PROVISIONAL for the attribution split, which depends on a sensitivity the record cannot
calibrate. SPECULATIVE for every counterfactual count, and the control is the reason.

## Re-run against the TING floor

The threshold above is 70 mg/dL. TING runs from 3.5 to 7.8 mmol/L, so its floor is 63, and a nadir
below that is a fall out of the tight band rather than a brush with the conventional line.
Repeating everything at 63:

| user | confirms | nadir below 63 | severe | rate |
|---|---|---|---|---|
| A | 72 | 10 | 3 | 0.14 |
| B | 123 | 16 | 10 | 0.13 |
| C | 113 | 39 | 10 | 0.35 |
| D | 75 | 24 | 13 | 0.32 |
| E | 20 | 4 | 0 | 0.20 |
| F | 64 | 12 | 6 | 0.19 |
| H | 24 | 4 | 0 | 0.17 |
| I | 16 | 4 | 2 | 0.25 |
| self | 84 | 25 | 12 | 0.30 |
| **cohort** | **591** | **138** | **56** | **0.23** |

Just under a quarter of confirms are followed by a nadir below the tight band, against a third
below 70. Every participant remains above 0.13. The ordering changes: C at 0.35, D at 0.32 and self
at 0.30 are the three highest, where at the looser threshold C and self were level at 0.50 and I
was third. D is unchanged between the two thresholds at 24, meaning every one of D's
confirm-related lows is already below the tight band, and D also carries the highest severe count
at 13 of 75.

The single-participant figures move the same way: 25 of 84 confirms rather than 42, with the
randomised reduction leaving 4 [1, 7] at the recorded sensitivity and the nadir rising by a median
of 35 mg/dL as before.

## What the stricter threshold does to the control, which is the point

| threshold | explained set | unexplained set |
|---|---|---|
| below 70 | 0.84 of lows removed | 0.51 |
| below 63 | 0.89 | 0.64 |

The control gets worse rather than better. Tightening the threshold was expected to help, on the
reasoning that a nadir sitting a couple of mg/dL under 70 flips on almost any lift while a genuinely
deep one should not. The opposite happens: the share of unexplained lows the model claims to remove
rises from 0.51 to 0.64.

The explanation is that the marginal events were never the problem. Raising the bar to 63 removes
the shallow lows from the numerator altogether, and what remains are deep ones which the modelled
lift, at a median sensitivity of 111 mg/dL/U for one participant and 25 to 59 for the rest applied
to roughly half a unit, is more than large enough to clear anyway. The credulity is in the size of
the lift, not in where the line is drawn.

That closes off threshold choice as a way of making this method more honest. Either the insulin
effect is calibrated, which the record cannot do, or the counterfactual is abandoned in favour of
the prospective trial. It also means the conclusion is unchanged: the trial is justified by the
counted rates, and the modelled effect sizes should not be used to size it at either threshold.
