# Boost V6 — advanced settings (set for you on install)

> You almost certainly do not need to touch anything on this page. The first time Boost V6 runs,
> it derives these settings from your own recent dosing history and writes sensible per-user
> values. This page exists so you can understand *what* each one is and *how* the value was chosen —
> not because you need to set them. The three dials you might actually adjust are on the
> [main README](../README.md#the-three-levers).

The settings live under the Boost plugin preferences; the advanced ones sit behind the "Advanced"
sub-screen. Defaults shown in brackets.

> **Simple Mode note:** the Boost preference *screen* is hidden while AndroidAPS is in Simple Mode,
> but your saved Boost dosing settings still apply — Boost reads them through a dedicated bypass,
> so they are no longer masked back to factory defaults.

---

## How auto-config sets these (first activation)

The first time V6 runs active, Boost seeds its settings from your own recent dosing history
(last 14 days) rather than dropping you onto generic defaults. The principle: dose calibration is
co-adapted to the individual, so the safe onboarding is to start where your prior dosing left
off — not a cold jump to a stranger's numbers. It reads only dosing history + glycaemia, so it
works from any prior engine (standard oref/AndroidAPS, not just Boost).

That history is read from the AndroidAPS database — so it is available immediately if you
upgraded in place, restored your database, or have Nightscout sync (NSClient) enabled (its first
load backfills up to ~100 days of your treatments and CGM into the database). On a genuinely empty
database with no sync, there is nothing to read: Boost holds conservative factory defaults and
retries each cycle until enough history accrues. There is no separate "import from Nightscout" step
inside Boost — it relies on the same local database the rest of AndroidAPS uses.

**The guard-rails:**

- Runs in the background while V6 is active. Rather than a single global "done" flag, each setting
  resolves once, independently — a value is written the first time there is enough data to derive
  it, and left alone thereafter. If there isn't enough data yet, it does nothing and retries next
  cycle.
- **Suggestion-only** — it writes a setting only if you haven't already changed it from a
  factory default (*any* factory default that setting ever shipped with, so a value carried over
  from an older build still counts as untouched). It never overrides anything you have tuned.
- Needs **≥ 7 days of data and ≥ 1500 CGM readings**; otherwise it waits.
- **Never auto-raises aggression** above neutral on day one; safety knobs only ever *tighten*.
- **Wrapped so any failure is logged and swallowed** — it can never block or alter the dose path.
- It **logs the full reasoning and notifies you** of exactly what it set and why.

### How it determines each setting

Over the last 14 days it gathers your true TDD (basal + bolus), your bolus and SMB sizes,
your time-below-range (% < 70 and % < 54 mg/dL), and your max-IOB / max-bolus limits. Then:

| Setting | Rule |
|---|---|
| **HypoCaution** (1.0–2.0) | `clamp(1.0 + max(0, TBR<70% − 4)/4 + max(0, TBR<54% − 1)×0.5, 1.0, 2.0)` — climbs above 1.0 only as time-low exceeds the consensus targets (4% / 1%). |
| **Aggression** (0.7–1.6) | `0.85` if hypo-prone; `0.92` if TBR<70% > 4%; else 1.0. Auto-config never sets it above 1.0 — the widened ceiling of 1.6 is for manual tuning only. |
| **Confirmed cap** (0–7.5 U) | `clamp(max(p90 of meal boluses, p95 of SMBs), 1.5, 7.5)` — covers your biggest *typical* single dose. The meal-bolus p90 only participates with ≥ 10 manual boluses in the window; below that the cap comes from the SMB p95 alone. |
| **Committed cap** (0–2.5 U) | `clamp(max(p75 of SMBs, TDD/40), 0.25, 2.5)` — your routine per-cycle hold. |
| **Cumulative SMB cap / 60 min** | `clamp(Confirmed cap + 2×Committed cap, 1.0, 10.0)` — one confirm shot plus two holds per hour, computed from the final operative caps (a value you kept sizes the budget, not a derivation that never applied). |
| **Max IOB / Bolus cap** | carried from your existing limits (clamped to range). |
| **Fast-carb confirm** | off if hypo-prone, otherwise on. |
| **Aggressive early confirm** and Velocity budget | on only for a well-controlled history (see below); off otherwise. |

Raise-guard. A dose-cap raise (Confirmed / Committed / Cumulative going *up* from the
current value) is not auto-applied when your 14-day time-below-range is elevated — held if
time-below-70 exceeds 4%, and also held by a severe co-guard if time-below-54 reaches 1%
even when the <70 figure is fine. Held raises are surfaced as a *suggestion* in the notification
instead. Lowerings and all non-cap tightenings always apply.

"Hypo-prone" = TBR<54% > 1.5% or TBR<70% > 6%. "Well-controlled" (the gate for the
insulin-adding opt-ins) is a much stricter cut: TBR<70% < 1.5% *and* TBR<54% < 0.3%. A
well-controlled user lands on a neutral config with the opt-ins available; a low-prone user gets
gentler aggression, more hypo damping, tighter caps, fast-carb off, and no opt-ins — all
conservative.

Auto-config-managed switches. New dosing toggles are never shipped default-on for everyone;
auto-config derives each one's per-user default. Any switch that can *add* insulin (aggressive early
confirm, velocity budget) is enabled only for the strict well-controlled cut above, and stays
off otherwise. You can always override in Advanced.

Validation. The derivation was checked against 12 real users (400–720 days each): the rules
were applied to each user's real history, the resulting knobs were run through the V6 engine over
that user's own logged cycles, and the dosing was probed for danger. Result: no dangerous dosing;
well-controlled users ran at neutral, and for hypo-prone users the protective knobs *reduced*
dose-into-low events 15–24%. *(That replay is open-loop, so absolute insulin totals from it are
inflated artefacts, not real closed-loop amounts.)* The derivation is in line-for-line parity with
the Trio (Swift) port.

---

## The advanced settings, one by one

### Per-shot dose caps
- **CONFIRMED dose cap** `0–7.5 U` (2.5) — hard limit on the meal-confirm commit shot.
- **COMMITTED dose cap** `0–2.5 U` (0.5) — hard limit on the per-cycle holding SMB.

### Frequency cap
- **Cumulative SMB cap / 60 min** `0–10 U` (10) — a rolling-hour ceiling across all SMBs. The
  factory default is deliberately non-binding; auto-config tightens it to your history. `0` disables
  it. Enforced on the V6 override path as well as the base engine, and clamped to the system max-IOB.

### Overall insulin limits
- **Max IOB** `0.1–12 U` and Bolus cap `0.1–10 U` — the lower of Boost's Max IOB and AndroidAPS's
  Max IOB is V6's hard headroom clamp.

### Meal-recognition options
- **Fast-carb confirm** (on) — a sharp, accelerating, score-corroborated rise jumps straight to
  CONFIRMED in one cycle. Suppressed within an hour of a low (< 80 mg/dL). Auto-config turns it off
  for a low-prone history.
- **Aggressive early confirm** (off) — brings the meal confirm forward a cycle when the score is
  already convincing, for users who otherwise peak before the catch-up shot lands. Understand the
  trade-off before enabling it: confirming a cycle earlier means *delivering the meal bolus sooner,
  on CGM evidence that is by definition more speculative* — a rise that is still only a few minutes
  old and might yet fizzle. You are buying a lower late peak at the cost of a higher chance of dosing
  into a rise that doesn't become a meal. That is exactly why it is auto-config-managed and switched
  on only for a well-controlled history — the users who can absorb the occasional early dose that
  didn't need to happen.

- **Acceleration primer** (`ApsBoostV5PrimerCapU`, default 0.0 = off) — when glucose is *accelerating*
  hard in OBSERVING (before the meal has confirmed), the primer delivers a small anticipatory dose to
  get ahead of a fast rise instead of waiting a full cycle. Like the setting above, this is
  *delivering insulin earlier on more speculative CGM evidence* — so it is made safe two ways. First,
  **confirm-net**: any primer insulin that fired is credited against the eventual CONFIRMED
  catch-up shot, so a meal's *total* net-extra is bounded to about one base dose no matter how many
  primers fizzled first (this is why it validated fizzle-safe — only ~+0.9% extra low risk). Second,
  **safety-routed delivery**: auto-config sizes the primer from your own routine SMB (a fraction of
  the Committed cap, capped at 0.6 U) and routes it as a **bolus for a well-controlled history** but as
  a **retractable temp-basal for everyone else** — a temp-basal unwinds if the meal doesn't
  materialise, a bolus cannot. `ApsBoostV5PrimerBolusMode` forces the bolus route if you want it.

### Aggression levers (not guards)
- **Velocity budget** (off) — puts a small floor under the velocity
  factor so a fast rise isn't throttled to nothing. Auto-config-managed; on only for well-controlled.
- **Phase-3 composed brake floor** (off) — enforces a 25% floor on the composed soft-brake multiplier
  during active meal sessions above 160 mg/dL with eventualBG at least 20 mg/dL above target, fixing the soft-brake
  stack compounding to sub-pump-step zero doses mid-meal. All hard gates and dose caps still apply.
  Unlike the two switches above, this is not auto-config-managed — it is a live runtime,
  fail-closed gate: it self-holds the floor the moment your trailing 14-day time-below-range leaves
  its window (<63 mg/dL below 2.0% *and* <70 mg/dL below 3.5%), so enabling it is safe but it
  only actually acts while you are well-controlled.

### DynISF / `future_sens`
- **DynISF normal target** (99 mg/dL), BG cap (210), velocity (100), adjustment factor
  (100) — shape the dynamic-ISF curve and how far ahead it projects. The activity learner nudges
  *sensitivity* around your baseline rather than overriding the curve.

### Activity *(currently shadow — logs what it would do)*
- **Activity / inactivity %** and the step thresholds (5/15/30/60-min: 420/800/1200/1800) — learn
  a personal daily-step baseline and would raise ISF on high-activity days / lower it on sedentary
  ones.

### Post-exercise & pre-meal
- **Post-exercise recovery** — optional gentler target and dosing scale for a configurable window
  (default 2 h, scale 0.5) after detected exercise.
- **Pre-meal target** (default 72 mg/dL, lead 60 min; off unless enabled) — an anticipatory
  target-lowering ahead of a learned meal time.

### Heart rate, sleep & night mode
See [Heart rate & sleep](v6-heart-rate-and-sleep.md) for the full detail.

---

*The per-control reference for the earlier V1/V2/v4.x plugins (DynISF V1/V2 formulae, the tier
system, UAM Boost tiers, the Acceleration Bolus, BG-source warnings) lives on the
[legacy settings page](boost-v1-settings.md).*
