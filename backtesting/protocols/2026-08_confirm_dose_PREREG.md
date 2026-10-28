# Reducing the confirm dose: a pre-registered within-participant randomised trial

Registered 2026-08-12. The arms, endpoints, stopping rules and analysis set out below were fixed
before any randomised data were collected.

## 1. Why this and not something else

Entering the CONFIRMED state is followed by glucose below 70 mg/dL within three hours on 22.8 per
cent of occasions and below 54 mg/dL on 7.6 per cent. Those figures on their own say nothing, since
glucose falls for reasons unconnected with a confirm. Matched against control windows from the same
participant, beginning from a starting glucose within 15 mg/dL, an insulin on board within 0.5 U and
the same hour of day, with no confirm in the window or the hour before it, the control rates are 14.0
and 1.9 per cent. The differences are 8.8 points [3.9, 14.0] below 70 and 5.7 points [3.0, 8.5] below
54, from 1074 matched confirms across eleven participants, with intervals from a bootstrap that
resamples participants. Nine of the eleven move in the same direction and no single participant
carries the result.

Confirming therefore roughly doubles the chance of going below 70 and quadruples the chance of going
below 54, from the same starting state in the same person. The severe figure is the one that
motivates a trial: 1.9 to 7.6 per cent is a fourfold increase in the exposure the consensus floor
sets at 1 per cent.

The alternative to a trial would be to predict which confirms will crash and restrain only those.
That has been tested and does not work. Out of sample, with participants held out as folds, the crash
is indistinguishable from chance at the moment of confirm, and three further attempts this month on
acceleration decay, on delta relative to its predecessor, and on the over-prediction of eventual
glucose all returned intervals spanning zero. Since the crash cannot be anticipated but confirming
reliably produces excess lows, the remaining levers are to give less insulin at confirm or to withdraw
it afterwards. This trial tests the first.

The observational finding cannot settle the question it raises. Confirms fire on rises that would
attract more insulin whatever the engine did, and matching on starting glucose and insulin does not
match on what the participant ate. Only randomisation at the moment of confirm separates the dose
from the circumstances that provoked it, which is the whole reason for running this rather than
reporting the association.

## 2. Intervention

At each entry into the CONFIRMED state the engine draws an assignment and applies it to the action
multiplier that scales the confirm shot. The control assignment leaves the multiplier as the engine
computes it today. The reduced assignment multiplies it by 0.7.

Everything else is untouched. The confirm gate, the state machine, the caps, the brakes and the
composed floor all behave exactly as they do now, and the reduced assignment cannot raise a dose
above what the control assignment would have given. The trial therefore only ever removes insulin,
which makes hyperglycaemia rather than hypoglycaemia the risk it introduces, and that asymmetry is
why it is acceptable to run on live therapy at all.

The multiplier of 0.7 is a judgement and not a derivation. Nothing in the observational record fixes
the right size, because the counterfactual glucose trajectory for a smaller dose does not exist. It
is chosen so that the reduction is large enough to move the primary endpoint if the relationship
between dose and nadir is anything like proportional, and small enough that the confirm continues to
do its job. At the median confirm dose of 1.41 U a thirty per cent reduction withholds 0.42 U, which
at a typical variable sensitivity near 58 mg/dL per unit is worth about 24 mg/dL of glucose, against
a detectable shift of 8 mg/dL at the sample size below.

## 3. Randomisation

The unit is the individual confirm, assigned one to one, from a generator seeded per participant so
that the sequence is reproducible from the record and cannot be influenced by the state of the loop.
Assignment happens at the moment of entry into CONFIRMED and is written to the reason string and
uploaded, so every event in the analysis carries its arm, and an event whose arm cannot be read is
excluded rather than guessed.

Randomising each confirm rather than each day is deliberate. Days differ in what is eaten and in how
much activity they contain, and a day-level assignment would put that variation between the arms
instead of within them. The cost is that consecutive confirms are not independent, which section 6
addresses in the analysis rather than by discarding events.

There is no blinding. The participant can see the dose, and pretending otherwise would be dishonest.
The analysis is run with arm labels replaced by neutral tokens until the primary result is computed.

## 4. Endpoints

The primary endpoint is the lowest glucose in the window beginning at the confirm and ending at the
earlier of three hours later or the next confirm. Truncating at the next confirm attributes the
outcome to the dose that plausibly caused it, and the alternative of a fixed three hours would credit
one confirm with insulin given by another.

The primary safety endpoint is the proportion of windows containing a glucose below 54 mg/dL. It is
named as an endpoint rather than left to the stopping rules because a fourfold excess in severe
exposure is the reason the trial exists, and an intervention that improves the nadir on average while
leaving severe events untouched has not answered the question.

The cost of the intervention is measured as deliberately as its benefit. The highest glucose in the
same window and the time spent above 180 mg/dL in the six hours following the confirm are reported
alongside the primary endpoint in every analysis. Withholding insulin will raise glucose, and a
protocol that reports only the hypoglycaemia it prevents would be advocacy rather than measurement.

Two further measures are recorded for interpretation and not for inference: the insulin actually
delivered in each arm, which confirms the intervention did what it was told, and the state the engine
occupied at the end of the window, since a reduced dose may leave the participant in a plateau the
current dose would have broken.

## 5. Participants, duration and staging

Participants are those already running the V5/V6 engine who generate at least twenty confirms a week,
who are told what the trial does and choose to take part. Observed rates over the seven weeks to
2026-08-12 range from 23 to 44 confirms a week per participant.

The trial runs in two stages. It begins with the developer alone for a fortnight, which yields around
sixty confirms and cannot settle the primary endpoint but will surface an implementation fault or an
unacceptable rise in glucose before anyone else is exposed. The stage one review reports the delivered
insulin by arm, the peak glucose, the time above 180 mg/dL and the severe count, and the trial
proceeds only if the delivered insulin differs between arms as intended and the glucose cost is
within the bound in section 7.

Stage two invites the remaining eligible participants and continues until 800 confirms have
accumulated across all participants or twelve weeks have elapsed, whichever comes first. At the
pooled rate that is about five weeks. The cap on time exists so the trial cannot run indefinitely
waiting for an endpoint that is not moving.

## 6. Analysis

The estimate is the within-participant difference in the primary endpoint between arms, pooled across
participants with each contributing its own difference, so that a participant with many confirms
cannot decide the answer. Intervals come from a bootstrap resampling participants rather than
confirms, for the same reason.

Consecutive confirms are not independent, since insulin from one persists into the window of the next.
The primary analysis addresses this through the truncation in section 4 and by resampling whole
participants. A pre-specified sensitivity analysis repeats the estimate on isolated confirms only,
meaning those with no other confirm in the preceding three hours, and the two are reported together.
If they disagree the isolated estimate is preferred and the disagreement is reported as the finding.

With a within-participant standard deviation of 29 mg/dL in the nadir, measured across nine
participants and 1236 confirms, 800 confirms split evenly detect a shift of 5.8 mg/dL at eighty per
cent power, and 400 detect 8.2. The severe endpoint is less well served: moving 7.6 per cent to 4 per
cent requires around 1300 confirms, which the twelve week cap may not reach, and the protocol says so
in advance rather than presenting an underpowered null as evidence of safety.

No adjustment is made for multiple endpoints, because there is one primary endpoint and the rest are
named as safety or cost measures rather than as tests. Subgroup analyses are not planned. Any analysis
not described here is exploratory and will be labelled as such.

## 7. Stopping rules and bounds

The standing time below range limits continue to apply to every participant as they would on any other
day, and they can only tighten. Fourteen day time below 70 mg/dL above 4 per cent, or time below 54
above 1 per cent, removes that participant from the trial and returns them to the unmodified engine.
These are absolutes and are not relaxed because a participant is in the reduced arm or because the
trial is going well.

The intervention withholds insulin, so its own risk is hyperglycaemia, and it is bounded rather than
merely watched. A participant whose fourteen day time above 180 mg/dL rises by more than five
percentage points against their own preceding fourteen days, or whose mean glucose rises by more than
15 mg/dL, is removed from the trial. The comparison is against the participant's own recent history
rather than against the control arm, so that a drift affecting both arms cannot hide inside the
randomisation.

Either stage stops immediately, for everyone, on a severe hypoglycaemic event requiring assistance, or
on evidence that the assignment is not being applied as written.

## 8. What this can and cannot show

It can show whether giving thirty per cent less insulin at confirm reduces the depth of the subsequent
fall, and what that costs in glucose. Because the assignment is randomised at the moment of confirm,
that comparison is causal within these participants, which is the one thing the observational record
cannot provide.

It cannot show the right multiplier. A single reduction tested against no reduction locates neither
the optimum nor the shape of the response, and a result at 0.7 says nothing about 0.85 except by
assumption. It cannot generalise beyond the participants who took part, who are few, self selected and
running their own settings. And it says nothing about whether the confirm should have fired, which is a
separate question the register records as unanswerable at the moment of confirm.

If the reduction improves the nadir at an acceptable glucose cost, the sequel is a dose finding trial
across two or three multipliers rather than an immediate change to the shipped default. If it does not,
the finding that confirming doubles the risk of a low still stands, and the lever moves to withdrawing
insulin after the fact, which the register already identifies as the only defence the evidence
supports.
