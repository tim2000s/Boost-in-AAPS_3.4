# V7 Shadow — live instrument for the revised distributional-sizing formulation

**Status: SHADOW-ONLY, read-only, failure-swallowed.** The V7 shadow computes, every Boost
cycle, what the V7 proposal WOULD dose and logs rich telemetry. It never touches the dose path:
delivered dosing is **bit-identical to Boost-V6-experimental** with or without it (asserted by
`V7ShadowSafetyTest`). It follows the V5-inside-V1 shadow pattern: invoked from
`OpenAPSBoostPlugin`'s cycle right after `OpenAPSBoostV5Plugin.runShadow`, wrapped in
`runCatching` at both the seam and inside `V7Shadow` — the shadow can NEVER break a loop cycle.

## NO-GO lineage (why this exists)

The 2026-07 foundation backtests (`backtesting/reports/2026-07_v7_foundation_REPORT.md`;
scripts in `backtesting/scripts/2026-07-v7-foundation/`) reached a split verdict:

- **Substrate (empirical residual quantiles): GO** — odd/even-day coverage within ~2–5 pp of
  nominal for 8 users × 3 horizons. Left tail NOT usable (tens of <70-relevant events per user
  validate a 5% shoulder only — the future chance constraint may only TIGHTEN).
- **Sizing rule as formulated: NO-GO.** Two acceptance criteria must be met by a revised
  formulation before the rule earns anything more than a shadow slot:
  - **(a) cost-ratio sensitivity** — R=4 vs R=10 must produce materially different doses
    (offline: identical for every user; the low arm never bound because the biased q25 shoulder
    never projected <70 — the safety knob did nothing).
  - **(b) bias absorption** — quiet-flat cycles must project ≈0 drift (offline: a +12..+38 mg/dL
    median residual from unannounced carbs polluted ALL residuals, and "quiet" defined by V5
    state alone still contained unannounced meal onsets).
- **Efficacy innovation: no teeth as specced** (d = 0.02) because the innovation was computed
  against the already-adapted `variable_sens` — the sens-frozen variant is the one concrete
  follow-up, instrumented here log-only.

This shadow build is the live instrument for iterating past (a) and (b).

## What is computed (per cycle)

### 1. `V7ResidualTracker` — the substrate (criterion b's instrument)

Rolling per-user residual estimation of the same IOB-only expected-BG model the backtests used
(`v7_common.py`): `projBG(t+h) = bg + (−iob_activity × variable_sens × 5) × h/5` for
h ∈ {30, 60, 90} min. When a horizon matures, `residual = observed − projected` joins a pool.

**Pools are REGIME-CONDITIONED — the debiasing fix for criterion (b):**

| pool | membership (at projection time) |
|---|---|
| `MEAL` | V5 state CONFIRMED / COMMITTED / RECOVERING |
| `NIGHT` | non-meal, local hour ∉ [07..22] |
| `QUIET_FLAT` | non-meal, daytime, **and flat by CGM dynamics** (\|delta\| and \|shortAvgDelta\| ≤ 3 mg/dL/5min) |
| *excluded* | non-meal daytime NOT flat — the unannounced-onset pollution, deliberately dropped |

Windowed ~21 days (size-capped 2000/pool·horizon), persisted as a JSON blob in
`StringKey.ApsBoostV7ResidualPools` (V5StateStore idiom: in-memory cache + async pref write;
corrupt blob → cold start). Deterministic; multi-invoke deduped per 5-min bucket (same rule as
the offline loader). Exposes per-pool quantiles (5/25/50/75/95, numpy-linear) + counts.
**Cold start: pools < 150 samples → the pool logs `…(warming n=…)` and the sizer abstains (null).**

### 2. `V7Sizer` — the revised rule (criterion a's instrument)

Ported EXACTLY from `03_distributional_sizing.py`: the asymmetric linear utility
`loss(d) = E[R·max(0, 70−BG(d)) + max(0, BG(d)−140)]`, h=60 base `bg + BGI5×12`, F_ACT=0.5,
dose grid 0..envelope step 0.05 (ceiling 3.0 U), and the full bounds-not-gates guard structure:
state-multiplier envelope (IDLE 1.0 / OBSERVING 0.3 / CONFIRMED 1.8 / COMMITTED 1.0 /
RECOVERING 0.4 on the live V5 budget), committedCap (COMMITTED), confirmedCap (CONFIRMED),
non-meal v1-bound (rT.units at the seam — still V1's dose), post-rescue exclusion of the
meal-state exemption, rolling cumulative-cap awareness, budget ≤ 0 ⇒ 0.

**REVISED: the predictive distribution.** The offline 3-point {q25,q50,q75} distribution made
cost-ratio insensitivity STRUCTURAL, not just a bias artifact: with ≤3 equally-weighted
quantiles and R ≥ 4, one quantile crossing below 70 always outweighs every high-side quantile
(R×1 > 3), so the argmin is identical for all R ∈ {4,7,10} wherever the envelope isn't binding.
Here the pool's five validated quantiles define a piecewise-linear inverse CDF discretized at 19
equal-probability points (5%..95% step 5%), giving the left tail *graded* mass — the marginal
condition R·P(BG<70) vs P(BG>140) then resolves at different doses for different R. Beyond the
5%/95% knots the distribution is truncated (the report's tail-honesty finding).

**Evaluated at R = 4, 7, 10 EVERY cycle; all three logged** (`boostV7_wouldDoseR4/R7/R10`).
If they remain identical in the field too, the formulation is still wrong — that is the live
criterion-(a) test.

Also computed: `p(BG<70 within 90 min)` off the h=90 pool CDF at the undosed projection
(`boostV7_pLow90`); values left of the 5% knot truncate to 0. **Display only — never permission.**

### 3. Sens-frozen efficacy innovation (log-only)

`V7InnovationTracker`: the Backtest-2 innovation with sensitivity FROZEN at the static profile
ISF instead of the adapted `variable_sens` (which absorbs the exercise signal before the
innovation can measure it — d = 0.02 offline). Rolling 30-min SUM → `boostV7_innovSensFrozen`.
No behaviour attached.

## Telemetry

| RT field | meaning |
|---|---|
| `boostV7_wouldDoseR4/R7/R10` | would-dose (U) at each cost ratio — **criterion (a) instrument**; null = abstained |
| `boostV7_pLow90` | p(BG<70 within 90 min), left-shoulder truncated; display only |
| `boostV7_q50Drift` | active pool's median 30-min residual (mg/dL) — **criterion (b) instrument**: quiet-flat must read ≈0 |
| `boostV7_pool` | active regime pool + n, `…(warming n=…)` when cold, `excluded` when the cycle fits no pool |
| `boostV7_innovSensFrozen` | rolling 30-min sens-frozen innovation sum (mg/dL) |

Reason-line breadcrumb ONLY when the R-doses differ (`v7: R4=0.30 R7=0.20 R10=0.10`) — the
interesting event. Extractor mappings + idempotent ALTERs live in
`oref-investigations-boost-v2/extract/extract_boost.py`.

## Safety invariants (tested)

- **Dosing-path bit-identity**: V5/V6 decision outputs and every dose-relevant RT field are
  identical with the shadow enabled vs a control without it (`V7ShadowSafetyTest`).
- **Failure-swallowing**: a throwing persistence layer / tracker never propagates
  (`V7ShadowSafetyTest`), and the seam adds a second belt-and-braces `runCatching`.
- **Cold-start abstention**: empty/corrupt pools → `warming`, sizer null (`V7ResidualTrackerTest`).
- **R-ordering appears on a debiased pool**: a synthetic pool whose q5 shoulder projects <70
  yields strictly R4 > R7 > R10 (`V7SizerTest`) — i.e. the revised formulation CAN express
  cost-ratio sensitivity; whether it DOES on live pools is what the shadow measures.
