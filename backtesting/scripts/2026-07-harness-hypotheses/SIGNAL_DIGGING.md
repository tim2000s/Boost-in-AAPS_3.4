# Signal digging on the GBM forecaster (2026-07-20) — the well is nearly dry for short-horizon prediction

*Full history, 9 users, 220k samples, BG+30 target, GroupKFold by user, bootstrap CIs. Question: with the
data we have, what signals reduce the GBM's error?*

## What the GBM is
Base GBM RMSE **21.7 mg/dL @30 min**. Importances: recent 5-min delta > current BG > IOB > time-of-day >
15-min delta > steps. It's a momentum + level + IOB + circadian model — the recent trajectory does most
of the work.

## Where it still fails (the residual map)
| regime | RMSE | share |
|---|---|---|
| rising (Δ15>+15) | **31.9** | 12% |
| high (>180) | 30.8 | 9% |
| meal-state | 25.9 | 6% |
| active (steps60>200) | 25.4 | 14% |
| falling | 24.5 | 12% |
| low (<80) | 23.8 | 9% |
| flat | 18.8 | 72% |
| overnight (0–6h) | **16.9** | 25% |

The error concentrates in RISING / HIGH / MEAL / ACTIVE regimes and is smallest overnight/flat. I.e. the
30-min forecast is hard exactly when something is happening — a meal or exercise — which is driven by
UNOBSERVED inputs (unannounced carbs, exercise intensity). Overnight/flat is nearly solved.

## Candidate signals — ΔRMSE when ADDED to base (95% CI)
| signal added | ΔRMSE [95% CI] | verdict |
|---|---|---|
| **acceleration** (Δ curvature) | **−0.164 [−0.179, −0.150]** | HELPS (the only real one) |
| volatility (SD30, Δ30) | −0.056 [−0.068, −0.041] | helps a little |
| heart rate (avg, HRR%) | −0.010 [−0.019, −0.001] | trivial |
| steps30 | −0.008 | trivial |
| IOB decomposition (activity/bolus/basal) | +0.111 | HURTS |
| sensitivity (DynISF + TDD 1d/7d/ratio) | +0.173 | HURTS |
| carbs + meal-state | +0.016 | hurts |
| ml_meal_likely + ml_hypo_risk | +0.010 | hurts |

## The honest conclusion
**For 30-min BG prediction the available signals are nearly exhausted.** The base momentum+IOB+circadian
model is near the data's information ceiling. The ONLY clean new signal is **acceleration** (curvature),
worth ~0.16 mg/dL — cheap, add it. Everything we'd *hope* carries information — the physiological IOB
decomposition, the sensitivity/TDD regime, the meal-state, the ML meal/hypo signals — actually **HURTS**
the short-horizon forecast: they're too slow (TDD/DynISF move over days), too noisy, or redundant with the
trajectory. The big residual (rising/meal regimes) is dominated by **unannounced meals + exercise
intensity, which are not in the data** (no meal announcements is the premise) → largely IRREDUCIBLE.

## Two threads — BOTH TESTED (2026-07-20)

### Thread 1 — longer horizon (+120): regime hypothesis REFUTED, HR a minor real signal.
Base RMSE 39.5 @2h (prediction is just hard). Importances shift to IOB + time-of-day + steps (momentum
decays, as expected). BUT the sensitivity/DynISF/TDD signals **still HURT, worse (+0.48)** — the "regime
signal has a home at long horizon" idea is dead. The only signal that flips to helping is **heart rate
(−0.13 [−0.15,−0.11])** — real and distinguishable, ~4× its +30 effect, but tiny against a base of 40. No
meaningful predictive win.

### Thread 2 — earlier meal DETECTION: no usable precursor; the glucose trajectory is the signal.
Per meal, lead of each candidate over the reactive BG-delta trigger (`meal_detection.py`):
- **HR appears to lead by ~15 min (86–100% of meals) — but it's a FALSE lead.** HR-crossing false-alarm
  rate is **83–100%**: HR is above resting+12 most of the awake day (movement/stress), so its "15-min
  lead" is just "HR was already up because the person was awake", not a meal-specific precursor. Same
  sensitive-not-specific trap as lo30. (2 of 8 users have no HR at all.) NOT usable.
- **Acceleration (curvature) leads by ~5 min [5.0, 9.8]** — real, CGM-derived (so specificity is
  manageable). Modest but genuine: the 2nd derivative flags the meal ~5 min before the delta threshold.

## Consolidated conclusion (signal digging + both threads)
**The glucose trajectory — value, delta, and its curvature — is essentially ALL the signal there is.**
Without meal announcements, you cannot know about an unannounced meal before its glucose signature, and no
non-CGM precursor (HR, activity, sensitivity, TDD, ML) gives specific, usable early warning. The remaining
residual is irreducible (unobserved carbs + exercise intensity). The ONE consistent, real, cheap win
across every test is **acceleration (curvature)**: it improves the forecast (~0.16 mg/dL @30) AND detects
the meal ~5 min earlier. Everything else we hoped carried hidden signal — the physiological state, the
sensitivity regime, HR — is either non-specific or too slow/noisy. The well is, honestly, nearly dry.
