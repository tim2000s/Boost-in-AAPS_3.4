package app.aaps.plugins.aps.openAPSBoostV2

import app.aaps.core.data.configuration.Constants
import app.aaps.core.interfaces.aps.APSResult
import app.aaps.core.interfaces.aps.AutosensResult
import app.aaps.core.interfaces.aps.CurrentTemp
import app.aaps.core.interfaces.aps.GlucoseStatus
import app.aaps.core.interfaces.aps.IobTotal
import app.aaps.core.interfaces.aps.MealData
import app.aaps.core.interfaces.aps.OapsProfileBoost
import app.aaps.core.interfaces.aps.Predictions
import app.aaps.core.interfaces.aps.RT
import app.aaps.core.interfaces.profile.ProfileUtil
import java.text.DecimalFormat
import java.time.Instant
import java.time.ZoneId
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.abs
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.roundToInt

@Singleton
class DetermineBasalBoostV2 @Inject constructor(
    private val profileUtil: ProfileUtil
) {

    private val consoleError = mutableListOf<String>()
    private val consoleLog = mutableListOf<String>()

    private fun Double.toFixed2(): String = DecimalFormat("0.00#").format(round(this, 2))

    fun round_basal(value: Double): Double = value

    fun round(value: Double, digits: Int): Double {
        if (value.isNaN()) return Double.NaN
        val scale = 10.0.pow(digits.toDouble())
        return Math.round(value * scale) / scale
    }

    fun Double.withoutZeros(): String = DecimalFormat("0.##").format(this)
    fun round(value: Double): Int = value.roundToInt()

    fun calculate_expected_delta(targetBg: Double, eventualBg: Double, bgi: Double): Double {
        val fiveMinBlocks = (2 * 60) / 5
        val targetDelta = targetBg - eventualBg
        return round(bgi + (targetDelta / fiveMinBlocks), 1)
    }

    fun convert_bg(value: Double): String =
        profileUtil.fromMgdlToStringInUnits(value).replace("-0.0", "0.0")

    // =====================================================================
    // Boost V2: Dynamic ISF calculation per BG level
    // Chris Wilson DynISF V2: ISF = 2300 / (ln(BG/insulinDivisor + 1) · TDD² · 0.02)
    // sensNormalTarget is pre-computed in the plugin using the V2 formula
    // with all adjustments (globalScale, sensRatio, TT). Here we just scale
    // by the BG ratio — equivalent to velocity=1.0 (no dampening).
    // =====================================================================
    fun getIsfByProfile(bg: Double, profile: OapsProfileBoost, useCap: Boolean): Double {
        var bgAdj = bg
        if (useCap) {
            val cap = profile.dynISFBgCap
            if (bgAdj > cap) bgAdj = cap + (bgAdj - cap) / 3.0
        }
        val sensBG = ln((bgAdj / profile.insulinDivisor) + 1.0)
        if (sensBG <= 0) return profile.sensNormalTarget  // safety guard
        val scaler = ln((profile.normalTarget / profile.insulinDivisor) + 1.0) / sensBG
        return profile.sensNormalTarget * scaler
    }

    // =====================================================================
    // Boost-specific: Circadian ISF sensitivity factor
    // Cubic polynomial adjustments by time of day
    // =====================================================================
    fun getCircadianSensitivity(hourOfDay: Int): Double {
        val now = max(hourOfDay, 0).toDouble()
        return when {
            now in 0.0..<2.0  -> {
                val n = max(now, 0.5)
                (0.09130 * n.pow(3)) - (0.33261 * n.pow(2)) + 1.4
            }
            now in 2.0..<3.0  -> (0.0869 * now.pow(3)) - (0.05217 * now.pow(2)) - (0.23478 * now) + 0.8
            now in 3.0..<8.0  -> (0.0007 * now.pow(3)) - (0.000730 * now.pow(2)) - (0.0007826 * now) + 0.6
            now in 8.0..<11.0 -> (0.001244 * now.pow(3)) - (0.007619 * now.pow(2)) - (0.007826 * now) + 0.4
            now in 11.0..<15.0 -> (0.00078 * now.pow(3)) - (0.00272 * now.pow(2)) - (0.07619 * now) + 0.8
            now in 15.0..22.0 -> 1.0
            now in 22.0..24.0 -> (0.000125 * now.pow(3)) - (0.0015 * now.pow(2)) - (0.0045 * now) + 1.2
            else              -> 1.0
        }
    }

    fun enable_smb(profile: OapsProfileBoost, microBolusAllowed: Boolean, meal_data: MealData, target_bg: Double): Boolean {
        if (!microBolusAllowed) {
            consoleError.add("SMB disabled (!microBolusAllowed)")
            return false
        } else if (!profile.allowSMB_with_high_temptarget && profile.temptargetSet && target_bg > 100) {
            consoleError.add("SMB disabled due to high temptarget of $target_bg")
            return false
        }

        if (profile.enableSMB_always) {
            consoleError.add("SMB enabled due to enableSMB_always")
            return true
        }

        if (profile.enableSMB_with_COB && meal_data.mealCOB != 0.0) {
            consoleError.add("SMB enabled for COB of ${meal_data.mealCOB}")
            return true
        }

        if (profile.enableSMB_after_carbs && meal_data.carbs != 0.0) {
            consoleError.add("SMB enabled for 6h after carb entry")
            return true
        }

        if (profile.enableSMB_with_temptarget && (profile.temptargetSet && target_bg < 100)) {
            consoleError.add("SMB enabled for temptarget of ${convert_bg(target_bg)}")
            return true
        }

        consoleError.add("SMB disabled (no enableSMB preferences active or no condition satisfied)")
        return false
    }

    fun reason(rT: RT, msg: String) {
        if (rT.reason.toString().isNotEmpty()) rT.reason.append(". ")
        rT.reason.append(msg)
        consoleError.add(msg)
    }

    private fun getMaxSafeBasal(profile: OapsProfileBoost): Double =
        min(profile.max_basal, min(profile.max_daily_safety_multiplier * profile.max_daily_basal, profile.current_basal_safety_multiplier * profile.current_basal))

    fun setTempBasal(_rate: Double, duration: Int, profile: OapsProfileBoost, rT: RT, currenttemp: CurrentTemp): RT {
        val maxSafeBasal = getMaxSafeBasal(profile)
        var rate = _rate
        if (rate < 0) rate = 0.0
        else if (rate > maxSafeBasal) rate = maxSafeBasal

        val suggestedRate = round_basal(rate)
        if (currenttemp.duration > (duration - 10) && currenttemp.duration <= 120 && suggestedRate <= currenttemp.rate * 1.2 && suggestedRate >= currenttemp.rate * 0.8 && duration > 0) {
            rT.reason.append(" ${currenttemp.duration}m left and ${currenttemp.rate.withoutZeros()} ~ req ${suggestedRate.withoutZeros()}U/hr: no temp required")
            return rT
        }

        if (suggestedRate == profile.current_basal) {
            if (profile.skip_neutral_temps) {
                if (currenttemp.duration > 0) {
                    reason(rT, "Suggested rate is same as profile rate, a temp basal is active, canceling current temp")
                    rT.duration = 0
                    rT.rate = 0.0
                    return rT
                } else {
                    reason(rT, "Suggested rate is same as profile rate, no temp basal is active, doing nothing")
                    return rT
                }
            } else {
                reason(rT, "Setting neutral temp basal of ${profile.current_basal}U/hr")
                rT.duration = duration
                rT.rate = suggestedRate
                return rT
            }
        } else {
            rT.duration = duration
            rT.rate = suggestedRate
            return rT
        }
    }

    // =====================================================================
    // Main algorithm entry point
    // =====================================================================
    fun determine_basal(
        glucose_status: GlucoseStatus, currenttemp: CurrentTemp, iob_data_array: Array<IobTotal>, profile: OapsProfileBoost, autosens_data: AutosensResult, meal_data: MealData,
        microBolusAllowed: Boolean, currentTime: Long, flatBGsDetected: Boolean
    ): RT {
        consoleError.clear()
        consoleLog.clear()
        // Even on the early-bailout path (invalid BG / stale data) we want the
        // Boost-specific markers present in the Nightscout upload so downstream
        // analysis can distinguish "field genuinely missing" from "decision skipped
        // before the algorithm got that far". We set the markers that are honestly
        // known at this point and leave the numerics null for fields the algorithm
        // never computed.
        var rT = RT(
            algorithm = APSResult.Algorithm.BOOST,
            runningDynamicIsf = true, // Boost always uses dynamic ISF
            timestamp = currentTime,
            consoleLog = consoleLog,
            consoleError = consoleError,
            // Boost markers — emitted even on the early-return path
            boostActive = profile.boostActive,
            boostProfileSwitch = profile.profileSwitch,
            boostTier = "NONE",
            fastCarbProtection = false,
            insulinReqPctEffective = 0.0,
            // Numerics that the plugin already pre-computed before determine_basal
            sensNormalTarget = if (profile.sensNormalTarget > 0) round(profile.sensNormalTarget, 1) else null,
            predictionISF = if (profile.variable_sens > 0) round(profile.variable_sens, 1) else null,
            tdd = if (profile.TDD > 0) round(profile.TDD, 1) else null
        )

        val deliverAt = currentTime
        val profile_current_basal = round_basal(profile.current_basal)
        var basal = profile_current_basal
        val systemTime = currentTime
        val bgTime = glucose_status.date
        val minAgo = round((systemTime - bgTime) / 60.0 / 1000.0, 1)
        val bg = glucose_status.glucose
        val noise = glucose_status.noise

        // =====================================================================
        // BG validation
        // =====================================================================
        if (bg <= 10 || bg == 38.0 || noise >= 3) {
            rT.reason.append("CGM is calibrating, in ??? state, or noise is high")
        }
        if (minAgo > 12 || minAgo < -5) {
            rT.reason.append("If current system time $systemTime is correct, then BG data is too old. The last BG data was read ${minAgo}m ago at $bgTime")
        } else if (bg > 60 && flatBGsDetected) {
            rT.reason.append("Error: CGM data is unchanged for the past ~45m")
        }
        if (bg <= 10 || bg == 38.0 || noise >= 3 || minAgo > 12 || minAgo < -5 || (bg > 60 && flatBGsDetected)) {
            if (currenttemp.rate > basal) {
                rT.reason.append(". Replacing high temp basal of ${currenttemp.rate} with neutral temp of $basal")
                rT.deliverAt = deliverAt
                rT.duration = 30
                rT.rate = basal
                return rT
            } else if (currenttemp.rate == 0.0 && currenttemp.duration > 30) {
                rT.reason.append(". Shortening ${currenttemp.duration}m long zero temp to 30m. ")
                rT.deliverAt = deliverAt
                rT.duration = 30
                rT.rate = 0.0
                return rT
            } else {
                rT.reason.append(". Temp ${currenttemp.rate} <= current basal ${round(basal, 2)}U/hr; doing nothing. ")
                return rT
            }
        }

        val max_iob = profile.max_iob

        var target_bg = (profile.min_bg + profile.max_bg) / 2
        var min_bg = profile.min_bg
        var max_bg = profile.max_bg

        // =====================================================================
        // Boost-specific: Delta acceleration calculation
        // =====================================================================
        val shortAvgDelta = glucose_status.shortAvgDelta
        val delta_accl = if (abs(shortAvgDelta) > 0.001)
            round(100.0 * (glucose_status.delta - shortAvgDelta) / abs(shortAvgDelta), 2)
        else 0.0

        var iTimeActive = false

        // =====================================================================
        // Boost Dynamic ISF for predictions
        // =====================================================================
        consoleError.add("═════════════════════════════════════════════════════════")
        consoleError.add("  Boost V2 (Chris Wilson DynISF V2) | Profile: ${profile.profileSwitch}%")
        consoleError.add("═════════════════════════════════════════════════════════")
        consoleError.add("Steps: 5m=${profile.recentSteps5Minutes} 15m=${profile.recentSteps15Minutes} 30m=${profile.recentSteps30Minutes} 60m=${profile.recentSteps60Minutes}")

        // Boost window reasoning from plugin
        if (profile.boostDebugReason.isNotEmpty()) {
            for (line in profile.boostDebugReason.split("\n")) {
                consoleError.add(line)
            }
        }

        // ── Glucose ──
        consoleError.add("── Glucose ─────────────────────────────────")
        consoleError.add("BG: $bg mg/dl | Delta: ${round(glucose_status.delta, 1)} | Short avg: ${round(glucose_status.shortAvgDelta, 1)} | Long avg: ${round(glucose_status.longAvgDelta, 1)}")
        consoleError.add("Delta acceleration: $delta_accl%")

        // ── Targets ──
        consoleError.add("── Targets ─────────────────────────────────")
        consoleError.add("min=$min_bg max=$max_bg target=$target_bg (TT: ${profile.temptargetSet})")

        // ── ISF ──
        consoleError.add("── ISF ─────────────────────────────────────")
        consoleError.add("Profile sens: ${round(profile.sens, 1)} | Variable sens: ${round(profile.variable_sens, 1)} | sensNormalTarget: ${round(profile.sensNormalTarget, 1)}")
        consoleError.add("DynISF V2: normalTarget=${convert_bg(profile.normalTarget)} | bgCap=${convert_bg(profile.dynISFBgCap)} | bgCapped=${profile.dynISFBgCapped}")
        if (profile.TDD > 0) consoleError.add("TDD: ${round(profile.TDD, 1)} | ISF from V2 formula: 2300/(ln·TDD²·0.02)")
        else consoleError.add("TDD: not available — V2 requires TDD (using profile ISF fallback)")

        // ISF calculation reasoning from plugin
        if (profile.isfDebugReason.isNotEmpty()) {
            for (line in profile.isfDebugReason.split("\n")) {
                consoleError.add("  $line")
            }
        }

        // ── Boost Config ──
        consoleError.add("── Boost Config ────────────────────────────")
        consoleError.add("Bolus cap: ${profile.boost_bolus} | maxIOB: ${profile.boost_maxIOB} | scale: ${round(profile.boost_scale, 2)} | insulinReq%: ${profile.Boost_InsulinReq}")
        consoleError.add("Percent scale: ${profile.enableBoostPercentScale} (${profile.boost_percent_scale}) | Circadian ISF: ${profile.enableCircadianISF}")

        // ── State ──
        consoleError.add("── State ───────────────────────────────────")
        consoleError.add("IOB: ${round(iob_data_array[0].iob, 2)} | Activity: ${round(iob_data_array[0].activity, 4)} | COB: ${meal_data.mealCOB}")
        consoleError.add("SMB allowed: $microBolusAllowed | Flat BGs: $flatBGsDetected")
        consoleError.add("═════════════════════════════════════════════════════════")

        val insulinPeak = profile.insulinPeak
        val ins_val = profile.insulinDivisor
        consoleLog.add("Insulin peak: $insulinPeak, divisor: $ins_val")

        val sens_bg = profile.dynISFBgCapped
        if (sens_bg != bg) consoleLog.add("Current sensitivity increasing slowly from ${profile.dynISFBgCap} mg/dl")

        var variable_sens = profile.variable_sens
        consoleLog.add("Current sensitivity for predictions is $variable_sens based on current bg")

        // =====================================================================
        // Circadian ISF adjustment
        // =====================================================================
        val now = Instant.ofEpochMilli(currentTime).atZone(ZoneId.systemDefault()).toLocalDateTime().hour
        val circadian_sensitivity = getCircadianSensitivity(now)
        consoleLog.add("Circadian_sensitivity factor: $circadian_sensitivity")

        var sens: Double
        if (profile.enableCircadianISF) {
            sens = round(variable_sens * circadian_sensitivity, 1)
            consoleLog.add("Circadian ISF enabled")
        } else {
            sens = round(variable_sens, 1)
            consoleLog.add("Circadian ISF disabled")
        }

        // =====================================================================
        // Autosens ratio and basal adjustment
        // =====================================================================
        var sensitivityRatio: Double = autosens_data.ratio
        consoleLog.add("Autosens ratio: $sensitivityRatio")

        basal = profile.current_basal * sensitivityRatio
        basal = round_basal(basal)
        if (basal != profile_current_basal)
            consoleLog.add("Adjusting basal from $profile_current_basal to $basal")
        else
            consoleLog.add("Basal unchanged: $basal")

        // adjust min, max, and target BG for sensitivity
        if (profile.temptargetSet) {
            // Temp Target set, not adjusting with autosens
        } else if (sensitivityRatio != 1.0) {
            if (profile.sensitivity_raises_target && autosens_data.ratio < 1 || profile.resistance_lowers_target && autosens_data.ratio > 1) {
                min_bg = round((min_bg - 60) / sensitivityRatio, 0) + 60
                max_bg = round((max_bg - 60) / sensitivityRatio, 0) + 60
                var new_target_bg = round((target_bg - 60) / sensitivityRatio, 0) + 60
                new_target_bg = max(80.0, new_target_bg)
                if (target_bg == new_target_bg)
                    consoleLog.add("target_bg unchanged: $new_target_bg")
                else
                    consoleLog.add("target_bg from $target_bg to $new_target_bg")
                target_bg = new_target_bg
            }
        }

        // =====================================================================
        // Boost-specific: HypoPredBG and Hypo target adjustment
        // =====================================================================
        val bgi_raw = round((-iob_data_array[0].activity * sens * 5), 2)
        val minDeltaRaw = min(glucose_status.delta, glucose_status.shortAvgDelta)
        val HypoPredBG = round(bg - (iob_data_array[0].iob * sens)) + round(60.0 / 5 * (minDeltaRaw - bgi_raw))

        val EBG = (0.02 * glucose_status.delta * glucose_status.delta) + (0.58 * glucose_status.longAvgDelta) + bg
        val REBG = EBG / min_bg
        consoleLog.add("EBG: $EBG REBG: $REBG")
        consoleLog.add("HypoPredBG = $HypoPredBG")

        var halfBasalTarget = profile.half_basal_exercise_target
        val normalTarget = 100

        if (!profile.temptargetSet && HypoPredBG <= 125 && profile.sensitivity_raises_target) {
            var hypo_target = round(min(200.0, min_bg + (EBG - min_bg) / 3), 0)
            if (hypo_target <= target_bg) {
                hypo_target = target_bg + 10
                consoleLog.add("target_bg from $target_bg to $hypo_target because HypoPredBG <= 125: $HypoPredBG")
            } else if (target_bg == hypo_target) {
                consoleLog.add("target_bg unchanged: $hypo_target")
            }
            target_bg = hypo_target
            halfBasalTarget = 160
            val c = (halfBasalTarget - normalTarget).toDouble()
            sensitivityRatio = c / (c + target_bg - normalTarget)
            sensitivityRatio = min(sensitivityRatio, profile.autosens_max)
            sensitivityRatio = round(sensitivityRatio, 2)
            consoleLog.add("Sensitivity ratio set to $sensitivityRatio based on temp target of $target_bg")
            basal = profile.current_basal * sensitivityRatio
            basal = round_basal(basal)
            if (basal != profile_current_basal)
                consoleLog.add("Adjusting basal from $profile_current_basal to $basal")
            else
                consoleLog.add("Basal unchanged: $basal")
        }

        // =====================================================================
        // IOB data
        // =====================================================================
        val iobArray = iob_data_array
        val iob_data = iobArray[0]

        val tick: String = if (glucose_status.delta > -0.5) {
            "+" + round(glucose_status.delta)
        } else {
            round(glucose_status.delta).toString()
        }
        val minDelta = min(glucose_status.delta, glucose_status.shortAvgDelta)
        val minAvgDelta = min(glucose_status.shortAvgDelta, glucose_status.longAvgDelta)
        val maxDelta = max(glucose_status.delta, max(glucose_status.shortAvgDelta, glucose_status.longAvgDelta))

        val eRatio = round(sens / 13.2)
        consoleError.add("Effective CR: $eRatio")

        // calculate BG impact
        val bgi = round((-iob_data.activity * sens * 5), 2)
        var deviation = round(30.0 / 5 * (minDelta - bgi))
        if (deviation < 0) {
            deviation = round((30.0 / 5) * (minAvgDelta - bgi))
            if (deviation < 0) {
                deviation = round((30.0 / 5) * (glucose_status.longAvgDelta - bgi))
            }
        }

        // naive eventual BG
        val naive_eventualBG: Double = if (iob_data.iob > 0) {
            round(bg - (iob_data.iob * sens), 0)
        } else {
            round(bg - (iob_data.iob * min(sens, profile.sens)), 0)
        }
        var eventualBG = naive_eventualBG + deviation

        // raise target for noisy / raw CGM data or high BG
        if (bg > max_bg && profile.adv_target_adjustments && !profile.temptargetSet) {
            val adjustedMinBG = round(max(80.0, min_bg - (bg - min_bg) / 3.0), 0)
            val adjustedTargetBG = round(max(80.0, target_bg - (bg - target_bg) / 3.0), 0)
            val adjustedMaxBG = round(max(80.0, max_bg - (bg - max_bg) / 3.0), 0)
            if (eventualBG > adjustedMinBG && naive_eventualBG > adjustedMinBG && min_bg > adjustedMinBG) {
                consoleLog.add("Adjusting targets for high BG: min_bg from $min_bg to $adjustedMinBG")
                min_bg = adjustedMinBG
            } else {
                consoleLog.add("min_bg unchanged: $min_bg")
            }
            if (eventualBG > adjustedTargetBG && naive_eventualBG > adjustedTargetBG && target_bg > adjustedTargetBG) {
                consoleLog.add("target_bg from $target_bg to $adjustedTargetBG")
                target_bg = adjustedTargetBG
            } else {
                consoleLog.add("target_bg unchanged: $target_bg")
            }
            if (eventualBG > adjustedMaxBG && naive_eventualBG > adjustedMaxBG && max_bg > adjustedMaxBG) {
                consoleError.add("max_bg from $max_bg to $adjustedMaxBG")
                max_bg = adjustedMaxBG
            } else {
                consoleError.add("max_bg unchanged: $max_bg")
            }
        }

        val expectedDelta = calculate_expected_delta(target_bg, eventualBG, bgi)

        // =====================================================================
        // Threshold - Boost modification: lower threshold when delta accelerating
        // =====================================================================
        consoleError.add("── Threshold ───────────────────────────────")
        var threshold = min_bg - 0.5 * (min_bg - 40)
        if (profile.lgsThreshold != null) {
            val lgsThreshold = profile.lgsThreshold ?: error("lgsThreshold missing")
            if (lgsThreshold > threshold) {
                consoleError.add("Threshold raised from ${convert_bg(threshold)} to ${convert_bg(lgsThreshold.toDouble())}")
                threshold = lgsThreshold.toDouble()
            }
        }
        // Boost: lower threshold when BG is accelerating upward
        if (delta_accl > 0) {
            threshold = 65.0
            consoleError.add("Threshold lowered to ${convert_bg(threshold)} (delta accelerating)")
        }
        consoleError.add("LGS threshold: ${convert_bg(threshold)}")

        // =====================================================================
        // RT object initialization
        // =====================================================================
        rT = RT(
            algorithm = APSResult.Algorithm.SMB,
            runningDynamicIsf = true,
            timestamp = currentTime,
            bg = bg,
            tick = tick,
            eventualBG = eventualBG,
            targetBG = target_bg,
            insulinReq = 0.0,
            deliverAt = deliverAt,
            sensitivityRatio = sensitivityRatio,
            consoleLog = consoleLog,
            consoleError = consoleError,
            variable_sens = sens,
            // Boost/DynISF fields for Nightscout upload — every field below is
            // emitted on every decision so the downstream analysis pipeline can
            // count records uniformly and detect "neutral" states explicitly.
            boostActive = profile.boostActive,
            predictionISF = round(profile.variable_sens, 1),
            sensNormalTarget = round(profile.sensNormalTarget, 1),
            tdd = if (profile.TDD > 0) round(profile.TDD, 1) else null,
            // tddRatio: emit even when neutral (1.0). Previously skipped via
            // `if (sensitivityRatio != null && sensitivityRatio != 1.0) ... else null`,
            // which made the field present in only ~60% of records.
            tddRatio = sensitivityRatio,
            deltaAcceleration = delta_accl,
            // boostProfileSwitch: emit on every decision, including 100% (no override).
            // Previously emitted only when != 100 which made it present in ~30% of records.
            boostProfileSwitch = profile.profileSwitch,
            // Initial defaults for fields populated later in the SMB block — these
            // ensure the field is always present even when SMB isn't allowed.
            boostTier = "NONE",
            fastCarbProtection = false,
            insulinReqPctEffective = 0.0
        )

        // =====================================================================
        // Prediction BG arrays
        // =====================================================================
        var COBpredBGs = mutableListOf<Double>()
        var aCOBpredBGs = mutableListOf<Double>()
        var IOBpredBGs = mutableListOf<Double>()
        var UAMpredBGs = mutableListOf<Double>()
        var ZTpredBGs = mutableListOf<Double>()
        COBpredBGs.add(bg)
        aCOBpredBGs.add(bg)
        IOBpredBGs.add(bg)
        ZTpredBGs.add(bg)
        UAMpredBGs.add(bg)

        var enableSMB = enable_smb(profile, microBolusAllowed, meal_data, target_bg)
        val enableUAM = profile.enableUAM

        var ci: Double
        val cid: Double
        ci = round((minDelta - bgi), 1)
        val uci = round((minDelta - bgi), 1)

        // Boost uses profile.sens for CSF (not autosens-adjusted)
        val csf = profile.sens / profile.carb_ratio
        consoleError.add("profile.sens: ${round(profile.sens, 1)}, sens: ${round(sens, 1)}, CSF: ${round(csf, 2)}")

        val maxCarbAbsorptionRate = 30
        val maxCI = round(maxCarbAbsorptionRate * csf * 5.0 / 60, 1)
        if (ci > maxCI) {
            consoleError.add("Limiting carb impact from $ci to $maxCI mg/dL/5m ($maxCarbAbsorptionRate g/h)")
            ci = maxCI
        }
        var remainingCATimeMin = 3.0 / sensitivityRatio
        val assumedCarbAbsorptionRate = 20
        var remainingCATime = remainingCATimeMin
        var lastCarbAge = 0
        if (meal_data.carbs != 0.0) {
            remainingCATimeMin = Math.max(remainingCATimeMin, meal_data.mealCOB / assumedCarbAbsorptionRate)
            lastCarbAge = round((systemTime - meal_data.lastCarbTime) / 60000.0)
            val fractionCOBAbsorbed = (meal_data.carbs - meal_data.mealCOB) / meal_data.carbs
            remainingCATime = remainingCATimeMin + 1.5 * lastCarbAge / 60
            remainingCATime = round(remainingCATime, 1)
            consoleError.add("Last carbs ${lastCarbAge} minutes ago; remainingCATime: ${remainingCATime}hours; ${round(fractionCOBAbsorbed * 100)}% carbs absorbed")
        }

        val totalCI = Math.max(0.0, ci / 5 * 60 * remainingCATime / 2)
        val totalCA = totalCI / csf
        val remainingCarbsCap: Int = min(90, profile.remainingCarbsCap)
        var remainingCarbs = max(0.0, meal_data.mealCOB - totalCA)
        remainingCarbs = Math.min(remainingCarbsCap.toDouble(), remainingCarbs)
        val remainingCIpeak = remainingCarbs * csf * 5 / 60 / (remainingCATime / 2)
        if (remainingCIpeak.isNaN()) {
            throw Exception("remainingCarbs=$remainingCarbs remainingCATime=$remainingCATime csf=$csf")
        }

        val slopeFromMaxDeviation = round(meal_data.slopeFromMaxDeviation, 2)
        val slopeFromMinDeviation = round(meal_data.slopeFromMinDeviation, 2)
        val slopeFromDeviations = Math.min(slopeFromMaxDeviation, -slopeFromMinDeviation / 3)

        val aci = 10
        if (ci == 0.0) {
            cid = 0.0
        } else {
            cid = min(remainingCATime * 60 / 5 / 2, Math.max(0.0, meal_data.mealCOB * csf / ci))
        }
        val acid = max(0.0, meal_data.mealCOB * csf / aci)
        consoleError.add("Carb Impact: $ci mg/dL per 5m; CI Duration: ${round(cid * 5 / 60 * 2, 1)} hours; remaining CI (~2h peak): ${round(remainingCIpeak, 1)} mg/dL per 5m")

        var minIOBPredBG = 999.0
        var minCOBPredBG = 999.0
        var minUAMPredBG = 999.0
        var minGuardBG: Double = bg
        var minCOBGuardBG = 999.0
        var minUAMGuardBG = 999.0
        var minIOBGuardBG = 999.0
        var minZTGuardBG = 999.0
        var minPredBG: Double
        var avgPredBG: Double
        var IOBpredBG: Double = eventualBG
        var maxIOBPredBG = bg
        var maxCOBPredBG = bg
        var maxUAMPredBG = bg
        val lastIOBpredBG: Double
        var lastCOBpredBG: Double? = null
        var lastUAMpredBG: Double? = null
        var UAMduration = 0.0
        var remainingCItotal = 0.0
        val remainingCIs = mutableListOf<Int>()
        val predCIs = mutableListOf<Int>()
        var UAMpredBG: Double? = null
        var COBpredBG: Double? = null
        var aCOBpredBG: Double?

        // =====================================================================
        // Prediction loop - Boost uses per-BG dynamic ISF (getIsfByProfile)
        // =====================================================================
        val insulinPeakTime = insulinPeak + 30
        val insulinPeak5m = (insulinPeakTime / 60.0) * 12.0

        iobArray.forEach { iobTick ->
            val predBGI: Double = round((-iobTick.activity * sens * 5), 2)

            // Boost: IOB predictions use dynamic ISF per predicted BG level
            val IOBpredBGI: Double = round((-iobTick.activity * getIsfByProfile(max(IOBpredBGs[IOBpredBGs.size - 1], 39.0), profile, true) * 5), 2)

            iobTick.iobWithZeroTemp ?: error("iobTick.iobWithZeroTemp missing")
            // Boost: ZT predictions also use dynamic ISF per predicted BG level
            val predZTBGI = round((-iobTick.iobWithZeroTemp!!.activity * getIsfByProfile(max(ZTpredBGs[ZTpredBGs.size - 1], 39.0), profile, true) * 5), 2)
            // Boost: UAM predictions use dynamic ISF per predicted BG level
            val predUAMBGI = round((-iobTick.activity * getIsfByProfile(max(UAMpredBGs[UAMpredBGs.size - 1], 39.0), profile, true) * 5), 2)

            val predDev: Double = ci * (1 - min(1.0, IOBpredBGs.size / (60.0 / 5.0)))
            IOBpredBG = IOBpredBGs[IOBpredBGs.size - 1] + IOBpredBGI + predDev
            val ZTpredBG = ZTpredBGs[ZTpredBGs.size - 1] + predZTBGI
            val predCI: Double = max(0.0, max(0.0, ci) * (1 - COBpredBGs.size / max(cid * 2, 1.0)))
            val predACI = max(0.0, max(0, aci) * (1 - COBpredBGs.size / max(acid * 2, 1.0)))
            val intervals = Math.min(COBpredBGs.size.toDouble(), ((remainingCATime * 12) - COBpredBGs.size))
            val remainingCI = Math.max(0.0, intervals / (remainingCATime / 2 * 12) * remainingCIpeak)
            if (remainingCI.isNaN()) {
                throw Exception("remainingCI=$remainingCI intervals=$intervals remainingCIpeak=$remainingCIpeak")
            }
            remainingCItotal += predCI + remainingCI
            remainingCIs.add(round(remainingCI))
            predCIs.add(round(predCI))
            COBpredBG = COBpredBGs[COBpredBGs.size - 1] + predBGI + min(0.0, predDev) + predCI + remainingCI
            aCOBpredBG = aCOBpredBGs[aCOBpredBGs.size - 1] + predBGI + min(0.0, predDev) + predACI
            val predUCIslope = max(0.0, uci + (UAMpredBGs.size * slopeFromDeviations))
            val predUCImax = max(0.0, uci * (1 - UAMpredBGs.size / max(3.0 * 60 / 5, 1.0)))
            val predUCI = min(predUCIslope, predUCImax)
            if (predUCI > 0) {
                UAMduration = round((UAMpredBGs.size + 1) * 5 / 60.0, 1)
            }
            UAMpredBG = UAMpredBGs[UAMpredBGs.size - 1] + predUAMBGI + min(0.0, predDev) + predUCI

            if (IOBpredBGs.size < 48) IOBpredBGs.add(IOBpredBG)
            if (COBpredBGs.size < 48) COBpredBGs.add(COBpredBG)
            if (aCOBpredBGs.size < 48) aCOBpredBGs.add(aCOBpredBG)
            if (UAMpredBGs.size < 48) UAMpredBGs.add(UAMpredBG)
            if (ZTpredBGs.size < 48) ZTpredBGs.add(ZTpredBG)

            if (COBpredBG < minCOBGuardBG) minCOBGuardBG = round(COBpredBG).toDouble()
            if (UAMpredBG < minUAMGuardBG) minUAMGuardBG = round(UAMpredBG).toDouble()
            if (IOBpredBG < minIOBGuardBG) minIOBGuardBG = IOBpredBG
            if (ZTpredBG < minZTGuardBG) minZTGuardBG = round(ZTpredBG, 0)

            if (IOBpredBGs.size > insulinPeak5m && (IOBpredBG < minIOBPredBG)) minIOBPredBG = round(IOBpredBG, 0)
            if (IOBpredBG > maxIOBPredBG) maxIOBPredBG = IOBpredBG
            if ((cid != 0.0 || remainingCIpeak > 0) && COBpredBGs.size > insulinPeak5m && (COBpredBG < minCOBPredBG)) minCOBPredBG = round(COBpredBG, 0)
            if ((cid != 0.0 || remainingCIpeak > 0) && COBpredBG > maxIOBPredBG) maxCOBPredBG = COBpredBG
            if (enableUAM && UAMpredBGs.size > 12 && (UAMpredBG < minUAMPredBG)) minUAMPredBG = round(UAMpredBG, 0)
            if (enableUAM && UAMpredBG!! > maxIOBPredBG) maxUAMPredBG = UAMpredBG!!
        }

        if (meal_data.mealCOB > 0) {
            consoleError.add("predCIs (mg/dL/5m):" + predCIs.joinToString(separator = " "))
            consoleError.add("remainingCIs:      " + remainingCIs.joinToString(separator = " "))
        }
        rT.predBGs = Predictions()
        IOBpredBGs = IOBpredBGs.map { round(min(401.0, max(39.0, it)), 0) }.toMutableList()
        for (i in IOBpredBGs.size - 1 downTo 13) {
            if (IOBpredBGs[i - 1] != IOBpredBGs[i]) break
            else IOBpredBGs.removeAt(IOBpredBGs.lastIndex)
        }
        rT.predBGs?.IOB = IOBpredBGs.map { it.toInt() }
        lastIOBpredBG = round(IOBpredBGs[IOBpredBGs.size - 1]).toDouble()
        ZTpredBGs = ZTpredBGs.map { round(min(401.0, max(39.0, it)), 0) }.toMutableList()
        for (i in ZTpredBGs.size - 1 downTo 7) {
            if (ZTpredBGs[i - 1] >= ZTpredBGs[i] || ZTpredBGs[i] <= target_bg) break
            else ZTpredBGs.removeAt(ZTpredBGs.lastIndex)
        }
        rT.predBGs?.ZT = ZTpredBGs.map { it.toInt() }
        if (meal_data.mealCOB > 0) {
            aCOBpredBGs = aCOBpredBGs.map { round(min(401.0, max(39.0, it)), 0) }.toMutableList()
            for (i in aCOBpredBGs.size - 1 downTo 13) {
                if (aCOBpredBGs[i - 1] != aCOBpredBGs[i]) break
                else aCOBpredBGs.removeAt(aCOBpredBGs.lastIndex)
            }
        }
        if (meal_data.mealCOB > 0 && (ci > 0 || remainingCIpeak > 0)) {
            COBpredBGs = COBpredBGs.map { round(min(401.0, max(39.0, it)), 0) }.toMutableList()
            for (i in COBpredBGs.size - 1 downTo 13) {
                if (COBpredBGs[i - 1] != COBpredBGs[i]) break
                else COBpredBGs.removeAt(COBpredBGs.lastIndex)
            }
            rT.predBGs?.COB = COBpredBGs.map { it.toInt() }
            lastCOBpredBG = COBpredBGs[COBpredBGs.size - 1]
            eventualBG = max(eventualBG, round(COBpredBGs[COBpredBGs.size - 1], 0))
        }
        if (ci > 0 || remainingCIpeak > 0) {
            if (enableUAM) {
                UAMpredBGs = UAMpredBGs.map { round(min(401.0, max(39.0, it)), 0) }.toMutableList()
                for (i in UAMpredBGs.size - 1 downTo 13) {
                    if (UAMpredBGs[i - 1] != UAMpredBGs[i]) break
                    else UAMpredBGs.removeAt(UAMpredBGs.lastIndex)
                }
                rT.predBGs?.UAM = UAMpredBGs.map { it.toInt() }
                lastUAMpredBG = UAMpredBGs[UAMpredBGs.size - 1]
                eventualBG = max(eventualBG, round(UAMpredBGs[UAMpredBGs.size - 1], 0))
            }
            rT.eventualBG = eventualBG
        }

        consoleError.add("UAM Impact: $uci mg/dL per 5m; UAM Duration: $UAMduration hours")
        consoleLog.add("EventualBG is $eventualBG")

        minIOBPredBG = max(39.0, minIOBPredBG)
        minCOBPredBG = max(39.0, minCOBPredBG)
        minUAMPredBG = max(39.0, minUAMPredBG)
        minPredBG = round(minIOBPredBG, 0)

        // =====================================================================
        // Boost-specific: future_sens calculation for dosing
        // Uses getIsfByProfile (uncapped) with Boost-specific weighting conditions
        // =====================================================================
        val boostActive = profile.boostActive
        val sensBgCap = profile.dynISFBgCap
        val fsens_bg = if (eventualBG > sensBgCap) (sensBgCap + ((eventualBG - sensBgCap) / 2)) else eventualBG
        if (fsens_bg != eventualBG)
            consoleLog.add("Dosing sensitivity increasing slowly from $sensBgCap mg/dl")

        var future_sens: Double
        if (boostActive && meal_data.mealCOB > 0 && delta_accl > 0) {
            // COB with acceleration: weight toward eventual BG
            future_sens = getIsfByProfile((fsens_bg * 0.75) + (sens_bg * 0.25), profile, false)
            consoleLog.add("Future state sensitivity is $future_sens weighted on eventual BG due to COB")
            rT.reason.append("Dosing sensitivity: $future_sens weighted on predicted BG due to COB;")
        } else if (boostActive && glucose_status.delta > 4 && delta_accl > 10 && bg < 180 && eventualBG > bg) {
            // Rapidly accelerating delta: 50/50 eventual and current
            future_sens = getIsfByProfile((fsens_bg * 0.5) + (sens_bg * 0.5), profile, false)
            consoleLog.add("Future state sensitivity is $future_sens weighted on predicted bg due to increasing deltas")
            rT.reason.append("Dosing sensitivity: $future_sens weighted on predicted BG due to delta;")
        } else if (bg > 180 && glucose_status.delta < 2 && glucose_status.delta > -2 && glucose_status.shortAvgDelta > -2 && glucose_status.shortAvgDelta < 2 && glucose_status.longAvgDelta > -2 && glucose_status.longAvgDelta < 2) {
            // Flat high BG: weight toward minPredBG and current
            future_sens = getIsfByProfile((minPredBG * 0.25) + (sens_bg * 0.75), profile, false)
            consoleLog.add("Future state sensitivity is $future_sens due to flat high glucose")
            rT.reason.append("Dosing sensitivity: $future_sens using current BG;")
        } else if (glucose_status.delta > 0 && delta_accl > 1 || eventualBG > bg) {
            // Rising: use current BG
            future_sens = getIsfByProfile(sens_bg, profile, false)
            consoleLog.add("Future state sensitivity is $future_sens based on current bg due to +ve delta")
        } else {
            // Falling: use minPredBG
            future_sens = getIsfByProfile(max(minPredBG, 1.0), profile, false)
            consoleLog.add("Future state sensitivity is $future_sens based on min predicted bg due to -ve delta")
            rT.reason.append("Dosing sensitivity: $future_sens using eventual BG;")
        }
        future_sens = round(future_sens, 1)
        consoleLog.add("Future sens adjusted to: $future_sens")
        rT.dynamicISF = future_sens

        // =====================================================================
        // minPredBG calculation (same as standard oref1)
        // =====================================================================
        val fractionCarbsLeft = meal_data.mealCOB / meal_data.carbs
        if (minUAMPredBG < 999 && minCOBPredBG < 999) {
            avgPredBG = round((1 - fractionCarbsLeft) * UAMpredBG!! + fractionCarbsLeft * COBpredBG!!, 0)
        } else if (minCOBPredBG < 999) {
            avgPredBG = round((IOBpredBG + COBpredBG!!) / 2.0, 0)
        } else if (minUAMPredBG < 999) {
            avgPredBG = round((IOBpredBG + UAMpredBG!!) / 2.0, 0)
        } else {
            avgPredBG = round(IOBpredBG, 0)
        }
        if (minZTGuardBG > avgPredBG) {
            avgPredBG = minZTGuardBG
        }

        if ((cid > 0.0 || remainingCIpeak > 0)) {
            if (enableUAM) {
                minGuardBG = fractionCarbsLeft * minCOBGuardBG + (1 - fractionCarbsLeft) * minUAMGuardBG
            } else {
                minGuardBG = minCOBGuardBG
            }
        } else if (enableUAM) {
            minGuardBG = minUAMGuardBG
        } else {
            minGuardBG = minIOBGuardBG
        }
        minGuardBG = round(minGuardBG, 0)

        var minZTUAMPredBG = minUAMPredBG
        if (minZTGuardBG < threshold) {
            minZTUAMPredBG = (minUAMPredBG + minZTGuardBG) / 2.0
        } else if (minZTGuardBG < target_bg) {
            val blendPct = (minZTGuardBG - threshold) / (target_bg - threshold)
            val blendedMinZTGuardBG = minUAMPredBG * blendPct + minZTGuardBG * (1 - blendPct)
            minZTUAMPredBG = (minUAMPredBG + blendedMinZTGuardBG) / 2.0
        } else if (minZTGuardBG > minUAMPredBG) {
            minZTUAMPredBG = (minUAMPredBG + minZTGuardBG) / 2.0
        }
        minZTUAMPredBG = round(minZTUAMPredBG, 0)

        if (meal_data.carbs != 0.0) {
            if (!enableUAM && minCOBPredBG < 999) {
                minPredBG = round(max(minIOBPredBG, minCOBPredBG), 0)
            } else if (minCOBPredBG < 999) {
                val blendedMinPredBG = fractionCarbsLeft * minCOBPredBG + (1 - fractionCarbsLeft) * minZTUAMPredBG
                minPredBG = round(max(minIOBPredBG, max(minCOBPredBG, blendedMinPredBG)), 0)
            } else if (enableUAM) {
                minPredBG = minZTUAMPredBG
            } else {
                minPredBG = minGuardBG
            }
        } else if (enableUAM) {
            minPredBG = round(max(minIOBPredBG, minZTUAMPredBG), 0)
        }
        minPredBG = min(minPredBG, avgPredBG)

        consoleLog.add("minPredBG: $minPredBG minIOBPredBG: $minIOBPredBG minZTGuardBG: $minZTGuardBG")
        if (minCOBPredBG < 999) consoleLog.add(" minCOBPredBG: $minCOBPredBG")
        if (minUAMPredBG < 999) consoleLog.add(" minUAMPredBG: $minUAMPredBG")
        consoleError.add("avgPredBG: ${round(avgPredBG, 0)} | COB: ${round(meal_data.mealCOB, 1)} / ${round(meal_data.carbs, 1)}")
        if (maxCOBPredBG > bg) {
            minPredBG = min(minPredBG, maxCOBPredBG)
        }

        rT.COB = meal_data.mealCOB
        rT.IOB = iob_data.iob
        rT.reason.append(
            "COB: ${round(meal_data.mealCOB, 1).withoutZeros()}, Dev: ${convert_bg(deviation.toDouble())}, BGI: ${convert_bg(bgi)}, ISF: ${convert_bg(sens)}, CR: ${
                round(profile.carb_ratio, 2).withoutZeros()
            }, Target: ${convert_bg(target_bg)}, minPredBG ${convert_bg(minPredBG)}, minGuardBG ${convert_bg(minGuardBG)}, IOBpredBG ${convert_bg(lastIOBpredBG)}"
        )
        if (lastCOBpredBG != null) {
            rT.reason.append(", COBpredBG " + convert_bg(lastCOBpredBG.toDouble()))
        }
        if (lastUAMpredBG != null) {
            rT.reason.append(", UAMpredBG " + convert_bg(lastUAMpredBG.toDouble()))
        }
        rT.reason.append("; ")

        var carbsReqBG = naive_eventualBG
        if (carbsReqBG < 40) {
            carbsReqBG = min(minGuardBG, carbsReqBG)
        }
        var bgUndershoot: Double = threshold - carbsReqBG
        var minutesAboveMinBG = 240
        var minutesAboveThreshold = 240
        if (meal_data.mealCOB > 0 && (ci > 0 || remainingCIpeak > 0)) {
            for (i in COBpredBGs.indices) {
                if (COBpredBGs[i] < min_bg) { minutesAboveMinBG = 5 * i; break }
            }
            for (i in COBpredBGs.indices) {
                if (COBpredBGs[i] < threshold) { minutesAboveThreshold = 5 * i; break }
            }
        } else {
            for (i in IOBpredBGs.indices) {
                if (IOBpredBGs[i] < min_bg) { minutesAboveMinBG = 5 * i; break }
            }
            for (i in IOBpredBGs.indices) {
                if (IOBpredBGs[i] < threshold) { minutesAboveThreshold = 5 * i; break }
            }
        }

        if (enableSMB && minGuardBG < threshold) {
            consoleError.add("minGuardBG ${convert_bg(minGuardBG)} projected below ${convert_bg(threshold)} - disabling SMB")
            enableSMB = false
        }
        // Boost uses 30% maxDelta threshold (vs 20% in standard)
        if (maxDelta > 0.30 * bg) {
            consoleError.add("maxDelta ${convert_bg(maxDelta)} > 30% of BG ${convert_bg(bg)} - disabling SMB")
            rT.reason.append("maxDelta ${convert_bg(maxDelta)} > 30% of BG ${convert_bg(bg)}: SMB disabled; ")
            enableSMB = false
        }

        consoleError.add("── Predictions ─────────────────────────────")
        consoleError.add("Above min_bg (${convert_bg(min_bg)}): ${minutesAboveMinBG}m")
        if (minutesAboveThreshold < 240 || minutesAboveMinBG < 60) {
            consoleError.add("Above threshold (${convert_bg(threshold)}): ${minutesAboveThreshold}m")
        }
        val zeroTempDuration = minutesAboveThreshold
        val zeroTempEffectDouble = profile.current_basal * sens * zeroTempDuration / 60
        val COBforCarbsReq = max(0.0, meal_data.mealCOB - 0.25 * meal_data.carbs)
        val carbsReq = round(((bgUndershoot - zeroTempEffectDouble) / csf - COBforCarbsReq))
        val zeroTempEffect = round(zeroTempEffectDouble)
        consoleError.add("naive_eventualBG: ${round(naive_eventualBG, 0)} | bgUndershoot: ${round(bgUndershoot, 1)} | zeroTempDuration: ${zeroTempDuration}m | zeroTempEffect: $zeroTempEffect | carbsReq: $carbsReq")
        if (carbsReq >= profile.carbsReqThreshold && minutesAboveThreshold <= 45) {
            rT.carbsReq = carbsReq
            rT.carbsReqWithin = minutesAboveThreshold
            rT.reason.append("$carbsReq add\'l carbs req w/in ${minutesAboveThreshold}m; ")
        }

        // =====================================================================
        // Low glucose suspend logic (Boost uses -40min IOB threshold vs -20min in standard)
        // =====================================================================
        if (bg < threshold && iob_data.iob < -profile.current_basal * 40 / 60 && minDelta > 0 && minDelta > expectedDelta) {
            rT.reason.append("IOB ${iob_data.iob} < ${round(-profile.current_basal * 20 / 60, 2)}")
            rT.reason.append(" and minDelta ${convert_bg(minDelta)} > expectedDelta ${convert_bg(expectedDelta)}; ")
        } else if (bg < threshold || minGuardBG < threshold) {
            rT.reason.append("minGuardBG ${convert_bg(minGuardBG)} < ${convert_bg(threshold)}")
            bgUndershoot = target_bg - minGuardBG
            val worstCaseInsulinReq = bgUndershoot / sens
            var durationReq = round(60 * worstCaseInsulinReq / profile.current_basal)
            durationReq = round(durationReq / 30.0) * 30
            durationReq = min(120, max(30, durationReq))
            return setTempBasal(0.0, durationReq, profile, rT, currenttemp)
        }

        // cancel temps before the top of the hour
        val minutes = Instant.ofEpochMilli(rT.deliverAt!!).atZone(ZoneId.systemDefault()).toLocalDateTime().minute
        if (profile.skip_neutral_temps && minutes >= 55) {
            rT.reason.append("; Canceling temp at $minutes m past the hour. ")
            return setTempBasal(0.0, 0, profile, rT, currenttemp)
        }

        // =====================================================================
        // eventualBG below target
        // =====================================================================
        if (eventualBG < min_bg) {
            rT.reason.append("Eventual BG ${convert_bg(eventualBG)} < ${convert_bg(min_bg)}")
            if (minDelta > expectedDelta && minDelta > 0 && carbsReq == 0) {
                if (naive_eventualBG < 40) {
                    rT.reason.append(", naive_eventualBG < 40. ")
                    return setTempBasal(0.0, 30, profile, rT, currenttemp)
                }
                if (glucose_status.delta > minDelta) {
                    rT.reason.append(", but Delta ${convert_bg(tick.toDouble())} > expectedDelta ${convert_bg(expectedDelta)}")
                } else {
                    rT.reason.append(", but Min. Delta ${minDelta.toFixed2()} > Exp. Delta ${convert_bg(expectedDelta)}")
                }
                if (currenttemp.duration > 15 && (round_basal(basal) == round_basal(currenttemp.rate))) {
                    rT.reason.append(", temp ${currenttemp.rate} ~ req ${round(basal, 2).withoutZeros()}U/hr. ")
                    return rT
                } else {
                    rT.reason.append("; setting current basal of ${round(basal, 2)} as temp. ")
                    return setTempBasal(basal, 30, profile, rT, currenttemp)
                }
            }

            // Boost: uses future_sens for low-temp insulin calculation
            var insulinReq = 2 * min(0.0, (eventualBG - target_bg) / future_sens)
            insulinReq = round(insulinReq, 2)
            var naiveInsulinReq = min(0.0, (naive_eventualBG - target_bg) / sens)
            naiveInsulinReq = round(naiveInsulinReq, 2)
            if (minDelta < 0 && minDelta > expectedDelta) {
                val newinsulinReq = round((insulinReq * (minDelta / expectedDelta)), 2)
                insulinReq = newinsulinReq
            }
            var rate = basal + (2 * insulinReq)
            rate = round_basal(rate)

            val insulinScheduled = currenttemp.duration * (currenttemp.rate - basal) / 60
            val minInsulinReq = Math.min(insulinReq, naiveInsulinReq)
            if (insulinScheduled < minInsulinReq - basal * 0.3) {
                rT.reason.append(", ${currenttemp.duration}m@${(currenttemp.rate).toFixed2()} is a lot less than needed. ")
                return setTempBasal(rate, 30, profile, rT, currenttemp)
            }
            if (currenttemp.duration > 5 && rate >= currenttemp.rate * 0.8) {
                rT.reason.append(", temp ${currenttemp.rate} ~< req ${round(rate, 2)}U/hr. ")
                return rT
            } else {
                if (rate <= 0) {
                    bgUndershoot = (target_bg - naive_eventualBG)
                    val worstCaseInsulinReq = bgUndershoot / sens
                    var durationReq = round(60 * worstCaseInsulinReq / profile.current_basal)
                    if (durationReq < 0) {
                        durationReq = 0
                    } else {
                        durationReq = round(durationReq / 30.0) * 30
                        durationReq = min(120, max(0, durationReq))
                    }
                    if (durationReq > 0) {
                        rT.reason.append(", setting ${durationReq}m zero temp. ")
                        return setTempBasal(rate, durationReq, profile, rT, currenttemp)
                    }
                } else {
                    rT.reason.append(", setting ${round(rate, 2)}U/hr. ")
                }
                return setTempBasal(rate, 30, profile, rT, currenttemp)
            }
        }

        // =====================================================================
        // eventualBG above min but BG falling faster than expected
        // =====================================================================
        if (minDelta < expectedDelta) {
            if (!(microBolusAllowed && enableSMB)) {
                if (glucose_status.delta < minDelta) {
                    rT.reason.append("Eventual BG ${convert_bg(eventualBG)} > ${convert_bg(min_bg)} but Delta ${convert_bg(tick.toDouble())} < Exp. Delta ${convert_bg(expectedDelta)}")
                } else {
                    rT.reason.append("Eventual BG ${convert_bg(eventualBG)} > ${convert_bg(min_bg)} but Min. Delta ${minDelta.toFixed2()} < Exp. Delta ${convert_bg(expectedDelta)}")
                }
                if (currenttemp.duration > 15 && (round_basal(basal) == round_basal(currenttemp.rate))) {
                    rT.reason.append(", temp ${currenttemp.rate} ~ req ${round(basal, 2).withoutZeros()}U/hr. ")
                    return rT
                } else {
                    rT.reason.append("; setting current basal of ${round(basal, 2)} as temp. ")
                    return setTempBasal(basal, 30, profile, rT, currenttemp)
                }
            }
        }

        // eventualBG or minPredBG is below max_bg
        if (min(eventualBG, minPredBG) < max_bg) {
            if (!(microBolusAllowed && enableSMB)) {
                rT.reason.append("${convert_bg(eventualBG)}-${convert_bg(minPredBG)} in range: no temp required")
                if (currenttemp.duration > 15 && (round_basal(basal) == round_basal(currenttemp.rate))) {
                    rT.reason.append(", temp ${currenttemp.rate} ~ req ${round(basal, 2).withoutZeros()}U/hr. ")
                    return rT
                } else {
                    rT.reason.append("; setting current basal of ${round(basal, 2)} as temp. ")
                    return setTempBasal(basal, 30, profile, rT, currenttemp)
                }
            }
        }

        // eventual BG is at/above target
        if (eventualBG >= max_bg) {
            rT.reason.append("Eventual BG ${convert_bg(eventualBG)} >= ${convert_bg(max_bg)}, ")
        }
        if (iob_data.iob > max_iob) {
            rT.reason.append("IOB ${round(iob_data.iob, 2)} > max_iob $max_iob")
            if (currenttemp.duration > 15 && (round_basal(basal) == round_basal(currenttemp.rate))) {
                rT.reason.append(", temp ${currenttemp.rate} ~ req ${round(basal, 2).withoutZeros()}U/hr. ")
                return rT
            } else {
                rT.reason.append("; setting current basal of ${round(basal, 2)} as temp. ")
                return setTempBasal(basal, 30, profile, rT, currenttemp)
            }
        } else {
            // =====================================================================
            // MAIN HIGH-TEMP / SMB DOSING SECTION - Boost version
            // =====================================================================

            // insulinReq uses future_sens (Boost-specific dosing sensitivity)
            var insulinReq = round((min(minPredBG, eventualBG) - target_bg) / future_sens, 2)
            if (insulinReq > max_iob - iob_data.iob) {
                rT.reason.append("max_iob $max_iob, ")
                insulinReq = max_iob - iob_data.iob
            }

            var rate = basal + (2 * insulinReq)
            rate = round_basal(rate)
            insulinReq = round(insulinReq, 3)
            rT.insulinReq = insulinReq

            val lastBolusAge = round((systemTime - iob_data.lastBolusTime) / 60000.0, 1)

            if (microBolusAllowed && enableSMB && bg > threshold) {
                val mealInsulinReq = round(meal_data.mealCOB / profile.carb_ratio, 3)
                var maxBolus: Double
                if (iob_data.iob > -0.2) {
                    consoleError.add("IOB ${round(iob_data.iob, 2)} > -0.2; maxUAMSMBBasalMinutes: ${profile.maxUAMSMBBasalMinutes} × basal ${round(profile.current_basal, 2)}")
                    maxBolus = round(profile.current_basal * profile.maxUAMSMBBasalMinutes / 60.0, 1)
                } else {
                    consoleError.add("IOB ${round(iob_data.iob, 2)} ≤ -0.2; maxSMBBasalMinutes: ${profile.maxSMBBasalMinutes} × basal ${round(profile.current_basal, 2)}")
                    maxBolus = round(profile.current_basal * profile.maxSMBBasalMinutes / 60.0, 1)
                }

                // =============================================================
                // BOOST SMB SIZING LOGIC - Multi-tier escalation
                // =============================================================
                val roundSMBTo = 1.0 / profile.bolus_increment
                val profileSwitch = profile.profileSwitch

                var insulinReqPCT = 100.0 / profile.Boost_InsulinReq
                val insulinPCTsubtract = insulinReqPCT - 1

                // Sliding scale variables
                val bga = abs(bg - 180)
                val bg_adjust = bga / 40.0

                var insulinDivisor: Double
                val scale_pct: Double
                if (profile.enableBoostPercentScale) {
                    scale_pct = round(100.0 / (profile.boost_percent_scale * (profileSwitch / 100.0)), 3)
                    insulinDivisor = if (bg < 108) {
                        scale_pct
                    } else {
                        insulinReqPCT - ((abs(bg - 180) / 72) * (insulinReqPCT - scale_pct))
                    }
                } else {
                    scale_pct = insulinReqPCT // fallback
                    insulinDivisor = insulinReqPCT
                }

                // Boost factors
                val uamBoost1 = if (abs(glucose_status.shortAvgDelta) > 0.001) glucose_status.delta / glucose_status.shortAvgDelta else 0.0
                val uamBoost2 = if (abs(glucose_status.longAvgDelta) > 0.001) abs(glucose_status.delta / glucose_status.longAvgDelta) else 0.0

                // Fast-carb rebound detection:
                // If BG was genuinely low (< 72) within the last 60 min and is now rising fast
                // with no logged carbs, this is likely a fast-carb rescue response.
                // UAM/Acceleration tiers would fire aggressively here (uamBoost2 inflated by
                // the recent fall), risking insulin stacking onto an unannounced carb rise.
                // Suppress Tiers 3, 5, 6 and let Tier 7 (mild) handle it instead.
                // Two detection signals, either sufficient (COB=0, delta_accl>25 required for both):
                // 1. recentLowBG < 100: BG was in low-normal range within the last 60 min —
                //    covers fast carbs eaten from or near target (the common treatment scenario).
                // 2. reversalScore > 30: delta × |longAvgDelta| when longAvgDelta<0 and delta>0 —
                //    captures fast carbs eaten from a falling high BG where the long average still
                //    reflects the preceding fall. Fires even if BG never dropped below 100.
                //    With flat longAvgDelta (±2 mg/dL) reversalScore ≈ delta×2, so requires
                //    delta > 15 to exceed threshold — appropriately conservative.
                // Validated: 12/12 fast-carb recall (corrected lookback), 3–4 meal FPs (unlogged).
                val lowTriggered      = profile.recentLowBG < 100.0
                val reversalScore     = if (glucose_status.longAvgDelta < 0 && glucose_status.delta > 0)
                    glucose_status.delta * Math.abs(glucose_status.longAvgDelta) else 0.0
                val reversalTriggered = reversalScore > 30.0
                val fastCarbRebound   = (lowTriggered || reversalTriggered)
                    && meal_data.mealCOB == 0.0
                    && bg < 170.0
                    && delta_accl > 25.0
                rT.fastCarbProtection = fastCarbRebound
                if (fastCarbRebound) {
                    val trigger = when {
                        lowTriggered && reversalTriggered -> "low ${round(profile.recentLowBG, 0)} rev ${round(reversalScore, 0)}"
                        lowTriggered      -> "low ${round(profile.recentLowBG, 0)}"
                        else              -> "rev ${round(reversalScore, 0)}"
                    }
                    consoleError.add("Fast-carb rebound detected ($trigger, accl ${round(delta_accl, 1)}): BG=$bg — UAM/Accel boost suppressed")
                    rT.reason.append("Fast-carb rebound ($trigger→$bg): boost suppressed; ")
                }

                val boostMaxIOB = profile.boost_maxIOB
                val boost_max = profile.boost_bolus
                val boost_scale = profile.boost_scale * (profileSwitch / 100.0)
                var boostInsulinReq = basal

                val COB = meal_data.mealCOB
                val CR = profile.carb_ratio

                consoleError.add("── SMB Dosing ──────────────────────────────")
                consoleError.add("InsulinReq%: ${round((1.0 / insulinReqPCT) * 100, 1)}% | Divisor: ${round(insulinDivisor, 2)} (${round((1.0 / insulinDivisor) * 100, 1)}%)")
                if (profile.enableBoostPercentScale) {
                    consoleError.add("Percent scale: ${round(100.0 / scale_pct, 1)}% from ${profile.boost_percent_scale}")
                }
                consoleError.add("insulinReq: $insulinReq | UAM Boost1: ${round(uamBoost1, 2)} | UAM Boost2: ${round(uamBoost2, 2)}")
                consoleError.add("Boost scale: ${round(boost_scale, 2)} (from ${round(profile.boost_scale, 2)}) | Max bolus: $boost_max | MaxIOB: $boostMaxIOB")
                consoleError.add("Boost ${if (!boostActive) "IN" else ""}ACTIVE | Base insulin: ${round(boostInsulinReq, 2)}U | delta_accl: $delta_accl")
                rT.reason.append("UAM Boost 1: ${round(uamBoost1, 2)}; UAM Boost 2: ${round(uamBoost2, 2)}; Delta: ${glucose_status.delta}; ShortAvg: ${glucose_status.shortAvgDelta}; ")

                var microBolus: Double

                // Decision tree debug
                consoleError.add("── Tier Decision ───────────────────────────")
                consoleError.add("bg=$bg | delta=${round(glucose_status.delta, 1)} | shortAvg=${round(glucose_status.shortAvgDelta, 1)} | delta_accl=$delta_accl")
                consoleError.add("eventualBG=${round(eventualBG, 0)} | target=$target_bg | IOB=${round(iob_data.iob, 2)}/$boostMaxIOB | COB=$COB | lastCarbAge=$lastCarbAge")

                // ----- Tier 1: Primary COB handling (< 25 min since carbs) -----
                if (boostActive && COB > 0 && lastCarbAge < 25) {
                    consoleError.add(">>> TIER 1: Primary COB handling <<<")
                    rT.boostTier = "COB_PRIMARY"
                    rT.insulinReqPctEffective = round((1.0 / insulinReqPCT) * 100, 1)
                    rT.reason.append("Primary carb handling code operating; lastCarbAge: $lastCarbAge; ")
                    microBolus = Math.floor(min(insulinReq / insulinReqPCT, insulinReq) * roundSMBTo) / roundSMBTo
                    consoleError.add("Insulin required % (${(1.0 / insulinReqPCT) * 100}%) applied.")
                }
                // ----- Tier 2: Secondary COB handling (< 40 min, delta > 5) -----
                else if (boostActive && COB > 0 && lastCarbAge < 40 && glucose_status.delta > 5) {
                    consoleError.add(">>> TIER 2: Secondary COB handling <<<")
                    rT.boostTier = "COB_SECONDARY"
                    rT.insulinReqPctEffective = round((1.0 / insulinReqPCT) * 100, 1)
                    val cob_boost_max = max((COB / CR) / insulinReqPCT, boost_max)
                    rT.reason.append("Secondary carb handling; boost_max due to COB = $cob_boost_max; lastCarbAge: $lastCarbAge; ")
                    microBolus = Math.floor(min(insulinReq / insulinReqPCT, cob_boost_max) * roundSMBTo) / roundSMBTo
                    consoleError.add("Insulin required % (${(1.0 / insulinReqPCT) * 100}%) applied.")
                }
                // ----- Tier 3: UAM Boost (strong acceleration with positive delta) -----
                else if (!fastCarbRebound && glucose_status.delta >= 5 && glucose_status.shortAvgDelta >= 3 && uamBoost1 > 1.2 && uamBoost2 > 2 && boostActive && iob_data.iob < boostMaxIOB && boost_scale < 3 && eventualBG > target_bg && bg > 80 && insulinReq > 0) {
                    consoleError.add(">>> TIER 3: UAM Boost <<<")
                    rT.boostTier = "UAM_BOOST"
                    consoleError.add("Insulin required pre-boost is $insulinReq")
                    boostInsulinReq = min(boost_scale * boostInsulinReq, boost_max)
                    if (boostInsulinReq > boostMaxIOB - iob_data.iob) {
                        boostInsulinReq = boostMaxIOB - iob_data.iob
                    }
                    if (delta_accl > 1) {
                        insulinReqPCT = insulinDivisor
                    }
                    if (boostInsulinReq < (insulinReq / insulinReqPCT)) {
                        microBolus = Math.floor(min(insulinReq / insulinReqPCT, boost_max) * roundSMBTo) / roundSMBTo
                        rT.reason.append("UAM Boost enacted; SMB equals $microBolus; ")
                    } else {
                        microBolus = Math.floor(min(boostInsulinReq, boost_max) * roundSMBTo) / roundSMBTo
                    }
                    iTimeActive = true
                    consoleError.add("UAM Boost enacted; SMB equals $boostInsulinReq; Original insulin requirement was $insulinReq")
                    rT.reason.append("UAM Boost enacted; SMB equals $boostInsulinReq; ")
                }
                // ----- Tier 4: UAM High Boost (high BG > 180 with acceleration) -----
                else if (delta_accl > 5 && bg > 180 && boostActive && iob_data.iob < boostMaxIOB && boost_scale < 3 && eventualBG > target_bg && bg > 80 && insulinReq > 0) {
                    consoleError.add(">>> TIER 4: UAM High Boost <<<")
                    rT.boostTier = "UAM_HIGH_BOOST"
                    consoleError.add("Insulin required pre-boost is $insulinReq")
                    boostInsulinReq = min(boost_scale * boostInsulinReq, boost_max)
                    if (boostInsulinReq > boostMaxIOB - iob_data.iob) {
                        boostInsulinReq = boostMaxIOB - iob_data.iob
                    }
                    if (boostInsulinReq < (insulinReq / insulinReqPCT)) {
                        boostInsulinReq = min(boostInsulinReq + (0.5 * (insulinReq / insulinReqPCT)), insulinReq / insulinReqPCT)
                        microBolus = Math.floor(min(boostInsulinReq / insulinReqPCT, boost_max) * roundSMBTo) / roundSMBTo
                        rT.reason.append("UAM High Boost enacted; SMB equals $microBolus; ")
                    } else {
                        microBolus = Math.floor(min(boostInsulinReq, boost_max) * roundSMBTo) / roundSMBTo
                    }
                    consoleError.add("UAM High Boost enacted; SMB equals $boostInsulinReq; Original insulin requirement was $insulinReq")
                }
                // ----- Tier 5: Percent scale (BG 98-180, delta > 3, accelerating) -----
                else if (!fastCarbRebound && bg > 110 && bg < 181 && glucose_status.delta > 3 && delta_accl > 0 && eventualBG > target_bg && iob_data.iob < boostMaxIOB && boostActive) {
                    consoleError.add(">>> TIER 5: Percent Scale <<<")
                    rT.boostTier = "PERCENT_SCALE"
                    if (insulinReq > boostMaxIOB - iob_data.iob) {
                        insulinReq = boostMaxIOB - iob_data.iob
                    }
                    if (insulinReq < 0) {
                        insulinDivisor = insulinReqPCT - ((abs(bg - 180) / 72) * (insulinReqPCT - (2 * scale_pct)))
                        insulinReq = boostInsulinReq
                        consoleError.add("Increased SMB as insulin required < 0")
                    }
                    microBolus = Math.floor(min(insulinReq / insulinDivisor, boost_max) * roundSMBTo) / roundSMBTo
                    rT.reason.append("Increased SMB as percentage of insulin required to ${(1.0 / insulinDivisor) * 100}%. SMB is $microBolus; ")
                    iTimeActive = true
                    consoleError.add("Post percent scale trigger state: $iTimeActive")
                }
                // ----- Tier 6: Acceleration bolus (delta_accl > 25) -----
                else if (!fastCarbRebound && delta_accl > 25 && glucose_status.delta > 4 && bg > 110 && iob_data.iob < boostMaxIOB && boostActive && eventualBG > target_bg) {
                    consoleError.add(">>> TIER 6: Acceleration Bolus <<<")
                    rT.boostTier = "ACCELERATION"
                    boostInsulinReq = min(boost_scale * boostInsulinReq, boost_max)
                    if (boostInsulinReq > boostMaxIOB - iob_data.iob) {
                        boostInsulinReq = boostMaxIOB - iob_data.iob
                    }
                    insulinDivisor = insulinReqPCT - ((abs(bg - 180) / 72) * (insulinReqPCT - (2 * scale_pct)))
                    insulinReqPCT = insulinDivisor
                    microBolus = Math.floor(min(boostInsulinReq / insulinReqPCT, boost_max) * roundSMBTo) / roundSMBTo
                    iTimeActive = true
                    consoleError.add("Acceleration bolus triggered; SMB equals $boostInsulinReq")
                    rT.reason.append("Acceleration bolus triggered; SMB equals $boostInsulinReq; ")
                }
                // ----- Tier 7: Enhanced oref1 (mild acceleration) -----
                else if (boostActive && glucose_status.delta > 0 && delta_accl >= 0.5) {
                    consoleError.add(">>> TIER 7: Enhanced oref1 <<<")
                    rT.boostTier = "ENHANCED_OREF1"
                    microBolus = Math.floor(min(insulinReq / insulinReqPCT, boost_max) * roundSMBTo) / roundSMBTo
                    rT.reason.append("Enhanced oref1 triggered; SMB equals $microBolus; ")
                }
                // ----- Tier 8: Regular oref1 (default fallback) -----
                else {
                    consoleError.add(">>> TIER 8: Regular oref1 (fallback) <<<")
                    rT.boostTier = "REGULAR_OREF1"
                    microBolus = Math.floor(min(insulinReq / insulinReqPCT, maxBolus) * roundSMBTo) / roundSMBTo
                    rT.reason.append("Regular oref1 triggered; SMB equals $microBolus; ")
                }

                // Zero temp calculation for SMB
                val smbTarget = target_bg
                val worstCaseInsulinReq = (smbTarget - (naive_eventualBG + minIOBPredBG) / 2.0) / sens
                var durationReq = round(60 * worstCaseInsulinReq / profile.current_basal)

                if (insulinReq > 0 && microBolus < profile.bolus_increment) {
                    durationReq = 0
                }

                var smbLowTempReq = 0.0
                if (durationReq <= 0) {
                    durationReq = 0
                } else if (durationReq >= 30) {
                    durationReq = round(durationReq / 30.0) * 30
                    durationReq = min(60, max(0, durationReq))
                } else {
                    smbLowTempReq = round(basal * durationReq / 30.0, 2)
                    durationReq = 30
                }
                rT.reason.append(" insulinReq $insulinReq")
                if (microBolus >= maxBolus) {
                    rT.reason.append("; standardMaxBolus $maxBolus")
                }
                if (durationReq > 0 && !iTimeActive) {
                    rT.reason.append("; setting ${durationReq}m low temp of ${smbLowTempReq}U/h")
                }
                rT.reason.append(". ")

                val SMBInterval = min(10, max(1, profile.SMBInterval)) * 60.0 // in seconds
                val lastBolusAgeSec = (systemTime - iob_data.lastBolusTime) / 1000.0
                consoleError.add("naive_eventualBG $naive_eventualBG,${durationReq}m ${smbLowTempReq}U/h temp needed; last bolus ${round(lastBolusAgeSec / 60.0, 1)}m ago; maxBolus: $maxBolus")

                if (lastBolusAgeSec > SMBInterval - 6.0) {
                    if (microBolus > 0) {
                        rT.units = microBolus
                        rT.reason.append("Microbolusing ${microBolus}U. ")
                    }
                } else {
                    val nextBolusMins = (SMBInterval - lastBolusAgeSec) / 60.0
                    val nextBolusSeconds = (SMBInterval - lastBolusAgeSec) % 60
                    val waitingSeconds = round(nextBolusSeconds, 0) % 60
                    val waitingMins = round(nextBolusMins - waitingSeconds / 60.0, 0)
                    rT.reason.append("Waiting ${waitingMins.withoutZeros()}m ${waitingSeconds.withoutZeros()}s to microbolus again.")
                }

                // =====================================================================
                // Boost-specific: iTimeActive triggers
                // =====================================================================
                if ((boostActive && COB > 0 && lastCarbAge < 15) || (basal > (4 * profile_current_basal) && lastBolusAge < 15 && delta_accl > 0)) {
                    iTimeActive = true
                }

                if (durationReq > 0 && !iTimeActive) {
                    rT.rate = smbLowTempReq
                    rT.duration = durationReq
                    return rT
                }
            }

            // =====================================================================
            // Boost-specific: iTimeActive high basal and bolus logic
            // =====================================================================
            val maxSafeBasal = getMaxSafeBasal(profile)
            consoleError.add("── High Basal ──────────────────────────────")
            consoleError.add("iTimeActive: $iTimeActive | maxSafeBasal: ${round(maxSafeBasal, 2)}")
            rT.reason.append("Additional basal trigger currently set to $iTimeActive; ")

            if (iTimeActive && !(microBolusAllowed && enableSMB && bg > threshold)) {
                // If iTimeActive but SMB wasn't processed, give a boost bolus
                val roundSMBTo = 1.0 / profile.bolus_increment
                val boostBolus = Math.floor(min(basal, profile.boost_bolus) * roundSMBTo) / roundSMBTo
                rT.reason.append("Boost bolus triggered due to continued acceleration post Boost function; ")
            }

            if (iTimeActive) {
                // Set 5x basal for 15 minutes
                rT.reason.append("Add high basal with Boost: ${(basal * 5 / 60) * 30}U; ")
                val durationReqHighBasal = 15
                rT.duration = durationReqHighBasal
                rate = round_basal(basal * 5)
            }

            if (rate > maxSafeBasal && !iTimeActive) {
                rT.reason.append("adj. req. rate: ${round(rate, 2)} to maxSafeBasal: ${maxSafeBasal.withoutZeros()}, ")
                rate = round_basal(maxSafeBasal)
            }

            val insulinScheduled = currenttemp.duration * (currenttemp.rate - basal) / 60
            if (insulinScheduled >= insulinReq * 2 && !iTimeActive) {
                rT.reason.append("${currenttemp.duration}m@${(currenttemp.rate).toFixed2()} > 2 * insulinReq. Setting temp basal of ${round(rate, 2)}U/hr. ")
                return setTempBasal(rate, 30, profile, rT, currenttemp)
            }

            if (currenttemp.duration == 0) {
                rT.reason.append("no temp, setting ${round(rate, 2).withoutZeros()}U/hr. ")
                return setTempBasal(rate, 30, profile, rT, currenttemp)
            }

            if (currenttemp.duration > 5 && (round_basal(rate) <= round_basal(currenttemp.rate))) {
                rT.reason.append("temp ${(currenttemp.rate).toFixed2()} >~ req ${round(rate, 2).withoutZeros()}U/hr. ")
                return rT
            }

            rT.reason.append("temp ${currenttemp.rate.toFixed2()} < ${round(rate, 2).withoutZeros()}U/hr. ")
            return setTempBasal(rate, 30, profile, rT, currenttemp)
        }
    }
}
