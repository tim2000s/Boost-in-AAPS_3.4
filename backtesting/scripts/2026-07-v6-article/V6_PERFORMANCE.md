# Boost V6 — cohort performance + dosing mechanism (2026-07-19)

Backing analysis for the V6 article. Script: `v6_analysis.py` (DB `oref.boost_decisions`, refreshed
to t=now first). Cohort = 7 V6-active users (`boostv5_active`), 11–24 days each, through 2026-07-19.
Honest by construction — see the split between **descriptive outcomes** and **clean mechanism** below.

## Outcomes over the V6-active era — DESCRIPTIVE, not a causal effect

Median across users (within-subject summary; the cohort is small + self-selected):

| metric | median | IQR |
|---|---|---|
| TIR 70–180 | 84.4% | 81.2–91.6 |
| TING 63–140 | 66.1% | 61.3–73.2 |
| TAR >180 | 13.4% | 4.9–16.4 |
| TBR <70 | 1.8% | 1.2–3.5 |
| TBR <54 | 0.2% | 0.1–0.7 |
| glucose CV | 29.3% | 25.0–34.7 |

Per-user spread is large (TIR 77–99%) and tracks CV almost perfectly — consistent with the frontier
finding that tight-range time is a **variability** problem (~1.3pp TING per 1% CV), not a dose-harder
one. **These are outcomes WHILE on V6, not a measured V6 effect:** no glucose simulator ⇒ no
counterfactual (how these users would have done on the previous Boost generation cannot be
generated); the cohort is small + self-selected; the within-user RCT has not been run.

## V1 → V6 before/after — WITHIN-USER, and it's a WASH (`v6_vs_v1_outcomes.py`)

The same 7 users ran the previous Boost generation (variant `v1`/`v1-silent`, the v4.1.5 lineage) for
2–4 months (≈Mar–Jun) before moving to V6 (Jul). Real measured CGM both eras → a within-user
before/after (far cleaner than cross-user, but NOT a crossover: the eras are different months, so
calendar/sensor/site/physiology confounds are baked in). Aggregate = mean across users (equal weight):

| era | TBR<70 | TIR | TAR | TING | TBR<54 | CV |
|---|---|---|---|---|---|---|
| **V1** | 2.5 | 87.1 | 10.4 | 70.2 | 0.49 | 29.7 |
| **V6** | 2.6 | 86.5 | 10.9 | 68.3 | 0.44 | 29.2 |

**Essentially identical.** Equal-weight has V6 a hair *worse* (TIR −0.6, TING −1.9); volume-pooled
flips it a hair *better* (TIR 84.3→86.0, TING 66.4→67.5) — the two aggregations disagreeing on sign
is the signature of no real effect. Per-user it's mixed (P4/F +8 TIR, P1/E +3; P6/A −6, P5/tim −2;
rest level) — gains and losses cancel. **⇒ Moving V1→V6 did not visibly move outcomes.** A before/
after can't rule out a *small* effect (needs the within-user RCT), but there is no large one, and no
safety cost. This is the honest headline of the article (Figure 1): V6 changed HOW it doses, not (on
this evidence) the outcome — consistent with the frontier finding that outcomes are a variance
problem, which redistributing insulin need not touch.

## Dosing mechanism — CLEAN (same-cycle `boostv5_finaldose` vs `v1_units`)

**Baseline is PREVIOUS BOOST, not oref.** `v1_units` = `sug.units` from `DetermineBasalBoost` — the
V1-generation Boost algorithm (its own UAM Boost tiers T3/T4/T5, committedCap, ML tier-downgrade;
152 Boost-specific refs), NOT stock oref. CLAUDE.md: "V1 is Boost, not oref." So this is what V6
adds *on top of an already-aggressive predecessor*, a demanding baseline — not a gain over passive
oref. There is no stock-oref would-dose stored on the Android build.

Every cycle V6 records the dose the previous Boost generation would have given. Comparing them, same
user/cycle/glucose, needs no counterfactual. V6 **changes the dose on ~1 cycle in 11** (median:
amplify 5.0%, restrain 3.5%, identical 91.4%), net **+11%** insulin/day (one user nets slightly
less — the protective-tightening case). Where it spends that insulin:

- **By glucose band (pooled, U/1000 cyc):** low <90 **+1.5**, in-band 90–140 +9.8, **mild-high
  140–180 +20.5**, high >180 +11.3. → concentrates on the addressable mild-high band; near-absent at lows.
- **By state:** IDLE +4.2, OBSERVING +4.8, **CONFIRMED +181.9** → almost all intervention lands once a
  meal is confirmed (front-loads ~40× harder than any other state).
- **By time of day:** overnight +32.4 vs day +9–11 U/1000 cyc.

## Safety

Dosing +11% more, low exposure stayed inside consensus targets across all 7 users (TBR<70 median
1.8% vs <4%; TBR<54 0.2% vs <1%). The mechanism is visible: extra insulin goes to 140–180, not into
recovering lows.

## Overnight — descriptively strong, but confounded

Overnight (00–06) median TIR 96% / TING 88% vs daytime 81% / 60%, and V6 is most active overnight.
**Not attributable to V6:** overnight is fasting (no meals to mishandle); every loop does better
there. Separating it needs a within-user randomised night (not run).

## What can / can't be claimed

- Mechanism (how V6 differs from the previous Boost generation): **solid** — clean same-cycle comparison.
- Safety (lows held while dosing more): **well-supported** — observed fact of the era.
- Outcome improvement: **not established** — no counterfactual, confounded cross-user comparison.
- Generality: **limited** — 7 self-selected users, hypothesis-generating.

Article (private artifact): rendered from `boost-v6-article.html` (scratchpad; not committed —
carries the same aggregates). Anonymised P1–P7; cross-user figures use within-user ratios / pooled
patterns to avoid mixing insulin concentrations (U100 vs U200).
