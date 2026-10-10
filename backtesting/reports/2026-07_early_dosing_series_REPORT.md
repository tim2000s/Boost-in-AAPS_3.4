# 2026-07 Early-Dosing Series — consolidated backtest report

**Window:** 2026-07-03 → 2026-07-06 &nbsp;·&nbsp; **Cohort:** anonymous users `tim, A–H` (letters only) &nbsp;·&nbsp;
**Source:** TimescaleDB `oref` (deduped `boost_decisions` / `boost_cgm`), refreshed before each analysis, plus targeted Nightscout pulls &nbsp;·&nbsp;
**Scripts:** [`backtesting/scripts/2026-07-early-dosing-series/`](../scripts/2026-07-early-dosing-series/)

This report retro-applies the backtest protocol (see `backtesting/README.md`, "Backtest protocol"):
every dosing-lever decision this week was backed by a decision-level replay; the scripts and the
numbers now live in the repo instead of a session scratchpad. All replays are **decision-level**
(no glucose-outcome simulation) — see the limitations section at the end.

The through-line of the week: Tim's question *"how do we get insulin in earlier / keep highs
shorter, safely?"* — tested lever by lever. Three "dose more after a confirm" levers were rejected
on harm pricing, the safe timing levers shipped, one genuine incident produced a shipped cap, the
auto-config migration was validated cohort-wide with five amendments, and one new systemic defect
(Phase-3 brake compounding) was found, bounded, and shipped shadow-first.

---

## 1. Post-confirm-high lever 1 — RECOVERING standard-SMB · REJECTED (2026-07-03)

**Question.** When BG stays high after a CONFIRMED meal and V6 sits in RECOVERING, should it dose
oref-style (a portion of basal as SMB) instead of holding at 0.4×?

**Method.** Cohort backtest over 606 post-confirm high episodes (7 users, 271 user-days, deduped
`boost_decisions`); counterfactual = dose to `v1WouldDose` during the episode.

**Key numbers.**

| finding | value |
|---|---|
| Episodes self-resolving <160 within 2 h on existing IOB | **77%** |
| Episodes ending <70 within 3 h | 19% — and **112 of 115 lows came from the self-resolving group** |
| Genuinely addressable (stuck + falling IOB + never re-engaged) | **26/606 (4%)**, ~8.4 U total (~0.03 U/user/day) |
| Counterfactual dosing to v1WouldDose | +227 U total; **+32.8 U into episodes that ended low** (21 lows deepened >0.5 U, 11 by >1 U) |
| Benefit : harm | ≈ **1 : 4, wrong direction** |

Spot check (tim, 2026-06-04): CONFIRMED 18:19, climb to 255 by 19:39 while V6 held back, then a
255→59 free-fall on 3.4 U IOB. Extra insulin would have made it severe — the machine was correct
by outcome. Structurally, RECOVERING persists only while delta ≥ 0 AND score ≥ 0.18; falling delta
exits to IDLE where the non-meal cap gives V1 parity. "Stuck in RECOVERING while high" therefore
means *still rising, score-corroborated* — the most dangerous population for extra insulin. Median
episode: 10 min.

**Verdict.** REJECTED — the stuck tail is tiny (≈2.5% of episode time), high-IOB by nature, and
every added-insulin mechanism feeds lows at base rate.

**Scripts:** `recovering_analysis.py`, `followup.py`, `dbg.py` · **Shipped:** nothing (the
rejection is the result).

---

## 2. Post-confirm-high lever 2 — sustained-delta re-engage · REJECTED (2026-07-03)

**Question.** Re-engage RECOVERING→COMMITTED when delta > 3 for N consecutive cycles and BG offset
> 20 — does any guard combination make that safe?

**Method.** 10 guard variants replayed over 1,501 RECOVERING runs; each variant scored on the 26
residual "stuck" episodes from §1, on the tim 06-04 crash episode, and on pre-low pricing.

**Key numbers.**
- The **only** guard that refuses the 06-04 crash is IOB-headroom (G2, IOB > p75-at-CONFIRMED) —
  but high IOB is the *defining* property of the stuck episodes the rule targets. Structural bind.
- Safe family: catches **1/26** residual episodes, **0.00 U** realistic insulin recovered.
- Effective family (7/26): fires on 06-04 (**+2.03 U** before the 255→59 plunge); **15% of firings**
  land inside a <70-within-3 h window — exactly base rate, i.e. the guards buy zero selectivity on lows.
- Least-bad variant (G1b+G2+G3, N=3, BG>160): never fires on tim-class crashes but catches ~nothing.

**Verdict.** REJECTED — every variant fails at least one leg of the bar. Existing accel-based
re-engage kept unchanged. If ever revisited: shadow would-fire telemetry only. The target
population ≡ the harm population on the IOB axis.

**Scripts:** `reengage_backtest.py` · results table `reengage_variants.csv` · **Shipped:** nothing.

---

## 3. Post-confirm-high lever 3 — committedCap raise · REJECTED cohort-wide (2026-07-03)

**Question.** Are cap-starved meals causing the post-confirm highs — would raising committedCap
(×1.5 / ×2, or auto-config p75→p85) fix them?

**Method.** Era-aware backtest (caps only operative from ~06-01 tim / ~06-17 cohort; tim's
auto-config cap = 0.40).

**Key numbers.**

| finding | value |
|---|---|
| Cap binds on dosing COMMITTED cycles | **42%** (tim 39%, ~4 clips/day) |
| Meal-phase under-delivery vs V1 occurring on cycles **below** the cap | **72%** (budget/velocity/gates, not the ceiling) |
| Clipped phases → stuck-high vs unclipped | 7% vs 8% — premise **not in the data** |
| Pre-low pricing of the ×1.5/×2 extra insulin | 14–17% (base rate; bar is ≲10%) |
| Confirm-floor coupling (floor = min(ccap, 0.8×confCap)) | raising the cap **blocks more confirms** — +18% of tim's confirms newly blocked at ×2 |

**Verdict.** REJECTED as a cohort-wide lever (three independent failures + an actively
counterproductive coupling). Later **reclassified per-user** by the 07-06 re-review (§12): the
cohort premise-failure stands, but *individual* raises for cap-clipped users are affirmed
(see §6, §9, §10). Genuine survivors: (a) users A/C/D ran hardcoded 0.25 **below** their formula
caps — config hygiene, which became the migration work in §6; (b) watch-item: the confirm gate
blocks 35–56% of fresh confirms (reconstructed) → cap/gate telemetry shipped (`e29630409b`).

**Scripts:** `capraise_backtest.py` · **Shipped:** telemetry only.

---

## 4. Early-dosing audit — the capstone (2026-07-03)

**Question.** Given §1–§3, what *does* move insulin earlier safely?

**Method.** Cohort DB, 73,840 deduped cycles, 1,094 confirms with detectable rise onset
(≥2-consecutive-delta>3). Base rate: 17–20% of ALL cycles precede a <70-in-3 h.

**Core principle established: MOVED insulin ≠ NEW insulin.** Shifting the same commit shot 1–2
cycles earlier (where score was already ≥0.55): harm Δ **0.0 pp / +0.5 pp**, landing IOB 1.15→0.60 U.
Every lever that *added* insulin priced at +14–17% into lows. Timing corrections are free; volume
additions are not.

**IOB-harm curve — real but trapped.** Pre-low % of dosing cycles at BG≥140 rises monotonically
6.7% (IOB<2.5%TDD) → 19.5% (10–15%TDD). But the unguarded early pool (onset→confirm window) is
21.4% pre-low — 24.9% in its LOW-IOB slice — because rises from low IOB are disproportionately
hypo-rebounds. "Early = safe" holds **only** inside BG≥140 ∧ IOB<5%TDD (14.1%). A blanket
OBSERVING-multiplier raise is contraindicated.

**Confirm latency:** median 15 min onset→CONFIRMED (tim 20); **53% mechanically limited** (score
was ready ≥2 cycles before — the age gate is the blocker), 47% score-limited.

**Ranked levers and outcomes:**

| # | lever | number | outcome |
|---|---|---|---|
| 1 | Confirm-gate over-block review | 26–29% of blocked confirms preceded BG>180 (historical) | live 23 h review same day: **no red flag** — the only observed daytime block self-corrected in one cycle; telemetry gaps (gate verdict, prospective shot, aggression knob) closed by `6067ec9a6d` |
| 2 | Age-gate −1 when score-ready | 1.5 U/user-day arrives 5 min sooner, **0.0 pp harm** | **SHIPPED** `242a6e179d` |
| 3 | Fast-path retune Δ≥6 / accl≥10 / score≥0.65 | +21 meals ~9 min earlier, false fires 39%→32% (plain relaxation is worse: 40%) | **SHIPPED** `d2f9a08108` |
| 4 | OBSERVING raise in the guarded cell only | 0.21 U/day at 14.1% | parked unless 1–3 underdeliver |
| 5 | Meal-time anticipation | onsets within ±90 min of top-3 personal modes = 34–52% vs 37.5% uniform chance | **DEAD** — learner deprioritized |

**Scripts:** `early_dosing.py` (+ `fetch_ns.py` pull helper) · **Shipped:** `242a6e179d`,
`d2f9a08108`, `6067ec9a6d`.

---

## 5. Post-rescue meal-state cap · SHIPPED (2026-07-04)

**Question (incident-driven).** 2026-07-03 19:47: V6 CONFIRMED **2.7 U at BG 119, thirty minutes
after a nadir of 40** (rescue-carb rebound, pump previously suspended, IOB≈0). The fast-path rescue
guard correctly blocked two fast confirms — but the non-meal cap's *meal-state exemption*
(`overrideDose = if (inMealState) finalDose else min(finalDose, v1WouldDose)`) discarded V1's
hypo-restrained 1.05 U. Outcome 181→nadir 81, zero margin. What's the fix, and does it price well?

**Fix.** Suppress the exemption when `recentLowBG45Min < 75` — meal states capped at v1WouldDose
for 45 min after a low. Same source value + threshold as V1's own post-rescue tier guard, so inside
the window the cap inherits a hypo-aware limit. De-amplifies, never blocks; expires ≤45 min.

**Backtest (SHIP verdict).**

| finding | value |
|---|---|
| Meal-state cycles that are post-rescue | 20.4% (4.1/user-day) |
| Era-honest insulin removal | 0.30 U/user-day |
| Removed insulin sitting directly pre-<70 | **27%** — the best-priced removal of the whole review (every other lever: 14–19%) |
| Post-rescue meal episodes double-dipping (second low) | 33% vs 19% base |
| Cost | 10% of genuine post-hypo meals, median **0.15 U** under-delivery, 0% double-dip, peaks ~228 even with amplification |
| Incident replay | 1.05 U + preserved cumulative-cap headroom ≈ right insulin (actual nadir 81 proves 2.7 U was ~1.6 U over) |

**Verdict.** SHIP. **Shipped:** `c306241a35` (experimental, full: code+docs+tests; +
`boostV5_postRescueWindow` RT field), cherry-picked to dev as `79a3e53220`.

**Scripts:** `postrescue_cap.py`.

---

## 6. Auto-config migration — cohort backtest ×4 replay groups (2026-07-06)

**Question.** The per-knob auto-config migration (`b2c0705e5e` — the "user H rescue", §9) will
re-derive knobs for every existing install. Is it safe for all 8 telemetry users?

**Method.** Four parallel decision-level replays (user groups A/B, C/D, tim/E, F/H), 28-day
windows, replaying the derivation formulas against each user's actual treatments/CGM and pricing
the dose deltas.

**Per-user upshot:**

| user | migration effect | verdict |
|---|---|---|
| tim | only ccap 0.5→0.40 (TDD/40 on U200 pump-units), −0.02 U/day | neutral |
| A | textbook rescue: 0.5→1.21, conf 2.5→6.8, cum→6.8 — **+3.4–4.5 U/day at 2.1% pre-low vs 3.4% base** | rescue validated (but conf from n=4 boluses → amendment 4) |
| B | **CAUTION** — deliberately reverted to factory 07-04; migration would set ccap 1.54 (3× his choice); added insulin **44.7% pre-low vs 32.8% base** | THE raise-guard case → amendment 5 |
| C | old-era factory 0.25/1.0 → 1.20/4.00, +44% shadow insulin; aggr flips 1.0/0.92 on the 4%-TBR boundary | rescue, needs amendment 1 |
| D | hypo-heaviest (11.7% TBR<70): tightens hard — conf clamped to 2.0, aggr 0.85, FCC off, cum 2.9 → **net −26%, removals 2.5:1 protective:costly** | safety half validated |
| E | ccap→0.62 raises the confirm floor → blocks most of his tiny confirms (budgets ~0.2 U) | exposed cumulative-from-derived incoherence → amendment 3 |
| F | main change conf 2.5→6.0 (clips ~1/day today; 0/7 unclipped events pre-low) | ship |
| H | near no-op (he self-escalated ccap to 1.8 on 07-06); sole effect cum 10→6 — the max(5,conf) clamp causes 6/8 suppressions | → amendment 2 |

**Five amendments required (all implemented same day):**
1. **BLOCKER — historical factory defaults**: old builds shipped ccap 0.25 / conf 1.0 / cum 6.0; a
   value-vs-*current*-factory test would freeze C/D at their tightest-ever values. Fix: per-key sets
   of ALL historical defaults (verified from git history) + per-knob classification logging.
2. Cumulative clamp → `clamp(conf + 2×ccap, 1.0, 10.0)` (kills "one confirm exhausts the hour").
3. Cumulative computed from **resolved** (kept-or-derived) caps, not raw derivations.
4. confirmedCap manual-bolus p90 term requires **n≥10**, else p95-SMB path.
5. **TBR raise-guard**: dose-cap *raises* not applied when TBR<70 > 4% — notify-suggest instead;
   lowerings always apply. (Re-review §12 added a <54 ≥1% co-guard — catches user B.)

**Verdict.** Mechanism VALIDATED (A/C/F rescued; D correctly tightened), amendments mandatory
before rollout. **Shipped:** `b2c0705e5e` (per-knob migration) → `fe9d8a1a13` (amendments, 27
tests) → `131923247e` (versioned re-migration, AUTO_CONFIG_SCHEMA_VERSION=2, 31 tests) →
`69f4a928fc` (ML-outage renormalize 1.25→1.2299, found by the parallel Trio audit).

**Scripts:** `mig_fetch_treatments.py`, `mig_common_fetch.py`, `mig_formula.py`, `mig_replay.py`,
`mig_AB_analysis.py`, `mig_CD_analysis.py`, `mig_CD_followup.py`, `mig_self_E_backtest.py`,
`mig_stress.py`, `mig_unclip.py`, `mig_v1era_sim.py` · per-user reports `mig_C_report.txt`,
`mig_CD_report.txt`, `mig_D_report.txt`.

---

## 7. Plateau analysis (tim) — parity lever REJECTED, real mechanism found (2026-07-05)

**Question.** Tim: "I get stuck above 160 after small meals — V6 won't finish the job."

**Method.** 14-day replay of tim's decisions/CGM; plateau episodes classified; V1-parity gap
measured cycle-by-cycle.

**Key numbers.**
- Complaint real (4.2 h/day >160) but **reframed**: 49% of >160 time is big-meal (>200) aftermath;
  strict small-meal plateaus = 10% of small meals, median 10 min, ~5% of high time.
- Plateau V1-parity gap measured properly = **0.13 U/day** (binding constraint = vf 0.4 flat-BG
  floor × OBSERVING 0.3× rounding to zero — not gates, not ML).
- Pricing: **31.7% of that insulin pre-low** vs his plateau base 21% (itself 2× cohort) → REJECTED.
- Stacking premise FAILED: second rises confirm at 64% vs 34% fresh — repeat meals are not starved.
- **Real mechanism: cumulative SMB cap 2.5 < his formula 4.0** — 18 cap suppressions in 2 live
  days, 8 at BG 150–190: one meal confirm spends the hour's budget, then every plateau correction
  zeroes. Same config-hygiene class as §6. (Tim raised it to 5.0 on 07-05.)

**Verdict.** Plateau-parity lever REJECTED for tim (stands on futility: 0.13 U/day at bad pricing);
the actionable was config hygiene + a telemetry gap — the cumulative cap was invisible to analysis.
**Shipped as a result:** `boostV5_cumulativeCapU` + `boostV5_smbVol60Min` RT fields (`2554b7f963`).

**Scripts:** `self_plateau.py`.

---

## 8. Phase-3 brake compounding — forensic + floor sweep (2026-07-06)

**Question.** Two same-day stuck highs on tim's device. Defect or design?

**Method.** Forensic reconstruction: every one of 17 cycles reproduced *exactly* from telemetry
(`fd = budget × actionMult × vf × stateCap × iobHeadroomBrake × decelBrake → 0.05 U floor-round`),
then a cohort-wide floor sweep over 40,180 capped-era cycles.

**Episode A (10:03Z, 174→255 in COMMITTED, budget=0 throughout): NOT a defect.** oref's insulinReq
was −0.9→−1.36 at IOB 3.93 after a full 3.0 U confirm; V1 base-would = 0.0 every cycle; outcome
peak 248 → glide to 86 on zero further insulin, no hypo. Budget = f(baseInsulinReq) zeroing at high
IOB is oref working.

**Episode B (13:08Z lunch, fresh site): genuinely starved** → 297 unresolved, manual 2.0 U at
14:41. Four contributors: (i) one benign budget-zero pause; (ii) committedCap 0.5 clipping raw
1.35–2.13 U holds to 0.4; (iii) premature RECOVERING at 13:38 while BG 261 still climbing (3rd
sighting of the re-engage gap); (iv) **the new mechanism: six consecutive fd=0 at BG 268–277 —
RECOVERING 0.4× × vf 0.40–0.50 × iobHeadroom 0.85 × decel 0.30 = 4.1% of budget → sub-pump-step →
zero for 30 straight minutes.** The multiplicative brake-stack V5 was built to kill, reassembled
downstream of the budget floor. V6 enacted 3.65 U vs base-would ~10.8 U across the episode.

**Floor sweep (cohort, 40,180 cycles): the compounding is SYSTEMIC** — median composed multiplier
on eligible stuck-high meal cycles = **0.037**.

| floor option | added insulin | pre-low pricing | note |
|---|---|---|---|
| F=0.25 (chosen) | 0.76 U/user-day | 16.6% (= base rate) | fails the strict selectivity bar; redeemed as a pipeline-**defect** fix with bounds: ≤committedCap/cycle, in-session only, 35% v1-bounded |

- Episode B dead stretch: 0.30 → 1.65 U; combined with ccap 1.0 → **10.6 U ≈ the 10.8 U base-would
  shape, staged**. Episode A untouched **by construction** (the floor multiplies budget; 0 stays 0 —
  never overrides oref's insulinReq verdict).
- User H gets **zero** from the floor — his stuck cycles are v1-parity or budget=0 (→ §9).
- tim's cap verdict: **1.0, not 1.5** (1.5 buys ~nothing; 19% pricing < his 24.4% hold base).
- **Critical coupling:** raising committedCap doubles the confirm-gate floor (min(ccap, 0.8×conf))
  → the committed term must be pinned at 0.5 before any cap raise.

**Verdict.** Episode A = design working; Episode B = composed-brake defect, fix shipped
shadow-first with the gate coupling pinned. **Shipped:** `311703ddf5` (gate-floor pin,
`CONFIRM_FLOOR_COMMITTED_TERM_MAX=0.5`, behaviour-preserving), `e0f18ddd0e` (composed floor F=0.25
**shadow-only**, `boostV5_floorWouldAdd` RT field, validation week before activation),
`2554b7f963` (cumulative-cap telemetry). Activation is per-user TBR-gated (§12).

**Scripts:** `phase3_floor_backtest.py` · forensic evidence `forensic0706/cycles.csv`,
`forensic0706/reconstruction.txt` (the 17/17 exact cycle reconstruction).

---

## 9. User H (user H) — budget-side investigation · CLOSED, correct by outcome (2026-07-05/06)

**Question.** User H (announces meals, TDD ~50 U, V6-ACTIVE since 06-30): "not enough insulin
early." Diagnosis, then: why is AggressionBudget=0 on his climbs?

**Method.** 22k decisions pulled to DB; dedupe per 5-min bucket; meal-episode decomposition;
then exact budget-formula verification and outcome adjudication of every budget=0 >180 stretch.

**Diagnosis (07-05).** Complaint validated: V6 era vs V1 era TING 79→73%, >180 2.8→5.4%, meal
peaks 161→179 — but hypos halved (<70 2.21→0.81%; his V1 era was above hypo target, so part of the
restraint was correction). Gap decomposition of his 21.7 U meal gap: **cap-clipped COMMITTED 44%**
(pinned at factory 0.5 while base wanted 1.20/cycle — his formula says 1.24; the exception the
cohort rule §3 allows), RECOVERING-during-rise 28%, OBSERVING 14%. → Config recommendation
(ccap 0.5→1.2, conf 4→6) + the root-cause of *why* auto-config never fixed him: two real defects
(key-presence "user-touched" test; global one-shot flag that travels via settings export) →
**shipped `b2c0705e5e`** (§6).

**Budget-side (07-06).** Verified: budget == max(0, oref insulinReq) **exactly** (96% of cycles to
the cent; no velocity term; mlHypoRisk irrelevant). His budget=0 climbs = unannounced eating
(COB=0) with his own bolus IOB 3.5–4 U aboard + dynISF strengthening as BG climbs → predictions
said "covered" — **and were right 5/5**: every V6-era budget=0 >180 stretch resolved <160 within
90 min of stretch-end on existing IOB, 0 lows, eventualBG unbiased at +60 min. V1 was faster only
because tiers added ~0.5 U/cycle of velocity insulin his predictions called unnecessary
(harm-neutral for him: 10.5% vs 10.6% base — it bought descent *speed*, not missing correction).
ISF recalibration: DEAD (predictions unbiased).

**Verdict.** Design decision, not a bug — V6 trades V1's speed for prediction-led restraint and
his data endorses the trade. Optional per-user **opt-in velocity-budget floor** (budget :=
max(insulinReq, tier-equivalent) when delta>3 ∧ BG>180, committedCap-bounded, shadow-first) is
defensible for him (+1.6 U/day, historically harm-neutral) — upgraded to YES-for-him by §12 —
but must NOT ship as cohort default (thrice-rejected class for rebound-driven users).

**Scripts:** `analyse_H.py`, `analyse_H2.py`, `analyse_H3.py`, `export_H_episodes.py`,
`userH_budget.py` · **Shipped:** `b2c0705e5e` (+ §6 follow-ons).

---

## 10. User A (Joost) — latest-model replay (2026-07-06)

**Question.** Same complaint as user H ("not enough, not early enough"), pure UAM (0
announcements). What does the *latest shipped stack* (early-confirm + fast-path retune +
post-rescue cap + amended auto-config) do for him?

**Method.** 14-day decision-level replay of the full current stack against his history.

**Key numbers.**
- Baseline: TING 61.5%, >180 3.3 h/day.
- **Dominant mechanism = committedCap clipping**: ~10 holds/day pinned at factory 0.5 with budgets
  >1 U. The amended migration derives **1.09** (TDD-window-sensitive 1.09–1.21) → restores
  **+4–6 U/day at 2.3% pre-low vs 7.6% base** — his complaint ≈ solved by installing the update.
- Early-confirm moves 10/79 confirms earlier + 2 fast-path catches (free, moved insulin).
- Amended confirmedCap 2.5→2.33 via the n≥10 min-sample guard (n=4 manual boluses → SMB path) —
  the amendment working as designed.
- Gate floor pinned at 0.5: no regression. Shadow floor prices mediocre for him (12.3%) — stays shadow.
- ~¼ of his high time (0.85 h/day) is budget=0 / insulinReq≤0 **Episode-A class** — deliberately
  untouched; re-adjudicate at +7 days; velocity-budget conversation only if the residual persists.
- Kill-switch: cap back to 0.5 if TBR<70 doubles from 1.27%.

**Verdict.** Install-the-update is the fix; no new code lever needed for him.

**Scripts:** `user_a_replay.py`.

---

## 11. HR ↔ glucose lead-lag · NULL RESULT (2026-07-06)

**Question.** Does heart rate lead glucose rises — i.e. can HR substitute for the retired
meal-time learner as a meal-signal input?

**Method.** TimescaleDB-wide: 37,141 paired 5-min cycles across 6 users, ~1,942 rise onsets;
residualized correlation, circular-permutation CCF, event-locked composites, and a hypo-tachycardia
positive control.

**Key numbers.**
- Raw BG↔HR **+0.18 is a circadian artifact** (both peak midday); residualized = 0 to weakly
  negative for every user (pooled −0.08). An earlier 9-day small-sample "sedentary +0.19 / asleep
  +0.38" did **not** replicate — noise. (The DB-first directive vindicated immediately.)
- Only significant CCF feature: |r|=0.063 at lag −10 min, **negative**, p=0.003 — HR rises ~10 min
  before BG **falls** (exercise/uptake coupling; redundant with steps). No positive HR-leads-rise
  signal at any horizon ±90 min.
- Sedentary rise onsets (n=1,098): HR **dips** −1.5 to −2 bpm — no cephalic/anticipatory lift.
- Positive control passes — weakly (+1.4–1.7 bpm) on the DB's 15-min-smoothed hr_avg, strongly
  (+6 to +13.6 bpm, p=0.014, small n) on instantaneous NS HR → **the DB's 15-min smoothing erases
  transients**; any future HR-transient analysis needs instantaneous/1-min HR.

**Verdict.** HR earns no place in the meal-signal score as currently sensed; its only algorithmic
value is movement confirmation (already covered by steps) and possibly hypo corroboration via
unsmoothed HR (untested at power). **Shipped:** nothing (null result preserved).

**Scripts:** `hr_bg_fetch.py`, `hr_bg_fetch_entries.py`, `hr_bg_analysis.py`, `hr_bg_events.py`,
`hr_bg_extra.py`, `hr_bg_db_analysis.py`, `hr_bg_ccf_strat.py`.

---

## 12. Absolute-TBR re-review — every verdict re-run under the formal bar (2026-07-06)

**Question.** The week's verdicts were made with evolving harm metrics ("% pre-low" vs base rate).
Re-adjudicate all of them under one formal, absolute bar (below). Any flips?

**Method.** Each lever's projected insulin delta converted to a TBR bracket per user and tested
against the absolute gates; nadir-deepening reviewed separately on <60 episodes.

**Outcomes (no flips, four refinements):**

| verdict | re-review outcome |
|---|---|
| RECOVERING-SMB (§1) + re-engage (§2) | **STAND** — now formally on the <54/nadir-deepening axis |
| committedCap cohort rejection (§3) | **RECLASSIFIED**: premise-failure cohort-wide + B/D safety; **per-user raises affirmed**; tim's 1.0 cleared on the 14d window (his 30d 4.01/1.24 was the 06-14→18 cluster; 14d = 2.51/0.37) |
| Plateau parity (§7) | STANDS — on futility, not danger |
| Composed floor (§8) | STRENGTHENED but **activation per-user TBR-gated: activate A/E/F/tim; hold B/C/D** (B +→4.24%, C +→4.50% upper bracket) |
| Velocity-budget opt-in (§9) | **UPGRADED: YES for user H** (≤1.6% projected, widest margin of the week); user A conditional on his +7d residual |
| TBR raise-guard (§6 amendment 5) | AFFIRMED + **new code item: <54 ≥1% co-guard** (catches user B: <70 3.83 under 4, but <54 1.01 over 1) |

Cohort 30d baselines (TBR<70 / TBR<54, 2026-07-06): A 1.11/0.22 · B 3.83/1.01 · C 3.82/0.60 ·
D 10.14/1.81 · E 1.04/0.00 · F 2.99/0.35 · G 6.34/1.48 · H 1.35/0.28 · tim 4.01/1.24 (30d),
2.51/0.37 (14d). Users over the absolutes (D, G) get removal/neutral levers only + clinical-review
escalation.

**Scripts:** re-uses the §1–§10 scripts' outputs; no separate script.

---

## The two-test bar (decision framework, Tim-approved 2026-07-06)

Every dosing lever from now on is judged by:

- **Test A — absolute gate, per user (hard):** projected trailing-**14-day** TBR<70 +
  upper-bracket ΔTBR ≤ **3.5%** AND TBR<54 + Δ ≤ **0.8%** (deliberate margin under the consensus
  4% / 1%). The **30-day** figure is tracked as *trend only* — window choice materially changes
  verdicts (see tim's cap in §12). Any lever adding insulin to episodes with nadir <60 additionally
  gets a **nadir-deepening review** — the <54 axis is the severe-harm axis and doesn't average away.
  Users already over the absolutes get removal/neutral levers only.
- **Test B — efficiency ranking among Test-A passers:** **moved insulin ≻ new insulin**; new
  insulin should price below the *user's own* base pre-low rate; base-rate pricing is acceptable
  only with a wide Test-A margin plus a demonstrated mechanism fix (e.g. §8's pipeline defect).
- **ΔTBR conversion bracket** (no glucose simulation available): extra low-minutes per pre-low
  unit ≈ **[0.15, 0.6] × ISF**. When a lever lands within-bracket of a threshold, the decision
  moves to **live telemetry**, not replay.

## Going-forward protocol

1. **DB refresh first.** Source = TimescaleDB (`oref`); refresh to t=now before analysis
   (`backfill_all.sh`, or targeted `--since` for one user). Never analyze a stale window silently.
2. **Scripts are standalone local Python**, committed under `backtesting/scripts/<series>/`.
3. **Reports committed under `backtesting/reports/`** with the results *contained* (numbers in the
   markdown, not pointers to ephemeral scratchpads). This report is the retro-application: the
   week's evidence for shipped dosing changes previously lived only in a session scratchpad.
4. Test A / Test B framing applied inside every report.

## Honest limitations

Everything above is a **decision-level replay**: counterfactual doses are priced against what
actually happened next, but the counterfactual insulin never moves subsequent glucose — a lever
that doses more would change the very BG trace it is scored on. "Base-would" / "v1WouldDose" are
therefore no-feedback counterfactuals, systematically flattering to added insulin on the benefit
side and priced only by temporal association on the harm side: the **low3h / pre-low attribution
is association, not causation** (an SMB before a low that was already coming gets charged for it;
one that caused a low it barely preceded may escape). Pre-telemetry eras reconstruct the velocity
factor only within **vf ∈ [0.4, 1.0] brackets**, so gate/floor numbers for those eras are ranges,
not points (the confirm-gate "26% needed" over-estimate that the 23 h live review corrected is the
canonical example). ΔTBR projections use the [0.15, 0.6]×ISF bracket rather than simulated
glucose — which is exactly why Test A carries margin under the consensus thresholds and why
within-bracket calls defer to live telemetry. Additional specifics: UTC+1 was assumed for all
users in the early-dosing audit; onset detection excludes confirms without ≥2-consecutive-delta>3
onsets; some users have short V6-ACTIVE windows (user H: 5.5 days, ~19 meal episodes).

---

## Appendix — source files not committed

Per the repo privacy policy (`backtesting/README.md`: no raw glucose series, no raw pulls in the
repo) and the >1 MB raw-pull rule, the following scratchpad files were **not** copied. All committed
numbers are contained above; raw data is reproducible from the DB / NS with the committed scripts.

- **Raw NS/DB pulls (.json, >1 MB or raw-trace):** `devicestatus_7d.json` (25 MB),
  `devicestatus_early.json` (9.5 MB), `devicestatus.json`, `ds_live.json`, `ds_week.json`,
  `entries*.json`, `inc_*.json`, `ns_14d.json`, `treatments*.json`, `mig_*_treatments*.json`
  (×10, 1.8–3.2 MB each), `mig_C_entries_28d.json`, `mig_D_entries_28d.json`,
  `mig_E_entries_28d.json`, `mig_tim_entries_28d.json`, `hr_bg_devicestatus.json`,
  `hr_bg_entries.json`, `sample_ds.json`; `forensic0706/{devicestatus,entries,treatments}.json`.
- **Binary/large intermediates:** `hr_bg_arrays.npz`, `hr_bg_db.csv` (6.3 MB),
  `mig_CD_cycles.csv` (1.4 MB).
- **Per-user trace CSVs (privacy policy — raw glucose/decision series):** `confirm_events.csv`,
  `episodes.csv`, `episodes_v2.csv`, `live_gate_cycles.csv`, `H_v6era_cycles_deduped.csv`,
  `mig_CD_cgm.csv`, `mig_E_cgm.csv`, `mig_E_decisions.csv`, `mig_E_tdd.csv`, `mig_tim_cgm.csv`,
  `mig_tim_decisions.csv`, `mig_tim_tdd.csv`; `forensic0706/reasons_all.txt`.
- **Small result .json (extension policy; numbers reproduced above):** `mig_AB_results.json`,
  `mig_E_report.json`, `mig_tim_report.json`, `oref_probe_results.json`.
- **Out-of-series scripts/logs:** `analyse.py`, `climb_cut.py` (predBG forecast accuracy — separate
  analysis), `wake_replay.py` (sleep-detector replay), `bisect_g.py`, `probe_g.py`,
  `probe_devices.py`, `probe_sites.py`, `probe_trio.py`, `probe_oref_sites.py`,
  `regress_variant.py`, `test_trio_parse.py`, `mig_refresh_AB.sh` (site-refresh wrapper),
  `full_extract_v5.py.bak`, `*.js` (analyser-tool work), `*.log`, `*.html`, `DBv5_experimental.kt`.

**Redactions applied to committed scripts** (the repo is public; tokens/URLs replaced with
`<REDACTED>`): `fetch_ns.py` (NS base URL + token), `hr_bg_fetch.py` (NS base URL + token),
`hr_bg_fetch_entries.py` (NS base URL + token), `mig_common_fetch.py` (2 NS site URLs + 2 tokens),
`analyse_H.py` (surname initial trimmed from a docstring). The fetch scripts require the operator to re-point `BASE`/`TOKEN`
or `~/.config/boost_backtest/sites.json` locally; they will not run as committed — deliberate.

---

# 2026-07-08 RE-VALIDATION (pre-promotion experimental→dev)

DB refreshed to t=now first (all 8 cohort users fresh to 2026-07-08 ~11:34; only oref-pipeline site
U018 failed — not a boost cohort user). Re-ran committed `phase3_floor_backtest.py` +
`floor_activation_tbr_gate.py` (new supplement, items 4/5). Numbers vs the original committed run:

## Items 1–2: systemic compounding + floor F=0.25 — HOLD (essentially unchanged)

| metric | ORIGINAL | CURRENT (07-08) |
|---|---|---|
| capped-era cycles | 40,180 | 44,011 |
| eligible stuck-high meal cycles | 1,133 | 1,301 |
| **median composed post-budget multiplier** | **0.037** | **0.045** |
| **F=0.25 added U/user-day** | **0.76** | **0.75** |
| **F=0.25 pre-low pricing** | **16.6%** | **15.7%** (cycle base-rate 14.7%) |
| stuck episodes rescued (≥0.5U) | 32/109 | 35/121 |

The systemic compounding still holds (median mult 0.045 ≈ 0.037 — half of eligible stuck-high meal
cycles still deliver <4.5% of budget). F=0.25 still adds ≈0.75 U/user-day at ≈15.7% pre-low. **The
"bounded DEFECT fix, not a selectivity-passing TIR lever" framing STANDS unchanged**: 15.7% ≈ the
14.7% cycle base rate, still fails the strict ≲10% selectivity bar; justified only as a compounding-
defect floor. Nothing moved materially.

## Item 3: Episode-A (budget=0) invariant — HOLDS by construction

75,145 budget=0 cycles in the V6 set; the floor's eligibility gate requires `budget>0`, and the
floored dose is `budget×F` (= 0 when budget=0). 100% of budget=0 cycles already have fd=0 (oref's
insulinReq verdict). The floor cannot override a budget=0 hold — confirmed in the current replay.
User H remains outside the era map (no capped-era rows) → gets zero from the floor, as before.

## Item 4: per-user TBR on current data (14d + 30d)

| user | 14d TBR<70 | 14d TBR<63 | 14d TBR<54 | 30d TBR<70 | 30d TBR<54 |
|---|---|---|---|---|---|
| tim | 2.99 | 1.38 | 0.42 | **4.08** | **1.14** |
| A | 1.39 | 0.70 | 0.35 | 0.88 | 0.20 |
| B | **4.49** | 2.60 | **1.35** | 3.46 | 0.77 |
| C | 3.12 | 1.56 | 0.48 | **3.95** | 0.68 |
| D | **9.44** | **5.13** | **1.83** | **10.12** | **1.86** |
| E | 0.60 | 0.10 | 0.00 | 1.15 | 0.00 |
| F | 1.06 | 0.53 | 0.13 | 2.68 | 0.32 |
| H | 0.64 | 0.20 | 0.02 | 1.26 | 0.22 |

## Item 5: shipped code gate (14d TBR<63 < 2.0%) vs manual verdict

| user | 14d TBR<63 | code gate | manual verdict | agree? |
|---|---|---|---|---|
| tim | 1.38 | ENGAGE | GO | ✅ |
| A | 0.70 | ENGAGE | GO | ✅ |
| E | 0.10 | ENGAGE | GO | ✅ |
| F | 0.53 | ENGAGE | GO | ✅ |
| B | 2.60 | SUPPRESS | HOLD | ✅ |
| D | 5.13 | SUPPRESS | HOLD | ✅ |
| **C** | **1.56** | **ENGAGE** | **HOLD** | **❌ DISAGREE** |

**6/7 agree. The one disagreement is user C** — TBR<63 1.56% < 2.0% so the code gate ENGAGES the floor,
but the manual two-test bar HELD C (original: C→+4.50% upper-bracket TBR<70). Root of the gap: the code
gate keys on **TBR<63 only**, which does not see C's elevated **TBR<70** (mild-low 63–70 band). C's
14d TBR<70 is 3.12% (borderline under the manual 3.5% bar) but her **30d TBR<70 is 3.95%** (over it) —
she is a genuinely wobbling borderline user, and the TBR<63 metric is too permissive to catch her.
Separation check: GO users' TBR<63 ≤ 1.38 (tim); HOLD users' TBR<63 ≥ 1.56 (C) — the true separating
threshold sits at ~1.4–1.5%, so the shipped **2.0% is ~0.5pp too loose** and lets C through.

**Calibration recommendation:** either tighten the gate to **TBR<63 < 1.5%**, or (preferred, since the
manual bar was TBR<70-primary) **add a TBR<70 < 3.5% co-check** — C's 30d TBR<70 3.95% would then
correctly hold her while all four GO users still engage. Note also **tim's 30d TBR<70 (4.08%) and <54
(1.14%) are both over the manual bar** though his 14d passes (2.99/0.42) — the gate correctly engages
him on 14d, but he is wobbling (recent evening-confirm hypo incident); worth a watch, not a hold.

## VERDICT

- **The floor backtest results HOLD on current data** — median composed mult 0.045≈0.037, F=0.25
  ≈0.75 U/user-day @ ≈15.7% pre-low, Episode-A invariant intact. Nothing moved materially; the
  defect-fix framing is unchanged. **The floor is clear to promote experimental→dev on the mechanics.**
- **The 2.0% TBR<63 activation gate is slightly MIS-CALIBRATED vs the manual per-user verdict**: it
  agrees for tim/A/E/F (engage) and B/D (suppress) but **would wrongly ENGAGE C**, whom the manual
  analysis held on TBR<70 grounds. Recommend tightening to TBR<63 < 1.5% or adding a TBR<70 < 3.5%
  co-check before relying on the automated gate for C-class borderline users. (This is an
  activation-gating calibration item, not a floor-mechanics blocker.)

### RESOLUTION (2026-07-08, Tim) — TBR<70 < 3.5% co-check, SAME 14d window for both

Shipped: the gate now engages the floor only if **TBR<63 < 2.0% AND TBR<70 < 3.5%**, both computed
over the **same 14-day window** (Tim's call — consistency + it is the documented two-test-bar window).
Correction to the calibration note above: on that consistent 14d window, **user C ENGAGES** — her *14d*
TBR<70 is 3.12% (under 3.5%) and 14d <63 1.56% (under 2.0%), so both pass. The manual "hold C" rested
on her **30d** <70 (3.95%), a different window. So the co-check does NOT hold C on 14d; it is the correct
two-test-bar PRIMARY gate that will hold any user whose *14d* <70 reaches 3.5% (C is not one right now).
Engaging C on current 14d data is defensible (she is within bar) and fail-safe: the self-updating gate
auto-holds her the moment her 14d low exposure crosses either bar. 30d-for-both was rejected because it
would also hold tim (30d <70 4.08%), switching off his own floor over the recent evening-confirm wobble.
