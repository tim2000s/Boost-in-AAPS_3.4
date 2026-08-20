# What Boost uploads to Nightscout in devicestatus

Every loop cycle the phone posts one devicestatus document to Nightscout. It carries the dosing
decision, the settings the decision was taken under, the sensing that fed it, and a set of read only
shadow channels that log what an unshipped mechanism would have done. This describes that document
as it stands on 2026-08-20.

The authority for the payload is `core/interfaces/src/main/kotlin/app/aaps/core/interfaces/aps/RT.kt`,
which declares 122 fields with a comment on each. Anything absent from that file is either inherited
oref, added by the AAPS uploader, or riding inside the `reason` string. The descriptions below come
from that declaration and from a live document sampled while writing this, not from the analysis
database, whose column names differ.

Uploads go to `/api/v3/devicestatus`. Reading them back through `/api/v1/devicestatus.json` is
supported and is what the extractors use.

## The envelope

| Key | Type | Meaning |
|---|---|---|
| `_id`, `identifier` | string | Nightscout's own identifiers |
| `app` | string | Always `AAPS` |
| `device` | string | `openaps://<manufacturer> <model>`, the uploading handset |
| `date` | int | Cycle time, epoch milliseconds |
| `created_at` | string | Cycle time as ISO 8601 |
| `srvCreated`, `srvModified` | int | When the server received the record, epoch milliseconds |
| `utcOffset` | int | Minutes. Reported as 0 by some builds regardless of locale, so do not rely on it |
| `isCharging` | bool | Handset charging state |
| `uploaderBattery` | int | Handset battery percentage |
| `configuration`, `uploader` | object | Present but commonly empty |

The difference between `srvCreated` and `created_at` is the upload lag, which is the instrument for
telling a site that has stopped from one replaying a backlog. During a replay `created_at` is old
while `srvCreated` is recent.

## Pump

| Key | Meaning |
|---|---|
| `pump.clock` | Pump clock at the cycle |
| `pump.reservoir` | Units remaining |
| `pump.battery.percent` | Pump battery |
| `pump.status.status` | For example `Closed Loop` |
| `pump.extended.Version` | AAPS version, build hash and date, for example `3.4.2.2-c-c995222eb5-2026.08.12` |
| `pump.extended.ActiveProfile` | Name of the active profile |
| `pump.extended.BaseBasalRate` | Current basal rate, U/h |
| `pump.extended.LastBolus`, `LastBolusAmount` | Most recent bolus, local time and units |
| `pump.extended.TempBasalStart`, `TempBasalRemaining` | Active temporary basal |

`pump.extended.Version` is the field to read when asking which build a participant is running, and
it is the only reliable one; the reason text does not carry the build.

## Insulin on board

`openaps.iob` carries `iob`, `basaliob`, `activity` and `time`. The first is total insulin on board
in units, the second the basal component, which is negative when the loop has been withholding.

## The dosing decision

These are the inherited oref fields, unchanged in meaning.

| Key | Meaning |
|---|---|
| `algorithm` | `SMB` or `AMA` |
| `bg`, `tick` | Glucose at the cycle and the signed delta |
| `eventualBG`, `minGuardBG`, `targetBG` | Prediction endpoints and the working target |
| `insulinReq` | Units oref considers required |
| `units`, `deliverAt` | The micro bolus and when it is to be delivered |
| `rate`, `duration` | Temporary basal rate and minutes |
| `COB`, `IOB` | Carbs and insulin on board |
| `sensitivityRatio` | Autosens ratio as a fraction of normal basal |
| `variable_sens`, `isfMgdlForCarbs` | Working sensitivity and the ISF passed to the client |
| `predBGs` | Prediction curves, keyed `IOB`, `ZT`, `UAM` and `COB` |
| `reason` | The human readable decision text, which also carries the Boost tags described below |
| `consoleLog`, `consoleError` | Arrays of diagnostic lines |

`eventualBG` is a control quantity rather than a forecast and should not be read as a prediction.
`minGuardBG` is the smart selected predicted low that the V5 shadow reads.

## Sensitivity and dose sizing

| Key | Meaning |
|---|---|
| `dynamicISF` | Dosing ISF used for the insulin requirement |
| `predictionISF` | Prediction ISF used for the curves |
| `sensNormalTarget` | ISF at normal target glucose |
| `tdd`, `tddRatio` | Blended total daily dose and the ratio of 8 hour weighted to 7 day |
| `runningDynamicIsf` | Whether dynamic ISF is driving this cycle |
| `insulinReqPctEffective` | Effective percentage of the requirement used for dosing |
| `deltaAcceleration` | Curvature of the glucose trace, as a percentage |
| `deviationSensRatio`, `deviationSensSource`, `deviationSensClean`, `deviationSensTotal` | Deviation derived sensitivity, its provenance, and the clean and total counts in the 8 hour window |

## Boost settings and per-user caps

This is the configuration under which the cycle was decided. All of it is emitted every cycle, so a
day's records are sufficient to reconstruct what a participant was running without asking them.

| Key | Meaning |
|---|---|
| `boostV5_aggressionKnob` | The participant's aggression setting |
| `boostV5_committedCap` | Per cycle hold cap in the COMMITTED state, units |
| `boostV5_confirmedCap` | Commit shot cap in the CONFIRMED state, units |
| `boostV5_cumulativeCapU` | Rolling 60 minute cumulative SMB cap, units; zero means disabled |
| `boostV5_smbVol60Min` | SMB volume delivered in the trailing 60 minutes, which is what the cap is compared against |
| `boostActive` | Whether Boost was inside its active window |
| `boostProfileSwitch` | Effective profile percentage after activity adjustment |
| `boostAutosens_mode` | Which mechanism drives basal: `tdd`, `autosens` or `curve` |
| `boostAutosens_orefRatio` | The real oref autosens ratio, 1.0 when autosens is off |
| `boostAutosens_curveRatio` | The legacy dynamic ISF curve ratio |
| `boostAutosens_appliedRatio` | The ratio actually applied |
| `boostActivityLoad_baselineSteps` | The participant's median daily step count |

The three autosens ratios are emitted together deliberately, because which one binds is a
configuration question and reading only the applied value cannot answer it.

## Boost engine state

| Key | Meaning |
|---|---|
| `boostTier` | Which tier fired, for example `REGULAR_OREF1`, `ENHANCED_OREF1`, `UAM_BOOST` |
| `boostV5_state` | `IDLE`, `OBSERVING`, `CONFIRMED`, `COMMITTED` or `RECOVERING` |
| `boostV5_age` | Cycles spent in the current state |
| `boostV5_score` | Meal signal score, 0 to 1 |
| `boostV5_budget` | Aggression budget, units |
| `boostV5_actionMult` | Action multiplier for the current state |
| `boostV5_active` | True when V5 was the acting doser rather than a shadow |
| `boostV5_confirmGate` | `pass`, `blocked` or `n/a` for the dose adequacy gate |
| `boostV5_prospectiveShot` | The prospective confirm shot the gate compares against the floor |
| `boostV5_postRescueWindow` | True inside a post rescue window, where the meal state exemption is suppressed |
| `fastCarbProtection` | Whether fast carb rebound protection suppressed the UAM and acceleration tiers |

The dose chain is reconstructible stage by stage, which is what makes an offline port checkable
against the handset: the raw shot is budget times action multiplier, then `boostV5_velocityFactor`
and the state cap give `boostV5_doseAfterCaps`, then the phase three brake stack gives
`boostV5_doseAfterBrakes`, and the composed floor gives `boostV5_finalDose`.
`boostV5_gateReduction` summarises which gates fired.

## Sensing

Heart rate: `hrBpmLatest` is the reading at the cycle, with `hrBpmAvg5m`, `hrBpmAvg15m`,
`hrBpmMax5m` and `hrBpmMin5m` around it, `hrReadingsCount15m` for how many arrived, and
`hrSource_resolved` naming the live feed as `garmin`, `worn:<model>`, `hc` or null when the feed has
died. `hrSource_states` lists every source with its freshness and count. Read
`hrBpmLatest` rather than any average when asking whether the sensor was working, because an average
can be null purely because nothing was logged.

Sleep: `sleepState` is `AWAKE`, `PRE_SLEEP` or `SLEEPING`, with `sleepStateEnteredAtMs` and
`sleepEntryReason` recording when and why. The learned window is `sleepLearnedStartMin`,
`sleepLearnedWakeMin`, `sleepLearnedDurationMin` and `sleepLearnedSessionCount`, all circular means
over a 28 day window. `hrLearnedRestingBpm` and `hrLearnedDaytimeBpm` are the deep sleep floor and
the active baseline, the latter feeding the exercise calculations and defaulting until roughly seven
nights have accumulated.

Activity: `boostActivityLoad_ratio` is decay weighted recent load over baseline, with
`boostActivityLoad_lastDaySteps`, `stepsToday`, `intradayRatio` and the two would be ISF deltas.
`boostActivitySource_resolved` names the source owning today's count, `boostActivitySource_states`
gives freshness and coverage per source, and `boostActivitySource_bridge` records any donor bridging
the baseline window.

## Shadow channels

These deliver nothing. They exist so a mechanism can be priced against the record before it is
allowed near the dose path.

| Prefix | What it logs |
|---|---|
| `mlHypoRisk`, `mlRiskScale`, `mlMealLikely` | Probability of a hypo within four hours, the SMB scaling applied, and probability of a rise of 50 mg/dL within 90 minutes |
| `mlPostSmb*` | The same hypo probability at projected post SMB insulin on board, and the extra damping |
| `isfShadow_*` | What an alternative sensitivity ratio would have implied for sensitivity, requirement and micro bolus, with `deltaPct` as the one number summary |
| `boostV7_wouldDoseR4`, `R7`, `R10` | The sizing rule's would dose at three low to high cost ratios. Identical values across the three mean the formulation is still wrong |
| `boostV7_pLow90` | Probability of going below 70 mg/dL within 90 minutes on the undosed projection. Display only, never a permission |
| `boostV7_q50Drift`, `boostV7_pool` | Median 30 minute residual for the active regime pool, and the pool with its sample count |
| `boostVwa_*` | The variable window total daily dose proposal, its projection, expected and delivered units, and the curve it rests on |
| `boostV5_floorWouldAdd`, `boostV5_velocityBudgetWouldAdd` | Units a floor would have added, or did add where the per user toggle is on |

Both `floorWouldAdd` fields carry dual semantics keyed on a per user toggle: with the toggle off the
value is what would have been added and dosing is untouched, with it on the value is the uplift
actually applied. Null means the conditions were not met either way.

## Tags carried inside the reason string

Some telemetry rides as text inside `reason` rather than as its own field, which was done to avoid a
verifier crash in a legacy plugin. Each tag is a comma separated list terminated by a semicolon, and
fields are appended at the end so existing positions stay valid. Older records therefore carry fewer
fields, and a parser must return null past the split length rather than fail.

| Tag | Fields, in order |
|---|---|
| `twin=` | fc30, fc60, lo60, hi60, ra, gi, insU, lo30, floorbreach |
| `accelMeal=` | trig, accel, shortAvgDelta, longAvgDelta, bg, state |
| `prTrial=` | enrolled, arm, cap |
| `plateau=` | plateau detector state, including insulin on board and the floor |
| `antBackout=` | anticipatory back out state, with the two rate of appearance and glucose readings and the confirm and backout flags |
| `anticip=` | per user anticipation probabilities, sources, arm and confirm flags, minutes since onset and banked counts |
| `autocfg=`, `autordv=` | auto configuration summary, and the re-derivation window with what changed |

`prTrial=` is emitted every cycle rather than only when its guard fires, so trial exposure is
countable on days the guard never engaged. The same is true of `accelMeal=`.

## Notes for anyone parsing this

Two extractors read these documents and they do not parse the same set of tags, so a field being
empty in the analysis database is a claim about the extractor rather than about the device. Confirm
by fetching a current record and running the parser against it before concluding a shadow has
stopped.

Decimal separators in `reason` follow the handset locale for some participants, so a European
locale can produce `Dev: -0,1` where the regex expects a full stop. The JSON numeric fields are
unaffected; only the human readable text is.

Record sizes are around 10 to 15 KB, which matters when a site is on a small instance and a
one minute cadence multiplies the write volume by five.
