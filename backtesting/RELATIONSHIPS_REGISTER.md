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
| V1 acceleration gate vs V6 confirm | V1's `delta_accl>10` leads V6 CONFIRMED by median 15 min at 98% recall (precision 15%); V6 gated it away | 2026-07-20 `2026-07-v1-acceleration/`, 14,430 fires | Early-detection signal to reclaim (small/retractable only) |
| Primer confirm-net (credit accumulated fizzle IOB against the commit-shot) | Keeps every seed; at CONFIRM nets primer IOB beyond one base off the commit-shot → meal net-extra bounded to one base regardless of fizzle count. 87% of confirms follow ≥1 primer; nets off >0.1U on 57% (median 0.39U). Only removes insulin (safe-signed) | 2026-07-21 `2026-07-primer-clustering/primer_confirm_net.py`, 2170 meals | SHIPPED `6c439c8dee` (the one primer-cluster lever that survives) |
| V1 early acceleration bolus fizzle-safety | Fizzle-safe by size: pure (bolus-attributed) fizzle-low 4.4% vs 3.3% ambient, Δ +0.9% [−0.6, +3.0] — no excess. 69% of the raw fizzle-lows were DOWNSTREAM follow-through, not the entry | 2026-07-20 `v1_fizzle_pure.py`, V1-era Aug'25–Jul'26 | Restore entry + rely on V6 brake for follow-through; C/tim(U200) smaller cap |

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
| Commit-to-peak interval → post-commit low | Commits whose glucose peak arrives within 10 min are followed by a low 26.8% vs 16.0%, +0.108 [+0.055, +0.147]. Stable across every cut from 0 to 30 min (+0.112 to +0.138), 8/9 users. Beats delta_accl (0.498) and every other quantity at the commit | 2026-08-13 `2026-08-commit-peak-timing/`, 2,505 commits | Attribution only, NOT a lever: the interval uses post-commit data |
| Anticipating that interval at the commit | Predictable at 0.731 [0.701, 0.770] out of sample, but the prediction does NOT separate the low (0.448 [0.404, 0.499], wrong direction). Glucose alone predicts an early peak at 0.720, so the model is a glucose detector and glucose is inversely associated with the low. The early peaks it MISSES are the harmful ones: n=145, low rate 0.352 at median BG 131 vs n=172, 0.198 at BG 166 | same folder, `predict_peak.py` | Discarded. Predictable component is the benign component |
| Twin appearance rate (Ra) at the commit | Cannot see it, for a structural reason. Ra is at its own 30-min maximum on 93.2% of commits and above 0.95 of it on 96.4%, so the discriminator has no spread. Ra is inferred FROM glucose and cannot lead it | 2026-08-13, 221 commits with estimator fields | Discarded. Needs a carb observation independent of glucose |
| Meal detection from the trajectory | A declared meal separates from an unannounced rise at 0.805 (10 min after onset) and 0.975 (30 min), participants held out | 2026-08-13 `2026-08-carb-signature/`, 592 meals vs 2,883 rises | Detection is not the constraint |
| Meal SIZE from the trajectory | Not readable at any actionable horizon. Re-tested 2026-08-25 on 492,440 Loop meals from 839 participants and 71,761 REPLACE-BG meals from 189, against 592 from six. Shape features alone: 0.519 [0.510, 0.528] at 10 min, 0.608 at 60. Set against a matched baseline carrying the same person and clock information with the glucose trace removed, the trace adds +0.007 at 10 min and +0.008 at 60; pre-registered margin was +0.05 by 20 min. As a quantity the participant's own median gives MAE 13.02 g and the full model 13.12 g. The 2026-08-13 sub-chance 0.267 does not reproduce and was small-sample instability. Bolusing does invert the sign within-participant (+0.0175 [+0.0038, +0.0317] at 10 min, unbolused +0.0118 vs bolused -0.0056) but unbolused meals are no more readable: 40 g of difference moves the 10-min rise 0.83 mg/dL against a spread of 9.71, a twelfth of the noise | 2026-08-25 `2026-08-meal-size-readability/`, GroupKFold on 1,028 participants, cluster bootstrap | Discarded on far stronger evidence. Closes dose-sizing-to-the-meal |
| Meal size from the PERSON and the clock | Readable, and it is what every apparent trajectory result was measuring. Participant history alone 0.812, plus clock 0.830, MAE 13.2 g, flat across horizon because it owes nothing to the excursion. Needs announcements to build the history, which Boost does not have, and answers what this person usually eats at this hour rather than what is in front of them | 2026-08-25 same folder | Not a lever for Boost; prices what a calibration period would buy |
| Meal DETECTION from the trajectory | Holds at scale, and its thirty-minute headline was partly a construction artefact. 492,440 announced meals against 562,564 undeclared rises, 850 participants: 0.833 [0.830, 0.836] at 10 min and 0.952 at 30 as previously built, reproducing 0.805/0.975 on six. But the negative class must reach 25 mg/dL in 30 min while meals face no such bar, so the classes are separated partly by rule; holding meals to the same bar gives 0.843 at 10 min and 0.873 at 30, near-flat across horizons. Quote the matched figures | 2026-08-25 `2026-08-meal-size-readability/detection.py` | Detection is not the constraint. The accel meal shadow's bar is 0.843 at 10 min, not 0.805 |
| Rise CONSEQUENCE from the trajectory | Real, distinguishable, and too small where it would be spent. 1,986,123 rise onsets, 1,807 participants, all 7 studies (the 5 without carbs are usable here because the outcome is read from the trace). Onset glucose alone gives 0.677 for peak rise >=60 and 0.812 for exceeding 180; plus clock, 0.717 and 0.829. The shape adds, as a PAIRED difference: +0.0142 [+0.0126, +0.0157] at 10 min and +0.0323 [+0.0300, +0.0347] at 20 for >=60; +0.0140 and +0.0267 for >180. Grows monotonically to +0.049 to +0.082 at 30 min, unlike meal size which was flat, so the information is genuinely arriving; it just arrives late. The 0.05-by-20-min bar is not cleared. Base rate for reaching 40 mg/dL is 0.833 to 0.859 across all 7 studies | 2026-08-25 `2026-08-meal-size-readability/` rise_outcomes.py, rise_consequence.py, rise_delta_ci.py | Not a lever at dosing horizons. Where a rise STARTS plus the clock is nearly all of it, and the controller has both already |
| Consequence prior vs what the loop already encodes | NOT redundant, and this is the one lever that survived its own control. 27,619 rise onsets, 36 participants, engine record joined to outcome. The loop's own forward projection is at chance for whether the excursion will be consequential: eventualBG alone 0.545 for peak rise >=60 (base 0.544) and 0.527 for exceeding 180 (base 0.398). Onset glucose plus the clock gives 0.625 and 0.763. Adding the entire loop record to that prior adds +0.002 and +0.001. The loop HOLDS onset glucose; it does not turn it into a consequence estimate | 2026-08-25 `2026-08-meal-size-readability/prior_vs_loop.py` | Live. Not new signal, an unused reading of existing signal. Confounded arm: delivered insulin scores 0.410 to 0.426, below chance, and changes the outcome it is scored against |
| IOB@30min prediction | Trustworthy | MAE 21, night bias ~0, Parkes A+B 98.9% | Usable |
| UAM prediction | Upper bound on unchecked climbs | +20/+48 on climbs | Interpret as a bound |
| Forward high / low predictability | Predictable an hour out | grouped-OOS AUC 0.83 / 0.78 | Foreseeability layer |
| ML model directionality | `mlHypoRisk` restrains only, on all four paths. `mlMealLikely` is dose-INCREASING on three: releases the V1 G3 tier hold above 0.50, weight 0.20 in the V5 meal-signal score (states multiply dose 0.3-1.8x), blocks the sleeping classification above 0.30 | 2026-09-02 source review, `backtesting/reports/2026-09_boost_lgbm_methods.md` | Documented. A learned component DOES add insulin in the shipping engine |
| Hypo model training-set size | The shipped model's binding constraint is its 28-participant training set, not its features. Commons-trained (183 participants) applied to Boost's users beats Boost-trained by +0.024 AUC [+0.013, +0.034] at 1h and +0.073 [+0.026, +0.102] at 4h, and beats the matched glucose+clock baseline by +0.054 at both. Learning curve 0.683 at n=7, 0.729 at n=28, 0.745 at n=112, flat thereafter | 2026-09-02 `2026-09-ml-features/c1_hypo_scale.py`, `c1b_hypo_transfer.py` | PROVISIONAL: comparison arm was a 16-user refit, not the production artefact. Refit on Commons and shadow-log against the live score |
| Fall-consequence prior | Null. Shape adds +0.017 to +0.042 over onset glucose + clock, never reaching the 0.05 margin; the clock adds nothing at all on falls, +0.0004 [-0.0008, +0.0015], against ~+0.04 on rises. Reduces to a monotone function of onset glucose, which the engine already thresholds | 2026-09-02 `2026-09-ml-features/c2_fall_consequence.py`, 137,582 Commons + 359,419 corpus onsets | Discarded. Do not build |
| Post-rescue guard conditioning | Works off Boost, fails on Boost. Repeat-low prediction at recovery: Commons +0.065, corpora +0.054 over a baseline at chance; Boost's own 16 users +0.029 to an absolute 0.529, Commons estimate outside the Boost interval. No decile beats the fixed rule | 2026-09-02 `2026-09-ml-features/c3_post_low_rebound.py`, `c3_operating.py` | Discarded. Keep the fixed rule |
| Clock as a meal-detection feature | Real but mostly a night gate. Cuts false alarms 29% on Loop at unchanged sensitivity (0.364 to 0.258/day, paired -0.105 [-0.112, -0.099]); restricted to 06:00-22:00 the AUC gain collapses +0.035 to +0.008. A fixed 21:00-05:00 gate recovers 71-77% with no model. REDISTRIBUTES: top 5% of overnight announcers lose median sensitivity 0.692 to 0.597, worst -34pp, and 42% of participants are worse off | 2026-09-02 `~/meal-investigations/scripts/clock_detection.py`, 3 cohorts | Build as an explicit night gate, not as hidden clock features |
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
| Primer rolling-window cap (block fizzle-clustering) | ~1:1 seed:fizzle trade at every W×K — seeds and fizzles temporally interleaved, real meals often start right after a fizzle burst, so no window separates them. gap+reset identical (fizzles precede the confirm) | 2026-07-21 `2026-07-primer-clustering/primer_cap_sweep.py` |
| Primer IOB-taper (shrink when recent primer-IOB high) | Cuts dips only ∝ cutting the dose everywhere incl. real-meal seeds (cap 0.5: dips −37%, seed −41%) — seeds fire after fizzle bursts so they get tapered too; ≈ a smaller global primer | 2026-07-21 `2026-07-primer-clustering/primer_iob_taper.py` |
| V4.4 post-SMB gate | Too restrictive to ever fire | engaged 0/99 then 0/115 (max delta far below trigger) |
| Per-user vs cross-user anticipation | EXERCISE onset (45min): per-user temporal AUC 0.78 (all 8 users 0.72-0.83) vs cross-user 0.67 — per-user DECISIVELY better (exercise timing idiosyncratic). MEAL onset: cross-user 0.72 ≈ per-user 0.68 (meal times semi-universal; per-user wins only for high-data users, collapses on thin-n). Reactive/cross-user 'no signal' conclusion does NOT bound the anticipation question | 2026-07-27 `2026-07-peruser-anticipation/` | Build exercise anticip PER-USER; meals HYBRID (cross prior + per-user adapt); safety from retractability not accuracy |
| Post-meal-exercise hypo — WHY | NOT dose-driven: crashers carry LESS IOB (0.96 vs 1.61U) same bolus; crash rate FALLS with IOB (32/22/18% low/mid/high tertile). Mechanism = carbohydrate-counterweight failure (insulin-independent exercise glucose drain lands when meal carb-flux is thin, from lower BG 114 vs 136). Loop on wrong side: needs glucose-IN, only has insulin-OUT (already spent). Fix = anticipatory withdrawal or carbs, NOT smaller meal dose | 2026-07-27 `2026-07-postmeal-exercise-mechanism/` (686 events) | Reframes the exercise problem; refutes review's dose story |
| True insulin-efficacy signal (does on-board insulin work?) | NONE beyond glucose trajectory + dose magnitude. OOS GroupKFold, 1717 stuck-high entries: crash LR 0.453→0.500 (chance); stall 0.561→0.592 (IOB-magnitude only); loop deviation 0.474 (below chance); Twin carb-appearance Ra INCONCLUSIVE (0.473 but only ~30 independent Twin-era episodes; 88-94% in-era coverage, NOT abstention; powered re-run pre-registered ~1 Sep). Efficacy blind spot is a SENSING problem not modelling | 2026-07-27 `2026-07-efficacy-signal/` | Discarded lever; don't build efficacy detector from current telemetry; validates existing post-rescue guards |
| Second confirm on continued post-confirm acceleration | Real prediction signal (peak +23 mg/dL, distinguishable) but NO low-rate headroom — accel group already crashes ~19%/severe ~6.6% at current dose, not lower than decel (Δ overlaps 0); per-user C/F crash MORE; the fast-carb overshoot shape. Engine already blocks it (Fix 6) + holds COMMITTED 1.0×, which is correct | 2026-07-20 `2026-07-postconfirm-accel/` (3,879 anchors, 9 users, cluster-boot CI + real-engine scenario run) |

### Signals and predictors
| Relationship | Why discarded | Evidence |
|---|---|---|
| HR → glucose-rise lead (meal signal) | No cephalic HR lift before a rise; HR is not a meal signal as sensed | 37k paired cycles; only real coupling is HR↑→BG↓ ~10 min (exercise), wrong direction |
| Rolling-24h step load → insulin sensitivity | No reliable signal | matched-IOB forward-low hi/lo 1.06; residual slope wrong-signed; autosens corr −0.06 |
| Learned bedtime → lead sleep detection | Bedtime too variable | onset SD ~92 min; learned ≈ fixed clock |
| Twin forecast → lead RISES (rise-retiming) | Twin fc30 is WORSE than oref eventualBG and the naive BG-trend at predicting rises (FA 0.24 vs 0.14 vs 0.10, less lead) — a rise is directly visible in the trend, no hidden state to infer. Twin value is asymmetric: descent-only | 2026-07-18 `TWIN_RISE_LEAD.md`, 146 rises/7 users |
| Dawn phenomenon → timed correction | Frequent but timing too loose | 82% of fasting nights, +55 mg/dL, but onset SD 75 min |
| Meal-time anticipation (per-user shadow) | The shadow is a more complicated way of telling the time. Priced 2026-08-25 on 11 participants and 149,906 cycles, first possible after the tag backfill. Against an hour-of-day rate fitted on the participant's other days: +15 min delta +0.001 [-0.027, +0.030], +30 min -0.003 [-0.018, +0.010], +60 min -0.022 [-0.036, -0.007], ahead on 6/11, 6/11 and 2/11 participants. Note onsets are NOT uniform, the clock alone reaches 0.587 to 0.625, so meal timing has real structure and the shadow simply fails to beat the clock at it | 2026-08-25 `2026-08-meal-size-readability/anticipation_price.py` | Discarded. Do not build on the per-user prior; if timing is ever wanted, use the hour |
| Exercise anticipation (per-user shadow, the other arm) | Worse than the meal arm and clearly beaten. 10 participants, movement onsets from their own step feed, control an hour-of-day rate fitted on their other days: +15 min shadow 0.489 vs clock 0.662, delta -0.173 [-0.220, -0.123], ahead on 0/10; +30 min -0.121 [-0.163, -0.073]; +60 min -0.104 [-0.148, -0.059]. Every interval excludes zero in the wrong direction. BUT the clock predicts exercise onset BETTER than it predicts meals, 0.662 to 0.694 against 0.587 to 0.625, and reaches 0.760 for one participant | 2026-08-26 `2026-08-meal-size-readability/anticipation_exercise.py` | Shadow discarded, both arms now priced. The hour-of-day exercise prior is the strongest per-user timing signal measured in this programme and points at the compound low mechanism |
| eventualBG as a forecast | Not predictive | R² −2.32 |
| Founding-flow restoration (seed-hard→trigger-UAM→firm-up) into V6 | NOT supported broadly. On real meals V1≈V6 (same peak 183, same lows, delivery indistinguishable; the 15-min "lead" is the CONFIRM label not delivery). On gated high meals the WITHHELD ones peak lower (193 vs 207) with fewer lows (8.4 vs 12.4%) than the aggressively-dosed — aggressive-early associates with MORE lows (selection-confounded by meal size, but no evidence gating costs outcomes). Keep the primer per-user; don't build a graded aggressive ramp | 2026-07-20 `2026-07-founding-flow/`, 8 users both eras, within-user cluster-boot |
| Crash-shape (spike→low) predictable AT confirm | No — chance. Rules out predict-and-restrain; vindicates the retractable back-out (unwind after the fact) as the only crash defence | 2026-07-20 `2026-07-postconfirm-accel/meal_shape.py`, OOS AUC 0.518 [0.485, 0.549], 2117 meals, GroupKFold by user |
| Decaying delta-acceleration across the approach → confirm crash | Not distinguishable. Also refuted: delta below the prior delta, and eventualBG over-prediction. NB `delta_accl` = 100×(delta−shortAvgDelta)/max(|shortAvgDelta|,2), so it reads near ZERO on a steady steep rise and high at rise ONSET — a low value does not mean the rise is failing | 2026-08-12 `2026-08-confirm-decay/`, 1268 confirms, 12 users, 9 threshold variants; decaying 24.0% vs sustained 22.1%, diff +1.9pp [−4.1, +8.1]; participant-level bootstrap |
| Confirm dose size → crash | Not distinguishable at any cut (≥2.5/3.0/3.5/4.0 U) | same run; ≥3.5 U 28.0% vs 22.7%, [−4.6, +24.9] |

### Models, methods, and corrected effect sizes
| Item | Why discarded / corrected | Evidence |
|---|---|---|
| Post-meal exercise "crashers carry LESS insulin" | WITHDRAWN. Rested on pooled absolute-unit IOB across participants whose TDD spans 16-58 U (3.5x) with one on U200. Between-participant correlation of median IOB at onset with own low rate is -0.388, which pulls the pooled association toward inversion. Standardised by own TDD and resampling participants: 0.549 [0.512, 0.604], every participant above 0.5, median IOB 1.76 U where a low followed vs 1.36 where none did — the ORDINARY direction | 2026-08-13 `2026-08-postmeal-exercise-recheck/`, 157 events, 5 users |
| ml_hypo_risk as a single quantity | The column pools THREE model generations with different targets and output scales, nothing marks the boundary. Cohort median score falls 0.364 → 0.038 in the week of 2026-06-29. Any figure computed across it is a mixture | 2026-08-13 `2026-08-ml-field-audit/` |
| One-armed counterfactual summed across a record | The acted-fraction kernel rises to 1 and STAYS there, so a modelled lift is a permanent step; 84 confirms x ~100 mg/dL drives modelled mean glucose to 8,290. Windowing does not repair it, it relocates the discontinuity. Only per-event framing is defensible | 2026-08-13 `2026-08-confirm-insilico/` |
| Tightening the hypo threshold to fix counterfactual credulity | Does NOT work and goes the wrong way. Share of UNEXPLAINED lows the model claims to remove rises 0.51 → 0.64 moving from 70 to the TING floor of 63, because the shallow lows leave the numerator and the lift clears the deep ones anyway. The credulity is in the size of the lift | same folder |
| ISF x dose x acted as a calibrated effect | Cannot be calibrated from the record. Predicted lowering by the nadir correlates with the observed peak-to-nadir fall at -0.03 across 80 confirms, because larger confirms accompany larger meals | same folder |
| Optuna hypo-model tuning | In-sample gain was leakage | +14 pp CV → +0.7 pp honest LOUO; production model not replaced |
| ISF EMA overlay equivalence | Not clinically equivalent | within ±5% on only 28–58% of cycles |
| delta_accl ML retrain | Rejected on validation | 05-05 |
| Deviation-sensitivity function | Removed | 04-30, superseded by TDD-EMA |
| Brake "34% of high-time" as a lever | Proximate over-attribution | brake is directionally right on audit (13% proven + 76% assumed; don't loosen) |
| Cohort +13 pp as a clean Boost effect | Mostly overnight + selection/basal confound | +2.9 pp raw → +1.2 pp adjusted; permutation p ≈ 0.27 |
| Post-exercise "delayed 2× ramp" | Window-length artefact | de-artefacted to ~1.2×, flat |
| KAIROS Twin as a controller / forecast-MPC | Insulin gain non-identified: 8× SI invariance in the EnKF (Ra absorbs it); clean-fall direct fit unstable (−1.4× to 39×, R²≤0). Anchoring SI to clinical ISF fixes the forward gain but off-policy calibration still decays + band doesn't self-limit. TING planner fed the Twin is degenerate (65–202 U/day vs 19 delivered) and can't be closed-loop-validated (needs the off-policy counterfactual the Twin lacks) | 2026-07-18 `TWIN_OFFPOLICY.md`, `twin_identify.py`, `twin_ting.py`, `KAIROS_DECISION.md` |
| Learn insulin sensitivity (SI) from CGM | Non-identifiable observationally — latent meal appearance Ra absorbs any insulin gain; needs a within-user micro-bolus probe, not a model | 2026-07-18 8× invariance + clean-fall instability |

---

### Confirm dose reduction, priced
| Item | Finding | Evidence |
|---|---|---|
| Confirms preceding a low, counted | 198 of 591 confirms across 9 participants are followed by a glucose below 70 within 4h (0.34); 138 below the TING floor of 63 (0.23); 56 severe. Every participant above 0.13. C 0.35, D 0.32, self 0.30 at the TING floor. Depends on no modelling | 2026-08-13 `2026-08-confirm-insilico/`, 30 days |
| Cost currency for a dose reduction | Insulin removed is NOT the cost; glucose exposure is, and it differs 8.5x by where the cut lands. Cutting a late commit to 0.85 costs 1.00 mg/dL.h and avoids 0.099 lows; a normal one costs 8.48 and avoids 0.119 | 2026-08-13 `2026-08-commit-dose-replay/` |
| Targeting the late commit | Worth 6.6x uniform at matched multiplier with perfect foresight. A buildable detector (predicting the cost of cutting, not the timing) reaches ~2x, and a combined gentle-uniform-plus-deep-targeted policy saves only 2-9% at matched benefit; DEEP targeted cuts are worse than uniform because a prediction error is charged at full cost | same folder |
| Attribution split for the in-silico trial | Only 214 of 591 confirms have a modelled deficit covering the observed peak-to-nadir fall; 141 of 198 lows sit after one the model cannot account for. The CONTROL: the reduction still removes 51% (0.64 at the TING floor) of the lows in the set it says it cannot explain, so effect sizes are inflated on both sets | 2026-08-13 `2026-08-confirm-insilico/cohort_trial.py` |

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
| V1 early-primer reintegration into V6 engine | Design on record (`2026-07-v1-acceleration/REINTEGRATION_SPEC.md`): OBSERVING acceleration primer, netted off the commit-shot (move-not-add), V6 brake guards the follow-through, auto-config-sized. Shadow-first, not built |
| Tail-shape (under-recovery) predictable AT confirm | Weakly — OOS AUC 0.60 [0.58, 0.63] (2026-07-20 `meal_shape.py`); diffuse, partly second-meal clustering (time-of-day). Too weak to gate; only safe use is a weak prior to bring plateau-nudge on earlier. Low priority |

---

## Recurring lessons

- Several discarded entries began as large-looking effects that shrank once measured against a matched baseline (brake 34%, cohort +13 pp, recovery 2×) or against a leakage-free split (Optuna +14 pp → +0.7 pp). Effect sizes are provisional until baselined and leakage-checked.
- Tuning a dosing knob online against outcomes did not beat static per-user auto-config, in either direction, for either caps or sliders.
- Adding insulin into a high-IOB tail (recovering highs, late overnight bounces) is the repeated source of lows; the guards exist for this.
