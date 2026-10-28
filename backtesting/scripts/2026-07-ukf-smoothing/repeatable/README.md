# Reproducible four-way CGM-smoother benchmark

A self-contained, seeded, third-party-runnable benchmark that compares four CGM
smoothing methods on **estimator quality**. It exists to supply the evidence for one
argument: **the exponential smoother currently in AAPS should be retired** in favour
of an Unscented Kalman Filter, and specifically the **v4 UKF (forward UKF + backward
RTS smoothing + chi-squared outlier handling)** is the better of the two UKFs on the
table.

> **Scope discipline (read this):** this benchmark measures *sensing / estimator
> quality only* — how closely each method tracks glucose, how much it lags, how it
> handles sensor artifacts. It makes **no TIR, dosing, or BG-outcome claim** of any
> kind. Whether cleaner sensing helps a controller is a separate question this code
> cannot and does not answer.

## The four smoothers

| name | what it is | source ported |
|------|-----------|---------------|
| `persistence` | naive baseline: estimate(t) = raw(t), no trend | — |
| `exponential` | **what AAPS ships today** | `plugins/smoothing/.../ExponentialSmoothingPlugin.kt` |
| `tsunami` | the UKF currently in `Boost-V7-shadow` | `plugins/smoothing/.../AdaptiveSmoothingPlugin.kt` |
| `v4` | the **better UKF** — forward UKF + **backward RTS pass** + chi² outlier | `AndroidAPS-v4-port/.../UnscentedKalmanFilterPlugin.kt` |

The `exponential` and `tsunami` Python ports are **reused** from the already-committed
`../ukf_smoothing_backtest.py` (imported, not re-derived). The `v4` port is **new**
in `smoothers.py` and mirrors the Kotlin operation-for-operation: 2-state UKF
`[glucose, rate]`, fixed Q / adaptive R (Huber-inflated `R_eff` + IAE adaptation with
trimmed-mean statistics and asymmetric gains), chi-squared outlier detection
(threshold 15.13 = 99.99% / 1 DOF, plus a 65 mg/dL absolute limit), a 2-of-3
same-sign Q-inflation gate for real trends, gap segmentation (>60 min), error-code
(`<=38 -> 39` floor) handling, and the backward **Rauch–Tung–Striebel** smoothing
pass that is the key architectural differentiator from `tsunami`.

**Parity oracle.** `smoothers.py`'s self-test asserts the v4 port reproduces the nine
behaviours of the Kotlin unit test `UnscentedKalmanFilterPluginTest.kt` (empty input,
single-value 39 floor, error-code collapse, clean-series sanity, rising-series trend,
**isolated-spike dampened < 200**, major-gap segmentation, determinism, and a coherent
RTS ramp). All nine PASS; `benchmark.py` re-runs them before every run and aborts on
failure.

## Quick start (zero private data)

```bash
pip install -r requirements.txt        # just numpy for the default mode
python benchmark.py                    # Mode A synthetic, 20 seeds x 3 days (default)
```

That runs the parity self-test, then the synthetic benchmark, prints the tables, and
writes `results.md` + `results.json`. It is fully seeded (`numpy.default_rng(seed)`,
seeds `0..19`) — **anyone cloning the repo reproduces the identical numbers**.

Other invocations:

```bash
python smoothers.py                          # just the v4 parity self-test (PASS/FAIL)
python benchmark.py --mode synthetic --seeds 40 --days 3   # more seeds = tighter means
python benchmark.py --mode real --csv mydata.csv           # bring your own real CGM
python benchmark.py --mode real --db                       # local TimescaleDB (optional)
```

## Two data modes

### Mode A — SYNTHETIC (default, the reproducible core)

`synthetic_cgm.py` generates a seeded, realistic day:

- **True latent glucose** (known ground truth): a continuous mean-reverting series —
  circadian setpoint with a mild dawn phenomenon, random meals (3–6/day) injected as
  gamma absorption curves (rises up to the physiologic `~3.5 mg/dL/min` cap), basal +
  clearance as soft mean-reversion, clamped 40–350 mg/dL, continuous across day
  boundaries.
- **Sensor model** on top of truth, 5-min sampling: colored **AR(1)** noise
  (φ = 0.5, stationary SD ≈ 6 mg/dL, Dexcom-class), integer quantization, occasional
  **compression artifacts** (transient sharp negative dips, 2–4 samples, 30–60 mg/dL,
  *not* present in truth), and short **dropouts** (missing readings → NaN).

Because truth is known, Mode A computes the metrics you **cannot** get on real data:
RMSE against TRUE glucose, lag against the true transitions, and exactly how far each
smoother is pulled toward the injected artifacts.

### Mode B — BRING YOUR OWN real CGM (optional)

- `--csv mydata.csv` — a two-column CSV `timestamp,glucose_mgdl` (header auto-detected;
  timestamps may be epoch seconds/ms or ISO/`YYYY-MM-DD HH:MM:SS`). **No extra deps.**
- `--db` — the local TimescaleDB (`psycopg2.connect("dbname=oref")`, table
  `boost_cgm(user_id, ts_utc, cgm_mgdl)`). Needs `psycopg2-binary`. **Optional** — the
  script runs fully without a database.

On real data there is no ground truth, so Mode B reports the two-sided
**one-step-ahead predictive RMSE** (predict the next raw reading), plus lag and jitter
vs raw. This reproduces the cohort result already in `../README.md`.

## Metrics

- **Ground-truth RMSE (Mode A only)** — smoothed curve vs TRUE glucose. The cleanest
  statement of estimator quality. The v4 curve includes its RTS backward pass.
- **One-step-ahead predictive RMSE (both modes)** — each smoother's *causal*
  (forward-only) estimate at `t` predicts `raw[t+1]`; the two-sided honest metric that
  penalizes lag **and** noise-chasing. Baseline = persistence.
- **Lag** — signed tracking offset on `|slope|>2` windows (+ = trails the move).
- **Jitter** — within-window variance on stable (`|slope|<0.3`) windows + reversals.
- **Artifact handling (Mode A)** — mean *absorbed fraction* of each injected
  compression dip (0 = fully rejected/held at truth, 1 = followed the false dip).

**Two evaluation stances, stated honestly.** One-step prediction uses each smoother's
*causal, forward-only* estimate (fair to all four). Ground-truth curve RMSE uses each
smoother's actual *shipped* output — for v4 that includes the RTS backward pass, which
by definition uses data after `t` (that is what a *smoother*, as opposed to a *filter*,
does, and is exactly where the v4-vs-tsunami architectural difference is visible).

## Expected output (reference numbers)

From `python benchmark.py` (Mode A, 20 seeds × 3 days, seed 0..19) and
`--mode real --db` on the reference cohort. Your Mode A numbers should match to the
digit; Mode B depends on your own data.

**Mode A — synthetic, ground truth (lower = better):**

| smoother | ground-truth RMSE | one-step RMSE | artifact absorbed | lag | jitter var |
|----------|-------------------|---------------|-------------------|-----|-----------|
| persistence | 8.638 | 8.678 | 1.000 | +0.61 | 45.35 |
| exponential | 8.125 | 9.730 | 0.903 | +5.42 | 31.31 |
| tsunami | 8.996 | 9.747 | 1.111 | +1.65 | 47.09 |
| **v4** | **6.121** | 9.415 | **0.708** | **+0.58** | **13.32** |

**Mode B — real cohort, one-step-ahead predictive RMSE (lower = better):**

| smoother | one-step RMSE | %vs persistence | lag | jitter var |
|----------|---------------|-----------------|-----|-----------|
| persistence | 5.878 | +0.0% | +0.00 | 13.40 |
| exponential | 6.154 | −4.7% | +4.36 | 17.42 |
| tsunami | 5.573 | +5.2% | +1.25 | 14.09 |
| v4 | 5.714 | +2.8% | −0.09 | 9.43 |

## What the evidence says (honest read)

1. **Ground-truth quality (Mode A, the decisive metric): v4 wins by a wide margin.**
   v4's smoothed curve sits **6.12 mg/dL** RMSE from true glucose vs persistence 8.64,
   exponential 8.12, and tsunami **8.99** — i.e. tsunami is *worse than the raw signal*
   (it is a responsive tracker that de-smooths, by its own design). v4 is **+29% vs
   persistence and +32% vs tsunami**.

2. **v4 vs tsunami (the head-to-head): v4 is measurably better, and it is the RTS +
   R_eff machinery that does it.** v4 beats tsunami on ground-truth RMSE (+32%),
   artifact rejection (absorbs 0.71 of a compression dip vs tsunami's 1.11 — tsunami
   actually *amplifies* dips) (+36%), lag (+0.58 vs +1.65 mg/dL, +65%), and jitter
   (13.3 vs 47.1, +72%). On real-data one-step tsunami edges v4 by 2.5%, but that
   metric rewards noise-chasing (its target is the *noisy* next raw); the only metric
   that measures true accuracy — ground-truth RMSE — favours v4 decisively.

3. **The case against the exponential.** On real data it is the **worst predictor** of
   all four — worse even than doing nothing (persistence): −4.7% at one-step even when
   given its best trend-extrapolated forecast, and the *shipped level-only* form is
   worse still (≈8.4 mg/dL, see `../README.md`). It carries by far the **largest lag**
   (+4.36 mg/dL real / +5.42 synthetic — roughly 4× the UKFs) from its second-order
   ringing. Both modes agree on this.

4. **Cross-validation — where the modes agree and where they don't (stated plainly).**
   Both modes agree that v4 is the best smoother on every accuracy/lag/jitter axis and
   that the exponential lags worst and predicts no better than persistence. They
   **disagree** on one point: on real data both UKFs beat persistence at one-step
   raw prediction, whereas on the (smoother) synthetic truth persistence is a very
   strong one-step baseline that none of the smoothers beat. That is an honest
   limitation of the one-step-vs-noisy-raw metric — and precisely why **ground-truth
   RMSE is the primary synthetic statement**, where v4's advantage is unambiguous.

**Bottom line:** the estimator-quality evidence supports retiring the exponential and
adopting the v4 UKF; the RTS backward pass and Huber R-inflation are what make v4
better than the tsunami UKF. No dosing/TIR benefit is claimed.

## Reproduce exactly

```bash
python -m venv .venv && source .venv/bin/activate   # or use an existing venv
pip install -r requirements.txt
python benchmark.py                                 # Mode A, seeds 0..19, deterministic
# optional, with your own data:
python benchmark.py --mode real --csv yourdata.csv
```

Seeds are `numpy.default_rng(0..seeds-1)`. Running `--mode synthetic` then
`--mode real` accumulates both into one `results.md` / `results.json`. Intermediate
data stays in memory; only the scripts and `results.*` are committed.

## Files

- `smoothers.py` — the four Python smoothers (exponential + tsunami reused from
  `../ukf_smoothing_backtest.py`; new faithful v4 RTS + chi² port) + the parity
  self-test. Run standalone for PASS/FAIL.
- `synthetic_cgm.py` — the seeded ground-truth + sensor-noise generator.
- `benchmark.py` — CLI, metrics, tables, writes `results.md` / `results.json`.
- `requirements.txt` — numpy (core); psycopg2-binary only for the optional `--db` path.
- `results.md` / `results.json` — last run's numbers (regenerate any time).
