package app.aaps.core.keys

import app.aaps.core.keys.interfaces.BooleanPreferenceKey
import app.aaps.core.keys.interfaces.StringPreferenceKey

enum class StringKey(
    override val key: String,
    override val defaultValue: String,
    override val defaultedBySM: Boolean = false,
    override val showInApsMode: Boolean = true,
    override val showInNsClientMode: Boolean = true,
    override val showInPumpControlMode: Boolean = true,
    override val dependency: BooleanPreferenceKey? = null,
    override val negativeDependency: BooleanPreferenceKey? = null,
    override val hideParentScreenIfHidden: Boolean = false,
    override val isPassword: Boolean = false,
    override val isPin: Boolean = false,
    override val exportable: Boolean = true
) : StringPreferenceKey {

    GeneralUnits("units", "mg/dl"),
    GeneralLanguage("language", "default", defaultedBySM = true),
    GeneralPatientName("patient_name", ""),
    GeneralSkin("skin", ""),
    GeneralDarkMode("use_dark_mode", "dark", defaultedBySM = true),

    AapsDirectoryUri("aaps_directory", ""),

    ProtectionMasterPassword("master_password", "", isPassword = true),
    ProtectionSettingsPassword("settings_password", "", isPassword = true),
    ProtectionSettingsPin("settings_pin", "", isPin = true),
    ProtectionApplicationPassword("application_password", "", isPassword = true),
    ProtectionApplicationPin("application_pin", "", isPin = true),
    ProtectionBolusPassword("bolus_password", "", isPassword = true),
    ProtectionBolusPin("bolus_pin", "", isPin = true),

    OverviewCopySettingsFromNs(key = "statuslights_copy_ns", "", dependency = BooleanKey.OverviewShowStatusLights),

    SafetyAge("age", "adult"),
    MaintenanceEmail("maintenance_logs_email", "logs@aaps.app", defaultedBySM = true),
    MaintenanceIdentification("email_for_crash_report", ""),
    AutomationLocation("location", "PASSIVE", hideParentScreenIfHidden = true),

    SmsAllowedNumbers("smscommunicator_allowednumbers", ""),
    SmsOtpPassword("smscommunicator_otp_password", "", dependency = BooleanKey.SmsAllowRemoteCommands, isPassword = true),

    VirtualPumpType("virtualpump_type", "Generic AAPS"),

    NsClientUrl("nsclientinternal_url", ""),
    NsClientApiSecret("nsclientinternal_api_secret", "", isPassword = true),
    NsClientWifiSsids("ns_wifi_ssids", "", dependency = BooleanKey.NsClientUseWifi),
    NsClientAccessToken("nsclient_token", "", isPassword = true),

    // Google Drive settings
    GoogleDriveStorageType("google_drive_storage_type", "local"),
    GoogleDriveFolderId("google_drive_folder_id", ""),
    GoogleDriveRefreshToken("google_drive_refresh_token", "", isPassword = true),

    PumpCommonBolusStorage("pump_sync_storage_bolus", ""),
    PumpCommonTbrStorage("pump_sync_storage_tbr", ""),

    // Boost
    ApsBoostStartTime("boost_start_time", "07:00", defaultedBySM = true),
    ApsBoostEndTime("boost_end_time", "07:01", defaultedBySM = true),
    ApsBoostNightModeStart("boost_night_mode_start", "22:00", defaultedBySM = true),
    ApsBoostNightModeEnd("boost_night_mode_end", "07:00", defaultedBySM = true),

    // V5 persisted state (JSON blob: mealHypothesis, age, mlMealLikelyNullStreak)
    ApsBoostV5State("boost_v5_state", "", defaultedBySM = true),

    // V7 shadow residual pools (JSON blob: pending IOB-only projections + regime-conditioned
    // residual samples, ~21-day window). Read/written by V7Shadow every Boost cycle; blank or
    // corrupt → cold start (sizer abstains until pools re-warm). See openAPSBoostV7/V7_SHADOW.md.
    ApsBoostV7ResidualPools("boost_v7_residual_pools", "", defaultedBySM = true),

    // ISF shadow persisted state (JSON blob: EMA value + timestamps for warmup computation)
    // Used by BoostIsfShadow to persist EMA(τ=3h) sensitivity ratio across plugin restarts.
    ApsBoostIsfShadowState("boost_isf_shadow_state", "", defaultedBySM = true),

    // Anticipation shadow onset history (JSON blob: rolling exercise + meal onset timestamps,
    // ~56-day window). Read/written by AnticipationShadow every Boost cycle to refit the per-user
    // habit models. Blank/corrupt → empty (falls back to the cross-user prior). Read-only to dosing.
    ApsBoostAnticipHistory("boost_anticip_history", "", defaultedBySM = true),

    // Sleep state machine persisted state (JSON blob: SleepState, hysteresis counters, entry ts)
    ApsBoostSleepState("boost_sleep_state", "", defaultedBySM = true),

    // Rolling 28-day sleep history (JSON blob with closed sessions + current openSleepStartMs)
    // Drives circular-mean sleep_start / wake-time learning; PRE_SLEEP fires
    // preSleepLeadMin before the learned average once ≥7 sessions exist.
    ApsBoostSleepHistory("boost_sleep_history", "", defaultedBySM = true),

    // v12 ML feature ring buffer — JSON array of last 6 cycle snapshots holding the
    // 6 lookback features (cgm_mgdl, iob_iob, iob_activity, sug_eventualBG,
    // recent_smb_units_60m, sug_minDelta). Persisted across plugin restarts so the
    // windowed feature vector survives cold starts. Reset is harmless: cold buffer
    // falls back to repeating the current cycle.
    ApsBoostMlRingBuffer("boost_ml_ring_buffer", "", defaultedBySM = true),

    // V6 meal-time learner — JSON array of recent V5-CONFIRMED meal-commit timestamps (rolling
    // 60 days). Drives circular-clustered habitual meal-time learning so the anticipatory
    // pre-meal low target can fire ~45-60 min before a learned meal. Empty/corrupt → no learned
    // meals → feature never fires (safe default).
    ApsBoostMealTimeHistory("boost_meal_time_history", "", defaultedBySM = true),

    // Activity-load SHADOW (2026-06-16) — JSON of single-source per-day step totals (rolling 28d).
    // Drives the personal step baseline; the activity/inactivity ISF factors are LOGGED ONLY (shadow).
    ApsBoostDailyStepHistory("boost_daily_step_history", "", defaultedBySM = true),

    // Intraday step bank (2026-07-07) — JSON {d: dayIndex, max: {source: count}} of per-source
    // running maxima of today's cumulative steps. Day-close resolves the completed day from this
    // BANK, never from post-reset live reads (the wear counter resets at DEVICE midnight before
    // the phone-local rollover — the 07-06 5.6x undercount). Persisted so a mid-evening app
    // restart keeps the day's peak. Empty/corrupt -> fresh bank (one day's history at risk, safe).
    ApsBoostIntradayStepBank("boost_intraday_step_bank", "", defaultedBySM = true),
}