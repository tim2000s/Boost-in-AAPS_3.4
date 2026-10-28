# The unforecastable lows are ACTIVITY — and V6 sees the steps but doesn't act on them

*2026-07-19. `sl1_steps.py`. Answers "does post-insulin step data correlate with lows?" — yes, and it
explains ff2/dr3 (the confirm-crash + plateau lows glucose+insulin scored at chance, 0.55).*

## Steps predict the lows glucose+insulin couldn't
Forward steps (activity in the 90 min AFTER the cell) as a low predictor, all users:
- **confirm** cells: go-low 766 vs safe 362 steps, **AUC 0.627**; 76% of lows had >300 fwd steps vs 54%.
- **plateau** cells: go-low 874 vs safe 254, **AUC 0.617**; 70% of lows >300 steps vs 46%.
These are "dose, then walk" lows. The cause is outside the glucose-insulin model — but it IS logged.

## But it's activity AFTER the decision — current activity is weak
Recent steps AT the cell: confirm AUC 0.595, plateau 0.534. So gating DOSING on current steps is weak
(the walk usually hasn't started). The actionable signals are activity ONSET (react fast when steps
land) + the habitual-time prior (register: fires ~55min ahead, AUC 0.85).

## V6 DETECTS the activity but does NOT act on it — the real gap
- The step-based activity-ISF (`wouldDeltaIsfPct`) is **SHADOW-ONLY**: code references it once, to pick
  the log sign (OpenAPSBoostPlugin:1926); it is NEVER applied to sens or dose. And it's a DAILY-load
  signal, not the acute walk.
- Data (tim, binned by steps_30m): DynISF is **flat** across activity (still 154 → active 156); no acute
  step-based dose reduction. The only APPLIED exercise protection is oref's exercise-TEMP-TARGET
  (`half_basal_exercise_target`), which requires the user to MANUALLY declare exercise → useless for an
  unannounced walk.
- ⇒ **The dose-then-walk lows are essentially UNPROTECTED.** V6 logs the steps and does nothing with them.
  This matches the memory's flagged "exercise protections dead on live path".

## The lever (finally, one that targets the CAUSE and is safe-direction)
An ACUTE activity response: when steps spike after a dose (`steps_5m/30m` over a per-user threshold),
raise ISF / zero-temp / withdraw the pending SMB. It is INSULIN-REDUCING (safety direction — much
lower-risk than the add-insulin levers that all died), and it attacks the actual cause of a third-plus
of these lows. Natural home: the KAIROS idea-4 WITHDRAWAL machinery, but triggered by activity onset
(not the Twin lo30, which failed for plateau lows). Caveats: steps are 0.62 AUC (helps, not eliminates);
reactive unless paired with the habit prior. Shadow-first + two-test bar, but the reduce-on-activity
direction is well-established (oref exercise mode, autosens).
