# Pre-meal exercise mode: the published protocols, the existing machinery, and a build

Research note, 2026-09-03.

## Summary

Exercise close to a meal is where automated insulin delivery fails people most often. The published
guidance on what to do about it is specific: raise the glucose target one to two hours ahead, reduce
the meal bolus by somewhere between a quarter and three quarters, leave brief intense work alone,
and stop the loop putting back the insulin it has just withheld.

Almost all of that machinery already exists here, wired to other triggers. The missing piece is a
way for someone to say exercise is coming and carry the four quantities the protocols depend on:
when it starts, what kind, how hard, how long. A temporary target carries a value, a duration and a
reason chosen from six, and it begins the moment it is set.

Whether that trigger should be a person or a detector is settled by one contrast. Announced exercise
with a reduced bolus, announced with a full bolus, and unannounced gave 2.0, 7.0 and 13.0 per cent
time below 3.9 mmol/L. Nothing in the detection literature separates two strategies by that much,
and a trial of automatic detection from wearable data could not be told apart from simply asking the
person to confirm.

None of this has been measured in the field. Sections 1 to 5 cover the guidance, the machinery that
exists, and what has already been measured here. Section 6 describes what would be built, which logs
its decisions and delivers nothing until a pre-registered within-person trial says otherwise.

Three decisions were taken before any of this was written and they bound what follows. The trigger
is a declaration, meaning the person tells the loop exercise is coming; detection appears below only
as the question of what happens when nobody declares, which turns out to be the harder half. Levers
are taken from the published corpus rather than derived, with EXTOD treated as central alongside the
Riddell consensus and the AID-specific position statement. And nothing doses. The mode logs what it
would have done, across the cohort, before any of it reaches the dose path.

The programme's hard rules apply unchanged: absolute time-below-range floors sit under every
statistical decision and can only tighten, no dosing change ships without the two-test bar and a
pre-registered within-user trial, and nothing trains or infers online where a dose is decided.

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
cover automated insulin delivery (AID).

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

### 1.8 Points of agreement and disagreement

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

### 1.9 Specified values against available mechanisms

This table states what the corpus specifies and names the mechanism that already exists, or
does not. Section 6.6 takes the same rows and says what promotion would change in each.

| Protocol lever | Specified value | Boost mechanism | Exists today? |
|---|---|---|---|
| Raise glucose target 1-2 h before | AID 2025 level A; e.g. 8.3 mmol/L |  1  with  2  | Yes,  3 , currently only fired after exercise |
| Reduce pre-exercise meal bolus | EXTOD 50%; Riddell 25-75%; AID 25-33% | Meal state multiplier in  4 , or the confirmed/committed caps in  5  | Multiplier exists and is live; no exercise-conditioned path into it |
| Order: target first, then bolus cut | AID 2025 | Requires the target to be set before the meal is detected, so the target write must precede  6  | Both exist; the ordering does not |
| Reduce basal 50-80% from 60-90 min before | EXTOD 50% at 60 min; Riddell 50-80% at 60-90 min | Activity profile percent,  7   8  | Yes, live, but only triggered by measured steps |
| No reduction for anaerobic or high intensity | All three |  9  already distinguishes  10  from aerobic subclasses | Classifier exists; a declaration would supply the type directly |
| Suppress the loop's response to the resulting rise | AID 2025 rationale | The high-TT Boost defeat at  11  already disables the ladder on a high target | Yes, as a side effect rather than by design |
| Carbohydrate top-ups by trend | EXTOD table; AID 3-20 g | Not a dosing lever; would be a user prompt | No prompting mechanism |
| Stop the raised target at the end of activity | AID 2025 level C |  12 , already used for the recovery target | Yes,  13  |
| Post-exercise: 20% overnight basal for 6 h | EXTOD 50-50-20; Riddell 20% for 6 h | Post-exercise recovery window and  14  | Partly: window and dose scale exist, default off, and the tail measured here is flat at ~1.2x |
| Reduce the next meal's bolus by ~50% | EXTOD, Riddell | Same meal multiplier path as the pre-exercise cut | Multiplier exists; no post-exercise conditioning on it |
| Do not exercise after a severe hypo in 24 h | EXTOD | Not a dosing lever; the composed brake and TBR floors act on the same risk | Related machinery exists, different purpose |

## 2. The existing machinery

Read from the code on the vehicle branch rather than from notes. Where a claim is about live versus shadow, the
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

The dosing consequence is at `OpenAPSBoostPlugin.kt:1243`. Profile percent scales insulin sensitivity factor (ISF) inversely
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
entire Boost supplementary microbolus (SMB) ladder when it fires. It excludes the INACTIVE branch. It sets `V5Inputs.asleep`
at line 1607, which gates the fast-carb confirm path. The night-mode master flag
(`ApsBoostNightModeEnabled`) defaults false, so out of the box `isInNightSleepPeriod()` returns
false on its first line, but `detectorAsleep` and the night-window test are read regardless of
that flag.

### 2.4 The activity ISF shadow, and its one side effect

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

### 2.5 Temporary targets as a template

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
`allowBoostWithHighTt` is set. And `SMBDefaults.exercise_mode` is hardcoded false, so the the OpenAPS reference algorithm (oref)
high-target-raises-sensitivity branch in `DetermineBasalBoost.kt:491` never fires; there is no
plugin-level exercise mode of any kind.

### 2.6 Signals present at decision time

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
whenever Boost V6 is the selected automated pancreas system (APS).

Insulin on board reaches the V6 decision as `V5Inputs.iob` alongside `maxIob` and
`baseInsulinReq`. Carbohydrate on board does not. There is no `cob` field in `V5Inputs`; carbohydrate on board (COB)
reaches V6 only folded into `baseInsulinReq` and `eventualBg` by the V1 engine. COB is directly
available in the V1 engine as `mealData.mealCOB` at `OpenAPSBoostPlugin.kt:1153` and is read in
`DetermineBasalBoost.kt` and by the night-mode test. Any pre-meal mode that wants to condition on
Carbohydrate on board in V6 would have to thread a new field.

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

## 3. The established constraints

Five things constrain the design. All are measured on this cohort unless stated, with the
participant as the resampling unit.

### 3.1 Two populations, with opposite requirements

Post-meal glucose and post-meal-exercise glucose separate people into two groups that do not
overlap. One spends 24 to 37 per cent of post-meal time above 180 mg/dL (10.0 mmol/L) with
post-meal lows at or near zero; exercise helps them, knocking down a peak they have the glucose to
spare. The other shows little post-meal high but exercise tips them low, at 6, 9 and 14 per cent of
post-meal-exercise time below 70 mg/dL (3.9 mmol/L). They have no buffer, so the drain runs straight
through the floor.

The people who need more meal insulin are therefore not the people who need exercise protection, and
a single setting cannot serve both. Any pre-exercise lever has to be per person.

### 3.2 Insulin on board at onset moves lows in the ordinary direction

More insulin on board when exercise starts is associated with more lows. Standardised by each
person's own total daily dose and resampled by participant, this reaches an area under the curve of
0.549 (95 per cent interval 0.512 to 0.604) on 157 events from five participants, every participant
above 0.5, with median insulin on board of 1.76 U where a low followed against 1.36 U where none
did.

The effect is small and the interval is narrow but above chance. Standardisation is not optional:
total daily dose in this cohort spans 16.3 to 57.6 U, a factor of 3.5, and at least one participant
doses in U200 where a unit carries roughly twice the mass. Pooling absolute units inverts the
association.

### 3.3 The clock is the strongest timing signal available

A plain hour-of-day rate, fitted on a person's other days, predicts their exercise onset at an area
under the curve of 0.662 to 0.694 pooled, with 0.764 for the best-served participant at a
60-minute lookahead. That is the strongest per-user timing signal measured anywhere in this
programme, and in absolute terms it is still a weak classifier: about 30 per cent of a person's
activity falls in their three busiest hours, so a clock-driven mode would be absent for most
sessions and present for many non-sessions.

Any timing claim has to be measured against the clock rather than against nothing. A per-user
anticipation model was tested that way and lost at every lookahead, on every interval, and is not
part of this design.

### 3.4 Reactive withdrawal is close to break-even, and worse if run earlier

Withdrawing insulin on measured activity is already live: the active predicate drops profile percent
to 80. Priced against outcomes it prevented 41 of 220 lows at the cost of 39 new highs, a ratio of
about 1.05, and only 26 per cent of activity bouts with insulin on board went low at all. Per
participant the ratio runs from 2.0 down to one person for whom it was pure cost.

Running the same withdrawal earlier makes it worse rather than better: 0.78 at a 30-minute lead and
0.70 at 60. That is this programme's own measurement of exactly the trade the literature recommends,
and it does not reproduce the literature's optimism. It is the single most important number for
anyone designing a pre-exercise lever here.

### 3.5 Two signal-level limits

Rolling 24-hour step load carries no reliable information about insulin sensitivity: a
matched-insulin forward-low ratio of 1.06 and an autosens correlation of -0.06. Heart rate shows no
lift before a glucose rise across 37,000 paired cycles; its only real coupling is heart rate up
followed by glucose down at about ten minutes, which is a concurrent exercise signal rather than an
anticipatory one.

The post-exercise recovery tail is real and modest, about 1.2 times baseline hazard and flat from
zero to five hours, which puts the shipped two-hour window roughly in the right place.

## 4. The declaration

The person tells the loop that exercise is coming. That is the whole of it, and keeping it to that
is a design decision rather than a simplification.

### 4.1 One question, three answers

A dialog reachable from the phone and the watch, asking a single thing: what sort of exercise, with
three answers.

| Answer | Meaning |
|---|---|
| Aerobic | continuous work, a run, a ride, a swim |
| Mixed | intervals, a class, team sport, anything that alternates |
| Anaerobic | lifting, sprints, brief maximal effort |

No start time, no intensity, no expected duration. Each of those is deliberately absent, and the
reasons differ.

Intensity goes because Riddell's table separates a 25 per cent bolus reduction from a 75 per cent
one on intensity and duration together, a threefold spread resting on two numbers people estimate
poorly about themselves. EXTOD declines the distinction and gives a flat 50 per cent, which is the
honest reading of the same evidence.

Duration goes because the loop can observe it. A self-reported expected length is a guess made
before the event; the step feed is a measurement made during it. The mode does not need to be told
when the session ends when it can see it end.

Start time goes because a declaration is made when someone thinks of it, not on a schedule, and
asking for a time invites either a wrong answer or no declaration at all. What matters for the
protocols is the lead, and the lead is whatever the person gives by declaring when they do. The AID
statement wants one to two hours, EXTOD wants sixty minutes, and this programme's own measurement
prices a 60-minute lead at 0.70 lows prevented per high caused, so the evidence for a long lead is
weaker here than the guidance suggests. Acting from the moment of declaration and letting the person
choose the lead is both simpler and closer to what the data supports.

The cost of dropping these is real and should be stated. Without a declared start, the mode cannot
distinguish a declaration made ninety minutes ahead from one made as the person walks out of the
door, so it treats both the same. Whether that costs anything is one of the things the shadow is for.

### 4.2 The undeclared case

Declaration will be forgotten, and the protocols say what to do then. The AID statement's strategy
for unplanned activity is to raise the target at onset, accept that it works less well, and expect
to need more carbohydrate. Neither it nor Riddell proposes detecting the exercise and acting as
though it had been declared.

Nor does the evidence here support doing so. The reactive withdrawal that already handles this case
prices at roughly break-even and gets worse when run earlier, a habit prior loses to the plain hour
of day, and a trial of an automated insulin delivery system adjusting from wearable data could not
be distinguished from one that asked the person to confirm.

So the undeclared case keeps exactly what it has today: the reactive step withdrawal, unchanged. A
declaration does not suppress it, extend it or alter it. That is a deliberate choice to change one
thing at a time, and whether the two should interact is a question for after the shadow has run.

## 5. The mode's behaviour

The three answers do different things, and one of them does the opposite of the other two.

### 5.1 Aerobic

The glucose target rises to 8.3 mmol/L (150 mg/dL) from the moment of declaration. That is the AID
statement's level A recommendation and the cheapest lever available: the mechanism exists, it
already retracts itself, and raising a target withholds insulin gradually rather than cutting it.
Raising it also disables the aggressive dosing ladder through an interlock that already exists,
which delivers the statement's requirement that the loop should not put the insulin back.

If a meal is detected while the mode is active, the meal dose is halved. That is EXTOD's flat figure
and it is the lever with the strongest evidence behind it, because the difference between announcing
exercise with a reduced bolus and announcing it with a full one is 2.0 against 7.0 per cent time
below 3.9 mmol/L.

The ordering matters and is the only sequencing work in the build. The target raise has to be in
place before the meal is recognised, so the write must precede the meal-hypothesis step. Both
operations exist today and neither currently runs before the other.

### 5.2 Mixed

The same target raise, and a quarter off the meal dose rather than a half. Riddell's guidance for
intermittent work sits between the continuous and resistance rows, and the honest position is that
nothing in this programme's own data distinguishes mixed from aerobic. It is a separate answer
because people describe their exercise that way, and because a shadow that collapses it into aerobic
can never find out whether it should have been separate.

### 5.3 Anaerobic

This one runs the other way. Anaerobic effort raises glucose, which is why EXTOD's third lever is
advice about ordering: put the sprint work first, because it lifts you before the aerobic work pulls
you down. Every protocol exempts it from bolus reduction, and Riddell recommends no reduction at all
above about 80 per cent VO2max.

So there is no target raise and no meal reduction. What the mode does instead is stop the loop
chasing the rise: correction dosing into an exercise-driven climb is suppressed for the duration.

That is worth stating plainly because it is the opposite of hypoglycaemia protection and it is
protecting against the same outcome. A loop that sees a catecholamine-driven rise and doses for it
puts insulin in that lands after the session ends, when sensitivity is elevated and the rise has
reversed on its own. Applying a hypoglycaemia protection to the exercise type that raises glucose
would be the obvious error; chasing the rise is the less obvious one, and it is the one an automated
system will make.

### 5.4 Ending, for all three

The mode stands down when the step feed has been quiet for fifteen minutes, or after a hard ceiling
of three hours, whichever comes first. The raised target is cancelled through the existing path, and
the post-exercise recovery window then runs as it does today.

It also stands down if nothing ever starts. If no activity is detected within ninety minutes of the
declaration, the mode gives up and says so, because the failure mode of a declared system is someone
who declares and then does not go.

### 5.5 Deliberate exclusions

No basal reduction. EXTOD asks for a 50 per cent cut from sixty minutes before, and this programme's
own measurement of withdrawing insulin on activity prices it at roughly break-even and worse when
run earlier. That contradiction is not resolved by a declaration, so the gentler and reversible
target raise is kept and the basal cut is left to the reactive path that already runs.

No reduction of the next meal's bolus. Both EXTOD and Riddell ask for roughly half, and the
post-exercise tail measured here is about 1.2 times baseline hazard and flat from zero to five
hours, which does not support a second reduction on top of the recovery window already in place.

No carbohydrate prompting. Both protocols ask for top-ups by trend, there is no prompting mechanism,
and that stays with the person.

## 6. Proving it and enabling it

### 6.1 Shadow first, and what it records

Nothing above doses on the day it ships. The mode computes what it would have done on every cycle
and writes it, and it does that across the cohort for as long as it takes to accumulate paired
observations.

Written once per declaration: an identifier, when it was made, which of the three answers was given,
and the route it arrived by. That is all the person supplies, so that is all there is to record.

The lead time is measured rather than declared, and it becomes one of the more interesting outputs.
The gap between a declaration and the first detected activity onset is what people actually give
when nobody asks them for a number, and nobody knows what that distribution looks like. If it turns
out to cluster at five minutes, the protocols' one to two hours is unreachable by this route and the
design has to be reconsidered.

Written every cycle: the state of the mode, minutes since the declaration, minutes since or until
the detected onset, the target and meal multiplier it would have applied, and what the loop actually
did on the same cycle, which is the counterfactual anchor. Alongside those, the observations needed
to say later whether the exercise happened at all: steps at 5, 15, 30 and 60 minutes with their
source, heart rate with its classification, sleep state, the meal state and its age, insulin on
board both absolute and as a share of that person's total daily dose, and the hour of day.

It runs on every cycle whether or not a declaration exists, because the undeclared cycles are the
comparison set. Logging only declared sessions would leave no way to price a missed declaration.

### 6.2 The bar for promotion

Three things, in order.

The declaration has to be usable. For each declaration, whether measured activity followed it at all
and how long after, using the step-onset definition the analysis scripts already use; and for each
measured onset, whether a declaration preceded it. Those two give the false-positive and
false-negative rates of the declaration itself, which nobody has measured and which decide what
fraction of exercise this path would ever reach. A mode that catches a third of sessions is worth
building; one that catches a twentieth is not.

The three answers also have to be worth separating. If aerobic and mixed produce indistinguishable
outcomes there is no case for two of them, and if anaerobic declarations turn out to be rare enough
that nothing can be said about them, the arm that suppresses correction is unproven rather than
useful.

The outcome has to move in the right direction. Time below 70 mg/dL (3.9 mmol/L) in the three hours
from onset is the primary measure, with time below 54 (3.0) second because the kill-switches key on
it. The cost side is measured on the same events or the result cannot be read: time above 180 (10.0)
and 220 (12.2) over the same window, reported as prevented against caused with a bootstrap interval.
The reactive withdrawal this sits alongside prices at about one low prevented per high caused, and
anything that does not clearly beat that has not earned promotion.

It has to survive a pre-registered within-person trial. Cross-user comparison on a cohort this size
is hypothesis-generating, and the two populations in section 3.1 have opposite requirements, so a
pooled effect would average them.

Powering is a live constraint. A tighter onset definition cut a previous analysis from 686 events to
157 across five participants, and a declared-exercise shadow sees only the sessions somebody
remembered to declare, so it sees fewer still. How long that takes should be estimated from the
observed declaration rate in the first fortnight rather than assumed.

### 6.3 Enabling

The switch is managed by the auto-configuration that already derives per-user settings, rather than
shipped off for every person to discover.

Its gate needs stating rather than copying. The convention's strict time-below-range cut exists to
keep insulin-adding features away from people already running low. This feature withholds insulin,
so that cut is the wrong test and what it has to be priced against is time above range. A tightening
and a loosening do not need to clear the same bar, and applying the symmetric one here would be the
error the convention warns about.

The sequence is: the declaration dialog and the shadow ship together and are available to anyone;
the mode auto-enables for a person only once their own shadow data shows they declare often enough
for it to matter and their outcome measures support it; and anyone can enable or disable it by hand
at any point regardless.

### 6.4 The build, piece by piece

| Piece | Where it goes | New? |
|---|---|---|
| Declaration dialog | beside the existing temporary-target dialog | yes, one question and three buttons |
| Declaration record | a JSON blob in a new settings key, as the sleep and meal-time histories already are | follows the pattern |
| Per-cycle shadow | beside the activity-load shadow, which already computes and logs without dosing | follows the pattern |
| Telemetry out | a tag appended to the reason string, parsed in the extractor | follows the pattern |
| Target raise on promotion | the existing insert-and-cancel call, fired from the declaration instead of after exercise | one call site |
| Meal reduction on promotion | the existing meal multiplier, with an exercise-conditioned path into it | one call site |
| Correction suppression, anaerobic | the high-target ladder defeat already used for a raised target | reuses an interlock |
| Stand-down on a quiet step feed | the step windows already blended for the activity predicate | reads an existing signal |

The telemetry rides in the reason string rather than on the result object because one added field
there costs one register in every engine's decision function, and the largest has none to spare: a
build carrying a single extra field crashed at startup, with no stack trace, because it happens
before the app starts.

### 6.5 Residual uncertainty

The lever with the strongest external grading is the one this programme's own data likes least.
Raising the target one to two hours ahead carries level A; withdrawal at a 60-minute lead prices
here at 0.70 lows prevented per high caused against 1.05 for the reactive path already shipping.
Building the declaration does not settle that disagreement, and the shadow exists because it is
unsettled.

Tier speculative throughout. None of it has been measured in the field.

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
