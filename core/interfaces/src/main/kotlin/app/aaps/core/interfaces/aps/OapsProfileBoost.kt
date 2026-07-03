package app.aaps.core.interfaces.aps

import kotlinx.serialization.Serializable

@Serializable
data class OapsProfileBoost(
    // Standard oref1 fields (same as OapsProfile / OapsProfileAutoIsf)
    var dia: Double,
    var min_5m_carbimpact: Double,
    var max_iob: Double,
    var max_daily_basal: Double,
    var max_basal: Double,
    var min_bg: Double,
    var max_bg: Double,
    var target_bg: Double,
    var carb_ratio: Double,
    var sens: Double,
    var autosens_adjust_targets: Boolean,
    var max_daily_safety_multiplier: Double,
    var current_basal_safety_multiplier: Double,
    var high_temptarget_raises_sensitivity: Boolean,
    var low_temptarget_lowers_sensitivity: Boolean,
    var sensitivity_raises_target: Boolean,
    var resistance_lowers_target: Boolean,
    var adv_target_adjustments: Boolean,
    var exercise_mode: Boolean,
    var half_basal_exercise_target: Int,
    var maxCOB: Int,
    var skip_neutral_temps: Boolean,
    var remainingCarbsCap: Int,
    var enableUAM: Boolean,
    var A52_risk_enable: Boolean,
    var SMBInterval: Int,
    var enableSMB_with_COB: Boolean,
    var enableSMB_with_temptarget: Boolean,
    var allowSMB_with_high_temptarget: Boolean,
    var enableSMB_always: Boolean,
    var enableSMB_after_carbs: Boolean,
    var maxSMBBasalMinutes: Int,
    var maxUAMSMBBasalMinutes: Int,
    var bolus_increment: Double,
    var carbsReqThreshold: Int,
    var current_basal: Double,
    var temptargetSet: Boolean,
    var autosens_max: Double,
    var out_units: String,
    var lgsThreshold: Int?,

    // Dynamic ISF base fields
    var variable_sens: Double,
    var insulinDivisor: Int,
    var TDD: Double,

    // Boost-specific: ISF calculation parameters
    var dynISFBgCap: Double,        // BG cap above which ISF increases more slowly
    var dynISFBgCapped: Double,     // Capped BG value used for ISF (sens_bg)
    var sensNormalTarget: Double,   // ISF at normal target BG level
    var normalTarget: Double,       // Normal target BG (e.g. 99 mg/dL)
    var dynISFvelocity: Double,     // How quickly ISF adjusts with BG changes (0.0-1.0)

    // Boost-specific: insulin peak
    var insulinPeak: Int,           // Insulin peak time in minutes (capped 30-75)

    // Boost-specific: Boost SMB sizing
    var boostActive: Boolean,                   // Whether Boost is in its active time window
    var profileSwitch: Int,                     // Effective profile percentage (adjusted for activity)
    var boost_bolus: Double,                    // Maximum individual SMB cap (e.g. 2.5U)
    var boost_maxIOB: Double,                   // Boost-specific IOB limit
    var Boost_InsulinReq: Double,               // Insulin required divisor percentage (e.g. 50 = give 50%)
    var boost_scale: Double,                    // Multiplier for boost insulin requirement
    var boost_percent_scale: Double,            // Sliding scale percentage factor (e.g. 200)
    var enableBoostPercentScale: Boolean,       // Enable sliding scale from BG 108→180
    var enableCircadianISF: Boolean,            // Enable time-of-day ISF adjustment
    var allowBoost_with_high_temptarget: Boolean, // Allow boost even with high temp target

    // Boost-specific: step counter data
    var recentSteps5Minutes: Int,
    var recentSteps15Minutes: Int,
    var recentSteps30Minutes: Int,
    var recentSteps60Minutes: Int,

    // Boost-specific: recent glucose nadir (minimum BG in last 60 minutes, mg/dL)
    // Used to detect fast-carb rebound: if BG was recently very low and is now rising fast,
    // suppress UAM boost to avoid stacking insulin onto an unannounced carb rescue.
    var recentLowBG: Double,

    // Boost-specific: braking signal (max |delta|×improvement across consecutive CGM triplets
    // while BG was still falling, over last 60 minutes). Captures rapid deceleration of a falling
    // glucose caused by fast-acting carb absorption — catches "candy without a preceding low"
    // that recentLowBG misses. Threshold ~800 distinguishes fast-carb braking from IOB decay.
    var recentBrakingProduct: Double,

    // Boost debug context (not used by algorithm, displayed in Script Debug)
    var boostDebugReason: String = "",
    var isfDebugReason: String = ""
)
