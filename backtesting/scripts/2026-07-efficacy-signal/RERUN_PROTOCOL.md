# Pre-registration — Twin-Ra efficacy re-run (locked 2026-07-27)

The 2026-07-27 efficacy probe left one strand undecided: whether the Twin's inferred
glucose-appearance rate **Ra** — a *dose-independent* observable — separates the rebound crash
from the settle at a stuck high. It was untestable then because the Twin was only ~10 days old
(~30 independent stuck-high episodes for the single Twin user). Ra coverage is **not** the
problem (88–94% within the Twin era); the Twin simply needs time. No code change helps — this is
a data-accrual wait. This file locks the exact test **before** the data exists, so the re-run is
confirmatory, not exploratory.

## Trigger

Re-run when the Twin-era stuck-high **regime-entry** count for the Twin user reaches **≥ 150**
usable episodes (full 3 h forward window). At the observed rate (~3.3/day) that is on or around
**2026-09-01**. Check with:

```sql
SELECT count(*) FILTER (WHERE be) FROM (
  SELECT (cgm_mgdl>150 AND iob_iob>1.0 AND coalesce(sug_cob,0)=0)
     AND NOT lag(cgm_mgdl>150 AND iob_iob>1.0 AND coalesce(sug_cob,0)=0)
             OVER (ORDER BY ts_epoch) AS be
  FROM boost_decisions WHERE user_id='tim' AND boosttwin_ra IS NOT NULL) t;
```

Do **not** re-run early and re-test on a peek — that reintroduces the multiple-comparisons
problem this file exists to prevent.

## Locked design (identical to the original probe, Ra strand)

- **Population:** stuck-high regime entries — BG > 150 mg/dL, IOB > 1 U, COB = 0, Twin-era,
  Ra present, full 3 h forward window.
- **Primary label:** `CRASH` = min BG < 70 within 3 h.
- **Primary test:** does adding Ra (and the deviation + IOB-activity efficacy block) to the
  trajectory baseline lift out-of-sample AUC for CRASH? Single Twin user → **time-blocked**
  5-fold CV (chronological folds, no shuffle), not GroupKFold.
- **Primary read of Ra specifically:** Ra-alone AUC vs CRASH, and crash rate in high-Ra vs
  low-Ra halves. The mechanism hypothesis (pre-registered direction): **high inferred
  carb-appearance → MORE crash** (carbs masking still-working insulin), so a positive result is
  Ra-alone AUC **> 0.5** with the high-Ra half crashing more.
- **Secondary label:** `STALL` = never < 140 within 2 h.

## Decision rule (locked)

- **Signal confirmed** only if Ra-alone AUC ≥ 0.58 **and** its bootstrap 95% CI excludes 0.50
  **and** the high-Ra/low-Ra crash-rate gap is in the pre-registered direction and ≥ 8 pp.
- **Null confirmed** if the incremental AUC over the trajectory baseline has a 95% CI containing
  0 (consistent with the crash negative already SOLID for non-Twin features).
- Anything between → still under-powered; extend the accrual window, do not soft-call.

## What a confirmed Ra signal would (and would not) mean

It would be the first evidence of a *dose-independent* efficacy read in our telemetry — worth a
shadow controller that damps the confirm-chase when Ra is high. It would **not** overturn the
main negative (no efficacy signal beyond trajectory + dose magnitude from non-Twin observables),
which is already SOLID and Twin-independent. Reproduce with `efficacy_signal_probe.py`; the Ra
block is the tim-only section.
