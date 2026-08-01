package app.aaps.core.keys

import app.aaps.core.keys.interfaces.BooleanPreferenceKey

enum class BooleanKey(
    override val key: String,
    override val defaultValue: Boolean,
    override val calculatedDefaultValue: Boolean = false,
    override val defaultedBySM: Boolean = false,
    override val showInApsMode: Boolean = true,
    override val showInNsClientMode: Boolean = true,
    override val showInPumpControlMode: Boolean = true,
    override val dependency: BooleanPreferenceKey? = null,
    override val negativeDependency: BooleanPreferenceKey? = null,
    override val hideParentScreenIfHidden: Boolean = false,
    override val engineeringModeOnly: Boolean = false,
    override val exportable: Boolean = true
) : BooleanPreferenceKey {

    GeneralSimpleMode("simple_mode", true),
    GeneralSetupWizardProcessed("startupwizard_processed", false),
    OverviewKeepScreenOn("keep_screen_on", false, calculatedDefaultValue = true),
    OverviewShowTreatmentButton("show_treatment_button", false, defaultedBySM = true, hideParentScreenIfHidden = true),
    OverviewShowWizardButton("show_wizard_button", true, defaultedBySM = true),
    OverviewShowInsulinButton("show_insulin_button", true, defaultedBySM = true),
    OverviewShowCarbsButton("show_carbs_button", true, defaultedBySM = true),
    OverviewShowCgmButton("show_cgm_button", false, defaultedBySM = true, showInNsClientMode = false),
    OverviewShowCalibrationButton("show_calibration_button", false, defaultedBySM = true, showInNsClientMode = false),
    OverviewShortTabTitles("short_tabtitles", false, defaultedBySM = true),
    OverviewShowNotesInDialogs("show_notes_entry_dialogs", false, defaultedBySM = true),
    OverviewShowStatusLights("show_statuslights", true, defaultedBySM = true, hideParentScreenIfHidden = true),
    OverviewUseBolusAdvisor("use_bolus_advisor", true, defaultedBySM = true),
    OverviewUseBolusReminder("use_bolus_reminder", true, defaultedBySM = true),
    OverviewUseSuperBolus("key_usersuperbolus", false, defaultedBySM = true, hideParentScreenIfHidden = true),
    OverviewUseBoostOverview("use_boost_overview", false, defaultedBySM = true),
    OverviewUseBoostOverviewV2("use_boost_overview_v2", false, defaultedBySM = true),

    PumpBtWatchdog("bt_watchdog", false, showInNsClientMode = false, hideParentScreenIfHidden = true),

    AlertMissedBgReading("enable_missed_bg_readings", false),
    AlertPumpUnreachable("enable_pump_unreachable_alert", true),
    AlertCarbsRequired("enable_carbs_required_alert_local", true),
    AlertUrgentAsAndroidNotification("raise_urgent_alarms_as_android_notification", true),
    AlertIncreaseVolume("gradually_increase_notification_volume", true),

    BgSourceUploadToNs("dexcomg5_nsupload", true, defaultedBySM = true, hideParentScreenIfHidden = true),
    BgSourceCreateSensorChange("dexcom_lognssensorchange", true, defaultedBySM = true),

    ApsUseDynamicSensitivity("use_dynamic_sensitivity", false),
    ApsUseAutosens("openapsama_useautosens", true, defaultedBySM = true, negativeDependency = ApsUseDynamicSensitivity), // change from default false
    ApsUseSmb("use_smb", true, defaultedBySM = true), // change from default false
    ApsUseSmbWithHighTt("enableSMB_with_high_temptarget", false, defaultedBySM = true, dependency = ApsUseSmb),
    ApsUseSmbAlways("enableSMB_always", true, defaultedBySM = true, dependency = ApsUseSmb), // change from default false
    ApsUseSmbWithCob("enableSMB_with_COB", true, defaultedBySM = true, dependency = ApsUseSmb), // change from default false
    ApsUseSmbWithLowTt("enableSMB_with_temptarget", true, defaultedBySM = true, dependency = ApsUseSmb), // change from default false
    ApsUseSmbAfterCarbs("enableSMB_after_carbs", true, defaultedBySM = true, dependency = ApsUseSmb), // change from default false
    ApsUseUam("use_uam", true, defaultedBySM = true), // change from default false
    ApsSensitivityRaisesTarget("sensitivity_raises_target", true, defaultedBySM = true),
    ApsResistanceLowersTarget("resistance_lowers_target", true, defaultedBySM = true), // change from default false
    ApsAlwaysUseShortDeltas("always_use_shortavg", false, defaultedBySM = true, hideParentScreenIfHidden = true),
    ApsDynIsfAdjustSensitivity("dynisf_adjust_sensitivity", false, defaultedBySM = true, dependency = ApsUseDynamicSensitivity), // change from default false
    ApsAmaAutosensAdjustTargets("autosens_adjust_targets", true, defaultedBySM = true),
    ApsAutoIsfHighTtRaisesSens("high_temptarget_raises_sensitivity", false, defaultedBySM = true),
    ApsAutoIsfLowTtLowersSens("low_temptarget_lowers_sensitivity", false, defaultedBySM = true),
    ApsUseAutoIsfWeights("openapsama_enable_autoISF", false, defaultedBySM = true),
    ApsAutoIsfSmbOnEvenTarget("Enable alternative activation of SMB always", false, defaultedBySM = true),   // profile target

    // Boost
    ApsBoostEnablePercentScale("enableBoostPercentScale", false, defaultedBySM = true),
    ApsBoostEnableCircadianIsf("enableCircadianISF", false, defaultedBySM = true),
    ApsBoostAllowWithHighTt("enableBoost_with_high_temptarget", false, defaultedBySM = true),
    ApsBoostUseTdd("boost_use_tdd", false, defaultedBySM = true),
    ApsBoostAdjustSensitivity("boost_adjust_sensitivity", false, defaultedBySM = true),
    ApsBoostAllowAllBgSources("boost_allow_all_bg_sources", true, defaultedBySM = true),
    ApsBoostNightModeEnabled("boost_night_mode_enabled", false, defaultedBySM = true),
    ApsBoostNightModeDisableWithCob("boost_night_mode_disable_with_cob", false, defaultedBySM = true),
    ApsBoostNightModeDisableWithLowTt("boost_night_mode_disable_with_low_tt", false, defaultedBySM = true),
    // Sleep detection hybrid (2026-06-02): when on, sleep state (HR + steps + clock) drives
    // night mode in HYBRID with the existing time window. PRE_SLEEP also engages night-mode
    // SMB suppression early so the user doesn't carry excess IOB into the night.
    ApsBoostNightModeAutoBySleep("boost_night_mode_auto_by_sleep", false, defaultedBySM = true),

    // Health Connect HR ingest (2026-06-03) — bridge for overnight HR from Garmin/Wear OS via Android Health Connect
    ApsBoostHealthConnectHrEnabled("boost_health_connect_hr_enabled", false, defaultedBySM = true),
    ApsBoostBypassVersionCheck("boost_bypass_version_check", true, defaultedBySM = true),
    // Boost V5 active-dosing alpha (2026-06-11) — when ON, V5's observe-confirm-commit SMB REPLACES
    // V1's SMB on cycles V1 permits one. V1 still owns basal + all safety gates. Toggle OFF = instant revert.
    // DEPRECATED 2026-06-15: V5 is now a selectable APS plugin ("Boost V5"); selecting it IS
    // "V5 active". No longer read/surfaced. Kept only so existing stored prefs don't error.
    ApsBoostV5ActiveDosing("boost_v5_active_dosing", false, defaultedBySM = true),
    // V6 anticipatory pre-meal low target (2026-06-15) — when ON, the loop applies the learned
    // pre-meal low target live ~45-60 min before a habitual meal. Default OFF = shadow (logs
    // "V6 pre-meal WOULD apply" to reason for validation; no dosing change). See MealTimeLearner.
    ApsBoostV6PreMealTarget("boost_v6_pre_meal_target", false, defaultedBySM = true),
    // 2026-06-16 fast-carb fast-path — single-cycle OBSERVING/IDLE→CONFIRMED on a sharp, accelerating,
    // score-corroborated rise while awake & not exercising. Replay-validated (backtesting/replay.py).
    // Default ON (it's the fix for the 2026-06-16 fast-carb crash); toggle OFF = instant revert.
    ApsBoostV5FastCarbConfirm("boost_v5_fast_carb_confirm", true, defaultedBySM = true),
    // 2026-07-17 aggressive early-confirm — shaves the sustained-score early-confirm path one more
    // cycle (age −2). The pre-push backtest showed ~28% of its candidates are fizzle-catches (new
    // insulin at ~base rate), so it is NOT a clean cohort default; it is OPT-IN and AUTO-CONFIG
    // MANAGED (BoostV5AutoConfig enables it only for clearly well-controlled users). Default OFF.
    ApsBoostV5AggressiveEarlyConfirm("boost_v5_aggressive_early_confirm", false, defaultedBySM = true),
    // 2026-07 composed Phase-3 brake floor (F = 0.25) — when ON (and V6 is the active doser), the
    // delivered dose is floored at min(budget × 0.25, committedCapU) on meal-session high cycles
    // (CONFIRMED/COMMITTED/RECOVERING ∧ BG > 160 ∧ eventualBG > target+20 ∧ awake ∧ not post-rescue ∧
    // budget > 0) — fixes the soft-brake stack compounding to sub-pump-step zero doses mid-meal
    // (Episode B). Default OFF; PER-USER activation gated on trailing-14d time-below-range being
    // within consensus targets (TBR<70 < 3.5%, <54 < 0.8%) — the 2026-07 re-review excluded cohort
    // users B/C/D whose TBR would cross those absolutes. All hard gates/caps still apply.
    ApsBoostV5ComposedFloorActive("boost_v5_composed_floor_active", false, defaultedBySM = true),
    // 2026-07-17 velocity-budget floor — when ON (and V6 active), the delivered dose is floored at
    // min(0.5U, committedCapU) on the budget≈0 high tail (BG > 180 ∧ oref insulinReq ≈ 0 ∧ not
    // RECOVERING ∧ awake ∧ not post-rescue), and the cycle is exempted from the non-meal seam cap so
    // it can out-dose V1 (V1 also doses ~0 there). It deliberately overrides a prediction that was
    // right-by-outcome on shadow data, so it is PER-USER opt-in AND gated on the SAME fail-closed
    // 14d-TBR gate as the composed floor (TBR<63 < 2.0% ∧ TBR<70 < 3.5%). committedCap + maxIOB
    // bounded; all Phase-3 hard gates + cumulative/boost-active/sleep seam guards still apply.
    // Default OFF. Field driver: user H "postprandial highs" — his budget=0 tail (55% of his >180).
    ApsBoostV5VelocityBudgetActive("boost_v5_velocity_budget_active", false, defaultedBySM = true),
    // 2026-07-20 V1-acceleration primer — hypo-prone routing (AUTO-CONFIG MANAGED). When ON,
    // auto-config has classified the user hypo-prone and routes the early primer through a
    // RETRACTABLE temp-basal instead of a bolus (safe-by-unwinding rather than safe-by-size).
    // OFF (default) = bolus primer (well-controlled). Overridable by ApsBoostV5PrimerBolusMode.
    ApsBoostV5PrimerTbrFallback("boost_v5_primer_tbr_fallback", false, defaultedBySM = true),
    // 2026-07-20 V1-acceleration primer — USER OVERRIDE (NOT auto-config-managed). When ON, forces
    // the bolus primer even if auto-config routed this user to the temp-basal fallback
    // (ApsBoostV5PrimerTbrFallback). Default OFF = respect the auto-config routing. Floors + net-off
    // are unaffected by the override; it only changes bolus-vs-temp-basal delivery.
    ApsBoostV5PrimerBolusMode("boost_v5_primer_bolus_mode", false, defaultedBySM = true),
    // LEGACY (2026-06-26..2026-07): global auto-config one-shot flag. Superseded by per-knob
    // BooleanComposedKey.BoostV5AutoConfigResolved; kept only so existing installs migrate
    // (OpenAPSBoostV5Plugin reads it raw once, marks tuned knobs resolved, then clears it).
    ApsBoostV5AutoConfigDone("boost_v5_autoconfig_done", false, defaultedBySM = true),
    ApsBoostPostExerciseRecoveryEnabled("boost_post_exercise_recovery_enabled", false, defaultedBySM = true),
    // Activity-load SHADOW (2026-06-16) — when ON, Boost reads HC steps, learns a personal daily-step
    // baseline, and LOGS what an activity/inactivity ISF modifier WOULD do (shadow; never doses).
    // Default ON but inert until READ_STEPS is granted in Health Connect.
    ApsBoostActivityShadowEnabled("boost_activity_shadow_enabled", true, defaultedBySM = true),
    // Autosens / TDD-DynISF coordination (2026-06-16). TDD-DynISF and traditional autosens are
    // ALTERNATIVE sensitivity-adaptation mechanisms — never both. When TDD is OFF (profile-anchored
    // DynISF curve), this lets traditional oref autosens drive basal/target/CR sensitivity instead of
    // the curve ratio (which is not a sensitivity signal). Requires ApsUseAutosens enabled to do
    // anything. Default OFF = legacy behaviour preserved; the oref-vs-curve comparison is logged as
    // shadow telemetry regardless, so it can be validated before flipping ON. No effect when TDD is ON.
    ApsBoostAutosensWhenNoTdd("boost_autosens_when_no_tdd", false, defaultedBySM = true),
    ApsBoostHrIntegrationEnabled("boost_hr_integration_enabled", false, defaultedBySM = true),
    ApsBoostHrStressDetection("boost_hr_stress_detection", false, defaultedBySM = true),

    MaintenanceEnableFabric("enable_fabric2", true, defaultedBySM = true, hideParentScreenIfHidden = true),

    MaintenanceEnableExportSettingsAutomation("enable_unattended_export", false, defaultedBySM = false),

    AutotuneAutoSwitchProfile("autotune_auto", false),
    AutotuneCategorizeUamAsBasal("categorize_uam_as_basal", false),
    AutotuneTuneInsulinCurve("autotune_tune_insulin_curve", false),
    AutotuneCircadianIcIsf("autotune_circadian_ic_isf", false),
    AutotuneAdditionalLog("autotune_additional_log", false),

    SmsAllowRemoteCommands("smscommunicator_remotecommandsallowed", false),
    SmsReportPumpUnreachable("smscommunicator_report_pump_unreachable", true),

    VirtualPumpStatusUpload("virtualpump_uploadstatus", false, showInNsClientMode = false),
    NsClientUploadData("ns_upload", true, showInNsClientMode = false, hideParentScreenIfHidden = true),
    NsClientAcceptCgmData("ns_receive_cgm", false, showInNsClientMode = false, hideParentScreenIfHidden = true),
    NsClientAcceptProfileStore("ns_receive_profile_store", true, showInNsClientMode = false, hideParentScreenIfHidden = true),
    NsClientAcceptTempTarget("ns_receive_temp_target", false, showInNsClientMode = false, hideParentScreenIfHidden = true),
    NsClientAcceptProfileSwitch("ns_receive_profile_switch", false, showInNsClientMode = false, hideParentScreenIfHidden = true),
    NsClientAcceptInsulin("ns_receive_insulin", false, showInNsClientMode = false, hideParentScreenIfHidden = true),
    NsClientAcceptCarbs("ns_receive_carbs", false, showInNsClientMode = false, hideParentScreenIfHidden = true),
    NsClientAcceptTherapyEvent("ns_receive_therapy_events", false, showInNsClientMode = false, hideParentScreenIfHidden = true),
    NsClientAcceptRunningMode("ns_receive_running_mode", false, showInNsClientMode = false, hideParentScreenIfHidden = true),
    NsClientAcceptTbrEb("ns_receive_tbr_eb", false, showInNsClientMode = false, engineeringModeOnly = true),
    NsClientNotificationsFromAlarms("ns_alarms", false, calculatedDefaultValue = true),
    NsClientNotificationsFromAnnouncements("ns_announcements", false, calculatedDefaultValue = true),
    NsClientUseCellular("ns_cellular", true),
    NsClientUseRoaming("ns_allow_roaming", true, dependency = NsClientUseCellular),
    NsClientUseWifi("ns_wifi", true),
    NsClientUseOnBattery("ns_battery", true),
    NsClientUseOnCharging("ns_charging", true),
    NsClientLogAppStart("ns_log_app_started_event", false, calculatedDefaultValue = true),
    NsClientCreateAnnouncementsFromErrors("ns_create_announcements_from_errors", false, calculatedDefaultValue = true, showInNsClientMode = false),
    NsClientCreateAnnouncementsFromCarbsReq("ns_create_announcements_from_carbs_req", false, calculatedDefaultValue = true, showInNsClientMode = false),
    NsClientSlowSync("ns_sync_slow", false),
    NsClient3UseWs("ns_use_ws", true),
    OpenHumansWifiOnly("oh_wifi_only", true),
    OpenHumansChargingOnly("oh_charging_only", false),
    XdripSendStatus("xdrip_send_status", false),
    XdripSendDetailedIob("xdripstatus_detailediob", true, defaultedBySM = true, hideParentScreenIfHidden = true),
    XdripSendBgi("xdripstatus_showbgi", true, defaultedBySM = true, hideParentScreenIfHidden = true),
    WearControl(key = "wearcontrol", defaultValue = false),
    WearWizardBg(key = "wearwizard_bg", defaultValue = true, dependency = WearControl, hideParentScreenIfHidden = true),
    WearWizardTt(key = "wearwizard_tt", defaultValue = false, dependency = WearControl, hideParentScreenIfHidden = true),
    WearWizardTrend(key = "wearwizard_trend", defaultValue = false, dependency = WearControl, hideParentScreenIfHidden = true),
    WearWizardCob(key = "wearwizard_cob", defaultValue = true, dependency = WearControl, hideParentScreenIfHidden = true),
    WearWizardIob(key = "wearwizard_iob", defaultValue = true, dependency = WearControl, hideParentScreenIfHidden = true),
    WearCustomWatchfaceAuthorization(key = "wear_custom_watchface_autorization", defaultValue = false),
    WearNotifyOnSmb(key = "wear_notifySMB", defaultValue = true),
    WearBroadcastData(key = "wear_broadcast_data", defaultValue = false),
    WizardCalculationVisible("wizard_calculation_visible", defaultValue = false),
    WizardCorrectionPercent("wizard_correction_percent", defaultValue = false),
    WizardIncludeCob("wizard_include_cob", defaultValue = false),
    WizardIncludeTrend("wizard_include_trend_bg", defaultValue = false),
    SiteRotationManagePump("site_rotation_manage_pump", defaultValue = false),
    SiteRotationManageCgm("site_rotation_manage_cgm", defaultValue = false),

    // Export destination settings
    ExportAllCloudEnabled("export_all_cloud_enabled", defaultValue = false),
    ExportLogEmailEnabled("export_log_email_enabled", defaultValue = true),
    ExportLogCloudEnabled("export_log_cloud_enabled", defaultValue = false),
    ExportSettingsLocalEnabled("export_settings_local_enabled", defaultValue = true),
    ExportSettingsCloudEnabled("export_settings_cloud_enabled", defaultValue = false),
    ExportCsvLocalEnabled("export_csv_local_enabled", defaultValue = true),
    ExportCsvCloudEnabled("export_csv_cloud_enabled", defaultValue = false),

}