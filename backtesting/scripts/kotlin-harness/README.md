# Kotlin engine harness — drive the REAL shipping Boost engines from Python

Backtest the exact Kotlin that ships in the APK, so dosing logic is written once, tested once, shipped
once — no Python re-implementations that drift. See `HARNESS_SPEC.md` for the full design.

## Build
```bash
boost-harness/build.sh          # compiles the REAL engine .kt sources (from plugins/aps) + shims → boost-harness.jar
```
The build points `kotlinc` at the actual source files under `plugins/aps/...`, so a change to an engine is
picked up on the next build — single source of truth.

## Use (Python)
```python
from kengine import run_engine
res = run_engine("twin", cycles=[{"cgm":120.0,"insulinThisCycleU":0.03,"expectedBasalPerCycleU":0.05}, ...])
# res[i] = {"fc30":..., "lo30":..., "raMean":..., ...} straight from the real TwinShadow
```
Engines: `twin` (TwinShadow→TwinEnkf/TwinModel), `backout` (AnticipationBackoutShadow), `sleep`
(SleepStateDetector). One JVM invocation per batch; engine state is carried across cycles as on-device.

## Fidelity gate (mandatory before trusting a harness result)
```bash
python3 fidelity_twin.py tim
```
Confirms the harness reproduces the on-device logged telemetry. **PASS (tim, 735 cycles): fc30 MAE
5.3 mg/dL, corr 0.991; Ra MAE 0.22, corr 0.960.** So the Python-driven Twin IS the shipped Twin.

## Status
- **Phase 1 — DONE + fidelity-gated:** Twin, back-out controller, sleep detector. All three compile the
  REAL sources standalone (Twin/back-out have zero AAPS deps; sleep needs 3 tiny compile-time shims —
  `shims/HR.kt`, `shims/Logging.kt` — because a null logger is passed, so they're never exercised). This
  **retires `kairoslab/forecast/twin.py`** (the hand-port) — use `run_engine("twin", ...)` instead.
- **Phase 2 — determine_basal (V1 `DetermineBasalBoost` / V5 `DetermineBasalBoostV5`): NOT built.** These
  carry the full AAPS DI graph (many injected interfaces, Android types) that cannot be `kotlinc`-compiled
  standalone. The path (per the spec) is a JUnit runner in `plugins/aps/src/test` that builds the engine
  with the existing test fakes and reads/writes a scenario file, invoked via gradle — a heavier mechanism,
  documented but deferred. Until then, the V1/V5 dosing backtests still use the Python reconstructions
  (`2026-07-v6-sim/sim_lib.py`, `whole_meal_replay.py`), which are the ones to replace when Phase 2 lands.

## Files
`boost-harness/Harness.kt` (main + engine dispatch) · `boost-harness/shims/` (compile shims for sleep) ·
`boost-harness/build.sh` · `kengine.py` (Python driver) · `fidelity_twin.py` (the gate).
