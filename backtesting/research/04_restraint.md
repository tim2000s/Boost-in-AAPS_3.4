# The composed brake, the caps and the floor beneath them

What a strictly defined suppression set contains, how much of it was safely recoverable, and why a
product of reasonable multipliers is not reasonable.

## Abstract

Attribution makes a composed brake the largest proximate mechanism behind time above range, at 34 per
cent, with those episodes already visible to a forecaster forty five minutes ahead, which invites the
reading that the brake is too aggressive. That reading contains an inference the attribution cannot
support, since the brake suppressing during a rise is not the same as the brake being wrong. Narrowing
to cycles where the underlying algorithm genuinely wanted insulin, requiring an insulin requirement
above 0.05 U, a composed budget below 0.10 and glucose above 170 mg/dL, the set contains 135 cycles
across eight participants over roughly six weeks, some 675 minutes, which is far smaller than 34 per
cent of high-time implies. Of those, 13 per cent were followed by a low within three hours, 76 per cent
occurred at high insulin on board with no low following, 7 per cent resolved on their own at low
insulin, and 3 per cent, about twenty minutes in six weeks, stayed high at low insulin without a low
following and are the only category the floor could safely recover, those carrying a 12 per cent
forward-low rate themselves. Separately, forensic reconstruction of seventeen consecutive cycles at a
glucose around 270 mg/dL shows the multiplier chain reaching 0.4 by 0.40 by 0.85 by 0.30, which is 4.1
per cent of budget and rounds to no delivery for thirty minutes, with no individual term unreasonable.
One participant contributes 51 per cent of the 135 cycles.

## Introduction

The attribution study ranks a composed brake first among mechanisms behind time above range and shows
its episodes to be foreseeable, which together suggest the largest available improvement is to loosen
it. The suggestion rests on an inference the attribution cannot support.

The competing hypothesis is that most suppression is correct restraint at high insulin on board, in
which case the apparent opportunity is mostly insulin that should not be given, and loosening the brake
converts time above range into time below it. Distinguishing the two requires asking what happened
after each suppressed cycle rather than how often suppression occurred.

A separate question concerns the mechanism rather than the policy. The brake is a product of several
multipliers, and a product of fractions falls faster than any of its terms, so it may reach values that
no single term implies and that nobody chose.

## Methods

The mechanism question was answered by reconstructing the multiplier chain cycle by cycle from
telemetry during a sustained high, over seventeen consecutive cycles, recorded under
`backtesting/scripts/2026-07-v6-dosing-forensics/`.

The policy question was answered by outcome rather than by mechanism, recorded under
`backtesting/scripts/2026-07-residency/BRAKE_AUDIT_REPORT.md`, using telemetry across eight
participants over roughly six weeks.

Inclusion required the underlying insulin requirement above 0.05 U, the composed budget below 0.10, and
glucose above 170 mg/dL. That is deliberately strict: it excludes highs where the algorithm was content
because insulin on board already covered them, and isolates the set where a wanted delivery was
actually blocked.

Each included cycle was classified by what followed and in what insulin context, on the reasoning that
correct and incorrect restraint have different signatures. Correct restraint is followed by no low and
occurs at high insulin on board; incorrect restraint leaves glucose high with little insulin present
and no low following.

The suppression signal is taken from the composed budget rather than from the state multiplier, since
the latter never approaches zero. The floor's own contribution could not be priced, because the field
recording it is absent from historical rows.

## Results

At a glucose around 270 mg/dL the chain multiplied to 0.4 by 0.40 by 0.85 by 0.30, which is 4.1 per
cent of budget and rounds to no delivery at all for thirty minutes. No individual term is unreasonable
and the product is.

The strict set contains 135 cycles, some 675 minutes over six weeks. Of those, 13 per cent were
followed by a low within three hours. Another 76 per cent occurred at high insulin on board with no low
following. Seven per cent resolved on their own at low insulin on board. Three per cent, about twenty
minutes in six weeks, stayed high at low insulin on board without a low following, and those carried a
12 per cent forward-low rate.

One participant contributes 51 per cent of the 135 cycles, and four others contribute one to three
cycles each.

## Discussion

The direction holds and the magnitude does not. The brake should not be loosened, since only 3 per cent
of a strictly defined suppression set was safely recoverable and 13 per cent actively preceded a low
that did not occur. But the figure of 90 per cent correct, arrived at by adding the outcome-proven and
the assumed categories, combines two things that should be reported separately. Thirteen per cent is
outcome-proven, in the sense that a low followed and did not happen. Seventy six per cent is correct by
assumption, defined as high insulin on board with no subsequent low and grounded in the separate
finding that adding insulin in that context prices about 19 per cent into lows, but not demonstrated
cycle by cycle. The defensible statement is thirteen proven plus seventy six presumed, and the
composite should not be quoted as though it were measured.

The sample is weaker than the cohort framing implies. One participant contributes half the cycles and
four others contribute one to three each, which is noise. The result is self-dominated and pooled and
cannot be resolved per participant for most of the cohort. The category credited with preventing a low
also credits the brake for any low within three hours, a window wide enough to catch lows caused by
activity or by rescue treatment and unrelated to the suppressed delivery.

Taken with the attribution study, the practical conclusion is that the composed floor is a bounded fix
rather than a lever. It addresses a real failure, demonstrated in the forensic reconstruction, in which
a product of individually reasonable multipliers reaches zero during a rise. Its upside is small and
quantified at about 3 per cent of brake suppression, and characterising it that way rather than as the
largest available opportunity is what the raw attribution number would not have supported.

The wider point is the one the register lists first among its recurring lessons. Several large-looking
effects in this programme are small once a matched or strictly defined comparison is constructed, and
the brake is the clearest case: a third of high-time becomes 675 minutes once the question is posed as
whether a wanted delivery had been blocked in error.
