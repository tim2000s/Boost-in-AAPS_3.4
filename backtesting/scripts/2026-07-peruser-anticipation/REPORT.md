# Per-user vs cross-user anticipation of exercise and meals (2026-07-27)

Our prediction work used cross-cohort splits (GroupKFold by user). That is the correct test for
a *physiological* signal — does it generalise across people. But meal and exercise *timing* is
habitual and idiosyncratic, so cross-user pooling cannot see a held-out person's routine and
will understate how anticipatable these events are. This measures the gap. Predict onset within
45 min from **habit features only** (time-of-day, day-of-week, weekend, minutes-since-last,
onsets-in-prior-24h — no glucose). Per-user uses an honest temporal split (train past, test
future).

## Result

| Event (45-min lead) | Cross-user (GroupKFold) | Per-user (temporal) | winner |
|---|---|---|---|
| **Exercise onset** | AUC 0.672 | **median 0.779** (all 8 users 0.72–0.83) | **per-user, decisively** |
| **Meal onset** | AUC 0.724 | median 0.683 (well-powered users 0.73–0.75; thin-data users collapse) | mixed |

## Reading

**Exercise: per-user is decisively better (+0.11 AUC, every single user beats the cross-user
pool).** Exercise timing is idiosyncratic — some walk mornings, some evenings — so a cross-user
model cannot learn the held-out person's routine, and per-user must. This confirms the intuition
and re-derives, freshly and out-of-sample, the earlier habit-prior finding.

**Meals: not a clear per-user win — and the reason is instructive.** Meal timing is far more
*universal* (nearly everyone eats breakfast / lunch / dinner at similar clock times), so the
cross-user model already captures most of the structure (0.724). Per-user matches or slightly
beats it **only for users with enough history** (0.73–0.75 for the four with 550–1,100 test
meals); for thin-data users it overfits and collapses (one user at 0.37 on 14 test events),
dragging the per-user mean below cross-user. So for meals the answer is data-volume-dependent.

## What this means for the anticipation levers

- **Exercise protection (Lever 2): build it per-user.** The habit model reaches AUC ~0.72–0.83
  at a 45-min lead — genuinely useful for pre-positioning — and cross-user pooling was leaving
  ~0.11 AUC on the table. Cross-user is the wrong tool here.
- **Meal anticipation (Lever 1): use a hybrid.** A cross-user prior (meal times are semi-
  universal; gives a warm start and covers thin-data users) with per-user adaptation layered on
  once enough history accrues. Pure per-user overfits the low-data users; pure cross-user leaves
  the well-characterised users' idiosyncrasies unused.
- **Gate per-user models on event count** — fall back to the cross-user prior below a minimum
  (the 14-event collapse is the cautionary case).

## Caveats (load-bearing)

- **Accuracy is not the safety mechanism.** AUC 0.72–0.83 still false-alarms often at any useful
  operating point. Anticipatory dosing is made safe by **retractability** (the back-out
  controller), not by prediction accuracy — per-user models reduce false arms, they do not
  license un-retractable action.
- **Non-stationarity.** The temporal split shows past→future works *now*, but habits drift
  (weekends, travel, seasons). A per-user model must update online within guardrails — this is
  the "learn the person" reframe: anticipatory adaptation, not a frozen policy.
- **Small-n honesty.** Per-user samples are tiny for some users; report per-user CIs and never
  let a thin-data user carry a conclusion.

## Methodological correction

Our "signal digging is dry / no meal precursor / rich signals hurt" conclusion was answering the
*cross-user, short-horizon, reactive* question and remains correct **for that question**. It does
**not** bound the anticipation question, which is per-user and longer-horizon, and where habit
features reach materially useful AUC. The two must be scoped separately; do not cite the reactive
null to dismiss anticipation.

*Reproduce: `peruser_vs_crossuser.py` (DB refreshed to t=now). 45-day window; exercise excludes
the no-step-feed user.*
