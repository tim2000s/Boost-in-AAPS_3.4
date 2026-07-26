# Composed post-rescue rebound guard — pricing report (2026-07-23)

## Incident

User H (V6-ACTIVE, mmol), 2026-07-23, verified from NS devicestatus. Twice in one
afternoon: hypo (3.7 mmol/L) → unannounced rescue carbs → rebound deltas 8–10 mg/dL/5min
→ state machine confirms a "meal" → Enhanced oref1 fires multi-unit SMBs into the
recovery (3.55U at BG 97 mg/dL, 25 min after a 67 low; 6.7U SMB total in 25 min) →
IOB peaks 6.0U against a 134 peak → second insulin-driven hypo → same replay on the
second rescue (2.4U at BG 100) → user set OpenAPS Offline (indefinite) at 13:49 local.

## Mechanism (code-verified)

1. The v4.4.4 Fix A v2 post-rescue tier block correctly demotes T3/T4/T5 — cycles fall
   through to T7 (Enhanced oref1) / T8 (Regular oref1).
2. **T7/T8 apply no fast-carb scaling** — `fastCarbScale` is only multiplied in inside
   T3/T5/T6. Tier demotion does not restrain the dose when the demoted-to tier is uncapped.
3. The delta-weighted dynamic ISF collapses under rebound deltas (19.8 vs ~50 daily),
   inflating insulinReq — so the demoted tier's dose is large, not small.
4. The `fastCarbRebound` trigger requires `delta_accl > 25`, which plateaus mid-rebound
   exactly when the big deltas arrive — so even the in-tier scaling had lapsed.
5. The V6 post-rescue meal-state cap (2026-07-04) caps CONFIRMED/COMMITTED to "V1's
   hypo-restrained dose" — but per (2)-(4) V1's dose was not restrained (capped 4.0→3.55U).
   The cap's load-bearing alignment assumption fails on exactly this path.

## Proposed change

Apply the graduated scale s(bg) (0.3 below 120 mg/dL, linear to 1.0 at 170) to the
**final microBolus after tier selection**, whenever the post-rescue window
(45-min rolling min BG < 75) is active, COB == 0, and bg < 170 — independent of tier and
of the delta_accl trigger, skipping cycles the in-tier scaling already handled. No
velocity/eventualBG escape inside the window (delta > 10 during a post-rescue rebound is
the rescue-carb signature — same contamination argument as the v4.4.3 Fix D gating).
Propagates through the V6 layer automatically because the plugin's `v1WouldDose` is the
V1 engine's final microBolus.

## Pricing (price_composed_guard.py, DB refreshed to 2026-07-23T12:18Z)

Universe: 102,976 dosing cycles, 9 users, Feb–Jul 2026. Derived window validated against
the live `boostv5_postrescuewindow` flag where present: 98.75% agreement.

- **Exposure**: 8,255 affected dosing cycles (8.0%); 2,332U removed of 3,669U delivered
  in affected cycles (64%). Tier split: ~35% T7/T8 explicit, 57% tier-unparsed (v1-silent
  era rows), 8% T3/T5/T6 where the in-tier trigger had lapsed.
- **Benefit**: 2,913 episodes; 33% followed by a second low <70 within 3h.
  **34% of removed insulin sits directly ahead of a second low — bootstrap 95% CI [32%, 37%]**.
  Benchmarks: 27% shipped the 07-04 cap; every other lever priced 14–19%.
  Excluding user G (Trio-shadow, hypothetical doses): 36% [33%, 38%].
  Second-low nadir median 57 mg/dL.
- **Cost**: 9% of episodes were genuine post-hypo meals (>180 for >60 min after window
  expiry); median under-delivery 0.80U, max 4.4U. With full dosing today those episodes
  still peaked at median 240 mg/dL and 11% still ended in a second low — full dosing was
  not containing them.
- **Velocity-override variant**: keeping the delta>10 escape in-window drops removed
  insulin to 1,848U at a nearly identical benefit share (35%) — but in the user-H replay
  the escape exempts the BG-119/127 chase shots. Gated (no escape) is the shipped variant.
- **User-H incident replay**: 9.90U delivered across the two episodes → **3.05U** under
  the composed guard (4.41U had the escape been kept).

## Verdict

SHIP-quality by the same standard as the 07-04 cap (which shipped at 27% benefit /
0.15U median cost). Confidence: **SOLID** for the benefit share (full-history,
CI-backed, matched to the established lever-pricing framework); the usual caveat
applies — no glucodynamic counterfactual, "ahead of a second low" is the validated
proxy, not an outcome simulation. Restraint-only change: it can only remove insulin,
never add.

## Limitations

- 57% of affected cycles are v1-silent rows where tier is unparsed; their "delivered"
  is v1_units (the delivered SMB on V1-acting builds), but tier-level already-scaled
  detection is blind there — removal is slightly over-counted if any had in-tier scaling.
- Approximated smoothed delta from CGM for the velocity-override variant.
- Leave-one-user-out on the headline share (measured): dropping any single user leaves
  33–37%, EXCEPT dropping D → 27.2%, below the pooled CI lower bound. D (highest hypo
  burden in the cohort) genuinely carries part of the benefit; the worst-case floor
  (27%) still equals the level that shipped the 07-04 cap.
