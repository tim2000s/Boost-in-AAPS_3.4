# AndroidAPS - Boost V2

* Check the wiki: https://wiki.aaps.app
* Everyone who's been looping with AndroidAPS needs to fill out the form after 3 days of looping https://docs.google.com/forms/d/14KcMjlINPMJHVt28MDRupa4sz4DDIooI4SrW0P3HSN8/viewform?c=0&w=1

[![Support Server](https://img.shields.io/discord/629952586895851530.svg?label=Discord&logo=Discord&colorB=7289da&style=for-the-badge)](https://discord.gg/4fQUWHZ4Mw)

***Boost V2 based on AAPS 3.4.0.0***

Boost V2 is a variant of the Boost plugin that uses **Chris Wilson's DynISF V2 formula** for ISF calculation. It can be installed alongside the original Boost plugin so that you can compare outputs before switching.

All Boost-specific settings, including Dynamic ISF V2, Night Mode, and Step Counting, are consolidated within the Boost V2 preferences screen as sub-screens.

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
| **Scaling** | BG impact slider (0–200%) | Fixed 0.02 multiplier |
| **BG impact dampening** | User-adjustable | None — always full effect |
| **TDD sensitivity** | 10% TDD change ≈ 10% ISF change | 10% TDD change ≈ 21% ISF change |

### Important: TDD sensitivity

Because TDD is squared in the V2 formula, ISF is **much more responsive to TDD changes** than in V1. A 10% increase in TDD produces roughly a 21% decrease in ISF (more aggressive dosing). This means:

* V2 will self-adjust more aggressively as your TDD changes day to day.
* It is strongly recommended to **log-compare V1 and V2 output side by side** before running V2 live.
* TDD data is mandatory for V2. If TDD data is incomplete, V2 falls back to your profile ISF.

---

## Dynamic ISF V2

Dynamic ISF V2 settings are located within the Boost V2 preferences under the **Dynamic ISF V2 (TDD²-based)** sub-screen. Within this, there is a switch to enable or disable TDD-based ISF calculation. If disabled, your profile ISF will be used.

The following settings are available in the Dynamic ISF V2 sub-screen:

* *Use TDD-based ISF* — Enable or disable TDD-based ISF calculation. When disabled, profile ISF is used directly. TDD data is required for V2 — falls back to profile ISF if data is incomplete.
* *Adjust Sensitivity* — Adjust sensitivity ratio using 24h TDD / 7D TDD, similar to Autosens. Recommended to start with this off.
* *DynISF normal target (mg/dl)* — Reference BG target for the ISF calculation. Default: 99.
* *DynISF BG cap* — BG above this value is softened to reduce ISF aggressiveness at very high BG. Default: 210.
* *TDD adjustment factor (%)* — Scales the blended TDD value up or down before ISF calculation. Default: 100.

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

Sensitivity raises target and resistance lowers target are always enabled in Boost V2 and are not user-configurable.

---

## Night Mode

Night Mode is located within the Boost V2 preferences under the **Night Mode** sub-screen. This enables SMBs to be disabled overnight in certain circumstances. The settings are:

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

You can use Boost V2 when announcing carbs or without announcing carbs. With COB there is an additional piece of bolusing code that operates for the first 40 mins of COB. If you prefer to manually bolus, it fully supports that with no other code.

It also has variable insulin percentage determined by the user, and while boost time is valid, the algorithm can bolus up to a maximum bolus defined by the user in preferences.

The intention of this code is to deliver an early, larger bolus when rises are detected to initiate UAM deviations and to allow the algorithm to be more aggressive. Other than Boost, it relies on oref1 adjusted to use the variable ISF function based on TDD.

All of the additional code outside of the standard SMB calculation requires a time period to be specified within which it is active. The default time settings disable the code. The time period is specified in hours using a 24 hour clock in the Boost V2 preferences section.

**COB:** ***Note: Boost V2 is not designed to be used with eCarbs. This may result in additional, unexpected bolusing. Do not use it.***

With Carbs on Board, Boost V2 has a 25 minute window to deliver the equivalent of a mealtime bolus and **is allowed to go higher than your Boost Bolus Cap**, up to `InsulinRequired / insulin required percent` calculated by the oref1 algorithm, taking carbs into account. In the following period up to 40 mins after the carbs are added, it can do additional larger boluses, as long as there is a delta > 5 and COB > 0. The max allowed is the greater of the Boost Bolus Cap or the "COB cap", which is calculated as `COB / Carb Ratio`.

During normal use, you should set your Boost Bolus Cap to be the max that Boost V2 delivers when Boost is enabled and no COB are entered.

Boost V2 outside the first 40 mins of COB, or with 0 COB, has six phases:

1. **Boost bolus (UAM Boost)**
2. **High Boost Bolus (UAM High Boost)**
3. **Percentage Scale**
4. **Acceleration Bolus**
5. **Enhanced oref1**
6. **Regular oref1**

### Boost bolus (UAM Boost)

When an initial rise is detected with a meal, but no announced COB, delta, short_avgDelta and long_avgDelta are used to trigger the early bolus (assuming IOB is below a user defined amount). The early bolus value is one hour of basal requirement and is based on the current period basal rate, unless this is smaller than "Insulin Required" when that is used instead. This only works between 80 mg/dl and 180 mg/dl.

The user defined Boost Scale Value can be used to increase the boost bolus if the user requires, however, users should be aware that this increases the risk of hypos when small rises occur.

Boost V2 also uses the percent scale value to increase the early bolus size.

If **Boost Scale Value** is less than 3, Boost is enabled.

The short and long average delta clauses disable boost once delta and the average deltas are aligned. There is a preferences setting (Boost Bolus Cap) that limits the maximum bolus that can be delivered by Boost outside of the standard UAMSMBBasalMinutes limit.

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

The **BOOST V2** settings have a number of extra items. Note that the default settings are designed to disable most of the functions, and you will need to adjust them.

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

*SMBMinutes settings* — When there is no longer any acceleration in glucose delta values, the algorithm reverts to standard oref1 code and uses SMBminutes values as its max SMB size. When using Boost V2 these values should generally be set to less than the default 30 mins. A max of 15 or 20 is usually best.

**Recommended Settings**

Start with the same settings as Boost V1. Because the V2 formula amplifies TDD changes, you may find V2 doses more aggressively on days with higher TDD and less aggressively on lower TDD days. Monitor closely and adjust as needed.

* *Boost Bolus Cap* — Start at 2.5% of TDD and increase to no more than 15% of 7 day average total daily dose.
* *Percent scale factor* — Once you are familiar with the percentage scale factor, the values can be increased up to 500% with associated increase in hypo risk with rises that are not linked to food.
* *UAM Boost max IOB* — Start at 5% of TDD and be aware that max IOB is a safety feature, and higher values create greater risk of hypo.
* *UAMSMBBasalMinutes* — 20 mins. This is only used overnight when IOB is large enough to trigger UAM, so it doesn't need to be a large value.
* *Boost insulin required percent* — Recommended not to exceed 75%. Start at 50% and increase as necessary.
* *Target* — Set a target of 120 mg/dl (6.5 mmol/l) to get started with Boost V2. This provides a cushion as you adjust settings. Values below 100 mg/dl (5.5 mmol/l) are not recommended.

---

## Stepcount Features

The three stepcount features are located in the Boost V2 preferences under the **Step Count Settings** sub-screen:

1. **Inactivity Detection** — Determines when the stepcount is below a user defined limit over the previous hour, and increases basal and DynamicISF adjustment factor by a user defined percentage. The defaults are 400 steps and increase to 130%. Inactivity detection does not work when Sleep-in protection is active.

2. **Sleep-in Protection** — Checks stepcount for a user defined period (in hours) after the Boost start time, and if it is below a user defined threshold, extends the time during which Boost and Percent Scale are disabled. The defaults are 2 hours and 250 steps. The maximum value for this is 18 hours. Inactivity detection doesn't work while sleep-in is active.

3. **Activity Detection** — Allows a user to set the number of steps in the past 5 mins, 30 mins and hour as triggers for activity. If any of these are true, it will set a user defined lower percentage, to reduce basal and DynamicISF adjustment factor. For the five minute setting, it will wait for 15 mins to revert to non-activity. The other two settings wait for the value for the period to drop below the threshold. The defaults are 420 steps for 5 mins (which corresponds to the 5 minute activity trigger on a Garmin), 1200 for 30 mins and 1800 for 60 mins. Profile decrease is set to 80%.

Both activity detection settings are overridden by a percentage profile switch.

There are no enable/disable buttons for these settings, however, in both activity detection settings, *if the % value is set to 100, they have no effect*. Similarly, *if the Sleep-in protection hours are set to 0, it has no effect*.

---

## BG Source Compatibility **WARNING - SAFETY RISK**

There is a setting in the Boost V2 preferences called **"Allow all BG sources for SMBs"**. This switch allows SMBs always, regardless of BG source, across the Boost V2 plugin. If you are using a Libre sensor or any other source that does not natively support advanced filtering, you will need to enable this setting. Please make sure you are using a sensor collection app that is providing glucose data every five minutes, and enable at least the Average Smoothing plugin.

---

## Running V1 and V2 side by side

Boost V2 is registered as a separate plugin in AAPS. You can switch between Boost and Boost V2 in the Config Builder. Only one can be active at a time, but both are available for selection. It is recommended to compare log outputs from both plugins before committing to V2 for live use.

---

<img src="https://cdn.iconscout.com/icon/free/png-256/bitcoin-384-920569.png" srcset="https://cdn.iconscout.com/icon/free/png-512/bitcoin-384-920569.png 2x" alt="Bitcoin Icon" width="100">

3KawK8aQe48478s6fxJ8Ms6VTWkwjgr9f2
