# Evening Confirm-Overshoot Backtest + Floor/Cap Day-1 Read — 2026-07-07

Scripts: `backtesting/scripts/2026-07-evening-confirms/` (`A_evening_confirms.py`,
`B_floor_cap_day1.py`; CSV in `out/`). Data: TimescaleDB `oref`, refreshed to 2026-07-07T17:38
(backfill_all.sh since 07-06; **only failure was oref-pipeline site U018 — not a boost cohort user;
tim + A–F all fresh, the 07-06 21:44Z incident is captured**). Dedup: last row per (user, 5-min bucket).
Local time ≈ UTC+1 (BST). ISF = logged `variable_sens` at the confirm cycle; "needed" = insulin to
return to target from the ACTUAL realized peak.

---

## PART A — Evening confirm-overshoot

### 1. Evening is NOT broadly worse — the danger is the PRE-SLEEP sub-band

Fresh CONFIRMED shots (age=0), cohort, by local band:

| band | n | med U | <70-in-4h | <54 | med nadir | fizzle |
|---|---|---|---|---|---|---|
| day (07–19) | 1007 | 0.35 | 27.2% | 8.8% | 86 | 36% |
| evening (19–24) | 345 | 0.55 | **20.0%** | 9.0% | 91 | 34% |
| night (00–07) | 218 | 0.48 | 32.1% | **17.0%** | 86 | 58% |

Evening-broad is **not** worse than daytime on lows (20% vs 27% <70). But split the evening at 22:00:

| evening sub-band | n | med U | <70 | <54 | fizzle |
|---|---|---|---|---|---|
| 19:00–21:59 | 244 | 0.48 | 17.6% | 7.0% | 31% |
| **≥22:00 (pre-sleep)** | 101 | **0.85** | **25.7%** | **13.9%** | **41%** |

Pre-sleep confirms are **bigger, fizzle more, and double the <54 rate** — IOB carried toward sleep with no
daytime activity to burn it. The 07-06 incident (22:44 local) sits squarely in this band. Per-user, tim's
evening <54 is 19% (day 16%); D's evening is 71%/38% (n=21, but D is already over the absolutes). Most
other users' evening ≈ or better than day. **So a blanket evening damper is unjustified; a pre-sleep one is.**

### 2. Oversized-confirm anatomy — overshoot is NOT systemic; it is a fizzle/high-ISF tail

- 21% of confirms deliver ≥2× base-would. Size driver: `prospective = budget × 1.8 × knob(1.3) × vf`
  (median prosp/budget = 1.85); only 1% are confirmedCap-bound, so the **1.8-multiplier and knob** do the work,
  not the cap.
- **Cohort calibration is UNDER, not over:** delivered − needed(from realized peak) median **−0.68U**; delivered
  exceeds need on only 22% of confirms. Most confirms under-cover the realized peak.
- **The <54 harm is concentrated in FIZZLES:** fizzle confirms (n=602) run **16% <54** vs 6% on sustained-meal
  confirms — when a rise fizzles, any meal-sized shot overshoots. Pre-sleep fizzles: 17% <54.
- **The incident is the high-ISF tail** (from DB, tim 07-06 22:44Z): budget 2.22 → prosp 5.19 (×1.8×1.3),
  confirmedCap-bound to **3.0U**; realized peak **219**, tim ISF≈132 → correction need **0.92U** →
  **over-delivered +2.08U**; nadir **52**. It is classed "sustained>180" (BG genuinely reached 219), so it is
  not a fizzle — it is a *modest* real rise on which a knob-amplified, eventualBG-projected 3U shot is ~3× the
  ISF-correction scale. 36% of tim's confirms exceed 1.5× his current-BG correction-need (cohort 31%).

**Root cause: the confirm shot is a velocity/eventualBG bet (budget×1.8×knob), decoupled from the user's
ISF-correction scale. For high-ISF/low-TDD tim, that decoupling makes any 2–3U shot a hypo risk; pre-sleep
removes the daytime burn that masks it elsewhere.**

### 3. Mitigations, priced (removal levers → strictly reduce hypo; cost = under-covered real evening meals)

Removed-U split by fizzle (good to remove) vs sustained-real-meal (cost = under-dose):

| lever | removed U (cohort) | on fizzles | on real-meals | on <54-preceding | tim removed | catches incident? |
|---|---|---|---|---|---|---|
| (d) blanket evening damper | — | — | — | — | — | **REJECT — evening ≈ day** |
| (a) pre-sleep ×0.6 | 36.9 | 43% | 32% | 17% | 7.56U | yes (3.0→1.8) |
| (a) pre-sleep ×0.7 | 27.7 | 43% | 32% | 17% | 5.67U | partial |
| (a) pre-sleep cap 1.5U | 21.8 | 39% | 39% | 24% | 4.65U | **yes (3.0→1.5)** |
| (b) staged first-shot cap 1.5U (all bands) | 340 | 29% | **40%** | 9% | 32.6U | yes but blunt |
| (c) knob-neutral evening | 1.9 | 48% | 21% | 0% | 1.9U | no (budget, not knob, drove it) |

- **Blanket evening (d): reject** — evening is not worse than day; only pre-sleep is.
- **Cohort-wide first-shot cap (b): reject** — 40% of removed insulin lands on real meals; under-doses genuine
  big meals across the whole cohort.
- **Knob-neutral (c): too weak** — the knob is rarely the binding size driver (budget×1.8 dominates); 1.9U total.
- **Pre-sleep damper (a): the recommendation.** Scale variants (×0.6–0.7) have the better fizzle:real-meal ratio
  (43:32); the absolute 1.5U cap catches the incident hardest but costs more on real meals (39:39). Best of both:
  **the "staged" principle** the post-rescue work validated — cap the pre-sleep FIRST confirm at ~1.5U and let
  COMMITTED holds add the rest *as the rise proves real*. Verified on the incident: after a 1.5U staged shot at
  22:44, BG rose to 219 then turned; the holds at 22:49–22:58 already delivered 0 (state → RECOVERING, budget → 0),
  so staging would have correctly withheld the excess 1.5U — "same insulin, staged with evidence," and this
  meal needed only ~0.9U.

**Test A (absolute):** all mitigations are *removal* levers → they can only reduce hypo exposure; no user is
pushed toward the 4%/1% ceilings. The cost is time-high on under-covered real evening meals (32–40% of removed U),
which is a TING trade, not a safety one. Recommend **pre-sleep (≥22:00 local, or within 90 min of night-window
start) first-confirm cap = min(confirmedCap, base-would×1.5) with remainder available to holds**, shadow-first.

### 4. tim trailing-14d TBR (incl. last night)

- **TBR<70 = 3.11%, TBR<54 = 0.51%** (n=3762 cycles).
- Excluding the incident night window: 2.48% / 0.46% — the single incident added **+0.63pp to <70, +0.05pp to <54**.
- For the 07-10 floor-activation gate: tim **passes** (<70 3.11 < 3.5, <54 0.51 < 0.8) but his <70 is now
  within 0.4pp of the gate, and pre-sleep confirms are the largest movable contributor. The pre-sleep damper
  buys back the margin the incident consumed.

---

## PART B — Floor + committedCap day-1 read (tim, 2026-07-07 05:00Z→17:38, 133 cycles)

1. **committedCap raise IS live and exercising:** committedCap = **1.0** today (was 0.5), confirmedCap 3.0.
   Two COMMITTED holds > 0.5:
   - 08:59Z BG 132, delivered **1.00** (raw demand budget 1.51, new-cap-bound) — old cap 0.5 → **+0.50U**.
   - 13:44Z BG 183, delivered **0.85** (budget 0.94, under cap) — old cap 0.5 would clip → **+0.35U**.
   - 18 COMMITTED holds total, max fd 1.00. The cap raise is working exactly as designed.

2. **Floor is NOT observable:** 0 `floor`/`brake-floor`/`floorWouldAdd` breadcrumbs, 0 `non-meal-capped`
   in today's reason lines, and no `floorWouldAdd` field in the DB. **Toggle state is undetermined from
   telemetry** — recommend adding a `boostV5_floorWouldAdd` RT field before the 07-10 review so activation
   can be audited rather than inferred.

3. **7 floor-eligible cycles today** — a live RECOVERING climb 15:14→15:49Z, BG **164→195**, composed
   multiplier < 0.25 on every cycle (floor_val 0.01–0.23U). This is a **live repeat of the Episode-B
   brake-compounding pathology.**

4. **Episode-B v1-bound question — answered decisively with live data:** on those 7 RECOVERING cycles,
   `v1_units = 0` on 4 (the zeroed ones) and `fd` already = `v1_units` on the other 3. Because RECOVERING is a
   non-meal state, the floor is bounded by `min(floor, v1_units)` → **net floor uplift = 0.00U across all 7
   eligible cycles today.** The composed floor, as specced, does **not** rescue RECOVERING stalls — the exact
   Episode-B situation it was meant to fix. It can only lift COMMITTED/CONFIRMED (meal states, not v1-bounded).
   **Implication:** fixing Episode-B-class RECOVERING stalls requires either a RECOVERING-specific floor exemption
   from the v1-bound (the safety-gated option the design deferred) **or** a state-machine change (hold COMMITTED
   longer / re-engage sooner) — not the floor as currently bounded. This should be resolved before the floor's
   activation review, because on RECOVERING it is currently a no-op.

---

## Caveats
- "Needed" uses logged dynISF (`variable_sens`) at the confirm cycle — for tim (ISF≈132, TDD≈15) this makes his
  correction-scale tiny and his shots look large; the finding is robust to that (it IS his physiology), but the
  per-user ISF sensitivity is the point, not an artifact.
- base-would is only in reason text on ~10% of confirms (V6-active override rows); `v1_units` on meal-state rows
  records the *delivered* SMB, so mitigation (b) is priced off the prospective-shot pipeline and an absolute cap,
  not a per-cycle base-would.
- <70/<54 outcomes attribute any low within 4h of the confirm regardless of intervening cause (rescue carbs,
  activity) — consistent with all prior pricing; no glucose sim, so mitigation nadir effects are directional.
- Fizzle/sustained defined on the first 45 min post-confirm; the incident (peak 219) is "sustained," so the
  fizzle framing does not capture it — it is the high-ISF over-delivery tail, reported separately.
- U018 (oref pipeline) failed to refresh; no impact on boost cohort. G excluded (thin/no era map); H negligible
  confirm volume.
