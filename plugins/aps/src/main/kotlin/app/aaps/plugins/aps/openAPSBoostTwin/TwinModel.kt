package app.aaps.plugins.aps.openAPSBoostTwin

import kotlin.math.max

/**
 * KAIROS Twin — physiological model core (2026-07-18).
 *
 * A per-person, compartmental, INTERPRETABLE glucose model — Bergman-minimal glucose + 2-compartment
 * subcutaneous insulin absorption + interstitial (CGM) lag + a LATENT glucose-appearance state Ra the
 * filter infers from CGM. Grounded in physiology on purpose: it cannot produce a non-physical
 * trajectory, and its parameters mean what an endocrinologist would expect. Because a pure-UAM user
 * announces no carbs, `Ra` is the only way to represent meals — the filter *discovers* them from
 * glucose alone (validated: backtesting/scripts/2026-07-kairos-twin, Twin forecast RMSE ≈ half of
 * oref's out-of-sample at 30/60 min, calibrated).
 *
 * This is a PURE forward model. It doses nothing. Faithful port of `twin_model.py`.
 *
 * State x = [Isc1, Isc2, X, Ra, G, Gi]:
 *   Isc1,Isc2  subcutaneous insulin depots (U)   dIsc1=-ka1·Isc1(+u);  dIsc2=ka1·Isc1-ka2·Isc2
 *   X          insulin action (1/min)            dX  =-p2·X + p2·SI·Isc2
 *   Ra         glucose appearance (mg/dL/min)     dRa =-kra·Ra  (+ process noise = meals)
 *   G          blood glucose (mg/dL)              dG  =-SG·(G-Gb) - X·G + Ra
 *   Gi         interstitial / CGM glucose         dGi =(G-Gi)/τi
 */

/** Per-person physiological parameters (priors; anchored by TDD/ISF). */
data class TwinParams(
    val ka1: Double = 0.030, val ka2: Double = 0.022,
    val p2: Double = 0.028, val si: Double = 0.00055,
    val sg: Double = 0.021, val gb: Double = 118.0,
    val taui: Double = 12.0, val kra: Double = 0.020,
)

/** State indices. */
const val TW_ISC1 = 0
const val TW_ISC2 = 1
const val TW_X = 2
const val TW_RA = 3
const val TW_G = 4
const val TW_GI = 5
const val TW_N = 6

/** Number of 1-minute substeps per 5-minute grid step (matches the validation). */
const val TWIN_SUBSTEPS = 5

/** One 1-minute forward step of a single state vector. `u` = insulin delivered this minute (U). Pure. */
fun twinStep1(x: DoubleArray, u: Double, p: TwinParams): DoubleArray {
    val isc1 = x[TW_ISC1] + (-p.ka1 * x[TW_ISC1]) + u
    val isc2 = x[TW_ISC2] + (p.ka1 * x[TW_ISC1] - p.ka2 * x[TW_ISC2])
    val xx = x[TW_X] + (-p.p2 * x[TW_X] + p.p2 * p.si * x[TW_ISC2])
    val ra = x[TW_RA] + (-p.kra * x[TW_RA])
    val g = x[TW_G] + (-p.sg * (x[TW_G] - p.gb) - x[TW_X] * max(x[TW_G], 1.0) + x[TW_RA])
    val gi = x[TW_GI] + ((x[TW_G] - x[TW_GI]) / p.taui)
    return doubleArrayOf(isc1, isc2, max(xx, 0.0), ra, max(g, 10.0), max(gi, 10.0))
}

/** One 5-minute grid step = [TWIN_SUBSTEPS] one-minute substeps, insulin `u5` spread across the bin. Pure. */
fun twinStep5(x: DoubleArray, u5: Double, p: TwinParams): DoubleArray {
    var s = x
    val per = u5 / TWIN_SUBSTEPS
    repeat(TWIN_SUBSTEPS) { s = twinStep1(s, per, p) }
    return s
}
