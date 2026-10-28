# Boost — legacy plugin & settings reference (V1 / V2 / v4.2)

[![Support Server](https://img.shields.io/discord/629952586895851530.svg?label=Discord&logo=Discord&colorB=7289da&style=for-the-badge)](https://discord.gg/aUzQ8q5zQd)

> 📖 **This page is the detailed settings reference for the earlier Boost plugins (V1, V2, v4.2).**
> It is kept separate so the main page stays focused on the current generation.
> **For Boost V6 — what's different, how it works, and the V6 settings — start at the
> [main README](../README.md).** Most V6 settings are *auto-seeded* from your own history
> (see the README's auto-configuration section); this page documents the underlying V1/V2
> plugins that V6 still runs on top of and derives its starting defaults from.

> ⚠️ **LEGACY REFERENCE — V2 / v4.2 etc. are retired and no longer selectable.** Only **"Boost"**
> (the base engine) and **"Boost V6"** now appear in the APS plugin list. The intermediate plugins
> (V2, V3, v4.4/v4.4.2 — the doc calls the last of these "v4.2") are hidden and cannot be chosen as
> your active APS. Any instruction below to *"select it as the active APS"* is **historical** and no
> longer possible; those plugins' behaviour has been folded into Boost V6. Keep reading for the
> settings *concepts* (DynISF formulae, tiers, night mode), not the plugin-selection steps.

---

This documentation adds two experimental features on top of the dev branch:

1. **On-device ML hypo risk model** — active in all three plugins (Boost V1, V2, v4.2)
2. **Deviation-based sensitivity model** — active in v4.2 only (replaces standard sensitivity ratio)

The APK contains three APS plugins: **Boost (V1)**, **Boost V2**, and **Boost v4.2**. The standalone V3 plugin has been removed from this branch — v4.2 supersedes it.

---

## What's different from dev

### ML hypo risk model (all plugins)

A LightGBM gradient-boosted decision tree model that predicts the probability of a hypoglycaemic event (2+ consecutive CGM readings < 70 mg/dL) in the next 4 hours. It runs every cycle in Boost V1, V2, and v4.2.

**Model:** 50 trees, max depth 4, ~148KB JSON, pure-Kotlin tree walker, <5ms inference, no native dependencies. Trained on ~3 million decisions from 28 Nightscout users (Leave-One-User-Out AUC: 0.68).

**Inputs (8 features):** current BG, total IOB, basal IOB, BG above target, BG trend direction, hour of day, insulin activity, algorithm's insulin requirement.

**How it modifies dosing:**

- **Graduated SMB scaling.** When risk > 30%, the SMB is scaled down linearly: full at 30%, halved at 65%, suppressed at 100%. Applied after tier selection — the tier logic runs normally, the ML model only reduces the final delivery.
- **Tier downgrade.** When risk > 60%, tiers 3–6 (UAM Boost, UAM High Boost, Percent Scale, Acceleration) are blocked. Tiers 1–2 and 7–8 remain available.

Risk score and scale factor are logged to Nightscout via `mlHypoRisk` and `mlRiskScale` in the device status.

### Deviation sensitivity (v4.2 only)

A real-time sensitivity model that measures how well insulin is actually working by analysing BG deviations over the past 8 hours. When enabled, it replaces the standard sensitivity ratio and controls:

- **Dosing ISF** — adjusted after the DynISF Chris Wilson log curve
- **Basal rate** — profile basal multiplied by the ratio
- **BG targets** — min_bg, max_bg, target_bg shifted by the ratio

Controlled by the **Use Autosens** toggle. Bounded by **Max/Min autosens ratio** (surfaced in the Boost DynISF settings screen).

**How it works:**

Reads from the AAPS deviation data store over 8 hours. Filters to clean entries only (no COB, no absorption, no UAM). Zeros positive deviations when BG < 80 (prevents post-hypo rebounds counting as resistance). Zero-pads when clean entries < 50% of the window (dampens sparse data). Takes the **median** of filtered deviations (robust to outliers), then:

```
ratio = 1 + (medianDeviation / mean|BGI|)
```

Applied to variableSens after the DynISF log curve:
```
variableSens = 1800 / (TDD × ln((currentBG / 120) + 1))
variableSens /= ratio
```

### Boost Overview V2 (all plugins)

Dark-theme redesign with hero BG ring, stat pills, chart cards, and sensitivity panel. Toggled via **Use Boost Overview V2** preference.

### Exercise recovery fix (v4.2 only)

Exercise recovery uses internal target raise (effectiveMinBg/effectiveMaxBg/effectiveTargetBg) instead of TempTarget insertion. TTs with target > 100 triggered the SMB-disable-on-high-temptarget check, killing Boost's tier system during recovery.

---

## Plugin comparison

| Feature | Boost V1 | Boost V2 | Boost v4.2 |
|---|---|---|---|
| **ISF formula** | 1800 / (TDD × ln) | 2300 / (ln × TDD² × 0.02) | 1800 / (TDD × ln) |
| **TDD source** | Blended (8H + 7D + 1D) | Blended (8H + 7D + 1D) | 7D average only |
| **BG impact dampening** | User-adjustable (velocity) | None | None |
| **ML hypo risk** | Yes | Yes | Yes |
| **Deviation sensitivity** | No | No | Yes |
| **Exercise recovery** | TT-based | TT-based | Internal target (no TT) |

---

For the full Boost documentation (tiers, settings, COB handling, night mode, step counting, heart rate, fast-carb rebound), see the dev branch README.

All Boost-specific settings, including Dynamic ISF, Night Mode, and Step Counting, are consolidated within each plugin's preferences screen as sub-screens.

This release also includes a **Boost Overview UI** — a redesigned home screen tailored for Boost users, with at-a-glance algorithm status, larger graphs, and tappable detail panels. See the [Boost Overview UI](#boost-overview-ui) section below.

## You will need to make a note of your preferences and re-enter them. This is true for all the Boost, Dynamic ISF and Night Mode preferences due to the major re-engineering that had to take place.

---

## What's new in this release?

### Calibration SMB Block

When a CGM calibration is detected, Boost and Boost V2 now automatically suppress SMBs for 15 minutes. Calibration can cause the sensor to temporarily report erratic or inaccurate glucose values, making the algorithm's decisions unreliable during the stabilisation period. The block applies only to SMBs — temp basal adjustments continue normally throughout.

Calibrations are detected from two sources: native CGM sources (Dexcom, Glunovo, Intelligo) that insert a `FINGER_STICK_BG_VALUE` therapy event into AAPS, and the AAPS Calibration dialog when a value is confirmed. Calibrations performed directly within xDrip+ and not entered via AAPS are invisible to the system and cannot be detected.

No settings are required. The block is always active and cannot be disabled.

---

### Post-Exercise Recovery Mode

After exercise ends, Boost and Boost V2 can automatically set a recovery TempTarget and reduce SMB aggressiveness for a configurable period. Post-exercise hypoglycaemia is one of the most common risks in closed-loop T1D management: glucose uptake by exercised muscle continues for up to two hours after aerobic exercise stops (immediate risk), and glycogen replenishment drives ongoing glucose uptake overnight (delayed risk).

**How it works:**

Exercise end is detected automatically by monitoring the step count transition from active to inactive. When steps were above the activity threshold and then fall back to resting levels, recovery is triggered. A minimum exercise duration (default 10 minutes) prevents false triggers from brief step bursts.

Once triggered, two protective actions are taken simultaneously:

1. **Visible TempTarget** — a temporary glucose target is inserted into AAPS (default 8.0 mmol/L / 144 mg/dL) for the duration of the recovery window. This target is visible in the Overview and can be cancelled manually at any time. If a TempTarget is already active, this step is skipped.
2. **Internal SMB reduction** — `boost_bolus` and `boost_scale` are reduced by a configurable factor (default 50%) for the duration of the window. This provides a safety net even if the user cancels the TempTarget.

**Recovery window defaults** are based on ATTD 2020 consensus (Riddell et al.):
- Recovery window: 2 hours (primary aerobic hypo risk window)
- Recovery target: 8.0 mmol/L / 144 mg/dL (ATTD recommended centre-point)
- SMB reduction: 50%
- Minimum exercise duration to trigger: 10 minutes

All four values are user-configurable in the **Post-Exercise Recovery** sub-screen within Boost preferences.

**Integration with Heart Rate** (see below): when Heart Rate integration is enabled, the recovery parameters adapt automatically to the type of exercise detected — see [Heart Rate Integration](#heart-rate-integration) for details.

---

### Heart Rate Integration

Boost and Boost V2 can now use heart rate data alongside step counts for more accurate exercise detection and classification. Steps alone cannot detect resistance training (low steps, elevated HR), stress/illness (elevated HR without movement), or distinguish vigorous aerobic exercise from a brisk walk.

Heart rate data is read from AAPS's built-in HR recording mechanism (populated by paired watches/wearables). Each reading is a 1-minute duration-weighted average of beats per minute stored in the AAPS database.

**Classification model — Karvonen Heart Rate Reserve (HRR%):**

```
HRR% = (current HR − resting HR) / (HRmax − resting HR) × 100
```

Karvonen is used in preference to simple %HRmax because it accounts for individual fitness level. Five zones are defined:

| Zone | HRR% | Label |
|---|---|---|
| 1 | < 30% | Very light (recovery, rest) |
| 2 | 30–40% | Light (easy aerobic) |
| 3 | 40–60% | Moderate (aerobic conditioning) |
| 4 | 60–80% | Hard (vigorous aerobic / strength) |
| 5 | > 80% | Maximum effort |

**Combined exercise states (HR + steps):**

| State | Detection | Effect |
|---|---|---|
| VIGOROUS_AEROBIC | High steps + zone 3–5 | Reduced profile %, raised target |
| MODERATE_AEROBIC | Moderate steps + zone 2–3 | Same as step-only ACTIVE |
| LIGHT_AEROBIC | Steps elevated + zone 1–2 | Same as step-only ACTIVE |
| RESISTANCE | Low/no steps + zone 3–4 | Raised target only — profile % unchanged (BG rises acutely; don't increase aggressiveness) |
| STRESS | Low steps + zone 2–3 (opt-in) | Raised target, profile unchanged |
| RESTING / INACTIVE | Low HR + low steps | Normal / inactivity reduction |

When HR data is unavailable or the feature is disabled, the code falls through to the existing step-only logic exactly. HR integration is strictly additive — it cannot produce worse behaviour than the step-only path.

**Settings** (in the **Heart Rate Integration** sub-screen):
- *Enable HR Integration* — Master switch. Default: off (opt-in, requires a paired wearable).
- *HRmax (BPM)* — Your maximum heart rate. Default: 180. If you know your HRmax (e.g. from a field test), enter it here for more accurate zone calculation. As a rough guide, 220 − age gives an estimate.
- *Resting HR (BPM)* — Your resting heart rate. Default: 60.
- *HR window (minutes)* — How many minutes of HR history to average for zone classification. Default: 15.
- *Enable stress detection* — Raises target BG when elevated HR is detected without movement. Off by default; use with caution.

---

### HR-Informed Post-Exercise Recovery

When both Heart Rate integration and Post-Exercise Recovery are enabled, the recovery parameters adapt to the type of exercise that was detected, rather than using the same settings for every session:

| Exercise type | Recovery window | Target BG | SMB reduction |
|---|---|---|---|
| VIGOROUS_AEROBIC | ×1.25 (2h → 2h30m) | unchanged | more (×0.8 of user setting) |
| RESISTANCE | ×1.5 (2h → 3h) | +10 mg/dL | less (×1.2 of user setting) |
| LIGHT_AEROBIC | ×0.5 (2h → 1h) | unchanged | less (×1.4 of user setting) |
| MODERATE / ACTIVE (or no HR) | ×1.0 — user defaults | unchanged | user defaults |

The rationale:
- **VIGOROUS_AEROBIC**: high immediate hypo risk from rapid glycogen depletion; longer window and stronger SMB suppression.
- **RESISTANCE**: acute BG rise short-term (don't over-suppress while BG is high), but delayed hypo risk overnight; longest window, higher target, less immediate suppression.
- **LIGHT_AEROBIC**: minimal glycogen depletion; a shorter window with less suppression is appropriate.

The user's configured settings always serve as the baseline for moderate/unclassified exercise. The multipliers are applied on top.

---

### Enhanced Exercise Management

Several improvements to how Boost detects and responds to exercise:

**15-minute activity detection:** Exercise detection now includes a dedicated 15-minute step threshold (`ApsBoostActivitySteps15`, default 800 steps). Previously, detection jumped from a 5-minute window directly to 30 minutes, meaning moderate activity that didn't trigger the 5-minute threshold would go undetected until 30 minutes of steps had accumulated. The 15-minute window closes this gap, allowing the algorithm to respond to sustained walking or light exercise within 15 minutes.

**Dedicated HR/Steps graph:** Heart rate and step count data are displayed on a dedicated third graph in the Boost Overview, separate from the IOB graph. The graph appears automatically when HR or Steps are enabled in the chart menu (column 1) and collapses when neither is selected.

---

### Fast-Carb Rebound Protection

When fast-acting carbohydrates are eaten to treat a low (a rescue carb event), the subsequent glucose rise can look identical to an unannounced meal from the algorithm's perspective — rapid rise, no COB entry, high UAM boost factors. Without a logged carb entry, Boost would previously fire its aggressive UAM and acceleration tiers during this recovery, risking insulin stacking onto what is actually a carb-driven rebound.

This release adds fast-carb rebound detection to both Boost and Boost V2. Each loop cycle, AAPS computes the minimum CGM reading over the last 60 minutes (`recentLowBG`) and passes it to the dosing algorithm. If the following conditions are all true simultaneously, the algorithm concludes a fast-carb rescue rebound is in progress:

- `recentLowBG` was below 100 mg/dL (BG was in low-normal range within the last hour)
- No carbs are currently logged (`mealCOB = 0`)
- Current BG is below 170 mg/dL (still in the recovery zone, not a true hyperglycaemic rise)
- `delta_accl` is above 25 (glucose acceleration is sharp — consistent with fast-carb absorption)

When this pattern is detected, **Tier 3 (UAM Boost), Tier 5 (Percent Scale), and Tier 6 (Acceleration Bolus)** have their SMB output scaled down proportionally based on the current BG, rather than being fully blocked:

- **BG below 120 mg/dL** — strong suppression (30% of the tier's calculated SMB)
- **BG 120–170 mg/dL** — linear ramp from 30% to 100% as BG rises further from target
- **BG above 170 mg/dL** — no suppression (full tier response)

This graduated approach means the algorithm still delivers some insulin during the early recovery phase, but increasingly so as BG moves further from target. Previously, the protection was binary — tiers were fully blocked until either `delta_accl` dropped below 25 or `recentLowBG` cleared 100 mg/dL, which could leave the algorithm unable to respond to a genuine spike building on top of a recovery.

**Velocity override:** If delta exceeds 15 mg/dL/5min and BG is already more than 20 mg/dL above target, the protection releases immediately regardless of `recentLowBG`. At that point the rise is a genuine spike, not a gentle recovery.

**Spike override cap:** A related enhancement addresses the SMB cap bottleneck that can occur after a post-hypo rebound develops into a full spike. When Tier 8 (regular oref1) fires with BG above 180 mg/dL, delta above 5, and `insulinReq` exceeding 3× the basal-derived `maxBolus` cap, the SMB ceiling is raised from `maxBolus` (basal × uamSMBmins / 60) to `boost_max`. This prevents the situation where the algorithm knows 2–3U of insulin is needed but can only deliver 0.1–0.2U per cycle due to a structurally low basal rate.

**What this means in practice:** after eating fast carbs without logging them, the algorithm will still deliver insulin if the glucose rises above target — scaled down near target but increasingly close to the full tier output as BG climbs. If the recovery overshoots into a genuine spike above 180 mg/dL, the algorithm can now respond with appropriate SMB sizes rather than being rate-limited by the basal-derived cap.

**How the detection works:**

Two signals are used — either is sufficient, with `delta_accl > 25` and `COB = 0` required in both cases:

- **`recentLowBG < 100 mg/dL`** — BG was in low-normal territory within the last 60 minutes (the typical pre-treatment state). This covers the common scenario of eating fast carbs to treat or prevent a low.

- **`reversalScore > 30`** — computed as `delta × |longAvgDelta|` when `longAvgDelta < 0` and `delta > 0`. This captures fast carbs eaten from a falling high BG where the long-term average still reflects the preceding fall — even if BG never dropped below 100 mg/dL. When the long average is essentially flat (±2 mg/dL), the score equals approximately `delta × 2`, requiring a delta above 15 mg/dL/5min to fire — appropriately conservative for a near-flat trend.

This combination was validated against a labelled dataset of 21 events (12 fast-carb, 9 meal): it correctly identified 12/12 fast-carb events (with corrected per-cycle lookback). The 3–4 false positives were all unlogged meals eaten after a low — cases the algorithm cannot distinguish from fast-carb rebounds, but where the clinical consequence (Tier 7 giving a modest dose instead of Tier 3) is lower-risk than the alternative.

This protection applies to both the **Boost** and **Boost V2** plugins.

---

### Boostv2 Plugin using DynISF V2

**Important:** When starting with DynISF V2 — set the **TDD adjustment factor to 100%** as your starting point. This gives you the unmodified formula output. Adjust up or down from there based on your results. Do not carry over your V1 adjustment factor, as the squared TDD term means the same percentage has a much larger effect in V2 (so if your value is below 100%, it produces significantly larger ISF values).

### Boost Overview UI

A new home screen designed specifically for Boost, replacing the standard AAPS Overview with a layout that puts algorithm decisions front and centre. See [Boost Overview UI](#boost-overview-ui) for full details.

---

## What's different in Boost V2?

Boost V2 replaces the DynISF calculation with a new formula. Everything else — the Boost tiers, COB handling, step counting, night mode, and all SMB sizing logic — is identical to the standard Boost plugin.

**DynISF V1 (original Boost):**
```
ISF = 1800 / (TDD × ln(BG / insulinDivisor + 1))
```
The V1 formula uses a **BG impact on ISF** slider (formerly "velocity") that dampens how much BG affects the ISF adjustment. At 50%, only half the BG-driven ISF change is applied.

**DynISF V2 (Boost V2):**
```
ISF = 2300 / (ln(BG / insulinDivisor + 1) × TDD² × 0.02)
```
The V2 formula squares the TDD term and uses a fixed 0.02 scaling factor. There is no velocity or dampening slider — the full BG-driven adjustment is always applied.

### Key differences at a glance

| | Boost (V1) | Boost V2 |
|---|---|---|
| **Numerator** | 1800 | 2300 |
| **TDD term** | TDD (linear) | TDD² (squared) |
| **BG impact dampening** | User-adjustable | None — always full effect |
| **TDD sensitivity** | 10% TDD change ≈ 10% ISF change | 10% TDD change ≈ 21% ISF change |

### Important: TDD sensitivity

Because TDD is squared in the V2 formula, ISF is **much more responsive to TDD changes** than in V1. A 10% increase in TDD produces roughly a 21% decrease in ISF (more aggressive dosing). This means:

* V2 will self-adjust more aggressively as your TDD changes day to day.
* It is strongly recommended to **log-compare V1 and V2 output side by side** before running V2 live.
* TDD data is mandatory for the V2 formula. If TDD data is incomplete, ISF falls back to your profile ISF.
* **Start with an adjustment factor of 100%** and adjust from there.

---

## What's different in Boost V3?

Boost V3 uses the same ISF formula as V1 (`1800 / (TDD × ln(BG / insulinDivisor + 1))`) but changes **how TDD is calculated** and **removes BG Impact dampening**.

### TDD: 7-day average only

V1 and V2 compute a blended TDD from three sources weighted equally:

```
TDD_blended = (WeightedLast8H × 0.33) + (7D_average × 0.34) + (1D_average × 0.33)
```

The `WeightedLast8H` component is `(1.4 × last4H + 0.6 × last8-4H) × 3`, which extrapolates recent insulin delivery to a daily rate. During a rollercoaster day — repeated spikes treated with large SMBs — this 4-hour window inflates the blended TDD far above the 7-day average. A higher TDD produces a lower ISF, making the algorithm more aggressive, which stacks more insulin, which crashes BG further, which requires rescue carbs, which starts the next spike.

V3 eliminates this feedback loop by using the **7-day average only**:

```
TDD_v3 = 7D_average × adjustment_factor
```

The safety check is retained: when the weighted 8-hour TDD falls below 75% of the 7-day average (indicating significantly reduced insulin delivery, e.g. overnight or during fasting), the 7-day value is pulled down toward recent reality to avoid overdosing:

```
if WeightedLast8H < 0.75 × 7D:
    TDD = WeightedLast8H + (WeightedLast8H / 7D) × (7D − WeightedLast8H)
```

### No BG Impact dampening

V1 includes a **BG Impact on ISF** setting (velocity) that controls how much the current BG level affects the ISF calculation. At 50%, only half the BG-driven ISF change is applied — the ISF is dampened toward the normal-target ISF.

V3 always applies the full BG effect (equivalent to velocity = 100%). This setting has been removed from the V3 preferences. The rationale: with the more stable 7-day TDD providing the base, the BG-driven ISF adjustment is already appropriately scaled and does not need artificial dampening.

### Key differences at a glance

| | Boost (V1) | Boost V2 | Boost V3 |
|---|---|---|---|
| **ISF formula** | 1800 / (TDD × ln) | 2300 / (ln × TDD² × 0.02) | 1800 / (TDD × ln) |
| **TDD source** | Blended (8H + 7D + 1D) | Blended (8H + 7D + 1D) | 7D average only |
| **BG impact dampening** | User-adjustable (velocity) | None | None |
| **TDD sensitivity** | Reactive to recent boluses | Highly reactive (TDD²) | Stable — immune to short-term spikes |
| **Best for** | General use | Users who want maximum TDD responsiveness | Users experiencing rollercoaster patterns |

### When to use V3

V3 is designed for users who experience repeated spike-crash-rebound cycles. If your Nightscout data shows:
- Multiple high-low swings in a single day (>3 transitions between <70 and >180 within 24h)
- The algorithm delivering large SMBs at BG 80-100 after a spike (overcorrection)
- 4-hour TDD significantly higher than 7-day average during these events

V3 will produce a more stable ISF that doesn't escalate during the spike, reducing the overcorrection that triggers the next cycle.

If your control is generally stable and you're not experiencing rollercoaster patterns, V1 or V2 may be more responsive to genuine changes in insulin needs.

> ⚠️ **Boost V3 is experimental.** Run it in parallel alongside V1 in Config Builder to compare outputs before switching. Start with a **TDD adjustment factor of 100%** and monitor for several days.

---

## Boost v4.2

Boost v4.2 extends V3 with two features: an on-device ML hypo risk model and a deviation-based sensitivity model. Everything else — the DynISF formula, the 8-tier SMB decision tree, TDD selection, exercise handling — is inherited from V3.

**Historical (no longer possible):** v4.2 was once selected as its own active APS plugin in Config Builder, appearing as a separate entry from Boost V3. It is now **retired and hidden** — it does not appear in the APS list and cannot be selected. Its ML hypo-risk model has been folded into the current **Boost V6** engine (see the [main README](../README.md)); the description below is kept for reference only.

### On-device ML hypo risk model

A LightGBM gradient-boosted decision tree model that predicts the probability of a hypoglycaemic event (2+ consecutive CGM readings below 70 mg/dL) in the next 4 hours.

The model uses 8 features available at decision time: current BG, total IOB, basal IOB, BG above target, BG trend direction, hour of day, insulin activity, and the algorithm's insulin requirement. It was trained on ~3 million decisions from 28 Nightscout users with a Leave-One-User-Out AUC of 0.68.

The model runs as a pure-Kotlin tree walker (50 trees, depth 4, ~148KB) with no native library dependencies. Inference takes <5ms per cycle.

**How it modifies dosing:**

The risk score (0.0–1.0) acts through two mechanisms:

1. **Graduated SMB scaling.** When risk exceeds 30%, the SMB is scaled down linearly. At 30% risk the SMB is unchanged; at 65% risk it is halved; at 100% risk it is suppressed. The scaling is applied after tier selection — the tier logic runs normally and the ML model only reduces the final delivery.

2. **Tier downgrade.** When risk exceeds 60%, tiers 3–6 (UAM Boost, UAM High Boost, Percent Scale, Acceleration) are blocked. The algorithm can still use tiers 1–2 and tier 7, but the aggressive boost tiers are suppressed.

The risk score and scale factor are logged to Nightscout via the `mlHypoRisk` and `mlRiskScale` fields in the device status.

### Deviation sensitivity

A real-time sensitivity model that measures how well insulin is actually working by analysing BG deviations over the past 8 hours. When enabled, it replaces the standard sensitivity ratio.

**What it controls:**
- Dosing ISF (variableSens) — adjusted after the DynISF log curve
- Basal rate — profile basal is multiplied by the ratio in determine_basal
- BG targets — min_bg, max_bg, and target_bg are shifted by the ratio

It is controlled by the **Use Autosens** toggle and bounded by the **Max autosens ratio** and **Min autosens ratio** settings, which are surfaced in the Boost DynISF settings screen.

**How it works:**

The model reads from the AAPS deviation data store over the past 8 hours. It filters to "clean" entries only — where there is no carb absorption active (COB < 1, not absorbing, not UAM). Positive deviations when BG < 80 are zeroed to prevent post-hypo rebounds from being counted as resistance. When clean entries are less than 50% of the window, zeros are added to dampen the signal.

The filtered deviations are sorted and the **median** is taken (robust to outliers). The ratio is then:

```
ratio = 1 + (medianDeviation / mean|BGI|)
```

The denominator — mean absolute BGI across the whole window — normalises by how much insulin effect there typically is. A ratio of 1.2 means insulin is 20% less effective than expected.

The ratio is applied to `variableSens` after the Chris Wilson DynISF log curve has been computed:

```
variableSens = 1800 / (TDD × ln((currentBG / 120) + 1))
variableSens /= ratio
```

This is a percentage adjustment on the DynISF output. At ratio 1.2, ISF is reduced by 17% from wherever DynISF placed it. The same ratio also adjusts basal and BG targets.

### Boost Overview V2

A dark-theme redesign of the Boost Overview screen with a hero BG ring, stat pills, chart cards, and a sensitivity panel showing the deviation ratio. Toggled via the **Use Boost Overview V2** preference.

### Key differences from V3

| | Boost V3 | Boost v4.2 |
|---|---|---|
| **ML hypo risk** | No | Yes — graduated SMB scaling + tier downgrade |
| **Deviation sensitivity** | Available but observation only | Active — replaces standard sensitivity ratio |
| **Boost Overview V2** | No | Yes |
| **Exercise recovery** | Internal target raise (no TT) | Internal target raise (no TT) |

---

## Boost Overview UI

The Boost Overview UI is a redesigned home screen that replaces the standard AAPS Overview when enabled. It is purpose-built for Boost, giving you immediate visibility of the algorithm's decisions without needing to navigate to the Boost tab or read log output.

### Enabling the Boost Overview UI

To enable the new UI, go to **Preferences → Overview → Use Boost Overview**. When this toggle is on, the HOME tab will display the Boost Overview instead of the standard AAPS Overview. Turning it off reverts to the standard layout. 

For the setting to take effect, restart the app.

### Layout

The screen is organised into four sections from top to bottom: status area, detail panels, graphs, and action buttons.

**Status area** — The top of the screen shows three elements side by side. On the left, pump reservoir level, battery, cannula age and sensor age. In the centre, a large BG bobble displaying your current glucose value with a colour-coded ring (green when in range, yellow when high, red when urgent high or low). A trend chevron on the right side of the bobble rotates to show the direction and speed of glucose change. On the right, the time since last reading and a loop status icon.

Below the bobble, a delta line shows the current rate of change and trend description (e.g. "-0.2 · stable").

**Detail panels — Row 1** shows four tappable panels: IOB, Boost Tier, DynISF, and Profile.

* **IOB** — Current insulin on board in units, coloured in the IOB theme colour. Tap to see the breakdown of bolus IOB and basal IOB.
* **Boost Tier** — The current Boost decision tier (e.g. "Regular oref1", "Percent Scale", "UAM Boost"), colour-coded by tier. Tap to see the full decision reason and delta acceleration value.
* **DynISF** — The current variable sensitivity value from the algorithm, displayed in your chosen units (mg/dL or mmol/L). Tap to see the full algorithm inputs: BG, weighted TDD, insulin divisor, and TDD history.
* **Profile** — Your active profile name and percentage. Tap to open the Profile Viewer. Long-press to open the Profile Switch dialog.

**Detail panels — Row 2** shows three tappable panels centred below: TDD, Target, and Exercise.

* **TDD** — The total daily dose used by the algorithm. This is sourced from Boost's own "Final TDD" calculation (which includes the weighted 8-hour blend and adjustment factor), not the simple 7-day average. Tap to see all TDD values: the algorithm's weighted TDD, the parsed Final TDD from Boost's debug output, the 7-day average, and the 24-hour total, along with the raw script debug text for verification.
* **Target** — Your current target BG in your chosen units. The value is coloured green when it matches your profile target, amber when the APS algorithm has adjusted it (e.g. due to sensitivity/resistance), and orange when a temporary target is active. Tap to open the Temp Target dialog.
* **Exercise** — The current Boost activity/exercise state. When Boost is active, this shows the exercise detection result: "INACTIVE - 140%" (inactivity detected, profile raised), "Active" (activity detected, profile lowered), or "Normal". When Boost itself is not running, it shows the reason: "Outside window" (outside Boost hours), or "Sleep-in" (sleep-in protection active). Tap to see the full state, profile percentage, and raw script debug output.

**Graphs** — A single card contains two graphs stacked vertically with a thin divider between them.

* **BG graph** (upper, larger) — Shows BG readings, predictions, treatments, temp basals, target line, and in-range shading, using the same data and overlays as the standard AAPS graph. Long-press to cycle the time range (6h → 12h → 18h → 24h → 6h). A chart menu button (top right) lets you toggle overlay layers. A scale button (top left) shows the current time range.
* **IOB graph** (lower, compact) — Shows IOB history as a stepped area chart with projected decay, sharing the same time axis as the BG graph. An "IOB" label is overlaid in the top-left corner.

Both graphs use subtle grid lines (20% opacity) to keep the data prominent without visual clutter.

A single tap on the upper graph brings up the Treatment History window.

**Action buttons** — Below the graphs, the standard AAPS action buttons are shown: Quick Wizard, Insulin, Carbs, Calculator, Treatment, Calibration, and CGM. Automation user action buttons appear in a row above these when configured. All buttons follow the same visibility rules and protection checks as the standard Overview.

### Data sourcing

The Boost Overview reads algorithm data directly from the last APS run result. For Boost-specific values that are not part of the standard AAPS data model (such as the Final TDD, exercise mode, and tier), the UI parses the `scriptDebug` output that Boost writes on each loop iteration. This means the panels always reflect the most recent algorithm decision. If Boost has not yet run (e.g. immediately after app start), panels will show placeholder values until the first loop completes.

---

## Dynamic ISF 

###Dynamic ISF in Boost Plugin

Dynamic ISF settings are located within the Boost and Boost V2 plugin preferences sub-screen.

### Settings

The following settings are available in the Dynamic ISF sub-screen:

* *Use TDD-based ISF* — Enable or disable TDD-based ISF calculation. When disabled, profile ISF is used directly. TDD data is required — falls back to profile ISF if data is incomplete.
* *Adjust Sensitivity* — Adjust sensitivity ratio using 24h TDD / 7D TDD, similar to Autosens. Recommended to start with this off.
* *DynISF normal target* — Reference BG target for the ISF calculation. Default: 99.
* *DynISF BG cap* — BG above this value is softened to reduce ISF aggressiveness at very high BG. Default: 210.
* *TDD adjustment factor (%)* — Scales the blended TDD value up or down before ISF calculation. This number is likely to need reducing.
* *BG impact on ISF ** — Controls how much of the BG-driven ISF adjustment is applied. At 100%, the full logarithmic scaling is used. At lower values, the ISF is dampened toward your profile value. 

###Dynamic ISF V2 in Boost2 Plugin

Dynamic ISF V2 settings are located within the Boost V2 preferences under the **Dynamic ISF V2 (TDD²-based)** sub-screen. Within this, there is a switch to enable or disable TDD-based ISF calculation. If disabled, your profile ISF will be used.

### Settings

The following settings are available in the Dynamic ISF V2 sub-screen:

* *Use TDD-based ISF* — Enable or disable TDD-based ISF calculation. When disabled, profile ISF is used directly. TDD data is required for V2 — falls back to profile ISF if data is incomplete.
* *Adjust Sensitivity* — Adjust sensitivity ratio using 24h TDD / 7D TDD, similar to Autosens. Recommended to start with this off.
* *DynISF normal target * — Reference BG target for the ISF calculation. Default: 99.
* *DynISF BG cap* — BG above this value is softened to reduce ISF aggressiveness at very high BG. Default: 210.
* *TDD adjustment factor (%)* — Scales the blended TDD value up or down before ISF calculation. **Start at 100%** and adjust from there. Do not carry over your V1 adjustment factor.

Note that the **BG impact on ISF** slider from V1 is not present in V2. The full BG-driven adjustment is always applied.

Traditional Autosens is deprecated in this code and sensitivityRatio is calculated using 'Eight hour weighted average TDD / 7-day average TDD', if the "Adjust Sensitivity" option is selected.

Boost V2 uses a similar version of DynamicISF for making predictions, however, unlike the hardcoded quanta for the different values of insulin peak, when free-peak is used, it scales between the highest and lowest values.

The ISF for dosing decisions within Boost V2 is slightly different to the prediction ISF. The calculation is intended to mimic the effects of higher insulin sensitivity at lower glucose levels, and runs as follows:

1. With COB and increasing deltas, use 75% of the predicted BG and 25% of the current BG.
2. If current BG is accelerating fast, BG is below 180 mg/dl (10 mmol/l) and eventual BG is higher than current, use 50% of both eventual and current BG.
3. If BG is above 180 mg/dl and almost flat (all deltas between -2 and +2), use 25% min predicted BG and 75% current BG.
4. If BG is increasing and delta acceleration is above 1%, or eventual BG is greater than current BG, use current BG.
5. If BG is not increasing, use minimum predicted BG.

In V2, the dosing ISF applies the full scaler ratio with no velocity dampening. This means the ISF used for dosing will always reflect the complete BG-driven adjustment.

---

## Night Mode

Night Mode is located within both the **Boost and Boost V2** preferences under the **Night Mode** sub-screen. This enables SMBs to be disabled overnight in certain circumstances. The settings are:

* *Enable Night Mode* — Master switch to enable or disable the feature.
* *BG Offset* — When Night Mode is enabled, this is the value above your target at which point SMBs will be re-enabled.
* *Start and end times* — Allow you to choose when this function is active.
* *Disable with COB* — Disables Night Mode if there are COB.
* *Disable with low temporary target* — If a low temp target has been set, SMBs can be enabled.

---

## Boost start and end times

The start and end times use a 24 hour clock. You will need to format this in an H:mm or HH:mm format (e.g. 7:00 or 07:00).

The end time can run over midnight, so you can set a start time of 07:00 and an end time of 02:00.

---

## Boost

You can use Boost and Boost V2 when announcing carbs or without announcing carbs. With COB there is an additional piece of bolusing code that operates for the first 40 mins of COB. If you prefer to manually bolus, it fully supports that with no other code.

It also has variable insulin percentage determined by the user, and while boost time is valid, the algorithm can bolus up to a maximum bolus defined by the user in preferences.

The intention of this code is to deliver an early, larger bolus when rises are detected to initiate UAM deviations and to allow the algorithm to be more aggressive. Other than Boost, it relies on oref1 adjusted to use the variable ISF function based on TDD.

All of the additional code outside of the standard SMB calculation requires a time period to be specified within which it is active. The default time settings disable the code. The time period is specified in hours using a 24 hour clock in the Boost and Boost V2 preferences section.

**COB:** ***Note: Boost and Boost V2 are not designed to be used with eCarbs. This may result in additional, unexpected bolusing. Do not use it.***

With Carbs on Board, Boost and Boost V2 have a 25 minute window to deliver the equivalent of a mealtime bolus and **are allowed to go higher than your Boost Bolus Cap**, up to `InsulinRequired / insulin required percent` calculated by the oref1 algorithm, taking carbs into account. In the following period up to 40 mins after the carbs are added, it can do additional larger boluses, as long as there is a delta > 5 and COB > 0. The max allowed is the greater of the Boost Bolus Cap or the "COB cap", which is calculated as `COB / Carb Ratio`.

During normal use, you should set your Boost Bolus Cap to be the max that Boost or Boost V2 delivers when Boost is enabled and no COB are entered.

Boost and Boost V2 outside the first 40 mins of COB, or with 0 COB, have six phases:

1. **Boost bolus (UAM Boost)**
2. **High Boost Bolus (UAM High Boost)**
3. **Percentage Scale**
4. **Acceleration Bolus**
5. **Enhanced oref1**
6. **Regular oref1**

### Boost bolus (UAM Boost)

When an initial rise is detected with a meal, but no announced COB, delta, short_avgDelta and long_avgDelta are used to trigger the early bolus (assuming IOB is below a user defined amount). The early bolus value is one hour of basal requirement and is based on the current period basal rate, unless this is smaller than "Insulin Required" when that is used instead. This only works between 80 mg/dl and 180 mg/dl.

The user defined Boost Scale Value can be used to increase the boost bolus if the user requires, however, users should be aware that this increases the risk of hypos when small rises occur.

Both Boost and Boost V2 use the percent scale value to increase the early bolus size.

If **Boost Scale Value** is less than 3, Boost is enabled.

The short and long average delta clauses disable boost once delta and the average deltas are aligned. There is a preferences setting (Boost Bolus Cap) that limits the maximum bolus that can be delivered by Boost outside of the standard max minutes of basal to limit SMB to for UAM limit.

### High Boost (UAM High Boost)

If glucose levels are above 180 mg/dl (10 mmol/l), and glucose acceleration is greater than 5%, a high boost is delivered. The bolus value is one hour of basal requirement and is based on the current period basal rate, unless this is smaller than "Insulin Required" when one hour of basal plus half the insulin required is used, divided by your "percentage of insulin required value", unless this value is more than insulin required, at which point that is used.

### Boost Percentage Scale

Boost Percentage Scale is a feature that allows Boost V2 to scale the SMB from a user entered multiple of insulin required at 108 mg/dl (6 mmol/l) to the user entered *Boost insulin required percent* at 180 mg/dl (10 mmol/l). It can be enabled via a switch in the preferences. It is only active when [Delta - Short Average Delta] is positive, meaning that it only happens when delta variation is accelerating.

### Acceleration Bolus

The acceleration bolus is used when glucose levels are rising very rapidly (more than 25%) when a dose that is scaled similar to the Percent Scale is used, with the scaling operating at half the rate of the "Boost Percentage Scale" option.

### Enhanced oref1

If none of the above conditions are met, standard SMB logic is used to size SMBs, with the insulin required PCT entered in preferences. This only works on positive deviations and, similar to the percent scale, when deltas are getting larger. Enhanced oref1 uses regular insulin sizing logic but can dose up to the Boost Bolus Cap.

### Regular oref1

Once you are outside the Boost hours, "max minutes of basal to limit SMB to for UAM" is enabled, and the dosing works in the same way as regular OpenAPSSMB.

With Boost and Percent Scale functions, the algorithm can set a 5x current basal rate in this run of the algorithm, with a cap of 2x insulin required, as per normal oref1. This is reassessed at each glucose point.

Enable Boost with High Temp Target is carried through. This allows Boost, Percent Scale and Enhanced oref1 to be disabled when a user sets a high temp target, while retaining SMBs.

Enhanced oref1 only fires when deltas are increasing above a rate of 0.5%. This reduces the amount of times it fires when glucose levels are higher, but still allows additional bolusing.

---

## Settings

The **Boost and Boost V2** settings share the following configuration. Note that the default settings are designed to disable most of the functions, and you will need to adjust them.

For a detailed walkthrough of how each setting affects dosing across the Boost tier system, see the **[Boost Tuning Guide](https://tim2000s.github.io/Boost-in-AAPS_3.4/boost_tuning_guide.html)**. The guide explains the relationship between settings with scenario-based examples.

To experiment with settings before applying them to your loop, use the **[Boost Simulator](https://tim2000s.github.io/Boost-in-AAPS_3.4/boost_simulator.html)**. The simulator models the full 8-tier decision tree and shows how each tier responds to your BG, delta, and IOB inputs. It can also connect to your Nightscout instance to replay real data.

### Settings screen layout

The settings screen is organised into expandable sections:

- **Default AAPS Settings** — Max basal, max IOB, autosens, temp target sensitivity adjustments
- **Boost Controls** — Insulin required %, bolus cap, percent scale factor, boost scale, Boost max IOB, active time window, percent scale and circadian ISF toggles
- **Dynamic ISF Controls** — Enable TDD-based ISF, adjust sensitivity, normal target, BG impact on ISF (V1 only), BG cap, TDD adjustment factor
- **Exercise Settings** — Parent section containing:
  - *Step Count Settings* — Activity/inactivity step thresholds, sleep-in detection, profile percentage adjustments
  - *Heart Rate Integration* — HR zone classification, HRmax/resting HR, stress detection
  - *Post-Exercise Recovery* — Recovery window, target BG, SMB reduction, minimum exercise duration
- **Night Mode** — Enable/disable, time window, BG offset, COB and low TT overrides
- **Safety Settings** — SMB enables (always, with COB, with TT, after carbs), UAM, SMB frequency and size limits, carbs request threshold, BG source and version check bypasses
- **Advanced Settings** — Safety multipliers, short delta preference, documentation links

* *Boost insulin required percent* — Defaults to 50%. Can be increased, but increasing increases hypo risk.
* *Boost Scale Value* — Defaults to 1.0. Only increase multiplier once you have trialled.
* *Boost Bolus Cap* — Defaults to 0.1.
* *Percent scale factor* — Defaults to 200.
* *UAM Boost max IOB* — Defaults to 0.1.
* *UAM Boost Start Time (24 hour clock)* — Needs to be set using H:mm or HH:mm format, e.g. 7:00 or 07:00. Defaults to 7:00.
* *UAM Boost End Time (24 hour clock)* — Needs to be set using H:mm or HH:mm format, e.g. 7:00 or 07:00. Defaults to 8:00.

**Notes on settings**

The settings with the largest effect on post prandial outcomes are *Boost insulin required percent* and *Percent Scale Factor*, alongside your usual SMBMinutes settings.

*Boost insulin required percent* — Under normal AAPS, percentage of insulin required to be given as SMB is hardcoded to 50%. This setting allows you to tell the accelerated dosing features to give a higher percentage of the insulin required.

*Percent scale factor* — This is the max amount that the Boost and Percent Scale functions can multiply the insulin required by at lower glucose levels. A larger number here leads to more insulin.

*SMBMinutes settings* — When there is no longer any acceleration in glucose delta values, the algorithm reverts to standard oref1 code and uses SMBminutes values as its max SMB size. When using Boost or Boost V2 these values should generally be set to less than the default 30 mins. A max of 15 or 20 is usually best.

**Recommended Settings**

Start with the same settings as Boost V1. Because the V2 formula amplifies TDD changes, you may find V2 doses more aggressively on days with higher TDD and less aggressively on lower TDD days. Monitor closely and adjust as needed.

* *TDD adjustment factor* — **Start at 100%**. This is the most important setting to get right first. Increase if V2 is under-dosing, decrease if over-dosing. Small changes (5–10%) have a meaningful effect due to the squared TDD term.
* *Boost Bolus Cap* — Start at 2.5% of TDD and increase to no more than 15% of 7 day average total daily dose.
* *Percent scale factor* — Once you are familiar with the percentage scale factor, the values can be increased up to 500% with associated increase in hypo risk with rises that are not linked to food.
* *UAM Boost max IOB* — Start at 5% of TDD and be aware that max IOB is a safety feature, and higher values create greater risk of hypo.
* *Max Minutes of basal to limit SMB to* — 15 mins. This controls the maximum SMB size when Boost is not active. 15 mins is recommended; higher values allow larger SMBs outside Boost hours.
* *Max minutes of basal to limit SMB to for UAM* — 20 mins. This is only used overnight when IOB is large enough to trigger UAM, so it doesn't need to be a large value.
* *Boost insulin required percent* — Recommended not to exceed 75%. Start at 50% and increase as necessary.
* *Target* — Set a target of 120 mg/dl (6.5 mmol/l) to get started with Boost or Boost V2. This provides a cushion as you adjust settings. Values below 100 mg/dl (5.5 mmol/l) are not recommended.

---

## Post-Exercise Recovery Settings

Located in the **Post-Exercise Recovery** sub-screen within Boost and Boost V2 preferences.

* *Enable Post-Exercise Recovery* — Master switch. When off, no recovery TempTarget or SMB reduction is applied.
* *Recovery window (hours)* — How long the recovery window lasts after exercise ends. Default: 2 hours. Range: 0.5–8 hours. When HR integration is enabled, this is used as the baseline and multiplied per exercise type.
* *Recovery target BG* — The TempTarget BG inserted at the end of exercise. Default: 8.0 mmol/L / 144 mg/dL. Enter in your current display units.
* *SMB reduction factor* — How much to scale down `boost_bolus` and `boost_scale` during recovery. Default: 0.5 (50%). A value of 1.0 disables the internal SMB reduction while keeping the TempTarget.
* *Minimum exercise duration (minutes)* — Exercise shorter than this will not trigger recovery. Default: 10 minutes. Prevents false triggers from brief step bursts.

---

## Heart Rate Integration Settings

Located in the **Heart Rate Integration** sub-screen within Boost and Boost V2 preferences.

Requires a Wear OS or Garmin watch paired with AAPS that is recording heart rate data.

* *Enable HR Integration* — Master switch. Default: off. When disabled, all exercise detection falls back to step counts only.
* *HRmax (BPM)* — Your maximum heart rate for Karvonen zone calculation. Default: 180. Use 220 − your age as a starting estimate, or a measured value from a maximal effort test.
* *Resting HR (BPM)* — Your resting heart rate (measured first thing in the morning). Default: 60.
* *HR averaging window (minutes)* — How many minutes of HR history to average before classifying the zone. Default: 15. Shorter values are more responsive; longer values are more stable.
* *Enable stress detection* — When enabled, elevated HR without movement (zone 2–3, near-zero steps) raises the target BG to protect against cortisol-driven insulin resistance. Off by default. Not recommended unless you have a clear use case, as it has a low confidence signal.

---

## Stepcount Features

The three stepcount features are located in both the **Boost and Boost V2** preferences under the **Step Count Settings** sub-screen:

1. **Inactivity Detection** — Determines when the stepcount is below a user defined limit over the previous hour, and increases basal and DynamicISF adjustment factor by a user defined percentage. The defaults are 400 steps and increase to 130%. Inactivity detection does not work when Sleep-in protection is active.

2. **Sleep-in Protection** — Checks stepcount for a user defined period (in hours) after the Boost start time, and if it is below a user defined threshold, extends the time during which Boost and Percent Scale are disabled. The defaults are 2 hours and 250 steps. The maximum value for this is 18 hours. Inactivity detection doesn't work while sleep-in is active.

3. **Activity Detection** — Allows a user to set the number of steps in the past 5 mins, 30 mins and hour as triggers for activity. If any of these are true, it will set a user defined lower percentage, to reduce basal and DynamicISF adjustment factor. For the five minute setting, it will wait for 15 mins to revert to non-activity. The other two settings wait for the value for the period to drop below the threshold. The defaults are 420 steps for 5 mins (which corresponds to the 5 minute activity trigger on a Garmin), 1200 for 30 mins and 1800 for 60 mins. Profile decrease is set to 80%.

Both activity detection settings are overridden by a percentage profile switch.

There are no enable/disable buttons for these settings, however, in both activity detection settings, *if the % value is set to 100, they have no effect*. Similarly, *if the Sleep-in protection hours are set to 0, it has no effect*.

---

## BG Source Compatibility **WARNING - SAFETY RISK**

There is a setting in both the **Boost and Boost V2** preferences called **"Allow all BG sources for SMBs"**. This switch allows SMBs always, regardless of BG source, across both plugins. If you are using a Libre sensor or any other source that does not natively support advanced filtering, you will need to enable this setting. Please make sure you are using a sensor collection app that is providing glucose data every five minutes, and enable at least the Average Smoothing plugin.

---

## Running V1 and V2 side by side

**Historical (no longer possible):** Boost V2 was once registered as a separate, selectable plugin in AAPS, and you could switch between Boost and Boost V2 in the Config Builder. Boost V2 is now **retired and hidden** — it no longer appears in the APS list, so only **Boost** (base) and **Boost V6** can be selected. The comparison notes below are kept for historical reference.

> ⚠️ **Do not use Boost V2 for live dosing.** It is currently available for parallel observation only — run it on a development or secondary phone alongside Boost to compare log outputs. Do not make it your active plugin until it has been explicitly cleared for live use.

The standalone DynISF V2 plugin can also be used independently with OpenAPSSMB if you want the updated formula without the Boost tier system.

---

<img src="https://cdn.iconscout.com/icon/free/png-256/bitcoin-384-920569.png" srcset="https://cdn.iconscout.com/icon/free/png-512/bitcoin-384-920569.png 2x" alt="Bitcoin Icon" width="100">

3KawK8aQe48478s6fxJ8Ms6VTWkwjgr9f2
