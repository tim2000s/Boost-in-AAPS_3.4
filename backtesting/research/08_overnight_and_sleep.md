# Overnight performance, the night gate, and sleep detection

The overnight and daytime performance of an amplifying dosing algorithm against its predecessor, and
whether a learned bedtime is worth learning.

## Abstract

Decomposing the aggregate advantage of the Boost generation over the oref-derived behaviour it
replaced by time of day shows it is not distributed. The advantage is overnight, at approximately
13.3 percentage points, and reverses between roughly nine in the morning and one in the afternoon,
where the predecessor leads by four to seven points. The algorithm is therefore better at night and
worse after breakfast, which localises the daytime problem to meal sizing and timing rather than to
aggression in general. The gate suppressing amplification during sleep removes about 47 per cent of
the amplifications the algorithm would otherwise apply over its predecessor, all of them nocturnal
and all on cycles with no meal entered. A learned bedtime prior does not beat a fixed clock: sleep
onset has a standard deviation of about 92 minutes across the cohort and the learned quantity
converges to something indistinguishable from a constant. The overnight advantage is associational
and the figure should be read against a separate cohort comparison in which an unadjusted thirteen
point advantage falls to 1.2 points after adjustment for selection and basal differences.

## Introduction

An algorithm that amplifies dosing relative to a predecessor can earn its advantage anywhere in the
day, and where it earns it determines what to do next. A uniform advantage would suggest the
amplification is simply correct. An advantage concentrated in one period, with a deficit in another,
localises both the mechanism and the remaining problem.

The gate that suppresses amplification during sleep raises a second question. If the gate removes
most of what distinguishes the algorithm from its predecessor overnight, then the overnight advantage
cannot be attributed to amplification, and the gate is either doing useful safety work or reducing
the algorithm to its predecessor at the very hours it appears to lead.

Sleep detection sits underneath the gate. It can be learned from a participant's own history or
detected from physiological and movement signals, and the choice matters only if the learned quantity
carries information a clock does not.

## Methods

The advantage was decomposed by hour of day across the migration cohort, comparing each participant
against their own earlier generation where possible.

The gate was assessed by counting the amplifications it suppresses relative to the predecessor
behaviour and characterising when they occur and whether a meal had been entered.

Two candidate sleep detectors were compared: a learned bedtime prior fitted per participant, and a
rule-based detector driven by heart rate and movement. The learned prior was scored against a fixed
clock, since a prior that cannot beat a constant is a constant.

The resting heart rate baseline uses a robust order statistic and the onset and wake times a circular
mean, both chosen because the underlying quantities are heavy-tailed or periodic rather than by
search over estimators.

## Results

The advantage is overnight and anti-phase with the predecessor. The algorithm runs approximately 13.3
percentage points ahead overnight, and the predecessor leads by four to seven points between roughly
nine in the morning and one in the afternoon.

The night gate suppresses about 47 per cent of the algorithm's amplifications over its predecessor.
All of the suppressed amplifications are nocturnal and all occur on cycles with no meal entered.

Learned bedtime does not beat a fixed clock. Sleep onset has a standard deviation of about 92 minutes
across the cohort, and the learned prior converges to a quantity indistinguishable from a fixed time.
It separates from a clock for one unusually regular sleeper and for nobody else.

The failure mode motivating the architecture is recorded from two incidents in May 2026, in which the
previous generation fired a cascade of microboluses on the rebound out of a hard overnight streak,
reaching nadirs of 51 and 48 mg/dL.

## Discussion

The regime split is the most useful part of the result, because it converts a single aggregate number
into two separate problems. The overnight period is close to solved and the post-breakfast period is
not, which is consistent with the forecasting work showing overnight to be the regime where
prediction error is smallest and meal onset the regime where it is largest. Effort belongs after
breakfast.

The overnight advantage is the strongest aggregate claim in the programme and the least identified.
Participants who chose this algorithm may differ overnight for reasons unrelated to it, and the basal
profiles they run differ as well. A pre-registered within-participant comparison is the test that
would settle it and has not been run. The magnitude should be read alongside the cohort analysis in
which a thirteen point unadjusted advantage falls to 1.2 points after adjustment, with a permutation
p of about 0.27. The two are not the same analysis, but they bound how much of an unadjusted
between-generation difference is likely to survive adjustment.

The sleep detection result is a small negative with a transferable shape. A learned parameter that
converges to a constant is not learning; it is an expensive way of writing down a constant, and the
appropriate response is to write down the constant. That reasoning recurs in the work on
per-participant configuration, where several online estimators converge to what a deterministic
derivation already produces.

The gate's 47 per cent is worth stating as a proportion of amplification rather than of dosing. It
does not switch the algorithm off overnight; it removes the additional aggression on cycles where no
meal was entered, which is the population that produced the two incidents above.
