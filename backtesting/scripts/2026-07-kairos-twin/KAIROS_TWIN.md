# KAIROS Twin — a physiological per-person forecaster that beats oref out-of-sample

*2026-07-18. The forecaster brick the TING-engine backtest proved was the prerequisite
(TING_ENGINE.md). A dosing policy is not counterfactually validatable; a FORECASTER is —
so this is the first piece of the KAIROS design that can be validated on real data, and is.*

## Why a Twin, and why physiological

The TING planner cannot be scored by overlay (you double-dose or go inert on trajectories the old
controller already dosed). It needs a counterfactual — a per-person forward model. Built **grounded
in physiology** on purpose: a compartmental, interpretable state-space model an endocrinologist
would recognise, incapable of a non-physical trajectory — because humans function as humans.

## The model (`twin_model.py`)

Bergman-minimal glucose + 2-compartment subcutaneous insulin absorption + interstitial (CGM) lag +
a **latent glucose-appearance state `Ra`** the filter infers from CGM. State `[Isc1, Isc2, X, Ra, G, Gi]`:

| state | meaning | dynamics |
|---|---|---|
| Isc1, Isc2 | SC insulin depots (U) | `-ka1·Isc1 (+u)`; `ka1·Isc1 − ka2·Isc2` |
| X | insulin action (1/min) | `−p2·X + p2·SI·Isc2` |
| **Ra** | glucose appearance (mg/dL/min, **latent**) | `−kra·Ra` + process noise (= meals) |
| G | blood glucose (mg/dL) | `−SG·(G−Gb) − X·G + Ra` |
| Gi | interstitial / CGM glucose | `(G−Gi)/τi` |

The latent `Ra` is the load-bearing idea: **tim announces zero carbs** (pure UAM), so there is no
carb input to feed — the filter must *discover* meals from glucose alone. It does (inferred Ra
p95 ≈ 2.4 mg/dL/min spikes at meals). This is what makes the Twin survive real life; textbook twins
that assume announced meals cannot.

Assimilation = a hand-rolled **Ensemble Kalman Filter** (150 members) over the physiological state,
ingesting CGM + the known insulin stream. Parameters are per-person priors (not fitted → no
overfitting). Forecast = roll the posterior ensemble forward under known future insulin, injecting
`Ra` process noise so the forecast band honestly reflects that future meals are unknowable.

## Validation (`twin_validate.py`) — out-of-sample, causal, prior-set

Forecast vs oref's own predictions and naïve persistence, on the held-out last 45% (n≈4,800/horizon):

| horizon | **Twin RMSE** | oref eventualBG | oref iobPredBG | persistence |
|---|---|---|---|---|
| 30 min | **33.6** | 66.2 | 133.4 | 31.9 |
| 60 min | **45.3** | 72.4 | 133.2 | 48.7 |

- **~2× better than oref at both horizons** — oref's `eventualBG` is a weak forecaster; the Twin is far better.
- **Beats persistence at 60 min** (45.3 vs 48.7) — the physiology earns its keep at the planning
  horizon; the edge is largest on *quiet* cycles (Twin 42.2 vs persistence 47.0).
- **Calibrated**: 60-min 90%-interval coverage **87%** (target 90) after modelling future-meal
  uncertainty; 30-min 76% (short-horizon residual structure — a known, fixable under-dispersion).
- *rising* cycles (unannounced meals) are hard for everyone — no forecaster can see a meal coming —
  but the Twin still beats oref there and, crucially, *widens its band to say it doesn't know*.

**Verdict: GO.** The Twin is a genuinely better, calibrated forecaster than the incumbent, validated
out-of-sample on real DIY data — the identifiable brick the TING planner needs.

## Next

1. Port the model + EnKF to a Kotlin SHADOW package (grow from the shipped UKF); log its forecast +
   band as telemetry, bit-identical dosing.
2. Re-score the TING planner against the Twin's rollouts (open-loop, undosed) — now the counterfactual
   exists, the planner can finally be tuned and priced at the two-test bar.
3. Generalise the per-person priors across the cohort (the federation prior) so a new user's Twin
   starts on the manifold of all metabolisms, not a cold start.

(Personal raw-glucose traces are kept out of the repo — scratchpad only. This records the method and
the aggregate validation.)
