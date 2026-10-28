# Founding-Boost flow — is it worth bringing back into V6? NO (broadly)

**Date:** 2026-07-20 · **Question (Tim):** the founding Boost idea was *seed a maybe-meal early
→ dose enough to trigger UAM → firm up on behaviour → deliver the appropriate amount*. V6 replaced
that graded flow with a discrete score-gated commit-shot. Should we bring the founding flow back?

**Verdict:** **Not as a general re-architecture.** The data refutes the premise that V6's gating
costs meal outcomes. What survives is the already-built primer — small, netted, per-user — for the
specific users where V6 genuinely lags.

---

## Test 1+2 — seed→firm-up on real meals (`founding_flow.py`)

Within-user, 8 users with both eras, 3,865 real-meal acceleration seeds (delta_accl>10, rising,
BG 90–160, pre-confirm, peak in +90min ≥ bg0+40). v1_units = actual delivered SMB (both eras).

- **Firm-up curve:** V1 and V6 cumulative SMB indistinguishable at every horizon (T+10..45, all Δ
  overlap 0; V6 marginally *more* if anything).
- **Time to first dose:** V1 14.9 vs V6 15.2 min — indistinguishable. (The 15-min "lead" found in
  `2026-07-v1-acceleration` is in the CONFIRM *label*, not delivery: V6's OBSERVING doses at V1's
  base rate throughout, so insulin isn't actually late — only the commit-shot's label is.)
- **Outcome:** peak BG **183 = 183** (Δ +1 [−7,+11]); low<70 10.1% vs 11.6% (Δ overlaps 0). Same.
- **Per-user, heterogeneous:** V6 lags V1 for **tim/E/H** (later first dose, less by T+30); leads for
  A/B. So "V6 slipped off some of that" is real **for tim**, but per-user, not universal.
- UAM-engagement sub-metric discarded: `uampredbg` sits mostly *below* BG (median −113), only 6% of
  seeds crossed threshold — not a usable "UAM engaged" signal from the DB.

## The untested case — meals V6's gate under-responds to (`overblock_meals.py`)

V6-era HIGH acceleration-meals (peak > 170), split by whether V6 CONFIRMED within 20 min.

| group | n | SMB by T+15 | by T+30 | peak | low<70 |
|---|---|---|---|---|---|
| V6 over-blocked (held ≥20min) | 578 | 0.69 | 1.65 | **193** | **8.4%** |
| V6 responsive (confirmed ≤20min) | 514 | 2.87 | 4.82 | **207** | **12.4%** |
| V1 | 1574 | 1.40 | 2.49 | 201 | 7.5% |

**53% of V6 high acceleration-meals were over-blocked** — yet the withheld meals peaked *lower*
(193 vs 207) with *fewer* lows (8.4% vs 12.4%) than the aggressively-dosed ones, and even peaked
~8 mg/dL below V1. The aggressive-early pattern (= the founding flow) **associates with more lows.**

**Caveat — selection-confounded:** V6's gate confirms the big/fast meals (peak high, need the
insulin) and holds on the smaller rises (peak lower). So "over-blocked peaks lower" is largely
"smaller meals peak lower", NOT "withholding lowers peaks". The counterfactual (dose the held meals
harder) is unidentified. But there is **no evidence over-blocking costs outcomes**, and a clear
associational signal that aggressive early dosing costs lows.

## Conclusion

- Do **not** build the graded-ramp firm-up / broad founding-flow restoration. On real meals V6 ≈ V1
  (same peak, same lows); on gated high meals the restraint is not costing outcomes and aggressive
  early dosing carries more lows. Consistent with H12 (V1 ≈ V6 net) and the recovering-highs / high-
  IOB-tail findings.
- What survives: the **primer as built** (`feat 3aa9a4d08e`) — small, netted, fizzle-safe, per-user
  — for the users where V6 genuinely lags (tim/E/H). NOT escalated into an aggressive ramp.

## Reproduce
`python3 founding_flow.py` · `python3 overblock_meals.py`  (local oref DB, t=now)
