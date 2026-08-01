# Boost V6 — how it works

*Detail page. For the short version, the three user levers, and getting started safely, see the
[main README](../README.md). For the settings that auto-config sets for you, see
[Advanced settings](v6-advanced-settings.md).*

Boost keeps the entire AndroidAPS engine — basal, DynISF / `future_sens`, glucose predictions
and every safety gate — and replaces only the SMB (super-micro-bolus) decision with a
meal-aware state machine plus a layer of personal context (activity, heart rate, sleep). Nothing
else about how AndroidAPS runs your pump is touched.

The single difference that matters: stock AndroidAPS sizes one isolated micro-bolus each cycle,
from scratch. Boost V6 carries a *meal hypothesis* across cycles and scales dosing to its
confidence.

## The meal-hypothesis state machine

```
IDLE → OBSERVING → CONFIRMED → COMMITTED → RECOVERING → IDLE
```

- **IDLE** — no meal in play; dosing falls back to what the base engine would do.
- **OBSERVING** — a rise is building; dose lightly (a small test dose) while evidence accrues.
- **CONFIRMED** — a meal is recognised (BG delta + acceleration + an ML meal-likelihood score +
  time-of-day + sustained rise + not-exercising, minus a recent-low penalty); deliver the one
  discretionary catch-up commit shot.
- **COMMITTED** — hold a measured per-cycle dose while the meal is clearly active.
- **RECOVERING** — deliberately wind down as insulin takes hold, rather than re-deciding from
  scratch and re-dosing a meal that is already handled.

The headline trade-off versus the old tier ladder: V6 deliberately holds back in OBSERVING
where the tiers might already fire, then catches up hard in CONFIRMED once the meal is real. This
is the central design choice, and it cuts both ways. *Confirming — and dosing — earlier in the cycle
means acting on CGM evidence that is more speculative:* a rise only a few minutes old that might still
fizzle. Waiting a cycle costs a slightly higher peak but avoids dosing into a rise that never becomes
a meal. Boost's default posture is to wait for proof; the opt-in "aggressive early confirm" lever
(see [advanced settings](v6-advanced-settings.md)) moves that line earlier for users who can absorb
the occasional early dose that wasn't needed.

> 👁️ See it live: the Boost Overview V2. Enable *"Use Boost Overview V2 (dark theme)"* in the
> Overview plugin settings. It is the live window into V6's internals — the meal-hypothesis state
> with its action multiplier, meal score and aggression budget; the active brakes and safety gates;
> DynISF, IOB and TDD; the activity / exercise state; and a steps + heart-rate graph. It answers
> *"why is V6 dosing the way it is right now?"* at a glance.

## The dosing core

Two cascade controls bound the state machine:

- an **aggression budget** — a per-cycle insulin sizing base, floored at 30% of oref's own
  requirement and (apart from the Sensitivity lever) capped at roughly oref's requirement. It is
  the *base* the state multipliers scale, not itself the burst ceiling — the hard per-burst limits
  are the dose caps below; and
- a **deceleration brake** — eases off (down to a 30% floor) the moment BG stops *accelerating*, so
  Boost stops *pushing* insulin into a meal that is already turning. It stays off while BG is still
  climbing fast.

Two risk inputs pull dosing back *before* trouble, not after:

- the **ML hypo-risk score** throttles the aggression budget — higher modelled risk allows *less*
  insulin. It is a safety reducer only: it can never amplify a dose (see
  [safety & validation](v6-safety-and-validation.md)); and
- a **recent-low penalty** damps the meal-confirm score for a window (the trailing-60-minute BG
  minimum) after any low — so a rescue-carb rebound is not eagerly read as a new meal.

## The July-2026 safety guards

Several guards bound the state machine's edges. Each only ever *removes* insulin.

- **Non-meal cap** — in IDLE / OBSERVING / RECOVERING, V6 never doses more than the base engine
  would on the same inputs; only a confirmed meal hypothesis (CONFIRMED / COMMITTED, or the
  opt-in velocity-budget floor) can out-dose the base.
- **Commit-shot worth check** — the one-per-meal CONFIRMED catch-up shot is only spent when the
  velocity-scaled dose would beat a routine hold cycle; otherwise V6 keeps observing rather than
  burning its confirm on a trivial upswing.
- **Rescue-carb guard** — the single-cycle fast-carb confirm is suppressed for an hour after any
  BG below 80 mg/dL, so a rescue-carb rebound is never treated as a new meal.
- **Post-rescue restraint** — for 45 minutes after any BG below 75 mg/dL, a confirmed meal
  hypothesis can't out-dose the hypo-restrained base — a rebound inherits the base engine's
  post-rescue restraint instead of a full catch-up shot.
- **Composed rebound guard** — in that same 45-minute post-low window, whatever SMB the fallback
  tiers would deliver is scaled down by glucose: about 30% below 6.7 mmol/L (120 mg/dL), ramping
  back to full by 9.4 mmol/L (170 mg/dL). This closes the *confirm-crash* — a modest rebound after a
  low being over-treated and then crashing a second time.
- **Elevated-HR exercise guard** — during hard exercise the loop stops *adding* insulin through the
  inactivity path: the activity classifier no longer mis-reads a moving-but-low-step session
  (30–99 steps + HR zone 3–4) as resting, and when the heart rate says exercise the loop
  suppresses the inactivity profile-raise and lifts the target to ~160 mg/dL rather than raising
  the profile. (This is the inactivity branch specifically; the base SMB path is not hard-zeroed.)

Every stock AndroidAPS safety gate still runs underneath — most importantly the hard
minGuardBG gate, which blocks dosing into a projected low. On the V6 path its threshold is your
configured low-glucose-suspend (LGS) threshold, defaulting to 80 mg/dL when the profile supplies
none; the base engine's own SMB-disable threshold is lower still.

## The learners (personal context)

These shape sensitivity and timing only — never the guardrails. Blend with autosens rather than
stacking on top of it, and act on *deviation* from your own baseline while keeping the clinical
absolutes fixed.

- **Activity load** — a personal daily-step baseline; high-activity days would raise ISF, sedentary
  days lower it. *(Currently shadow — logs what it would do.)*
- **Heart rate & sleep** — detects sleep and shapes overnight dosing; see
  [Heart rate & sleep](v6-heart-rate-and-sleep.md).
- **Meal-time learning** — an anticipatory pre-meal target around habitual meal times. *(Shadow.)*
- **Anticipation (routine learning)** — a per-user onset-hazard model that learns *when* you tend to
  eat and exercise, from your own history (refit periodically, never inside the dosing loop), and
  predicts the next meal or walk about 45 minutes ahead. It exists to make future anticipatory
  dosing *retractable* and per-user. *(Shadow — logs `anticip=` telemetry, doses nothing.)*
