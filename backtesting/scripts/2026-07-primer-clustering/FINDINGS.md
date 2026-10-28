# Primer fizzle-clustering — cap and taper rejected, confirm-net shipped

**Date:** 2026-07-21 · **Question:** the V1-acceleration primer fires often and fizzles most of
the time; clustered fizzles accumulate IOB (tim's lunch: 3 pre-lunch fizzles → dip to 78, which then
suppressed the primer on the real meal). What's the optimal constraint? Replays the exact live primer
logic (OBSERVING + delta_accl>10 + floors + once-per-session) across all V6-era history (8 users).

**Verdict:** No cap or taper works — both trade real-meal seeds for fizzles ~1:1, because seeds and
fizzles are temporally interleaved and indistinguishable at fire time (73% FP is irreducible). The
ONE lever that survives is Tim's **confirm-net**: keep every primer, but credit the accumulated
primer IOB (beyond one base) against the commit-shot at CONFIRM. Shipped (commit `6c439c8dee`).

---

## 1. How often does it cluster? (`primer_clustering.py`) — 4,836 fires

- **~12 fires/day per user**; **73% fizzle** (never confirm); **84% of fires are clustered** (≥2 within
  90 min); up to **4–5 per 90-min window** (≈1.75 U of primer).
- Clusters that preceded a BG<80 dip: **6% pooled** — mostly benign. Concentrated in the sensitive
  users: **D 23%**, **tim 9%**, B 6%, rest ≤3%. So the clustering is *frequent* but *mostly safe*, and
  the dip risk is a per-user thing (D/tim).
- The subtler cost = **self-suppression**: a fizzle cluster dips BG<80, which then blocks the primer on
  the *next real meal* via the recentLow≥80 guard (exactly tim's lunch).

## 2. Rolling-window cap (`primer_cap_sweep.py`) — REJECTED

count-cap(W,K) = allow < K fires in the trailing W min. Trade-off is **~1:1** at every setting:

| W | K=1 seed-kept / fizzle-blocked |
|---|---|
| 60 min | 66% / 32% |
| 90 min | 55% / 44% |
| 120 min | 48% / 53% |

seed-kept + fizzle-blocked ≈ 100 everywhere — every fizzle blocked costs a seed. K≥2 keeps seeds but
blocks ~nothing. gap+reset (confirm resets the refractory) is identical — the fizzles happen *before*
the confirm, so the reset comes too late. **No operating point worth having.**

## 3. IOB taper (`primer_iob_taper.py`) — REJECTED

Shrink the primer when recent primer-IOB is high (dip impact via bounded insulin-perturbation replay):

| cap | dip<80 vs base | avg seed dose vs base |
|---|---|---|
| 0.7 | −19% | −23% |
| 0.5 | −37% | −41% |
| 0.35 | −55% | −57% |

Dip reduction and seed-dose reduction move together — the taper doesn't spare seeds (real-meal seeds
usually fire *after* a fizzle burst, so `recentPrimerIOB` is high when they fire). Effectively ≈ just
using a smaller global primer. (Absolute dip counts inflated — perturbation has no closed-loop
compensation — but the proportionality is robust.)

## 4. Confirm-net (`primer_confirm_net.py`) — SHIPPED

Tim's rule: keep every primer firing; at CONFIRM, net the accumulated primer IOB **beyond one base**
off the commit-shot. Magnitude over 2,170 confirmed meals:

- **87%** of confirms follow ≥1 primer within DIA; **76%** follow ≥2 (fizzle + seed).
- primer IOB at confirm: **median 0.56 U, p90 1.04 U**.
- The net-off would reduce the commit-shot on **57% of confirms** (>0.1 U), **42% by >0.3 U**;
  median net-off when >0 = **0.39 U**.

It's the only lever that **loses no seeds** and bounds the meal's net-extra insulin to one base
regardless of fizzle count. It only ever *removes* insulin (safe-signed). It does NOT address
pure-fizzle clusters that never confirm (their mild intermediate dip stays "fizzle-safe, accept it").
Safety is **mechanical** (removes double-counted insulin), not outcome-proven — the historical
"more preceding primer IOB → fewer lows" proxy is confounded (primer wasn't live; those are bigger
meals). Implemented `6c439c8dee` (`primerIobU` cross-session accumulator, netted at the CONFIRMED
transition off the commit-shot then COMMITTED holds).

## Reproduce
`python3 primer_clustering.py` · `primer_cap_sweep.py` · `primer_iob_taper.py` · `primer_confirm_net.py`
