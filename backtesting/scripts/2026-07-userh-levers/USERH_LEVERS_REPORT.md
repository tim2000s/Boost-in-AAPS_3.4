# User-H lever backtest — A2 (confirm sooner) + C5 (velocity-budget floor)

*2026-07-17. Pre-push two-test-bar pricing for the "user H" lever batch. Script:
`backtest_userh_levers.py` (cohort `oref.boost_decisions`, 60-day lookback, V6-active cycles).*

## Summary

| Lever | Verdict |
|---|---|
| **B3** widen Aggression range 1.3→1.6 | Ships — default unchanged (1.0), no dose change unless a user raises the slider. |
| **B4** raise user H's confirmedCap 4→6 | No-code (his device setting); unclips ~15% of his CONFIRMED shots. |
| **C5** velocity-budget floor (opt-in) | **Ships as opt-in.** Fail-closed 14d-TBR gate blocks C & tim; user H passes cleanly (cell pre-low 5.2% < 5.8% base). |
| **A2** confirm sooner (age −1 → −2) | **FLAGGED — needs a disposition.** 72% of candidates are free timing-moves, but 28% are fizzle-catches (new insulin) at ~base rate; not the cleanly harm-neutral lever age −1 was. Clean for user H, marginal for B/E cohort-wide. |

## A2 — confirm sooner (sustained-score early confirm, age −1 → −2)

A2 lets a meal whose score is confirm-strength on two consecutive cycles confirm as soon as it
enters OBSERVING. Each candidate cycle is split by the **observed** outcome of its OBSERVING episode:

- **MOVED** — the episode reached CONFIRMED anyway ⇒ A2 fires the *same* shot earlier (harm-neutral;
  the early-dosing audit's finding for the −1 step).
- **FIZZLE** — the episode fell back to IDLE without confirming ⇒ A2 would newly dose a meal the
  standard gate let fizzle = genuinely **new insulin** (the priced risk).

| user | base% | candidates | moved | fizzle | fizzle pre-low% |
|---|---|---|---|---|---|
| A | 8.2 | 41 | 32 | 9 | 11.1 |
| B | 25.7 | 72 | 60 | 12 | 33.3 |
| C | 33.4 | 27 | 25 | 2 | 100.0 (n=2, noise) |
| E | 9.0 | 12 | 5 | 7 | 14.3 |
| F | 11.9 | 62 | 45 | 17 | 11.8 |
| **H** | **5.8** | **26** | **12** | **14** | **0.0** |
| tim | 21.6 | 75 | 49 | 26 | 23.1 |
| **POOLED** | — | **315** | **228 (72%)** | **87** | **18.4** |

Pooled cohort base pre-low<70/3h = **15.8%** (n=40,055). So A2's fizzle-catches price at **18.4%
(+2.6pp over base)** — modest new-insulin cost, *not* the 0.0pp of the moved-only age −1 lever.
For the target user **H it is clean** (0.0% on 14 fizzle-catches). Cohort-wide it adds marginal
new insulin (B/E slightly over base; C is n=2 noise).

**Conclusion:** A2 as a **cohort default** does not cleanly clear the two-test bar (it adds new
insulin at ~base rate without a demonstrated mechanism fix). It IS clean for user H. Dispositions:
make A2 an **opt-in toggle** (sibling to the fast-carb confirm; ships safe, H opts in), **tighten**
it (e.g. require a 3-cycle streak / higher offset to cut fizzles), or **revert to age −1** (the
shipped, audit-validated step). Recommend the opt-in toggle.

## C5 — velocity-budget floor (budget≈0 high tail, opt-in + fail-closed 14d-TBR gate)

Delivers `min(0.5U, committedCap)` on `budget≈0 ∧ BG>180 ∧ state≠RECOVERING ∧ awake ∧ !postRescue`,
out-dosing V1 via the non-meal-cap exemption, behind the per-user toggle AND the same fail-closed
14d-TBR gate as the composed floor (TBR<63<2.0% ∧ TBR<70<3.5%).

| user | gate | 14d TBR<70 | 14d TBR<54 | base% | cells | U/day† | cell pre-low% | verdict |
|---|---|---|---|---|---|---|---|---|
| A | pass | 1.40 | 0.13 | 8.2 | 296 | 9.60 | 10.8 | pass |
| B | pass | 2.71 | 0.23 | 25.7 | 133 | 4.24 | 8.3 | pass |
| C | **BLOCK** | 5.38 | 1.33 | 33.4 | 52 | 3.66 | 9.6 | gate blocks |
| E | pass | 1.36 | 0.02 | 9.0 | 8 | 0.23 | 0.0 | pass |
| F | pass | 1.85 | 0.00 | 11.9 | 277 | 8.12 | 18.1 | cells above base — review |
| **H** | **pass** | **0.63** | **0.08** | **5.8** | **115** | **3.57** | **5.2** | **PASS** |
| tim | **BLOCK** | 4.17 | 0.91 | 21.6 | 441 | 11.09 | 20.9 | gate blocks |

† U/day is an **upper bound** — the rolling-60-min cumulative cap and maxIOB headroom (both
enforced live) are not modelled here, so real delivery is materially lower.

**Conclusion:** the fail-closed gate does its job (blocks C & tim, whose TBR would breach the
absolutes). For the target user **H, C5 passes cleanly** (cell pre-low 5.2% *below* his 5.8% base;
modest, cumulative-capped delivery). F's cells price above base but F is opt-in and would not enable
it by default. **C5 ships as the opt-in it is.**

## Caveats

- Associational (identification constraint): no glucodynamic sim, so "pre-low within 3h of the
  cell" prices the *company* the added/moved insulin keeps, not a counterfactual trajectory.
- C5 U/day upper-bounds delivery (cumulative cap + maxIOB unmodelled).
- A2 fizzle/moved split uses the *observed* episode outcome as the counterfactual for "would it have
  confirmed anyway" — a reasonable but not exact proxy.
