# Boost V6 — post-meal plateau nudge: specification

*2026-07-19. Design spec (not yet built). The under-recovery is real (ff1); the confirm-ramp and a
forecast-gated descent lever are both closed (ff2, dr2, dr3 — the per-cycle plateau low is
unforecastable, best OOS AUC 0.55). What survives is a PER-USER lever: nudge the plateau down only for
users whose plateaus demonstrably don't go low. This specs that, plus a user override.*

## 1. What it does
In the post-meal **plateau** — glucose parked above tight range, flat or falling, hours after a meal,
where V6 currently doses ~0 — deliver a small correction to walk glucose back into range. Both V6 and
V1 hold here today, so this **out-doses V1** (a genuinely new behaviour), and it doses into a
recovering high (the register's danger zone). It is therefore gated hard and shadow-first.

## 2. The safety model — READ THIS FIRST
The per-cycle plateau low is NOT predictable (dr3: no signal — Twin forecast, floor, slope, oref
minGuard/minPred, BG, IOB, trend — clears chance out-of-sample). So this is **NOT** a "forecast the low
and dose" rule. It is a **base-rate + small-dose + hard-floor** rule:
- **Base rate:** only enabled for users whose banked plateau-low rate is near zero (auto-config, §5).
- **Small dose:** each nudge is tiny and rate-limited, so an occasional mis-timed nudge (even enabled
  users aren't at 0% — H 3%, C ~9%) cannot drive a dangerous low on its own.
- **Hard floors:** the absolute low-guards below still apply every cycle and can only tighten.

## 3. Trigger (per cycle) — ALL must hold
- Meal-dosing active (not asleep / night-mode suppressed / high temp target).
- **BG in [145, 200)** — above the 140 tight-range ceiling, below the zone V6's normal correction owns.
- **Flat or falling:** `delta15 ≤ +5 mg/dL` (a still-rising glucose is the meal, handled by confirm).
- **Post-meal:** state ∈ {COMMITTED, RECOVERING, IDLE-with-recent-meal}, i.e. within ~3h of a
  detected onset (not a fresh rise — that's the confirm channel).
- IOB below `maxIOB` with headroom for the nudge.

## 4. Nudge sizing
- `nudge = min(PLATEAU_NUDGE_U, committedCapU, maxIOB−IOB headroom)` where `PLATEAU_NUDGE_U ≈ 0.10U`
  (auto-config-scaled by the user's ISF/TDD, like committedCap).
- **Rate-limited:** at most one nudge per `PLATEAU_NUDGE_MIN_INTERVAL` (≈15 min).
- **Cumulative cap:** total plateau-nudge per meal ≤ `PLATEAU_NUDGE_MEAL_CAP_U` (≈0.4U), and it counts
  toward the existing rolling-60-min cumulative SMB cap.

## 5. Auto-config default (per-user) — `BoostV5AutoConfig`
Derive `plateauLowRate` from the user's banked history: of plateau cells (BG>140, flat/falling,
+90..210min post-onset), the fraction whose forward-3h nadir < 70. Then:
- **Enable by default IFF** `plateauLowRate < PLATEAU_LOW_RATE_MAX` (≈5%) **AND** the standard
  insulin-adding TBR gate passes (14d TBR<70 ≤ 3.5%, TBR<54 ≤ 0.8% — same fail-closed gate the
  velocity-budget floor uses). Else default OFF.
- On the current cohort this enables **A, H, D** (plateau-low 0–3%) and leaves **F, B, tim, C, E** OFF
  (9–23%) — the rule matches the data. Re-derived on each auto-config run; managed key.

## 6. User override — `BooleanKey.ApsBoostV5PlateauNudge`
Per Tim: a user may **force the feature ON even if auto-config left it OFF** — an explicit opt-in to
nudge the plateau down above what V1 would dose, accepting the trade (more mild-highs corrected, a
higher residual low risk than an auto-enabled user). Semantics:
- Override ON → feature active regardless of the derived default. Override at default → auto-config decides.
- **The override enables the FEATURE; it does NOT disable the §7 hard floors** — those protect every
  user every cycle and are non-overridable. (An advanced user can accept more risk, not remove the floors.)

## 7. Hard floors (non-negotiable, non-overridable, can only tighten)
Never nudge if ANY: recent low (`recentLowBG45Min < 75`); post-rescue window; exercise active; asleep;
`minGuardBG ≤ threshold` (kept as a floor even though it's a weak predictor — a *forecast* low is still
a veto); cumulative-SMB cap reached; composed brake at its floor. The nudge is the LAST thing computed
and the first suppressed.

## 8. Out-dosing V1 (the seam) — exemption flag
Like the velocity-budget floor and composed-brake floor: when a nudge fires, set
`V5Decision.plateauNudgeExempt = true` so the OpenAPSBoostPlugin non-meal-state cap lets the delivered
dose exceed `v1_units` (committedCap-bounded). Without the exemption the non-meal cap clamps it to V1's
would-dose (≈0) and the nudge never reaches the pump.

## 9. Telemetry + shipping path (shadow-first, two-test bar)
- **Ship as SHADOW first:** compute `plateauNudgeWouldAddU` + the trigger/floor state, append to the
  reason tag; deliver NOTHING. Extractor → `boostv5_plateaunudge_*` cols. Bank ~2–4 weeks.
- **Price it** on-device: does the shadow nudge fire in the plateau, and (critically, per user) does a
  low follow the cells it would have dosed — the direct on-device version of dr1/dr3. Confirm the
  banked `plateauLowRate` matches the enable decision.
- Only then flip to active, auto-config-managed, override available. Absolute TBR gates + within-user
  trial. Watch the high tail (it should improve) AND the low tail (must not worsen).

## 10. Honest caveats
The whole lever rests on `plateauLowRate` being a STABLE per-user trait (it looks it — A/D 0%, F 22% —
but on ~3-week windows). The per-cycle low is unforecastable, so enabled users still carry a small
residual low risk, bounded by the small dose + floors, not eliminated. This is the narrowest, most
conservative form of a meal-recovery lever the evidence permits; it is not a general V6 fix.
```
Config keys (all auto-config-managed except the override):
  ApsBoostV5PlateauNudge (BooleanKey)          — user override (default: auto-config-derived)
  PLATEAU_NUDGE_U ≈ 0.10U                       — nudge size (ISF/TDD-scaled)
  PLATEAU_NUDGE_MIN_INTERVAL ≈ 15 min           — rate limit
  PLATEAU_NUDGE_MEAL_CAP_U ≈ 0.4U               — per-meal cumulative cap
  PLATEAU_LOW_RATE_MAX ≈ 5%                      — auto-enable threshold
  BG band [145, 200), delta15 ≤ +5              — trigger window
```
