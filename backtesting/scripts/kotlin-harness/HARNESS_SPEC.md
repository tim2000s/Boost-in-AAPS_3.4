# Kotlin engine harness — spec: backtest the SHIPPING engine from Python ("build and test once")

*2026-07-20. Stop re-implementing the dosing logic in Python. The backtest should drive the SAME Kotlin
that ships in the APK, so a change is written once, tested once, and shipped once. This spec is
infrastructure; the harness itself must pass a FIDELITY GATE (§8) before any result from it is trusted.*

## 1. The problem it kills
Every offline study this programme has run re-ported the logic into Python, and the ports drift from the
real engine — the documented source of "build confidently, refute later":
- `kairoslab/forecast/twin.py` re-ports `TwinModel.kt` + `TwinEnkf.kt` (two copies of one model).
- `2026-07-v6-sim/sim_lib.py` RECONSTRUCTS the V6 confirm-shot (`v6_confirm_shot`) — an approximation.
- `whole_meal_replay.py` / `v1_vs_v6_replay.py` approximate V1's dose via a partial re-derivation.
Each is a place where the backtest and the APK can silently disagree. **Single-source the engine.**

## 2. Principle
Python owns the DATA + ORCHESTRATION + ANALYSIS (DB pulls, scenario construction, stats, plots). Kotlin
owns the ENGINE (dosing, Twin, sleep, back-out) — the exact classes compiled into the APK. Python calls
the real Kotlin; nothing dosing-related is re-implemented in Python again.

## 3. Architecture
```
TimescaleDB ──psycopg2──▶ Python driver (kengine.py) ──JSON stdin──▶  boost-harness (JVM, main())
   analysis ◀── DataFrame ◀── JSON stdout ◀────────────────────────  ↳ calls the real :plugins:aps classes
```
- **`boost-harness`** — a NEW JVM-only Gradle module (`java-library`/`application`, NOT Android) that
  depends on the pure dosing classes in `:plugins:aps`. A `main()` reads a JSON request from stdin, runs
  the requested engine over the supplied cycles, writes a JSON response to stdout. Deterministic (seeded).
- **`kengine.py`** — a thin Python wrapper: builds the request from DB rows, subprocess-invokes the
  harness JAR, parses the response into numpy/pandas. One function: `run_engine(engine, cycles, params, seed)`.

## 4. The dependency boundary (the crux — phased by how DI-heavy each engine is)
- **Phase 1 — PURE engines (no Android/AAPS deps): Twin, SleepStateDetector, AnticipationBackoutShadow.**
  These are already plain Kotlin on plain data (the unit tests run them headless). Expose immediately.
  This alone RETIRES `twin.py` and single-sources the Twin — an instant fidelity win.
- **Phase 2 — determine_basal (V1 `DetermineBasalBoost`, V5/V6 `DetermineBasalBoostV5`).** These are
  DI'd (aapsLogger, profileUtil, preferences, persistenceLayer …). HONEST STATUS: the unit tests
  currently exercise V5 *components* headless (VelocityBudgetFloorTest, ExerciseGateDecideTest,
  ComposedFloorShadowTest) and the pure engines, but the FULL `determine_basal` entrypoint is NOT yet
  constructed in a test with a complete fake dependency set — so Phase 2 is *feasible but real work*, not
  already done. The path: assemble the full fake graph (the deps are all known and mostly value-returning
  stubs — prefs from the request JSON, a no-op logger, a fake profile), move it into a shared
  `testFixtures`/`harness` source set, construct the engine there, feed per-cycle inputs. Gate on §8
  before trusting it. This is what retires the `sim_lib`/`whole_meal_replay` reconstructions — the big win,
  and the harder half.
- Anything that truly needs a live Android service (rare on the dose path) is stubbed with a fake that
  returns the value carried in the scenario JSON (e.g. prefs come from the request `params`, not a real
  SharedPreferences).

## 5. I/O contract (versioned JSON; one request = one engine over N cycles)
Request (stdin):
```json
{ "engine": "twin|sleep|backout|determineBasal|v5override", "schema": 1, "seed": 1,
  "params": { "...engine config / prefs (ApsBoost* keys) as plain values..." },
  "cycles": [ { "ts": 173..., "cgm": 120.0, "insulinThisCycleU": 0.03, "scheduledBasalU": 0.05,
                "...engine-specific inputs (glucoseStatus, iob, profile, state) as flat JSON..." } ] }
```
Response (stdout):
```json
{ "engine": "twin", "schema": 1,
  "results": [ { "ts": 173..., "fc30": 125.0, "fc60": 130.0, "raMean": 0.4, "lo30": 95.0, ... } ] }
```
Rules: schema is versioned (breaks are explicit); RNG seeded from the request (reproducible; vary by
run-index for stochastic engines); one JVM invocation processes the whole cycle batch (no per-cycle
process spawn); stateful engines (Twin ensemble, sleep state machine, back-out state) carry their state
ACROSS cycles inside the single invocation, exactly as on-device.

## 6. Invocation model
- **Default: subprocess batch.** Python writes the full scenario, invokes `java -jar boost-harness.jar`
  once, reads the batch result. Simple, isolated, fast enough (JVM start ~0.5s amortised over thousands
  of cycles). Good for per-user backtests.
- **Optimization (only if needed): a persistent gateway** (Py4J) — the harness runs as a long-lived JVM
  the Python process calls repeatedly, avoiding JVM restart. Spec it as a later optimization; the batch
  model covers all current backtests (they're per-user, one invocation each).

## 7. Build integration ("build and test once")
- `./gradlew :boost-harness:jar` (or `installDist`) produces the runnable artifact; `kengine.py` points
  at it. A `make harness` / small script rebuilds it before a backtest run.
- The harness depends on `:plugins:aps`, so a change to `DetermineBasalBoostV5` (or the Twin, or the
  back-out shadow) is picked up on the next harness build — **the backtest and the APK compile the same
  source.** No parallel Python implementation to keep in sync.

## 8. FIDELITY GATE (mandatory before trusting any harness output)
The harness must reproduce the ENGINE'S OWN LOGGED OUTPUT on historical cycles before it is used for
anything: feed real DB rows through `determineBasal`/`v5override` and confirm the harness dose matches the
logged `boostv5_finaldose` / `v1_units` (MAE ≈ 0); feed real cycles through `twin` and match the logged
`boosttwin_*`. Only once the harness reproduces reality do its counterfactual runs mean anything. (This is
the same fidelity-gating already used for the Python sims — now applied to the harness itself, once.)

## 9. What it retires / changes
- **Retire** `kairoslab/forecast/twin.py`, the `sim_lib` confirm-shot reconstruction, and the V1
  re-derivations — replaced by `kengine.run_engine(...)` calls to the real classes.
- The lab keeps its VALUE-ADD (data, features, stats, CIs, the physiological Twin's Python analysis
  utilities) but stops OWNING any dosing logic.
- Net: one source of truth for dosing; backtests become faithful by construction; the "my Python port
  drifted from the APK" failure mode is gone.

## 10. Build order (phased, each independently useful)
1. **`boost-harness` module + `kengine.py`, Phase-1 engines (Twin, Sleep, Backout).** Immediate: retire
   twin.py, backtest the real Twin + the real back-out shadow state machine.
2. **Fidelity-gate the Twin harness** (match logged `boosttwin_*`).
3. **Phase-2 determineBasal** (shared fakes/testFixtures) → fidelity-gate vs logged doses → retire the
   sim/replay reconstructions; re-run the V1-vs-V6 and confirm-shot studies on the REAL engine.
4. Optional Py4J gateway if batch latency ever bites.
Nothing here is a dosing change — it is test infrastructure. But per the validation discipline, no study
result from the harness is trusted until §8 passes.
```
Home: backtesting/scripts/kotlin-harness/  (boost-harness module under the repo root; kengine.py here)
```
