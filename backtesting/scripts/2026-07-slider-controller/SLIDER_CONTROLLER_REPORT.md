# Evidence-gated SLIDER controller — cohort policy replay

_Data: TimescaleDB `oref.boost_decisions`, V6, cohort ['tim', 'A', 'B', 'C', 'D', 'E', 'F', 'H'], span 2026-05-07 → 2026-07-08. Faithful counterfactual dose (exact slider multipliers); insulin priced vs observed lows/highs. `slider_controller_replay.py`._

## Parameters
```
HC_STEP = 0.25
HC_MAX = 2.0
HC_LOW_WINDOW_H = 3.0
HC_RELAX_CLEAN_DAYS = 3.0
HC_RELAX_STEP = 0.25
AG_WINDOW = 10
AG_STEP = 0.1
AG_MAX = 1.3
AG_COOLDOWN_H = 24.0
AG_HIGH_MGDL = 180.0
AG_RETRO_MARGIN = 15.0
AG_IOB_SAFE_FRAC = 0.05
AG_LOW_ATTRIB_H = 3.0
```

## HYPO-CAUTION track (safe: remove insulin before lows)

Cohort: removed **564.6 U**, of which **107.3 U (19%) preceded a low within 3 h** (good removals), **138.4 U** was on cycles that then went high (undershoot). Per-user table in the script output.

Reading: a high prelow% = the caution is cutting insulin where it mattered; a high wrong_U = it is starving legitimate doses. hypoCaution only bites when mlHypoRisk>0.30, so it is self-targeting — this measures whether that targeting is good.

## AGGRESSION track (expensive: add insulin on sustained highs)

Armed users: raises **12**, reverts **10** (45% of changes were reverts). Adds insulin on CONFIRMED cycles only (the one state the aggression knob scales).

## Static hypoCaution sweep (the decisive result)

Pricing removed insulin at FIXED hypoCaution (independent of the ratchet controller):

| h | removed_U | prelow_U | wrong_U | prelow% | good:wrong |
|---|---|---|---|---|---|
| 1.25 | 147.8 | 27.3 | 37.1 | 18% | **0.74** |
| 1.5 | 295.2 | 54.5 | 74.0 | 18% | **0.74** |
| 1.75 | 442.1 | 81.8 | 110.9 | 18% | **0.74** |
| 2.0 | 587.7 | 108.5 | 147.5 | 18% | **0.74** |

**The ratio is flat 0.74 at every level** — the slider *magnitude* is irrelevant; the *targeting signal* (mlHypoRisk>0.30) is what's mediocre.

⚠️ **Audit notes (2026-07-10):** (1) The flatness is partly *definitional* — raising h only rescales the same fixed set of targeted cycles (mlHypoRisk>0.30), so pre and wrong scale together and their ratio is near-invariant by construction; read it as "magnitude doesn't change the targeted set," not as an independent empirical result. (2) The good:wrong ratio **omits the neutral majority** — at h=2.0, of 587.7 U removed, 108.5 (18%) was pre-low and 147.5 (25%) pre-high, so **~332 U (56%) was outcome-neutral** (BG stayed in range). So "starves ~35% more legit doses than it saves" compares only the two tail buckets; most removal was harmless. (3) The pooled ratio is computed over ALL users incl. the ones a TBR-gate would exclude — it correctly damns the *ungated online loop*, not the per-user static setting.

## Verdict — both NO-GO as online auto-controllers, for different reasons

- **Aggression up-on-highs: NO-GO** (12 raises / 10 reverts = 45% revert) — identical failure to the cap-stepper. Confirms the residency map: highs are **sizing/timing in specific meal cycles**, not global under-aggression, so a global CONFIRMED multiplier mis-targets and reverts.

- **HypoCaution up-on-lows: NO-GO as an online controller** — good:wrong 0.74 flat, and the 'step up on any low' loop ratchets almost everyone to max (2.0), removing insulin indiscriminately. BUT **per-user it is well-targeted for the genuinely hypo-prone** (D 32% pre-low, self 28%) and badly for the well-controlled (A 6%, E 1%). So hypoCaution belongs as a **per-user static setting driven by TBR** (which auto-config already gates on), NOT an online any-low loop that mis-fires on well-controlled users.

## Unifying conclusion (with the cap-stepper)

Across caps AND sliders, in BOTH directions: **online outcome-driven auto-tuning of dosing knobs does not beat auto-config + static per-user settings.** The controller keeps re-deriving — badly, with churn/reverts or a coarse targeting signal — what a one-time, TBR-gated config already sets correctly. Auto-config + the raise-guard + per-user hypoCaution IS the controller. See `backtesting/scripts/2026-07-cap-stepper/CAP_STEPPER_PAPER.md`.
