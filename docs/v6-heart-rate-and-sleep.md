# Boost V6 — heart rate, steps & night mode

*Detail page. See the [main README](../README.md) for the overview and
[how it works](v6-how-it-works.md) for the dosing core.*

Boost reads heart rate and steps from a wear device (via Health Connect, with a Wear OS step
bridge) and uses them to detect sleep and shape overnight dosing. There is no fixed clock window
doing the dosing — the clock only sets a broad outer band.

## Sleep detection (`SleepStateDetector`, 3 states)

- **PRE_SLEEP** — a time-only pre-warm window before your configured night-start (lead default
  60 min). It engages night-mode SMB suppression *proactively* so you don't carry excess IOB into
  the night.
- **SLEEPING** — entered when, together and held through a hysteresis: heart rate within ~15% of your
  resting HR, steps near-zero, inside the outer night band, and no meal imminent. Because the HR feed
  can be intermittent, a *drought* of HR transmissions also counts as a sleep signal.
- **AWAKE** — exit requires a genuine wake: an HR rise and step activity. A BG rise alone
  never wakes it (REM can lift HR without waking you).

## Learned night window (`SleepHistoryTracker`)

Boost learns your personal sleep-onset and wake times over a rolling 28-day window, but the wake
boundary is anchored to your configured night-end and only allowed to move ± 90 min, and only
learns from *genuine* HR/step wakes. This anchoring stops a feedback loop that used to ratchet the
learned wake ever-earlier when overnight HR data was sparse.

## What night mode does

Night mode (`ApsBoostNightModeEnabled`, optionally auto-triggered by sleep detection rather than a
clock) suppresses SMB while you sleep — `isSMBModeEnabled` returns false, so the loop runs
basal / temp-basal only and the V6 meal-hypothesis override is gated off too.

There is no target raise. The configurable BG offset (default 27 mg/dL) is an *activation
gate*, not a target: night mode only suppresses while BG is below `profileTarget + offset`, so if you
are running high it lets SMB correct. Overnight, Boost therefore runs gentle and basal-led, then
resumes full behaviour on a genuine wake. Optional guards disable night mode if carbs are on board or
a low temp-target is set.
