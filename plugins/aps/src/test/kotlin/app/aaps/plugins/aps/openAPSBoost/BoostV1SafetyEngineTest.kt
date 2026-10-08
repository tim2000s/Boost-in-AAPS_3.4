package app.aaps.plugins.aps.openAPSBoost

import app.aaps.core.data.model.GlucoseUnit
import app.aaps.core.interfaces.aps.AutosensResult
import app.aaps.core.interfaces.aps.CurrentTemp
import app.aaps.core.interfaces.aps.GlucoseStatusSMB
import app.aaps.core.interfaces.aps.IobTotal
import app.aaps.core.interfaces.aps.MealData
import app.aaps.core.interfaces.aps.OapsProfileBoost
import app.aaps.core.interfaces.aps.RT
import app.aaps.core.interfaces.profile.ProfileUtil
import com.google.common.truth.Truth.assertWithMessage
import org.junit.jupiter.api.Test
import org.mockito.kotlin.anyOrNull
import org.mockito.kotlin.mock
import org.mockito.kotlin.whenever

/**
 * Audit items 4, 5, 19 and 20 exercised through DetermineBasalBoost.determine_basal itself, on a minimal
 * profile with no ML models, so the tests cover the call sites as well as the rules in
 * BoostV1SafetyRules.kt. Each scenario prints the tier and the dose with the engine's console on failure.
 */
class BoostV1SafetyEngineTest {

    private val now = 1_790_000_000_000L

    private fun profile(
        bg: Double,
        maxIob: Double = 10.0,
        insulinReqPercent: Double = 85.0,
        percentScale: Double = 250.0,
        recentLowBG: Double = 999.0,
        boostBolus: Double = 3.0,
        boostMaxIob: Double = 10.0,
        boostScale: Double = 1.0,
    ) = OapsProfileBoost(
        dia = 5.0, min_5m_carbimpact = 8.0, max_iob = maxIob, max_daily_basal = 1.0, max_basal = 4.0,
        min_bg = 100.0, max_bg = 100.0, target_bg = 100.0, carb_ratio = 10.0, sens = 50.0,
        autosens_adjust_targets = false, max_daily_safety_multiplier = 3.0, current_basal_safety_multiplier = 4.0,
        high_temptarget_raises_sensitivity = false, low_temptarget_lowers_sensitivity = false,
        sensitivity_raises_target = false, resistance_lowers_target = false, adv_target_adjustments = false,
        exercise_mode = false, half_basal_exercise_target = 160, maxCOB = 120, skip_neutral_temps = false,
        remainingCarbsCap = 90, enableUAM = true, A52_risk_enable = false, SMBInterval = 3,
        enableSMB_with_COB = true, enableSMB_with_temptarget = false, allowSMB_with_high_temptarget = false,
        enableSMB_always = true, enableSMB_after_carbs = false, maxSMBBasalMinutes = 30, maxUAMSMBBasalMinutes = 30,
        bolus_increment = 0.05, carbsReqThreshold = 1, current_basal = 1.0, temptargetSet = false, autosens_max = 1.2,
        out_units = "mg/dl", lgsThreshold = null,
        variable_sens = 50.0, insulinDivisor = 75, TDD = 40.0,
        dynISFBgCap = 210.0, dynISFBgCapped = bg, sensNormalTarget = 50.0, normalTarget = 99.0, dynISFvelocity = 1.0,
        insulinPeak = 75,
        boostActive = true, profileSwitch = 100, boost_bolus = boostBolus, boost_maxIOB = boostMaxIob,
        Boost_InsulinReq = insulinReqPercent, boost_scale = boostScale, boost_percent_scale = percentScale,
        enableBoostPercentScale = true, enableCircadianISF = false, allowBoost_with_high_temptarget = false,
        recentSteps5Minutes = 0, recentSteps15Minutes = 0, recentSteps30Minutes = 0, recentSteps60Minutes = 0,
        recentLowBG = recentLowBG, recentBrakingProduct = 0.0, dynIsfMode = true,
    )

    private fun iob(iob: Double, activity: Double = 0.0): Array<IobTotal> {
        val zt = IobTotal(time = now, iob = iob, activity = activity)
        return Array(48) { i ->
            IobTotal(time = now + i * 5 * 60_000L, iob = iob, activity = activity, lastBolusTime = now - 3_600_000L, iobWithZeroTemp = zt)
        }
    }

    private fun run(
        profile: OapsProfileBoost, bg: Double, delta: Double, shortAvg: Double, longAvg: Double, iobNow: Double,
        recentLowBG45Min: Double = 999.0,
    ): RT {
        val profileUtil = mock<ProfileUtil>()
        whenever(profileUtil.units).thenReturn(GlucoseUnit.MGDL)
        whenever(profileUtil.fromMgdlToStringInUnits(anyOrNull(), anyOrNull())).thenReturn("0")
        val engine = DetermineBasalBoost(profileUtil)
        return engine.determine_basal(
            glucose_status = GlucoseStatusSMB(glucose = bg, delta = delta, shortAvgDelta = shortAvg, longAvgDelta = longAvg, date = now),
            currenttemp = CurrentTemp(duration = 0, rate = 0.0, minutesrunning = 0),
            iob_data_array = iob(iobNow),
            profile = profile,
            autosens_data = AutosensResult(),
            meal_data = MealData(),
            microBolusAllowed = true,
            currentTime = now,
            flatBGsDetected = false,
            recentSmbVolume60Min = 0.0,
            cumulativeSmbCap60Min = 0.0,
            recentLowBG45Min = recentLowBG45Min,
        )
    }

    private fun RT.describe() =
        "tier=$boostTier units=$units insulinReq=$insulinReq\nREASON: $reason\nCONSOLE:\n${consoleError?.joinToString("\n")}"

    // Item 4. Tier 3 at 270 mg/dL with insulinReq% 85 and percent scale 250: the old divisor was
    // 1.176 - (90/72)(1.176 - 0.4) = 0.206, multiplying insulinReq by 4.9, up to the bolus cap (10 U here so
    // that the cap does not hide the difference). The divisor is now 1.176, so the dose is insulinReq x 0.85.
    @Test fun `tier 3 above 180 doses insulinReq at the insulinReq percent, not multiplied by a shrinking divisor`() {
        val bg = 270.0
        val rt = run(profile(bg, boostBolus = 10.0), bg = bg, delta = 12.0, shortAvg = 8.0, longAvg = 4.0, iobNow = 0.5)
        assertWithMessage(rt.describe()).that(rt.boostTier).isEqualTo("UAM_BOOST")
        val req = rt.insulinReq!!
        assertWithMessage(rt.describe()).that(req).isGreaterThan(0.0)
        val expected = Math.floor(minOf(req / (100.0 / 85.0), 10.0) * 20) / 20
        assertWithMessage(rt.describe()).that(rt.units ?: 0.0).isWithin(1e-9).of(expected)
    }

    // Item 5. IOB 1.0 and max_iob 1.5 leave 0.5 U of headroom. Tier 3 at 105 mg/dL gives the basal-derived
    // Boost dose (boost_scale 1 x basal 1 U/h = 1.0 U), which is clamped only against boost_maxIOB (10), so
    // V1 gave 1.0 U and took IOB to 2.0 although oref's own insulinReq was 0.1 U. It now gives at most 0.5 U.
    @Test fun `final SMB never takes IOB above max_iob`() {
        val bg = 105.0
        val rt = run(profile(bg, maxIob = 1.5), bg = bg, delta = 9.0, shortAvg = 6.0, longAvg = 3.0, iobNow = 1.0)
        assertWithMessage(rt.describe()).that(rt.boostTier).isEqualTo("UAM_BOOST")
        assertWithMessage(rt.describe()).that(rt.units ?: 0.0).isAtMost(0.5 + 1e-9)
        assertWithMessage(rt.describe()).that(rt.units ?: 0.0).isGreaterThan(0.0)
    }

    // Item 19. A low of 62 mg/dL 50 min ago: outside the 45-min post-rescue window, inside the 60-min recentLowBG
    // lookback. Glucose 130 and rising 6 per 5 min with a steady short average, no carbs, no release signal
    // (delta_accl 0, glucose below 160, no meal model). The low used to lift the G3 hold and Tier 7/8 dosed;
    // the hold now stands and no SMB is given.
    @Test fun `a recent low keeps the G3 hold`() {
        val bg = 130.0
        val rt = run(profile(bg, recentLowBG = 62.0), bg = bg, delta = 6.0, shortAvg = 6.0, longAvg = 3.0, iobNow = 0.2)
        assertWithMessage(rt.describe()).that(rt.boostTier).isEqualTo("NONE")
        assertWithMessage(rt.describe()).that(rt.units ?: 0.0).isEqualTo(0.0)
    }

    // Item 19, no-low control: the same cycle without a recent low was held before the change and still is.
    @Test fun `without a recent low the G3 hold is unchanged`() {
        val bg = 130.0
        val rt = run(profile(bg), bg = bg, delta = 6.0, shortAvg = 6.0, longAvg = 3.0, iobNow = 0.2)
        assertWithMessage(rt.describe()).that(rt.boostTier).isEqualTo("NONE")
    }

    // Item 20. In the post-rescue window (45-min low 70) Tier 8 at 200 mg/dL is capped by maxBolus
    // (1 U/h x 30 min = 0.5 U). The spike override used to lift that to insulinReq / 1.176, up to boost_bolus;
    // inside the window it no longer does.
    @Test fun `spike override does not apply in the post-rescue window`() {
        val bg = 200.0
        val rt = run(profile(bg, recentLowBG = 70.0), bg = bg, delta = 6.0, shortAvg = 6.5, longAvg = 5.0, iobNow = 0.3,
                     recentLowBG45Min = 70.0)
        assertWithMessage(rt.describe()).that(rt.boostTier).isEqualTo("REGULAR_OREF1")
        assertWithMessage(rt.describe()).that(rt.insulinReq!!).isGreaterThan(1.5)
        assertWithMessage(rt.describe()).that(rt.units ?: 0.0).isAtMost(0.5 + 1e-9)
    }

    // Item 20, control: outside the window the same Tier 8 cycle still gets the override.
    @Test fun `spike override still applies to tier 8 outside the post-rescue window`() {
        val bg = 200.0
        val rt = run(profile(bg), bg = bg, delta = 6.0, shortAvg = 6.5, longAvg = 5.0, iobNow = 0.3)
        assertWithMessage(rt.describe()).that(rt.boostTier).isEqualTo("REGULAR_OREF1")
        assertWithMessage(rt.describe()).that(rt.units ?: 0.0).isGreaterThan(0.5)
    }
}
