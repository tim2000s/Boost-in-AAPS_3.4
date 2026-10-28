# RECOVERING Floor-Exemption + Pre-Sleep Confirm Damper — 2026-07-07

Scripts: `backtesting/scripts/2026-07-recovering-exemption/` (`bt1_recovering_exemption.py`,
`bt2_presleep_damper.py`; CSV in `out/`). Data: TimescaleDB `oref`, refreshed to 2026-07-07T21:18
(backfill since 07-07; only oref-pipeline site U018 failed — no boost cohort impact). Dedup: last row
per (user, 5-min bucket). Local ≈ UTC+1 (BST). Both feed the 07-10 decisions.

---

## BACKTEST 1 — RECOVERING v1-bound exemption for the composed floor (ADDS insulin)

Candidate: let ONLY the floor bypass the non-meal v1-bound in RECOVERING, gated on the floor's existing
conditions PLUS **delta≥0**: `RECOVERING ∧ BG>160 ∧ eventualBG>target+20 ∧ awake ∧ !postRescue ∧ budget>0
∧ delta5≥0`. Added dose = `min(budget×F, committedCap) − current_delivered` (current = min(fd, v1_units) = 0
when v1_units=0). Capped-era cohort; 521 gate cycles.

### Test A (absolute) at F=0.25 — the gate

| user | cyc | added U/day | pre-<70 U | pre-<54 U | ΔTBR<70 pp | ΔTBR<54 pp | base 70/54 | **Test A** |
|---|---|---|---|---|---|---|---|---|
| tim | 96 | 0.173 | 1.88 | 0.43 | 0.06–0.26 | 0.01–0.06 | 3.11/0.51 | **PASS** (worst 3.37/0.57) |
| A | 45 | 0.496 | 0.99 | 0.00 | 0.02–0.08 | 0.00 | 1.11/0.22 | PASS |
| E | 41 | 0.639 | 4.00 | 0.00 | 0.12–0.48 | 0.00 | 1.04/0.00 | PASS |
| F | 105 | 1.110 | 3.33 | 0.00 | 0.08–0.33 | 0.00 | 2.99/0.35 | PASS |
| H | 12 | 0.131 | 0.00 | 0.00 | 0.00 | 0.00 | 1.35/0.28 | PASS |
| B | 117 | 1.729 | 3.07 | 0.64 | 0.05–0.20 | 0.01–0.04 | **3.83**/1.01 | **FAIL** (base>3.5) |
| C | 40 | 0.420 | 1.63 | 1.00 | 0.05–0.19 | 0.03–0.12 | **3.82**/0.60 | **FAIL** (base>3.5) |
| D | 27 | 0.225 | 0.04 | 0.00 | 0.00 | 0.00 | **10.14**/1.81 | **FAIL** (base>>gate) |

B/C/D fail on **baseline** — their 14d TBR<70 already exceeds the 3.5% gate, so they take no additive lever
(identical to the floor-activation gate; removal/neutral only). Sensitivity F=0.15→0.35 does not change any
verdict (only magnitudes; full sweep in stdout).

### The delta≥0 gate does NOT separate the exemption from the rejected re-engage population — VERIFIED, and it matters

- Floor-exemption cycles (delta≥0): IOB **11–12% TDD** median.
- Re-engage-rejected cycles (sustained-delta δ>3×3): IOB **11–12% TDD** median — **the same population.**
- The distinction is **dose size only:** floor delivers `budget×0.25` (**median 0.25U**) vs re-engage's
  full COMMITTED `budget×1.0` (**median 0.80U**), ~3× less.

**Honest conclusion:** the exemption is NOT safer than re-engage by virtue of a cleaner population (it is the
same climbing-RECOVERING, ~11%-TDD-IOB cycles that killed re-engage). Its defensibility rests entirely on
(a) the ~3× smaller floor-bounded dose and (b) the per-user absolute-TBR gate. Frame it that way — do not
claim delta≥0 excludes the rejected population.

### Benefit — resolves the Episode-B pathology (tim 07-07 15:14Z, live)

The RECOVERING climb 164→195 that delivered **0.00U today** would receive **+0.77U over 8 cycles** under the
F=0.25 exemption (0.01→0.23U per cycle, tracking budget). It is the small, staged, budget-bounded response
that the v1-bound currently zeroes — exactly the Episode-B fix, without re-engage's full-COMMITTED shot.

### BT1 Verdict
- **GO for tim (the one running the floor) + A, E, F, H** at F=0.25: passes Test A with margin, <54-deepening
  negligible (tim worst-case 0.57% < 0.8%), resolves the Episode-B stall. **Per-user TBR-gated** (activate only
  where trailing-14d TBR<70 < 3.5% ∧ <54 < 0.8%), delta≥0, floor-bounded.
- **HOLD for B, C, D** — baseline TBR<70 ≥ 3.5%; no additive lever until back under with margin.
- **Required framing:** the safety comes from dose-size + TBR gate, NOT from the delta≥0 gate separating it
  from re-engage (it does not). This is a shadow-first change with a per-user activation gate.

---

## BACKTEST 2 — pre-sleep confirm damper (REMOVES insulin)

Candidate (spec): first CONFIRMED of a session, pre-sleep, capped at `min(confirmedCap, base_would×K)`,
remainder staged to COMMITTED holds. Population = V6-ACTIVE confirms (only these drive the pump and carry a
parseable `base would=`); 213 V6-active fresh confirms, 14 pre-sleep(≥22h).

### 1. The specced base_would×1.5 FAILS on the incident it targets — stated plainly

Incident (tim 07-06 22:44Z, from DB reason line): fd **3.0**, **base_would 2.0**, confirmedCap 3.0, peak 219.

| K | base_would×K | cap = min(ccap, ·) | delivered | removed |
|---|---|---|---|---|
| 1.3 | 2.6 | 2.6 | 2.6 | 0.4U |
| **1.5** | **3.0** | **3.0** | **3.0** | **0.0U (no-op)** |
| 2.0 | 4.0 | 3.0 | 3.0 | 0.0U |

The incident's overshoot was V6 delivering 3.0 vs oref's own base_would of 2.0 (+1.0U); base_would×1.5 = 3.0
permits the full shot. **The damper as specced does nothing here.** (Both 2.0 and 3.0 already exceed tim's
ISF-97 correction need of 1.37U for a 219 peak — the excess is upstream of the ×1.5 rule.)

- Where base_would×1.5 *does* bite across the pre-sleep set, it is a **clean fizzle filter**: removes 4.93U
  at **100% fizzle**, 0% real-meal. Good component, wrong tool for the incident.

### 2. What actually catches the incident (absolute cap)

| rule (pre-sleep, ≥22h) | removed U | on fizzles | on real-meals | tim removed | added >180min on real-meals |
|---|---|---|---|---|---|
| abs cap **2.0U** | 5.60 | 71% | 29% | 2.00 | ~92 |
| abs cap 1.5U | 9.45 | 67% | 33% | 3.00 | ~92 |
| ×0.6 scale | 9.44 | 60% | 40% | 2.40 | ~92 |
| cap base_would×1.0 | 7.90 | 81% | 19% | 2.35 | ~92 |

Incident under abs 1.5U → delivers 1.5U (≈ the ISF-need 1.37U); abs 2.0U → delivers 2.0U (removes the V6
amplification, matches oref).

### 3. Gate: clock ≥22:00 beats night-start proximity (tim)

| gate | n confirms | fizzle | <54 | catches incident? |
|---|---|---|---|---|
| **clock ≥22:00 local** | 18 | 61% | 28% | **YES** |
| within 90 min of night start (23:08–00:38 BST) | 12 | 58% | 42% | **NO** (22:44 < 23:08) |

The incident (22:44 BST) falls *before* the 90-min-pre-night window (tim sleeps ~00:38), so night-proximity
misses it entirely. **Clock ≥22:00 is the correct gate** — more inclusive and catches the incident.

### 4. Test A (removal → can only improve TBR)

Under abs-1.5U cap: tim removes 3.0U (**1.5U of it preceded a <54** — removing insulin that deepened lows),
cost = 1 real-meal confirm under-covered (+60 min >180). A −2.1U, B −2.35U (2.0U preceded <54), F −2.0U — all
strictly TBR-improving; cost is time-high on 1–3 real evening meals each (~92 min added >180). No user harmed.

### BT2 Verdict
- **The specced `base_would×1.5` alone FAILS** — a no-op on the incident (a removal lever that under-fires on
  its own target case). Keep it only as a fizzle-filter component.
- **Recommend: pre-sleep (clock ≥22:00) first confirm cap = `min(confirmedCap, base_would×1.5, 2.0U)`, staged
  to holds.** The base_would×1.5 term filters fizzles; the **2.0U absolute term catches the high-ISF
  over-delivery** the ×1.5 misses. Removes ~5–6U cohort at 71% fizzle, delivers oref-equivalent on the
  incident (2.0U vs 3.0), stages the rest to holds (which correctly withheld on the incident as BG peaked and
  turned). Test A: strict improvement, no user harmed.
- If a single knob is preferred, **abs 2.0U pre-sleep cap** is the cleanest one-liner (71% fizzle, matches
  oref on the incident); 1.5U catches more but costs more real-meal coverage.
- Gate: **clock ≥22:00 local**, not night-start proximity.

---

## Caveats
- ΔTBR brackets are decision-level ([0.15,0.6]×ISF-min per pre-low U), no glucose sim — directional; the
  per-user PASS/FAIL turns on baseline distance to 3.5/0.8, which is robust.
- BT1 IOB comparison uses iob/TDD; re-engage-rejected set reconstructed as δ>3×3 consecutive (the sustained
  variant) — the population-overlap finding is the load-bearing one and is unambiguous.
- BT2 base_would parseable only on V6-active override rows (213 confirms); shadow-mode confirms don't reach the
  pump so are correctly excluded. Pre-sleep V6-active n is small (14 with base_would; 18 by clock gate) — the
  incident finding is decisive but cohort sizing is thin; re-measure at +7d.
- "needed-from-peak" uses logged dynISF; tim's high ISF (97–132) is physiology, not artifact — it is why his
  confirm shots overshoot.
- low70/low54 attribute any low within 3–4h regardless of intervening cause; consistent with all prior pricing.
- committedCap eras include tim's 07-07 raise to 1.0 (live-verified). U018 (oref) refresh failure — no boost
  cohort impact. A (Joost) data ends 17:08 today (site quiet); no pre-sleep confirms missed.
