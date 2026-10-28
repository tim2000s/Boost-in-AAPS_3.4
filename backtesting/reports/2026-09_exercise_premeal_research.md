# Pre-meal exercise mode: evidence base and what Boost already has

Research note, 2026-09-03. Sections 1 to 5 set out what the published guidance recommends
before exercise when a meal is involved, what machinery already exists in the Boost fork, and
what the programme's own measurements say about the problem. Section 6 states how the mode is
built in the app and what each piece costs, since the survey on its own left that unanswered.

Three decisions are already taken and shape what the survey covers. The trigger is user-declared,
so the person tells the loop that exercise is coming, and detection appears below only as the
question of what happens when nobody declares. The levers come from the published corpus rather
than from first principles, with EXTOD treated as central alongside the Riddell consensus and the
AID-specific position statement. And the mode logs what it would have done and delivers nothing,
across the cohort, before anything touches dosing.

The hard rules apply unchanged. Absolute time-below-range floors sit under every statistical
decision and can only tighten. No dosing change ships without the two-test bar and a
pre-registered within-user trial. Nothing trains or infers online in the dose path.

Confidence tiers follow the project convention: SOLID for out-of-sample, interval-backed and
challenged; PROVISIONAL for a single test or an unknown interval; SPECULATIVE for reasoning
or specification with no measurement behind it.

## 1. Published guidance

### 1.1 The 2017 consensus statement

Riddell MC, Gallen IW, Smart CE, Taplin CE, Adolfsson P, Lumb AN, et al. Exercise management in
type 1 diabetes: a consensus statement. Lancet Diabetes Endocrinol 2017; 5(5): 377-390.

The statement is explicit that its numbers are starting points derived from a small published
literature plus the authors' clinical experience, so the whole of it sits at the level of
consensus opinion informed by trials rather than at the level of trial evidence.

The central table for a pre-meal exercise mode is Table 3, the suggested reduction in bolus
insulin dose before exercise, which applies specifically to exercise started within 90 minutes
of eating the meal.

| Exercise intensity | 30 min duration | 60 min duration |
|---|---|---|
| Mild aerobic (~25% VO2max) | -25% | -50% |
| Moderate aerobic (~50% VO2max) | -50% | -75% |
| Heavy aerobic (70-75% VO2max) | -75% | not assessed |
| Intense aerobic or anaerobic (>80% VO2max) | no reduction recommended | not assessed |

The "not assessed" cells are the authors' own note that the intensity cannot usually be
sustained for an hour. The decision tree in Figure 2 of the same paper gives the same range in
compressed form: reduce bolus insulin by 25 to 75 per cent at the meal before exercise
depending on intensity, with 25 per cent for light, 50 per cent for moderate and 75 per cent
for high intensity. The accompanying text states that reducing the bolus by as much as 75 per
cent does not appear to increase ketone production during exercise.

Two conditions attach to the whole table. Bolus reduction is advised only when exercise occurs
within about 120 minutes of the bolus dose, and the magnitude varies with timing, type,
duration and intensity. For brief intense exercise, bolus reduction is not advised at all, and
a conservative correction may be needed if hyperglycaemia develops.

Starting glucose targets are given as five bands with an action for each:

| Starting glucose | Action |
|---|---|
| <5.0 mmol/L (<90 mg/dL) | Ingest 10-20 g glucose; delay exercise until above 5.0 mmol/L |
| 5.0-6.9 mmol/L (90-124 mg/dL) | Ingest 10 g glucose before aerobic exercise; anaerobic and HIIT can start |
| 7.0-10.0 mmol/L (126-180 mg/dL) | Aerobic exercise can start; anaerobic can start but glucose may rise |
| 10.1-15.0 mmol/L (182-270 mg/dL) | Aerobic can start; anaerobic can start but glucose may rise |
| >15.0 mmol/L (>270 mg/dL) | Check ketones; contraindicated at blood ketones >=1.5 mmol/L |

The stated ideal operating range for most people doing aerobic exercise lasting up to an hour
is 7.0 to 10.0 mmol/L (126 to 180 mg/dL), with the note that higher may be acceptable where
added protection against hypoglycaemia is wanted. Anaerobic exercise and interval sessions can
be started lower, around 5 to 7 mmol/L (90 to 126 mg/dL), because glucose tends to hold or
rise. A separate field observation in adolescents put the ideal at 6 to 8 mmol/L (108 to 144
mg/dL).

Carbohydrate intake during exercise, for the hypoglycaemia-prevention columns of Table 1:

| Exercise duration | Low circulating insulin | High circulating insulin |
|---|---|---|
| up to 30 min | 10-20 g if glucose <5.0 mmol/L | 15-30 g may be required |
| 30-60 min | 10-15 g/h low to moderate aerobic; none for anaerobic unless <5.0 mmol/L | up to 15-30 g every 30 min |
| 60-150 min | 30-60 g/h | up to 75 g/h |
| >150 min | 60-90 g/h | 60-90 g/h |

The decision tree also gives a carbohydrate route where the bolus cannot be reduced: roughly
0.5 to 1.0 g per kg body mass per hour of activity, or 20 to 30 g/h as a simpler figure.

For basal insulin the statement recommends that a temporary basal rate reduction should ideally
occur well before exercise starts, up to 90 minutes, and that pump suspension should be limited
to under two hours on rapid-acting pharmacokinetics. After afternoon or evening aerobic
exercise it recommends a roughly 20 per cent overnight basal reduction for six hours from
bedtime, and a roughly 50 per cent reduction in the bolus for the first meal after exercise.

Aerobic exercise lowers glucose, brief intense anaerobic work and high intensity intervals hold
it or raise it, and mixed activity sits between the two. That asymmetry is the reason the table
recommends no reduction at all above about 80 per cent VO2max.

### 1.2 The companion review with the same numbers

Zaharieva DP, Riddell MC. Insulin management strategies for exercise in diabetes. Can J
Diabetes 2017; 41(5): 507-516.

This review restates the same guidance in a form organised by exercise type rather than
intensity, and is the more directly usable table for anything that has to classify what a
person is doing.

Table 2, bolus insulin adjustments for postprandial exercise:

| Exercise type | Meal before, ~30 min exercise | Meal before, ~60 min exercise | Meal after exercise |
|---|---|---|---|
| Aerobic, moderate to vigorous continuous | 25-50% bolus reduction | 50-75% bolus reduction | up to 50% reduction |
| Resistance, weight lifting | no reduction typically | 25-50% reduction | no change |
| Brief intense anaerobic | not applicable, lasts minutes | not applicable | small (~50%) correction if hyperglycaemic |
| Mixed intermittent aerobic and anaerobic | ~25% reduction | ~50% reduction | up to 50% reduction |

The review is careful to say that not all of these have been formally tested. Its Figure 2 gives
the timing rule that matters most here: if exercise starts three or more hours after a meal, no
bolus adjustment is normally made; if it starts one to three hours after a meal, a 50 per cent
bolus reduction is generally required, for aerobic exercise lasting more than 30 minutes. The
text tightens this further, saying bolus reductions are ideally made when exercise is initiated
within 90 minutes of insulin administration.

Its Table 3 sets the basal lead time at 60 to 90 minutes before exercise for a 50 to 80 per
cent reduction, with 100 per cent reduction at onset as the alternative, flagged as likely to
need carbohydrate because insulin levels may not fall fast enough.

### 1.3 CGM-era guidance

Moser O, Riddell MC, Eckstein ML, Adolfsson P, Rabasa-Lhoret R, van den Boom L, et al. Glucose
management for exercise using continuous glucose monitoring (CGM) and intermittently scanned
CGM (isCGM) systems in type 1 diabetes: position statement of the EASD and ISPAD, endorsed by
JDRF and supported by the ADA. Diabetologia 2020; 63(12): 2501-2520.

This statement adds trend-arrow-conditioned actions and stratifies targets by hypoglycaemia
risk. Pre-exercise sensor glucose thresholds for adults are given as below 7.0 mmol/L (126
mg/dL) for low hypoglycaemia risk, below 8.0 mmol/L (145 mg/dL) for moderate risk and below
9.0 mmol/L (161 mg/dL) for high risk as the points at which carbohydrate is taken. During
exercise the target band is 5.0 to 10.0 mmol/L (90 to 180 mg/dL). Carbohydrate for endurance
performance is 30 to 80 g/h, with trend-conditioned top-ups of 10-15 g at a flat arrow, 15-25 g
at a slight fall and 20-35 g at a fall, taken every 15 to 20 minutes.

Its bolus guidance is the same 25 to 75 per cent band, with the caution that exaggerated
reductions should be avoided, and the timing rule that exercise should start when mealtime
insulin is low or about 90 minutes after the last carbohydrate-rich meal.

The important limitation for present purposes is stated repeatedly in the tables: these
recommendations are not applicable to hybrid closed-loop systems. The 2020 statement does not
cover AID.

Adolfsson P, Taplin CE, Zaharieva DP, Pemberton J, Davis EA, Riddell MC, et al. ISPAD Clinical
Practice Consensus Guidelines 2022: Exercise in children and adolescents with diabetes. Pediatr
Diabetes 2022; 23(8): 1341-1372. This repeats the 25 to 75 per cent prandial reduction band at
evidence level D, sets the basal lead time at 90 minutes at the same level, and gives
carbohydrate at 0.5 to 1.0 g/kg/h during aerobic exercise with active bolus insulin, falling to
0.3 to 0.5 g/kg/h beyond two hours post-prandial.

### 1.4 The AID-specific statement

Moser O, Zaharieva DP, Adolfsson P, Battelino T, Bracken RM, Buckingham BA, et al. The use of
automated insulin delivery around physical activity and exercise in type 1 diabetes: a position
statement of the EASD and ISPAD. Diabetologia 2025; 68(2): 255-280. Published simultaneously in
Hormone Research in Paediatrics.

This is the document that speaks directly to the question. Five strategies are given. For
planned activity, set a higher glucose target if a fall or a flat response is expected, or hold
the usual target if a rise is expected. For planned activity within two hours of a meal, reduce
the prandial bolus if a fall is expected. During exercise, watch the sensor trend and take small
amounts of fast-acting carbohydrate if glucose is low. For unplanned activity, set the higher
target immediately at onset. And plan activity for when insulin on board is low.

Three numbers carry a level A grade, which in this statement means supported by trial evidence
rather than consensus. Set the higher glucose target one to two hours before the activity if a
fall in glucose is expected. Maintain it until the end of the activity. Reduce the prandial
bolus by 25 to 33 per cent for meals eaten less than two hours before the activity when a fall
is expected.

The 25 to 33 per cent figure is notably smaller than the 25 to 75 per cent of the pump-era
guidance, and the reason given is that the algorithm is also acting. The statement's ordering is
explicit and is the point most relevant to a pre-meal mode: for planned activity up to two hours
after a meal, the higher glucose target should be set first where possible, and the prandial
bolus reduction performed after that. The rationale is that an AID will otherwise respond to the
rise caused by the carbohydrate and by the reduced bolus, and add back the insulin that was
just withheld.

Setting a higher target at activity onset rather than in advance is graded as consensus D and
described as less likely to be effective. Higher insulin on board is graded level C as a
predictor of hypoglycaemia risk during activity, immediate postprandial activity is graded C as
raising that risk, and the statement notes that the insulin on board an AID displays does not
reflect peak insulin action, which arrives one to two hours after a prandial bolus. Stopping the
higher target at the end of activity is level C.

For unannounced activity the statement says AID may give some protection relative to fixed basal
delivery, but that carbohydrate intake is typically required and to a greater extent than for
planned activity. Most system-specific guidance in the paper is consensus D.

Carbohydrate during activity, if sensor glucose falls below 7.0 mmol/L, is graded by trend: 3-6 g
at a flat arrow, 6-9 g slightly falling, 9-12 g falling, 12-20 g at two or three falling arrows,
with a recheck 20 to 30 minutes later.

### 1.5 The trial the AID guidance rests on

Tagougui S, Taleb N, Legault L, Suppère C, Messier V, Boukabous I, et al. A single-blind,
randomised, crossover study to reduce hypoglycaemia risk during postprandial exercise with
closed-loop insulin delivery in adults with type 1 diabetes: announced (with or without bolus
reduction) vs unannounced exercise strategies. Diabetologia 2020; 63(11): 2282-2291.

Thirty-seven adults, exercise taken 90 minutes after a meal, three arms. Announced to the
closed-loop with a 33 per cent meal bolus reduction, announced with a full bolus, and
unannounced with a full bolus. Time below 3.9 mmol/L during exercise and the following hour was
2.0 +/- 6.2 per cent, 7.0 +/- 12.6 per cent and 13.0 +/- 19.0 per cent respectively. The
conclusion was that announcing plus reducing the bolus cut time in hypoglycaemia against both
alternatives, at the cost of more time in hyperglycaemia.

This is the single most informative result for the present question. Announcing alone was better
than not announcing, and announcing with a bolus reduction was better than announcing alone,
which means the two levers are not substitutes.

Myette-Côté É, Molveau J, Wu Z, Raffray M, Devaux M, Tagougui S, et al. A randomised crossover
pilot study evaluating glucose control during exercise initiated 1 or 2 h after a meal in adults
with type 1 diabetes treated with an automated insulin delivery system. Diabetes Technol Ther
2023; 25(2). Thirteen adults, 60 minutes of cycling at 60 per cent VO2peak, meal bolus reduced
33 per cent and the target raised from 6 to 9 mmol/L. Time below 3.9 mmol/L was 0.2 +/- 0.7 per
cent at the one-hour start and 0.0 +/- 0.0 per cent at two hours, with no hypoglycaemic events
in either condition. Small, but it is the direct evidence that the combined strategy holds at
both timings.

### 1.6 Automatic detection in an AID

Jacobs PG, Resalat N, El Youssef J, Reddy R, Branigan D, Preiser N, et al. Integrating metabolic
expenditure information from wearable fitness sensors into an AI-augmented automated insulin
delivery system: a randomised clinical trial. Lancet Digit Health 2023; 5(9): e607-e617.

Twenty-seven participants, 76-hour two-arm crossover. One arm detected exercise from wearable
fitness data, prompted the user to confirm, and shut insulin off during exercise. The other
adjusted insulin automatically from the same fitness data with no confirmation step. Over the
12-hour in-clinic session, time below 3.9 mmol/L was 1.3 per cent (SD 2.9) for the automatic arm
against 2.5 per cent (SD 7.0) for the prompted arm, not a significant difference; time in range
was 63.2 per cent against 59.4 per cent, also not significant. In the two hours after exercise
mean glucose was 7.3 (1.6) against 8.0 (1.7) mmol/L, p=0.023. Over the full 76 hours both arms
had significantly lower time below range than the run-in period at 2.4 per cent.

The finding to carry forward is a negative one. With about that sample size, an automatic
wearable-driven response was not distinguishable from one that asked the user first. Automatic
detection did not buy a measurable hypoglycaemia advantage over a confirmation prompt.

### 1.7 EXTOD

EXTOD, Exercise for Type One Diabetes, is the UK programme led from Birmingham and Exeter by
Parth Narendran and Rob Andrews. Its structured education programme was developed under the MRC
framework for complex interventions and described in Narendran P, Greenfield S, Troughton J,
Doherty Y, Quann N, Lucas S, et al. Development of a group structured education programme to
support safe exercise in people with Type 1 diabetes: the EXTOD education programme. Diabet Med
2020; 37(6): 945-952. The programme was tested in a pilot randomised controlled trial of 96
participants against an updated DAFNE course, powered to size a definitive trial rather than to
demonstrate an effect, so the evidence status of EXTOD's rules is that they are expert-derived
teaching content delivered inside a programme whose pilot has been run and whose definitive
trial has not.

The numbers below are taken from the EXTOD-branded teaching material authored by Narendran and
Andrews and distributed through the ABCD and DTN-UK education programme (Narendran P, Andrews R.
Exercise and the FreeStyle Libre. ABCD/DTN-UK Flash Glucose Monitoring Education Programme).

EXTOD organises everything around three levers it calls ICE: insulin, carbohydrate and the
ordering of the exercise itself. That third lever has no analogue in the other guidance and no
analogue in an AID system; it is advice to put resistance or sprint work before continuous
aerobic work, or to add sprints, because anaerobic effort raises glucose.

Before exercise, EXTOD asks three questions about the exercise (type, intensity, duration),
three about timing (insulin on board, when the person last ate, morning or afternoon) and three
about glucose (hypoglycaemia in the last 24 hours, the trend over the last hour, the current
value). It divides the day into three insulin states: lowest circulating insulin on waking
before breakfast and the lowest hypoglycaemia risk there, highest risk inside the two-hour
window after fast-acting insulin, and a second low-risk period beyond that window. It flags
greater hypoglycaemia risk for exercise after 16:00.

The insulin rules are deliberately single-valued rather than a matrix.

Meal insulin: if exercising within two hours of quick-acting insulin, reduce the pre-exercise
bolus by 50 per cent, then adjust from the person's own CGM traces. This applies to both
injections and pumps.

Basal on a pump: reduce basal by 50 per cent one hour before starting exercise, and return to
the usual rate at the end of exercise.

Carbohydrate during exercise: start at 60 g/h and move to 30 g/h or to other strategies, taking
something every 20 minutes. The CGM-conditioned table is:

| Sensor glucose | Trend | Action |
|---|---|---|
| <5.0 mmol/L | flat or falling | 15-20 g; stop exercise if at or below 3.9 |
| 5.0-6.1 mmol/L | flat | 15 g |
| 5.0-6.1 mmol/L | falling | 20 g |
| 6.1-6.9 mmol/L | falling | 8 g |
| >7.0 mmol/L | any | no action |

The pre-exercise decision uses the same values with the trend: flat and 5.7 to 6.9 mmol/L means
proceed without extra carbohydrate; falling and 5.7 to 6.9 means take twice the usual amount at
20 and 40 minutes into the session; falling and 7.0 to 9.0 means 15 g at the start. Confirm with
a fingerstick below 6.0 or above 15.0 mmol/L.

After exercise, EXTOD teaches the 50-50-20 rule. Reduce the normal bolus by 50 per cent for the
next two meals. Reduce the normal correction by 50 per cent for the next 12 hours. Reduce the
evening background insulin by 20 per cent if the exercise was after 16:00, lasted more than two
hours, or was high-intensity at any time of day; on a pump that is a 20 per cent basal reduction
for six hours from bedtime.

On recent hypoglycaemia, EXTOD is more restrictive than a dosing algorithm can be: a severe
episode needing assistance in the last 24 hours means do not exercise that day, and a
self-treated episode means do not exercise alone and monitor more often.

### 1.8 Where the protocols agree and where they differ

| Question | EXTOD | Riddell 2017 / Zaharieva 2017 | EASD-ISPAD AID 2025 |
|---|---|---|---|
| Pre-meal bolus cut | 50% flat, within 2 h of the bolus | 25-75% by intensity and duration, within 90 min of the meal | 25-33%, within 2 h of the meal |
| Basal cut lead time on a pump | 50% at 60 min before | 50-80% at 60-90 min before | not the primary lever; target instead |
| Higher target lead time | not framed as a target | not framed as a target | 1-2 h before, level A |
| Carbohydrate during exercise | 60 g/h then 30 g/h, every 20 min | 30-60 g/h, up to 75 g/h at high insulin | 3-20 g by trend when below 7.0 mmol/L |
| Entry glucose | act below 7.0 mmol/L, adjusted by trend | ideal 7-10 mmol/L aerobic, 5-7 mmol/L anaerobic | keep target elevated; carbohydrate below 7.0 mmol/L |
| Anaerobic and high intensity | raises glucose; use ordering as a lever | no reduction above ~80% VO2max | hold usual target when a rise is expected |
| Post-exercise | 50-50-20 rule | 20% overnight basal for 6 h; ~50% cut at the next meal | stop the higher target at the end of activity |

The three agree on the shape. Insulin has to come out before the exercise starts, not at its
onset; the window that matters is the one to two hours after a bolus; anaerobic work is the
exception that needs no reduction; and the effect persists overnight.

They differ on magnitude and on which lever leads, and the differences are explicable rather
than contradictory. EXTOD's flat 50 per cent is a teaching simplification for people adjusting
by hand, given with an explicit instruction to tune it from the person's own traces; it sits in
the middle of Riddell's range and is the value Riddell's own Figure 2 gives for the one to three
hour case. Riddell's matrix is finer but is graded as suggested starting points, with the paper
noting that not all cells have been formally tested. The AID statement's 25 to 33 per cent is
smaller than either because the algorithm is also acting, and this is the one figure of the three
that carries a level A grade and a trial behind it.

On lever ordering the AID statement is the only one that speaks to a closed loop, and it says
something the other two cannot: raise the target first, then cut the bolus, because otherwise
the loop reads the resulting rise as a reason to put the insulin back. Neither the pump-era
guidance nor EXTOD anticipates an algorithm that responds to the intervention.

Best evidenced, in order. The Tagougui 2020 trial of 37 adults is a direct randomised comparison
of announcement plus a 33 per cent cut against announcement alone against nothing, with time
below 3.9 mmol/L of 2.0, 7.0 and 13.0 per cent, and it is the only one of these numbers derived
from a trial of the exact intervention in a closed loop. Riddell's Table 3 cites published
studies per row but the row-level evidence is thin and the authors say so. EXTOD's 50 per cent
has the weakest direct support as a number, though the programme containing it has been
piloted; its value here is that it is the simplest rule that anybody has taught at scale, and
simplicity is worth something when the input is a person declaring an intention.

### 1.9 What the protocols specify, and what Boost could implement it with

This table states what the corpus specifies and names the mechanism that already exists, or
does not. Section 6.6 takes the same rows and says what promotion would change in each.

| Protocol lever | Specified value | Boost mechanism | Exists today? |
|---|---|---|---|
| Raise glucose target 1-2 h before | AID 2025 level A; e.g. 8.3 mmol/L | `insertAndCancelCurrentTemporaryTarget` with `TT.Reason.ACTIVITY` | Yes, `OpenAPSBoostPlugin.kt:1210`, currently only fired after exercise |
| Reduce pre-exercise meal bolus | EXTOD 50%; Riddell 25-75%; AID 25-33% | Meal state multiplier in `MealActionMultiplier.kt`, or the confirmed/committed caps in `V5Inputs` | Multiplier exists and is live; no exercise-conditioned path into it |
| Order: target first, then bolus cut | AID 2025 | Requires the target to be set before the meal is detected, so the target write must precede `MealHypothesis.step` | Both exist; the ordering does not |
| Reduce basal 50-80% from 60-90 min before | EXTOD 50% at 60 min; Riddell 50-80% at 60-90 min | Activity profile percent, `OpenAPSBoostPlugin.kt:1275` `pump.baseBasalRate * profileScale` | Yes, live, but only triggered by measured steps |
| No reduction for anaerobic or high intensity | All three | `HrActivityCalculator.ExerciseState` already distinguishes `RESISTANCE` from aerobic subclasses | Classifier exists; a declaration would supply the type directly |
| Suppress the loop's response to the resulting rise | AID 2025 rationale | The high-TT Boost defeat at `OpenAPSBoostPlugin.kt:712` already disables the ladder on a high target | Yes, as a side effect rather than by design |
| Carbohydrate top-ups by trend | EXTOD table; AID 3-20 g | Not a dosing lever; would be a user prompt | No prompting mechanism |
| Stop the raised target at the end of activity | AID 2025 level C | `cancelCurrentTemporaryTargetIfAny`, already used for the recovery target | Yes, `OpenAPSBoostPlugin.kt:1310` |
| Post-exercise: 20% overnight basal for 6 h | EXTOD 50-50-20; Riddell 20% for 6 h | Post-exercise recovery window and `activeRecoveryScale` | Partly: window and dose scale exist, default off, and the tail measured here is flat at ~1.2x |
| Reduce the next meal's bolus by ~50% | EXTOD, Riddell | Same meal multiplier path as the pre-exercise cut | Multiplier exists; no post-exercise conditioning on it |
| Do not exercise after a severe hypo in 24 h | EXTOD | Not a dosing lever; the composed brake and TBR floors act on the same risk | Related machinery exists, different purpose |

## 2. What the Boost fork already has

Surveyed on branch `dev` at `/Users/timstreet/StudioProjects/Boost-AAPS-core`. Everything below
was read from the code rather than from notes. Where a claim is about live versus shadow, the
deciding line is named.

All of the activity machinery lives in the V1 engine,
`plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSBoost/OpenAPSBoostPlugin.kt`, and runs
identically whether the selected plugin is Boost or Boost V6. The V6 plugin
(`openAPSBoostV5/OpenAPSBoostV5Plugin.kt`, display name "Boost V6") owns no activity logic of
its own; it calls the V1 engine with `v5Active = true`.

### 2.1 Steps are already a live dose input

Four ingest paths write step counts. The phone pedometer feeds an in-memory ring buffer in
`openAPSBoost/StepService.kt`, registered at `app/src/main/kotlin/app/aaps/MainApp.kt:210`. The
AAPS Wear watch and the Garmin watch both write rows to the `SC` table, the latter through
`plugins/sync/.../garmin/GarminPlugin.kt:442` (`onPostSteps`). Health Connect writes daily totals
only, in `openAPSBoost/HealthConnectStepsIngest.kt`, and never reaches `SC`.

`StepService` buckets into five-minute blocks and exposes 5, 10, 15, 30 and 60 minute windows
plus a midnight-anchored daily total. The `SC` row carries the same windows plus 180 minutes. At
`OpenAPSBoostPlugin.kt:718-738` the freshest watch row is blended into the phone counts with
`maxOf` per window.

The classifier predicate is at `OpenAPSBoostPlugin.kt:805`:

```kotlin
val isActive = (activitySteps5  > 0 && recentSteps5Min  > activitySteps5)
    || (activitySteps15 > 0 && recentSteps15Min > activitySteps15)
    || (activitySteps30 > 0 && recentSteps30Min > activitySteps30)
    || (activitySteps60 > 0 && recentSteps60Min > activitySteps60)
```

Default thresholds, from `core/keys/.../IntKey.kt:60` and `DoubleKey.kt:62`, are 420 steps in 5
minutes, 800 in 15, 1200 in 30 and 1800 in 60. An ACTIVE classification sets profile percent to
80, an INACTIVE one to 130, with the inactivity trigger at fewer than 500 steps in 60 minutes.

The dosing consequence is at `OpenAPSBoostPlugin.kt:1243`. Profile percent scales ISF inversely
(`profile.getIsfMgdl(...) / profileScale`) and scales basal directly
(`pump.baseBasalRate * profileScale` at line 1275), and it is passed into the engine as
`profileScale` at line 1427, where it scales the Boost dose terms in `DetermineBasalBoost.kt`.
The activity branches also write min, max and target glucose, guarded so that a user temporary
target always wins.

This is a live, step-driven, bidirectional ISF and basal modifier with no master enable flag.
The withdrawal direction is already built and shipping; what does not exist is any way to invoke
it ahead of the activity.

`openAPSBoost/StepFeed.kt` guards on feed availability and is separately unit-tested. Its
`inactivityEligible(...)` requires the step feed to be present and the person not to be asleep,
in the night window, or in a lie-in, which is the safety asymmetry: the insulin-adding direction
carries more preconditions than the insulin-withholding one.

### 2.2 Heart rate is live but off by default

Garmin `/hr` posts land in the `HR` table via `GarminPlugin.kt:414` and a side-channel path on
`/get` and `/sgv.json`. The AAPS Wear listener and a Health Connect gap-filler write the same
table; the Health Connect path is gated by `ApsBoostHealthConnectHrEnabled`, default false.

`openAPSBoost/HrActivityCalculator.kt` classifies into Karvonen heart-rate-reserve zones
(`NONE` through `ZONE_5_MAX`) and into an exercise state
(`VIGOROUS_AEROBIC`, `MODERATE_AEROBIC`, `LIGHT_AEROBIC`, `RESISTANCE`, `STRESS`, `RESTING`,
`INACTIVE`) with a confidence level. It rejects frozen sensors. It is called at
`OpenAPSBoostPlugin.kt:812`, wrapped in `if (hrIntegrationEnabled)`, where the key is
`ApsBoostHrIntegrationEnabled`, default false.

When it is on, `VIGOROUS_AEROBIC` drops profile percent a further 10 points with a floor at 50
and sets target 150; `RESISTANCE` and `STRESS` set target 160 without touching profile; and a
zone at or above moderate suppresses the INACTIVE insulin raise entirely
(`OpenAPSBoostPlugin.kt:902`). That last branch is a live safety interlock.

Learned baselines come from `openAPSBoost/SleepHistoryTracker.kt`. Resting heart rate is the
median of the per-session tenth percentile during sleep; daytime heart rate is the median of the
per-session daytime tenth percentile. Both are null until at least seven sessions have
accumulated. Both are live: resting feeds the sleep detector at line 2049, daytime feeds the
Karvonen reference for exercise classification at line 822 with a one-cycle lag. They persist in
`ApsBoostSleepHistory`.

`openAPSBoost/HrSourceResolver.kt` and the feed-dark tracker are telemetry and a user
notification, with no dosing consumer.

### 2.3 Sleep state is live and gates the whole Boost ladder

`openAPSBoost/SleepStateDetector.kt` runs a three-state machine, `AWAKE`, `PRE_SLEEP`,
`SLEEPING`, from heart rate against a learned resting floor (sleep cap at 1.15 times resting,
wake floor at 1.25 times), steps in the last 15 and 60 minutes, clock position against a learned
night window, and a meal-likely signal. It is evaluated every cycle at
`OpenAPSBoostPlugin.kt:2064` and persisted in `ApsBoostSleepState`.

Its consequences are live. `boostActive = !isInNightSleepPeriod()` at line 704 disables the
entire Boost SMB ladder when it fires. It excludes the INACTIVE branch. It sets `V5Inputs.asleep`
at line 1607, which gates the fast-carb confirm path. The night-mode master flag
(`ApsBoostNightModeEnabled`) defaults false, so out of the box `isInNightSleepPeriod()` returns
false on its first line, but `detectorAsleep` and the night-window test are read regardless of
that flag.

### 2.4 The activity ISF shadow is genuinely shadow, with one edge

`boost_activity_shadow_enabled` maps to `BooleanKey.ApsBoostActivityShadowEnabled`, default true,
at `core/keys/.../BooleanKey.kt:165`. The block runs at `OpenAPSBoostPlugin.kt:2216-2354` and
every assignment inside it goes to a telemetry field or to the reason string. Nothing touches the
profile, the ISF or the target.

The engine behind it is `openAPSBoost/DailyStepHistoryTracker.kt`: a 28-day window, a minimum of
seven days before a baseline exists, and asymmetric caps of 15 per cent on the ISF-raising
direction against 8 per cent on the insulin-adding direction. It computes both a day-level ratio
against baseline and an intraday ratio against the expected step count by this hour of day, and
logs what each would do to ISF. The intraday form is the closest thing already built to a
within-day activity anticipation signal.

One edge is worth knowing. Turning this shadow off also disables Health Connect step ingest
(`HealthConnectStepsIngest.kt:102`) and removes the daily-total seed at
`OpenAPSBoostPlugin.kt:2247`, which feeds the sleep detector's wake evidence, which gates
`boostActive`. The flag is not fully inert.

### 2.5 Temporary targets: a working template already exists

The persistence surface is `core/interfaces/.../db/PersistenceLayer.kt`, with
`getTemporaryTargetActiveAt`, `insertAndCancelCurrentTemporaryTarget` and
`cancelCurrentTemporaryTargetIfAny` for targets, and the profile-switch equivalents.
`TT.Reason` already includes `ACTIVITY` and `EATING_SOON`.

`OpenAPSBoostPlugin.kt:1173-1233` is a plugin creating an exercise temporary target today. It is
the post-exercise recovery feature, gated by `ApsBoostPostExerciseRecoveryEnabled`, default false.
On the transition out of an exercise state, if the bout lasted long enough, it picks a window
multiplier, a target offset and a dose scale by the exercise subclass:

| Last exercise state | Window multiplier | Target offset mg/dL | Dose scale |
|---|---|---|---|
| VIGOROUS_AEROBIC | 1.25 | 0 | 0.8 |
| RESISTANCE | 1.5 | +10 | 1.2 |
| LIGHT_AEROBIC | 0.5 | 0 | 1.4 |
| other | 1.0 | 0 | 1.0 |

then inserts a `TT` with `reason = TT.Reason.ACTIVITY` only if no temporary target is already
active, and scales `boost_bolus` and `boost_scale` by the recovery factor for the window
(lines 1428-1439). It cancels its own target early when glucose has recovered 20 mg/dL above a
recent low (lines 1304-1323), which is a retraction mechanism already written and tested against
the same target reason a pre-meal mode would use.

Two related facts. A high user temporary target disables Boost outright at line 712 unless
`allowBoostWithHighTt` is set. And `SMBDefaults.exercise_mode` is hardcoded false, so the oref
high-target-raises-sensitivity branch in `DetermineBasalBoost.kt:491` never fires; there is no
plugin-level exercise mode of any kind.

### 2.6 Signals available at decision time

Everything a pre-meal mode would want to read is already assembled each cycle, with one gap.

Steps at 5, 10, 15, 30 and 60 minutes from the phone plus the watch, and 180 minutes from the
watch row; steps today; and the 28-day daily baseline with an expected-by-this-hour figure from
the shadow tracker. Heart rate readings over a configurable window with an average, a Karvonen
zone, an exercise subclass and a confidence, plus learned resting and daytime baselines once
seven nights have accumulated. Sleep state with its entry reason and the learned bedtime, wake
time and session count.

The meal state machine is `openAPSBoostV5/MealHypothesis.kt`, with states `IDLE`, `OBSERVING`,
`CONFIRMED`, `COMMITTED` and `RECOVERING`. `step(...)` is pure and already takes an
`exerciseActive` argument. Its dose consequence is the multiplier in
`openAPSBoostV5/MealActionMultiplier.kt`: 1.0 at idle, 0.3 while observing, 1.8 at confirmed
(times the user aggression knob), 1.0 while committed and 0.4 while recovering. That is live
whenever Boost V6 is the selected APS.

Insulin on board reaches the V6 decision as `V5Inputs.iob` alongside `maxIob` and
`baseInsulinReq`. Carbohydrate on board does not. There is no `cob` field in `V5Inputs`; COB
reaches V6 only folded into `baseInsulinReq` and `eventualBg` by the V1 engine. COB is directly
available in the V1 engine as `mealData.mealCOB` at `OpenAPSBoostPlugin.kt:1153` and is read in
`DetermineBasalBoost.kt` and by the night-mode test. Any pre-meal mode that wants to condition on
carbohydrate on board in V6 would have to thread a new field.

Exercise state already crosses into V6 through `OapsProfileBoost.v5_exerciseActive`,
`v5_inPostExerciseWindow` and `v5_exerciseSubclass`, filled at `OpenAPSBoostPlugin.kt:1467`.
These were dead on the live path from the V6 plugin split until 2026-07-07. Three live consumers
read them: the meal signal score down-weights while exercising
(`MealSignalScore.kt:121`), the fast-carb confirm requires not exercising
(`MealHypothesis.kt:352`), and the aggression budget applies a post-exercise damper
(`AggressionBudget.kt:130`).

One inconsistency is worth recording. `V5_EXERCISE_STATES` at `OpenAPSBoostPlugin.kt:2802`
excludes `STRESS`, while the V6 anticipatory pre-meal target suppression at line 1347 includes
it. The same activity classification therefore means two different things at two points in the
same cycle.

Finally, `openAPSBoostTwin/AnticipationShadow.kt` is present and shadow-only, with an exercise
onset test at more than 150 steps in five minutes, appending to the reason string and delivering
nothing. It is the residue of the anticipation work described in section 3.

## 3. What the programme has already measured

Source: `backtesting/RELATIONSHIPS_REGISTER.md`, plus the study directories it cites. Everything
in this section is Boost's own data, and several of the entries constrain the design more
sharply than the literature does.

### 3.1 The contrast that stands

Meals followed by activity within two hours end in a low below 70 mg/dL 23 per cent of the time
(95% CI 19 to 27); meals not followed by activity, 15 per cent (95% CI 12 to 18). The intervals
do not overlap. Eight users with a step feed, about 30 days to 2026-07-28, in
`backtesting/reports/2026-07_meal_with_and_without_exercise.md`. Tier SOLID. This contrast was
not affected by the later withdrawal described below.

The same report splits the cohort into two populations that want opposite treatment. Four users
spend 24 to 37 per cent of post-meal time above 180 mg/dL with post-meal lows at or near zero;
three spend little time high but 6, 9 and 14 per cent of post-meal-exercise time below 70. A
single cohort-wide pre-meal reduction would help the second group and worsen the first.

Time-in-regime, cohort-pooled over the same window:

| Regime | Share of time | Mean mmol/L | TIR 70-180 | TING 63-140 | <70 | >180 |
|---|---|---|---|---|---|---|
| Background, non-meal | 59% | 6.6 | 93% | 82% | 2.7% | 4% |
| Post-meal, no exercise | 18% | 8.1 | 76% | 54% | 2.4% | 22% |
| Post-meal, with exercise | 23% | 7.7 | 78% | 55% | 4.0% | 18% |

### 3.2 The withdrawn mechanism

On 2026-07-27, `backtesting/scripts/2026-07-postmeal-exercise-mechanism/` reported that people
who went low after post-meal exercise were carrying less insulin, not more: median 0.96 U at
exercise onset against 1.61 U, on comparable boluses (2.40 U against 2.10 U in the first 30
minutes), from a lower glucose (114 against 136 mg/dL), with a monotone tertile gradient of 32,
22 and 18 per cent crash rate across low, mid and high insulin on board. The claim built on that
was that post-meal exercise lows are a carbohydrate-counterweight failure rather than insulin
excess, and that the remedy is anticipatory withdrawal or carbohydrate rather than a smaller
meal dose. It was filed as SOLID on 686 events.

On 2026-08-13, `backtesting/scripts/2026-08-postmeal-exercise-recheck/` withdrew it. The
original figures were pooled across participants in absolute units, and total daily dose in the
cohort spans 16.3 to 57.6 U, a factor of 3.5, with at least one person on U200 where a unit
carries twice the mass. The between-participant correlation of median insulin on board at onset
with that person's own low rate is -0.388, which is enough to invert a pooled association.
Standardising insulin on board by each person's own total daily dose and resampling with the
participant as the unit gives an AUC of 0.549 (95% CI 0.512 to 0.604) on 157 events from five
users, every participant above 0.5, with median insulin on board 1.76 U where a low followed
against 1.36 U where none did. The pooled absolute-unit construction on the same 157 events
gives 0.588 (0.518 to 0.656), also above 0.5.

The corrected finding is the ordinary direction: more insulin on board at exercise onset is
associated with more lows. The effect is small and the interval is narrow but clearly above
chance. What this removes is the argument that reducing the meal dose is the wrong lever. What
survives is only the structural observation that the loop's lever is insulin-out while the
disturbance is exogenous glucose drain, which is reasoning rather than measurement.

The 2026-07 cohort report still carries the withdrawn claim at SOLID and has not been annotated.
Anyone reading it should treat its dose-refutation section as superseded.

### 3.3 Timing signals: the hour of day beats everything built

On 2026-07-27 a per-user anticipation model looked strong. Exercise onset at a 45-minute lead
gave a per-user temporal AUC of 0.779 (all eight users 0.72 to 0.83) against 0.672 for a
cross-user model, and the conclusion was that exercise timing is idiosyncratic and should be
learned per user. The report attached its own caveat, that accuracy is not the safety mechanism
and AUC in that range still false-alarms often at any useful operating point.

On 2026-08-26 that shadow was priced against a plain hour-of-day rate fitted on the same
person's other days, in `backtesting/scripts/2026-08-meal-size-readability/anticipation_exercise.py`,
on ten participants with movement onsets taken from their own step feed:

| Lookahead | Shadow AUC | Hour-of-day AUC | Delta | 95% CI | Participants where shadow won |
|---|---|---|---|---|---|
| +15 min | 0.489 | 0.662 | -0.173 | -0.220 to -0.123 | 0/10 |
| +30 min | 0.553 | 0.673 | -0.121 | -0.163 to -0.073 | 1/10 |
| +60 min | 0.591 | 0.694 | -0.104 | -0.148 to -0.059 | 0/10 |

Every interval excludes zero in the wrong direction. The shadow is discarded. The result that
matters for a pre-meal mode is the control arm rather than the treatment arm: the clock alone
reaches 0.662 to 0.694 for exercise onset, against 0.587 to 0.625 for meal onset in the
companion test, and the best individual figure is 0.764 for one participant at the 60-minute
lookahead. The register rounds that to 0.760, which corresponds to a second participant at the
same lookahead (0.7595); either is defensible as the best-participant figure but the exact
maximum is 0.764. Tier SOLID for the comparison, since it is out-of-sample with participant
clustered intervals and survived being the losing arm of its own test.

That makes the hour-of-day exercise prior the strongest per-user timing signal measured anywhere
in this programme. It is also, on its own, a weak classifier in absolute terms.

### 3.4 Activity withdrawal has been priced and it is close to break-even

`backtesting/scripts/2026-07-v6-activity/FINDINGS.md`, 2026-07-19, verdict MARGINAL. On 837
bouts of activity with insulin on board, 220 went below 70 mg/dL and 68 below 54. A reactive
withdrawal prevented 41 of the 220 lows (19 per cent pooled, 16 per cent per-user median) and 15
of the 68 deep lows, at a cost of 39 new excursions above 180, of which 5 exceeded 220. Prevented
to caused is about 41 to 39. The insulin actually withheld was 0.25 to 0.73 U per bout and the
median lift at the nadir was 6 to 9 mg/dL.

Moving the withdrawal earlier catches more lows and costs more highs, and the ratio gets worse:

| Lead | Lows prevented | Deep lows prevented | New highs | Prevented per caused |
|---|---|---|---|---|
| Reactive | 41/220 (19%) | 15/68 | 39 | 1.05 |
| 30 min early | 111/220 (50%) | 37/68 (54%) | 142 | 0.78 |
| 60 min early | 160/220 (73%) | 59/68 (87%) | 228 | 0.70 |

Only 26 per cent of activity bouts with insulin on board went low at all, which is why the cost
side scales so fast. Per-user the picture separates cleanly: B at 2.0, F at 1.5, E at 1.3 and C
at 1.0 are worth switching on; one user produced 91 bouts, 2 lows and 8 caused highs, pure cost;
another produced 19 bouts, 7 lows and prevented none. The recommendation was not to ship it
blanket and not to build the anticipatory arm. That last point contradicts the direction the
withdrawn mechanism report pointed in, and the register carries neither recommendation.

The lead-time table is the sharpest constraint on any pre-meal mode. It is the programme's own
measurement of exactly the trade being proposed, and at a 60-minute lead, which is what the
literature asks for, it prices at 0.70 lows prevented per high caused.

### 3.5 Related entries

Recent activity is a leading indicator of forward hypoglycaemia per user but not cross-user, with
a dose-response from 13 to 38.5 per cent and steps running 1.5 to 1.6 times baseline up to three
hours before a low. Time of day plus weekday predicts activity at out-of-sample AUC 0.73 to 0.85,
with about 30 per cent of activity falling in a person's top three hours. The post-exercise
recovery tail is real but modest, about 1.2 times baseline hazard and flat from 0 to 5 hours once
the window-length artefact is removed, which puts the shipped 2-hour window roughly in the right
place; the earlier "delayed 2x ramp" figure was that artefact.

Two signal-level nulls constrain what a detector can use. Rolling 24-hour step load carries no
reliable information about insulin sensitivity: matched-insulin forward-low ratio 1.06, residual
slope wrong-signed, correlation with autosens -0.06. Heart rate carries no cephalic lift before a
glucose rise across 37,000 paired cycles, so it is not a meal signal; the only real coupling is
heart rate up followed by glucose down at about a 10-minute lag, which is the exercise signal.
Forward steps predict at AUC 0.62 against 0.55 for glucose plus insulin alone.

On temporary targets the register is nearly silent. There is no entry using the term. The one
adjacent item is filed under unproven and unbuilt: an activity BG-rising override, called Design
9, believed shipped but never coded in any branch, leaving the activity target unguarded. The
only lever language resembling a temporary target is in the cohort report, which proposes a
retractable anticipatory temporary basal reduction that unwinds if the activity does not appear.
That is a specification with no measurement behind it. Tier SPECULATIVE.

Two further items are listed as unproven: that exercise-anticipation preparation helps in
practice, where detection is validated but the dosing benefit needs a shadow log before any
claim, and a multi-day activity-load ISF adjustment in its deviation form, designed but never
built, where only the simplest 24-hour form has been tested and was null.

## 4. The trigger

The trigger is user-declared: the person tells the loop that exercise is coming. This section
covers what a declaration has to carry for the protocol levers to be applied, what the existing
machinery already accepts, and what happens when nobody declares.

### 4.1 What a declaration must carry

The protocol levers in section 1.9 are functions of four things, and none of the four can be
inferred from a temporary target as it exists today.

Lead time is the first, and it is the one with the strongest evidence behind it. The AID
statement grades one to two hours ahead at level A and grades onset-time target raising as
consensus D with the note that it is less likely to work. EXTOD says 60 minutes for a pump basal
cut. Riddell and Zaharieva say 60 to 90 minutes. The programme's own measurement at a 60-minute
lead prices withdrawal at 0.70 lows prevented per high caused, so the lead time is simultaneously
the most-recommended parameter and the one Boost's own data is least comfortable with. A
declaration therefore has to say when the exercise starts, not merely that it is coming.

Exercise type is the second, because it decides the sign of the intervention. Every one of the
three protocols exempts brief intense anaerobic work from bolus reduction, and Riddell's Table 3
recommends no reduction at all above about 80 per cent VO2max. A declaration that does not
distinguish aerobic from anaerobic will apply a hypoglycaemia protection to the exercise type
that raises glucose. Boost already has the vocabulary: `HrActivityCalculator.ExerciseState`
separates `VIGOROUS_AEROBIC`, `MODERATE_AEROBIC`, `LIGHT_AEROBIC`, `RESISTANCE` and `STRESS`,
and the post-exercise recovery feature already branches on that subclass with different window
multipliers and dose scales. A declared type could populate the same field directly instead of
being inferred from heart rate.

Intensity and expected duration are the third and fourth, and they are what select a cell in
Riddell's table. Mild for 30 minutes is 25 per cent; moderate for 60 is 75 per cent. That is a
threefold difference driven entirely by two numbers the loop cannot observe in advance. EXTOD
declines to make the distinction and gives a flat 50 per cent, which is the honest response to
the fact that people estimate their own intensity poorly. If the design follows EXTOD, the
declaration needs only a start time and a type; if it follows Riddell, it needs an intensity and
a duration as well, and both will be self-reported with unknown error.

There is one further field with no protocol basis but a clear operational one: whether the
declaration is retractable and on what evidence. The post-exercise recovery code already
retracts its own target when glucose recovers 20 mg/dL above a recent low
(`OpenAPSBoostPlugin.kt:1304`), which is the pattern.

### 4.2 What the existing machinery already accepts

A declaration can be made today, through five routes, and all of them collapse to the same
narrow payload.

`ui/dialogs/TempTargetDialog.kt` offers Eating Soon, Activity, Hypo and Custom as reasons and
takes a target and a duration. The Activity preset defaults to 140 mg/dL for 90 minutes
(`UnitDoubleKey.OverviewActivityTarget`, `IntKey.OverviewActivityDuration`). The AAPS Wear watch
has the same presets, reaching `DataHandlerMobile.handleTempTargetPreCheck` with
`PRESET_ACTIVITY`, so a one-button declaration from the wrist already exists. The SMS
communicator can set one. Nightscout can sync one. And the Automation plugin has
`ActionStartTempTarget`, which can be fired by `TriggerRecurringTime`, `TriggerTime`,
`TriggerLocation`, `TriggerBTDevice`, `TriggerWifiSsid`, `TriggerStepsCount` or
`TriggerHeartRate`, all of which exist and are shipping.

The payload every one of these produces is a target value, a duration and a reason drawn from a
fixed enum. It carries no start time other than now, no exercise type, no intensity and no
expected duration of the activity as distinct from the duration of the target.

Two details matter for anything built on top. The Automation action writes
`reason = TT.Reason.AUTOMATION` at `ActionStartTempTarget.kt:105`, not `ACTIVITY`, so the
existing Boost auto-cancel at line 1310, which keys on `TT.Reason.ACTIVITY`, will not retract an
automation-created target. And a high temporary target disables the Boost SMB ladder outright at
`OpenAPSBoostPlugin.kt:712` unless `allowBoostWithHighTt` is set. That interlock delivers the AID
statement's "stop the loop adding the insulin back" requirement for free, but it does so by
switching the ladder off wholesale rather than by scaling it, which is a blunter instrument than
the 25 to 33 per cent the statement asks for.

The gap between what a declaration can carry and what the levers need is therefore a payload
gap rather than a plumbing gap. Temporary targets, their cancellation, profile switches, the
per-subclass branch, the recovery window and the dose scaling all exist and all run. Nothing
exists that carries a start time in the future, an exercise type from the person rather than
from the sensors, or an intensity.

### 4.3 The backstop: undeclared exercise

Declaration will be forgotten, and the protocols say what happens then. The AID statement's
fourth strategy is for unplanned activity: raise the target immediately at onset, accept that it
works less well, and expect to need more carbohydrate. Riddell's decision tree routes the
no-bolus-adjustment-possible case to carbohydrate at roughly 0.5 to 1.0 g/kg/h. Neither protocol
proposes detecting the exercise and acting as though it had been declared.

Boost's position on detection is unusually well measured, and it is not encouraging.

Detection from steps is already live and already withdrawing insulin: the ACTIVE predicate at
`OpenAPSBoostPlugin.kt:805` drops profile percent to 80. That is the unannounced case, already
shipping. Its value has been priced. Reactive withdrawal prevented 41 of 220 lows at the cost of
39 new highs, a ratio of about 1.05, and only 26 per cent of activity bouts with insulin on board
went low at all. Per user the ratio ranges from 2.0 down to a user for whom it was pure cost.

Detection run early, which is what a pre-meal mode would need if it were to fire without a
declaration, gets worse rather than better: 0.78 at a 30-minute lead and 0.70 at 60 minutes. That
is the programme's own measurement of exactly the trade the literature recommends, and it does
not reproduce the literature's optimism.

A habit prior as the trigger is ruled out by measurement rather than by argument. The per-user
anticipation shadow was beaten by a plain hour-of-day rate at every lookahead, with every
interval excluding zero in the wrong direction, and is discarded. The hour-of-day rate that beat
it reaches AUC 0.662 to 0.694 pooled and 0.764 for the best participant, which makes it the
strongest per-user timing signal in the programme and still a weak classifier. About 30 per cent
of a person's activity falls in their top three hours, so a clock-triggered mode would be absent
for most sessions and present for many non-sessions.

Two signal-level constraints bound what any detector could use. Rolling 24-hour step load carries
no information about insulin sensitivity (matched-insulin forward-low ratio 1.06, autosens
correlation -0.06). Heart rate shows no lift before a glucose rise across 37,000 paired cycles;
its only real coupling is heart rate up followed by glucose down at about 10 minutes, which is a
concurrent exercise signal rather than an anticipatory one.

The external evidence points the same way. In the Jacobs 2023 trial, an AID that adjusted insulin
automatically from wearable fitness data was not distinguishable from one that detected the same
activity and asked the user to confirm: time below 3.9 mmol/L 1.3 per cent (SD 2.9) against 2.5
per cent (SD 7.0), time in range 63.2 against 59.4 per cent, neither significant on 27
participants. Automatic detection did not beat a confirmation prompt.

Set against that, the announcement result is the strongest in the corpus. Announced with a 33 per
cent bolus cut, announced with a full bolus, and unannounced gave 2.0, 7.0 and 13.0 per cent time
below 3.9 mmol/L. The gap between announcing and not announcing is larger than the gap between
any two detection strategies anyone has published.

So the backstop question is not which detector to build. It is whether the already-live reactive
step withdrawal, which is what currently handles undeclared exercise and which prices at roughly
break-even pooled and strongly per-user, should be left exactly as it is when a declaration path
exists alongside it, and whether a declaration should suppress it, extend it or leave it
untouched. That is a design question and it is not answered here. What can be said from the
measurements is that per-user gating is the only form in which reactive withdrawal has ever
priced positively, and that its lead-time table argues against running it earlier.

The remaining option, retractable after-the-fact detection, is the one the code is best equipped
for and the one with the least evidence. The retraction mechanism exists and is tested: the
recovery target cancels itself when glucose recovers. But nothing in the corpus prices a
retractable anticipatory withdrawal, the cohort report proposes one purely as a specification,
and `2026-07-v6-activity/FINDINGS.md` explicitly recommends against building the anticipatory
arm. Tier SPECULATIVE.

## 5. What the shadow must record

Nothing here touches dosing until it has been logged across the cohort, priced against real
exercise, and taken through the two-test bar and a pre-registered within-user trial. The shadow
is what makes that trial possible, so its field list is determined by what the trial will have to
estimate rather than by what is convenient to log.

### 5.1 What the shadow computes and does not do

Each cycle the shadow decides whether a declared pre-meal exercise mode would be active, and if
so what it would have done to the target and to the meal dose. It writes those as telemetry and
delivers nothing. The template is the existing activity-load shadow at
`OpenAPSBoostPlugin.kt:2216`, which computes a would-be ISF delta and logs it, and whose fields
are already extracted into the decision table. The one lesson from that block is to keep the
shadow free of side effects: it currently also seeds the Health Connect daily total, which means
turning it off changes sleep-detector wake behaviour, which gates dosing.

### 5.2 The declaration record

Written once at declaration and carried on every subsequent cycle until the mode ends: a
declaration identifier, the wall-clock time of the declaration, the declared start time, the
declared exercise type, the declared intensity, the declared expected duration, and the route the
declaration arrived by. Also the lead time actually achieved, which is the declared start minus
the declaration time, because that is the exposure variable the AID statement's level A
recommendation is about and it will vary from the intended value in practice.

### 5.3 Per-cycle fields

The state of the mode, meaning not declared, declared and waiting, in the pre-exercise window,
in the declared exercise period, or in the post-exercise window, plus minutes to or from the
declared start. What the mode would have done, meaning the would-be target in mg/dL, the would-be
meal multiplier or bolus fraction, and which protocol row produced each. What the loop actually
did on the same cycle, which is the counterfactual anchor: the real target, the real dose, and
whether a user temporary target was active and would have overridden the shadow.

Alongside these, everything needed to say later whether the exercise happened and whether the
mode was right. Steps at 5, 15, 30 and 60 minutes, from which source, and the feed availability
label. Heart rate average over the window with the Karvonen zone, the classified exercise state
and the confidence, plus the learned resting and daytime baselines and their session counts.
Sleep state. The meal hypothesis state and its age in cycles, the meal action multiplier, and the
meal signal score. Insulin on board, both absolute and as a fraction of that person's total daily
dose, because the 2026-08-13 recheck showed that the absolute figure inverts a pooled
association. Carbohydrate on board, which means threading `mealData.mealCOB` from the V1 engine
into `V5Inputs`, where it does not currently exist. Glucose, delta and short average delta. The
hour of day, which is the control arm any timing claim will be measured against.

Cadence is the loop cycle, so every five minutes, with the shadow running whether or not a
declaration is present. The undeclared cycles are what the analysis needs as its comparison set;
logging only declared sessions would leave no way to price a missed declaration.

### 5.4 What has to be recorded to price the trigger

A declaration is a claim about the future, so the shadow has to record enough to score it. For
each declaration, whether measured activity followed within a tolerance of the declared start,
using the step-onset definition already used in the analysis scripts (400 steps in the preceding
30 minutes marks an onset, 100 marks quiet), and how far the observed onset fell from the
declared one. For each measured activity onset, whether a declaration preceded it. Those two give
the false-positive and false-negative rates of the declaration itself, which nobody has measured
and which the analysis will need in order to say what fraction of exercise the declared path
would ever reach.

The hour-of-day rate should be logged as a parallel would-have-fired series on the same cycles.
It is the control the anticipation shadow lost to, and any claim that a declaration adds
information over the clock has to be made against it rather than against nothing.

### 5.5 The outcome measure

The primary outcome is time below 70 mg/dL in the three hours from the declared or observed
exercise onset, which matches the horizon already used across the post-meal-exercise analyses
(`LOW_HORIZON_MIN = 180`) and matches the trial literature's exercise-plus-one-hour window
closely enough to be comparable. Time below 54 mg/dL over the same window is the second, because
the programme's kill-switches key on the absolute severe-hypoglycaemia rate.

The cost side has to be measured on the same events or the result is not interpretable. The
activity withdrawal work priced at roughly one low prevented per high caused, and that ratio, not
the lows-prevented count, was what made it marginal. So: time above 180 mg/dL and above 220
mg/dL over the same horizon, and the count of new excursions attributable to a shadow-active
window. Report prevented against caused as a ratio with a bootstrap interval.

Insulin actually withheld per session should be recorded because the earlier work found the
reactive arm was withholding only 0.25 to 0.73 U per bout for a median nadir lift of 6 to 9
mg/dL, which is small enough that a change could look statistically real and be clinically
irrelevant.

Two analysis constraints follow from the corrected finding in section 3.2 and should be fixed
before any data is collected rather than after. Insulin on board must be standardised by each
person's own total daily dose, because the cohort spans 16.3 to 57.6 U with at least one person
on U200 and pooling absolute units inverted a real association. And the participant, not the
event, is the resampling unit, with per-user results reported alongside the pooled figure. The
cohort splits into people who run high after meals and people who go low after post-meal
exercise, and a pooled effect will average two opposite requirements.

Powering is a live constraint rather than an afterthought. The 2026-08 recheck found 157 events
across five users where the 2026-07 run had claimed 686, because a tighter onset definition and a
shorter refresh window removed most of them. A declared-exercise shadow will see fewer events
still, since it sees only the sessions somebody remembered to declare. The shadow needs to run
long enough to produce a per-user event count that supports a within-user comparison, and how
long that is should be estimated from the observed declaration rate in the first weeks rather
than assumed.

## 6. How the mode is built in the app

### 6.1 One session, start to finish

At 17:00 you declare that a moderate aerobic run starts at 18:00 and will last 45 minutes. The
declaration is written once and carries an identifier, the time it was made, the declared start,
the type, the intensity, the expected duration, the route it arrived by, and the lead time it
actually achieved, which is 60 minutes here and will often not be the lead time intended.

From 17:00 the mode reads as being in the pre-exercise window. It computes a target of 8.3
mmol/L. If a meal is detected before 18:00 it computes a reduced meal dose, and the size of that
reduction depends entirely on which protocol row is being followed: EXTOD's flat rule takes half
the dose off, the nearest cell of Riddell's table for moderate work lasting an hour takes off
three quarters, and the AID statement takes off a quarter to a third. That is a threefold spread
for one session, which is why the shadow records the row that produced each number rather than
the number alone. At 18:00 the mode moves to the declared exercise period, and at 18:45 to the
post-exercise window.

Throughout, it writes what it would have done and delivers nothing.

### 6.2 The declaration is the only real new construction

Section 4.2 established that the gap is in what a declaration can carry rather than in the
plumbing behind it. `TT.Reason` holds six values, `CUSTOM`, `HYPOGLYCEMIA`, `ACTIVITY`,
`EATING_SOON`, `AUTOMATION` and `WEAR`, and a temporary target is a target, a duration and one
of those, beginning at the moment it is set. All five declaration routes collapse to that
payload. None of the four quantities the protocols are functions of can be expressed in it.

So the first piece is a dialog beside `ui/dialogs/TempTargetDialog.kt` taking minutes until
start, exercise type, intensity and expected duration. The type should populate the same
vocabulary `HrActivityCalculator.ExerciseState` already uses, separating `VIGOROUS_AEROBIC`,
`MODERATE_AEROBIC`, `LIGHT_AEROBIC` and `RESISTANCE`, so that the post-exercise recovery branch
reads a declared type through the path it already uses for a classified one. Nothing downstream
then needs to know whether a person or a heart-rate classifier supplied it.

The record persists as a JSON blob in a new `StringKey`, following `ApsBoostSleepState` and
`ApsBoostMealTimeHistory`. Blank or corrupt means no declaration, which is both the safe default
and the behaviour every other blob in that file already has.

### 6.3 The shadow sits beside one that already works

The per-cycle shadow belongs next to the activity-load shadow in `OpenAPSBoostPlugin.kt`, which
already computes a would-be ISF delta every cycle, logs it and doses nothing. Its fields are
already extracted into the decision table, so the pattern for getting a shadow from the plugin to
the database is established rather than invented.

That block carries one lesson worth taking with it. It also seeds the Health Connect daily step
total, so disabling it changes sleep-detector wake behaviour, which gates dosing. A shadow with a
side effect is not a shadow. The exercise mode's version computes and writes, and touches nothing
else.

It runs on every cycle whether or not a declaration exists, because the undeclared cycles are the
comparison set. Logging only declared sessions would leave no way to price a missed declaration,
which is the quantity section 5.4 needs and which nobody has measured.

### 6.4 Telemetry rides in the reason string

The state and the would-be numbers leave as a tag appended to `reason`, parsed into columns in
the extractor, in the same way the KAIROS twin forecast, the tranche telemetry and the shadow
hypo-risk score already travel.

This is not a stylistic preference. `RT` is constructed inside `determine_basal` in every engine
in this repository, so one added field costs one register in each of them, and
`DetermineBasalBoostV3MLG3.determine_basal` has no headroom: a build carrying one extra field
crashed at startup on 2026-09-02, measured at 274 registers where 273 runs. The failure produces
no stack trace and no log line, because it happens before the app starts. `RtFieldCountTest` now
fails on any attempt, and the reason string costs nothing.

### 6.5 The switch, and which direction it points

The toggle is managed by `BoostV5AutoConfig` under the 2026-07-17 convention, which means adding
it to `managedBooleanKeys` and `suggestionBoolean` in the plugin together with a derived flag on
`V5Suggestion`, rather than shipping it off for every user to discover.

The auto-enable gate is the part that needs stating rather than copying. The convention's strict
time-below-range cut exists to stop insulin-adding features reaching people who are already
running low. A pre-exercise target raise withholds insulin instead, so that gate is the wrong
one, and the cost it has to be priced against is time above range rather than time below. The
programme's own position is that a tightening and a loosening do not need to clear the same
evidence bar, and this is a case where applying the symmetric bar would be the error.

### 6.6 What promotion would change

Almost nothing, which is the point of building it this way. Every lever in the section 1.9 table
already has a live call site.

| Lever | Call site today | What promotion changes |
|---|---|---|
| Raise the target before exercise | `insertAndCancelCurrentTemporaryTarget` with `TT.Reason.ACTIVITY`, fired only after exercise | Fire it from the declaration instead of from the recovery path |
| End the raised target | `cancelCurrentTemporaryTargetIfAny`, already keyed on `TT.Reason.ACTIVITY` | Nothing; it already retracts |
| Cut the pre-exercise meal dose | `MealActionMultiplier` | Add an exercise-conditioned path into a multiplier that is already live |
| Cut basal before exercise | activity profile percent, driven by measured steps | Let a declaration drive the same scale |
| No cut for anaerobic work | `HrActivityCalculator.ExerciseState` branch | Nothing; the declared type populates the field the branch already reads |
| Stop the loop replacing the insulin | the high-target ladder defeat, unless `allowBoostWithHighTt` | Nothing functionally, though it disables the ladder outright where the AID statement asks for a 25 to 33 per cent scaling |

Two items in that table are not levers and stay out. Carbohydrate top-ups by trend need a
prompting mechanism that does not exist, and the advice against exercising within 24 hours of a
severe hypoglycaemic episode is not a dosing action.

One ordering constraint has no call site and is the only sequencing work in the list. The AID
statement puts the target raise before the bolus reduction, which means the target write has to
precede `MealHypothesis.step`. Both operations exist and neither currently runs before the other.

### 6.7 What is not settled by building this

The lever with the strongest external grading is the one the programme's own data likes least.
Raising the target one to two hours ahead carries the AID statement's level A, and withdrawal at
a 60-minute lead has been priced here at 0.70 lows prevented per high caused, against 1.05 for
the reactive step withdrawal already shipping. Building the declaration path does not resolve
that, and the shadow exists precisely because it is unresolved.

What the declaration route has behind it is the announcement result rather than any lever in
particular: announced with a bolus cut, announced with a full bolus, and unannounced gave 2.0,
7.0 and 13.0 per cent time below 3.9 mmol/L. That gap is wider than the gap between any two
detection strategies in the literature, and it is the reason the trigger is a person rather than
a classifier. Tier SPECULATIVE throughout, since no part of this has been measured in the field.

## References

Adolfsson P, Taplin CE, Zaharieva DP, Pemberton J, Davis EA, Riddell MC, et al. ISPAD Clinical
Practice Consensus Guidelines 2022: Exercise in children and adolescents with diabetes. Pediatr
Diabetes 2022; 23(8): 1341-1372.

Jacobs PG, Resalat N, El Youssef J, Reddy R, Branigan D, Preiser N, et al. Integrating metabolic
expenditure information from wearable fitness sensors into an AI-augmented automated insulin
delivery system: a randomised clinical trial. Lancet Digit Health 2023; 5(9): e607-e617.

Moser O, Riddell MC, Eckstein ML, Adolfsson P, Rabasa-Lhoret R, van den Boom L, et al. Glucose
management for exercise using continuous glucose monitoring (CGM) and intermittently scanned CGM
(isCGM) systems in type 1 diabetes: position statement of the EASD and ISPAD, endorsed by JDRF
and supported by the ADA. Diabetologia 2020; 63(12): 2501-2520.

Moser O, Zaharieva DP, Adolfsson P, Battelino T, Bracken RM, Buckingham BA, et al. The use of
automated insulin delivery around physical activity and exercise in type 1 diabetes: a position
statement of the EASD and ISPAD. Diabetologia 2025; 68(2): 255-280.

Myette-Côté É, Molveau J, Wu Z, Raffray M, Devaux M, Tagougui S, et al. A randomised crossover
pilot study evaluating glucose control during exercise initiated 1 or 2 h after a meal in adults
with type 1 diabetes treated with an automated insulin delivery system. Diabetes Technol Ther
2023; 25(2): 122-130.

Narendran P, Andrews R. Exercise and the FreeStyle Libre. ABCD / DTN-UK Flash Glucose Monitoring
Education Programme teaching slides, EXTOD.

Narendran P, Greenfield S, Troughton J, Doherty Y, Quann N, Lucas S, et al. Development of a
group structured education programme to support safe exercise in people with Type 1 diabetes: the
EXTOD education programme. Diabet Med 2020; 37(6): 945-952.

Riddell MC, Gallen IW, Smart CE, Taplin CE, Adolfsson P, Lumb AN, et al. Exercise management in
type 1 diabetes: a consensus statement. Lancet Diabetes Endocrinol 2017; 5(5): 377-390.

Tagougui S, Taleb N, Legault L, Suppère C, Messier V, Boukabous I, et al. A single-blind,
randomised, crossover study to reduce hypoglycaemia risk during postprandial exercise with
closed-loop insulin delivery in adults with type 1 diabetes: announced (with or without bolus
reduction) vs unannounced exercise strategies. Diabetologia 2020; 63(11): 2282-2291.

Zaharieva DP, Riddell MC. Insulin management strategies for exercise in diabetes. Can J Diabetes
2017; 41(5): 507-516.

Internal: `backtesting/RELATIONSHIPS_REGISTER.md`;
`backtesting/reports/2026-07_meal_with_and_without_exercise.md`;
`backtesting/scripts/2026-07-postmeal-exercise-mechanism/`;
`backtesting/scripts/2026-08-postmeal-exercise-recheck/`;
`backtesting/scripts/2026-07-v6-activity/FINDINGS.md`;
`backtesting/scripts/2026-07-peruser-anticipation/REPORT.md`;
`backtesting/scripts/2026-08-meal-size-readability/anticipation_exercise.py`.
