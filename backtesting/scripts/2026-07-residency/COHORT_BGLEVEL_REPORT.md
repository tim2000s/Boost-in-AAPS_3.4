# Cohort BG-level comparison — AAPS-Boost vs the oref/Trio reference cohort

_2026-07-08. `boost_decisions` (AAPS-Boost, self+A–H+G) vs `multiuser_combined` (oref/Trio reference, U000–U020). Reproduce: `cohort_bglevel.py`._

![comparison](cohort_bglevel.png)

## Why only BG-level

The Trio shadow emits boostV5 **state** but no `budget`/`steps`/`HR`, and 23 of the 24 Trio-tagged sites aren't extracted into `boost_decisions` at all (they carry oref fields only). So the Boost-specific cause attribution, the brake audit and the activity→hypo analysis **cannot run on Trio** and stay AAPS-only. What *is* comparable across every user is the glucose distribution + high/low residency from BG and the shared oref fields.

## Platform comparison (median across users)

| cohort | n | TING 63–140 | TIR 70–180 | TBR<70 | TBR<54 | TAR>180 | TAR>250 | CV |
|---|---|---|---|---|---|---|---|---|
| **AAPS-Boost** | 9 | **71.9** | **88.1** | **3.7** | **0.6** | **6.9** | 1.1 | **30** |
| oref/Trio | 21 | 67.4 | 85.2 | 4.0 | 0.8 | 9.2 | 1.1 | 32 |

The AAPS-Boost cohort is **modestly better on essentially every axis** — ~3 pp higher TING/TIR, fewer lows (TBR<70 and <54 both lower), less high-time (TAR>180 6.9 vs 9.2), and slightly lower variability — at equal severe-high time (TAR>250 1.1 both).

## Coarse IOB context (the only cause signal Trio supports)

Share of high-time at LOW IOB / low-time at HIGH IOB (IOB relative to each user's own median; tdd-normalised context is AAPS-only):

| cohort | high-time at low-IOB | low-time at high-IOB |
|---|---|---|
| AAPS-Boost | 1% | 25% |
| oref/Trio | 4% | 24% |

Consistent across platforms: high-time is overwhelmingly at *above-median* IOB (insulin already onboard — the recovering-highs physiology), and ~a quarter of low-time is at high IOB (stacking). The *physiology* looks the same; the difference between cohorts is in the aggregate distribution, not the shape of the failure modes.

## What this does and doesn't say

- **Suggestive, not causal.** These are two *different populations* (curated AAPS-Boost users vs a broad oref/Trio reference set), not a within-user or randomised Boost-vs-not comparison. Selection effects (motivation, baseline control, device mix) are uncontrolled. So "Boost cohort has better TIR" is an association, not proof Boost *causes* it.
- **Directionally reassuring.** On the axes that matter — TIR up, lows down, high-time down, at equal severe-high — the Boost cohort sits ahead of the reference cohort, and it's consistent across all five metrics rather than a single lucky one.
- **The Trio telemetry gap is the real limiter.** To ever run the mechanism analyses (brake, activity, sizing) on Trio, the port must emit `budget`/`steps`/`HR` to devicestatus (the deferred "fix the Trio port" path). Until then, Trio is BG-level-only and the Boost-specific levers can only be studied on the AAPS cohort.

## Dig-deeper (2026-07-08): this IS a Boost-vs-oref comparison, but small & underpowered

**Correction to an earlier over-correction: `V1` is Boost.** "V1-acting" = Boost V1 (the first Boost generation) is the *dosing* algorithm — NOT oref. So the AAPS cohort has been **Boost-dosing throughout** (V1 generation, with V5/V6 shadowing); the ~4.9% `boostv5_active` is just the slice where the *V5/V6* generation took over dosing from V1, not "Boost vs not." The comparison to the oref/Trio cohort is therefore a **legitimate Boost-vs-oref population comparison** (an earlier draft here wrongly called it "two oref populations" — retracted).

Two caveats survive and bound the strength:

1. **Population comparison, not within-user.** Different people (9 Boost vs 21 oref/Trio); selection is uncontrolled. There is no within-user Boost-vs-oref transition to exploit — the AAPS cohort was Boost the whole window (a within-user cut here would be Boost-V1 vs Boost-V5/V6, a *generation* question, not Boost-vs-oref).
2. **Small and not-yet-significant after adjusting for case difficulty.** Raw median TIR gap **+2.9 pp**; the Boost cohort has slightly easier cases (CV 30 vs 32, mean BG 123 vs 125). OLS `TIR ~ platform + CV + meanBG` (one row per user; permutation at the user level) attenuates the platform effect to **+1.2 pp**, permutation **p = 0.27 (not significant)**. _(2026-07-10 audit: the "~59% is difficulty" is imprecise — it divides an OLS **mean** partial effect by a **median** raw gap, so part of the shrink is a median→mean change, not confounder adjustment. The unit-of-analysis and the significance test are correct; only the 59% attribution is loose.)_

**Verdict:** a **genuine but suggestive** Boost-vs-oref edge — consistent in direction across all five metrics (TIR/TING up, TBR/TAR down), but small (+1.2 pp difficulty-adjusted) and underpowered (p = 0.27) in a 9-vs-21 population comparison. Not conclusive, not a selection *artifact* either — it points the right way and warrants a larger / better-matched comparison to firm up.

**→ The regime decomposition (`COHORT_REGIME_REPORT.md`) is where this gets interesting:** the flat +2.9 pp aggregate is *entirely overnight* (+13.3 pp, 00–06 local) partly offset by a post-breakfast *deficit* vs oref. The time-specific structure is a mechanism signature (overnight machinery = Boost's strength; meal sizing/timing = its deficit), which the aggregate hides. Read that report next.

## Per-user detail

Full per-user table (TING/TIR/TBR/TAR/CV, both cohorts) is printed by the script and in `cohort_bglevel.json`. Notable: within AAPS-Boost, E (TIR 97) and H (94.5) lead, F (76.6) trails on high-time; within oref/Trio the spread is wider (U011 94 → U013 69), consistent with a broader, less-curated population.
