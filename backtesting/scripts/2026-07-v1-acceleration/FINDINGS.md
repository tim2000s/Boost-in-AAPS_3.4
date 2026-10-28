# V1's acceleration signal + early-tier bolus — did V6 lose it, and is it safe to restore?

**Date:** 2026-07-20 · **Question (Tim):** V1's early tiers used the acceleration signal to
deliver a small bolus sized to be harmless if the meal didn't continue. Did V6 lose it, and can
we look back at the V1-era data to see whether it's useful to re-add for earlier meal detection?

**Verdict:** V1's acceleration response is a real ~15-min earlier detector that V6 gated away; the
early *bolus* is genuinely **fizzle-safe** (the crashes blamed on it were 69% **downstream** dosing,
not the entry). Restore the early fizzle-safe bolus + guard the follow-through. See
`REINTEGRATION_SPEC.md`.

---

## What V1 does with acceleration (code)

`delta_accl = 100·(delta − shortAvgDelta)/max(|shortAvgDelta|,2)` — a normalised % form, exported
by every Boost generation (DB `delta_acceleration`). V1 (`DetermineBasalBoost`) uses it two ways
V6 dropped or tightened:
1. **Graded acceleration→forecast dosing** (L810‑825): the faster BG accelerates, the more V1 doses
   toward eventualBG. V6 replaced DynISF-for-dosing with the budget state machine — the graded
   coupling is gone.
2. **G3 acceleration-release** (L1274‑1301): on an unannounced rise from near-target, `delta_accl>10`
   releases the SMB hold and doses early. V6's descendant (fast-confirm) needs `delta≥6 AND accl≥10
   AND score≥0.65 AND awake AND !exercise` — far more gated. V1 released on acceleration alone.

## 1. Is the acceleration gate an earlier detector? (`v1_accel_lead.py`, V6-era, 14,430 fires)

| metric | pooled (95% CI) |
|---|---|
| recall (confirms preceded by a `delta_accl>10` fire) | **97.8% [97.0, 98.7]** |
| median lead (fire → confirm) | **15.0 min [15.0, 15.1]** |
| precision (fires reaching a confirm ≤30 min) | 15.0% [11.5, 17.3] |

V1's gate precedes ~every V6 confirm by a median 15 min (recall 98%) — a real, large early signal —
but 85% of fires don't reach a confirm. Unusable as a raw *aggressive* trigger; ideal as an early
*small/retractable* one.

## 2. Was V1's early bolus fizzle-safe? (`v1_fizzle_safety.py` → `v1_fizzle_pure.py`, V1-era)

V1 dosed a **small** bolus on fires (median 0.25 U, mean ~0.5 U), from a lower mean BG (119) —
early-onset context. First pass (any low in +30..150 min → the bolus) looked mixed: pooled fizzle
low 12.7%, with D/tim ~28%. **But that attribution was wrong** — V1 kept dosing after the fizzle, so
those lows include downstream SMBs. Re-run allocating a low to the fizzle bolus only when the
insulin delivered *after* it (before the low) ≤ the bolus itself:

| | pooled (95% CI) |
|---|---|
| raw fizzle low<70 | 13.8% [5.8, 23.5] |
| **PURE — fizzle bolus was the dominant insulin** | **4.4% [2.2, 6.5]** |
| matched-ambient baseline (same attribution) | 3.3% [2.5, 4.4] |
| **Δ (pure − baseline)** | **+0.9% [−0.6%, +3.0%] — no excess** |

**Of 571 fizzle-lows, 394 (69%) were downstream-dosing lows, not the early bolus.** D and tim — the
two that looked dangerous — were 70–77% downstream (D raw 29%→pure 6.6%≈baseline; tim 27.8%→8.3%).
Residual: **C** keeps a small pure excess (10.5% vs 2.8%, n=114) and **tim** is mildly elevated
(8.3% vs 2.4%) — consistent with U200 making his "small" bolus 2× mass. → the entry wants a light
per-user touch, not a blanket gate.

## Conclusion

- V1's acceleration bolus is **fizzle-safe by size** (pure Δ +0.9%, not distinguishable) — Tim's
  original design thesis, validated on production data. SOLID-leaning-PROVISIONAL (wide pooled CI).
- **The crash risk is the post-fizzle follow-through** (69% of the lows) — V1/V6 keep dosing after
  an unannounced rise stalls. That is the real lever, and it lines up with the high-IOB-tail and
  post-meal under-recovery findings.
- So restore V1's early fizzle-safe entry **and** retract the *follow-through* when the rise fizzles
  — a cleaner division of labour than arming a temp-basal. Design in `REINTEGRATION_SPEC.md`.

Caveats: baseline is matched-ambient, not a true no-dose control (V1 dosed broadly); "pure" uses a
strict dominance rule (subsequent insulin ≤ the fizzle bolus); prior IOB is matched in the baseline.

## Reproduce
`python3 v1_accel_lead.py` · `v1_fizzle_safety.py` · `v1_fizzle_pure.py`  (local oref DB, t=now)
