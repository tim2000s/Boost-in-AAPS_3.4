# Four-way CGM smoother benchmark -- results

Estimator quality ONLY. No TIR / dosing / BG-outcome claim is made.

Smoothers: persistence (baseline), exponential (AAPS today), tsunami-UKF (v7-shadow), v4-UKF (forward UKF + backward RTS + chi-squared outlier).


**v4 parity self-test:** PASS (9/9) -- reproduces the 9 behaviours of UnscentedKalmanFilterPluginTest.kt.

## Mode A -- SYNTHETIC (known ground truth)

Seeds: 20 x 3 days, sensor noise SD=6.0 mg/dL. 16999 valid samples (281 dropouts), 436 injected compression-artifact samples. Regenerate identically with `--seeds 20 --days 3`.

### Headline (lower = better)

| smoother | ground-truth RMSE (vs TRUE) | one-step RMSE (vs next raw) | GT %vs persist | 1-step %vs persist |
|----------|-----------------------------|-----------------------------|----------------|--------------------|
| persistence | 8.638 | 8.678 | +0.0% | +0.0% |
| exponential | 8.125 | 9.730 | +5.9% | -12.1% |
| tsunami | 8.996 | 9.747 | -4.2% | -12.3% |
| v4 | 6.121 | 9.415 | +29.1% | -8.5% |

- Ground-truth RMSE is the cleanest statement: how far the shipped smoothed curve sits from the *actual* glucose. The v4 curve includes its RTS backward pass.

### Artifact handling (injected compression dips)

`absorbed fraction` = how much of each artifact dip the smoother followed (0.0 = fully rejected/held at truth, 1.0 = tracked the false dip). Lower is safer.

| smoother | mean absorbed fraction | mean |err| at artifact (mg/dL) |
|----------|------------------------|-------------------------------|
| persistence | 1.000 | 36.94 |
| exponential | 0.903 | 30.06 |
| tsunami | 1.111 | 40.83 |
| v4 | 0.708 | 23.71 |

### Lag & jitter

Lag = signed tracking offset on |true slope|>2 windows (mg/dL; + = trails the move). Jitter = within-window variance on |true slope|<0.3 windows (mg/dL^2; lower = smoother).

| smoother | lag offset (mg/dL) | jitter var (mg/dL^2) | reversals |
|----------|--------------------|-----------------------|-----------|
| persistence | +0.61 | 45.35 | 3525 |
| exponential | +5.42 | 31.31 | 1821 |
| tsunami | +1.65 | 47.09 | 2924 |
| v4 | +0.58 | 13.32 | 1490 |

### v4-UKF vs tsunami-UKF (the head-to-head)

| metric | v4 | tsunami | v4 improvement |
|--------|----|---------|----------------|
| ground-truth RMSE | 6.121 | 8.996 | +32.0% |
| one-step RMSE | 9.415 | 9.747 | +3.4% |
| artifact absorbed | 0.708 | 1.111 | +36.3% |
| lag offset | +0.58 | +1.65 | +65.0% |
| jitter var | 13.32 | 47.09 | +71.7% |

## Mode B -- REAL CGM (no ground truth)

Source: local TimescaleDB oref_phase2_sites_v2 sensor=G7 (6 users). Metrics available without truth: one-step-ahead predictive RMSE (vs next raw), lag (vs raw), jitter (vs raw stable windows). Cohort labels only.

### One-step-ahead predictive RMSE (pooled, mg/dL)

| smoother | one-step RMSE | %vs persistence |
|----------|---------------|-----------------|
| persistence | 7.834 | +0.0% |
| exponential | 9.123 | -16.5% |
| tsunami | 8.705 | -11.1% |
| v4 | 9.024 | -15.2% |

### Per-series one-step RMSE

| series | persistence | exponential | tsunami | v4 |
|--------|---|---|---|---|
| U1 | 7.652 | 8.420 | 8.082 | 8.203 |
| U2 | 6.289 | 7.800 | 6.827 | 6.622 |
| U3 | 6.412 | 7.360 | 7.230 | 6.990 |
| U4 | 7.092 | 8.040 | 7.508 | 7.500 |
| U5 | 9.430 | 11.213 | 10.757 | 11.565 |
| U6 | 4.656 | 5.375 | 5.070 | 4.879 |

### Lag & jitter (vs raw)

| smoother | lag offset (mg/dL) | jitter var (mg/dL^2) | reversals |
|----------|--------------------|-----------------------|-----------|
| persistence | +0.00 | 30.75 | 23972 |
| exponential | +5.30 | 35.43 | 14971 |
| tsunami | +1.11 | 31.16 | 22118 |
| v4 | -0.14 | 18.81 | 14014 |

