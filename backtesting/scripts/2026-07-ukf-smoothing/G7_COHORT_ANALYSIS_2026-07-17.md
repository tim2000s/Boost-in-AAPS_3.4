# G7/One+ cohort — CGM-smoother analysis (2026-07-17)

A re-run and per-user extension of the G7 real-sensor benchmark that underpins the
"retire exponential, adopt UKF" argument. Two questions:

1. **Does the shipped result still reproduce** off the current DB? (Reproducibility.)
2. **Does the v4 UKF's win hold for every G7 user**, or only in the pooled total —
   where one user (U5) holds ~1/3 of the rows and could carry the average?

Nothing here changes dosing. This is estimator-quality only: how faithfully each
smoother tracks glucose, how much sensor noise it removes, and how much it lags.

## Data

`oref_phase2_sites_v2`, `sensor_type='G7'` — the only table carrying sensor labels.
6 users (U1–U6), 152,207 raw rows, deduped to one reading per 5-min bucket
(`DISTINCT ON floor(ts/300000)`), because the phase2 export interleaves two upload
streams ~1 min apart and reads as a ±40 mg/dL sawtooth otherwise. One+ shares G7
hardware/firmware and reports as G7; there is no separate label. The export is a
**static historical set** (spans to 2025-12-23), so no extractor refresh applies.

Four smoothers compared: **persistence** (= raw, a floor), **exponential** (what
AAPS ships today), **tsunami** (the earlier UKF), **v4** (the shipped
UnscentedKalmanFilter, RTS + adaptive R). v4 parity self-test: **9/9 pass**.

## 1. Reproducibility — confirmed

The pooled Mode-B (real G7) and Mode-A (synthetic ground-truth) numbers match the
shipped report exactly:

| metric (pooled) | persistence | exponential | tsunami | **v4** |
|---|---|---|---|---|
| lag offset (mg/dL) | +0.00 | +5.30 | +1.11 | **−0.14** |
| jitter var (mg/dL²) | 30.75 | 35.43 | 31.16 | **18.81** |
| reversals | 23,972 | 14,971 | 22,118 | **14,014** |
| ground-truth RMSE (synthetic) | 8.64 | 8.13 | 9.00 | **6.12** |

v4 removes the most noise (jitter −39% vs raw; exponential *adds* noise, +15%, from
its 2nd-order ringing), with essentially **zero lag** where exponential trails by
+5.3 mg/dL (≈ one 5-min step behind). On the synthetic set with known truth, v4 is
**+29% closer to the true glucose than persistence and +32% than tsunami**, and
absorbs the least of an injected compression dip (0.71 vs exponential 0.90,
tsunami 1.11 — lower is safer).

**One caveat, unchanged:** the one-step-ahead-predict-next-*raw* metric favours
persistence on the G7 (7.83 vs v4 9.02). That is the known noise-chasing lens — on
an already-clean sensor it rewards predicting the noise, so it flatters raw and is
*not* the headline. Truth-aligned metrics (ground-truth RMSE, lag, jitter) are.

## 2. Per-user — the win is unanimous

Running the identical metrics per user (`g7_cohort_peruser.py`):

**Jitter variance (mg/dL², lower = smoother):**

| user | n(5-min) | raw | exponential | **v4** | v4 vs raw | v4 vs exp |
|---|---|---|---|---|---|---|
| U1 | 22,359 | 23.55 | 25.88 | **12.35** | −48% | −52% |
| U2 | 14,001 | 66.80 | 69.31 | **61.54** | −8% | −11% |
| U3 | 28,806 | 18.75 | 19.87 | **9.19** | −51% | −54% |
| U4 | 28,948 | 24.99 | 30.91 | **15.81** | −37% | −49% |
| U5 | 51,835 | 34.44 | 42.75 | **15.56** | −55% | −64% |
| U6 | 6,058 | 13.90 | 16.43 | **8.95** | −36% | −46% |

**Lag (mg/dL, + = trails):** v4 sits at −0.47…+0.08 for every user; exponential
trails +3.6…+5.5 for every user.

- v4 has **lower jitter than exponential in 6/6** users.
- v4 has **smaller |lag| than exponential in 6/6** users.
- **Verdict: unanimous.** The pooled win is not carried by the largest user — U5
  (the biggest series) is in fact where v4 wins by the widest margin (−64% jitter).

The single hardest case is **U2**: the noisiest raw signal in the cohort (jitter ~67
vs ~14–34 for the others) and where v4's margin is thinnest (−11% vs exponential).
It still wins on both jitter and lag; it's just the user whose sensor noise most
resists smoothing. Worth a closer look only if U2 is a real ongoing user.

Reversals (direction chatter in flat windows) track the same way — v4 lowest or
tied-lowest for all users except U6, where exponential is marginally lower
(603 vs 663) at the cost of its +3.6 lag.

## Point-by-point trace

`g7_pointwise_trace.png` (busiest G7 user, regenerated) shows the raw sawtooth, the
exponential curve visibly lagging and ringing, and the v4 curve sitting cleanly on
the signal centre with no phase delay.

## Limitations

- **Static export** — G7 phase2 data ends 2025-12; this is a characterisation of the
  historical cohort, not a live-forward test.
- **No IOB in this table**, so the v4 compression-low damper (IOB-gated) is
  fail-safe-*off* here and is not exercised — its safety benefit is not in these
  numbers. It's validated separately by unit test + the 07-10→11 overnight event.
- Estimator quality only. This says the shipped smoothed curve is closer to truth
  and cleaner; it does **not** by itself quantify a dosing/outcome benefit — the
  value to Boost is the cleaner rate signal feeding confirm-timing, argued elsewhere.

## Bottom line

The G7/One+ cohort result reproduces exactly and **strengthens** on inspection: the
v4 UKF is the best smoother by every truth-aligned metric, and it beats the shipped
exponential on noise-removal and lag for **all six users, not just on average**. The
"retire exponential, adopt UKF" argument holds across the whole real G7 cohort.

Reproduce: `python3 repeatable/benchmark.py --mode real --db --sensor G7`,
`python3 repeatable/benchmark.py --mode synthetic`, `python3 repeatable/g7_cohort_peruser.py`,
`python3 repeatable/g7_pointwise_plot.py`.
