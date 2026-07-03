# Release Notes — Boost 3.4.2.1

Based on upstream AndroidAPS 3.4.2.1 (Nightscout release).

## Algorithm Enhancements

### Graduated Fast-Carb Rebound Protection
Fast-carb protection is now proportional rather than binary. When a post-hypo rebound is detected, Tiers 3/5/6 scale their SMB output based on current BG instead of being fully blocked:
- BG below 120 mg/dL: 30% of tier output (strong suppression near target)
- BG 120-170 mg/dL: linear ramp from 30% to 100%
- BG above 170 mg/dL: no suppression
- **Velocity override**: delta > 15 mg/dL/5min with BG > target+20 releases protection immediately

### Spike Override Cap
When Tier 8 (regular oref1) fires during a confirmed spike (BG > 180, delta > 5, insulinReq > 3x the basal-derived cap), the SMB ceiling is raised from `maxBolus` to `boost_max`. This prevents rate-limiting during genuine spikes where the basal-derived cap is structurally too small.

### Delta Acceleration Floor
The `delta_accl` denominator is now floored at 2.0 mg/dL/5min, preventing artificial amplification when `shortAvgDelta` is near zero. Previously, BG flattening from -0.3 to 0.0 could produce delta_accl of 100%, triggering aggressive Tier 4 on flat BG.

### Auto-Cancel Recovery TempTarget on Hypo Rebound
When a hypo is detected (recentLowBG < 100) and BG is rising, any active ACTIVITY-reason TempTarget is automatically cancelled. This prevents the post-exercise recovery target from blocking Boost during a genuine hypo rebound.

### ISF Correction for Profile Switch
ISF now correctly scales inversely with profile switch percentage: 80% profile produces 125% ISF (less aggressive). Previously the scaling was in the wrong direction.

## Exercise Management

### 15-Minute Step Detection
A dedicated 15-minute step threshold (`ApsBoostActivitySteps15`, default 800) enables exercise detection within 15 minutes instead of waiting for the 30-minute window.

### 15-Minute Loop Suspension
A 15-minute option is now available in the loop suspension dialog alongside 1h/2h/3h/10h.

### Dedicated HR/Steps Graph
Heart rate and step count data are displayed on a separate third graph in the Boost Overview, independent of the IOB graph.

## User Interface

### Restructured Settings
The Boost and Boost V2 settings screens are reorganised into expandable sections:
- Default AAPS Settings
- Boost Controls
- Dynamic ISF Controls
- Exercise Settings (Step Count / Heart Rate / Post-Exercise Recovery)
- Night Mode
- Safety Settings
- Advanced Settings

### Reservoir Colour
The pump reservoir level in the Boost Overview now changes colour at warning/critical thresholds, matching the standard AAPS behaviour.

## Documentation

### Simulator & Tuning Guide Links
Links to the [Boost Tuning Guide](https://tim2000s.github.io/Boost-in-AAPS_3.4/boost_tuning_guide.html) and [Boost Simulator](https://tim2000s.github.io/Boost-in-AAPS_3.4/boost_simulator.html) are added to the README header and Settings section.

### Simulator Updates
The simulator now models graduated fast-carb protection (BG-proportional scaling) and the spike override cap.

## Upstream (AndroidAPS 3.4.2.1)
- Equil pump: fix activation wizard and progress dialog
- Medtrum: prevent re-use of wrong patch during activation
- Tidepool: fix session handling
- Omnipod Dash: BLE driver interface refactoring
- Romanian translations
