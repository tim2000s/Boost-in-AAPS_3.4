package app.aaps.plugins.aps.glucagon

import app.aaps.core.data.model.BS
import app.aaps.core.data.plugin.PluginType
import app.aaps.core.interfaces.aps.APS
import app.aaps.core.interfaces.aps.APSResult
import app.aaps.core.interfaces.aps.GlucoseStatus
import app.aaps.core.interfaces.aps.IobTotal
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.plugin.PluginBase
import app.aaps.core.interfaces.plugin.PluginDescription
import app.aaps.core.interfaces.pump.GlucagonPump
import app.aaps.core.interfaces.rx.events.EventGlucagonDoseDelivered
import app.aaps.core.keys.BooleanKey
import app.aaps.core.keys.IntKey
import app.aaps.core.keys.StringKey
import app.aaps.shared.tests.TestBaseWithProfile
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mock
import org.mockito.kotlin.any
import org.mockito.kotlin.never
import org.mockito.kotlin.verify
import org.mockito.kotlin.whenever

/**
 * Unit tests for [GlucagonAlgorithmPlugin].
 *
 * Tests use [evaluateAndDoseForTest] (internal accessor) to invoke the dosing
 * logic directly without starting the plugin or waiting on the event bus.
 *
 * A [TestGlucagonPlugin] inner class provides a concrete PluginBase + GlucagonPump
 * implementation for pump-discovery testing.
 */
class GlucagonAlgorithmPluginTest : TestBaseWithProfile() {

    @Mock lateinit var mockAps: APS
    @Mock lateinit var mockApsResult: APSResult
    @Mock lateinit var mockGlucoseStatus: GlucoseStatus
    @Mock lateinit var mockPersistenceLayer: PersistenceLayer

    private lateinit var plugin: GlucagonAlgorithmPlugin
    private lateinit var fakePump: TestGlucagonPlugin

    // -------------------------------------------------------------------------
    // Concrete test double: both PluginBase and GlucagonPump
    // -------------------------------------------------------------------------

    inner class TestGlucagonPlugin(
        var ready: Boolean = true,
        var deliveryResult: Boolean = true,
        var lastDoseMcg: Double = 0.0
    ) : PluginBase(
        PluginDescription().mainType(PluginType.GENERAL),
        aapsLogger, rh
    ), GlucagonPump {
        override fun isGlucagonPumpReady(): Boolean = ready
        override fun deliverGlucagon(doseMcg: Double): Boolean {
            lastDoseMcg = doseMcg
            return deliveryResult
        }
        override val glucagonReservoirMcg: Double = 1000.0
        override val lastGlucagonDeliveryTimestamp: Long = 0L
    }

    // -------------------------------------------------------------------------
    // Setup
    // -------------------------------------------------------------------------

    @BeforeEach
    fun setUp() {
        plugin = GlucagonAlgorithmPlugin(
            aapsLogger = aapsLogger,
            rh = rh,
            rxBus = rxBus,
            aapsSchedulers = aapsSchedulers,
            preferences = preferences,
            activePlugin = activePlugin,
            profileFunction = profileFunction,
            persistenceLayer = mockPersistenceLayer,
            dateUtil = dateUtil
        )

        fakePump = TestGlucagonPlugin()

        // Default: all 8 conditions passing
        whenever(preferences.get(BooleanKey.GlucagonEnabled)).thenReturn(true)
        whenever(preferences.get(IntKey.GlucagonMinBgMgdl)).thenReturn(90)
        whenever(preferences.get(IntKey.GlucagonMaxSingleDoseMcg)).thenReturn(150)
        whenever(preferences.get(IntKey.GlucagonMinIntervalMinutes)).thenReturn(20)
        whenever(preferences.get(IntKey.GlucagonMaxDailyMcg)).thenReturn(900)
        whenever(preferences.get(StringKey.GlucagonFormulation)).thenReturn("DASIGLUCAGON")
        whenever(preferences.get(IntKey.GlucagonMaxGobMcg)).thenReturn(75)

        whenever(activePlugin.activeAPS).thenReturn(mockAps)
        whenever(mockAps.lastAPSResult).thenReturn(mockApsResult)

        whenever(mockApsResult.isCarbsRequired).thenReturn(true)
        whenever(mockApsResult.carbsReq).thenReturn(10)
        whenever(mockApsResult.glucoseStatus).thenReturn(mockGlucoseStatus)
        val setupNow = dateUtil.now()
        whenever(mockApsResult.iobData).thenReturn(arrayOf(IobTotal(setupNow, iob = 0.5)))

        whenever(mockGlucoseStatus.glucose).thenReturn(80.0)
        whenever(mockGlucoseStatus.delta).thenReturn(-2.0)
        whenever(mockGlucoseStatus.shortAvgDelta).thenReturn(-1.5)

        // No prior glucagon doses
        whenever(mockPersistenceLayer.getBolusesFromTimeToTime(any(), any(), any()))
            .thenReturn(emptyList())

        // Active, ready glucagon pump
        whenever(activePlugin.getSpecificPluginsListByInterface(GlucagonPump::class.java))
            .thenReturn(arrayListOf(fakePump as PluginBase))

        fakePump.setPluginEnabled(PluginType.GENERAL, true)

        // Profile: 1 U/h basal (from validProfile JSON: basal=[{00:00, value:1}])
        whenever(profileFunction.getProfile()).thenReturn(validProfile)
    }

    // -------------------------------------------------------------------------
    // Condition 1: GlucagonEnabled
    // -------------------------------------------------------------------------

    @Test
    fun `no dose when glucagon feature is disabled`() {
        whenever(preferences.get(BooleanKey.GlucagonEnabled)).thenReturn(false)

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(0.0)
    }

    // -------------------------------------------------------------------------
    // Condition 2: carbsRequired
    // -------------------------------------------------------------------------

    @Test
    fun `no dose when carbsReq is zero`() {
        whenever(mockApsResult.isCarbsRequired).thenReturn(false)
        whenever(mockApsResult.carbsReq).thenReturn(0)

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(0.0)
    }

    // -------------------------------------------------------------------------
    // Condition 3: current BG <= threshold
    // -------------------------------------------------------------------------

    @Test
    fun `no dose when BG is above threshold`() {
        whenever(mockGlucoseStatus.glucose).thenReturn(95.0)

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(0.0)
    }

    @Test
    fun `dose delivered when BG is exactly at threshold`() {
        whenever(mockGlucoseStatus.glucose).thenReturn(90.0)

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isGreaterThan(0.0)
    }

    // -------------------------------------------------------------------------
    // Condition 4: BG falling (delta <= 0 OR shortAvgDelta <= 0)
    // -------------------------------------------------------------------------

    @Test
    fun `no dose when both delta and short avg delta are positive`() {
        whenever(mockGlucoseStatus.delta).thenReturn(3.0)
        whenever(mockGlucoseStatus.shortAvgDelta).thenReturn(2.0)

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(0.0)
    }

    @Test
    fun `dose allowed when delta is rising but short avg delta is zero`() {
        whenever(mockGlucoseStatus.delta).thenReturn(1.0)
        whenever(mockGlucoseStatus.shortAvgDelta).thenReturn(0.0)

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isGreaterThan(0.0)
    }

    // -------------------------------------------------------------------------
    // Condition 5: GOB below max
    // -------------------------------------------------------------------------

    @Test
    fun `no dose when GOB exceeds max (large recent dose)`() {
        // 150 mcg dasiglucagon delivered 5 min ago → GOB ≈ 149 mcg > 75 mcg max
        val recentDose = BS(
            timestamp = dateUtil.now() - 5 * 60_000L,
            amount = 150.0 / 1000.0,
            type = BS.Type.GLUCAGON,
            isValid = true
        )
        whenever(mockPersistenceLayer.getBolusesFromTimeToTime(any(), any(), any()))
            .thenReturn(listOf(recentDose))

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(0.0)
    }

    // -------------------------------------------------------------------------
    // Condition 6: min interval since last dose
    // -------------------------------------------------------------------------

    @Test
    fun `no dose when last dose was only 5 minutes ago (below 20 min interval)`() {
        val recentDose = BS(
            timestamp = dateUtil.now() - 5 * 60_000L,
            amount = 0.025,   // 25 mcg — small enough not to exceed GOB
            type = BS.Type.GLUCAGON,
            isValid = true
        )
        whenever(mockPersistenceLayer.getBolusesFromTimeToTime(any(), any(), any()))
            .thenReturn(listOf(recentDose))

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(0.0)
    }

    @Test
    fun `dose allowed when last dose was 30 minutes ago (above 20 min interval)`() {
        val oldDose = BS(
            timestamp = dateUtil.now() - 30 * 60_000L,
            amount = 0.025,
            type = BS.Type.GLUCAGON,
            isValid = true
        )
        whenever(mockPersistenceLayer.getBolusesFromTimeToTime(any(), any(), any()))
            .thenReturn(listOf(oldDose))

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isGreaterThan(0.0)
    }

    // -------------------------------------------------------------------------
    // Condition 7: daily cap
    // -------------------------------------------------------------------------

    @Test
    fun `no dose when daily total equals hard cap`() {
        // 18 × 50 mcg = 900 mcg (equal to default cap)
        val doses = (1..18).map { i ->
            BS(
                timestamp = dateUtil.now() - i * 60 * 60_000L,
                amount = 0.05,
                type = BS.Type.GLUCAGON,
                isValid = true
            )
        }
        whenever(mockPersistenceLayer.getBolusesFromTimeToTime(any(), any(), any()))
            .thenReturn(doses)

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(0.0)
    }

    // -------------------------------------------------------------------------
    // Condition 8: pump ready
    // -------------------------------------------------------------------------

    @Test
    fun `no dose when no glucagon pump plugin is active`() {
        whenever(activePlugin.getSpecificPluginsListByInterface(GlucagonPump::class.java))
            .thenReturn(arrayListOf())

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(0.0)
    }

    @Test
    fun `no dose when pump plugin is disabled`() {
        fakePump.setPluginEnabled(PluginType.GENERAL, false)

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(0.0)
    }

    @Test
    fun `no dose when pump reports not ready`() {
        fakePump.ready = false

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(0.0)
    }

    // -------------------------------------------------------------------------
    // Dose calculation
    // -------------------------------------------------------------------------

    @Test
    fun `dose is multiple of 25 mcg`() {
        val now = dateUtil.now()
        whenever(mockApsResult.carbsReq).thenReturn(10)
        whenever(mockApsResult.iobData).thenReturn(arrayOf(IobTotal(now, iob = 0.0)))

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg % 25.0).isWithin(0.001).of(0.0)
        assertThat(fakePump.lastDoseMcg).isGreaterThan(0.0)
    }

    @Test
    fun `dose minimum is 25 mcg for tiny carbsReq`() {
        val now = dateUtil.now()
        whenever(mockApsResult.carbsReq).thenReturn(1)   // 1×5=5 mcg → clamp to 25
        whenever(mockApsResult.iobData).thenReturn(arrayOf(IobTotal(now, iob = 0.0)))

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isAtLeast(25.0)
    }

    @Test
    fun `dose is capped at maxSingleDoseMcg`() {
        val now = dateUtil.now()
        whenever(mockApsResult.carbsReq).thenReturn(100)  // 100×5=500 → clamp to 150
        whenever(mockApsResult.iobData).thenReturn(arrayOf(IobTotal(now, iob = 0.0)))

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isAtMost(150.0)
    }

    @Test
    fun `IOB penalty halves dose when IOB ratio exceeds 1 5`() {
        // Profile: 1 U/h. IOB = 2.0 → ratio = 2.0 → penalty = 0.5
        // carbsReq=20 → baseDose = 100 mcg → penalised raw = 50 → round(50/25)*25 = 50
        val now = dateUtil.now()
        whenever(mockApsResult.carbsReq).thenReturn(20)
        whenever(mockApsResult.iobData).thenReturn(arrayOf(IobTotal(now, iob = 2.0)))

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(50.0)
    }

    @Test
    fun `no IOB penalty when IOB ratio is below 1 5`() {
        // Profile: 1 U/h. IOB = 1.0 → ratio = 1.0 → no penalty
        // carbsReq=20 → baseDose = 100 mcg → no penalty → 100
        val now = dateUtil.now()
        whenever(mockApsResult.carbsReq).thenReturn(20)
        whenever(mockApsResult.iobData).thenReturn(arrayOf(IobTotal(now, iob = 1.0)))

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(100.0)
    }

    // -------------------------------------------------------------------------
    // EventGlucagonDoseDelivered
    // -------------------------------------------------------------------------

    @Test
    fun `EventGlucagonDoseDelivered with success true is sent on delivery`() {
        val events = mutableListOf<EventGlucagonDoseDelivered>()
        rxBus.toObservable(EventGlucagonDoseDelivered::class.java).subscribe { events.add(it) }

        plugin.evaluateAndDoseForTest()

        assertThat(events).hasSize(1)
        assertThat(events[0].success).isTrue()
        assertThat(events[0].doseMcg).isGreaterThan(0.0)
    }

    @Test
    fun `EventGlucagonDoseDelivered with success false is sent when pump fails`() {
        fakePump.deliveryResult = false

        val events = mutableListOf<EventGlucagonDoseDelivered>()
        rxBus.toObservable(EventGlucagonDoseDelivered::class.java).subscribe { events.add(it) }

        plugin.evaluateAndDoseForTest()

        assertThat(events).hasSize(1)
        assertThat(events[0].success).isFalse()
    }

    // -------------------------------------------------------------------------
    // Null safety
    // -------------------------------------------------------------------------

    @Test
    fun `no dose when lastAPSResult is null`() {
        whenever(mockAps.lastAPSResult).thenReturn(null)

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(0.0)
    }

    @Test
    fun `no dose when glucoseStatus is null`() {
        whenever(mockApsResult.glucoseStatus).thenReturn(null)

        plugin.evaluateAndDoseForTest()

        assertThat(fakePump.lastDoseMcg).isWithin(0.001).of(0.0)
    }

    // -------------------------------------------------------------------------
    // Preference screen
    // -------------------------------------------------------------------------

    @Test
    fun `preference screen has at least one preference`() {
        val screen = preferenceManager.createPreferenceScreen(context)
        plugin.addPreferenceScreen(preferenceManager, screen, context, null)
        assertThat(screen.preferenceCount).isGreaterThan(0)
    }
}
