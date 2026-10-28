# Boost V6 — acute-activity insulin withdrawal: specification

*2026-07-19. The dose-then-walk lows are activity-driven (steps AUC 0.62 vs glucose+insulin 0.55) and
V6 currently DETECTS but does not ACT on the steps (wouldDeltaIsfPct is shadow-only). This specs a real
protection: withdraw insulin when activity lands with insulin on board. INSULIN-REDUCING → the safe
direction, so far lower-risk than the add-insulin levers that all died on their safety anchors.*

## 1. What it does
When brisk activity is detected (steps) AND there is insulin on board, **zero-temp the basal + suppress
the V6 SMB + hold the target up** for the activity window — stop feeding insulin into a walk. It cannot
undo IOB already delivered, but it stops the loop making the walk-low worse and removes near-term basal.

## 2. Trigger (per cycle) — ALL must hold
- `steps_5m ≥ STEP_ONSET_5M` (brisk pace; auto-config per-user from the step distribution, ≈100) OR
  `steps_30m ≥ STEP_SUSTAINED_30M` (a sustained walk).
- `IOB ≥ IOB_MIN` (≈0.5U — something to withdraw; no IOB = no walk-low risk).
- Not already in a rescue/treatment window.

## 3. Action
- **Zero-temp** (basal → 0) for `ACTIVITY_WINDOW` (≈30 min), RE-armed each cycle while activity
  continues, released `ACTIVITY_BUFFER` (≈15 min) after steps subside.
- **Suppress the V6 SMB** this cycle (the override delivers 0).
- (Optional, phase 2) raise the target like oref exercise mode.

## 4. Auto-config (per-user)
`STEP_ONSET_5M` = the user's brisk-walk threshold (a high percentile of their nonzero steps_5m). The
activity→forward-hypo relationship is per-user, not cross-user (register). Enable by default for all
users (insulin-reducing = safety); the threshold personalises the sensitivity.

## 5. User override — `BooleanKey.ApsBoostV5ActivityWithdrawal`
Force ON/OFF and tune the aggressiveness (threshold, window). Default = auto-config-derived. Because
it only ever WITHHOLDS insulin, the override carries far less risk than the add-insulin overrides.

## 6. Safety
The direction IS the safety (withholding prevents lows). The only cost is HIGHS if the walk wasn't going
to cause a low. So the guard is on OVER-withdrawal, not lows: cap the total withheld per window, and
don't withdraw if BG is already high-and-rising with no recent activity trend (not a walk). Absolute
floors are unaffected (they already prevent lows; this adds to them).

## 7. Telemetry + shipping (shadow-first, two-test bar)
Shadow: log `activityWithdraw=trig,wouldWithholdU,steps5m,iob,bg,window;` — deliver nothing, bank the
would-withhold. Price on-device: of the cycles it would fire, did a low follow (it should); of the
non-firing activity, did lows slip through (missed). Then active — but the reduce-on-activity direction
is well-established (oref exercise mode, autosens), so the bar is lower than any add-insulin lever.

## 8. Honest caveats
Steps predict the low at AUC ~0.62 — this helps materially, not completely. It is REACTIVE (the walk
must start); pairing with the habitual-time prior (register: fires ~55 min ahead, AUC 0.85) makes it
anticipatory. It cannot undo IOB already on board — it prevents the loop WORSENING the walk-low and
trims near-term basal. Natural home: the KAIROS idea-4 withdrawal path, triggered by activity onset
(not the Twin lo30, which failed for these lows).
```
Config: ApsBoostV5ActivityWithdrawal (override) · STEP_ONSET_5M≈100 · STEP_SUSTAINED_30M≈400 ·
        IOB_MIN≈0.5U · ACTIVITY_WINDOW≈30min · ACTIVITY_BUFFER≈15min
```
