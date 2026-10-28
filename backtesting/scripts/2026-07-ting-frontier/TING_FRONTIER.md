# TING frontier — the target is variance, not aggression

*2026-07-17. Strategic anchor for a TING-maximising programme. Script: `ting_frontier.py`
(cohort `oref.boost_decisions`, 90-day window, CGM deduped to 5-min bins). Anonymised tags.*

## The question

"Target 100% TING." Literal 100% (63–140 mg/dL every minute) is unreachable with subcutaneous
insulin + interstitial CGM, and *chasing* it naively (dose the mild highs down) feeds the low-tail
— the failure mode the whole safety edifice exists to prevent. So the real target is each person's
**TING frontier: the maximum TING achievable without spending any extra time below the floor.**

## The finding

TING is governed by **glucose variability (CV)**, not by how hard you dose.

| tag | TING% | CV% | TBR<70% | 140–180% (addressable) |
|---|---|---|---|---|
| E | 86.1 | **18.8** | 0.7 | 12.7 |
| D | 88.5 | 26.0 | **9.9** ← bought with lows | 5.1 |
| H | 77.3 | 23.3 | 1.1 | 18.4 |
| C | 72.8 | 29.7 | 4.3 | 18.2 |
| G | 69.8 | 33.9 | 4.2 | 18.3 |
| **tim** | **68.0** | **36.4** | 5.4 | 17.9 |
| A | 63.9 | 30.6 | 1.1 | 22.1 |
| B | 62.4 | 37.5 | 4.2 | 18.7 |
| F | 59.8 | 33.1 | 3.2 | 20.7 |

Cross-user (n=9):
- **TING vs CV: r = −0.81, r² = 0.65, p = 0.008** — variability explains ~⅔ of who has good TING.
- **TING vs the 140–180 band: r = −0.86, r² = 0.74, p = 0.003** — that band is the addressable loss.
- Slope: **each +1% CV costs ~1.3pp TING.** Fit `TING ≈ 112 − 1.3·CV`; the low-CV frontier
  (~19% CV, user E) projects TING ~87%.

The low-TING users are the high-CV users; the high-TING users are the low-CV users. The mild-high
**140–180 band** — glucose that is *in range* by TIR but *out* of the tight band — is where TING
leaks, and it is ~18–22% for everyone stuck in the 60s.

**Caution — TING must be pinned to the floor.** User D reaches 88% TING but on ~10% time-below-70:
TING at any cost is not the target. The frontier is TING *at a held low-tail*.

## What this means for the programme

The lever is **not** more insulin — the residency lever-map and the thrice-rejected
"dose-more-into-highs" class establish that adding insulin into the high tail (which is high-IOB)
feeds lows at base rate. The lever is **earlier, better-predicted, lower-variance** dosing that
**compresses the 140–180 band and drops CV**, with the low-tail held by the existing floors:

1. **Smoother sensing** — the shipped UKF already reduces reactive over/under-shoot; quantify its CV
   contribution and push it.
2. **Earlier response** — front-load ahead of *predictable* excursions (the confirm-timing shave,
   the validated exercise/GLP-1 anticipation), moving insulin rather than adding it (harm-neutral).
3. **Smoother sizing** — distributional / anti-overshoot micro-dosing (the V7 substrate was GO) so
   corrections don't ring the glucose up-and-down.
4. **A shadow TING objective** — score each cycle against a `duration-outside-63–140 + CV` loss,
   floor-constrained, logged vs V6, validated on the DB before anything doses. This is the concrete
   objective for a forecaster-planner "TING engine" — the disciplined landing of the KAIROS/AION
   design: variance-crusher, shadow-first, floors as hard constraints.

**Target:** move each user toward the low-CV frontier (CV → ~20–23%), holding the low-tail — worth
roughly **+8–15pp TING** for the high-CV users (tim 68→~82, F 60→~75), reached at the speed of
shadow-validated bricks, not a thunderclap.
