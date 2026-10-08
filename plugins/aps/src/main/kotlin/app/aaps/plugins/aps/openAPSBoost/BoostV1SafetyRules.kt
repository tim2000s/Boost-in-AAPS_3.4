package app.aaps.plugins.aps.openAPSBoost

import app.aaps.core.interfaces.aps.GlucoseStatus
import app.aaps.core.interfaces.aps.IobTotal
import app.aaps.core.interfaces.aps.MealData
import app.aaps.core.interfaces.aps.OapsProfileBoost
import kotlin.math.abs
import kotlin.math.floor
import kotlin.math.min

// Dose-path rules for the V1 Boost engine (DetermineBasalBoost), from the dose-path audit of
// 8 October 2026 (backtesting/reports/2026-10_dose_path_audit.md, items 4, 5, 19 and 20).
//
// They live here, as top-level functions, because DetermineBasalBoost.determine_basal sits at the limit
// of what ART's verifier accepts: an eleven-line branch inlined into it took the method from 246 to 270
// registers and two release builds died at startup with a VerifyError (2026-09-24). determine_basal calls
// each function in place of the expression it replaces. The functions it calls take at most five argument
// registers (a Double takes two), so that each call compiles to a plain invoke-static. A wider call needs
// an invoke-static/range and its own run of consecutive registers: measured with d8 and dexdump on
// 2026-10-08, calling the all-primitive forms from determine_basal took it from 266 to 273 registers, and
// the forms used here take it to 237. The primitive versions carry the logic and the tests.

/**
 * How far the percent-scale divisor moves away from the user's insulinReq% divisor (audit item 4).
 * The divisor is `insulinReqPct - boostPercentScaleReduction(bg, insulinReqPct - scalePct)`.
 *
 * The sliding scale was written for 108 to 180 mg/dL: at 180 the divisor is insulinReqPct and it moves
 * linearly towards scalePct as glucose falls to 108. The original reduction, `abs(bg - 180) / 72 * slope`,
 * used the absolute distance from 180, so above 180 the divisor moved towards scalePct again and then
 * through zero (near 276 mg/dL at insulinReq% 50 and percent scale 200, near 289 mg/dL at 85% and 250%),
 * multiplying insulinReq in Tiers 3 and 6, which have no upper glucose bound.
 *
 * Above 180 a positive [slope] (a divisor that would shrink) now gives no reduction, so the divisor stays
 * at its value at 180. A zero or negative slope (percent scale at or below insulinReq%, or Tier 6 with
 * percent scale off, where its slope is `-insulinReqPct`) makes the divisor grow above 180, which is the
 * more conservative direction, and is kept. At and below 180 the reduction is the original one, so Tier 5
 * (110 to 180 mg/dL) is unchanged.
 *
 * The divisor cannot reach zero: above 180 it is at least insulinReqPct, and at and below 180 the callers
 * only reach this with bg >= 108 (Tier 3) or bg > 110 (Tier 6), where `abs(bg - 180) / 72` is at most 1,
 * so the divisor lies between insulinReqPct and the scale divisor the caller subtracted, both positive.
 *
 * Tier 6 passes `insulinReqPct - 2 * scalePct` as [slope], as its own formula always has.
 */
internal fun boostPercentScaleReduction(bg: Double, slope: Double): Double =
    if (bg > 180.0 && slope > 0.0) 0.0 else (abs(bg - 180) / 72) * slope

/**
 * Final microbolus held inside oref's max_iob (audit item 5). insulinReq is already clamped to
 * max_iob − IOB, but tier divisors below 1 and the basal-derived Boost doses in Tiers 3, 4 and 6 are only
 * clamped against boost_maxIOB, so an SMB could take IOB above the user's max_iob. The dose is reduced to
 * the headroom, floored to the bolus increment; a dose already inside the headroom is returned unchanged.
 * A headroom that is zero, negative or not a number gives 0.
 */
internal fun boostSmbWithinMaxIob(microBolus: Double, maxIob: Double, iob: Double, bolusIncrement: Double): Double {
    val headroom = maxIob - iob
    if (!(headroom > 0.0)) return 0.0
    if (microBolus <= headroom) return microBolus
    if (!(bolusIncrement > 0.0)) return min(microBolus, headroom)
    val steps = 1.0 / bolusIncrement
    return floor(headroom * steps + 1e-9) / steps
}

/** [boostSmbWithinMaxIob] with the profile's max_iob and bolus increment; the form determine_basal calls. */
internal fun boostSmbWithinMaxIob(microBolus: Double, profile: OapsProfileBoost, iobData: IobTotal): Double =
    boostSmbWithinMaxIob(microBolus, profile.max_iob, iobData.iob, profile.bolus_increment)

/**
 * Conditions under which the G3 pre-UAM hold engages (audit item 19), before its release signals are
 * considered. The hold was written with "recentLowBG >= 70 (not in hypo recovery)" as a condition, which
 * scoped it to rises from near target and left recovery to the fast-carb rebound protection; in effect a
 * low lifted the hold, so a low 45 to 60 min ago was covered by neither G3 nor the 45-min post-rescue
 * window. A recent low no longer lifts it. With no low in the last hour the old condition was always
 * true, so behaviour there is unchanged.
 */
internal fun boostG3HoldConditionsMet(mealCob: Double, delta: Double, shortAvgDelta: Double): Boolean =
    mealCob < 1.0 && delta >= 5.0 && shortAvgDelta >= 3.0

/** [boostG3HoldConditionsMet] read from the meal and glucose status; the form determine_basal calls. */
internal fun boostG3HoldConditionsMet(mealData: MealData, glucoseStatus: GlucoseStatus): Boolean =
    boostG3HoldConditionsMet(mealData.mealCOB, glucoseStatus.delta, glucoseStatus.shortAvgDelta)

/**
 * Whether the Tier 8 spike override may raise the SMB cap (audit item 20). The override exists because
 * Tier 8 is the one tier capped by the basal-derived maxBolus; it was not restricted to Tier 8, and it
 * re-inflated doses that the post-rescue window or the ML tier downgrade had deliberately sent to the
 * conservative tiers. It now applies only to Tier 8, and never in the post-rescue window or under the
 * ML downgrade. The glucose, delta, insulinReq and IOB conditions stay where they were.
 */
internal fun boostSpikeOverrideAllowed(boostActive: Boolean, tier: String?, inPostRescueWindow: Boolean, mlTierDowngrade: Boolean): Boolean =
    boostActive && tier == "REGULAR_OREF1" && !inPostRescueWindow && !mlTierDowngrade
