# KAIROS Twin — does the forecast floor predict lows better than oref? (identifiable)

**The make-or-break test for the "descent-side withdrawal" idea (dream idea 4).** If the
Twin's forecast *floor* doesn't lead real lows better than the hypo predictors oref already
computes, the idea dies here — cleanly, the way rebound-avoidance did.

**Design.** Ground truth = objective low events from CGM alone (BG crosses <70 mg/dL having
descended from ≥90, deduped 60 min): **80 events, 7 users** (tim 24, B 22, C 12, F 7, E 6,
A 5, H 4). Predictors, each swept over its own threshold to trace an ROC and compared at
matched **sensitivity** (sensitivity saturates high, so false-alarm is the discriminating
axis):
- **Twin `lo30` / `lo60`** — 5th-percentile forecast floor at 30 / 60 min (offline EnKF
  forecast replay, same design as the validated forecaster: roll forward under delivered
  insulin + meal-uncertainty process noise).
- **oref `minGuardBG`, `minPredBG`** — oref's own forward hypo predictions (`reason_*`).

A predictor "leads" a low if it fires in [onset−60 min, onset−10 min] (≥10 min lead to
act). False alarm = firing on a descending cycle with no low in the next 60 min. Scripts:
`twin_hypo_lead.py`. Aggregates only; raw traces in scratchpad.

**Data-quality note (found here, worth flagging):** `reason_minguardbg` / `reason_minpredbg`
are stored **mmol/L for six users** (median ~5, can go negative — oref's unbounded
projection) but **mg/dL for E** (median ~103). Unit-normalised per user (×18 where
median<30) before comparison. Other analyses reading these columns should do the same.

## Result — the Twin's 30-min floor wins on false-alarm rate

| catch ≥ this % of real lows | Twin `lo30` FA (lead) | oref `minPredBG` FA (lead) | oref `minGuardBG` FA (lead) |
|---|---|---|---|
| 86% | **0.10** (20 min) | 0.29 (55 min) | 0.36 (55 min) |
| 90% | **0.14** (25 min) | 0.29 (55 min) | 0.36 (55 min) |
| 94% | **0.24** (40 min) | 0.34 (60 min) | 0.36 (55 min) |

At equal catch the Twin's 30-min floor fires on **⅓–½ the false alarms** of oref's own
predictors. oref cannot reach a false-alarm rate below ~0.26 (minPred) / ~0.36 (minGuard)
at *any* threshold — it predicts deep lows aggressively, which is the blunt over-warning
behind the known over-braking. The Twin operates in a low-false-alarm regime oref can't.

**The trade is lead time**, and it is the right trade: the Twin warns 20–40 min ahead, oref
55–60 — but oref's extra lead comes bundled with 2–3× the spurious warnings. For insulin
*withdrawal* (a zero-temp acts 30–60 min out), 20–40 min is sufficient, and the lower
false-alarm rate is exactly what protects TIR: far fewer unnecessary withdrawals dragging
highs back up.

**`lo60` is unusable as a trigger** (FA 0.56 at its tightest). The meal-uncertainty process
noise that makes the 60-min band honestly wide also makes its lower edge cross the threshold
almost always — consistent with the on-device observation (lo60 floor of 39 during a benign
glide to 108). The actionable Twin hypo signal is the **30-min** floor, not the 60-min one.

## Verdict

**Idea 4's identifiable leg clears.** The Twin's 30-min forecast floor is a materially
better discriminator of real lows than the hypo predictors oref already ships — same catch
at a third to a half the false alarms — with enough lead (20–40 min) to act by withdrawing
insulin. This is the first genuine, out-of-sample, response-side evidence for KAIROS on the
descent, and it is exactly where today's detection-side work said the recoverable variance
lives (the come-down, not the peak).

**What this does NOT show (the policy leg, still open):** that acting on the signal — a
forecast-floor-triggered early zero-temp — actually improves outcomes. That changes
delivered insulin, so it is unvalidatable offline (identification wall) and must go
shadow-first, priced against observed outcomes at the two-test bar. And `n=80` pooled is
thin: this is a cross-user pooled prediction result, not per-user proven. But the gate to
*build the shadow* is now met: the signal is real and beats the incumbent.
