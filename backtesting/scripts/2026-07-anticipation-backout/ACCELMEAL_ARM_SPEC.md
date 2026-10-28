# Spec: wire `accelMeal` → `antBackout` ARM (shadow)

**Date:** 2026-07-20 · **Tier: SPECULATIVE** (the lever is unproven).
**Status: shadow IMPLEMENTED 2026-07-20 (commit `d8c4fafaee`) — banking arm economics, delivers
nothing.** A live version is a dosing change → two-test bar → auto-config-managed. Do not dose on
this until the banked economics below clear the bar. The section "The change" records what was built.

## Why

Two validated pieces are running side by side but **disconnected**:

- **`accelMeal`** (2026-07-20, shipped shadow) — the best *onset* detector we have. Signal
  digging found BG acceleration is the one usable cue and it leads the delta-based confirm by
  ~5 min. Currently detection-only.
- **`antBackout`** (2026-07-20, shipped shadow) — the retractable-anticipation state machine
  that makes acting on a *weak, early* signal **safe**: arm → confirm (Ra rise OR BG rise within
  40 min) or unwind (deadline / early-low trip). Validated crux E08: confirm AUC 0.83–0.87,
  false-back-out ~11% and benign.

`antBackout` currently arms on a **placeholder** trigger — `mlMealLikely ≥ 0.6` — *not* the
acceleration signal we validated as the best onset cue. So the strongest detector isn't driving
the safe action.

Two fresh findings make this the *right* next step rather than a shape-gated lever:

1. **Crashes are unpredictable at confirm** (`meal_shape.py`, OOS AUC 0.52 = chance). You cannot
   pre-select which meals crash → predict-and-restrain is off the table → the only viable crash
   defence is a **retractable** action. That is exactly what `antBackout` is.
2. **Dosing more on a detection crashes** (post-confirm second-confirm NO-GO; recovering-highs
   NO-GO). So the arm must be *retractable temp-basal*, never an SMB commit — which is already
   the `antBackout` contract.

## The change (shadow — read-only)

In `OpenAPSBoostPlugin.invoke()` the `accelMeal` trigger is computed at ~L1522, just *after* the
`backoutShadow.runCycle(...)` call at ~L1509. Two edits:

1. **Hoist** the accel trigger above the back-out call (it's cheap — `shortAvgDelta −
   longAvgDelta`, a rising check, and the pre-confirm state check already written at L1523‑28).
   Compute a local `accelArm: Boolean` before L1509.

2. **Add an `armSignal: Boolean` parameter** to `AnticipationBackoutShadow.runCycle(...)` and make
   the IDLE→ARMED transition fire on it:

   ```kotlin
   // AnticipationBackoutShadow
   fun runCycle(nowMs, bg, ra, lo30, mealLikely, armSignal: Boolean = false): String? {
       ...
       St.IDLE -> if (armSignal || ml >= trigMealLikely) { st = St.ARMED; ra0 = ra; bg0 = bg; armedAtMs = nowMs; armSrc = if (armSignal) "accel" else "ml" }
       ...
       // append armSrc to the tag so arm-trigger economics are separable offline
   }
   ```

   Keep the `mlMealLikely` path in the OR (and log `armSrc`) so the two arm-triggers can be
   compared on banked data — do **not** silently drop the placeholder; bank both and let the data
   choose. Confirmation (Ra OR BG rise within 40 min) and back-out (deadline / low-trip) are
   **unchanged** — only the ARM source widens.

3. **Pass it through** at the call site:
   `backoutShadow.runCycle(now, glucoseStatus.glucose, fc.raMean, fc.lo30, it.mlMealLikely, accelArm)`.

Both remain wrapped in the existing double `runCatching` — a shadow failure never touches the dose.

## What it banks (the questions the shadow answers)

The `antBackout=` tag already logs `state, ra0, ra, bg0, bg, confirmed, backedOut, trip, ml`;
add `armSrc`. Then over ~2–4 weeks of on-device data, per arm-source (`accel` vs `ml`):

- **ARM→confirm rate** — of arms, how many were real meals (Ra/BG confirmed within 40 min)? This
  is the true-positive economics of arming on acceleration vs ml_meal_likely.
- **False-back-out rate + cost** — of arms that unwound, how benign was the unwind (BG/lo30 at
  back-out; did a low follow anyway)? E08 said ~11% benign; verify on-device for the accel arm.
- **Lead** — arm time vs the eventual CONFIRMED time: does the accel arm actually pre-position
  earlier than the confirm (the ~5 min the offline analysis suggested)?
- **Overlap** — does `accel` arm on meals `ml` misses, and vice-versa? (Union coverage.)

## Gate before it ever doses

1. Shadow bank clears: accel-arm ARM→confirm rate materially beats the ml placeholder AND
   false-back-out stays benign (no excess lows in the unwind window), with bootstrap CIs.
2. The retractable temp-basal magnitude is priced against observed outcomes (counterfactual
   caveat stated) and **auto-config-managed** — enabled only for well-controlled users (the same
   strict-TBR gate the insulin-adding switches use).
3. Two-test bar: absolute TBR gates + relative pricing + a pre-registered within-user trial.

## Explicitly NOT in scope

- No SMB / commit-shot on the arm (settled: dosing more on a detection crashes).
- No shape-gating (crashes unpredictable at confirm — `meal_shape.py`).
- No change to the confirm state machine (Fix 6 single-confirm-per-session stays intact).
