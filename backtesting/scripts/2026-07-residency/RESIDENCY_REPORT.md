# Residency attribution — where the TIR loss actually comes from

_Boost dosing research note, 2026-07-08. V6 (`boostv5_*`) telemetry, TimescaleDB `oref.boost_decisions`, 8 anonymised users (self + A–H), 2026-02 → 07. ~87k cycles, 1,100 episodes. Reproduce: `residency_attribution.py` → `residency_ml.py` → `residency_chart.py`._

> **⚠️ CORRECTION 2026-07-16 — the RESCUE_OVERSHOOT low-lever was a measurement artifact.** `classify_low` attributed `RESCUE_OVERSHOOT` from `low3h` — a **forward** "low within the next 3h" flag (`v7_common.add_rolling`), which leaks the outcome and made the bucket near-tautological. Fixed to a **backward** antecedent (`prior_low3h` = a low in the *prior* 3h → a genuine recurring/see-saw rescue low). Re-run on data refreshed through 2026-07-13: **RESCUE_OVERSHOOT collapses from POOL 37% / per-user-median 44% → POOL 7% / MEDN 5%**, and that time reallocates almost entirely to **BASAL_DRIFT (POOL 1% → 30%, MEDN 1% → 37%)**. ACTIVITY (~48/36%) and STACKING (~16/17%) are unchanged (they rank ahead of rescue in the if-chain). **The reversed conclusion: after ACTIVITY, the #2 low lever is basal/ISF drift, NOT rescue-overshoot — do not build a rescue-handling lever on this data.** The corrected LOW table and findings below supersede the originals; the `residency_attribution.png` chart is stale (regenerate). Everything HIGH-time is unaffected.

![attribution](residency_attribution.png)

## Method

Each user's timeline is segmented into **HIGH** (>180 mg/dL) and **LOW** (<70) episodes (brief dips bridged if < 20 min apart). Each episode's **onset** is attributed to one proximate mechanism from the telemetry in the 45 min before the crossing; the onset owns the episode's minutes (fix the onset → the episode doesn't happen). Minutes = hot-cycle count × 5 (CGM cadence). Purely **attributive** over observed data — no counterfactual BG is claimed.

An LGBM layer (GroupKFold **by user**, so no within-user leakage) then answers *foreseeability*: predict forward-high (BG+60 > 180) and forward-low (BG+60 < 70), report AUC + gain importance, and score each episode's pre-onset cycle to give a **mean model risk 45 min before onset, by cause** — high risk ⇒ the episode was already forecastable ⇒ a dosing-failure cause there is avoidable.

## HIGH-time attribution (% of each user's >180 minutes)

| user | high% | LATE_CONFIRM | BRAKE_SUPPRESS | RECOVERING_HOLD | CAP_CLIP | UNDERSIZED | UNCOVERABLE | NO_MEAL_HIGH |
|---|---|---|---|---|---|---|---|---|
| self | 11.2 | 23 | **47** | 6 | 13 | 0 | 10 | 2 |
| A | 14.6 | 6 | 38 | 9 | 22 | 5 | 16 | 5 |
| B | 16.6 | 19 | 22 | 17 | 12 | 13 | 11 | 5 |
| C | 5.2 | 12 | 13 | 13 | **38** | 8 | 5 | 11 |
| D | 2.0 | 0 | 14 | 12 | **59** | 16 | 0 | 0 |
| E | 1.0 | **74** | 11 | 0 | 0 | 0 | 0 | 15 |
| F | 13.6 | 15 | 40 | 11 | 3 | 21 | 5 | 5 |
| H | 7.4 | 7 | 39 | 7 | 41 | 0 | 0 | 5 |
| **COHORT** | — | **16** | **34** | 11 | 15 | 9 | 10 | 5 |

## LOW-time attribution (% of each user's <70 minutes)

_Corrected 2026-07-16 (backward `prior_low3h` antecedent; data through 2026-07-13). Original buggy-flag numbers in [brackets] for the two columns that changed._

| user | low% | ACTIVITY | STACKING | RESCUE_OVERSHOOT | BASAL_DRIFT |
|---|---|---|---|---|---|
| self | 5.3 | 50 | 23 | 7 [27] | 20 [0] |
| A | 1.2 | 20 | 15 | 17 [65] | 49 [1] |
| B | 3.9 | 22 | 22 | 4 [55] | 52 [1] |
| C | 4.3 | 57 | 19 | 4 [23] | 20 [0] |
| D | 8.9 | 61 | 7 | 8 [31] | 24 [1] |
| E | 1.0 | 19 | 12 | 2 [67] | 67 [2] |
| F | 3.2 | 59 | 10 | 6 [31] | 25 [1] |
| H | 0.7 | 4 | 38 | 0 [54] | 58 [4] |
| **POOL** | — | **48** | 16 | **7** [36] | **30** [1] |
| **MEDN** | — | **36** | 17 | **5** [43] | **37** [1] |

## Foreseeability (LGBM, grouped-by-user OOF)

Forward-high **AUC 0.83 ± 0.02**, forward-low **AUC 0.78 ± 0.06** — both substantially predictable an hour out. Base rates: high 0.09, low 0.04. Mean model risk 45 min **before** onset, by cause:

| cause | minutes | pre-onset risk | × base | reading |
|---|---|---|---|---|
| high · BRAKE_SUPPRESS | 14,370 | 0.14 | 1.5× | **foreseeable** |
| high · LATE_CONFIRM | 6,790 | 0.12 | 1.2× | elevated |
| high · CAP_CLIP | 6,505 | 0.05 | 0.5× | surprise |
| high · RECOVERING_HOLD | 4,480 | 0.09 | 1.0× | at base |
| high · UNCOVERABLE | 4,065 | 0.09 | 0.9× | surprise |
| high · UNDERSIZED | 3,860 | 0.06 | 0.6× | surprise |
| high · NO_MEAL_HIGH | 1,990 | 0.22 | 2.4× | **foreseeable** |
| low · ACTIVITY | 7,410 | 0.04 | 1.2× | elevated |
| low · RESCUE_OVERSHOOT | 5,885 | 0.05 | 1.4× | elevated |
| low · STACKING | 2,555 | 0.04 | 1.0× | at base |

Feature importance corroborates the taxonomy: forward-high is driven by BG, IOB-fraction, recent-meal-insulin, hour, score, delta5; forward-low by BG, recent-meal-insulin, eventual-BG, hour, delta5, **steps/activity**, sens — the prominence of steps/activity in the low model independently backs ACTIVITY as the top low cause.

## Findings

1. **The brake owns a third of all high-time (34%, 14,370 min) — and it's foreseeable (1.5× base).** The single largest TIR-loss mechanism is the composed-multiplier suppression firing on rises the model can already see coming. This directly validates the composed brake-floor work as the **#1 high lever**, and is heaviest for self (47%), F (40%), H (39%), A (38%).
2. **Low-time is dominated by activity + basal/ISF drift, not by dosing** _(corrected 2026-07-16 — the original "activity + rescue" reading was the forward-flag artifact; see the ⚠️ banner)._ Corrected shares: ACTIVITY POOL 48% / MEDN 36%, **BASAL_DRIFT POOL 30% / MEDN 37%**, STACKING 16/17%, RESCUE_OVERSHOOT only 7/5%. So the #1 low lever is ACTIVITY (exercise protections / Garmin ingest), and the **#2 is basal/ISF drift** (overnight + between-meal), not rescue. Boost's *dosing* (stacking 16%) remains a minor low driver, and rescue-overshoot is now minor too.
3. **Cap-clip / undersized / uncoverable highs are *not* foreseeable 45 min out** (0.5–0.9× base) — sudden meal hits. These need a faster/bigger *response*, not better *prediction*; per-user cap sizing (auto-config) and confirm sizing (V7) are the levers, not anticipation.
4. **Late-confirm (16%) and dawn/basal (NO_MEAL_HIGH, 2.4× base — most foreseeable of all) are avoidable by timing** — the confirm age-gate/score-ready lever and proactive basal handling.
5. Roughly **85% of high-time is dosing-mechanism attributable**; ~15% (uncoverable + surprise no-meal) is closer to irreducible. _(Corrected 2026-07-16: the earlier "basal well-tuned, BASAL_DRIFT = 1% of lows" was the forward-flag artifact — with the backward antecedent BASAL_DRIFT is **30–37%** of lows, i.e. basal/ISF drift is a genuine second low lever, not negligible.)_

## Lever priority (what this says to work on)

1. **Brake correctness** — 34% of high-time, foreseeable. The composed brake-floor is validated as the top lever. **Caveat:** this is *proximate mechanism, not proven causation* — "the brake was suppressing during the rise" ≠ "the brake was wrong" (some suppression is correct high-IOB restraint). The follow-up is the **brake-correctness audit** (of suppressed-rise cycles, what fraction stayed high vs resolved) to price it.
2. **Activity → hypo (#1) and basal/ISF drift (#2)** — the low-time drivers _(corrected 2026-07-16)_. ACTIVITY POOL 48% / MEDN 36%; BASAL_DRIFT POOL 30% / MEDN 37%. Prioritise the Garmin ingest / exercise protections, then a basal/ISF-drift review (overnight + between-meal). Rescue-overshoot (5–7%) is NOT a top lever — the earlier co-equal-with-activity claim was the forward-flag artifact.
3. **Confirm timing** — 16% high, foreseeable (age-gate / score-ready).
4. ~~**Rescue-overshoot** — 37% low; a rescue-handling lever.~~ **RETRACTED 2026-07-16** — the 37% was a forward-flag artifact; corrected to 5–7%. Do not build a rescue-handling lever on this. The reallocated time is **basal/ISF drift** (see #2).

## Caveats

- **Pooled vs per-user (added on 2026-07-10 audit).** The cohort cause-shares above are **minute-weighted pooled** (Σ cause-minutes / Σ total-minutes), so high-hot-time users dominate. Per-user medians differ, sometimes materially: low-time **activity/rescue rank flips** (pooled activity 47>rescue 37; per-user rescue 44>activity 36); high-time **brake's lead over sizing narrows** (pooled brake 34 vs cap-clip 15.5; per-user-median brake 30.1 vs cap-clip 17.2 + undersized 6.5 ≈ 24). Direction of the top high cause (brake) survives; the *magnitude* of "brake ≫ sizing" is a pooling effect and the low #1 is aggregation-dependent. Read pooled = population-total, per-user-median = typical user.
- **Proximate ≠ causal.** Attribution names the mechanism active at onset; it does not prove that mechanism *caused* the episode. The brake finding especially needs the correctness audit before it drives a change.
- **Decision-tree ordering** puts BRAKE before CAP_CLIP/UNDERSIZED, so a cycle that is both braked and clipped counts as brake — this inflates upstream causes; combined with the pooling caveat, the "brake ≫ sizing" high gap is the least robust part of the taxonomy. The ordering is a documented judgement call and can be swept.
- **Foreseeability is model-relative** (AUC 0.83/0.78) and thresholded against base rate, not an absolute claim of avoidability.
