# Boost V3ML

> ⚠️ **HISTORICAL — describes an early-2026 branch state; superseded by Boost V6.** When this was
> written the ML hypo-risk model and V3ML plugin were experimental and *not* in the mainline branch.
> That is no longer true: the **ML hypo-risk model is now live inside the current Boost V6 engine**
> (`BoostRiskModel.kt`), and the standalone V3ML plugin (`openAPSBoostV3ML`, shown in the app as
> "Boost v4.4") has been **retired and hidden** — it is no longer selectable. Read this only for the
> history of how the ML model was built and validated; for current behaviour start at the
> [main README](../README.md).

## What V3ML is

V3ML is an experimental branch of Boost V3 that adds two features to the base V3 algorithm: an on-device ML hypo risk model that modulates SMB delivery, and a deviation-based sensitivity model that adjusts ISF, basal, and BG targets in real time. Everything else — the DynISF formula, the 8-tier SMB decision tree, TDD selection, exercise handling — is inherited from V3.

This document covers what V3ML adds and how it differs from the dev branch.

## What's in dev

The dev branch contains Boost V1, V2, and V3 plugins with:
- Full Nightscout field coverage (all Boost decision fields emitted to devicestatus)
- Boost Overview with sensitivity panel and sensitivity graph
- Boost widget with BG bobble and data table
- AAPSClient Boost Overview support (reads from NS device status)
- UnitDoubleKey double-conversion fix for AAPSClient
- Enum crash fix in TypeConverter
- Tier 5+6 BG floor raised to 110 mg/dL (V1, V2, V3)

Dev does not include the ML risk model, deviation sensitivity, the V3ML plugin, or the Boost Overview V2 dark-theme redesign.

## What V3ML adds

### 1. On-device ML hypo risk model

A LightGBM gradient-boosted decision tree model that predicts the probability of a hypoglycaemic event (2+ consecutive CGM readings below 70 mg/dL) in the next 4 hours.

**Model specification:**
- 50 trees, max depth 4, ~148KB JSON
- Trained on 2,972,585 decisions from 28 Nightscout users
- Leave-One-User-Out AUC: 0.6796
- Pure-Kotlin tree walker, no native library dependencies, inference <5ms

**Input features (8, all available at decision time):**

| Feature | Description |
|---|---|
| cgm_mgdl | Current BG in mg/dL |
| iob_iob | Total insulin on board (U) |
| iob_basaliob | Basal IOB component (signed, U) |
| bg_above_target | BG minus algorithm target (mg/dL) |
| direction_num | BG trend as numeric (-2 to +2) |
| hour | Hour of day (0-23) |
| iob_activity | Insulin activity — rate of IOB decay (U/5min) |
| sug_insulinReq | Algorithm's insulin requirement this cycle (U) |

**How it modifies dosing:**

The risk model runs every cycle, after insulinReq is computed but before the SMB tier ladder. It produces a probability score between 0 and 1, which acts on dosing through two mechanisms:

**Graduated SMB scaling.** When risk exceeds 30%, the SMB is scaled down linearly:
```
riskScale = max(0, 1 - (risk - 0.3) / 0.7)
```
At 30% risk, riskScale = 1.0 (no effect). At 65% risk, riskScale = 0.5 (SMB halved). At 100% risk, riskScale = 0.0 (SMB suppressed). The scaling is applied after tier selection, so the tier logic runs normally and the ML model only reduces the final delivery.

**Tier downgrade.** When risk exceeds 60%, tiers 3 through 6 (UAM Boost, UAM High Boost, Percent Scale, Acceleration) are blocked. The algorithm can still use tiers 1-2 (Regular oref1, Enhanced oref1) and tier 7 (IOB cap), but the aggressive boost tiers are suppressed. This prevents large correction boluses when the model detects elevated hypo risk.

Both the risk score and the scale factor are logged to Nightscout via the RT fields `mlHypoRisk` and `mlRiskScale`.

### 2. Deviation sensitivity

A real-time sensitivity model that measures how well insulin is actually working by analysing BG deviations over the past 8 hours. When enabled, it replaces the standard sensitivity ratio entirely.

**What it controls:**
- Dosing ISF (variableSens) — the per-cycle insulin sensitivity used for SMB and temp basal calculations
- Basal rate — profile basal is multiplied by the ratio in determine_basal
- BG targets — min_bg, max_bg, and target_bg are shifted by the ratio

It is controlled by the "Use Autosens" toggle and bounded by the autosens max/min settings (now surfaced in the Boost DynISF settings screen).

**What it measures:**

Every 5 minutes, AAPS computes two values for each CGM reading:
- BGI (Blood Glucose Impact) — how much BG should have changed based on the insulin on board
- Deviation — the difference between what actually happened and what was predicted: `actual_delta − BGI`

If insulin is working as expected, deviation is near zero. Positive deviation means BG is rising more than insulin predicts (resistance). Negative deviation means BG is falling faster than expected (sensitivity).

**How it computes the ratio:**

The model looks back 8 hours and applies strict filtering. It only uses entries where:
- validDeviation is true
- COB < 1 (no active carbs on board)
- absorbing is false (no carb absorption in progress)
- uam is false (no unannounced meal detection active)

This typically excludes 40–50% of entries in the window. The goal is to measure insulin's effect on BG without meal carbs confounding the signal.

From the clean entries it computes:
```
meanDeviation = sum of clean deviations / number of clean entries
meanAbsBGI    = sum of |BGI| across ALL entries / total entries
ratio         = 1 + (meanDeviation / meanAbsBGI)
```

The denominator — mean absolute BGI across the whole window — normalises the deviation by how much insulin effect there typically is. This makes the ratio dimensionless: a ratio of 1.3 means "BG is moving 30% more than insulin predicts" regardless of whether the user carries 0.5U or 5U of IOB.

If mean absolute BGI is below 0.5 (very low insulin activity, e.g. fasting with minimal IOB), the model returns 1.0 (neutral) because the deviation signal is unreliable — small BG noise produces large ratios when the denominator is near zero.

The ratio is clamped to the user's autosens min/max bounds. If fewer than 6 clean entries exist in the 8-hour window, the model falls back to a TDD ratio (24H TDD / 7D TDD), also clamped to the same bounds.

**Where the ratio is applied:**

The DynISF pipeline computes ISF using the Chris Wilson logarithmic formula:
```
variableSens = 1800 / (TDD × ln((currentBG / 120) + 1))
```

The deviation ratio is then applied to the result:
```
variableSens /= ratio
```

This is a percentage adjustment on the DynISF output. At ratio 1.3, ISF is reduced by 23% from wherever the Chris Wilson formula placed it at the current BG. At ratio 0.8, ISF is increased by 25%. The adjustment is the same percentage at any BG level, but because the Chris Wilson formula already produces lower ISF at higher BG, the absolute effect in mg/dL/U is larger at high BG than at low BG.

The same ratio is passed to determine_basal where it adjusts basal rate and BG targets.

### 3. Boost Overview V2

A dark-theme redesign of the Boost Overview screen with:
- Hero BG ring (bobble) with trend chevron
- Stat pills showing IOB, COB, TDD, sensitivity ratio
- Chart cards with dark-theme graph styling (subtle cyan in-range, orange basals, blue IOB)
- Sensitivity panel showing deviation ratio, source, and clean/total entry counts

Toggled via the "Use Boost Overview V2" preference.

### 4. Sensitivity graph

Added to both the original and V2 Boost Overview. Computes a rolling deviation ratio from raw BG and IOB data independently of the deviation sensitivity preference, so the signal is always visible for monitoring. Uses the algorithm's variableSens for BGI calculation (not profile ISF).

## What V3ML inherits from V3 (not on dev)

These features are on the V3/V3ML branches but not on dev:

- **Deviation-based 8H sensitivity ratio** — the computeDeviationSensitivity() function and its integration into calculateBoostIsf()
- **Exercise recovery internal target raise** — V3 removed the TempTarget from exercise recovery and uses internal effectiveMinBg/effectiveMaxBg/effectiveTargetBg instead, because TTs with target > 100 triggered the SMB-disable-on-high-temptarget check
- **Tier 5 BG floor at 110** — V3 raised from 98 to 110 based on testing

**Note:** The V3ML branch still uses TT-based exercise recovery. The internal-target fix from V3 has not yet been ported to V3ML.

## Files

| File | Purpose |
|---|---|
| `openAPSBoostV3ML/OpenAPSBoostV3MLPlugin.kt` | V3ML plugin — calculateBoostIsf() with deviation sensitivity, exercise/activity detection, preference screen |
| `openAPSBoostV3ML/DetermineBasalBoostV3ML.kt` | V3ML determine_basal — 8-tier SMB ladder with ML risk integration (graduated scaling + tier downgrade) |
| `openAPSBoostV3ML/BoostRiskModel.kt` | Pure-Kotlin LightGBM tree walker — loads JSON model, runs inference |
| `app/src/main/assets/boost/hypo_risk_model.json` | 50-tree depth-4 model (148KB) |
| `app/src/main/assets/boost/hypo_risk_meta.json` | Model metadata (features, AUC, training size) |
| `core/interfaces/.../RT.kt` | Added fields: deviationSensRatio, deviationSensSource, deviationSensClean, deviationSensTotal, mlHypoRisk, mlRiskScale |
| `overview/boost/BoostOverviewV2Fragment.kt` | Dark-theme overview redesign |
| `overview/boost/BoostV2GraphData.kt` | Custom graph data with dark-theme colours |
