# KAIROS Twin — does the forecast lead RISES better than the incumbent? No. (the gate that failed)

*2026-07-18. Script: `twin_rise_lead.py`. The identifiable gate for the second brick (rise-retiming),
run before shipping any shadow — and it did not clear. Cohort of 7, pooled, aggregates only.*

## The question

Idea-4 (descent) cleared its gate: the Twin's 30-min forecast **floor** (`lo30`) led real lows at
⅓–½ the false alarms of oref's hypo predictors (`TWIN_HYPO_LEAD.md`), justifying earlier
*withdrawal*. The mirror question for the rise: does the Twin's forecast **point** (`fc30`) lead real
upward excursions earlier than the incumbent's own forward predictor, so a Twin-informed confirm
could bring the incumbent's dose earlier (move insulin, not add it — the harm-neutral TING lever)?

Ground truth = objective rise events (BG crosses >170 having been ≤140 within 30 min, deduped 60 min;
**146 events, 7 users**). Predictors swept and compared at matched sensitivity (FA is the axis).

## Result — the Twin is WORSE than the incumbent on rises

| catch ≥ | Twin `fc30` FA (lead) | oref `eventualBG` FA (lead) | naive `trend` FA (lead) |
|---|---|---|---|
| 70% | 0.242 (15 min) | 0.142 (20 min) | **0.100 (20 min)** |
| 80% | 0.242 (15 min) | 0.142 (20 min) | **0.100 (20 min)** |
| 90% | — (can't reach) | 0.165 (25 min) | 0.157 (20 min) |

The Twin `fc30` has **higher false alarms and less lead** than both oref's own `eventualBG` and the
trivial "BG rose over the last 15 min" trend, and cannot even reach 90% sensitivity. `hi30` (upper
band) cries wolf (FA 0.47 at 95% catch) — the expected control, mirroring `lo60` on the downside.

## Why — the Twin's value is ASYMMETRIC (descent-only), and this is physical

A **fall** depends on hidden state — insulin on board and the trajectory — which the physiological
filter tracks better than oref's crude forward projection; that is why the floor beat oref. A **rise**
is just glucose going up, already visible in the recent CGM trend to every predictor equally (the
20-min observability wall, `TWIN_VS_V6_DETECTION.md`). There is no hidden state to infer on the way
up, so the Twin adds nothing the trend does not already give — and the trend, being direct, has fewer
false alarms.

## Verdict

**The rise-retiming brick is a NO-GO *as a Twin signal*.** Do not ship a `fc30`/`hi30` rise shadow —
it is dominated by the trivial trend baseline, so banking it would only add noise (matched-baseline
rule). If rise-timing is ever pursued, it belongs to the incumbent's **existing** confirm-timing
levers (early-dosing audit: confirm-gate over-block fix, age-gate −1 — already in the register), not
to KAIROS.

**Net effect on the program:** the Twin's single validated, differentiated, buildable contribution is
the **descent floor** (idea-4 withdrawal). One brick, not two. That is the honest ceiling: KAIROS is
a descent sensor that lets a proven reactive core give back insulin earlier on the way down — where
the recoverable variance actually lives — and nothing more that the data will support.
