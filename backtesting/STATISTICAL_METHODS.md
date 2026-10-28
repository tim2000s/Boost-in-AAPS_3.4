# Statistical methods — Boost development

Reference for the statistical and ML methods used in the Boost backtesting and analysis work. Written for a technical reader. Methods only, no patient data.

## The main constraint

There's no glucodynamic simulator, so for a dosing change we can't generate the counterfactual BG trajectory. A "simulate policy A vs B" backtest isn't available to us. The approach works around that:

- Prediction and detection questions (does a pattern exist, does it forecast an event) are answered out-of-sample.
- Policy questions (does changing a dosing knob help) are handled by pricing the change against observed outcomes, plus within-subject and matched-baseline designs where the data allows.
- An observational effect size is treated as associational unless a within-user or randomised design backs it.

The limiting factor is identification, not modelling.

## Where the methods sit: lab vs loop

What actually doses is deterministic. The statistical machinery is offline — it decides what gets built, it doesn't run in the loop.

| Method | Where | Role |
|---|---|---|
| State machine, multipliers, caps, composed brake-floor | Runtime (loop) | The dosing logic; deterministic |
| Rule-based sleep detector (HR + steps + clock) | Runtime (loop) | Night-mode gating; thresholds, not a model |
| Auto-config per-user knob derivation (from own TBR/dosing history) | Runtime (loop) | Sets hypoCaution/caps/aggression; deterministic formula, once/periodic |
| `mlHypoRisk`, `mlMealLikely` (pre-trained models) | Runtime (loop) | The only learned components live; fixed functions at inference |
| — hard constraint — | | No training or online inference in the dose path |
| LightGBM + grouped-by-user CV | Offline (lab) | Does a signal exist / forecast, leakage-safe |
| Empirical-Bayes Beta-Binomial, asymmetric-loss lower-bound gating, hierarchical partial pooling | Offline (lab) | The decision-layer work — analysing recurring structure |
| Policy-replay pricing, permutation tests, OLS confound-adjustment, regime decomposition, matched-window hazard | Offline (lab) | GO/NO-GO on proposed levers |
| Exercise-prep Beta-lower-bound gate | Specced, not built | Would move a decision rule into runtime; shadow-log first |
| Night-mode mixed-effects A/B | Pre-registered, not run | Needs instrumentation first |
| V7 residual-tracker / sens-frozen innovation | Shadow | Computes, doesn't dose |

In short: the shipping controller is deterministic (state machine, caps, a per-user auto-config derivation) plus two pre-trained ML models used at inference. The Bayesian and inferential methods are offline. The two cases where inference would move into the loop are gated behind shadow-logging or a pre-registered trial.

## 0. Learned components in runtime and shadow

The runtime holds some learned quantities (HR baselines, sleep timing); the V7 shadow holds a distributional model. None are parametric or posterior Bayesian models. They're robust order statistics, circular statistics, and asymmetric-loss decision theory — kept simple on purpose, since they sit in or near a safety-critical loop.

| Component | Derivation | Tier |
|---|---|---|
| V7 sizer "p10/p90" | empirical windowed quantiles of regime-conditioned forecast residuals → minimum-expected-loss dose | Shadow |
| HR learning (resting / daytime baseline) | per-session p10, median across ≥7 sessions → personalises Karvonen HRR | Runtime |
| Sleep learning (bedtime / wake) | circular mean of onset/wake clock-minutes | Runtime |

### V7 distributional sizer ("p10/p90"), shadow only

A windowed empirical predictive distribution with a decision rule on top, not a fitted distribution.

- Substrate (`V7ResidualTracker`): each cycle records the IOB-only forecast `projBG(t+h) = bg + BGI5·(h/5)`, `BGI5 = −iob_activity·variable_sens·5`. When a horizon matures it pools the residual = observed − projected, keyed by regime × horizon. The regimes {QUIET_FLAT, MEAL, NIGHT} (V5 state + CGM flatness + hour) are a debiasing split; without it, unannounced-carb absorption biases the residual by roughly +12 to +38 mg/dL.
- Quantiles: each pool is a ~21-day windowed, size-capped sample (oldest evicted) giving five empirical percentiles (5/25/50/75/95) by linear interpolation. Pools under 60 samples return null and the sizer abstains. So the "p10/p90" is empirical order statistics of the recent regime-conditioned forecast error, not a parametric fit.
- Decision: for a candidate dose it builds a predictive BG distribution (point projection plus residual quantiles) as a piecewise-linear inverse CDF through the five knots, discretised at 19 equal-probability points (5–95%), and picks the dose that minimises an asymmetric linear loss `E[R·max(0,70−BG) + max(0,BG−140)]`, cost ratio R ∈ {4,7,10}. Grid search, first minimum, hard cap/budget envelope.
- In short: a minimum-expected-loss decision under an empirical predictive distribution, with an asymmetric loss. It doses nothing — it logs the R4/R7/R10 results so we can see whether the output is even sensitive to R (the earlier formulation wasn't, which is why it's shadow).

### HR learning (runtime)

Robust order statistics feeding a fixed formula.

- Learned resting HR = median over sessions of each session's sleep-period p10, once at least 7 sessions have accrued. The p10 is the quiescent floor (robust to movement spikes); the median across sessions is robust to odd nights. Learned daytime baseline is the same, on the awake-period p10.
- These feed the Karvonen heart-rate reserve: `HRR% = (HR − HRrest)/(HRmax − HRrest)·100`, with fixed zone thresholds (<30 / 30–40 / 40–60 / 60–80 / >80). The only learned input is the personalised HRrest (and daytime baseline).

### Sleep learning (runtime)

- Learned bedtime and wake are the circular mean of the clock-minute-of-day values (map each minute to an angle, vector-sum, `atan2` back), because clock times wrap at midnight: the mean of 22:00 and 02:00 is 00:00, not 12:00, and a plain arithmetic mean gets it wrong. Needs a minimum number of sessions. HR baselines in the same tracker use the median-of-p10s above.

## 1. Supervised prediction (gradient-boosted trees)

- LightGBM binary classifiers for forward events (BG > 180 or < 70 at +60 min) and for habitual activity. Roughly 350–400 trees, lr 0.03, num_leaves 15–31, min_child_samples 50, subsample/colsample 0.8.
- Leakage control: GroupKFold with the user as the group, so no subject is in both train and test. That's what makes "does feature block X add value" a real question — it tests cross-user generalisation rather than per-person memorisation. Habit models also use a temporal split (first 60% train, last 40% test).
- Reported: out-of-sample AUC (forward-high 0.83, forward-low 0.78, activity habit 0.85), gain importance, and the incremental OOS AUC of a feature block over a baseline block. That last one is how we found the activity→hypo signal is per-user: it lifted in-sample and in gain rank but not in grouped-OOS AUC, i.e. it doesn't transfer across subjects, so per-user thresholds rather than a global model.

## 2. Bayesian decision layer

Bayesian methods are used in the decision layer rather than for prediction (the GBMs handle prediction).

- Empirical-Bayes / Beta-Binomial for habitual-event rates: `P(event | weekday, time-bin)` as a Beta posterior per cell, shrunk toward the subject's base rate with a pseudo-count (α₀=β₀=1, strength ≈ 20). Gives usable rates for sparse (weekday × time) cells rather than 0/1 noise.
- Asymmetric loss: anticipatory actions gate on the posterior lower credible bound (~90%) rather than the mean, since the loss is asymmetric (a missed exercise costs a hypo, a false prep costs a mild high). The action only fires when the pattern is reliably present.
- Hierarchical partial pooling (James–Stein shrinkage) for per-(user, weekday) estimates such as bedtime onset: `μ = (k·weekday_mean + m·global_mean)/(k + m)`, borrowing across a subject's weekdays when a cell is sparse.

## 3. Inferential methods

- Policy replay with observational pricing (cap-stepper, slider-controller): walk a proposed policy over the real per-cycle telemetry. Where a lever is a known multiplier on the dose (the sliders), compute the counterfactual dose exactly, but not the counterfactual BG, and price the insulin delta against observed forward lows/highs. Reported: revert rate, good-vs-wrong insulin ratios, priced pre-low units. No BG simulation is claimed.
- Permutation testing: the cross-cohort comparison used a 5,000-draw permutation null on the platform coefficient for a non-parametric p-value (p ≈ 0.27, not significant).
- OLS confound adjustment: `TIR ~ platform + CV + meanBG`, to separate a raw cross-cohort gap from case difficulty (+2.9 pp raw, +1.2 pp adjusted).
- Subgroup / regime decomposition: splitting an aggregate by time of day showed a flat +0.3 pp daytime average was hiding a +13 pp overnight difference and a compensating post-breakfast deficit. Time-specific structure like that is harder to explain by selection than a flat offset would be.
- Mixed-effects, pre-registered but not yet run: the night-mode A/B plan is `overnight_TIR ~ arm + weekday + (1 | user)` on a within-user night-randomised crossover, sized from the measured night-to-night TIR SD (~13 pp), giving roughly 5–6 pp MDE at 6–8 users × 4 weeks. It's the design that separates the mechanism from selection and basal-tuning.
- Matched-baseline / per-hour hazard: for time-to-event tails (post-exercise hypo), compare a per-hour hazard to a matched-window baseline rather than a cumulative window to a fixed baseline. This showed a "delayed 2× ramp" was a window-length artefact; the real effect is about 1.2× and flat.

## 4. Working practices

- Out-of-sample throughout; grouped-by-subject CV to avoid leakage.
- Check effect sizes against a matched baseline. Several large-looking findings shrank once baselined properly: an attribution share that was over-counting (a "34%" that audited to 90% correct), a cross-cohort TIR gap that was mostly selection, a post-exercise recovery "2×" that was window length. Un-baselined effect sizes are treated as provisional.
- Prefer within-subject to between-subject designs. The population is small (single digits to ~30 users) and self-selected, so cross-user results are mostly hypothesis-generating.
- Absolute safety thresholds sit under the statistics. The time-below-range kill-switches can only tighten; the statistics rank options, they don't override a safety floor.

## Summary

The modelling is intentionally modest (GBMs, empirical Bayes, standard linear and mixed models, permutation tests). The constraint is identification rather than fitting power. Without a simulator we validate prediction out-of-sample, price policy changes against observed outcomes with the counterfactual caveat stated, check effect sizes against matched baselines, and put anything that would change dosing through a pre-registered within-user trial before it ships.
