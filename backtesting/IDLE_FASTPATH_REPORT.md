# Cold-IDLE fast-path — full-cohort analysis & recommendation
2026-06-26 · `idle_fastpath_analysis.py` over `replay.py` cohort (7 sites, fresh 30-day pull)

## TL;DR — I was wrong earlier; do NOT keep the blanket removal
An earlier pass (run on a **stale/partial cache** that showed `self` IDLE firing only once) led me to
recommend deleting the `IDLE → CONFIRMED` branch as a "zero-cost" safety win. **That was an artifact of
incomplete data.** On a fresh, complete 30-day pull across all 7 users the branch fires **59 times** and
catches real fast carbs at the **same rate as the OBSERVING path**. Removing it has a real cost.

## The data (fresh 30-day cohort)
Fresh CONFIRMED transitions, split by origin state:

| user | mode | IDLE→C | OBS→C | IDLE sustained | IDLE undershoot | recovered @+1 | "lost" early-catch |
|---|---|---|---|---|---|---|---|
| **self (tim)** | **V5-ACTIVE** | **11** | 221 | **6** | **2** | 1 | 5 |
| A | shadow | 11 | 120 | 5 | 0 | 3 | 2 |
| B | shadow | 6 | 145 | 4 | 1 | 0 | 4 |
| C | shadow | 6 | 114 | 6 | 2 | 1 | 5 |
| D | shadow | 11 | 74 | 7 | 5 | 1 | 6 |
| E | shadow | 5 | 60 | 2 | 0 | 0 | 2 |
| F | shadow | 9 | 168 | 6 | 1 | 1 | 5 |

**Pooled IDLE-origin (n=59):** sustained real-rise **61%** · reversed transient 5% · led to undershoot **18%**.
**OBSERVING-origin baseline (n=902):** sustained 59% · undershoot **9%** (untouched by any fix).

## What this means
1. **Cold-IDLE is not spurious — it's a regular, productive part of V5's fast-carb response.** 59 fires/30d;
   it catches genuine fast carbs at **61%**, statistically the same as OBSERVING's 59%.
2. **But cold-IDLE fires undershoot 2× as often as OBSERVING fires (18% vs 9%).** Firing on a single
   uncorroborated cycle with no prior OBSERVING context is genuinely riskier — it just isn't *useless*.
3. **The "one beat" fix is costly: only 11% (7/59) of IDLE catches would be re-caught by the OBSERVING
   fast-path at +1 cycle.** Acceleration (≥15%) typically spikes only on the onset cycle, so the next
   cycle no longer qualifies. The other ~29 sustained catches revert to the slow normal observe→confirm
   path — i.e. removing the branch partially **un-does the 2026-06-16 fast-path latency fix** for the
   cold-start subset (spikes the fast-path was built to prevent).

## Tim specifically (the only V5-ACTIVE / real-dosing user)
- 11 cold-IDLE fires / 30d (~1 every 3 days).
- **6 genuine fast carbs caught early** (benefit) vs **2 undershoots** (the 07:08-type mild lows, BG→~4.3).
- So for Tim it's a real clinical trade: ~6 spike-preventions against ~2 mild lows per month. Not the
  free win I claimed, and not obviously worth deleting.
- (Shadow users A–F: their undershoots are **not** V5-caused — V1 was dosing — so the only real dosing
  harm in the whole cohort is Tim's 2 mild lows.)

## Recommendation
**Revert the blanket removal** (AAPS `e95561aa02`, Trio `9386c6b6e`). It deletes a branch that catches
real fast carbs as well as OBSERVING does, and ~89% of those catches don't recover quickly.

The real, narrow problem is the **2× undershoot rate on cold-IDLE confirms**, caused by full-confidence
dosing on a single uncorroborated cycle. Fix *that*, not the detection:

- **Preferred — dose-conservative cold-IDLE confirm:** keep `IDLE → CONFIRMED` (early catch) but apply a
  reduced action multiplier / velocity-confidence discount / lower SMB cap to IDLE-origin confirms (no
  OBSERVING corroboration ⇒ lower confidence). Keeps the 6 early catches, shrinks the 2 overshoots if the
  rise turns out transient. Needs a constant + replay validation before shipping.
- **Acceptable alternative:** leave cold-IDLE as-is and monitor — for Tim it's roughly break-even and the
  lows are mild (~4.3, not severe).

Either way: **the removal as shipped is not supported by the data and should come out.**

## Reproduce
`cd backtesting && python3 idle_fastpath_analysis.py` (refresh first with
`rm ~/.cache/boost_backtest/replay_*_30d.json` so `self` includes today's cycles — the stale cache is
exactly what produced the wrong "fired once" figure).
