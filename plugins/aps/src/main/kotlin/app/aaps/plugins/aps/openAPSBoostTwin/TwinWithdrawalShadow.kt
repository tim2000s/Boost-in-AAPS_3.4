package app.aaps.plugins.aps.openAPSBoostTwin

/**
 * KAIROS — Twin-forecast insulin WITHDRAWAL (idea-4), pure decision logic (2026-07-20).
 *
 * The one lever that is both a VALIDATED signal and in the SAFE direction: when the Twin forecasts a low
 * (lo30 = the 30-min forecast floor, validated to catch real lows at ~1/3–1/2 the false-alarm rate of
 * oref's minGuardBG/minPredBG), WITHHOLD the insulin about to be delivered this cycle. Insulin-REDUCING
 * only — it can never add a dose, so its worst case is running mildly high, not a low.
 *
 * Pure + deterministic. Used two ways from ONE source: (a) the offline full-history validation via the
 * Kotlin harness, and (b) an on-device shadow / eventual action. Delivers nothing itself; it returns a
 * decision the caller logs (shadow) or applies (later, gated). Hard floors remain the backstop underneath.
 */
object TwinWithdrawalShadow {

    /** [wouldWithholdU] = insulin the withdrawal would remove THIS cycle (0 if not triggered). */
    data class Decision(val withdraw: Boolean, val wouldWithholdU: Double, val reason: String)

    /**
     * @param lo30           Twin 30-min forecast floor (mg/dL), null if the Twin has no forecast yet.
     * @param bg             current BG (mg/dL).
     * @param deliverableU   insulin deliverable this cycle that COULD be withheld (SMB + this-cycle basal).
     * @param lo30Threshold  withhold when lo30 < this (default 70 = the floorbreach line).
     * @param bgFloor        never withhold below this BG — already low, the deterministic floors own it.
     */
    fun decide(
        lo30: Double?,
        bg: Double,
        deliverableU: Double,
        lo30Threshold: Double = 70.0,
        bgFloor: Double = 70.0,
    ): Decision {
        if (lo30 == null) return Decision(false, 0.0, "no-forecast")
        if (bg < bgFloor) return Decision(false, 0.0, "already-low")      // floors handle it, not this
        if (lo30 >= lo30Threshold) return Decision(false, 0.0, "no-hypo-forecast")
        if (deliverableU <= 0.0) return Decision(false, 0.0, "nothing-to-withhold")
        return Decision(true, deliverableU, "lo30<$lo30Threshold")        // withhold the pending insulin
    }
}
