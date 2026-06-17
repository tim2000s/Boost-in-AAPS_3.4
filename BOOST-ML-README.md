# Boost ML + V5 Shadow Build — A Quick Read

*What this build of AndroidAPS does, why it does it, and what changes for the person actually wearing the pump.*

---

## The short version

This build takes Boost and adds two things on top: a small set of **machine-learning components that make hypos slightly less likely and meal-rises slightly less stressful**, and a **silent observer** called V5 that watches every cycle without changing what the pump does. Boost's DynISF formula, its tier ladder, and the way it sizes microboluses are unchanged in spirit. The additions sit alongside, contribute information, and occasionally apply a brake. Nothing about the underlying dose calculation has been replaced.

A user who flashes this APK and does nothing else will see two new fields in their Nightscout dashboard immediately (`mlHypoRisk`, `mlMealLikely`), seven more once the silent observer wakes up (`boostV5_*`), and gradually notice that the pump trims its corrections during moments when a low looks likely. Nothing else changes visually. There is no new setting to tune. There is no new mode to enable.

---

## Who this is for

People who already run Boost and want the safety benefit of probabilistic hypo prediction without changing the dosing logic they're already calibrated against. There is no medical claim here — these are improvements at the margins, not a redesign.

People who don't run Boost should stay on whatever they're using.

---

## What's different

Boost decides what to dose every five minutes by looking at the current blood glucose, the trend, the insulin on board, and a few derived quantities; picking one of eight tiers of response — from a small correction at the gentle end to a strong COB-triggered bolus at the aggressive end; and sizing the microbolus accordingly.

That logic stays the same in this build. What's added is a small layer of context that asks, before any dose is delivered: *given everything we know about the next four hours, is this dose the right size and shape?*

Concretely, four things are different:

### 1. A hypo-risk forecast every five minutes

A small machine-learning model — trained on a 28-user cohort contributing roughly three million decision cycles between them — looks at the eight inputs the algorithm has already calculated, and produces a single probability: the chance that blood glucose will dip below 70 mg/dL in the next four hours. The model was validated on five further users who weren't in the training set; the numbers came out essentially where the cross-validation said they would (more on this below).

The forecast is published to Nightscout in real time as `mlHypoRisk`, a number between 0 and 1. Watching it for a day or two builds intuition: it rises overnight as insulin on board accumulates, spikes after a meal correction, falls during exercise.

### 2. A meal-rise forecast every five minutes

The sister model. Same inputs, different question: what's the chance blood glucose will rise by at least 50 mg/dL in the next 90 minutes? This is what an unbolused (or under-bolused) meal usually looks like on a CGM. The model fires when a meal-shaped climb is starting — whether the carbs were entered or not. Published to Nightscout as `mlMealLikely`.

The meal model is the more reliable of the two. Across the five out-of-cohort validation users, it scored above the published cross-validation baseline on every single one. The meal signal turns out to be more universal than the hypo signal — a rising glucose curve with the right IOB shape looks the same across most physiologies.

### 3. Two brakes that act on those forecasts

This is where the dose actually changes. When `mlHypoRisk` rises above 0.3, every microbolus the algorithm wants to deliver is multiplied by a scaling factor that ramps from 1.0 down to 0.0 as the risk approaches 1.0. The size of the brake is published as `mlRiskScale` so it can be inspected after the fact.

When `mlHypoRisk` exceeds 0.6, a second brake kicks in: Boost's aggressive tiers (the higher tiers responsible for the larger correction doses, including the strong-acceleration tiers and the percent-scale tier) are skipped, and the algorithm falls through to one of the two conservative tiers (Enhanced oref1 or Regular oref1). The pump still doses if dosing is warranted — it just won't fire one of the larger response modes when the hypo forecast is loud.

Both brakes are strictly downward. Neither makes any cycle more aggressive than Boost would have been by itself. They can only soften.

### 4. A pre-meal-tier hold that delays a small set of marginal doses

When blood glucose starts climbing from near target with no logged carbs — the exact pattern of an unannounced meal whose carbs haven't been entered yet — the algorithm now holds the gentler tiers (Percent Scale, Acceleration, Enhanced oref1, Regular oref1) for one to three cycles, waiting for one of three signals to release the hold:

- Acceleration becomes deterministic (`delta_accl > 10`).
- Glucose climbs above 160 and is still rising (the safety backstop).
- The meal model says a meal is likely (`mlMealLikely > 0.5`).

If Boost's strong-acceleration tiers (the ones that fire for genuine meal-shaped climbs) become eligible during the hold, they fire normally — those aren't gated. The hold only affects the gentler tiers, which would otherwise fire small SMBs into what might turn out to be a fast-carb rebound rather than a real meal climb.

This was the most carefully-validated piece of the upstream work: 0 strong-tier doses were blocked across 20 real-meal events, and 80% of fast-carb pre-rescue over-doses were suppressed.

### 5. A small set of additional tweaks

The build also includes a refinement to the high-BG aggressive tier so that it keeps firing during sustained climbs into the 200s+ even after acceleration has plateaued, and a more responsive fast-carb release so that a genuine spike isn't held back by the rebound-protection logic for too long. These are the kind of small refinements that came out of months of incident reviews on the development branch.

---

## What V5 is — and why it's silent

V5 is a clean-slate redesign of the Boost decision logic, sitting on a different architectural principle: a three-phase **Observe → Confirm → Commit** state machine rather than the existing tier ladder. It's been running in production-shadow form on the developer's pump for several weeks. It is *not* used to dose insulin in this build.

What V5 actually does on this branch is **watch**. Every five-minute cycle, V5 sees the same inputs the active algorithm sees, computes what it would have done, and publishes seven fields to Nightscout describing that hypothetical decision:

| Field | What it means |
|---|---|
| `boostV5_score` | A confidence number between 0 and 1: how strongly V5 thinks a meal-like event is happening |
| `boostV5_state` | The state machine's current state — IDLE, OBSERVING, CONFIRMED, COMMITTED, or RECOVERING |
| `boostV5_age` | How many cycles V5 has been in the current state |
| `boostV5_budget` | V5's accumulated "aggression budget" in units of insulin |
| `boostV5_actionMult` | The action multiplier V5 would have applied for the current state |
| `boostV5_finalDose` | The microbolus V5 would have delivered (in units) — a direct comparison against the actual delivery |
| `boostV5_gateReduction` | Which safety gates fired, if any |

The point of running V5 silently is straightforward: **calibration data**. The CONFIRMED-state threshold, the safety-gate window, and the meal-detection components need to be tuned against real-world score distributions across multiple users before V5 is ever asked to drive a pump. Running V5 in parallel with the active algorithm, on multiple users, is what generates that data.

If something goes wrong inside V5 — a bug, a corner case, a thread it doesn't expect — the error is caught and logged. The active algorithm carries on as if V5 wasn't there. V5 cannot affect dosing; the path through which dosing decisions are made does not consult V5.

V5 also does not appear in the AndroidAPS plugin list. Users cannot enable or disable it. It runs because the active Boost plugin calls it at the end of every cycle.

---

## A second silent observer — the ISF shadow

Boost has a long history of debating one specific question: should the sensitivity ratio (the number that says "the user is currently 10% more sensitive than their 7-day baseline, so dose accordingly") be the **instantaneous** value, or should it be **smoothed** to dampen short-term noise? The publicly-released Boost takes the instantaneous value. A later development branch settled on a smoothed-with-a-3-hour-exponential-average approach. Both have plausible arguments behind them. Neither has been A/B tested cleanly because changing the sensitivity calculation changes everything downstream and no two days are comparable.

This build adds a way to test it without changing dosing. Every cycle, the algorithm now computes **both** the instantaneous sensitivity ratio it actually uses and the smoothed ratio it would have used under the alternative, and publishes both to Nightscout for direct comparison. Like V5, the shadow path is observation-only; the dose the pump delivers is determined by the instantaneous value as before.

Seven fields appear in Nightscout per cycle:

| Field | What it means |
|---|---|
| `isfShadow_ratioRaw` | The instantaneous tdd_24h / tdd_7d ratio — the same number Boost actually uses today |
| `isfShadow_ratioEma` | The 3-hour exponentially-smoothed version of the same ratio |
| `isfShadow_warmup` | A 0.0–1.0 number that climbs to 1.0 over the first five days of EMA history. While warming up, the shadow leans toward "no smoothing" so the user isn't comparing against an unsettled smoother. |
| `isfShadow_variableSens` | What `variable_sens` would have been if the smoothed ratio had been used (mg/dL/U) |
| `isfShadow_insulinReq` | What this cycle's `insulinReq` would have been |
| `isfShadow_microBolus` | What the delivered microbolus would have been |
| `isfShadow_deltaPct` | A single-number ISF summary: `(shadow variable_sens / actual variable_sens − 1) × 100`, implemented as `(ratio_v1 / ratio_ema − 1) × 100`. This is an ISF delta, not a dose delta: negative means the smoothed version would have given more insulin this cycle; positive means it would have given less. |

The interesting field to watch is `deltaPct`. In steady-state — TDD this week broadly matches TDD this month — it sits near 0%. When TDD is rising fast (heavy day, illness, bigger meals), the instantaneous ratio rises above the lagging EMA. Because `deltaPct` is the ISF delta, it goes mildly **positive**: the smoothed shadow has a higher `variable_sens` and would deliver slightly less insulin. When TDD is falling fast (active day, smaller meals, fasting), the instantaneous ratio falls below the lagging EMA, so `deltaPct` goes mildly **negative** and the smoothed shadow would deliver slightly more insulin. The sign is opposite to the dose delta. The two ratios diverge most during the first few hours of a TDD shift; over a 24-hour window they converge.

Over a week of observation, plotting `isfShadow_deltaPct` against actual outcomes (time-in-range, time-below-70, peak-after-meal) will tell whether the smoothing approach would have improved the user's day or simply produced different doses with similar results. If `deltaPct` ranges within ±5% and outcomes look similar, the instantaneous approach is a perfectly reasonable choice. If `deltaPct` swings to ±15-25% and bigger swings correlate with hypos or highs, the smoothing approach has a real argument behind it.

Note that this is a single-cycle counterfactual, not a full simulation. The shadow says "for this cycle, with everything else held equal, what would the smoothed approach have produced?" It does not re-simulate the entire day under the alternative — that would require running a parallel pump in parallel time, which obviously isn't possible. Differences accumulate over a day in ways the shadow can't see, but in practice over a 24-hour window they remain small (a percent or two) because the ratio difference is small at most points in time.

Like V5 shadow, the ISF shadow does not appear as a setting. It runs invisibly. The fields just show up in Nightscout.

---

## What the user sees and doesn't see

**Visible immediately in Nightscout**: `mlHypoRisk`, `mlMealLikely`, `mlRiskScale`, `mlMealG3Released`, `mlG3ReleaseSource`, plus the seven `boostV5_*` fields and the seven `isfShadow_*` fields. Useful for understanding what the algorithm is thinking; not useful for tuning anything (these aren't user-controllable knobs).

**Visible occasionally in the algorithm's "reason" text**: notes like `ML risk scale 65%: SMB 0.45 → 0.29`, or `pre-UAM uncertainty hold: gentler tiers suppressed`, or `Fast-carb conditions met but delta 12.4 > 10 override`. These appear when the brakes or the hold actually fire.

**New `boostTier = "NONE"` entries** during the pre-meal hold — distinct from baseline NONE cycles. When the hold is suppressing the gentler tiers, no SMB is delivered for that cycle, and the tier reads NONE with a hold-active explanation.

**Three new V5 settings** in `Boost V5 (PRE-ALPHA)` — Aggression, Hypo Caution, and Meal-detection Sensitivity. These are knobs for the shadow observer's calibration, not the active algorithm. Most users should leave them at their defaults (all 1.0). Changing them only affects what V5 would have done if it were dosing; it cannot change actual dosing.

**Not visible**: any change to the user's profile settings, basal rates, ISF, CR, or targets. The build doesn't touch profile calibration. Users who have spent time tuning their profile for Boost should find that work is preserved.

---

## Why this is built the way it is

The decision to keep the DynISF formula identical to Boost is deliberate. Users have spent time calibrating against that formula. Replacing it would require all those users to retune. The additions decide *what* the algorithm should do with the dose it has computed — not *how* the dose is computed in the first place.

The decision to run V5 silently rather than asking users to opt into a beta reflects the principle that calibration data should be gathered before active deployment, not during it. V5 will graduate to alpha — actively driving doses for at least one user — only after its score distribution and CONFIRMED threshold have been verified against multi-user data. That data only accumulates if V5 is observing.

The decision to validate everything against five real users before any code shipped reflects the principle that cross-validation numbers are estimates, not guarantees. The five out-of-cohort users came through the transfer test confirming that the ML models generalise as advertised — mean hypo AUC 0.679 against a cross-validation baseline of 0.680, mean meal AUC 0.771 against a baseline of 0.738. Those numbers said: ship it.

---

## What this build does not do

It does not change the user's basal rates, ISF, CR, target, max IOB, or max bolus. It does not change profile switching. It does not change exercise mode, sleep mode, or any of the time-of-day behaviours. It does not introduce new alerts or notifications. It does not change the way carbs are entered or boluses are confirmed.

---

## What to expect after flashing

In the first few hours, very little will look different. Nightscout will start showing the new fields, glucose will continue trending the way it normally does, and the algorithm will continue dosing the way it normally does. If the user happens to be at moderate hypo risk during that window, they may notice a slightly smaller-than-usual SMB and an `ML risk scale 75%` note in the reason text. If they happen to start a climb shortly after an unannounced meal, they may notice a one-or-two-cycle delay before the algorithm starts firing — that's the pre-meal-tier hold engaging and then releasing once the meal-shaped climb confirms.

Over a few days, the cumulative effect is what's worth watching: time-below-70 should be modestly lower, peak-after-meal values should be roughly similar, time-in-range should be modestly higher. None of these effects is dramatic. They were never supposed to be. The algorithm was already doing the right thing most of the time. The additions described here are about the tails — the cycles where Boost would have over-dosed near a hypo, or under-dosed at the start of a real meal, or held back while a genuine spike was beginning.

V5's fields will populate from the first cycle. There will be no visible effect from V5 in dosing terms because V5 doesn't drive anything. Anyone watching it on a dashboard will see the state machine moving between IDLE, OBSERVING, and CONFIRMED, with the score rising and falling alongside real meal events.

The ISF shadow fields will also populate from the first cycle, but `isfShadow_warmup` will start near 0.0 and climb toward 1.0 over five days. During that period the shadow is leaning conservative and the `deltaPct` numbers will be artificially small. After day five they reflect the actual smoothing-vs-instantaneous difference and become the comparison worth looking at.

---

## In summary

Boost decides what to dose. This build adds a probabilistic check, a brake, a pre-meal hold, two small refinements for sustained climbs, a silent observer (V5) that's preparing the ground for the next generation of the algorithm, and a second silent observer (the ISF shadow) that lets the smoothed-vs-instantaneous sensitivity-ratio debate be resolved with the user's own data. The user sees a small number of new dashboard fields and a slightly more cautious response near hypos. They do not see a different algorithm. The dose calculation is the same. The safety logic is the same. The change is in judgement at the margins — the kind of refinement that's hard to feel cycle-by-cycle but adds up across thousands of cycles a week.
