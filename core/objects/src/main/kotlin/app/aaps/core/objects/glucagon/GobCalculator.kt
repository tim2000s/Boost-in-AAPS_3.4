package app.aaps.core.objects.glucagon

import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.utils.DateUtil
import kotlin.math.exp
import kotlin.math.pow

/**
 * Subcutaneous glucagon formulations and the activity curve used for each.
 *
 * Peak is the median plasma glucagon tmax at the small doses a closed loop gives. Duration is
 * that peak plus about five plasma half-lives, by which time under 5% of a dose remains. Both are
 * modelling choices read off the published data below, not fitted values.
 *
 * GLUCAGEN (native glucagon, reconstituted): Hövelmann 2019 (doi 10.1111/dom.13562), Lilly native
 * glucagon 0.03 to 0.2 mg, tmax 0.25 h, t1/2 0.25 h; Blauw 2016 (doi 10.1111/dom.12571), 0.11 to
 * 0.44 mg, tmax 10 to 20 min. GlucaGen US label: hyperglycaemic action 60 to 90 min.
 * GVOKE (Xeris non-aqueous glucagon): G-Pen Mini, same formulation, NCT02081014, 75 and 150 mcg,
 * mean tmax 29 to 30 min fasting and 24 to 33 min after insulin; Gvoke US label, 1 mg, t1/2 32 min.
 * DASIGLUCAGON (Zegalogue): Hövelmann 2019, 0.03 to 0.2 mg, median tmax 0.5 h, t1/2 0.4 to 0.7 h;
 * Zegalogue US label, 0.6 mg, tmax about 35 min, t1/2 about 30 min.
 *
 * Gvoke and dasiglucagon share a curve because the data give no basis to separate them.
 *
 * doseFactor scales the dose to give the same 30-minute glucose rise as native glucagon. For
 * dasiglucagon it is 0.65, from Hövelmann 2019 Table 2 at 0.03 and 0.08 mg (0.61 and 0.66; 0.90 at
 * 0.2 mg), computed in backtesting/scripts/2026-10-glucagon-formulations/dose_factor.py. Its
 * larger late effect is carried by the longer curve instead. Gvoke stays at 1.0 because no
 * small-dose comparison with native glucagon was found.
 *
 * maxReservoirHours is how long glucagon may stay in the pump before a reminder to replace it. None of
 * the three is licensed for pump use. Reconstituted GlucaGen is labelled for immediate use; 72 h is
 * the longest one n=1 report found it still working (diabettech.com, Glucagon & Me part 2), so it is
 * an upper bound rather than a shelf life. Gvoke and dasiglucagon are ready-made solutions with no
 * in-pump figure, so no reminder is set.
 */
enum class GlucagonFormulation(val peakMinutes: Int, val durationMinutes: Int, val doseFactor: Double, val maxReservoirHours: Int?, val displayName: String) {
    GLUCAGEN(15, 90, 1.0, 72, "GlucaGen"),
    GVOKE(30, 180, 1.0, null, "Gvoke"),
    DASIGLUCAGON(30, 180, 0.65, null, "Dasiglucagon");

    companion object {
        // An unknown value falls back to the slowest curve, which holds GOB higher for longer
        fun fromKey(key: String): GlucagonFormulation = entries.firstOrNull { it.name == key } ?: DASIGLUCAGON
    }
}

/**
 * Glucagon On Board (GOB) calculator.
 *
 * Uses the oref exponential activity curve (as InsulinOrefBasePlugin does for insulin) with the
 * formulation's peak and duration, so a dose counts in full at delivery and decays slowly until
 * its absorption peak has passed.
 *
 * Dose amounts are stored in the BS table in mg; this class converts to mcg internally.
 */
class GobCalculator(
    private val persistenceLayer: PersistenceLayer,
    private val dateUtil: DateUtil
) {

    /** Calculate current Glucagon On Board in micrograms. */
    fun currentGob(formulation: GlucagonFormulation): Double {
        val now = dateUtil.now()
        val since = now - formulation.durationMinutes * 60_000L

        return persistenceLayer
            .getGlucagonDosesFromTime(since, includeInvalid = false)
            .blockingGet()
            .sumOf { dose ->
                val minutesSince = (now - dose.timestamp) / 60_000.0
                dose.amount * 1000.0 * fractionRemaining(minutesSince, formulation)   // mg → mcg
            }
    }

    companion object {

        /** Share of a dose still on board [minutes] after delivery. */
        fun fractionRemaining(minutes: Double, formulation: GlucagonFormulation): Double {
            val td = formulation.durationMinutes.toDouble()
            val tp = formulation.peakMinutes.toDouble()
            if (minutes >= td) return 0.0
            val t = minutes.coerceAtLeast(0.0)
            val tau = tp * (1 - tp / td) / (1 - 2 * tp / td)
            val a = 2 * tau / td
            val s = 1 / (1 - a + (1 + a) * exp(-td / tau))
            return 1 - s * (1 - a) * ((t.pow(2.0) / (tau * td * (1 - a)) - t / tau - 1) * exp(-t / tau) + 1)
        }
    }
}
