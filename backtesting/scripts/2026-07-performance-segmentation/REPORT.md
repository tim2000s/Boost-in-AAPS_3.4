# Performance review, re-cut by post-meal exercise (2026-07-27)

The headline cohort numbers (TIR 87, TING 72) average over three regimes the loop handles very
differently. Separating them — and removing the exercise-affected post-meal windows the
mechanism study showed are not the loop's dosing fault — isolates the loop's actual meal-handling
quality. Eight users with a step feed, 30 days.

## Cohort, segmented

| segment | % of time | mean (mmol) | TIR | TING | TBR<70 | TBR<54 | TAR>180 |
|---|---|---|---|---|---|---|---|
| **All time** | 100 | 7.1 | 86.7 | 70.5 | 2.9 | 0.5 | 10.4 |
| **All minus exercise-postmeal** | 76.9 | 6.9 | **89.2** | **75.1** | 2.6 | 0.4 | 8.2 |
| Background (non-post-meal) | 59.0 | 6.6 | **93.3** | 81.5 | 2.6 | 0.4 | 4.1 |
| Post-meal, **no exercise** | 17.9 | 8.1 | 75.8 | 53.8 | **2.5** | 0.5 | **21.7** |
| Post-meal, **with exercise** | 23.1 | 7.7 | 78.2 | 55.2 | **4.0** | 0.7 | 17.8 |

## What it says

1. **Background control is essentially solved.** Away from meals — 59% of the time, including
   overnight — the loop holds **93% TIR, 82% TING** with lows no worse than average. This is the
   fully-closed loop at its best, and it is very good.

2. **The real cost of fully-closed is the post-meal high, and it is a dosing/insulin-speed cost,
   not an exercise one.** In the clean post-meal window (no exercise) TAR>180 is **21.7%** and
   TING falls to **53.8** — one in five post-meal minutes above range. Crucially, **lows are not
   elevated there (2.5%, same as background)**: the loop is not over-dosing meals, it is too slow
   to cover them. The high is the price of no announcement plus slow insulin, isolated cleanly.

3. **Exercise redistributes post-meal risk — trims the high, adds the low.** The with-exercise
   post-meal window has a lower TAR>180 (17.8 vs 21.7) but a higher TBR<70 (**4.0 vs 2.5**) and
   TBR<54 (0.7 vs 0.5). Exercise's glucose disposal blunts the peak and, when the carbohydrate
   counterweight is thin, tips the floor — exactly the mechanism the companion study established.

4. **Removing exercise-affected post-meal time lifts the review by +2.5 pp TIR and +4.5 pp TING**
   (86.7 → 89.2; 70.5 → 75.1). So the exercise confound accounts for a meaningful but minority
   share of the imperfection; the larger remaining sink is the post-meal high.

## The pattern is bimodal by physiology (per-user)

|  | background | post-meal no-ex | post-meal with-ex |
|---|---|---|---|
| **Large-meal / high-CR users** (TIR/TING/TBR/TAR) | 87–92 / 70–83 / low | 62–71 / 35–53 / **TAR 24–37** / TBR low | high mostly persists, **TBR stays low** |
| **Tight / sensitive users** | 94–98 / 86–93 | 88–100 / 61–92 / TAR ≤11 | **TBR jumps** (one at 9%, one at 14%) |

Exercise after a meal **helps the high-runners** (knocks down a peak they have glucose to spare)
and **hurts the tight-runners** (tips them low, because they have no post-meal glucose buffer).
The post-meal-exercise low burden is concentrated precisely in the users who otherwise have the
best control — the carb-counterweight mechanism at user resolution.

## Takeaways for where effort goes

- Do not chase background control — it is at ceiling.
- The post-meal high is the honest headline deficit of fully-closed dosing, and it is an
  insulin-speed / no-announcement problem (lows are flat), not something a smaller or larger dose
  fixes.
- The post-meal-exercise low is a distinct, physiology-gated problem that lands on the
  well-controlled, and its fix is anticipatory withdrawal or carbohydrate — not meal-dose tuning
  (see the mechanism study).

*Reproduce: `segmented_performance.py` (DB refreshed to t=now). One no-step-feed user excluded
from the split; its overall TIR 87 / TING 71 is unremarkable.*
