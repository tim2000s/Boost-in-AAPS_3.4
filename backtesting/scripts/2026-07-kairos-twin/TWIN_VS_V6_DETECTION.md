# KAIROS Twin vs V6 — unannounced-meal detection (identifiable)

**Question.** How well does the Twin handle unannounced meals compared to the shipped V6
state machine? Specifically the two *identifiable* legs (no counterfactual needed):
detection **timing** and rising-cycle **attribution**.

**Design.** Replay the validated offline EnKF over each user's historical CGM (45 d, 7
users: tim, F, H, B, E, A, C — the cohort with ≥20 confirms) to recover the latent
glucose-appearance state `Ra`. Meal onsets are defined **from CGM alone** (≥30 mg/dL rise
over 45 min from an 80–170 start, deduped to 60 min) so neither detector defines its own
ground truth. Latency = minutes from that objective onset until each detector first fires
in a −15…+60 min window. Detectors compared **at equal false-alarm rate** (false alarm =
firing on a non-meal rising cycle, Δ>3 mg/dL/5 min, outside any onset window). Twin `Ra` is
a change-point detector (rise ≥ jump above its own trailing-30 min median), swept across
thresholds to trace its ROC; V6 is its single shipped confirm gate. Per-person `Gb` only;
all other params at population priors (a change-point on `Ra`'s own baseline is robust to
per-user SI/TDD bias). Filter fit (Gi vs CGM RMSE) 2.0–4.5 mg/dL across users — the model
tracks. Scripts: `twin_vs_v6_detection.py`, `twin_vs_v6_roc.py`. Raw traces stay in
scratchpad; only aggregates here.

## Result 1 — detection timing: a wash (observability wall)

| detector | sensitivity | false-alarm | median latency from onset |
|---|---|---|---|
| **V6 confirm gate** (shipped) | 0.767 | 0.116 | **20.0 min** |
| **Twin `Ra`** @ V6-matched FA (jump 0.8) | 0.805 | 0.105 | **20.0 min** |

At equal false-alarm rate the Twin catches **+3.8 pp** more meals (80.5% vs 76.7%) — a
marginally better ROC — but at the **same 20 min latency**. And latency is **flat at 20 min
across the Twin's entire ROC** (jump 0.4→3.0), i.e. tightening or loosening the Twin
detector does not move *when* it fires, only *how many* it catches:

```
 jump  sens   fa     lat_med
 0.4   0.92   0.170   20 min
 0.8   0.81   0.105   20 min   <- matched to V6 FA
 1.2   0.63   0.062   20 min
 2.0   0.33   0.017   20 min
 3.0   0.12   0.003   15 min
```

**Interpretation.** The 20 min floor is not a property of either detector — it is the
**interstitial lag plus the time for an unannounced meal to emerge from CGM noise**. Both
detectors sit downstream of the same lagged signal, so neither can fire before the meal is
distinguishable, and a better filter does not move that floor. This is the observability /
identification wall, quantified: **you cannot detect an undeclared carb earlier than the
CGM reveals it, and the Twin does not.**

## Result 2 — attribution: the Twin is the more *conservative* meal-caller

On rising cycles (Δ>3 mg/dL/5 min, pooled), how the two label the rise (Twin `Ra` change-
point at jump 1.2 vs V6 state ∈ {CONFIRMED, COMMITTED}):

| both say meal | Twin-only | V6-only | neither |
|---|---|---|---|
| 14.7% | 5.3% | **15.4%** | 64.7% |

V6 commits to a rise as a meal on ~30% of rising cycles; the Twin on ~20%. V6 flags **~3×
as many rises the Twin's physiology attributes to non-appearance** (its `Ra` stays flat →
the rise is explained by falling insulin action / rebound / noise). Some of those V6-only
calls are the meals the Twin misses (the sensitivity gap in Result 1); the rest are the
rebound/sensitivity rises the Twin declines to treat as meals. This analysis does not
separate those two sub-populations, so it is suggestive, not proof, of a rebound-avoidance
edge — but it is directionally consistent with the physiology (the model separates `Ra`
from `X`) and with why V6 needs its heuristic guards.

## Result 3 — rebound avoidance: hypothesis REJECTED (matched-baseline dissolution)

Result 2's "V6 flags ~3× more rises than the Twin" looked like the Twin wisely declining
harmful rebounds. It does not survive a harm-priced test (`twin_vs_v6_rebound.py`). For
every **non-meal** rising cycle (outside onset windows) where a detector fires, classify the
forward 60 min: `reaches_fall` (BG drops ≥20 mg/dL — a meal shot here stacks into a fall,
harmful), `real_climb` (BG net-rises ≥20 — a genuine appearance the onset detector was too
strict to log), or `flat`.

At **matched false-alarm rate** (jump 0.8) the two detectors' false alarms are
indistinguishable in harm — if anything the Twin's are marginally *worse*:

| detector | false alarms/day | reaches_fall | real_climb | harmful/day |
|---|---|---|---|---|
| V6 | 1.61 | 45.4% | 16.1% | 0.73 |
| Twin (matched FA) | 1.50 | **53.1%** | 8.6% | 0.79 |

And the decisive **differential** test — cycles V6 fires on but a *conservative* Twin
(jump 1.2) declines, i.e. the ones the Twin would "save":

| set | n | reaches_fall | real_climb |
|---|---|---|---|
| **V6-fires, Twin-declines** ("saved") | 129 | **40.3%** | 18.6% |
| Twin-fires, V6-declines | 50 | 46.0% | 10.0% |
| *(baseline: V6's overall FA)* | | *45.4%* | *16.1%* |

The cycles the Twin sheds are **less** likely to be harmful rebounds (40.3% vs 45.4%
baseline) and **more** likely to be real climbs it is missing (18.6%). The Twin's extra
conservatism is not selective rebound avoidance — it is simply firing less across the board,
and the declined set is if anything enriched for genuine (missed) meals. **Hypothesis
rejected.**

## Verdict

**The Twin does not beat V6 on unannounced meals in any *detection*-side metric we can
identify.** Detection timing is a 20 min observability wall both hit; the sensitivity/FA
trade-off is +3.8 pp (marginal); and the apparent rebound-avoidance edge dissolves under a
harm-priced baseline — the cycles the Twin declines are no safer than V6's, slightly
meal-ier. This is a textbook matched-baseline dissolution of a plausible-looking finding.

The Twin's genuine advantage on unannounced meals is therefore **entirely on the response
side, not the detection side** — the calibrated forecast band (60 min coverage 87%) and the
`Ra`-vs-`X` decomposition let the *dose* be sized under honest uncertainty (dose confidently
when the band is tight, hold when wide). That is a **tail/recovery** improvement — shaving
the second wave and the over-correction low, not front-running the peak — and it remains a
**policy** question, unvalidatable offline. Detection is not where KAIROS helps with
unannounced meals; sizing the response to a calibrated forecast is.
