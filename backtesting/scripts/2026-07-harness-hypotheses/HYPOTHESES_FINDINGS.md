# Harness-hypothesis batch (2026-07-20) — four hypotheses, run in parallel, with CIs

*Real Twin (Kotlin harness) + full history (8 users, ~1159 user-days, Feb–Jul, eras by telemetry:
BoostV1_415 = the early v4.1.5 Boost / no explicit v1/v6 telemetry, then V5V6). Validate-before-building
discipline: every effect size has a bootstrap 95% CI + a distinguishable-from-baseline verdict.*

## H12 — did Boost get better across versions? **No measurable change. (SOLID — now on a deep V1 baseline.)**
*Updated 2026-07-20 after the deep backfill: the Boost V1 era now reaches back to Aug 2025 (tim/A/D/F
72–82k V1 cycles each; 9 users). The verdict STRENGTHENED — every metric still overlaps 0.*
Within-user paired Boost V1 (4.1.5) → V5/V6, median Δ [95% CI], n=9:
- ΔTING −1.6 [−5.4, +2.4] · ΔTIR −0.3 [−2.3, +3.5] · ΔTBR<70 −0.21 [−0.92, +0.28] · ΔTBR<54 +0.01 [−0.45,+0.24]
  · ΔCV −0.9 [−3.1, +2.8] · Δmean +3 [−6, +4]
Cohort medians near-identical (TING 68.9↔69.6, TIR 87.2↔85.7, TBR<70 3.93↔3.66, CV 31.2↔29.8, mean 125↔127).
Per-user a wash (C +7 TING on V6, F +2 & CV 36→30, A −5, H −7; TBR lower on V6 for F/tim/D). **Across the
whole arc from the original Boost v4.1.5 (back to Aug 2025) to V5/V6, net glycaemic outcomes did NOT
measurably change** — the versions changed dosing *behaviour* (meal handling, brakes) but not the person's
overall TIR/TING/TBR/CV. Season-confounded (V1 autumn–spring, V6 summer), but the null holds regardless.
Robust, humbling headline: **v4.1.5 ≈ V5/V6 on outcomes.** (Deep-history extension: [[harness-hypotheses-batch]].)

## H4 — Twin+GBM hybrid forecaster? **GBM beats the Twin; the Twin adds ~nothing. (SOLID.)**
BG+30 RMSE (OOS GroupKFold, n=308k): Twin 23.6, GBM 21.5, GBM+Twin 21.48.
- GBM − Twin: **−2.05 [−2.11, −1.99]** → the GBM is a distinctly better forecaster (confirms E01).
- hybrid − GBM: −0.05 [−0.06, −0.04] → distinguishable only by the huge n; **practically zero.**
So for raw BG prediction, use the GBM; **the Twin contributes nothing on top of it.** The Twin's value is
NOT forecasting — it's its physiological state (Ra/IOB compartments) for meal-detection / control substrate.

## H2 — activity-gate the withdrawal? **Helps selectivity, doesn't rescue it. (SOLID.)**
lo30<60 withdrawal, gated on recent-hour steps ≥200: median %-justified rises **18% → 23%**, paired Δ
**+4.9 [+0.7, +11.0]** (gate helps). BUT even gated, **77% of firings are still unjustified**, and gated
bouts are far fewer. So activity+lo30 beats lo30-alone but is still not a viable standalone auto-withhold.

## H7 — Twin distinguishes compression from real lows? **No. (UNPROVEN.)**
139 compression vs 1190 real-low overnight dips. Twin 30-min-forecast "surprise" AUC **0.48 [0.43, 0.53]**
— chance. Mean surprise nearly identical (compression +27, real +30). The forecast-error proxy fails
because a *real* low is also a forecast surprise. Would need the filter's actual update INNOVATION (how
physiologically-impossible the drop is), which the Twin doesn't currently expose — a possible follow-up.

## Net
Three of four came back null/negative, one a weak positive — exactly what the machine is for: four honest
verdicts in one parallel pass on the real engine. The standout is **H12** — across every version and all
the data, Boost's net glycaemic outcomes are statistically indistinguishable. The one clean *positive*
across the whole session's search remains: **a DB-trained GBM is a genuinely better BG forecaster than the
Twin (~2 mg/dL, SOLID)** — the sensor win, reconfirmed here at scale.

## EXTENDED-DATA RE-RUN (2026-07-20, after the Aug-2025 deep backfill — ~1949 user-days, all versions)
All re-run on the full history (my earlier "no pre-Feb data" was a 504 fetch failure, now fixed via
chunked pull). Consolidated, CI-backed:
- **H12 (versions):** every glycaemic Δ still overlaps 0 → **v4.1.5 ≈ V5/V6 on outcomes** (strengthened).
- **H4 (forecaster):** GBM − Twin **−2.41 [−2.46, −2.36]** mg/dL → GBM distinctly better; Twin adds 0.15
  (negligible). The one durable positive. SOLID.
- **Withdrawal:** 1949 user-days, still **7% justified / 93% unjustified / 50% covered** → not viable. SOLID.
- **H2 (activity-gate):** DOWNGRADED — on 9 users Δ +4.1 **[−1.3, +12.7]** now overlaps 0 (was "helps" on
  8). The gate is NOT a reliable rescue. (Discipline catching a small-cohort artifact.)
- **H7 (compression):** AUC **0.50 [0.46, 0.53]** = chance. UNPROVEN.

**Bottom line across all Boost data (Aug 2025 → now, every version):** the ONLY thing that survives is a
DB-trained GBM being a better BG forecaster than the Twin (~2.4 mg/dL, SOLID). Every dosing/action lever is
null-or-unproven, and versions didn't move net outcomes. The sensor is the win; the dosing levers are not.
