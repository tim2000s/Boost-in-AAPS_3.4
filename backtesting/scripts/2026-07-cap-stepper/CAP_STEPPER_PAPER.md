# An evidence-gated cap-stepper for Boost: two policy-replay experiments, and why auto-config is already the controller

_Boost dosing research note — 2026-07-08. Cohort: 8 anonymised users (self + A–H) on the V6 engine (`openAPSBoostV5`). Data: local TimescaleDB `oref.boost_decisions`, ~394k decision-cycles, span 2026-02 → 2026-07. Reproduce with `cap_stepper_replay.py`._

## Abstract

We tested whether a per-user controller that steps a dosing **cap up** on accumulated evidence of *under-dosing* — cap-binding clip + sustained high + retrospective need, in the low-IOB "safe-to-add" slice, with an immediate revert on hypo and a hard TBR-headroom gate — beats the static auto-config caps. Two tracks were replayed over real telemetry: the **committedCap** (sustained-hold cap) and the **confirmedCap** (meal-response cap). Both are **NO-GO** as general mechanisms, in mirror-image ways: committedCap binds often but at high IOB where adding provokes lows (33–50% of cap-changes reverted); confirmedCap is safe to add to but rarely binds (1–5 raises cohort-wide over six weeks). The absolute TBR-headroom gate correctly froze the three users for whom arming the stepper would have been dangerous (safe-slice pre-low 12–29%). The achievable benefit is already captured by auto-config's initial cap derivation plus the existing raise-guard.

## 1. Motivation

Cohort work established that per-user caps *matter*: some users are cap-clipped and under-dosed, others are TBR-heavy and correctly held. A natural next step is to make the cap **adaptive** rather than derived-once — a Bayesian-flavoured stepper that raises the cap after N instances of "we hit the cap and stayed high," and reverts immediately on a resulting hypo. This note asks whether such a controller earns its place, and — critically — **how often the hypo-revert actually fires**, since a revert *is* a low we caused.

## 2. Method

**Honest scope.** No glucodynamic model exists, so the BG trajectory under a *higher* cap is unobservable — which is exactly why Boost prices insulin empirically rather than simulating it. We therefore do **not** simulate counterfactual BG. Instead we run a **policy replay** over the real telemetry:

- Triggers are detected from actual per-cycle fields (delivered dose, state, IOB, eventual-BG, target, steps, TDD).
- The stepper's raise/revert dynamics are walked against the **actual forward-BG** as the outcome oracle: a low that really followed an extra-insulin cycle is the revert signal; a high that really followed is the buy-back target.
- Added insulin is **priced** against observed lows (the established two-test method), not assumed harmless.

The load-bearing outputs are therefore the **revert frequency** and the **safe-slice size**, both directly observable and bias-free. (Any TIR buy-back is an upper bound and is not claimed.)

**The trigger** (per cycle, for the track's cap):

1. **cap binding** — final dose ≥ 98 % of the cap on a cycle of the track's state (COMMITTED for committedCap; CONFIRMED for confirmedCap);
2. **sustained high followed** — any of BG at +30/+60/+90 min exceeds 180 mg/dL;
3. **retrospective need** — the cycle's own eventual-BG exceeded target + 15 mg/dL (the model itself expected to stay high);
4. **low-IOB safe slice** — IOB < 5 % of TDD (the ~6.7 %-pre-low regime, not the ~19 % recovering regime);
5. **not exercising** (steps/hr proxy).

**The policy.** Accumulate 10 qualifying clips → raise the cap ×1.15 (ceiling 1.5× auto-config), then a 24 h cooldown. After a raise, any real low within 3 h of an extra-insulin cycle → **revert to auto-config** (immediate fall-back), cooldown. During exercise/recovery the cap is clamped to auto-config.

**Arming gate.** The stepper is active **only** for users with absolute TBR headroom (trailing-14d TBR<70 < 3.5 % **and** <54 < 0.8 %). Users over the gate are frozen at auto-config.

## 3. Experiment 1 — committedCap (sustained-hold cap)

| user | armed | clips | safe-clips | qualifying | raises | reverts | final × | safe pre-low % |
|---|---|---|---|---|---|---|---|---|
| self | yes | 141 | 49 | 24 | 2 | 2 | 1.00 | 10.3 |
| A | yes | 149 | 39 | 13 | 1 | 1 | 1.00 | 0.0 |
| B | no | 56 | 47 | 23 | — | — | 1.00 | 11.8 |
| C | no | 137 | 123 | 17 | — | — | 1.00 | 25.0 |
| D | no | 105 | 105 | 6 | — | — | 1.00 | 28.6 |
| E | yes | 8 | 8 | 0 | 0 | 0 | 1.00 | 0.0 |
| F | yes | 44 | 26 | 10 | 1 | 0 | 1.15 | 9.1 |

**Cohort:** 4 raises, 3 reverts — **43 % of cap-changes were reverts.** Robust across a parameter sweep (revert share 33–50 % for window 5/10, IOB<3–5 % TDD, high-threshold 160/180). Only one user (F) held a single raise without a low.

**Reading.** committedCap binds constantly, but the COMMITTED hold is the *recovering tail* — high IOB. The low-IOB safe slice is small (self: 49 of 141 clips), and even it goes low ~10 %+ of the time. Two of the frozen users (C, D) show why the gate exists: their safe-slice pre-low is 25–29 %.

## 4. Experiment 2 — confirmedCap (meal-response cap)

| variant | raises | reverts | revert share |
|---|---|---|---|
| window 10 (default) | 1 | 1 | 50 % |
| window 5 | 3 | 1 | 25 % |
| window 5, IOB<3 % | 2 | 1 | 33 % |
| high threshold 160 | 2 | 1 | 33 % |
| window 5, high 160 | 5 | 1 | **17 %** |

**Reading.** The revert rate is **materially better** than committedCap (17–33 % vs 33–50 %) and at the permissive end tips to raises-outweigh-reverts — confirming the design intuition that CONFIRMED fires early, at low IOB, where adding is genuinely safer. **But** confirmedCap barely *binds*: it is set generously (2.5–3.0 U), so meal responses rarely reach it (self: 12 CONFIRMED clips vs 141 committedCap clips). The lever is 1–5 raises cohort-wide over six weeks, and **every revert came from one user (A)**. Most users never trigger it.

## 5. The mirror-image failure

The two tracks fail for opposite reasons:

| | binds often? | safe to add? | outcome |
|---|---|---|---|
| **committedCap** | yes | no (high-IOB tail) | fires, then reverts (lows) |
| **confirmedCap** | no (generous cap) | yes (low IOB) | almost nothing to act on |

There is no track that both **binds** and is **safe** to add to. The design intuition — move the trigger to the low-IOB response — was correct; it is just that in a tuned cohort the low-IOB cap is not the binding one.

## 6. Conclusion

**Auto-config + the raise-guard is already the controller.** An outcome-triggered stepper adds churn where the cap binds (committed) and finds nothing where it is safe (confirmed). This confirms, at the per-user evidence-gated level, the earlier rejection of a *blanket* committedCap raise — and shows the narrow gated form does not rescue it.

The **one** scenario the stepper would help is a user whose confirmedCap is genuinely **too low** for their meals (repeated low-IOB clips on real highs) — but auto-config already sizes confirmedCap from that user's bolus history (n ≥ 10), so the initial derivation covers it without a running loop. The finding is therefore an argument for auto-config's sizing, not for an online stepper; and it upholds the standing constraint against a training loop in the dose path.

**Engine note.** All fields are `boostv5_*` — the live V6 engine. V7 is shadow-only (no live caps to replay) and sizes distributionally rather than clipping a cap, so this question dissolves rather than transfers under V7; the equivalent V7 question is whether its distributional sizer should widen its upper tail on the same evidence — a separate experiment.

## Reproducibility

```
python3 cap_stepper_replay.py --track committed     # Experiment 1
python3 cap_stepper_replay.py --track confirmed     # Experiment 2
# sweep any of: --window --step --iob_safe_frac --high_mgdl --cooldown_h ...
```
Raw per-run tables in `CAP_STEPPER_REPORT.md` (committed) and `CAP_STEPPER_REPORT_confirmed.md`.
