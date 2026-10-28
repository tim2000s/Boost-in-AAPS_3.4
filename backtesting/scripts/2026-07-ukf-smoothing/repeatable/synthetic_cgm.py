#!/usr/bin/env python3
"""
synthetic_cgm.py -- seeded generator of realistic latent glucose + CGM sensor noise.

This is what makes the benchmark third-party-reproducible with ZERO private data:
truth is KNOWN, so we can compute metrics you cannot compute on real CGM
(RMSE-vs-true, lag-vs-true, and how each smoother handles injected compression
artifacts). Everything is seeded via numpy.default_rng(seed) so output is
byte-reproducible; run many seeds/days for stable means.

Two layers
----------
1. TRUE latent glucose g(t): a mean-reverting day. A circadian setpoint (mild dawn
   drift) pulls glucose home; random meals inject positive appearance via a gamma
   absorption curve (realistic rises, capped so |dG/dt| <= ~3.5 mg/dL/min); the
   mean-reversion term stands in for basal insulin + clearance. Clamped 40-350.

2. SENSOR reading z(t) on top of truth, 5-min sampling:
   - colored AR(1) noise (phi=0.5) with stationary SD ~6 mg/dL (real Dexave-class),
   - integer quantization,
   - occasional COMPRESSION ARTIFACTS: transient sharp negative dips (pressure on
     the sensor), 2-4 samples, -30..-60 mg/dL, NOT present in truth,
   - short DROPOUTS/gaps (readings marked missing -> NaN).

Returned arrays are chronological (oldest-first). Missing samples are NaN in `raw`;
callers segment around them. `is_artifact` flags the compression samples so the
benchmark can score artifact rejection against truth.
"""

import numpy as np

STEP_MIN = 5
SAMPLES_PER_DAY = (24 * 60) // STEP_MIN  # 288


def _gamma_absorption(magnitude, tau_min, horizon_min):
    """Discrete per-5-min appearance-rate samples (mg/dL per min) for one meal.
    a(t) = M * (t / tau^2) * exp(-t / tau)  -- integrates to ~M mg/dL total rise."""
    ts = np.arange(0, horizon_min + STEP_MIN, STEP_MIN, dtype=float)
    a = magnitude * (ts / (tau_min ** 2)) * np.exp(-ts / tau_min)
    return a  # mg/dL per minute, one entry per 5-min step from meal onset


def generate_true(rng, n_days, base_ts_ms):
    """Generate a CONTINUOUS multi-day latent-glucose series (no day-boundary
    discontinuities). Returns (ts int64 ms, true float), oldest-first."""
    N = SAMPLES_PER_DAY * n_days
    ts = base_ts_ms + np.arange(N) * STEP_MIN * 60_000

    # circadian setpoint repeats daily (mild dawn phenomenon, peak ~09:00)
    hours = ((np.arange(N) * STEP_MIN) / 60.0) % 24.0
    setpoint = 105.0 + 12.0 * np.sin(2 * np.pi * (hours - 3.0) / 24.0)

    # meals across the whole span (3-6 per day)
    meal_rate = np.zeros(N)
    for d in range(n_days):
        n_meals = int(rng.integers(3, 7))
        meal_starts = np.sort(rng.integers(0, SAMPLES_PER_DAY, size=n_meals)) + d * SAMPLES_PER_DAY
        for ms in meal_starts:
            # `magnitude` is the gamma integral; peak appearance = magnitude/(tau*e).
            # Chosen so post-meal rises reach ~2-4 mg/dL/min before reversion claws back.
            magnitude = float(rng.uniform(140.0, 340.0))
            tau = float(rng.uniform(28.0, 50.0))
            a = _gamma_absorption(magnitude, tau, 180)
            for k, val in enumerate(a):
                if ms + k < N:
                    meal_rate[ms + k] += val

    # continuous mean-reverting integration (basal + clearance stand-in)
    k_rev = 0.014  # /min
    g = np.zeros(N)
    g[0] = float(setpoint[0] + rng.normal(0, 5))
    for t in range(1, N):
        reversion = k_rev * (setpoint[t] - g[t - 1])
        dgdt = float(np.clip(meal_rate[t] + reversion, -3.5, 3.5))  # physiologic rate cap
        g[t] = float(np.clip(g[t - 1] + dgdt * STEP_MIN, 40.0, 350.0))

    return ts.astype(np.int64), g


def add_sensor_noise(rng, ts, true,
                     ar_phi=0.5, noise_sd=6.0,
                     p_compression=0.010, p_dropout=0.006):
    """Overlay the CGM sensor model on a true-glucose series. Returns raw (NaN for
    dropouts), is_artifact (bool), and echoes ts/true."""
    N = len(true)
    # colored AR(1) noise with stationary SD = noise_sd
    sigma_w = noise_sd * np.sqrt(1 - ar_phi ** 2)
    e = np.zeros(N)
    e[0] = rng.normal(0, noise_sd)
    for t in range(1, N):
        e[t] = ar_phi * e[t - 1] + rng.normal(0, sigma_w)

    raw = true + e
    is_artifact = np.zeros(N, dtype=bool)

    # compression artifacts: transient sharp negative dips
    t = 3
    while t < N - 4:
        if rng.random() < p_compression:
            dur = int(rng.integers(2, 5))         # 2-4 samples
            depth = float(rng.uniform(30.0, 60.0))  # mg/dL below truth at trough
            # V-shaped: ramp down to trough then recover
            half = max(dur // 2, 1)
            for k in range(dur):
                idx = t + k
                if idx >= N:
                    break
                frac = (k + 1) / half if k < half else (dur - k) / max(dur - half, 1)
                frac = min(frac, 1.0)
                raw[idx] = true[idx] - depth * frac + rng.normal(0, 2.0)
                is_artifact[idx] = True
            t += dur + 2
        else:
            t += 1

    # quantization to whole mg/dL
    raw = np.round(raw)
    raw = np.clip(raw, 40.0, 400.0)

    # dropouts (missing readings)
    for t in range(N):
        if rng.random() < p_dropout:
            dur = int(rng.integers(1, 7))
            for k in range(dur):
                if t + k < N:
                    raw[t + k] = np.nan

    return dict(ts=ts, true=true, raw=raw, is_artifact=is_artifact)


def generate(seed, n_days=3, noise_sd=6.0, base_ts_ms=1_700_000_000_000):
    """Full seeded generation of `n_days` of latent glucose + sensor readings.

    Returns chronological (oldest-first) numpy arrays:
        ts (int64 ms), true (float), raw (float, NaN=dropout), is_artifact (bool).
    Deterministic in `seed`.
    """
    rng = np.random.default_rng(seed)
    ts, true = generate_true(rng, n_days, base_ts_ms)
    sensor = add_sensor_noise(rng, ts, true, noise_sd=noise_sd)
    return sensor


if __name__ == "__main__":
    # quick sanity: print summary stats for seed 0
    s = generate(0, n_days=3)
    raw = s['raw']
    valid = ~np.isnan(raw)
    resid = raw[valid] - s['true'][valid]
    print(f"days=3 samples={len(raw)} valid={valid.sum()} dropouts={(~valid).sum()} "
          f"artifacts={s['is_artifact'].sum()}")
    print(f"true range {s['true'].min():.0f}-{s['true'].max():.0f} mg/dL")
    print(f"raw-vs-true residual SD (incl. artifacts) = {resid.std():.2f} mg/dL")
    non_art = valid & ~s['is_artifact']
    print(f"raw-vs-true residual SD (clean only)       = "
          f"{(raw[non_art] - s['true'][non_art]).std():.2f} mg/dL")
    # rate distribution
    dg = np.diff(s['true']) / STEP_MIN
    print(f"true dG/dt: min={dg.min():.2f} max={dg.max():.2f} mg/dL/min")
