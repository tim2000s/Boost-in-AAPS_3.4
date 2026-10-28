# Per-user anticipation architecture — full spec (2026-07-27)

**Status: Phases 1+2 BUILT (shadow, read-only, doses nothing); Phases 3+4 pending.** Every
component ships shadow-first, is priced per-user on banked data, and crosses to live dosing only
through the two-test bar (absolute TBR gates + relative pricing + a pre-registered within-user
trial). BUILT 2026-07-27 (commit `5ea788a911`, Boost-V7-shadow): `AnticipationHabitModel`,
`AnticipationOnsetStore`, `RetractableArm`, `AnticipationShadow` in `openAPSBoostTwin/`, wired into
the shared `OpenAPSBoostPlugin.runEngine` (covers plain Boost, V5/V6, and V7-shadow — one
instrument, both engines), `StringKey.ApsBoostAnticipHistory`, extractor `anticip=` parser + 14 DB
columns, 11 unit tests green. Now banking; Phase 3 pricing runs once history accrues.

## 0. What this rests on (measured this session)

1. **Background control is solved** (93% TIR / 82% TING, lows flat); the entire remaining deficit
   is post-meal. *(segmented performance)*
2. **The deficit is two disjoint per-user problems needing opposite fixes:** a **post-meal high**
   in high-runners with near-zero post-meal lows (headroom for *more* insulin), and a **post-meal
   exercise low** in tight-runners with no glucose buffer. *(segmented performance)*
3. **The exercise low is a carbohydrate-counterweight failure, not a dose problem** — crashers
   carry *less* insulin; the fix is anticipatory *withdrawal* or carbs, never a smaller meal dose.
   *(post-meal-exercise mechanism)*
4. **There is no efficacy signal in the telemetry** — do not build a detector; lean on the inputs
   we have. *(efficacy-signal probe)*
5. **Exercise timing is per-user predictable** (habit AUC 0.78, +0.11 over cross-user, 45-min
   lead); **meal timing is semi-universal** (cross-user 0.72, per-user wins only with volume).
   *(per-user anticipation)*
6. **Safety comes from retractability, not prediction accuracy** — the back-out shadow's
   retraction fires cleanly; its arming was too eager. *(back-out shadow)*

## 1. Design principles (each traces to a finding)

- **Anticipate the person, not a policy.** The lever is per-user routine, refit from the person's
  own history. (5)
- **Two levers, opposite signs, disjoint populations.** Never a global change. (2)
- **Retractable or nothing.** Every anticipatory action is a temp-basal that auto-unwinds; never
  an SMB. Accuracy reduces false arms; retraction is what makes weak anticipation safe. (6)
- **The loop cannot add glucose**, so for exercise its only pre-emptive lever is *removing
  insulin ahead of time*; for meals, *moving insulin earlier* (not adding net, except where a
  strict-TBR high-runner has proven headroom). (2,3)
- **No in-loop learning.** The per-user model is a robust statistic refit **offline/periodically**
  (nightly, from accumulated history) and applied at inference — the same class as the existing
  auto-config derivation. It never learns-and-doses inside a cycle (hard rule #2).
- **Fizzle-safe by construction.** A wrong arm costs ~nothing: an un-needed reduction → a mild
  self-correcting high; an un-needed addition → backed out on the deadline or a low-trip.

## 2. Architecture (four components)

```
  ┌─ A. Per-user habit predictor ─┐     ┌─ C. Population gate (auto-config) ─┐
  │  p_exercise(45m), p_meal(45m) │     │  eligible? which lever? per-user   │
  │  refit nightly, offline        │     │  derived from own history          │
  └───────────────┬───────────────┘     └──────────────┬─────────────────────┘
                  │  (both feed) ▼                       │
          ┌───────────────── B. Retractable anticipation controller ─────────────────┐
          │  arms ONLY when predictor fires AND population-eligible AND context-gated  │
          │  action = retractable temp-basal (reduce | move-earlier);  never SMB       │
          │  confirm = Twin Ra rise OR BG rise within deadline; back out otherwise     │
          └───────────────────────────────┬───────────────────────────────────────────┘
                                          ▼
                              ┌─ D. Safety envelope ─┐
                              │ absolute TBR floors  │
                              │ bounded, time-limited│
                              │ shadow → trial gate   │
                              └──────────────────────┘
```

## 3. Component A — per-user habit predictor

**Form.** A per-user **onset-hazard table**, not a black box: p(onset within 45 min) as a
function of hour-of-week (168 bins, smoothed), recency (minutes since last onset), and a 24-hour
count. Interpretable, tiny, deterministic given history. Two instances: **exercise** and **meal**.

**Fitting.** Refit **nightly, offline** from the person's own trailing history (~6–8 weeks,
recency-weighted). This is the "robust statistic computed periodically" carve-out — not in-loop
learning. Cold start and thin data fall back to the cross-user prior (below).

**Exercise vs meal, per the evidence (5):**
- **Exercise → pure per-user.** Idiosyncratic timing; cross-user leaves ~0.11 AUC on the table.
  Gate on a minimum event count (the thin-data collapse to 0.37 on 14 events is the cautionary
  case); below it, hold the cross-user prior.
- **Meal → hybrid.** A cross-user meal-time prior (breakfast/lunch/dinner structure is semi-
  universal) blended with per-user adaptation as volume accrues. Weight shifts to per-user with n.

**Output each cycle (shadow telemetry first):** `p_ex45`, `p_meal45`, the active source
(`peruser | prior | blend`), and the fitted-history depth. Extractor parses to
`boost_anticip_*` columns for pricing.

**Non-stationarity.** Nightly refit tracks drift (weekends already carried as features; travel/
seasons tracked by the trailing window). A hard staleness guard freezes the table to the prior if
the last refit is older than N days.

## 4. Component B — retractable anticipation controller

Generalises the existing `AnticipationBackoutShadow` from a single accel-armed state machine to a
two-lever, population-gated one. **Read-only until Phase 4.**

**Two anticipatory actions, both retractable temp-basal, never SMB:**

| Lever | Population | Trigger | Action | Confirm / back-out |
|---|---|---|---|---|
| **Exercise pre-reduce** | tight-runner (see C) | `p_ex45 ≥ θ_ex` | reduce basal (down to zero-temp) for a bounded window *ahead* of the predicted bout | **Confirm** = activity appears (steps/HR) → hold the reduction; **back out** (restore basal) on deadline-without-activity |
| **Meal move-earlier** | high-runner, strict-TBR (see C) | `p_meal45 ≥ θ_meal` **and** post-meal context | small retractable temp-basal *ahead* of the usual confirm, **netted against the eventual commit-shot** (as the live primer already does) | **Confirm** = Twin Ra rise OR BG rise within deadline → hand to normal meal handling; **back out** on deadline-without-rise OR early low-trip (BG or Twin lo30 heading low) |

**Why these directions.** For exercise, the loop cannot add glucose, so the only pre-emptive
lever is removing exogenous insulin *before* the bout so less insulin is acting when the
insulin-independent drain lands (3). For meals, the high-runners have measured headroom (2), so
moving insulin earlier attacks the post-meal high without adding net dose — the exception where a
strict-TBR high-runner may add is gated hard in C.

**Confirmation crux** is already validated in shadow (E08: confirm AUC 0.83–0.87; false-back-out
~11% benign). Reuse it verbatim.

## 5. Component C — per-user population gate (auto-config)

`BoostV5AutoConfig` derives, from each person's own history, which lever (if any) they are
eligible for. Both default OFF for everyone; eligibility is per-user and must be re-earned.

- **Exercise-pre-reduce eligibility** (safe-signed, insulin-*removing* → lower bar): tight control
  **and** a measured post-meal-exercise low burden above baseline (the D/E/C signature), **and** a
  per-user exercise predictor above a usefulness floor (AUC / event-count). Example holders: the
  tight-runners.
- **Meal-move-earlier eligibility** (insulin-*adding-in-time* → strict bar): post-meal TAR high
  **and** post-meal TBR ≈ 0 (the A/F signature — proven headroom), **and** the strict TBR cut that
  already gates insulin-adding switches. Never enabled for a user with any meaningful post-meal
  low burden (this excludes, e.g., the high-runner who *also* runs post-meal lows).

These are disjoint by construction (2): the more-insulin users are not the exercise-protection
users. A user can hold zero, one — never both.

## 6. Component D — safety envelope

- **Absolute TBR kill-switches unchanged** — consensus absolutes (TBR<70 >4%, <54 >1%), can only
  tighten, key on absolutes never relative doubling. Statistics rank; floors override.
- **Bounded actions.** Reduce: floored at zero-temp, time-limited to the predicted window + margin,
  auto-restored on back-out. Add: small, retractable, netted against the commit-shot, never SMB,
  under the cumulative-SMB and post-rescue guards already live.
- **Post-rescue / rebound interaction.** The anticipation controller must **not arm inside the
  post-rescue window** (the arming bug that over-fired in shadow was exactly rebound context). The
  composed rebound guard and cumulative cap sit downstream and still bind.
- **Fizzle accounting.** Log every would-arm with its outcome so the false-arm cost is priced, not
  assumed.

## 7. Phasing & validation (two-test bar)

| Phase | What | Doses? | Exit criterion |
|---|---|---|---|
| **1** ✅ BUILT | Component A (`AnticipationHabitModel` + `AnticipationOnsetStore`) + telemetry `anticip=`; log `p_ex45`, `p_meal45` + source | No | predictor live-matches the offline AUCs (0.72–0.83 exercise) on banked data |
| **2** ✅ BUILT | Component B arming (`RetractableArm` ×2 in `AnticipationShadow`, context-gated: no-arm-in-post-rescue); log arm / confirm / back-out per lever | No | arming fires in the right population/context; false-arm rate characterised |
| **3** | Price per-user on banked data: does exercise-pre-reduce prevent post-meal-exercise lows at acceptable cost? does meal-move-earlier cut post-meal TAR with **no** low increase? Bootstrap CI, per-user + pooled | No | pre-registered thresholds met, CI excludes null, floors respected |
| **4** | Within-user trial, **one lever at a time**, live, auto-config-gated, kill-switch-bounded | Yes | pre-registered within-user win; absolute TBR gate held |

Exercise-pre-reduce (insulin-removing, safe-signed) is the natural **first** live lever; meal-
move-earlier (insulin-adding-in-time) follows only after its own trial.

## 8. What could go wrong (pre-mortem)

- **Habit drift outruns the nightly refit** → staleness guard freezes to prior; back-out catches
  the mis-fire regardless.
- **Predictor good but operating point too eager** → too many reductions → mild highs. Priced in
  Phase 3; θ tuned per-user; cost is a high, not a low (safe-signed).
- **Meal move-earlier reintroduces the very post-meal low we avoided** → gated to the zero-post-
  meal-TBR signature only, netted against the commit-shot, backed out on low-trip. If any low
  appears in trial, the strict TBR gate pulls it.
- **Two levers interact for a mis-classified user** → disjoint eligibility (C) forbids holding
  both; a user near the boundary holds neither until the signature is unambiguous.

## 9. Confidence

- Architecture direction: **SPECULATIVE** but each principle traces to a **SOLID/PROVISIONAL**
  finding above.
- Exercise predictor usefulness: **PROVISIONAL→SOLID** (0.78 AUC, per-user temporal, all users).
- Meal hybrid: **PROVISIONAL** (volume-dependent).
- The two-lever/disjoint-population claim: **SOLID** (segmentation + mechanism).
- Everything about *live dosing benefit*: **untested** — that is what Phases 3–4 exist to decide.

*Companion evidence: `2026-07-performance-segmentation/`, `2026-07-postmeal-exercise-mechanism/`,
`2026-07-efficacy-signal/`, `2026-07-peruser-anticipation/`, and the existing
`AnticipationBackoutShadow.kt` + accelMeal + primer + rebound guard.*
