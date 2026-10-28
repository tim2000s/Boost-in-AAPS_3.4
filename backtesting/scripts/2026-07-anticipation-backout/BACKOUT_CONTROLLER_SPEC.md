# Boost — anticipatory back-out controller: specification (shadow-first)

*2026-07-20. The anticipation-ceiling test (kairos-lab E07) showed meal timing is only ~1-in-3
predictable from habits — too weak to pre-dose blindly. This controller makes a WEAK anticipation SAFE by
making every anticipatory dose RETRACTABLE and unwinding it the moment the anticipated event fails to
confirm. Anticipation doesn't need to be accurate — it needs to be retractable. This is the foundational
mechanism the whole anticipation layer depends on; spec + shadow it before any anticipator model drives it.*

## 1. What it does
Wraps ANY anticipatory pre-position (from the event-anticipator: meal/activity likelihood). It (a) delivers
the anticipatory insulin as a small RETRACTABLE temp-basal — never an SMB; (b) watches whether the
anticipated event actually materialises, via the Twin's latent meal state `Ra` + the BG trajectory,
against a DEADLINE; (c) hands off to normal dosing if confirmed, or BACKS OUT (zero-temp + a protection
window) if not. Hard safety floors sit underneath, unchanged and non-overridable.

## 2. Why temp-basal, never SMB
An SMB is irreversible the instant it is given. A raised temp-basal trickles the extra insulin and can be
ZEROED next cycle, so the maximum insulin ever "stuck" from a wrong anticipation is ~one cycle of a small
basal bump — trivially recoverable. This single choice caps the downside and is what makes acting on a
1-in-3 signal defensible.

## 3. State machine
```
IDLE ──anticipation fires──▶ ARMED ──confirmed──▶ HANDOFF (normal meal/activity dosing takes over)
                              │  └─deadline w/o confirm─▶ BACKED_OUT (zero-temp + protection window) ─▶ IDLE
                              └─early low-risk trip──────▶ BACKED_OUT (immediate)
```
- **ARMED**: deliver `antBasalU` (a small, confidence-scaled temp-basal bump) each cycle; record baseline
  `Ra0`, `bg0`, and the expected-rise threshold. Cap total ARMED delivery at `ANT_CAP_U`.
- **Confirmation (→ HANDOFF)** — ANY of, within `ANT_WINDOW_MIN`:
  - Twin `Ra` rises above `Ra0 + RA_CONFIRM_MARGIN` (the meal-appearance state lifting — the cleanest
    signal, since Ra is meal-specific after insulin action is removed), OR
  - observed BG rises ≥ `bg0 + BG_CONFIRM_RISE` (a plain excursion started).
  On confirm, stop the anticipatory temp-basal and let the normal meal/activity path govern.
- **Back-out (→ BACKED_OUT)** — EITHER the deadline `ANT_WINDOW_MIN` passes with no confirmation, OR an
  early trip: BG or the Twin's `lo30`/minGuard heads below `ANT_LOW_TRIP` before the deadline. Action:
  zero-temp for `ANT_PROTECT_MIN` to wash out any small excess delivered, log the outcome.

## 4. The confirmation signal (the crux — VALIDATED, kairos-lab E08)
`Ra` is the Twin's latent glucose-appearance state, inferred from CGM AFTER accounting for insulin action,
so it is meal-specific in a way raw BG is not. E08 (per-user, loop's own meal labels) measured how well
each signal confirms a real meal within the 40-min window:
- **AUC: Ra 0.83, BG-rise 0.87, OR(Ra,BG) 0.86** — both are good confirmers (~0.85). Ship the **OR clause**,
  not Ra alone: offline, BG-rise is marginally better; Ra's edge is LIVE-only (it sees a real meal THROUGH
  the anticipatory insulin masking its BG rise — the exact deployment case this offline test can't show).
- **Confirmation latency ~20–25 min** → the 40-min deadline is right (margin without premature back-out).
- **Error economics favour the design.** Ra alone misses ~31% of real meals; the BG-rise clause rescues
  ~66% of those → residual **~11% FALSE BACK-OUT** — and that error is **BENIGN**: you only lose the
  anticipatory head-start, normal meal dosing still catches the meal reactively once BG rises. The
  DANGEROUS error (keep dosing with no meal) is backstopped by the low-trip (§3). Asymmetry is in our favour.

## 5. Per-direction use (from E07 + the anticipation probes)
- **Activity** (AUC 0.85, insulin-REDUCING): the "pre-position" is a REDUCTION (lower temp / raise target)
  ahead of a likely walk. Safe direction — back-out is "restore normal" if no walk comes. Act confidently.
- **Meal** (AUC ~0.6, insulin-ADDING): tiny `antBasalU`, ONLY for users whose meal timing is regular
  enough (per-user auto-config gate on meal-time entropy — the E07 "F-type" clocked eaters), always
  retractable. Never blanket.

## 6. Config (auto-config-managed; insulin-adding side gated to well-controlled + regular)
```
ANT_WINDOW_MIN        ≈ 40      deadline to confirm before back-out
ANT_CAP_U             small     max cumulative ARMED delivery (per-user, U200-aware)
RA_CONFIRM_MARGIN     tuned     Ra rise that counts as a meal appearing (from e08)
BG_CONFIRM_RISE       ≈ 15 mg/dL
ANT_LOW_TRIP          ≈ 85 mg/dL early back-out floor
ANT_PROTECT_MIN       ≈ 30      zero-temp wash-out window on back-out
Gate: activity ON for most; meal-pre-position ON only if meal-time-regular AND TBR-clean (strict cut)
```

## 7. Telemetry (shadow-first) — bank the confirm/back-out economics BEFORE it doses
Log per candidate: `antBackout=state,wouldAntBasalU,ra0,raNow,bg0,bgNow,confirmed?,backedOut?,trip?;`.
The numbers we need before going live: (a) how often it would ARM, (b) of ARMED, the CONFIRM vs BACK-OUT
split, (c) on BACKED_OUT, did forward BG stay safe (the mechanism's whole promise), (d) on CONFIRMED, did a
real meal actually follow (true-positive rate). Belt-and-braces runCatching; delivers NOTHING in shadow.

## 8. Honest caveats
- Depends on the Twin `Ra` confirmation being reliable and reasonably PROMPT (Ra tracks the rise, it does
  not lead it — that's fine, confirmation is a "has it started" question, not anticipation). e08 measures it.
- The dangerous error is a FALSE BACK-OUT of a real meal (Ra fails to rise though a meal came) → under-dose
  a real meal. Measured in e08; the BG-rise OR-clause (§3) is the backstop against it.
- First-order: shadow measures would-doses + confirm/back-out outcomes, not a counterfactual trajectory.
  Real proof = on-device shadow banking + the two-test bar. Floors underneath throughout.
```
Config key (future): BooleanKey.ApsBoostAnticipationBackout — shadow → per-user auto-config → two-test bar
```
