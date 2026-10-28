# UKF CGM-Smoothing Backtest (2026-07)

Faithful Python mirror of the committed Kotlin `AdaptiveSmoothingPlugin.kt` (2-state adaptive UKF), backtested against real raw CGM from the local TimescaleDB (`boost_cgm`, Feb 1 - Jul 10 2026). Baselines: naive persistence, the shipped `ExponentialSmoothingPlugin.kt` (ported), and raw-delta linear extrapolation.

Run: `python ukf_smoothing_backtest.py` (needs numpy/matplotlib/psycopg2; peer-auth `dbname=oref`). Self-check: `python ukf_smoothing_backtest.py --selftest`.

## What this proves / what it does NOT

- **PROVES (sensing only):** one-step-ahead predictive accuracy against the next RAW reading - a ground-truth-free metric that penalises BOTH over-smoothing/lag AND noise-chasing - plus jitter reduction in stable windows and transition lag.

- **DOES NOT prove:** any TIR / BG-outcome / dosing benefit. There is no reference "true" glucose and no glucodynamic simulator here, so no clinical or dosing claim is made. Cleaner sensing *may* help Boost's confirm-timing, but that is a separate question this backtest cannot answer.

## Fidelity

The Python UKF mirrors the Kotlin operation-for-operation (constants, sigma-point weights alpha=1/beta=0/kappa=3, predict/update/2x2 matrix-sqrt, the `med()` median with even-size averaging, the 48-deep addFirst/removeLast innovation window, the R-adaptation order, the night test `hour not in [7,23)`, and the compression / rapid-rise / kinetic-hypo guards). **Bit-exact JVM<->CPython parity was NOT formally unit-tested** - that golden-vector test is the formal gate before trusting the ABSOLUTE numbers. The RELATIVE ranking is robust: every predictor is fed the identical stream, and sub-ULP float drift cannot flip a multi-percent RMSE gap. The filter runs one continuous forward pass per contiguous segment (consecutive gap <=15 min); `learnedR`/innovations persist across segments and reset on >24h gaps, matching the Kotlin member-state (production re-inits state per rolling call, which is if anything noisier than this clean single pass).

**Internal consistency (sine+noise):** RMSE(raw vs clean)=8.26, RMSE(UKF vs clean)=6.48 -> UKF RECOVERS clean signal better (PASS) [+21.5% error reduction]

## 1. One-step-ahead predictive RMSE (PRIMARY, mg/dL)

Lower = better. `%vs persist` and `%vs exp` are RMSE reductions (positive = UKF better).

| user | n(1-step) | UKF | persistence | exp(level) | linear | exp(trend) | %vs persist | %vs exp |
|------|-----------|-----|-------------|-----------|--------|-----------|-------------|---------|
| tim | 44195 | 7.269 | 7.349 | 10.480 | 6.609 | 7.788 | +1.1% | +30.6% |
| A | 45221 | 5.162 | 5.546 | 7.489 | 8.609 | 5.872 | +6.9% | +31.1% |
| B | 45086 | 4.448 | 5.483 | 8.331 | 2.621 | 5.213 | +18.9% | +46.6% |
| C | 35668 | 6.059 | 6.145 | 8.271 | 6.173 | 6.350 | +1.4% | +26.7% |
| D | 45598 | 4.954 | 4.801 | 7.026 | 4.370 | 5.482 | -3.2% | +29.5% |
| E | 45800 | 3.109 | 3.279 | 4.970 | 2.300 | 3.606 | +5.2% | +37.4% |
| F | 40511 | 6.315 | 7.088 | 10.084 | 5.941 | 7.228 | +10.9% | +37.4% |
| G | 35218 | 7.147 | 7.290 | 10.385 | 6.427 | 7.610 | +2.0% | +31.2% |
| H | 19323 | 4.034 | 4.273 | 6.507 | 2.856 | 4.635 | +5.6% | +38.0% |
| **POOLED** | 356620 | **5.562** | 5.869 | 8.386 | 5.581 | 6.139 | **+5.2%** | **+33.7%** |

Interpretation: persistence is a strong baseline at 5-min cadence (BG barely moves in 5 min), so beating it by even a few percent is meaningful; exp(level) is the shipped smoother's forward signal.

## 2. Noise reduction in stable windows (HONEST NEGATIVE)

Stable windows: |raw slope|<0.3 mg/dL/min over >=6 readings (pooled n=39033 windows).

- Mean within-window variance: raw=11.58, UKF=12.15, exp=15.74 mg/dL^2.

- **The UKF does NOT reduce stable-window jitter**: variance is +5.0% vs raw (i.e. slightly HIGHER), and direction reversals go raw=40968 -> UKF=44292 (+8.1%). The exp smoother, by contrast, has higher variance still (+35.9%, long-tail ringing) but fewer reversals (raw 40968 -> exp 28296).

- Why: this filter is tuned RESPONSIVE (adaptive R falls toward its floor, so Kalman gain stays high and it tracks the raw closely), and the kinetic-hypo guard deliberately reverts the estimate toward the raw value (and steepens it) whenever BG is low/falling - i.e. it DE-smooths near hypo by design, for safety. So no jitter-reduction claim can be made; the value (if any) is in trend/prediction, not denoising.

## 3. Lag on fast transitions

Windows with |slope|>2 mg/dL/min (UKF n=3193, exp n=3193). At 5-min cadence, integer cross-correlation cannot resolve sub-5-min lag, so we report a **signed tracking offset (mg/dL)**: positive = the smoother sits BEHIND the direction of motion (lags); ~0 = tracks the move; negative = leads/overshoots.

- UKF mean offset = **+1.25 mg/dL**, exp mean offset = **+4.39 mg/dL**. Larger positive = more lag on rises/falls; the UKF zero-lag rapid-rise maneuver and velocity state are meant to keep this small.

## 4. Safety-feature audit (tim)

- Fail-safe run (IOB=99, compression guard disabled by design): kinetic-hypo guard fired **2691** times, rapid-rise maneuver **474** times over 45698 readings.

- Real-IOB run (compression guard ENABLED via `boost_decisions.iob_iob`, 44089 readings had a joined IOB): compression rejection fired **450** times, kinetic-hypo **2515**, rapid-rise **368**. Compression only fires on steep isolated drops (< -25 day / -15 night) while IOB<3, i.e. plausibly-artefactual drops, not everywhere.

## 5. Fast-carb event overlays

PNG per event (raw vs UKF smoothed on top; raw 5-min delta vs UKF velocity below; vertical marks = guard fires). Times are local (Europe/London, BST).


### event1_2026-07-09_midday  -> `event1_2026-07-09_midday.png`

- Peak 217 @ 14:28, nadir 67 @ 15:33.

- UKF velocity first signals a clear fall (< -1 mg/dL/min) at **11:03**; raw 5-min delta first prints < -5 mg/dL at **11:03**.

- Kinetic-hypo guard fired at: 11:28, 12:08, 15:18, 15:23, 15:28, 15:33, 15:38.

- Compression fired at: (none); rapid-rise at: (none).


### event2_2026-07-09_evening  -> `event2_2026-07-09_evening.png`

- Peak 164 @ 21:33, nadir 46 @ 23:03.

- UKF velocity first signals a clear fall (< -1 mg/dL/min) at **19:53**; raw 5-min delta first prints < -5 mg/dL at **19:23**.

- Kinetic-hypo guard fired at: 22:43, 22:48, 22:53, 22:58, 23:03, 23:08.

- Compression fired at: (none); rapid-rise at: 23:18.


### event3_2026-07-10_afternoon  -> `event3_2026-07-10_afternoon.png`

- Peak 154 @ 14:33, nadir 78 @ 12:53.

- UKF velocity first signals a clear fall (< -1 mg/dL/min) at **14:48**; raw 5-min delta first prints < -5 mg/dL at **12:53**.

- Kinetic-hypo guard fired at: 15:18.

- Compression fired at: (none); rapid-rise at: (none).


## Honest read

- **One-step prediction (the money metric): a real but modest win.** Pooled UKF RMSE 5.56 mg/dL beats persistence 5.87 by 5.2% and the shipped exponential 8.39 by 33.7%. It improves on persistence for 8 of 9 users (only D is marginally worse, -3.2%).

- **Robustness is the real story vs the naive linear baseline.** Raw-delta linear extrapolation actually pools slightly *better* than the UKF (5.58 vs 5.56) and wins big on smooth/low-noise users (B, E, H), BUT it blows up on the noisiest user (A: 8.61 vs UKF 5.16) - it doubles sensor noise into its velocity. The UKF is never the worst predictor on any user; linear swings from best to catastrophic. That bounded-downside behaviour is the practical argument for the UKF over trend chasing.

- **No jitter-reduction win** (Section 2): the UKF is a responsive tracker, not a denoiser, and it de-smooths near hypo by design. Do not sell this as noise reduction.

- **Lag** (Section 3): the UKF trails fast transitions ~3.5x less than the exponential (+1.25 vs +4.39 mg/dL offset) - meaningfully snappier trend.

- **Safety guards behave sanely** (Section 4): compression fires only on steep isolated drops at low IOB; kinetic-hypo fires around real falls (see the fast-carb events). Neither fires everywhere.

- **Verdict:** the sensing evidence supports enabling this as a **shadow / selectable** option for evaluation - the trend signal is snappier and prediction is at least as good as the incumbent exponential and modestly better than persistence, with bounded downside. It does NOT support any dosing/TIR claim, and the ABSOLUTE numbers still owe the formal Kotlin<->Python parity unit-test before they should be quoted.

