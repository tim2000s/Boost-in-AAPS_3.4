# Boost V6 — safety, "no training" & validation

*Detail page. See the [main README](../README.md) for the overview. The full data-analysis method
and tooling live on the [backtesting page](../backtesting/README.md); this page gives the
essentials and the honest evidence picture.*

## There is no training loop in the dose path

This is the point people most often get wrong about Boost, so it is stated plainly:

- **The dose decision is a deterministic, rule-based state machine.** It is *not* a model trained to
  output insulin. Nothing in the dosing path is fit to data, learned online, or a black box. Given
  the same inputs it produces the same dose, and every branch is readable in source.
- **Two small on-device trained models feed the decision — neither outputs insulin.** The
  hypo-risk score (a gradient-boosted tree validated *leave-one-user-out*, so it is scored on
  users it never saw in training) throttles the aggression budget and can only ever *reduce*
  delivery. The meal-likelihood score is one bounded input (weight 0.20, renormalised away when
  the model is unavailable) into the otherwise rule-based meal-confirm score — it can help recognise
  a meal *earlier* (which necessarily means acting on more speculative CGM evidence), but every dose
  that follows passes the same caps and gates, and in non-meal states Boost stays capped at what the
  base engine would do. Neither model can *add* a dose or relax a limit.
- **Personalisation ≠ training.** Auto-config and the learned baselines derive *suggestions* from
  your own history — they tune settings, they do not learn the dose.
- **Validation is replay on real history, not curve-fitting.** Candidate changes are scored against
  real recorded decisions before any dosing code ships — there is no parameter sweep optimising a
  glucose objective on the same data, which is exactly how dosing algorithms overfit.

## Why changing a dosing algorithm is treated as a clinical-equivalence problem

Users co-adapt to an algorithm's behaviour (manual pre-boluses, knob settings, meal habits). A
"correct" fix can make control *worse* until the user re-adapts. So every change is classified before
it ships, following a published taxonomy of safe algorithm updates in automated insulin delivery
(*"Safe Algorithm Updates in Automated Insulin Delivery Systems"* — see the backtesting page for the
full citation):

| class | meaning | how it is treated |
|---|---|---|
| **Factual** | objective, wrong-by-computation | fix immediately (e.g. an inverted knob, a null-returning method) |
| **Heuristic** | co-adapted with the user's behaviour | transition gradually, shadow-first (e.g. dose aggressiveness, meal-confirm timing) |
| **Computational** | numeric / port differences | verify equivalence (e.g. the Android↔Trio port) |

**The bar:** a change should be *clinically equivalent or better* — validated on real history —
before it doses for anyone. Two rules fall out: don't flash an unvalidated dosing change right
before the user is away (if it can't be watched, it doesn't ship — unless it's pure shadow); and
shadow-first for anything heuristic.

## The backtesting toolkit

All scripts read Nightscout `devicestatus`, which already logs paired outputs (the actual dose,
the V6 shadow/active decision, and a `base would=` counterfactual), so they reconstruct decisions
from data we already have rather than re-implementing the algorithm.

| script | what it answers |
|---|---|
| **`shadow_equivalence.py`** | Per-component agreement/divergence between two algorithm paths — "how different is the change, and where?" |
| **`replay.py`** | Re-runs a candidate change over real history and scores it (meals caught earlier vs false fires vs sleep fires) — lets us reject unsafe designs before writing dosing code. |
| **`parkes_grid.py`** | Parkes Error Grid of Boost's predicted BG vs the BG that actually occurred — forecast accuracy. |
| **`episode_impact.py`** / `cold_idle_dose_validation.py` | First-order / counterfactual BG-impact estimates around real low/high episodes (open-loop, clamped — not a simulation). |

Worked example — the fast-carb fast-path. A fast carb spike-then-crash was observed where V6 sat
in OBSERVING one cycle too long. Classified *heuristic*. A one-cycle promotion on a sharp
accelerating rise was designed — but replay rejected the obvious rule (it fired during sleep and
~2×/day falsely). Adding corroboration (require the meal score *and* awake *and* not-exercising) gave
zero sleep fires, half the false rate, and still caught ⅓ of meals ~15 min earlier. The replay chose
the safe design before any dosing code was written. A separate proposed cold-IDLE fast-path was
likewise reverted after a full-cohort re-run didn't support it.

## Robustness, in one list

- **Every stock AndroidAPS safety gate is unchanged** — Boost only replaces the SMB decision.
- **Shadow mode is a real execution path**, not a simulation — the same code runs and logs without
  touching the pump, so what you watch *is* what would dose.
- **Auto-config is suggestion-only and only ever tightens safety knobs** — see
  [advanced settings](v6-advanced-settings.md).
- **Caps are layered** — per-shot magnitude caps *and* a rolling-hour cumulative cap.
- **Android and the Trio (Swift) port are kept in numeric parity**, checked line-for-line.
- **What is *not* claimed:** there is no glucose-outcome simulation and no clinical-equivalence pass
  on simulated glucose. The tools validate *decisions and forecasts*, plus real single-user outcomes
  — not a population glucose-outcome guarantee. This is an experimental dosing algorithm; a shadow
  mode (the "Boost" plugin) is available for anyone who wants to watch before going active, but the
  supported path is Boost V6 active, seeded from your own history.

## Testing & evidence

A single developer running V6 active on their own pump for months, plus a small cohort running it
in shadow. This is real-world experience and shadow analysis, not a clinical trial.

Developer's own V6-active glycaemia (honest, full picture):

- **Time in range (70–180): ~85%**, mean ~6.9 mmol/L.
- **Normal weeks: within hypo targets** — TBR<70 ~2.5–3%, severe <54 < 0.5%.
- **High-activity weeks** (multi-day festival / heavy training): hypo above target. The exercise
  lows are the loop's hardest case — most are activity-driven, and the loop's only lever is to
  withhold insulin, which it has often already done. Two July-2026 changes help: the loop now
  suppresses the inactivity insulin-add and lifts the target during elevated-heart-rate exercise, and
  the composed rebound guard prevents the post-rescue confirm-crash. Cohort analysis shows the
  residual post-meal-exercise low is a *carbohydrate-counterweight* effect (exercise's
  insulin-independent glucose uptake landing when the meal's carb flux is thin), not over-dosing —
  the next lever is per-user *anticipatory* insulin withdrawal, which the anticipation shadow is
  banking data toward. Watch this if you run it through heavy exercise.

Period reports live in `backtesting/`.
