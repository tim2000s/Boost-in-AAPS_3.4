# Proposal — Boost **V5** Overview & Widget

Status: **proposal / for review** · Author: design pass 2026-06-26 · Scope: phone overview fragments + home-screen widget (+ optional wear)

---

## 1. Why

The current Boost overview and widget are built around the **tier structure** — an 8-value
`BoostTier` enum (`BOOST_BOLUS … REGULAR_OREF1 … INACTIVE`), each a coloured label, parsed out of the
engine's console text with a regex (`tier\s+(\d+)\s*[-:]\s*(.+)`). That model belongs to the
V3ML / V3MLG3 engines, which chose **one of N discrete dosing tiers** per cycle.

**V5 has no tiers.** V5 is a five-state meal-hypothesis **state machine** with a continuous meal
**score**, an **aggression budget**, a per-state **action multiplier**, and a stack of **safety
brakes**. Displaying "Tier 5 – Percent Scale" for a V5 run is meaningless — there is no such tier.
We need overview + widget views whose central metaphor is *"where is the state machine, how strong
a meal signal does it see, and how hard is it acting (and what's holding it back)?"*

Good news: V5 already publishes everything we need as **structured typed fields on `RT`** (no regex
needed) — see §4.

---

## 2. What V5 actually exposes (the new vocabulary)

All already written each cycle (`OpenAPSBoostV5Plugin.runShadow` → `RT`, `RT.kt:90-96`):

| RT field | Meaning | UI use |
|---|---|---|
| `boostV5_state` | `IDLE \| OBSERVING \| CONFIRMED \| COMMITTED \| RECOVERING` | **primary chip** (replaces tier label) |
| `boostV5_age` | cycles in current state | chip subtitle (e.g. `OBSERVING · 2c`) |
| `boostV5_score` | meal-signal score 0.0–1.0 | **score gauge** w/ threshold ticks |
| `boostV5_actionMult` | per-state action multiplier (0.3 / 1.8 / 1.0 / 0.4 …) | "acting ×1.8" badge |
| `boostV5_budget` | aggression budget (U) | budget stat |
| `boostV5_finalDose` | V5's SMB this cycle (U) — the actual dose when V5 is active | dose stat |
| `boostV5_gateReduction` | compact list of fired brakes (`iobHeadroom:0.85,decel:0.50,HARD:min_guard_bg`) | **brakes row** |

Supporting context (also on `RT`, already used by the tier UI — keep): `dynamicISF`, `tdd`,
`tddRatio`, `deltaAcceleration`, `boostProfileSwitch`, `mlHypoRisk`, `mlMealLikely`, and the
**sleep/HR** block (`sleepState` `AWAKE|PRE_SLEEP|SLEEPING`, learned schedule, `hrBpmAvg5m`).

### State semantics (drives colour + copy)
| State | Meaning | Action mult | Proposed colour |
|---|---|---|---|
| `IDLE` | no meal hypothesis | 1.0 (oref baseline) | blue-grey `#78909C` |
| `OBSERVING` | suspecting a meal, dosing gently | 0.3 | amber `#FFC107` |
| `CONFIRMED` | meal confirmed, peak bite | 1.8 | orange-red `#FF6E40` |
| `COMMITTED` | sustained meal coverage | 1.0 | orange `#FF9800` |
| `RECOVERING` | BG turning, easing off | 0.4 | teal `#26C6DA` |

(Palette is a starting point — tunable. Keeps the existing "hotter = dosing harder" intuition:
grey idle → amber watching → orange/red acting → teal cooling.)

---

## 3. Proposed UI

### 3a. Overview — V5 pill row (replaces the tier panel / profile pill)

Engine-aware: when V5 is the active/selected engine, the tier panel is replaced by a **STATE** pill
plus a **SCORE** gauge; the rest of the stat pills (IOB, DynISF, TDD, activity/sleep, profile%,
temp-target) stay as they are.

```
┌───────────────────────────────────────────── Boost V5 ─────────────────────────────────────────┐
│  ┌─ STATE ─────────┐  ┌─ MEAL SCORE ───────────────┐  ┌─ DOSE ──────┐  ┌─ BUDGET ┐              │
│  │  CONFIRMED  ×1.8│  │ 0 ──────╫────●────╫──── 1   │  │ 0.45 U      │  │ 0.78 U  │              │
│  │  2c · acting    │  │      .44(obs) .55(confirm)  │  │ this cycle  │  │ aggr.   │              │
│  └─────────────────┘  └────────────────────────────┘  └─────────────┘  └─────────┘              │
│  brakes:  ⛔ HARD min_guard_bg     ·  iobHeadroom 0.85  ·  decel 0.50            (tap → detail)  │
│  context: DynISF 28.4 · TDD 41 · IOB 1.9 · ⏾ SLEEPING (hr) · profile 140% · TT —                │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **STATE chip** — coloured by state, shows action multiplier (`×1.8`) and a one-word verb
  (`idle / watching / acting / covering / easing`). Subtitle = `{age}c`.
- **SCORE gauge** — horizontal 0–1 bar with ticks at the live thresholds (enter-observing **0.44**,
  confirm **0.55**, fall-back **0.36**). Instantly shows "how close to confirming".
- **DOSE / BUDGET** — `boostV5_finalDose` and `boostV5_budget`. When V5 is *shadow* (running under
  V4), label DOSE as "would-dose" so it's clearly not delivered.
- **brakes row** — chips parsed from `boostV5_gateReduction`. HARD gate shown as a red ⛔ chip
  (binary disable); soft brakes as muted chips with their factor. "none" → hide the row.
- **detail sheet** (tap, like today's reason view) — full score-component breakdown, budget
  breakdown (ML hypo-risk scale, post-exercise scale), every gate factor, and the raw reason.

### 3b. Widget — V5 home-screen widget

Same frame as today (BG bobble left, 2×3 data grid right); swap the tier label and re-purpose two
grid cells for V5:

```
┌──────────────────────────────┐
│ ●BG  5.4→     STATE: CONFIRMED│   ← state chip replaces "Tier N – …", coloured by state
│  -3m          ████████░░  ×1.8│   ← mini score bar + action mult
│ ───────────────────────────── │
│ DynISF 28  │ TDD 41 │ dose .45│   ← dose cell = boostV5_finalDose
│ IOB 1.9    │ ⏾ SLEEP│ prof140%│   ← sleep glyph from sleepState
└──────────────────────────────┘
```

Widget keeps the existing opacity / black-bg config. State colour drives the chip; mini score bar
is a tiny `RemoteViews` progress bar (or a drawn bitmap, matching the BG bobble approach).

### 3c. Wear (optional, Phase 4)

Tier was never sent to the watch — only `variableSens` + `tirWeights` ride `EventData.Status`. To
put V5 on the wrist, add `boostV5State: String` (+ optional `boostV5Score: String`) to
`EventData.Status`, populate in `DataHandlerMobile`, and add a **V5 state complication** (SHORT_TEXT:
title `V5`, text `CONFIRM`/`OBSERVE`/… colour-mapped) hostable by the WFF faces we already ship.

---

## 4. Data plumbing — read structured RT, drop the regex

`BoostOverviewHelper` currently regex-parses the tier out of `reason`/`scriptDebug`. For V5 we read
the typed fields directly — more robust, no string fragility.

1. **New status model** `BoostV5Status` (state enum + colour, score, age, actionMult, budget,
   finalDose, `List<Brake>`, isShadow) alongside the existing `BoostStatus`. Add
   `enum class BoostV5State(label, verb, colorHex)`.
2. **Source** — `computeV5Status()` reads `rt.boostV5_state … boostV5_gateReduction` from the same
   `RT` the helper already pulls (`loop.lastRun?.request` → fallback
   `processedDeviceStatusData.openAPSData.suggested`). Parse `boostV5_gateReduction` into chips
   (the *only* small parse — a fixed `k:v` list, not free text).
3. **Engine-aware switch** — `isV5 = activeApsIsBoostV5() || rt.boostV5_state != null`. When `isV5`,
   fragments/widget render the V5 views; otherwise the existing tier views. **Both engines keep
   working** — nothing is deleted, the old tier UI stays for V3ML/V3MLG3.
   - *Recommended default:* key off the **selected APS plugin** (`OpenAPSBoostV5Plugin` active), so a
     pure-shadow V5-under-V4 run still shows the tier UI (V4 is delivering), with V5 in the detail
     sheet. (Open decision D1 below.)
4. Reuse the 30 s cache (`CACHE_TTL_MS`).

No changes to the engine are required for Phases 1–3 — all fields already exist on `RT`.

---

## 5. Phasing & effort

| Phase | Work | Risk |
|---|---|---|
| **1 — model** | `BoostV5State` enum + colours, `BoostV5Status`, `computeV5Status()` in `BoostOverviewHelper`, `gateReduction` parser, engine-aware switch | low (pure read, unit-testable) |
| **2 — overview** | State chip + score gauge + dose/budget + brakes row in `BoostOverviewV2Fragment` (V2 first — it's the dark-pill layout you use); detail sheet; layout strings | low/med (UI only) |
| **3 — widget** | State chip + mini score bar + dose cell in `BoostWidget` / `boost_widget_layout.xml` | low/med |
| **4 — wear (opt)** | `EventData.Status` + `DataHandlerMobile` + new complication | med (cross-module, version-compat field — additive/backward-compatible) |
| **5 — cleanup (opt)** | Once V5 is the only engine you run, retire the tier code paths | deferred |

All display-only — **zero dosing impact**, nothing in the dose path changes.

---

## 6. Open decisions (need a steer)

- **D1 — Replace vs coexist.** Recommended: *engine-aware coexist* (auto-switch on active engine; tier
  UI stays for the old engines). Alternative: hard-replace the tier UI with V5 everywhere and drop
  tier rendering now. *Recommend coexist* — non-destructive, and you still have V3MLG3 selectable.
- **D2 — V1 fragment.** Update only `BoostOverviewV2Fragment` (the one you run), or both V1 + V2?
  *Recommend V2 only* now; V1 later if needed.
- **D3 — Wear.** In scope now (Phase 4) or defer? *Recommend defer* until the phone views settle.
- **D4 — Shadow labelling.** When V5 runs as shadow under V4, show the V5 pills as a secondary
  "shadow" strip, or only swap to V5 pills when V5 is the active doser? *Recommend the latter* (active
  only; shadow stays in the detail sheet) to avoid implying delivery that didn't happen.
- **D5 — Colours/copy.** Sign off the 5-state palette + verbs in §2, or iterate.

---

## 7. Key files (touch list)

- `plugins/main/.../overview/boost/BoostOverviewHelper.kt` — new `BoostV5State`, `BoostV5Status`,
  `computeV5Status()`, engine switch (keep `BoostTier` for legacy).
- `plugins/main/.../overview/boost/BoostOverviewV2Fragment.kt` (+ `boost_overview_v2_fragment.xml`).
- `plugins/main/.../overview/boost/BoostOverviewFragment.kt` (+ `boost_overview_fragment.xml`) — D2.
- `plugins/main/.../overview/boost/widget/BoostWidget.kt` (+ `boost_widget_layout.xml`).
- `core/interfaces/.../aps/RT.kt` — **no change** (fields already present).
- *(Phase 4)* `core/interfaces/.../rx/weardata/EventData.kt`,
  `plugins/sync/.../wear/wearintegration/DataHandlerMobile.kt`, new wear complication.
</content>
