# Boost V6 — experimental AndroidAPS fork

[![Support Server](https://img.shields.io/discord/629952586895851530.svg?label=Discord&logo=Discord&colorB=7289da&style=for-the-badge)](https://discord.gg/aUzQ8q5zQd)

> ⚠️ Experimental. Not medical advice. Not a released or approved product.
> This is a developer's research fork of AndroidAPS that changes the automated insulin-dosing
> decision. Do not run it on a pump unless you fully understand the code, accept the risk, and can
> self-manage the consequences. You are the safety system.

## What Boost V6 is

Boost keeps the entire AndroidAPS engine — basal, dynamic ISF, glucose predictions and every
safety gate — and changes only one thing: the super-micro-bolus (SMB) decision. Stock
AndroidAPS sizes one isolated micro-bolus each cycle, from scratch. Boost V6 instead carries a
*meal hypothesis* across cycles and scales its dosing to how confident it is that a meal is under
way. Nothing else about how AndroidAPS runs your pump is touched.

The result is a system that holds back before a meal is proven, then catches up firmly once it is —
and that you tune with just three dials (far fewer than before), most of which you never touch,
because Boost sets them from your own history on day one.

> *Naming:* the plugin is labelled "Boost V6", but its code and its settings keys still carry the
> earlier "V5" name (`ApsBoostV5…`) from its lineage — V1 → V2 → V3 → v4.4 → v4.4.2 → V6. If you
> read the source, "V5" and "V6" refer to the same current engine.

## How it works — in one glance

A meal-hypothesis state machine drives the SMB:

```
IDLE → OBSERVING → CONFIRMED → COMMITTED → RECOVERING → IDLE
```

It observes lightly while a rise builds, commits a firm catch-up shot once a meal is confirmed,
holds through the meal, then deliberately winds down as insulin takes hold. A layer of safety guards
and personal context (heart rate, sleep, activity) sits around it, and every stock AndroidAPS gate
still runs underneath.

→ Full detail: [How Boost V6 works](docs/v6-how-it-works.md) (the dosing core, the state machine,
the July-2026 safety guards, and the learners).

## Getting started

Boost V6 is the default APS engine in this fork, and you go straight to it — there is no need to
run an older engine first. On its first active cycle it seeds its three dials and its dose caps from
your own recent dosing history (the last 14 days), so it starts where your prior control left off
rather than on a stranger's numbers. That history is read from the AndroidAPS database, and it is
already there if you upgraded in place, restored your AndroidAPS database, or have
Nightscout sync (NSClient) enabled — which backfills up to ~100 days of your treatments and CGM
into the database on first load. It draws from whatever you were running before — standard
AndroidAPS/oref or an earlier Boost — because it only reads dosing history and glucose, not the
engine that produced them.

1. **Install the build.** On a fresh setup Boost V6 is already selected as the APS engine; on an
   in-place upgrade your existing selection is kept, so switch the APS plugin to "Boost V6" if you
   want it.
2. **Make sure your history is present** before you rely on the auto-tuning — enable Nightscout sync,
   or restore your AndroidAPS database, so the last two weeks of dosing are in the app. With no
   history at all, Boost waits and runs on conservative factory defaults until enough data
   accumulates, tuning itself once it has.
3. **It tunes itself and tells you what it set.** You should rarely need to change anything; the three
   dials below are the only ones you would normally touch.

Prefer to watch before you switch? You still can. Selecting the "Boost" plugin (instead of
"Boost V6") runs the same engine with the V6 layer in shadow — it logs what it *would* dose to
Nightscout without driving your pump — and the
[Analyser](https://tim2000s.github.io/Boost-in-AAPS_3.4/boost_analyser.html) compares V1 vs V6 on
your own data. That is optional now, not a required warm-up.

| APS plugin you select | What drives your pump |
|---|---|
| **"Boost V6"** *(default)* | active — the state machine drives the SMB |
| **"Boost"** | the same engine with the V6 override in shadow — logs what it *would* do, does not dose |
| (any other engine) | unchanged — Boost not involved |

### Building it in your browser

If you build the app with GitHub Actions in your own fork (the AndroidAPS browser build), run the
Branch CI workflow, with "Use workflow from" set to the branch you want: `dev` for this line
(`master` is the other). Do not use the AAPS CI workflow. It fetches a release tag from the
upstream nightscout/AndroidAPS repository and builds that, so the app it produces is standard
AndroidAPS without Boost.

> ⚠️ Going active means an experimental algorithm is dosing your pump. You are the safety system —
> watch it, understand it, and keep your own limits (max-IOB, max-bolus) sensible.

## The three levers

These are the only dials you would normally touch — and auto-config already sets each one from your
own dosing history, so most people leave them alone. Each scales *aggressiveness*; none can bypass
a safety limit.

| Setting (as named in the app) | Where | Range (default) | What it is | Turn it up → | Turn it down → |
|---|---|---|---|---|---|
| **Aggression** | Boost V6 | 0.7–1.6 (1.0) | How firm the one meal catch-up shot is (it scales the CONFIRMED commit only — routine holds are bounded by the caps, not this). | a bigger catch-up shot on confirmed meals — for people who peak high | a gentler meal response |
| **Hypo Caution** | Boost V6 | 1.0–2.0 (1.0) | How hard Boost backs off when its hypo-risk model is worried (it does nothing while risk is low). | more insulin trimmed on elevated risk = more hypo-defensive | 1.0 is the floor = least caution |
| **Meal-detection Sensitivity** | Boost V6 → Advanced Settings | 0.8–1.2 (1.0) | A single overall-strength dial for the whole engine — one number that scales *all* of Boost's dosing up or down. **The name is misleading in two ways:** it is not your insulin sensitivity / ISF (that lives in your profile), and despite "meal-detection" it does not change how meals are detected — it scales the per-cycle insulin (aggression) budget. Reach for it when Boost feels uniformly too strong or too weak for you. | firmer everywhere — if Boost runs too weak for you | gentler everywhere — if Boost runs too strong for you |

The **Where** column gives the exact path in the app, and the names above are the exact labels you
will see on those screens — so you can match documentation to settings without guessing.

**How to use them:** start from the auto-config values, change one at a time, and check the
caps and Max IOB first — if a cap or the IOB clamp is what's binding, more Aggression changes
nothing. The [Tuning Guide](https://tim2000s.github.io/Boost-in-AAPS_3.4/boost_tuning_guide.html)
shows each dial on a conservative→aggressive spectrum with worked scenarios.

### Two dose caps you will see referenced

These are not dials you tune day to day, but they are the two limits most often hit, so it helps to
know what they are when a dose looks smaller than you expected.

| Setting (as named in the app) | Where | Range (default) | What it does |
|---|---|---|---|
| **Max allowed bolus [U]** | Preferences → Treatments safety | your own limit | The largest single bolus AndroidAPS will deliver, manual or automated, and the value to adjust if Boost's doses are being held down by a bolus limit. The Boost Bolus Cap in the base engine's settings no longer applies when Boost V6 is the engine. Boost's largest automated dose, the catch-up shot when a meal is confirmed, is limited by the V6 CONFIRMED dose cap (Boost V6 → Advanced Settings), which auto-config sets from your own bolus history; raising Max allowed bolus above that cap does not make Boost's automated doses any larger. |
| **Max minutes of basal to limit SMB to for UAM** | Preferences → SMB settings | 15–120 min (15); set 20 | Sets the ceiling on a single microbolus as a number of minutes of your own basal: the limit is your current basal rate times these minutes, divided by 60. At a basal of 0.6 U/h, 20 minutes is a ceiling of 0.2 U. Boost V6 sizes meal doses itself, so this limit governs the microboluses V6 does not size: those given overnight, under a high temporary target or while asleep, when Boost stands aside for plain oref1. Set it to 20 and no higher. At 120 minutes and a basal of 1.0 U/h each of those microboluses can be 2 U, and repeated through a rise they have stacked to more than 10 U of insulin on board before a low. |

The companion setting **Max Minutes of basal to limit SMB to**, on the same screen with a default of
15 minutes, does the same job when insulin on board has fallen below -0.2 U, which happens after a
long low temporary basal. Leave it at 15.

The cap is a size and not a rate: it limits any one bolus and says nothing about how often that
bolus may repeat. Raising it raises every dose the cap was holding down, so change it in small steps
and watch what follows.

Everything else — the cumulative cap, fast-carb confirm, the opt-in aggression levers, DynISF,
activity — is [advanced and set for you on install](docs/v6-advanced-settings.md). You
should rarely need to open that page except to understand a value auto-config chose.

## Exercise, activity and recovery

Boost adjusts for activity only while Boost itself is active, which means outside night mode. It
reads steps from the phone or a watch and, if you turn on heart-rate integration (Wear OS or
Garmin), heart rate as well. Each cycle it places you in one activity state and changes your
profile percentage and target to suit. A temporary target you set yourself always takes precedence
over the target changes below.

| State | How it is detected | What Boost does |
|---|---|---|
| Active | more than 420 steps in 5 min, 800 in 15, 1,200 in 30 or 1,800 in 60 | profile to 80% (Activity percentage), target 150 mg/dL (8.3 mmol/L) |
| Vigorous aerobic | steps as above, at least 300 in the last 15 min, and heart rate zone 3 or higher | profile to 70% (Activity percentage less 10, never below 50%), target 150 mg/dL |
| Resistance, or raised heart rate with few steps | heart rate zone 3 or 4 with fewer than 100 steps in 15 min | no profile reduction, target 160 mg/dL (8.9 mmol/L) |
| Stress (opt-in) | heart rate zone 2 or 3 with fewer than 30 steps in 15 min | target 160 mg/dL |
| Inactive | fewer than 500 steps in the last hour, awake, outside the night window | profile to 130% (Inactivity percentage), which adds insulin |
| No step data | the step feed has gone quiet | nothing changes; a dark feed is not read as inactivity |

The inactive row is the only one that adds insulin. With heart-rate integration on, heart rate in
zone 2 or above blocks it: cycling, rowing or weights produce few steps, and without that check an
effort could read as sitting still. At zone 2 only the raise is withheld; the resistance target
starts at zone 3. Without heart-rate integration nothing can block it, so a long ride reads as
inactivity. For a planned ride, set a high temporary target: with Allow Boost with high temp target
off, the default, Boost stands aside for the length of the target, including the inactivity raise.

Heart rate is turned into a zone by the Karvonen method, which measures effort as a share of your
heart-rate reserve, the gap between your resting and maximum heart rates. Boost averages the last 15
minutes of heart rate, subtracts your resting rate and divides by the reserve. Below 30% of the
reserve is zone 1, 30 to 40% zone 2, 40 to 60% zone 3, 60 to 80% zone 4 and above 80% zone 5. The
maximum defaults to 180 beats per minute and is a setting. The resting rate starts at the setting's
60 and, once seven days of heart rate have been banked, is replaced by a learned daytime baseline:
the median of each day's 10th-percentile waking heart rate. A trace that repeats one value is read as
a stalled watch, not a heart rate. Without heart-rate integration only the step rows apply, and
every bout of exercise counts as Active.

V6 treats exercise as a reason for caution when it decides whether a meal is under way. While any
exercise state is active the fast-carb confirm and the early primer are both held off, the meal
score loses its small "not exercising" term, and the anticipatory pre-meal target is suppressed.

Post-exercise recovery is off by default and is switched on under Post-exercise recovery in the
advanced settings. When it is on, a bout of exercise lasting at least 10 minutes opens a recovery
window when it ends. For that window Boost sets an Activity temporary target of 144 mg/dL (8.0
mmol/L) unless you already have one running, multiplies its bolus cap and scale by 0.5, and halves
V6's per-cycle insulin budget. The type of exercise adjusts the defaults:

| Exercise type, as last classified before the bout ended | Window | Target | Bolus cap and scale |
|---|---|---|---|
| Vigorous aerobic | 2.5 h | 144 mg/dL | x 0.4 |
| Resistance | 3 h | 154 mg/dL (8.6 mmol/L) | x 0.6 |
| Anything else, including light and moderate aerobic and steps only | 2 h | 144 mg/dL | x 0.5 |

If glucose rebounds after a low during the window (a low below 100 mg/dL, and glucose now 20
mg/dL above it), Boost cancels the recovery target so the loop can respond to the rise. In the
programme's own data the extra hypoglycaemia risk after exercise was modest, about 1.2 times the
background rate, and roughly flat over the five hours measured, so the 2 hour default is a
reasonable starting point rather than a measured optimum.

## The learned models

Every dosing decision in Boost comes from fixed rules and arithmetic, apart from two small
gradient-boosted tree models (LightGBM) that the engine consults each cycle. Both were trained
offline on about three million decision cycles from other people's Nightscout records, with
participants held out during validation, and both ship inside the app as fixed trees. Nothing is
trained on your phone and neither model changes as you use it.

| | Hypo risk | Meal likelihood |
|---|---|---|
| Predicts | glucose below 70 mg/dL (3.9 mmol/L) for at least 15 min within 90 min | a rise of at least 50 mg/dL (2.8 mmol/L) within 90 min |
| Size | 100 trees, 53 inputs | 50 trees, 8 inputs |
| Training | 32 participants | 28 participants |
| Accuracy, participants held out | AUC 0.83 | AUC 0.74 |
| Accuracy in the field | AUC 0.66 (0.61 to 0.70) | AUC 0.72 (0.68 to 0.76) |
| Direction | can only remove insulin | can add insulin |

The hypo-risk model is a brake. Below a score of 0.30 it does nothing. Above that it shrinks V6's
per-cycle insulin budget, by at most half at the default Hypo Caution and by up to three quarters
at its maximum, and in the V1 engine it scales the microbolus down and blocks the four aggressive
tiers above 0.60. The meal-likelihood model works the other way: it contributes a fifth of V6's
meal score, which decides when a meal is confirmed and the larger doses begin; above 0.50 it
releases V1's pre-meal hold; and above 0.30 it keeps the sleep detector from classifying you as
asleep. The caps, Max IOB and the state machine bound what it can cause, not the model.

If either model cannot be loaded, the engine carries on without it: no hypo damping, and the meal
score's weight spread across its other terms. No setting turns them off. The hypo model's thresholds
were set against the model it replaced in June 2026 and have not been re-set since. The full account,
including what is known about their field behaviour and what cannot be reproduced, is in
[the methods report](backtesting/reports/2026-09_boost_lgbm_methods.md).

Everything else that learns from your data is ordinary statistics rather than a trained model:
auto-config's settings, the learned bedtime and wake time, and the resting and daytime heart rates.
The digital-twin forecast and the anticipation model run in shadow, logging what they would do and
delivering nothing.

## Interactive tools

Three self-contained HTML tools — no install, no data leaves your machine. A good order for a
newcomer is Tuning Guide → Simulator → Analyser:

- **[▶ Tuning Guide](https://tim2000s.github.io/Boost-in-AAPS_3.4/boost_tuning_guide.html)**
  ([source](boost_tuning_guide.html)) — *learn what each setting does.* Every knob on a
  conservative→aggressive spectrum, with real-world tuning scenarios, for both V1 and V6.
- **[▶ Simulator](https://tim2000s.github.io/Boost-in-AAPS_3.4/boost_simulator.html)**
  ([source](boost_simulator.html)) — *play with the dosing maths.* Set BG, trend, IOB, TDD and the
  settings (or pull a snapshot from Nightscout) and watch the ISF and SMB recompute, live, for both
  the V1 tier ladder and the V6 state machine.
- **[▶ Analyser](https://tim2000s.github.io/Boost-in-AAPS_3.4/boost_analyser.html)**
  ([source](boost_analyser.html)) — *V1 vs V6 on your own data.* Enter your Nightscout URL + a
  read token and it reads the shadow telemetry every Boost build logs, for a real paired comparison.
  Runs entirely in your browser; the token goes only to your Nightscout.

> These tools validate decisions (what dose, which state, why) — not glucose outcomes. They model
> the algorithm, not a body.

## Learn more

- **[How Boost V6 works](docs/v6-how-it-works.md)** — the dosing core, state machine, safety guards, learners.
- **[Advanced settings](docs/v6-advanced-settings.md)** — everything auto-config sets on install, and how.
- **[Heart rate, steps & night mode](docs/v6-heart-rate-and-sleep.md)** — sleep detection and overnight dosing.
- **[Safety, "no training" & validation](docs/v6-safety-and-validation.md)** — why changing a live dosing algorithm is defensible.
- **[Backtesting method & shadow validation](backtesting/README.md)** — the data-analysis toolkit.
- **[Legacy V1 / V2 / v4.x settings](docs/boost-v1-settings.md)** — the earlier plugins' full reference.

---

*Boost is a research fork and an experimental dosing algorithm. Read the code, understand the
risk, and keep your own safety limits sensible. Shadow mode (the "Boost" plugin) is there if you want
to watch before you switch.*
