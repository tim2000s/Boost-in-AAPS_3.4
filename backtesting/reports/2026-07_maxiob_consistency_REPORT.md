# maxIOB Path-Divergence Bug (user H) — 2026-07-07

Scripts: `backtesting/scripts/2026-07-maxiob/maxiob_investigation.py` (CSV in `out/`).
Data: TimescaleDB `oref` (H current to 21:19 today; the 17:00–20:00Z rise captured). Dedup: last row
per (user, 5-min bucket). Code refs: repo `Boost-AAPS-core`, branch `Boost-V6-experimental`.

---

## PART A — MECHANISM (headline, resolved with certainty)

**user H's big CONFIRMED/COMMITTED shots are zeroed because SafetyGates receives `maxIob = 1.0`
(the `ApsBoostMaxIob` factory default) instead of his configured 8 — during a percentage
profile-switch window.** SafetyGates itself is correct; it is FED the wrong ceiling.

### The arithmetic (SafetyGates.kt)
- Hard clamp (`SafetyGates.kt:125-128`): `headroom = max(0, maxIob − iob); if dose > headroom: dose = headroom`.
  At iob=1.04, maxIob=1.0 → headroom = **0.00** → any dose → 0.
- iobHeadroomBrake (`SafetyGates.kt:186-198`, ladder `:82-85`): `fraction = iob/maxIob`; ≥0.85 → **0.40**.
  At iob=1.04, maxIob=1.0 → fraction 1.04 → **0.40**.
- Both fire → gate string `iobHeadroom:0.40,maxIOB`, fd=0. With maxIob=8: headroom 6.96, fraction 0.13 → brake 1.0 → **no throttle**.

### The direct evidence (console_error logs `maxIOB: ${profile.boost_maxIOB}`, DetermineBasalBoost.kt:361)

| time | state | iob | budget | fd | **console maxIOB** | committedCap | confirmedCap | **profile_switch** | gate |
|---|---|---|---|---|---|---|---|---|---|
| 17:34 | CONFIRMED | 1.04 | 5.64 | **0.00** | **1.0** | 0.5 | 2.5 | **130** | iobHeadroom:0.40,maxIOB |
| 17:39 | COMMITTED | 1.11 | 7.16 | **0.00** | **1.0** | 0.5 | 2.5 | **130** | iobHeadroom:0.40,maxIOB |
| 17:44 | COMMITTED | 1.18 | 7.25 | **0.00** | **1.0** | 0.5 | 2.5 | **130** | iobHeadroom:0.40,maxIOB |
| 17:49 | COMMITTED | 1.24 | 7.19 | **0.00** | **1.0** | 0.5 | 2.5 | **130** | iobHeadroom:0.40,maxIOB |
| 17:54 | RECOVERING | 0.92 | 2.54 | **0.60** | **8.0** | 1.2 | 4.0 | **100** | decel:0.55 |

At the instant the profile switch drops 130→100 (17:49→17:54), **all three Boost values flip from
factory defaults (maxIOB 1.0 / committedCap 0.5 / confirmedCap 2.5) to his real settings (8.0 / 1.2 /
4.0)** in a single cycle. The 0.6U-at-iob-0.93 vs 0-at-iob-1.04 "contradiction" was never a constant-
ceiling puzzle — the ceiling itself changed from 1.0 to 8.0 across that boundary.

### Trigger correlation (H, full history)
- `maxIOB=1.0` occurs on **13/13 cycles with a %-profile-switch active** (never at ps=100). It coincides
  1:1 with the caps also reading defaults → this is an **auto-config-output triple** (maxIOB + both caps
  are the three values BoostV5AutoConfig manages), reset together and reverted together.
- BUT a %-switch is **necessary, not sufficient**: only 13 of H's ~12,900 %-switch cycles masked — so the
  trigger is a *specific* profile-switch event (the 130% at 17:34), not every switch. The exact code path
  (auto-config re-run writing defaults during the switch vs `getMaxIOBAllowed()` reduction) is traced in
  the CODE PATH section below.

### SHARED gate — the zeroing is NOT V6-specific (reconciles V1_units=0 too)

`profile.boost_maxIOB` feeds BOTH engines, so the masked 1.0 zeroes base-oref and V6 identically:
- **Base engine (DetermineBasalBoost):** every boost tier is guarded `iob < boostMaxIOB` and clamps the
  dose to `boostMaxIOB − iob` (`DetermineBasalBoost.kt:1491/1496, 1529/1534, 1550/1553, 1574/1578, 1600,
  1632`). At boostMaxIOB=1.0, iob=1.04: `1.04 < 1.0` = **false** → ALL boost tiers skipped; the surviving
  clamp is `1.0 − 1.04 = −0.04` → 0. Base oref delivers ~0 → **v1_units = 0**.
- **V6:** `maxIob = min(boost_maxIOB=1.0, max_iob=8) = 1.0` → SafetyGates clamp+brake → fd = 0.

This is why the DB side-by-side shows **V6 == V1_would == 0** on the high-budget cycles — both read the
same masked `profile.boost_maxIOB`, not a V6-only brake. Verified split (all H budget>3 cycles): every
masked cycle (18:29–18:49, maxIOB=1.0) has fd=0 AND v1=0; at maxIOB=8 he DELIVERS — **6.00U at 07-07
14:54** (CONFIRMED budget 3.17), 2.50U at 07-04 03:34, 1.65–1.80U on 07-03 rises. The only maxIOB=8 zeros
carry `HARD:enable_smb_pre_checks` (a legitimate SMB-eligibility gate on specific cycles, not systematic).
His target was **80–85 during the mask window** (NOT the activity-raised 150) — so activity/target is ruled
out as the cause of these zeros; it is the masked boost_maxIOB.

**Conclusion: this is a PATH-DIVERGENCE bug — both engines use a `profile.boost_maxIOB` = 1.0 ≠ his
setting 8, during a %-profile-switch window. Not a low ceiling, not a SafetyGates logic error, not IOB
exhaustion, not activity/target. The SINGLE thing to fix is the transient factory-default reset of
boost_maxIOB (and the caps); correcting it restores delivery — empirically, at maxIOB=8 his insulinReq
lands (6.0U on 07-07 14:54).**

---

## PART B — THE SINGLE FIX (correct boost_maxIOB), not a new lever

**The velocity-budget "restore V1 aggression" lever is DEAD for user H** — the DB side-by-side shows V6
doses IDENTICALLY to V1_would for him (budget>4: both avg 0.514, both zero on 5/7; budget>2: 1.22 vs
1.26), and his real V1-era never gave big shots either (max 2.15 when BG>180). There is no V1 aggression
to restore. The right question is: **what single gate/setting, changed, lets his insulinReq 5.64 deliver?**
Answer from the code + data above: **the masked `boost_maxIOB`.** Correct it (1.0→8) and delivery is
restored with no new lever — empirically confirmed by 07-07 14:54 (6.0U delivered at maxIOB=8, same
machinery). The counterfactual below quantifies the specific masked cycles.

Replaying the 4 masked cycles with maxIob=8 and his real caps (confirmedCap 4.0, committedCap 1.2,
knob 1.30), through the true clamp+brake:

| time | state | iob | budget | actual fd | fd with maxIob=8 |
|---|---|---|---|---|---|
| 17:34 | CONFIRMED | 1.04 | 5.64 | 0.00 | **4.00** (budget×1.8×1.3=13.2 → confirmedCap 4.0; headroom 6.96, brake 1.0) |
| 17:39 | COMMITTED | 1.11 | 7.16 | 0.00 | **1.20** (committedCap) |
| 17:44 | COMMITTED | 1.18 | 7.25 | 0.00 | **1.20** |
| 17:49 | COMMITTED | 1.24 | 7.19 | 0.00 | **1.20** |

**Delivered 0.00U → counterfactual 7.60U** (a 4.0U confirmed shot + three 1.2U holds) on a genuine rise
(BG 148→177, eventualBG projected 310–331). This IS the "single big shot" user H says he never gets — his
4U confirmedCap correction, killed by the maxIob=1.0 mask.

**Test A (honest):** his 14d TBR is 0.65%/0.02% — enormous headroom; 4.0U is exactly his own configured
confirmedCap and the rise justified it (eBG 310+). The counterfactual is his INTENDED behaviour, not new
aggression. Caveat: with 16k steps and an activity-raised target that day, 7.6U over 20 min carries some
low risk if the rise had fizzled — but it did not (peaked ~187, drifted down slowly), and the shot is
bounded by his own caps. Net: the bug is suppressing dosing he configured and that his TBR can absorb.

---

## PART C — COHORT SCOPE + auto-config consistency

### C1. The mask is NOT user H-only — and user E is chronically throttled

| user | maxIOB=1.0 cycles | during %-switch | maxIOB values seen | reading |
|---|---|---|---|---|
| **E** | **32,949 (94%)** | 26,211 (also 6,738 at ps=100) | 1.0, 8.0 | **chronic — E's V6 has been throttled ≈off for months, at ALL ps** (separate from the mask bug; E likely never raised maxIOB off default) |
| D | 117 | 117 (all) | 1.0,4.0,4.5,5.0 | transient mask, rare |
| H (user H) | 13 | 13 (all) | 1.0…8.5 | **transient mask bug** (clean ps=130 signature) |
| B | 9 | 9 (all) | 1.0…8.0 | transient mask, rare |
| A | 4 | 4 (all) | 1.0,9.0,10.0 | transient mask, rare |
| F / C / tim | 0 | — | 3.0–8.0 / 3.55 / 3–8 | unaffected |

Two manifestations of the SAME Simple-Mode masking bug: (a) **H/A/B/D — transient** (`simple_mode`
read true for a short window, zeroing big shots when a rise coincided); (b) **E — chronic**: E runs in
Simple Mode, so `preferences.get(ApsBoostMaxIob)` returns 1.0 on ~94% of cycles regardless of ps — **E's
V6 amplification has been read-suppressed the entire time** (the largest-impact instance; the occasional
8.0 cycles are when E was momentarily out of Simple Mode). Not a settings mistake by E — the mask (Part
ROOT CAUSE) overrides whatever E configured.

### C2. Latent auto-config maxIOB↔confirmedCap inconsistency (widespread)

Auto-config carries maxIOB (`BoostV5AutoConfig.kt:129 maxIobU = currentMaxIobU.coerceIn(0.1,12)`) but
never checks it against the derived confirmedCap. Per user (14d), `maxIOB_mode − IOB_p90 ≥ confirmedCap`?

| user | maxIOB mode | confirmedCap | IOB p90 | confCap reachable at p90 IOB? |
|---|---|---|---|---|
| A | 10.0 | 2.50 | 6.26 | ✅ |
| tim | 5.0 | 3.00 | 1.65 | ✅ |
| H | 8.0 | 6.00 | 4.01 | ❌ (8−4.0 < 6.0) |
| B | 5.5 | 2.75 | 5.80 | ❌ |
| F | 5.0 | 2.50 | 4.43 | ❌ |
| E | 1.0 | 2.50 | 2.57 | ❌ (chronic) |

6/8 users' derived confirmedCap cannot fully land at their 90th-percentile IOB. **Caveat:** p90-IOB is
pessimistic (confirm shots fire at meal onset when IOB is lower), so this overstates the everyday impact —
but it confirms auto-config never validates maxIOB ≥ confirmedCap + margin. The consistency floor
(`maxIOB := max(carriedMaxIob, confirmedCapU + typicalIObMargin)`) is a real latent gap; it is **not**
user H's cause (his 8 is adequate — the mask is), and would only tame the residual for H/B/F. Recommend it
as a low-priority hardening, secondary to fixing the path-divergence.

---

## ROOT CAUSE (definitive, code-certain) — Simple Mode masks the dosing keys

The three prefs are not reset or rewritten — they are **masked by Simple Mode at read time**:

- `PreferencesImpl.kt:125` (the `DoublePreferenceKey` getter):
  ```kotlin
  override fun get(key: DoublePreferenceKey): Double =
      if (simpleMode && key.calculatedBySM) calculatePreference(key)
      else if (simpleMode && key.defaultedBySM) key.defaultValue   // ← returns the FACTORY DEFAULT
      else sp.getDouble(key.key, key.defaultValue)                 //   ignoring the stored 8/4/1.2
  ```
- All three Boost dosing keys are declared `defaultedBySM = true`:
  `DoubleKey.kt:57` `ApsBoostMaxIob(…, 1.0, …, defaultedBySM = true)`,
  `:77` `ApsBoostV5ConfirmedCapU(…, 2.5, …, defaultedBySM = true)`,
  `:78` `ApsBoostV5CommittedCapU(…, 0.5, …, defaultedBySM = true)`.
- `simpleMode = sp.getBoolean(GeneralSimpleMode, …)` (`PreferencesImpl.kt:63`).

So **whenever Simple Mode is ON, `preferences.get(ApsBoostMaxIob)` returns 1.0** (and the caps 2.5/0.5) —
exactly the observed trio — regardless of his stored 8.0/4.0/1.2. That value flows:
`OpenAPSBoostPlugin.kt:253/1217 (boost_maxIOB)` → both the base engine's tier guards
(`DetermineBasalBoost.kt:1491…1632`) AND `OpenAPSBoostV5Plugin.kt:497 min(boost_maxIOB,max_iob)` → SafetyGates.
Both engines zero together because both read the same masked getter.

**Auto-config is EXONERATED:** it reads these keys via `getIfExists` (`PreferencesImpl.kt:129`, raw
`sp.getDouble`, mask-bypassing) and only ever writes DERIVED values — never factory defaults. It marks
his 8/4/1.2 as user-tuned and keeps them. This is why auto-config "sees" his real values while the dosing
engine, using `get()`, sees the masked defaults — a read-path divergence between the two.

**Trigger (temporal):** the masking is gated purely on `simple_mode` reading `true`. There is **no code
linking a profile-switch percentage to `simple_mode`** (all `GeneralSimpleMode` writers are UI/setup only;
profile-switch events only refresh caches). So the ps=130 correlation is coincidental to a 65-min window in
which `simple_mode` read `true` for user H (most likely an app restart re-initialising it, or a settings
import; on-device, read the `simple_mode` boolean during vs outside the window to confirm). **The masking
mechanism itself is certain; only the reason simple_mode flipped for those 65 min needs device confirmation.**

**This also explains user E** (Part C1): E runs in **Simple Mode**, so his boost_maxIOB is *permanently*
masked to 1.0 — his V6 amplification has been read-suppressed the whole time, not a transient event.

### FIX (code)
Stop Simple Mode from silently defaulting safety-critical dosing ceilings: **drop `defaultedBySM = true`
from `ApsBoostMaxIob`, `ApsBoostV5ConfirmedCapU`, `ApsBoostV5CommittedCapU` (`DoubleKey.kt:57/77/78`)**, or
have the engine read them via a raw/`getIfExists` path (as auto-config already does) so a Simple-Mode user's
configured caps/ceiling are honoured by the doser. Without this, ANY Simple-Mode Boost user silently runs
maxIOB=1.0 / committedCap=0.5 / confirmedCap=2.5 regardless of what they set.

---

## Caveats
- Mechanism (Part A), root cause (Simple-Mode mask, `PreferencesImpl.kt:125` + `DoubleKey.kt:57/77/78`),
  and counterfactual (Part B) are certain from console_error + gate strings + clamp/brake arithmetic +
  the code. The one residual unknown is WHY `simple_mode` read true for user H's 65-min window (no code
  links it to the profile switch) — confirm on-device by reading the `simple_mode` boolean in vs out of
  the window; the masking itself does not depend on that answer.
- Part B counterfactual excludes the decel brake (those cycles were CONFIRMED/COMMITTED still climbing,
  decel≈1.0) and assumes the caps also unmask (they do — same cycle).
- C2 "reachable" uses p90-of-all-IOB (pessimistic vs confirm-time IOB); flags the gap, not everyday size.
- H aggression knob 1.30 (from telemetry). E's chronic maxIOB=1.0 is a distinct issue from the transient
  mask and should be triaged separately.
- DB refresh since 07-07 failed on oref-site U018 only (no boost impact); H captured through 21:19.
