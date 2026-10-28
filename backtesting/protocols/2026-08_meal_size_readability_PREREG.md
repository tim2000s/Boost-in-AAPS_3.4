# Pre-registered protocol: is meal size readable from the glucose trace?

Status: pre-registered, analysis plan fixed before any model is fitted.
Registered: 2026-08-25.
Version: 1.1.
Supersedes nothing. Re-opens a question closed in `scripts/2026-08-carb-signature/`.

## 1. Why this is being re-opened

The carb-signature study of 2026-08-13 concluded that meal size is not readable from the glucose
trace at any horizon that would let a dose be sized. Held out by participant, a large meal was
separated from a small one with an area under the curve of 0.267 at ten minutes and 0.508 at
forty five; as a quantity the correlation with announced carbohydrate was negative at every
horizon and the mean absolute error of 18 to 21 g was worse than the 13.2 g obtained by predicting
the median. The finding was labelled SOLID and it closed dose sizing to the meal. The staged
response design rests on it.

It rests on 592 meals from six participants, of whom one contributed 372. The report says so in
its own limitations, and it offers a mechanism for the sub-chance result: that the mapping from
carbohydrate to early glucose differs between people, so a model fitted on some people is actively
misled on others. Six participants cannot test that. The confidence interval at ten minutes runs
from 0.167 to 0.553 and therefore includes chance, so what the data support is that size is not
usefully readable, not that the relationship inverts. The inversion is an interpretation.

A corpus is now available in the `studies` schema that removes the constraint. Loop contributes
1,467,850 announced carbohydrate entries across 919 participants and REPLACE-BG a further 150,060
across 196. On a sample of 25 Loop participants, 30,340 entries of 15 g or more had glucose
spanning 45 minutes before to 180 minutes after, a coverage of 98 per cent. The analysable set is
of the order of a million meals with about a thousand participants available as folds, against 592
meals and six.

There is a second reason to re-open it, which the prior study could not examine. Its meals were
announced, and an announced meal is usually bolused for. A bolus computed from the carbohydrate
damps the early rise in proportion to the amount eaten, and a pre-bolus can flatten or invert it
altogether. That is a candidate explanation for an out-of-sample result below chance which has
nothing to do with people differing from one another, and it would not transfer to Boost, where
meals are not announced and the only insulin on the rise is what the loop itself decides to give.
In a 40 participant sample of Loop, 79.6 per cent of meals were bolused within five minutes of the
entry, 5.8 per cent were pre-bolused, and 6.5 per cent carried no bolus within an hour either way.
At full scale that is tens of thousands of meals in every stratum, so the two explanations can be
separated.

## 2. Data and its limits

Seven JAEB public datasets are held in the `studies` schema, joined throughout on `subject_id`,
formatted as study and patient identifier. Only Loop and REPLACE-BG carry carbohydrate and both
carry insulin, so only those two enter this work. FLAIR ships no pump file at all and the
remaining four ship no carbohydrate.

Dates are de-identified and the method differs by study, which `studies.study` records. Loop and
FLAIR are shifted by a random offset of up to 365 days per participant, IOBP2 is shifted by
inference, REPLACE-BG is rebased so that 180 of 196 participants begin on 2015-01-01, and the
remainder are unknown. No calendar or seasonal quantity is admissible anywhere in this protocol.
Because the Loop offset is a whole number of days it leaves clock time intact, and the announced
meals confirm it: they peak at 07:00, 11:00 to 12:00 and 18:00, and fall to a minimum at 02:00 to
03:00. Time of day is therefore an admissible feature and day of week is not, since an offset that
is not a multiple of seven destroys it. Study day is comparable across participants in REPLACE-BG
alone and is not used.

These are Loop, and in REPLACE-BG sensor-augmented pump, participants. They are not Boost users
and they are not on the same insulins or the same era of hardware. What transfers from this corpus
is a statement about how much information a glucose trace carries about the food that caused it.
Nothing about how the Boost controller responds transfers, and no policy conclusion is available
from it at all.

## 3. Hypotheses

H1, replication. With participants held out, meal size is not separable from the glucose trace at
horizons of 10 to 60 minutes after onset, reproducing the prior null on three orders of magnitude
more data.

H2, between-person inversion. The per-participant association between announced carbohydrate and
early glucose rise is heterogeneous in sign, so that a distribution of per-participant slopes
straddles zero. This is the mechanism the prior report asserted. If it is false, the prior
sub-chance point estimate was small-sample noise.

H3, bolus artefact. Size readability differs by whether and when the meal was bolused, being
lowest where a bolus preceded or accompanied the meal and highest where none was given. If H3
holds, the prior null is a property of announced meals and does not transfer to the unannounced
setting Boost operates in.

H4, label-free calibration. Expressing the trajectory in units of the participant's own scale,
using only quantities available without any announcement, recovers separability that the raw
trajectory does not carry.

H5, calibrated ceiling. Allowing a participant's own earlier announced meals as calibration raises
separability further. This is not deployable in Boost as it stands and is included to price what a
calibration period would be worth if one were ever asked for.

## 4. What counts as a meal

The prior definition is adopted unchanged so that H1 is a replication rather than a new study.
Carbohydrate entries below 8 g are dropped, which is the prior study's threshold. Carbohydrate entered to treat a low is not a meal and
is excluded, by the prior rule: glucose at or below the rescue threshold at the entry, or falling
over the preceding three samples. Entries within 90 minutes of an accepted meal are folded into it
rather than counted again. Onset is the last non-rising sample at or before the entry and within
30 minutes of it, which is what a detector could find without the announcement, and every feature
is computed forward from that onset rather than from the entry.

Size classes follow the prior study: small is 20 g or below, large is 40 g or above, and the
middle is dropped so the classes genuinely differ. Size as a quantity is carried alongside in
grams.

A meal is admitted only if the glucose series covers 20 minutes before the onset and the full
horizon after it, with at least three samples before and two after.

## 5. Arms

The learner is held fixed across arms and the feature space is what varies, so that a null cannot
be blamed on the model and a positive result can be attributed to something.

| arm | information available | deployable in Boost today |
|---|---|---|
| 1 | the glucose trajectory alone, prior feature set unchanged | yes |
| 2 | arm 1 plus participant scale from insulin and demographics only, no carbohydrate labels | yes |
| 3 | arm 2 plus the participant's own earlier announced meals | only after a calibration period |
| 4 | within-participant fit, on participants with sufficient meals of their own | only after a calibration period |

Arm 1 carries the thirteen shape features of the prior study, computed over the same six horizons:
the baseline, the rise and its rate, the peak so far, the area over baseline, the largest, last and
mean increments, the acceleration and the curvature, the pre-onset slope and whether the trace is
still rising. Time of day is added, which the prior study did not carry and which is admissible.

Arm 2 adds total daily dose computed from the participant's basal and bolus record, age, and the
participant's own distribution of rise amplitudes over all detected rises. None of these requires
a carbohydrate announcement, which is what makes the arm deployable. It is the direct test of H4
and, with arm 1, of whether the failure is one of scale rather than of signal.

Arm 3 adds the participant's own median announced size, their size by time of day, and the running
estimate of their glucose rise per gram, each computed from their meals strictly earlier in their
own record than the meal being scored.

## 6. Model

A histogram gradient boosting model is used throughout, which is what the prior study used and what
LightGBM implements. The learner is not the binding constraint here and swapping one histogram
booster for another buys nothing on its own. LightGBM is chosen for the practical reasons that it
handles a million rows by fifty columns in seconds, takes categorical features natively, and
accepts monotone constraints should a later arm want them. Hyperparameters are fixed in advance at
the prior study's values, 200 iterations, depth 4, learning rate 0.06, and are not tuned, because
tuning inside the fold structure is how a previous piece of work in this programme turned a leakage
artefact into a fourteen point gain.

H2 is not a task for a booster. It is estimated as a mixed model with a random slope on
carbohydrate per participant, and the reported quantity is the distribution of those slopes across
the 919 Loop participants, together with the proportion whose interval excludes zero and the
proportion of the opposite sign to the population mean. That distribution is what adjudicates the
prior report's stated mechanism, and it can be read directly rather than inferred from a fall in
out-of-sample accuracy.

## 7. Baselines

The headline comparison is not against chance. A controller already knows the clock and, for an
established user, something about the person, so the only quantity worth measuring is what the
trajectory adds on top of that. Four baselines are pre-specified: the population median size; the
median size at that time of day; the participant's own median size, which is available to arm 3
and above; and the raw rise at the horizon taken alone, which the prior study reported at 0.587 to
0.654 and against which its multivariate fit lost.

A model that does not beat the raw rise taken alone has not earned its features.

## 8. Validation and uncertainty

Participants are the fold unit throughout, in five-fold `GroupKFold` on `subject_id`, so that no
participant appears in both the fitting and the scoring of any estimate. Confidence intervals come
from a cluster bootstrap resampling participants, 2,000 draws, never resampling meals, since meals
within a person are dependent and the person is the unit that carries the uncertainty. Every
reported effect size carries a 95 per cent interval and an explicit verdict on whether it is
distinguishable from its baseline, and any interval overlapping the baseline is reported as
unproven.

External validation is by study. Models are fitted on Loop and scored on REPLACE-BG and the
reverse, which crosses therapy, era and de-identification scheme at once and is the strongest
generalisation test the corpus supports.

Arm 4 fits on a participant's earlier meals and scores their later ones, temporally split within
each participant, restricted to those with at least 100 meals so that the split leaves both sides
usable.

## 9. Endpoints and what each result would mean

The primary endpoint is the area under the curve for large against small, participants held out,
at 10, 15, 20, 30, 45 and 60 minutes after onset, for each arm and each bolus stratum. Secondary
endpoints are the mean absolute error in grams against the baseline ladder, and the operational
quantity, being the share of large meals identified by 15 and by 20 minutes at a false positive
rate fixed at 10 per cent, which is the form a dosing rule would actually take.

Decisions are fixed now.

| result | what follows |
|---|---|
| arm 1 fails to beat the raw rise at every horizon, in every bolus stratum | the prior null is confirmed at scale, is promoted from six participants to a thousand, and dose sizing to the meal is closed for good |
| arm 1 fails but the no-bolus stratum separates | the prior null is an artefact of announced and bolused meals and does not transfer to Boost; the question re-opens on the unannounced setting |
| the per-participant slopes straddle zero | the inversion mechanism is confirmed and per-person calibration becomes the only route to size |
| the slopes are consistent in sign | the prior sub-chance estimate was noise and the report's mechanism should be withdrawn |
| arm 2 beats arm 1 by at least 0.05 in AUC at a horizon of 20 minutes or less, with the interval excluding zero | a label-free per-person scaling is buildable in Boost and a specification follows |
| arm 3 or 4 clears that bar where arm 2 does not | size is readable only with announcements, and the finding is the price of a calibration period rather than a feature |

The margin of 0.05 and the horizon of 20 minutes are set before any fitting. A gain smaller than
that, or arriving later than that, does not change what is built, because insulin given after the
excursion has declared itself is insulin given too late to size it.

## 10. Leakage controls

No per-meal insulin quantity enters any feature in any arm. The bolus for an announced meal is
computed from the announced carbohydrate through the participant's ratio, so a model given it
would recover the label by arithmetic rather than by physiology. Bolus timing is used to stratify
and never to predict. Participant-level total daily dose is admitted because it is a property of
the person rather than of the meal.

Every feature in arm 3 and arm 4 that draws on a participant's own history is computed from meals
strictly earlier in that participant's own record, which is both leak-free and the only form in
which such a feature could exist at run time.

Hyperparameters are fixed rather than searched. The size classes, the exclusions, the horizons and
the decision margins in section 9 are fixed by this document.

## 11. Order of work

Extraction first, since it is the expensive step and every arm reads the same table. One row per
meal with the glucose grid from 30 minutes before onset to 60 minutes after, the bolus stratum,
the participant scalars and the label, written to parquet, chunked by participant. Then arm 1 with
the bolus stratification, which settles H1 and H3 together and is the point at which the study is
already publishable whichever way it falls. Then the mixed model for H2, which is cheap and
interpretable and does not depend on the arm 1 result. Then arms 2 to 4 in order, each conditional
on the last having something left to explain. Then the external validation across studies.

Detection is carried as a secondary analysis because the extraction is shared and it costs almost
nothing. The prior study put meal against non-meal separability at 0.805 at ten minutes and 0.975
at thirty, on six participants and with a negative class of unannounced rises that included dawn
phenomenon and rebounds. The same measurement on a thousand participants bounds what a detector
can do far more tightly, and it is the figure the accel meal shadow is judged against.

## 12. What this cannot settle

The corpus answers a question about information and not about policy. Whether a dose sized to an
estimated meal would improve any outcome is not addressed here, cannot be addressed by any
observational corpus, and would require the pre-registered within-participant trial the two-test
bar demands. Announced carbohydrate is an estimate made by the person eating and carries its own
error, which places a ceiling on measured accuracy that this design cannot separate from the
ceiling imposed by physiology. And the participants are not Boost users, so a positive result
would establish that the information exists in a glucose trace and would still require confirmation
on unannounced meals before anything was built on it.
