# Design spec — exercise-anticipation gentle hypo-prep

_2026-07-09. Draft design, informed by `ANTICIPATION_REPORT.md` (thread A) + the de-artifacted recovery finding. Calibrated to a MODEST expected effect — not oversold._

## What survives to justify this

- **Detection is validated (thread A):** the habit prior `P(exercise | weekday, time-of-day)` predicts activity at OOS AUC 0.85 and **pre-arms 55% of exercise episodes ~55 min before onset at 0.63 precision** — it genuinely *leads* Boost's reactive steps signal.
- **The hypo it prevents is real but modest:** post-exercise/peri-exercise hypo hazard is ~1.2× baseline (de-artifacted), and activity-driven lows are 47% of all low-time. So the *population* impact is meaningful even though the *per-episode* effect is modest.
- **Honest framing:** this is a small, opt-in, safety-oriented nudge, not a step-change. Expected benefit is a modest reduction in exercise-associated lows for *habitual* exercisers; it does nothing for irregular ones (e.g. user B, 0% pre-armed).

## Mechanism

A **confidence-gated, per-user, gentle pre-exercise damper** that arms *before* the reactive steps signal would, and hands off to the existing reactive protection once steps actually rise.

1. **Habit model (per user, updated offline/nightly):** empirical-Bayes rate per `(weekday, 30-min bin)` — Beta posterior, shrunk toward the user's base rate (calibrated for sparse cells). Stored as a compact lookup, refreshed nightly. No online training in the dose path.
2. **Arming (Bayesian decision under asymmetric loss):** arm the prep for the next ~60 min only when the posterior **lower credible bound** (not just the mean) exceeds a per-user threshold — so we act only when the habit is *reliably* present. Asymmetric loss encodes hypo ≫ mild high.
3. **The prep action (gentle, dampen-only):** while armed and steps are still quiescent — a small target raise (e.g. +10–15 mg/dL toward the existing post-exercise recovery target of 144) and/or a modest SMB dampening (a fraction of the existing `POST_EXERCISE_RECOVERY_SCALE` 0.5). **Never adds insulin; only eases.** Bounded and small by construction.
4. **Hand-off:** the moment the reactive steps signal fires (real movement), the existing peri-/post-exercise protection takes over; the anticipatory prep just bought lead time.

## Safety & gating (mandatory)

- **Opt-in, default OFF.** Per-user, and auto-disabled for users the habit model can't predict (low pre-arm rate / low precision — e.g. B).
- **Dampen-only:** the prep can only reduce insulin / raise target, never increase — so a false prep (37% of arms) costs at most a small transient high, never a low.
- **Confidence gate:** arms only on the posterior lower-bound, so low-certainty windows don't fire.
- **Fail-closed:** no habit data / degraded feed → no prep (behaves exactly as today).
- **All absolute safety unchanged** (maxIOB, caps, kill-switches).
- **Counterfactual caveat:** we cannot simulate the BG under the prep, so a live rollout must be shadow-logged first (log "would-arm" + outcome) and priced before it doses — same discipline as every dosing change.

## Why not just rely on the reactive signal

Boost already reacts to steps ~3 h ahead of a low — but that fires *at movement onset*. The habit prior fires ~55 min *before* onset, on habitual episodes. For a scheduled hard workout (BG already dropping by the time steps register), that lead is where the avoidable lows are. The value is bounded (modest per-episode effect, only habitual users) but real and asymmetric-safe.

## Recommended path

1. **Shadow-log first:** ship the habit model + "would-arm" telemetry (no dosing) → validate on live data that arming precedes real exercise and that the dampen-only action would have helped (priced against observed lows), per user.
2. Only if the shadow shows a clean, per-user benefit → enable the gentle action, opt-in, for habitual exercisers.
3. Tie the post-exercise side to the (minor) recovery-window extension from `RECOVERY_AND_SENSITIVITY_REPORT.md` (extend V4's 2h → ~4h taper) so pre- and post- are coherent.

**Expectation:** a modest, safe, population-meaningful reduction in exercise lows for habitual exercisers — not a headline TIR jump. Worth the shadow-log to confirm; not worth overselling.
