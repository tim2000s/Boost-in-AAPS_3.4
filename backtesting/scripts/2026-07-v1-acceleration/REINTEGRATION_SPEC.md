# Spec: reintegrate V1's early acceleration bolus into the V6 meal-state engine

**Date:** 2026-07-20 · **Tier: SPECULATIVE** (design only; nothing built). Shadow-first → two-test
bar → auto-config-managed before it doses. Evidence: `FINDINGS.md` (this folder).

## The idea in one line

Restore V1's ~15-min-earlier acceleration response as a **small fizzle-safe primer during
OBSERVING**, delivered as an **advance on** the CONFIRMED commit-shot (move, don't add) — and lean
on V6's existing brake/RECOVERING to guard the follow-through that actually crashed V1.

## Why this is the right shape (from the data)

- V1's `delta_accl>10` gate leads V6's CONFIRMED by a median **15 min at 98% recall** — a real early
  detector V6 gated away (precision only 15%, so it must be *small/retractable*, never an aggressive
  trigger).
- V1's early **bolus is fizzle-safe by size**: pure (bolus-attributed) fizzle-low 4.4% vs 3.3%
  ambient, Δ **+0.9% [−0.6, +3.0]** — not distinguishable.
- The crashes blamed on V1's early tier were **69% downstream dosing**, not the entry — V1 kept
  correcting after the rise fizzled, and V1 had **no brake**. **V6 does** (composed brake +
  RECOVERING, ~90% correct; it actually *under*-recovers post-meal). So the follow-through that
  crashed V1 is already handled in V6 — the reintegration is mostly the *entry* + netting.

The two branches are therefore both safe by construction:
- **Meal fizzles** → the primer is the only insulin, and it's the small fizzle-safe amount we proved
  benign (Δ +0.9%). V6's brake damps any follow-on.
- **Meal confirms** → the primer is netted off the commit-shot, so total meal insulin is unchanged,
  just delivered ~15 min earlier — **moving insulin earlier is harm-neutral** (early-dosing audit),
  *adding* it is +15 pp lows (which we do not do).

## The change (V6 meal engine)

**A. OBSERVING acceleration primer.** Today OBSERVING doses ~nothing (the non-meal seam cap blocks
OBSERVING budget). Add an exemption: when in OBSERVING (or IDLE→OBSERVING) with
- acceleration present — `delta_accl > 10` (V1's threshold) **or** the accelMeal curvature
  `shortAvgDelta − longAvgDelta > 2` (the shipped shadow's form; log both, pick on banked data),
- rising, BG rising from near-target, and **all existing floors clear**: recentLowBG ≥ 80 (rescue
  guard), not post-rescue, not sleeping, not exercising, cumulative-SMB cap not reached,

deliver a **small primer** `min(primerCapU, share·expectedCommitShot)`. Track
`cumulativePrimedThisSession`.

**B. Net it off the commit-shot.** When CONFIRMED fires, `commitShot = max(0, normalCommitShot −
cumulativePrimedThisSession)`. Move, not add. (This is the safety keystone — without it the primer is
additive insulin and the audit says +15 pp lows.)

**C. Follow-through: rely on the existing brake.** On OBSERVING→IDLE (fizzle) the engine already
falls back and V6's brake/RECOVERING damps further SMBs — the exact guard V1 lacked. No new
suppression state needed for V6; **do not loosen the brake** (it's ~90% correct and is what makes the
fizzle branch safe). Optionally log a `primedFizzle` flag for audit.

**D. Per-user sizing (auto-config-managed).** `primerCapU` is derived by `BoostV5AutoConfig`:
- default primer for well-controlled users (A/E/H-type — pure fizzle-low ≤ baseline);
- **smaller cap for the hypo-prone and U200** — C keeps a small pure excess (10.5% vs 2.8%) and tim
  is mildly elevated (8.3% vs 2.4%, U200 = 2× mass), so their cap must be scaled down (U200-aware,
  same strict-TBR gate every insulin-adding switch uses);
- for the most hypo-prone, fall back to the **retractable temp-basal** (`antBackout`) instead of a
  bolus — safe-by-unwinding rather than safe-by-size.

## Shadow-first (what to build first, dosing nothing)

Log per cycle, delivering nothing: `primerWould = <U>`, the trigger form (accl vs curvature),
`netCommitWould`, `cumulativePrimedWould`, and the fizzle/confirm outcome. This banks, on-device:
- would-be primer sizes + how often the floors block them,
- the realised lead (primer cycle vs the eventual CONFIRMED),
- the fizzle rate and the *pure* fizzle-low rate under the actual per-user cap,
- the net-off arithmetic (confirm-shot reduction), to prove total insulin is unchanged.

The `accelMeal` and `antBackout` shadows already bank the detector lead and the retractable-arm
economics — this primer shadow adds the bolus-path leg.

## Gate before it doses

1. Shadow bank clears: realised lead ≈ 15 min, pure fizzle-low under the per-user cap ≤ ambient (the
   +0.9% result holds on-device), net-off confirmed (no added insulin on real meals), with CIs.
2. Auto-config sizing validated per-user (well-controlled default; C/tim/U200 scaled; most-hypo →
   temp-basal).
3. Two-test bar: absolute TBR gates + relative pricing + a pre-registered within-user trial.

## Explicitly NOT in scope

- Additive early insulin (must net off the commit-shot — move, not add).
- Loosening the composed brake / RECOVERING (that is the follow-through guard; V1's crashes came from
  *not* having it).
- A blanket cohort default (per-user auto-config only; C/tim need a smaller cap).
- Touching Fix 6 (single-CONFIRMED-per-session) — the primer is pre-confirm and netted, not a second
  commit-shot.
