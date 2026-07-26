# Relationships register — Boost analysis

A record of the data relationships, dosing levers, mechanisms and models we've examined, with the verdict and the number or reason behind each. The point is to avoid re-testing things that are already settled. It spans the recorded work from April to July 2026. Grouped by outcome (used / discarded / partial), and within that by theme. Predictor→outcome relationships, levers with a verdict, and mechanisms with a root cause are in scope; build/port/tooling records are not.

---

## Found and used

### Dosing timing and sizing
| Relationship / lever | Finding | Evidence | Status |
|---|---|---|---|
| Moving insulin earlier vs adding new insulin | Moving is harm-neutral; new insulin adds ~15 pp to lows | early-dosing audit, 07-03 | Frames "dose earlier, safely" |
| Confirm-gate over-blocking | 26–29% of blocked confirms preceded BG>180 | 07-03 | Fix candidate (live-verify first) |
| Age-gate −1 when score-ready | Harm-neutral, ~1.5 U/day shifted | 07-03 | Score-ready lever |
| OBSERVING raise, restricted cell | Only defensible in BG≥140 ∧ IOB<5% TDD | 07-03 | Blanket raise contraindicated |
| Post-rescue meal-state cap | 27% of removed insulin sat pre-low (worst-priced found) | 07-04 backtest | Shipped: suppress meal-state exemption when recentLow<75 |
| Composed post-rescue rebound guard (scale T7/T8 in-window) | Tier demotion alone doesn't restrain: T7/T8 uncapped by fastCarbScale + delta-weighted ISF inflates insulinReq → 3.55U at BG 97 post-hypo (user-H 2026-07-23 double incident, loop disabled). Graduated scale on FINAL microBolus in-window: 34% [32,37] of removed insulin sat pre-low (new best-priced; LOUO floor 27% dropping D); cost 9% genuine meals at 0.80U median | 07-23 `2026-07-postrescue-rebound-guard/` (103k dosing cycles) | Shipped `51e7663a36` (V7-shadow) + `0eb4a65b39` (experimental); no velocity escape in-window (Fix D argument) |
| committedCap OBSERVING→CONFIRMED gate | ~41% block (tracks the trivial population), defensible | 07-02 | Shipped; STUCK-14% is the watch-item |
| Fast-carb confirm latency | V5 stayed OBSERVING one cycle too long (0.3U vs 1.7U) → late peak/crash | 06-16 | Fast-carb fast-path |
| V5 front-loads before highs | All users dose earlier ahead of highs | 06-15 shadow backtest | V5 design validated (severe-low pullback mixed) |

### Exercise and activity
| Relationship / lever | Finding | Evidence | Status |
|---|---|---|---|
| Recent activity → forward hypo | Leading indicator, per-user (not cross-user) | dose-response 13%→38.5%; steps ~1.5–1.6× baseline up to 3h before a low | Validates exercise protections + Garmin steps ingest |
| Time-of-day + weekday → activity | Exercise is habitual | OOS AUC 0.73–0.85; ~30% of activity in top-3 hours | Basis for anticipation |
| Habit prior vs reactive steps | Prior fires before movement | pre-arms 55% of episodes ~55 min ahead; AUC 0.85; precision 0.63 | Spec written (shadow-log first) |
| Post-exercise recovery tail | Modest, immediate | ~1.2× baseline hazard, flat 0–5h (de-artefacted) | V4's 2h window ~right |

### Overnight and sleep
| Relationship / lever | Finding | Evidence | Status |
|---|---|---|---|
| boostActive ← night-mode gate | Suppresses ~47% of Boost's over-V1 amplifications, all at night, all unannounced | 07-02 backtest | Shipped |
| Overnight vs daytime (Boost vs oref) | Boost's advantage is overnight | +13.3 pp overnight; anti-phase with oref | Protect night mode (causal test pending) |
| Post-breakfast vs oref | oref beats Boost mid-morning | −4 to −7 pp ~09:00–13:00 | Confirm sizing/timing is the daytime lever |
| Late-tail SMB cascade (overnight) | V4.4.2 fired SMBs on the bounce out of a hard streak → nadir 51 / 48 | 05-21, 05-25 incidents | V5 architecture vindicated |
| HR resting baseline | median of per-session p10, ≥7 sessions → Karvonen HRR | robust order statistic | Ships (runtime) |
| Sleep bedtime/wake | circular mean of onset/wake clock-minutes | directional statistic | Ships (runtime) |
| HR daytime baseline warm-up | Populates after ~7 nights (default 70 until then) | 06-27 | Expected behaviour, not a bug |

### Sensitivity and TDD
| Relationship / lever | Finding | Evidence | Status |
|---|---|---|---|
| TDD-anchored EMA sensitivity | ratio = EMA (τ=3h) of tdd_24h/tdd_7d, DB-seeded warmup | 04-30 | Replaced the deviation function; ships |
| Absorption is multi-phase | ~80-min second waves | 06-13 | Soft-ceiling handling |
| Recovering-highs IOB context | The high tail is high-IOB; adding there causes lows | ~19% pre-low at recovering IOB vs ~7% at low IOB | Rationale for the dosing guards |

### Prediction and models
| Relationship / lever | Finding | Evidence | Status |
|---|---|---|---|
| IOB@30min prediction | Trustworthy | MAE 21, night bias ~0, Parkes A+B 98.9% | Usable |
| UAM prediction | Upper bound on unchecked climbs | +20/+48 on climbs | Interpret as a bound |
| Forward high / low predictability | Predictable an hour out | grouped-OOS AUC 0.83 / 0.78 | Foreseeability layer |
| ML models 28-user trained | Meal model transfers to new users; hypo model bimodal | one new user 0.708 ≈ GroupKFold, another 0.628 below LOUO | Per-user calibration for outliers; no retrain |
| mlHypoRisk / mlMealLikely | Pre-trained, applied at inference | — | Ships (runtime) |

### Mechanisms and root causes
| Relationship / mechanism | Finding | Evidence | Status |
|---|---|---|---|
| Phase-3 brake compounding | 0.4 × 0.40 × 0.85 × 0.30 = 4.1% of budget → rounds to 0 for 30 min at BG ~270 | 07-06 forensic, 17/17 cycles reconstructed | Composed brake-floor |
| Brake (composed multipliers) correctness | Directionally right (don't loosen); the "90%" is 13% outcome-proven + 76% correct-by-assumption, on a pooled self-dominated n=135 | 13% saved a low, 76% high-IOB restraint (assumed), ~3% recoverable | Don't loosen; don't quote "90%" |
| Where TIR loss comes from | Highs: sizing/timing (brake #1 but lead over sizing narrow per-user). Lows: activity + rescue (pooled activity 47>rescue 37; per-user rescue 44>activity 36 — ranking pooling-dependent) | residency attribution (cause-shares POOLED; per-user differs) | The lever map |
| 2026-05-14 evening excursion | Unannounced meal on a basal deficit, not insulin stacking | peak IOB only +4.62 | Canonical V6 sequence-aware use case |

### Per-user configuration
| Relationship / lever | Finding | Evidence | Status |
|---|---|---|---|
| Auto-config migration | A/C/F rescued, D tightened protectively | 7-user cohort, 07-06 | Shipped with 5 amendments |
| Per-user caps at derivation | Cap-clipped users need higher caps | migration cohort + the user-H case | Used via auto-config |
| hypoCaution by TBR (static) | Well-targeted for the hypo-prone, off for the well-controlled | removed-insulin pre-low share 28–32% (hypo-prone) vs 1–6% (well-controlled) | Already in auto-config; validated |
| Auto-config policy | Never auto-raise aggression; TBR-driven hypoCaution | four online-tuning experiments re-derived it | Ships |
| V7 residual substrate | Regime-conditioned pools debias the IOB forecast | criterion met when QUIET_FLAT drift ≈ 0 | GO as a substrate (shadow) |

---

## Discarded (no-go, null, artefact, rejected)

### Dosing levers
| Lever | Why discarded | Evidence |
|---|---|---|
| Online cap-raise, committedCap | Binds at high IOB; churns | 43% revert (33–50% sweep); ~4 raises/6wk |
| Online cap-raise, confirmedCap | Rarely binds | 1–5 raises/6wk, all reverts from one user |
| Online aggression slider (up-on-highs) | Mis-targeted; highs are sizing/timing | 45% revert |
| Online hypoCaution slider (up-on-lows) | Coarse targeting; ratchets to max | good:wrong 0.74 flat; static per-user version used instead |
| Blanket committedCap raise | Suppressed confirms; priced badly | rejected 07-03 |
| RECOVERING-state SMB | Adds into a high-IOB tail → lows | rejected 07-03 |
| "Re-engage tuning" after confirmed highs | Same high-IOB problem | rejected 07-03 |
| Blanket OBSERVING raise | Contraindicated outside the safe cell | 07-03 |
| V4.4 post-SMB gate | Too restrictive to ever fire | engaged 0/99 then 0/115 (max delta far below trigger) |
| Second confirm on continued post-confirm acceleration | Real prediction signal (peak +23 mg/dL, distinguishable) but NO low-rate headroom — accel group already crashes ~19%/severe ~6.6% at current dose, not lower than decel (Δ overlaps 0); per-user C/F crash MORE; the fast-carb overshoot shape. Engine already blocks it (Fix 6) + holds COMMITTED 1.0×, which is correct | 2026-07-20 `2026-07-postconfirm-accel/` (3,879 anchors, 9 users, cluster-boot CI + real-engine scenario run) |

### Signals and predictors
| Relationship | Why discarded | Evidence |
|---|---|---|
| HR → glucose-rise lead (meal signal) | No cephalic HR lift before a rise; HR is not a meal signal as sensed | 37k paired cycles; only real coupling is HR↑→BG↓ ~10 min (exercise), wrong direction |
| Rolling-24h step load → insulin sensitivity | No reliable signal | matched-IOB forward-low hi/lo 1.06; residual slope wrong-signed; autosens corr −0.06 |
| Learned bedtime → lead sleep detection | Bedtime too variable | onset SD ~92 min; learned ≈ fixed clock |
| Dawn phenomenon → timed correction | Frequent but timing too loose | 82% of fasting nights, +55 mg/dL, but onset SD 75 min |
| Meal-time anticipation | ≈ chance | onsets roughly uniform |
| eventualBG as a forecast | Not predictive | R² −2.32 |
| Crash-shape (spike→low) predictable AT confirm | No — chance. Rules out predict-and-restrain; vindicates the retractable back-out (unwind after the fact) as the only crash defence | 2026-07-20 `2026-07-postconfirm-accel/meal_shape.py`, OOS AUC 0.518 [0.485, 0.549], 2117 meals, GroupKFold by user |

### Models, methods, and corrected effect sizes
| Item | Why discarded / corrected | Evidence |
|---|---|---|
| Optuna hypo-model tuning | In-sample gain was leakage | +14 pp CV → +0.7 pp honest LOUO; production model not replaced |
| ISF EMA overlay equivalence | Not clinically equivalent | within ±5% on only 28–58% of cycles |
| delta_accl ML retrain | Rejected on validation | 05-05 |
| Deviation-sensitivity function | Removed | 04-30, superseded by TDD-EMA |
| Brake "34% of high-time" as a lever | Proximate over-attribution | brake is directionally right on audit (13% proven + 76% assumed; don't loosen) |
| Cohort +13 pp as a clean Boost effect | Mostly overnight + selection/basal confound | +2.9 pp raw → +1.2 pp adjusted; permutation p ≈ 0.27 |
| Post-exercise "delayed 2× ramp" | Window-length artefact | de-artefacted to ~1.2×, flat |

---

## Partial / unproven / unbuilt

| Item | State |
|---|---|
| Overnight is causally Boost's doing | Suggestive from the regime split; the pre-registered within-user A/B is the test, not yet run |
| Exercise-anticipation prep helps in practice | Detection validated; the dosing benefit needs the shadow-log before any claim |
| Bedtime prior | Works only for the one very regular sleeper |
| Post-exercise window extension (2h → ~4h) | Supported by the mild tail; small refinement, untested |
| Multi-day activity-load ISF bump (deviation-based) | Design on record but never built; this session tested only the simplest 24h form (null) — the full deviation form is untested |
| Activity BG-rising override (Design 9) | Believed shipped but never coded in any branch; activity target still unguarded |
| Menstrual-cycle / hormonal sensitivity | Literature review + 3 proposals on record; needs cycle-detection input, not built |
| Tail-shape (under-recovery) predictable AT confirm | Weakly — OOS AUC 0.60 [0.58, 0.63] (2026-07-20 `meal_shape.py`); diffuse, partly second-meal clustering (time-of-day). Too weak to gate; only safe use is a weak prior to bring plateau-nudge on earlier. Low priority |

---

## Recurring lessons

- Several discarded entries began as large-looking effects that shrank once measured against a matched baseline (brake 34%, cohort +13 pp, recovery 2×) or against a leakage-free split (Optuna +14 pp → +0.7 pp). Effect sizes are provisional until baselined and leakage-checked.
- Tuning a dosing knob online against outcomes did not beat static per-user auto-config, in either direction, for either caps or sliders.
- Adding insulin into a high-IOB tail (recovering highs, late overnight bounces) is the repeated source of lows; the guards exist for this.
