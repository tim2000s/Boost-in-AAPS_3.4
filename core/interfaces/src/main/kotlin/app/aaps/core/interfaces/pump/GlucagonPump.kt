package app.aaps.core.interfaces.pump

/**
 * Interface implemented by any plugin that can deliver glucagon microdoses.
 *
 * Discovered at runtime via:
 *   activePlugin.getSpecificPluginsListByInterface(GlucagonPump::class.java)
 *
 * Amounts: doseMcg is in micrograms. The underlying BS record stores amount in mg
 * (i.e. doseMcg / 1000.0) so that existing unit handling is preserved.
 */
interface GlucagonPump {

    /** True if the pump is ready to deliver a dose (enabled, reservoir holds at least the minimum dose, no active delivery). */
    fun isGlucagonPumpReady(): Boolean

    companion object {

        /** enteredBy on the NOTE that carries each dose to Nightscout, so the graph can skip it. */
        const val NOTE_ENTERED_BY = "AAPS glucagon"
    }

    /**
     * Deliver a glucagon microdose.
     * @param doseMcg dose in micrograms (e.g. 100.0 for 100 mcg)
     * @return true on successful delivery initiation; false on any error
     */
    fun deliverGlucagon(doseMcg: Double): Boolean

    /** Remaining glucagon in the reservoir, in micrograms. */
    val glucagonReservoirMcg: Double

    /** When the reservoir was last filled (ms), or 0 if unknown. Glucagon in solution has a limited life. */
    val glucagonReservoirFilledAt: Long
}
