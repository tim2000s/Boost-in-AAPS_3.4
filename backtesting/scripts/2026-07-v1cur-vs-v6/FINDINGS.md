# V1 (as it runs in the V7-shadow build) vs V6 — confirm-meal dosing comparison

*2026-07-19. Follow-up to the ml-beta-vs-current V1 diff: the v7-shadow V1 adds two restraining guards
(post-rescue cap; cumulative SMB cap) + the v12 ML hypo-risk model over ml-beta. Does that changed V1
still out-perform V6 on the meal window? Semi-closed-loop confirm-meal replay, same method as
2026-07-v6-sim/sim_replay.py. Script: v1_vs_v6_replay.py (per-user parallel; JSON gitignored).*

## Verdict: V6 modestly BEATS the current V1 on the confirm shot (7/8 users).

| user | confirm meals | V6 TING% | V1 TING% | V6 tail | V1 tail | Δdose (V1−V6) |
|---|---|---|---|---|---|---|
| tim | 439 | 47.6 | 38.6 | 134 | 147 | −0.2U |
| C | 88 | 64.0 | 54.9 | 109 | 136 | −0.2U |
| H | 104 | 44.3 | 38.8 | 134 | 144 | −0.2U |
| D | 19 | 72.5 | 67.6 | 116 | 85 | +0.1U |
| B | 227 | 44.0 | 39.9 | 142 | 150 | −0.2U |
| F | 143 | 29.3 | 27.5 | 150 | 165 | −0.1U |
| A | 175 | 32.1 | 30.7 | 155 | 158 | −0.3U |
| E | 31 | 68.8 | 69.1 | 107 | 105 | 0.0U |

V6 wins TING in 7/8 (E tie) by ~+1.4 to +9 points; V1 sits on a higher post-meal tail. At the
confirmation point V1's UAM tiers dose ~0.1–0.3U LESS than V6's 1.8× confirm shot, so the V1
counterfactual gets less insulin and plateaus higher. (tim/D also show V1 crashing a touch MORE despite
lower mean dose — V1's UAM tiers are spikier meal-to-meal: bigger on some, smaller on others.)

## WHOLE-MEAL-WINDOW result (the proper answer — whole_meal_replay.py)
Anchored on MEAL ONSET (not CONFIRMED — that biased to V6's aggressive confirm meals), projecting the
full excursion. Current V1 is WORSE-or-TIED vs V6 on meal-window TING in ALL 8 users:

| user | windows | V6 TING | V1 TING | V6 tail | V1 tail | net V1−V6 |
|---|---|---|---|---|---|---|
| tim | 54 | 45.7 | 34.5 | 138 | 200 | −0.9U |
| E | 42 | 72.1 | 63.4 | 115 | 118 | −0.2U |
| C | 29 | 58.9 | 53.5 | 116 | 129 | −0.6U |
| B | 65 | 47.0 | 42.0 | 147 | 158 | −0.8U |
| F | 45 | 33.6 | 29.3 | 142 | 161 | −0.6U |
| D | 5 | 80.0 | 70.7 | 110 | 47(crash) | +5.3U |
| A | 55 | 35.5 | 35.0 | 152 | 138 | +0.9U |
| H | 50 | 50.9 | 50.6 | 134 | 128 | +0.2U |

**The earlier −7.5 (V1 better) was the OLD ml-beta V1. The v7-shadow V1 has since been reined in**
(post-rescue cap + cumulative-SMB cap + v12 ML), so it now net-doses LESS than V6 on the meal window
for most users (tim −0.9, B −0.8, F −0.6) → under-recovers → HIGHER tail → worse TING. The very recovery
corrections that gave old-V1 its edge are what the new guards throttle. Where current V1 still doses MORE
(A, D), it overshoots into lows (D crash 80% vs V6 0%, tail 47) — the high-IOB brake's justification.

⇒ The meal-window lever is NOT "revert toward V1". It's the descent/plateau-nudge line on V6 (add the
recovery insulin UNDER V6's brake, not remove the brake). Confirm-only view below (V6 also wins there).

## OLD V1 (pre-ML, running LIVE, Feb–Apr) vs V6 — direct actuals (old_v1_era_vs_v6.sql)
Not a shadow: old V1 was its own era before the ML/V6 line (~2026-05-01). Pure old-V1 exists for A,B,E,F,
tim. Daytime (07–22 London) actual outcomes:

| user | TING old→V6 | TIR old→V6 | TBR<70 old→V6 |
|---|---|---|---|
| A | 56.1→44.1 | 82.9→73.0 | 1.2→1.1 |
| B | 67.9→56.8 | 83.6→75.7 | 3.1→2.0 |
| tim | 67.1→61.1 | 85.1→81.7 | 2.9→3.4 |
| E | 77.1→84.4 | 91.2→97.5 | 2.2→1.4 |
| F | 45.4→48.0 | 63.0→77.9 | 4.3→2.4 |

Old V1 higher TING for A(+12)/B(+11)/tim(+6) — genuinely tighter 63–140 — BUT more lows (B/E/F TBR up)
and worse TIR for F (ran high). V6 safer (lower TBR, better TIR), slightly less tight-band TING; E/F
better on V6. = **tighter-but-more-hypo old V1 vs safer V6** — the aggression V6's brake tames. TWO
caveats: (1) SEASON — old V1 spring, V6 summer, can't separate here; (2) the within-cycle counterfactual
(which removes season) says V1's DOSING POLICY doesn't beat V6 → the era TING edge is part season, part
old-V1 dosing harder into more lows, NOT a free-lunch policy win. So old V1's tight-band edge came with a
hypo cost V6 deliberately gave up; lever stays add-recovery-under-the-brake (plateau-nudge), not brake-off.

## Architecture fact that makes this a faithful current-V1 comparison
OpenAPSBoostPlugin ~1345: ONE determine_basal call — the V1 DetermineBasalBoost — passed the RESOLVED
cumulativeSmbCap60Min (line 1360). Its rT.units IS the logged `v1_units`, computed live each cycle WITH
all of V1's guards (post-rescue cap, cumulative cap, v12 ML). The V5/V6 override replaces .units AFTER
(line 1505). So **the DB's v1_units already IS the in-build V1 dose** — no offline reconstruction needed,
and all the ml-beta→current changes are already baked in for current-build data.

### Discarded first attempt (documented so the trap isn't repeated)
I first tried to reconstruct current-V1 by re-applying the guards to logged V1 → tails of 250–300 (an
artifact). Wrong twice: (1) double-counted guards that are already in v1_units; (2) used the 1.5U
signature default for the cumulative cap when the real DoubleKey default is **10.0**, auto-config-derived
(candidates [1.5, 6.0]) — the recurring auto-config-≠-default + U200 trap. ISF winsorised 250, per-user
median throughout.

CAVEAT: earliest V6-era v1_units came from pre-2026-07-04 builds (no post-rescue cap), but confirm meals
almost never sit in a post-rescue window (BG high), so that guard barely moves confirm-meal v1_units.
