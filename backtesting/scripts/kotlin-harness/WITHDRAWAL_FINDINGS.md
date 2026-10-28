# Twin-forecast insulin withdrawal — full-history validation (real engine, all Boost versions)

*2026-07-20. First study run through the Kotlin harness: the REAL TwinShadow + real TwinWithdrawalShadow
driven over ALL the data we have (8 users, ~1159 user-days, Feb–Jul 2026, across every Boost version;
delivered insulin = the live engine's dose). Framing (Tim): not "better than X" — run the new logic on all
history, compare its insulin delivery to what actually happened, and postulate the glucose from the IOB
difference. `full_history_withdrawal.py`, engine `twinwithdraw`.*

## Verdict: the lo30→withhold action is NOT viable as a standalone trigger. (SOLID — full history, real engine.)
The Twin's `lo30` (30-min forecast floor) is a sensitive-but-not-specific hypo signal — a good WARNING,
far too false-alarm-prone to drive an automated withhold.

| threshold | median withdrawals/day | median % FOLLOWED BY A REAL LOW (selectivity) | median % of real lows COVERED |
|---|---|---|---|
| lo30 < 70 | ~8 | **7%** (93% unjustified) | ~52% |
| lo30 < 60 | ~7 | ~15% | ~49% |
| lo30 < 54 (deep only) | ~6 | ~16–20% | ~42% |

At the loose trigger it withholds insulin ~8×/day and **93% of those withholdings are not followed by any
low** — it would systematically run people high — while catching only ~half the real lows. Tightening the
threshold raises selectivity only to ~1-in-5 and costs coverage; the precision/recall trade-off is poor at
every threshold. So a withhold-everything-on-lo30 rule over-treats far more than it protects.

## Descriptive numbers (per Tim's framing)
- Insulin it would remove vs actual: ~2.5–9 U/day withheld per user (varies with dose level + ISF).
- Projected glucose from the IOB difference at covered lows: +9 to +74 mg/dL nadir lift (scales with the
  user's DynISF; large for the U200 user). So WHERE it fires ahead of a real low it does lift the nadir —
  but that's swamped by the 80–93% of firings where no low was coming.

## Why this is a good outcome for the method
This is the shadow-first + harness discipline working exactly as intended: the withdrawal was the "ripest"
lever (a validated signal, safe insulin-reducing direction), it would have looked appealing to build, and
running the REAL engine over ALL the data in one faithful pass killed it cleanly — no Python re-port, no
"build then refute". The harness's first study earned its keep.

## What survives
- `lo30` stays a WARNING/telemetry signal (it already logs `floorbreach`), NOT an auto-withhold trigger.
- The withdrawal could still be a COMPONENT gated behind additional context (it does cover ~52% of lows),
  but not a standalone action — and any such combination must clear this same full-history bar first.
- The Kotlin logic (`TwinWithdrawalShadow`) + the harness `twinwithdraw` engine remain, so any future
  variant (different trigger, fractional withhold, combined gates) is one harness run from a verdict.

Confidence: SOLID (real shipping engine, full history, all 8 users, event-based metric — no accumulation
artifact, consistent across users and thresholds). The projected-lift magnitude is first-order
DynISF-anchored (directional, not exact); the selectivity/coverage numbers are direct observation.
