# V6 vs V1 dosing forensic — why V6's meal window loses tight-range, and how to fix it

*2026-07-19. Four parallel analyses (`f1`–`f4`) over the transition window (18 Jun–12 Jul, 5 users
with V1 sleep telemetry, meal-dosing-active cycles only, seasonality held). Same-cycle dosing +
matched-state + meal-onset-aligned trajectories.*

## The question
Outcome analysis found V6's meal-dosing window has −7.5 TING vs the previous Boost gen (V1),
season-controlled, all 5 users. Why — and how to improve?

## What each forensic showed
- **f1 (decomposition):** V6's genuine dose divergence over V1 concentrates in **CONFIRMED** state
  (+0.135U/cyc, ~all the net excess; shots avg ~1.98U) and **fast-rise** (+0.043U); it **restrains at
  high IOB** (−0.010U). Amplification is aggression/velocity, survives caps+brakes.
- **f2 (matched-state forward):** at matched pre-state (BG×trend×IOB), V6 and V1 forward trajectories
  are **near-identical** — forward BG range Δ+0.3, swing Δ+0.9, **<70 Δ−1.0 (V6 fewer lows)**, only
  **>180 Δ+3.4 (V6 slightly more highs)**. V6 doses **slightly LESS per matched state** (−0.03U). ⇒
  the "+11% more insulin" (unmatched) is a **state-distribution artifact**, not per-state aggression;
  V6 is if anything more conservative per state. NOT a variance/overshoot story.
- **f3 (shots):** V6 shots crash <70 at ~14–17% regardless of over-dosing; worst contexts BG<150
  (17%) and CONFIRMED (17%, 1.98U). **No V1 shot-crash baseline** → can't call V6's shots worse.
- **f4 (meal-onset-aligned, the tiebreaker):** meals **rise identically** (onset ~146, peak ~170 at
  +25min for both) but **V6 UNDER-RECOVERS**: post-peak it plateaus at 143–150 while V1 returns to
  132. **BG@+180: V6 143 vs V1 132.** Per-user peaks similar (Δ −8..+9) → it is the descent, not the
  peak.

## Mechanism (resolved)
**V6's high-IOB brake over-suppresses the post-meal RECOVERY.** After the peak, IOB is high and
glucose is descending through 150→145; V1 keeps making small corrections that nudge it into tight
range (132); V6's composed brake / high-IOB restraint shuts those corrections off, leaving a
**mild-high plateau (143–150) for hours** = the lost TING. Consistent with everything: lows unchanged
(f2 −1%), variance unchanged (f2), doses less per state (f2), the register's brake trade-off, and the
phase-3 brake-compounding note ([[phase3-brake-compounding]]).

My earlier "V6 adds variance" reading was **wrong** — corrected to under-recovery.

## How to improve (data-grounded, but in the danger zone)
Let V6 keep V1's small post-meal recovery corrections in the **140–160, descending, IOB-present**
window instead of braking them off. **Crucially the data shows this is achievable low-safely: V1
reaches 132 at the SAME (actually lower) low rate as V6's 143** — so the tight-range is recoverable
without paying in lows. This is the exact context the register says feeds lows
([[recovering-highs-smb-rejected-2026-07-03]]), so it MUST be shadow-first — but V1's own recovery
behaviour is a proven-safe target to aim at, which the earlier rejected RECOVERING-SMB levers lacked.

Natural discriminator: the KAIROS Twin's calibrated 30-min floor (`lo30`) — keep correcting the 145
plateau when `lo30` says no low is coming; withdraw when it does. Ties the recovery fix to the one
Twin signal that survived its gates.

## Caveats
5/7 users (H,E lack V1 sleep telemetry); within-window V1/V6 split is a flash-date (≤~2wk internal
gap; anything changed at the flash rides along); meal-onset detection is a CGM proxy; C has only 7 V6
onsets. The mechanism is consistent across f1–f4 but the magnitude carries these confounds.

---

## Follow-up (velocity challenge) — the fix is the velocity gate, not the descent brake

**f5 (descent, same-cycle + meal-aligned):** the plateau is NOT set by a harsher V6 descent brake.
Same-cycle, in the descent (falling, IOB>1.5), V6's dose == V1's would-dose in every BG band (%V6<V1
= 0–2%). But meal-aligned (transition window), V1 delivers **+0.77U MORE in the descent (t30–90)**
while V6 front-loads **+0.31U MORE on the rise (t0–30)**, and V6 delivers LESS total (4.10 vs 4.57U).

**f6/f7 (front-load trade, velocity-gated):** binning on PEAK (an outcome/collider) manufactured a
front-load→lower-plateau benefit; gating on the pre-dose signal (velocity/accel at onset) it
collapses — front-load only lowers the plateau on genuinely steep rises (>45 mg/dL/15min ≈ 90/30min);
on modest rises it does not lower the plateau and adds crashes (flat rises crash 23%).

**Resolved mechanism:** V6 over-front-loads MODEST rises → builds IOB → the (correct, both-algorithm)
high-IOB reduction then suppresses the descent correction → less total meal insulin, higher plateau
(143–150 vs V1's 132) → the −7.5 TING. The extra front-load doesn't even lower the peak (V1 reaches
the same peak with less). Root cause = the velocity gate is mistuned.

**THE FIX (existing constants, `velocityScaledDoseFactor` in DetermineBasalBoostV5.kt):**
current `VELOCITY_RISE_HI=50, VELOCITY_SCALE_FLOOR=0.40` gives FULL front-load at 50/30min (≈25/15min,
the no-benefit/crash band) and a 0.40 floor on flat rises. Retune **RISE_HI 50→90, FLOOR 0.40→0.15**
(f8): cuts front-load −37% overall, concentrated in the flat/modest bands (crash 23%/10%, no plateau
benefit) and **preserves the steep >90 band 1.00→1.00** (the only band where front-loading helps).

This is INSULIN-REDUCING (safety direction; risk is higher peaks, not lows) and it is the OPPOSITE of
the userH B3/A2 levers — the velocity gate is where the two reconcile: pull back the modest-rise floor
for everyone, let per-user aggression modulate only the steep-rise response. Path: it's a policy
change (outcome unvalidatable offline — the dose delta IS priced here), so auto-config-managed, watch
the high tail, within-user trial at the two-test bar.
