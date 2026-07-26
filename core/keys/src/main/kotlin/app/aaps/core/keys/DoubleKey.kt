package app.aaps.core.keys

import app.aaps.core.keys.interfaces.BooleanPreferenceKey
import app.aaps.core.keys.interfaces.DoublePreferenceKey

enum class DoubleKey(
    override val key: String,
    override val defaultValue: Double,
    override val min: Double,
    override val max: Double,
    override val defaultedBySM: Boolean = false,
    override val calculatedBySM: Boolean = false,
    override val showInApsMode: Boolean = true,
    override val showInNsClientMode: Boolean = true,
    override val showInPumpControlMode: Boolean = true,
    override val dependency: BooleanPreferenceKey? = null,
    override val negativeDependency: BooleanPreferenceKey? = null,
    override val hideParentScreenIfHidden: Boolean = false,
    override val exportable: Boolean = true
) : DoublePreferenceKey {

    OverviewInsulinButtonIncrement1("insulin_button_increment_1", 0.5, -5.0, 5.0, defaultedBySM = true, dependency = BooleanKey.OverviewShowInsulinButton),
    OverviewInsulinButtonIncrement2("insulin_button_increment_2", 1.0, -5.0, 5.0, defaultedBySM = true, dependency = BooleanKey.OverviewShowInsulinButton),
    OverviewInsulinButtonIncrement3("insulin_button_increment_3", 2.0, -5.0, 5.0, defaultedBySM = true, dependency = BooleanKey.OverviewShowInsulinButton),
    ActionsFillButton1("fill_button1", 0.3, 0.05, 20.0, defaultedBySM = true, hideParentScreenIfHidden = true),
    ActionsFillButton2("fill_button2", 0.0, 0.05, 20.0, defaultedBySM = true),
    ActionsFillButton3("fill_button3", 0.0, 0.05, 20.0, defaultedBySM = true),
    SafetyMaxBolus("treatmentssafety_maxbolus", 3.0, 0.1, 60.0),
    ApsMaxBasal("openapsma_max_basal", 1.0, 0.1, 25.0, defaultedBySM = true, calculatedBySM = true),
    ApsSmbMaxIob("openapsmb_max_iob", 3.0, 0.0, 70.0, defaultedBySM = true, calculatedBySM = true),
    ApsAmaMaxIob("openapsma_max_iob", 1.5, 0.0, 25.0, defaultedBySM = true, calculatedBySM = true),
    ApsMaxDailyMultiplier("openapsama_max_daily_safety_multiplier", 3.0, 1.0, 10.0, defaultedBySM = true),
    ApsMaxCurrentBasalMultiplier("openapsama_current_basal_safety_multiplier", 4.0, 1.0, 10.0, defaultedBySM = true),
    ApsAmaBolusSnoozeDivisor("bolussnooze_dia_divisor", 2.0, 1.0, 10.0, defaultedBySM = true),
    ApsAmaMin5MinCarbsImpact("openapsama_min_5m_carbimpact", 3.0, 1.0, 12.0, defaultedBySM = true),
    ApsSmbMin5MinCarbsImpact("openaps_smb_min_5m_carbimpact", 8.0, 1.0, 12.0, defaultedBySM = true),
    AbsorptionCutOff("absorption_cutoff", 6.0, 4.0, 10.0),
    AbsorptionMaxTime("absorption_maxtime", 6.0, 4.0, 10.0),
    AutosensMin("autosens_min", 0.7, 0.1, 1.0, defaultedBySM = true, hideParentScreenIfHidden = true),
    AutosensMax("autosens_max", 1.2, 0.5, 3.0, defaultedBySM = true),
    ApsAutoIsfMin("autoISF_min", 1.0, 0.3, 1.0, defaultedBySM = true),
    ApsAutoIsfMax("autoISF_max", 1.0, 1.0, 3.0, defaultedBySM = true),
    ApsAutoIsfBgAccelWeight("bgAccel_ISF_weight", 0.0, 0.0, 1.0, defaultedBySM = true),
    ApsAutoIsfBgBrakeWeight("bgBrake_ISF_weight", 0.0, 0.0, 1.0, defaultedBySM = true),
    ApsAutoIsfLowBgWeight("lower_ISFrange_weight", 0.0, 0.0, 2.0, defaultedBySM = true),
    ApsAutoIsfHighBgWeight("higher_ISFrange_weight", 0.0, 0.0, 2.0, defaultedBySM = true),
    ApsAutoIsfSmbDeliveryRatioBgRange("openapsama_smb_delivery_ratio_bg_range", 0.0, 0.0, 100.0, defaultedBySM = true),
    ApsAutoIsfPpWeight("pp_ISF_weight", 0.0, 0.0, 1.0, defaultedBySM = true),
    ApsAutoIsfDuraWeight("dura_ISF_weight", 0.0, 0.0, 3.0, defaultedBySM = true),
    ApsAutoIsfSmbDeliveryRatio("openapsama_smb_delivery_ratio", 0.5, 0.5, 1.0, defaultedBySM = true),
    ApsAutoIsfSmbDeliveryRatioMin("openapsama_smb_delivery_ratio_min", 0.5, 0.5, 1.0, defaultedBySM = true),
    ApsAutoIsfSmbDeliveryRatioMax("openapsama_smb_delivery_ratio_max", 0.5, 0.5, 1.0, defaultedBySM = true),
    ApsAutoIsfSmbMaxRangeExtension("openapsama_smb_max_range_extension", 1.0, 1.0, 5.0, defaultedBySM = true),

    // Boost
    ApsBoostBolus("boost_bolus_cap", 2.5, 0.1, 10.0, defaultedBySM = true),
    ApsBoostMaxIob("boost_max_iob", 1.0, 0.1, 12.0, defaultedBySM = true),
    ApsBoostInsulinReqPct("boost_insulin_req_pct", 50.0, 30.0, 100.0, defaultedBySM = true),
    ApsBoostScale("boost_scale_value", 1.0, 0.1, 3.0, defaultedBySM = true),
    ApsBoostPercentScale("boost_percent_scale_factor", 200.0, 50.0, 500.0, defaultedBySM = true),
    ApsBoostDynIsfVelocity("boost_dynisf_velocity", 100.0, 0.0, 100.0, defaultedBySM = true),
    ApsBoostSleepInHours("boost_sleep_in_hrs", 2.0, 0.0, 18.0, defaultedBySM = true),
    ApsBoostInactivityPct("boost_inactivity_pct", 130.0, 100.0, 200.0, defaultedBySM = true),
    ApsBoostActivityPct("boost_activity_pct", 80.0, 30.0, 150.0, defaultedBySM = true),
    ApsBoostPostExerciseRecoveryHours("boost_post_exercise_recovery_hours", 2.0, 0.5, 8.0, defaultedBySM = true),
    ApsBoostPostExerciseRecoveryScale("boost_post_exercise_recovery_scale", 0.5, 0.0, 1.0, defaultedBySM = true),
    // Default is permissive (10 = the max, effectively off) on purpose: auto-config LOWERS it to the
    // per-user value on first V6 activation; until then a conservative default would needlessly throttle.
    ApsBoostCumulativeSmbCap60Min("boost_cumulative_smb_cap_60min", 10.0, 0.0, 10.0, defaultedBySM = true),

    // Boost V5 — three (and only three) user-facing knobs per the minimal-settings tenet
    // 2026-07-17: range max 1.3 → 1.6 (default UNCHANGED at 1.0). Widened the same way the cap
    // ranges were (see the confirmed/committed comment below) so a high-headroom user who wants a
    // firmer meal response can push the CONFIRMED catch-up shot harder — the knob scales the
    // CONFIRMED multiplier only (MealActionMultiplier.kt), still bounded above by the Phase-3 gates.
    // Auto-config still never auto-raises above 1.0 (BoostV5AutoConfig.kt); this only affects a
    // user who deliberately raises the slider. Field driver: user H pinned at the old 1.3 ceiling.
    ApsBoostV5Aggression("boost_v5_aggression", 1.0, 0.7, 1.6, defaultedBySM = true),
    // Boost V5 active-dosing alpha (2026-06-11) — user-adjustable dose caps so the operator can
    // tune V5's commit/holding doses live. 2026-06-26: defaults raised to match the developer's
    // running build (confirmed 1.0→2.5, committed 0.25→0.5) and ranges widened (confirmed 5.0→7.5,
    // committed 1.0→2.5) so higher-insulin-need users and big meals aren't clipped.
    ApsBoostV5ConfirmedCapU("boost_v5_confirmed_cap_u", 2.5, 0.0, 7.5, defaultedBySM = true),
    ApsBoostV5CommittedCapU("boost_v5_committed_cap_u", 0.5, 0.0, 2.5, defaultedBySM = true),
    ApsBoostV5HypoCaution("boost_v5_hypo_caution", 1.0, 1.0, 2.0, defaultedBySM = true),
    ApsBoostV5Sensitivity("boost_v5_sensitivity", 1.0, 0.8, 1.2, defaultedBySM = true),

    // Boost V6 — anticipatory pre-meal low target (2026-06-15).
    // PreMealTargetMgdl: the low target applied during the learned pre-meal window (default 72
    // mg/dL = 4.0 mmol — an "eating-soon" target that raises insulinReq before carbs land).
    // PreMealLeadMin: window OPENS this many minutes before the learned meal mode; it CLOSES at
    // PRE_MEAL_LEAD_MIN_FLOOR (45 min, a MealTimeLearner constant) before the meal.
    ApsBoostV6PreMealTargetMgdl("boost_v6_pre_meal_target_mgdl", 72.0, 65.0, 90.0, defaultedBySM = true),
    ApsBoostV6PreMealLeadMin("boost_v6_pre_meal_lead_min", 60.0, 30.0, 90.0, defaultedBySM = true),

}