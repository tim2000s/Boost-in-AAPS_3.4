# The local analysis database


PostgreSQL with TimescaleDB, database `oref`, tables in `public`. Written by the extractor from each participant's Nightscout site and read by everything in `backtesting/`. Generated from the live database rather than maintained by hand, so it reports what is there rather than what was intended.


## Tables


| table | columns | rows | participants | earliest | latest |
|---|---|---|---|---|---|
| `boost_cgm` | 4 | 1,882,825 | 35 | 2025-08-01 | 2026-08-11 |
| `boost_decisions` | 154 | 1,967,058 | 35 | 2025-08-01 | 2026-08-11 |
| `boost_devicestatus_raw` | 5 | 619,404 | 9 | 2025-08-01 | 2026-07-21 |
| `boost_treatments` | 8 | 376,184 | 35 | 2025-06-29 | 2026-08-11 |

## Keys and indexes


| table | index | definition |
|---|---|---|
| `boost_cgm` | `boost_cgm_pkey` | `btree (user_id, ts_utc)` |
| `boost_decisions` | `boost_decisions_pkey` | `btree (user_id, ts_utc)` |
| `boost_decisions` | `boost_decisions_ts_idx` | `btree (ts_utc)` |
| `boost_decisions` | `boost_decisions_user_variant_idx` | `btree (user_id, variant)` |
| `boost_devicestatus_raw` | `boost_devicestatus_raw_pkey` | `btree (user_id, ts_utc)` |
| `boost_treatments` | `boost_treatments_pkey` | `btree (user_id, ns_id)` |
| `boost_treatments` | `boost_treatments_user_ts` | `btree (user_id, ts_utc)` |

None of the `boost_` tables is a hypertable. They are ordinary PostgreSQL tables, indexed on participant and time, in a database that also holds older TimescaleDB hypertables from earlier work: `oref_v1`, `oref_v3`, `multiuser_combined`, `oref_v2`. Nothing in the current analysis depends on TimescaleDB features, so the tables can be read with plain PostgreSQL.


## `boost_decisions`


154 columns over 1,967,058 rows. The fill column is the share of rows where the value is not null, which is the quickest way to see whether a field belongs to an engine generation or a shadow layer that only some participants ran.


### Identity and time


| column | type | fill |
|---|---|---|
| `user_id` | text | 100% |
| `ts_utc` | timestamp with time zone | 100% |
| `ts_epoch` | bigint | 100% |
| `variant` | text | 100% |
| `console_error` | text | 100% |

### Glucose


| column | type | fill |
|---|---|---|
| `cgm_mgdl` | float | 100% |
| `delta_acceleration` | float | 22% |

### The oref suggestion


| column | type | fill |
|---|---|---|
| `sug_current_target` | float | 37% |
| `sug_eventualbg` | float | 100% |
| `sug_insulinreq` | float | 100% |
| `sug_rate` | float | 91% |
| `sug_duration` | float | 91% |
| `sug_cob` | float | 100% |
| `sug_iob` | float | 100% |

### Parsed from the reason string


| column | type | fill |
|---|---|---|
| `reason_dev` | float | 100% |
| `reason_bgi` | float | 100% |
| `reason_minpredbg` | float | 100% |
| `reason_minguardbg` | float | 100% |
| `reason_iobpredbg` | float | 100% |
| `reason_uampredbg` | float | 73% |
| `reason_text` | text | 100% |

### Insulin on board


| column | type | fill |
|---|---|---|
| `iob_iob` | float | 100% |
| `iob_activity` | float | 100% |
| `iob_basaliob` | float | 100% |
| `iob_bolusiob` | float | 63% |
| `iob_netbasalinsulin` | float | 63% |

### Boost, engine-agnostic


| column | type | fill |
|---|---|---|
| `boost_active_top` | boolean | 22% |
| `boost_profile_switch` | float | 19% |
| `boost_tier_top` | text | 18% |
| `fast_carb_protection` | text | 17% |
| `boost_active_console` | boolean | 22% |
| `boost_tier` | text | 18% |
| `v1_units` | float | 28% |
| `boost_steps_feed` | text | 5% |
| `boost_activity_load_steps_today` | float | 8% |
| `boost_activity_load_last_day_steps` | float | 8% |
| `boost_activity_load_baseline_steps` | float | 8% |
| `boost_activity_load_ratio` | float | 8% |
| `boost_activity_load_intraday_ratio` | float | 8% |
| `boost_activity_load_intraday_delta_isf_pct` | float | 8% |
| `boost_activity_load_would_delta_isf_pct` | float | 8% |
| `boost_activity_load_source` | text | 8% |
| `boost_activity_load_steps_source` | text | 7% |

### V5/V6 engine state


| column | type | fill |
|---|---|---|
| `boostv5_active` | boolean | 7% |
| `boostv5_state` | text | 13% |
| `boostv5_finaldose` | float | 13% |
| `boostv5_budget` | float | 12% |
| `boostv5_actionmult` | float | 12% |
| `boostv5_score` | float | 13% |
| `boostv5_age` | float | 12% |
| `boostv5_gatereduction` | text | 12% |
| `boostv5_committedcap` | float | 6% |
| `boostv5_confirmedcap` | float | 6% |
| `boostv5_confirmgate` | text | 5% |
| `boostv5_prospectiveshot` | float | 5% |
| `boostv5_aggressionknob` | float | 5% |
| `boostv5_postrescuewindow` | boolean | 6% |
| `boostv5_floorwouldadd` | float | 0% |
| `boostv5_cumulativecapu` | float | 5% |
| `boostv5_smbvol60min` | float | 5% |
| `boostv5_velocityfactor` | float | 4% |
| `boostv5_doseaftercaps` | float | 4% |
| `boostv5_doseafterbrakes` | float | 4% |
| `boostv5_plateau_trig` | float | 2% |
| `boostv5_plateau_wouldnudge` | float | 2% |
| `boostv5_plateau_bg` | float | 2% |
| `boostv5_plateau_trend` | float | 2% |
| `boostv5_plateau_iob` | float | 2% |
| `boostv5_plateau_floor` | text | 2% |

### Twin shadow forecaster


| column | type | fill |
|---|---|---|
| `boosttwin_fc30` | float | 2% |
| `boosttwin_fc60` | float | 2% |
| `boosttwin_lo60` | float | 2% |
| `boosttwin_hi60` | float | 2% |
| `boosttwin_ra` | float | 2% |
| `boosttwin_gi` | float | 2% |
| `boosttwin_insu` | float | 2% |
| `boosttwin_lo30` | float | 2% |
| `boosttwin_floorbreach` | float | 2% |

### V7 shadow


| column | type | fill |
|---|---|---|
| `boostv7_woulddoser4` | float | 1% |
| `boostv7_woulddoser7` | float | 1% |
| `boostv7_woulddoser10` | float | 1% |
| `boostv7_plow90` | float | 1% |
| `boostv7_q50drift` | float | 1% |
| `boostv7_pool` | text | 2% |
| `boostv7_innovsensfrozen` | float | 2% |

### Machine-learning inputs


| column | type | fill |
|---|---|---|
| `ml_hypo_risk` | float | 7% |
| `ml_meal_likely` | float | 7% |

### Acceleration meal detector shadow


| column | type | fill |
|---|---|---|
| `accelmeal_trig` | integer | 0% |
| `accelmeal_accel` | float | 0% |
| `accelmeal_shortavgdelta` | float | 0% |
| `accelmeal_longavgdelta` | float | 0% |
| `accelmeal_bg` | float | 0% |
| `accelmeal_state` | text | 0% |

### Anticipatory back-out controller shadow


| column | type | fill |
|---|---|---|
| `antbackout_armsrc` | text | 2% |
| `antbackout_state` | text | 2% |
| `antbackout_ra0` | float | 2% |
| `antbackout_ranow` | float | 2% |
| `antbackout_bg0` | float | 2% |
| `antbackout_bgnow` | float | 2% |
| `antbackout_confirmed` | integer | 2% |
| `antbackout_backedout` | integer | 2% |
| `antbackout_trip` | integer | 2% |
| `antbackout_meallikely` | float | 2% |

### Anticipation predictor shadow


| column | type | fill |
|---|---|---|
| `anticip_p_ex` | float | 2% |
| `anticip_p_meal` | float | 2% |
| `anticip_src_ex` | text | 2% |
| `anticip_src_meal` | text | 2% |
| `anticip_ex_arm` | integer | 2% |
| `anticip_ex_conf` | integer | 2% |
| `anticip_ex_bo` | integer | 2% |
| `anticip_meal_arm` | integer | 2% |
| `anticip_meal_conf` | integer | 2% |
| `anticip_meal_bo` | integer | 2% |
| `anticip_mins_ex` | integer | 2% |
| `anticip_mins_meal` | integer | 2% |
| `anticip_n_ex` | integer | 2% |
| `anticip_n_meal` | integer | 2% |

### Sleep detection


| column | type | fill |
|---|---|---|
| `sleep_state` | text | 7% |
| `sleep_learned_onset` | text | 6% |
| `sleep_learned_wake` | text | 6% |
| `sleep_learned_days` | integer | 6% |

### ISF


| column | type | fill |
|---|---|---|
| `sens_normal_target` | float | 22% |
| `variable_sens` | float | 37% |
| `dynamic_isf` | float | 22% |
| `running_dynamic_isf` | boolean | 23% |
| `prediction_isf` | float | 22% |
| `isf_mgdl_for_carbs` | float | 24% |

### Heart rate and activity


| column | type | fill |
|---|---|---|
| `steps_5m` | integer | 22% |
| `steps_15m` | integer | 22% |
| `steps_30m` | integer | 22% |
| `steps_60m` | integer | 22% |
| `hr_avg` | float | 5% |
| `hrr_pct` | float | 5% |
| `hr_zone` | text | 5% |
| `hr_bpm_max5m` | float | 3% |
| `hr_bpm_min5m` | float | 3% |
| `hr_bpm_latest` | float | 6% |
| `hr_bpm_avg5m` | float | 4% |
| `hr_bpm_avg15m` | float | 6% |
| `hr_learned_resting_bpm` | float | 3% |
| `hr_learned_daytime_bpm` | float | 5% |
| `hr_source_resolved` | text | 5% |
| `hr_source_states` | text | 7% |

### Total daily dose


| column | type | fill |
|---|---|---|
| `tdd` | float | 20% |
| `tdd_ratio` | float | 20% |
| `tdd_7d` | float | 20% |
| `tdd_1d` | float | 20% |
| `tdd_24h` | float | 20% |
| `tdd_4h` | float | 20% |
| `tdd_8to4h` | float | 20% |
| `tdd_weighted8h` | float | 20% |
| `tdd_blended` | float | 18% |
| `tdd_adj_factor` | float | 20% |

### Pump and device


| column | type | fill |
|---|---|---|
| `pump_battery` | float | 78% |

## `boost_cgm`


4 columns over 1,882,825 rows.


| column | type | nullable |
|---|---|---|
| `user_id` | text | no |
| `ts_utc` | timestamp with time zone | no |
| `cgm_mgdl` | float | yes |
| `direction` | text | yes |

## `boost_devicestatus_raw`


5 columns over 619,404 rows.


| column | type | nullable |
|---|---|---|
| `user_id` | text | no |
| `ts_utc` | timestamp with time zone | no |
| `created_at` | timestamp with time zone | yes |
| `device` | text | yes |
| `openaps` | jsonb | no |

## `boost_treatments`


8 columns over 376,184 rows.


| column | type | nullable |
|---|---|---|
| `user_id` | text | no |
| `ns_id` | text | no |
| `ts_utc` | timestamp with time zone | no |
| `event_type` | text | yes |
| `bolus_type` | text | yes |
| `insulin` | float | yes |
| `carbs` | float | yes |
| `is_smb` | boolean | yes |
