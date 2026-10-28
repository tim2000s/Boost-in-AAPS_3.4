# Post-confirm acceleration — is it a signal to issue a *second* confirm?

**Date:** 2026-07-20 · **Question (Tim):** after a CONFIRMED commit-shot, if deltas are
still accelerating, is that a signal to issue a second confirm (dose more)?

**Verdict:** **No.** Continued acceleration is a real *prediction* signal (bigger peak,
SOLID) but does **not** clear the bar for more insulin (no measured low-rate headroom;
already ~1-in-5 crash at the current dose). The engine's existing behaviour — hold in
COMMITTED at 1.0× rather than fire a second shot — is the correct shape.

---

## 1. Mechanical — what the confirm engine actually does (`confirm_scenario.kt`)

Drives the **real** `MealHypothesis` state machine (compiled from
`plugins/aps/.../openAPSBoostV5/MealHypothesis.kt`, no AAPS deps) over a synthetic meal
that accelerates straight through the confirm (delta +12→+18, accl +16→+22):

```
15 | 128 | +10.0 | +14.0 | 0.66 | 175 | -> CONFIRMED  (cis=true)  <-- CONFIRM #1 FIRES
20 | 140 | +12.0 | +16.0 | 0.68 | 195 | -> COMMITTED  (cis=true)
25 | 154 | +14.0 | +18.0 | 0.70 | 215 | -> COMMITTED
30 | 170 | +16.0 | +20.0 | 0.72 | 235 | -> COMMITTED
35 | 188 | +18.0 | +22.0 | 0.74 | 255 | -> COMMITTED
TOTAL confirm-shots fired: 1
```

CONFIRMED fires **once**; continued acceleration keeps the state in COMMITTED at the
sustained 1.0× multiplier. A second commit-shot is hard-blocked by `committedInSession`
(**Fix 6**, 2026-05-26) — which exists *because* the earlier multi-confirm behaviour is
exactly this: on 2026-05-25 V5 fired CONFIRMED 4× in 20 min → 8U, and 1.5U alone had
already crashed BG 192→48. A milder re-escalation already exists (**Fix 7**): a meal that
decelerates then genuinely re-accelerates resumes COMMITTED (1.0×), never a fresh 1.8× shot.

## 2. Empirical — is the signal real, and is there headroom? (`postconfirm_accel.py`)

Clean prediction test (identification-safe: keep observed BG, ask what follows). Anchor =
each CONFIRMED cycle; split by mean `delta_acceleration` over +5..+15 min
(STILL-ACCEL > +5, DECEL < 0); forward outcomes = peak BG (+90 min) and low/severe-low in
the +30..+180 min crash window. 3,879 anchors, 9 users, May–Jul; cluster-bootstrap by user.

| outcome | STILL-ACCEL | DECEL | Δ (A−D), 95% CI | verdict |
|---|---|---|---|---|
| peak BG (mg/dL) | 195.6 | 173.0 | **+23.0 [+15.8, +29.5]** | distinguishable |
| low <70 rate | 19.3% | 20.4% | −1.6% [−9.2, +6.5] | unproven |
| severe <54 rate | 6.6% | 8.1% | −1.6% [−5.3, +2.8] | unproven |

- **SOLID:** post-confirm continued acceleration predicts a **~23 mg/dL higher peak** —
  a genuine "bigger excursion than one commit-shot served" signal.
- **No headroom for more insulin:** the still-accel group already crashes ~19% (severe
  ~6.6%) *at the current dose*, and that low-rate is **not lower** than the decel group
  (Δ overlaps 0). The high peak co-occurs with a 1-in-5 crash — the fast-carb overshoot
  shape ([[fastcarb-confirm-crash]]). Adding a second shot front-loads insulin into an
  already-crashing population.

### Two caveats, both cutting *against* a second confirm
- **The comparison flatters "accel".** The DECEL group's higher low-rate is partly reverse
  causation — some decelerated *because* BG was already turning down toward a low. Accel's
  apparent safety edge is therefore overstated.
- **Per-user heterogeneous, small-n.** Users C and F crash *more* when still accelerating
  (C 34% vs 22%, severe 19% vs 10%; F 28% vs 15%). A general lever would harm them.

## 3. Where a lever could live (SPECULATIVE — not built)

The only defensible version is a **bounded, sustained (not bolus), per-user auto-config-gated**
escalation for the specific users whose accel-group does **not** crash more — the same
auto-config-managed pattern the aggressive-early-confirm lever uses. This is SPECULATIVE and
would need a within-user trial before it doses anything. It is **not** a general second confirm.

## Reproduce
```
# empirical (needs local oref DB refreshed to t=now)
python3 postconfirm_accel.py
# mechanical scenario through the real engine
kotlinc <repo>/plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSBoostV5/MealHypothesis.kt \
        confirm_scenario.kt -include-runtime -d scenario.jar
kotlin -classpath scenario.jar app.aaps.plugins.aps.openAPSBoostV5.Confirm_scenarioKt
```
