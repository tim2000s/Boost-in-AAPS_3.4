# V7 Foundation Backtests — 2026-07-07

Scripts: `backtesting/scripts/2026-07-v7-foundation/` (`v7_common.py`, `01_residual_quantiles.py`,
`02_efficacy_innovation.py`, `03_distributional_sizing.py`; CSV outputs in `out/`).
Data: TimescaleDB `oref`, refreshed to 2026-07-07T09:59 (backfill_all.sh, since 07-05, all sites OK).
Dedup: last row per (user, 5-min bucket). Users tim, A–F, H (G excluded: thin, no era map).

**Expected-BG model used throughout (the honest subset of what the DB carries):** the DB does not
log the +30/+60/+90 predBG curves, so all three backtests use the IOB-only projection
`predBG(t+h) = bg + (−iob_activity × variable_sens × 5) × h/5`. Residuals in meal regimes contain
unmodeled absorption by construction; consumers condition on regime. This choice turns out to be
the binding limitation of Backtests 2 and 3 (see verdicts).

---

## 1. Residual-quantile substrate (Transplant-1 substrate)

Per-user quantiles (mg/dL) at h=60, 30d window (full table in `out/residual_quantiles.csv`):

| user | n | q5 | q25 | q50 | q75 | q95 | meal q50 | quiet q50 | night q50 |
|---|---|---|---|---|---|---|---|---|---|
| tim | 7999 | −23 | +8 | +38 | +82 | +171 | +62 | +35 | +10 |
| A | 8286 | −15 | +9 | +31 | +63 | +122 | +41 | +29 | +15 |
| B | 8023 | −25 | +4 | +24 | +54 | +110 | +26 | +23 | +18 |
| C | 7677 | −67 | −31 | −8 | +16 | +69 | −15 | −7 | −16 |
| D | 7983 | −27 | +2 | +19 | +38 | +79 | +8 | +20 | +20 |
| E | 8403 | −30 | −2 | +12 | +34 | +95 | +32 | +11 | +7 |
| F | 7512 | −13 | +10 | +32 | +77 | +155 | +71 | +27 | +12 |
| H | 1883 | −26 | −4 | +12 | +36 | +82 | +15 | +12 | +5 |

- **Calibration is the headline positive**: odd/even-day split coverage of the 5/25/50/75/95
  quantiles lands at 2.6–7.1 / 22–31 / 47–56 / 72–82 / 93–98 across all 8 users and all three
  horizons — center and shoulders are well-calibrated and stable. The empirical-quantile substrate
  is statistically sound.
- **Systematic positive bias** (median +12 to +38 at 60 min for 7/8 users): the IOB-only
  projection under-predicts because unannounced carbs live in the residual. C is inverted
  (median −8: projection over-predicts; his sens/activity fields run hot). Regime splits behave
  as expected (meal ≫ quiet ≫ night) but "quiet" still contains unannounced meal onsets
  (IDLE/OBSERVING cycles), so the bias survives regime conditioning. **Any consumer of these
  quantiles inherits this bias unless the point prediction absorbs it** — see Backtest 3.
- **Tail honesty (expected to fail — result: partial fail, as documented):** samples where the
  h=60 outcome was <70 that inform the bottom-5% bucket: tim 99, B 40, A 24, others 15–95
  (`out/residual_tail_honesty.csv`). Tens of events per user is enough to *validate a 5% shoulder*,
  nowhere near enough to *fit a 1% left tail* (a per-user 1st percentile of hypo-conditional
  residuals would need ~10–50× more events). **This is the documented reason the future chance
  constraint may only TIGHTEN existing guards, never relax them.**

---

## 2. Efficacy-innovation discrimination (Transplant-2 teeth)

Innovation = observed ΔBG(5m) − BGI5; `innov30` = 30-min rolling mean.

**(a) DAMPER side — no teeth as specced.**
- tim festival (06-17..22, day) vs quiet (06-03..13, day): innov30 **5.80 vs 5.66, Cohen's d = 0.02**.
  Threshold sweep: TPR 1–5% at FPR 0–3% — indistinguishable from noise.
- Cohort high-step (≥p90 steps_60m) vs low-step: d ∈ [−0.55, +0.20], signs inconsistent
  (only F shows the expected direction at d=−0.55).
- **Why (honest diagnosis):** the projection uses the *already-adapted* `variable_sens`
  (dynISF + activity-load pipelines have absorbed exercise into sens before we measure), so the
  innovation is centered precisely when the adaptation works. The damper statistic as specced
  measures the residual of a system that already contains the damper's signal. A **sens-frozen
  variant** (expected-ΔBG under profile/TDD-static ISF) is the follow-up that could give the
  damper teeth; untested here.

**(b) FLAG side — stays evidence-free, per the red-team prediction.**
Feature table (`out/flag_feature_table.csv`):

| stretch | label | innov30 | IOB | site age |
|---|---|---|---|---|
| tim 07-06 13:38 (Episode B) | **under-absorption (TRUE)** | **+17.4** | 2.7 | **1.7 h** |
| tim 07-06 10:03 (Episode A) | correct restraint | **+24.2** | 3.5 | 69.4 h |
| H ×5 budget=0 stretches | correct restraint | +3.8..+5.4 | 2.1–4.2 | n/a |
| compression artifacts ×4 | sensor artifact | −0.8..−5.3 (night) | ~0 | n/a |

- **Innovation does NOT separate under-absorption from correct restraint** — the strongest
  innovation in the sample is Episode A (the stretch where withholding was *right*). Positive
  innovation means "BG above IOB-projection", which is equally true of a resolving covered rise
  and a failing site.
- **Site age is the only separating feature** (1.7 h fresh site vs 69 h), at n(true)=1 — no AUC is
  honest at this n. Compression artifacts do show a distinct signature (negative night innovation
  with rebound) — consistent with the sensor-drift inversion that killed the two-sided state.
- **Conclusion: the flag gets no teeth from this data. V7 ships damper-only per the design — and
  per (a), even the damper needs the sens-frozen reconstruction before it has a signal.**

---

## 3. Distributional-sizing replay (Transplant-1 go/no-go)

Rule: argmax over dose grid of asymmetric utility (low:high cost R ∈ {4,7,10}) against the h=60
predictive distribution (point projection + user/regime residual quantiles 25/50/75), with the full
existing guard structure intact (state-multiplier envelope as bounds, era committedCap/confirmedCap,
non-meal v1-bound, post-rescue v1-bound, rolling cumulative cap, budget=0 ⇒ 0, awake only).

| R=7 | days | actual U | rule U | add U/day | pre-low % (base) | ΔTBR bracket pp | Test A |
|---|---|---|---|---|---|---|---|
| tim | 37 | 249.0 | 217.4 | 0.70 | 22.0 (27.8) | 0.20–0.78 | PASS |
| A | 21 | 244.4 | 283.8 | 4.29 | 7.5 (8.9) | 0.14–0.57 | PASS |
| B | 20 | 221.0 | 314.4 | 7.26 | 12.2 (19.6) | 0.30–1.18 | FAIL (base 3.83/1.01) |
| C | 19 | 92.8 | 115.0 | 3.04 | 19.4 (28.5) | 0.33–1.32 | FAIL (base 3.82) |
| D | 21 | 108.4 | 51.4 | 1.38 | 19.5 (33.8) | 0.10–0.39 | FAIL (baseline >4/1) |
| E | 21 | 15.0 | 67.6 | 2.67 | 7.0 (6.0) | 0.12–0.48 | PASS |
| F | 20 | 125.0 | 225.2 | 5.47 | 20.3 (22.1) | 0.55–2.21 | FAIL |
| H | 8 | 77.5 | 62.3 | 1.27 | 15.3 (2.9) | 0.07–0.30 | PASS |

Findings, in order of importance:

1. **Cost-ratio insensitivity — the tell that kills the go.** Results are *identical* across
   R = 4/7/10 for every user. The low-arm of the utility never binds because the q25 shoulder of
   the (positively-biased) residual distribution almost never projects <70. The safety knob does
   nothing; the rule is not making risk-sized decisions, it is riding the substrate's +12..+38
   median bias.
2. **Where the added insulin lands confirms it:** 205 U in BG 120–160 and **75 U at BG <120**
   (vs 244 U above 160). With every projection shifted +30, the rule sees "heading above 140" on
   nearly every cycle and doses to the envelope. B +7.3 U/day and F +5.5 U/day (+~15% of TDD) is
   not sizing, it is a bias pump. (It also *removes* 57 U from tim and 86 U from D — the same bias
   read through their caps/v1-bounds.)
3. **Episode B verification — FAILS, with a data correction.** On the 13:43–14:09 zeroed stretch
   the rule delivers exactly the historical 0.00: those are RECOVERING (non-meal) cycles and the
   recorded `v1_units` is **0** — the non-meal v1-bound zeroes any rule. The 07-06 forensic's
   "V1 base-would 0.3 U/cycle" was a reconstruction, not the recorded field; **the shadow-floor
   backtest that used 0.3 U/cycle inherits the same correction** (its Episode-B benefit on the
   RECOVERING stretch depends on which number is real — the live shadow-floor telemetry now
   logging will adjudicate). The rule does add on the COMMITTED holds (0.40→0.50, cap-bound),
   matching the committedCap analysis.
4. **Restraint preservation works by construction:** H's budget=0 morning stretches receive 0
   (envelope = budget × mult = 0); post-rescue and cumulative caps engaged correctly in replay.
5. Stuck-episode touch rate 51/101 ≥0.5 U (vs the composed floor's 32/109) — but bought with
   ~10–20× the floor's insulin volume, at base-rate-or-worse pricing for half the cohort.

---

## VERDICT

- **Transplant-1 substrate (empirical residual quantiles): GO** — calibration validated across
  8 users × 3 horizons (coverage within ~2–5 pp of nominal at every level, stable odd/even-day).
  **Left tail: NOT usable** — tens of <70-relevant events per user support a 5% shoulder only;
  the chance-constraint may only tighten. This is now documented with the n's.
- **Transplant-1 sizing rule as formulated: NO-GO for shadow implementation.** Two acceptance
  criteria must be met by a revised formulation before it earns a shadow slot:
  (a) **cost-ratio sensitivity** — R=4 vs R=10 must produce materially different doses (today: 0);
  (b) **bias absorption** — the point prediction must be conditioned so that quiet-flat cycles
  project ≈0 drift (e.g. delta-history/meal-onset conditioning, or per-regime recentering with
  "quiet" defined by CGM dynamics rather than V6 state). Until then the rule is a bias pump that
  fails Test A for B/C/D/F and adds sub-120-BG insulin nobody asked for.
- **Transplant-2 (efficacy): the flag gets NO teeth** (innovation ranks the correct-restraint
  stretch *above* the true under-absorption; only site-age separates, at n=1 — evidence-free, as
  the red-team predicted). **The damper also has no signal as specced** because the innovation is
  computed against the already-adapted sens; the sens-frozen variant is the one concrete follow-up.
  Per the design ("damper-only, chance constraints only tighten"), what survives today is:
  substrate GO, damper pending sens-frozen re-test, flag shelved with the evidence documented.

## Caveats
- IOB-only projection (no logged predBG curves): the central limitation, stated above; all three
  results are conditional on it.
- Residual quantiles fitted on the full 30d window and replayed over overlapping capped-era data
  (leakage is conservative here — it *flatters* the sizing rule, which still failed).
- ΔTBR brackets are decision-level ([0.15,0.6]×ISF min per pre-low U), no glucose feedback;
  low3h attributes any <70 within 3h regardless of cause (consistent with all prior pricing).
- vf/brakes unobservable historically; the envelope uses state multipliers without them (that IS
  the transplant under test). H's era caps 0.8→1.8 self-set (07-06); tim knob 1.3 not applied to
  the CONFIRMED envelope (conservative). Local time ≈ UTC+1 for the awake filter.
- `v1_units` = recorded would-SMB; the Episode-B forensic discrepancy (0 vs 0.3) is flagged in
  §3.3 and should be resolved from live shadow-floor telemetry before the floor's activation
  review.
