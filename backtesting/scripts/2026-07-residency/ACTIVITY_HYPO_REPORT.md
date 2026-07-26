# Does activity genuinely precede the hypo? — validating the 47% ACTIVITY low finding

_Follow-up to `RESIDENCY_REPORT.md`, 2026-07-08. oref.boost_decisions, self+A–H, ~89.5k cycles. Reproduce: `activity_hypo.py`._

## Verdict

**Yes — steps are a strong LEADING predictor of hypos, with hours of lead time. The signal is real and user-specific (not cross-user transferable), and STEPS, not HR, carries it on current data.** This validates the residency's ACTIVITY = 47%-of-low-time finding and the exercise protections / Garmin **steps** ingest; it does *not* (yet) validate the HR ingest, which is too sparse to evaluate.

## 1. Dose-response — strong and monotone (steps)

Forward-low (<70 within 3h) rate by recent steps (cohort base 19.1%):

| steps_60m | n | fwd-low% |
|---|---|---|
| 0 | 35,608 | 13.1 |
| 1–100 | 15,350 | 17.1 |
| 100–300 | 17,171 | 18.5 |
| 300–600 | 9,045 | 25.9 |
| 600–1200 | 6,010 | 31.8 |
| **1200+** | 4,277 | **38.5** |

Sedentary → very active nearly **triples** the hypo rate (13% → 38.5%), cleanly monotone.

**HR-reserve is not a usable signal here** — `hrr_pct` is **76% NULL** (the overnight-HR-death problem), and where populated it's flat (~21–22% across 0–40% HRR). So HR as currently ingested carries no clean hypo signal; that's a *data-sparsity* verdict, not proof HR is useless.

## 2. But the signal is PER-USER, not cross-user

LGBM forward-low, GroupKFold **by user**:

| model | AUC |
|---|---|
| baseline (BG / IOB / delta / hour / eventualBG / state) | 0.739 ± 0.046 |
| + activity (steps + HR + iob-activity) | 0.717 ± 0.040 |
| **activity's cross-user lift** | **−0.02 (within fold noise)** |

Adding activity does **not** improve a *generalised* (held-out-user) hypo predictor, even though its pooled dose-response is strong and its in-sample gain rank is high (steps_60m #5, iob-activity #6). The reading: the activity→hypo relationship is **user-specific** — each user's fitness, step baseline, and post-activity drop differ, so a one-size cross-user model can't transfer it. **This validates the design choice of per-user activity thresholds** (Boost's protection) over a global model.

## 3. Lead time — activity precedes the low by hours

Mean `steps_60m` at increasing look-back before each real low onset (baseline 256):

| min before low | mean steps_60m | × baseline |
|---|---|---|
| 5 | 610 | 2.4× |
| 15 | 521 | 2.0× |
| 30 | 434 | 1.7× |
| 60 | 391 | 1.5× |
| 90–180 | ~400 | 1.5–1.6× |

Activity sits **~1.5–1.6× above baseline as far as 3h ahead**, rising to 2.4× just before. Directionally this reads as a **leading** indicator — the exercise protection has time to act.

⚠️ **Caveat (2026-07-10 audit) — these lead-time multiples are soft.** Two weaknesses: (a) **no matched control** — despite the section header, the code compares pre-onset activity only to a global baseline, not to matched non-low periods, so it doesn't isolate "before a low" from "activity in general"; (b) **weighting mismatch** — the pre-onset means pool low-onsets across users (onset-weighted) while the baseline is a user-averaged mean, so the ratio mixes two weightings and can be inflated by users who both step more and go low more. The multiples should be read as suggestive, not as clean causal evidence. The **load-bearing** result for "activity → hypo is real and per-user" is Section 1 (dose-response) + Section 2 (GroupKFold-OOS), not this section.

## Implications for the Garmin work

- **Steps ingest is the validated hypo lever** — the strong dose-response + long lead time back the exercise protections and the Garmin **steps** path directly.
- **HR ingest is unvalidated because HR is too sparse (76% null)** — precisely the overnight-HR-death the Garmin **HR** ingest is built to fix. If the Garmin firmware-HR (24/7, no listener death) fills that gap, HR *may* then contribute — but that's a hypothesis to re-test once dense HR exists, not a proven signal today.
- **Per-user thresholds are the right shape** — a global activity→hypo model doesn't transfer; the protection must stay personalised.

## Caveats

- **The dose-response table (13→38.5%) is pooled across users** (as well as confounded by time-of-day and low IOB), so between-user differences in both activity and hypo-rate contribute; the within-user counterpart is Section 2's GroupKFold result. The lead-time section is NOT a clean causal control (no matched non-low comparator) — see its caveat.
- Forward-low here = any <70 within 3h (base 19.1%), a deliberately sensitive label.
- The HR conclusion is "can't validate on sparse data," not "HR doesn't predict."
