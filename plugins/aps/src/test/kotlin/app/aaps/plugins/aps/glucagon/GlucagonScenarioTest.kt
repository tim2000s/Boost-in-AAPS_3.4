package app.aaps.plugins.aps.glucagon

import app.aaps.core.data.model.BS
import app.aaps.core.data.model.RM
import app.aaps.core.data.plugin.PluginType
import app.aaps.core.interfaces.aps.APS
import app.aaps.core.interfaces.aps.APSResult
import app.aaps.core.interfaces.aps.GlucoseStatus
import app.aaps.core.interfaces.aps.IobTotal
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.plugin.PluginBase
import app.aaps.core.interfaces.plugin.PluginDescription
import app.aaps.core.interfaces.pump.GlucagonPump
import app.aaps.core.keys.BooleanKey
import app.aaps.core.keys.IntKey
import app.aaps.core.keys.StringKey
import app.aaps.shared.tests.TestBaseWithProfile
import com.google.common.truth.Truth.assertThat
import io.reactivex.rxjava3.core.Single
import org.json.JSONObject
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.TestFactory
import org.mockito.Mock
import org.mockito.kotlin.any
import org.mockito.kotlin.whenever
import java.io.File

/**
 * Data-driven scenario tests for [GlucagonAlgorithmPlugin].
 *
 * Each JSON file in `src/test/resources/glucagon_scenarios/` describes one
 * clinical situation (glucose trend, IOB, prior doses, preferences) and the
 * expected dose (0.0 = blocked).  New scenarios can be added without touching
 * the test code.
 *
 * Scenarios cover:
 *  - Dose calculation: baseline, minimum clamp, maximum clamp, IOB penalty
 *  - Safety blocks: BG above threshold, BG rising, carbs not required,
 *    GOB exceeded, interval too short, daily hard cap
 *  - Pass-through after interval elapsed
 */
class GlucagonScenarioTest : TestBaseWithProfile() {

    @Mock lateinit var mockAps: APS
    @Mock lateinit var mockApsResult: APSResult
    @Mock lateinit var mockGlucoseStatus: GlucoseStatus
    @Mock lateinit var mockPersistenceLayer: PersistenceLayer

    private lateinit var fakePump: TestGlucagonPlugin

    // -------------------------------------------------------------------------
    // Concrete test double
    // -------------------------------------------------------------------------

    inner class TestGlucagonPlugin : PluginBase(
        PluginDescription().mainType(PluginType.GENERAL),
        aapsLogger, rh
    ), GlucagonPump {
        var lastDoseMcg: Double = 0.0
        override fun isGlucagonPumpReady() = true
        override fun deliverGlucagon(doseMcg: Double): Boolean {
            lastDoseMcg = doseMcg
            return true
        }
        override val glucagonReservoirMcg: Double = 1000.0
        override val lastGlucagonDeliveryTimestamp: Long = 0L
    }

    // -------------------------------------------------------------------------
    // Data classes
    // -------------------------------------------------------------------------

    private data class PriorDose(val minutesAgo: Long, val doseMcg: Double)

    private data class Scenario(
        val name: String,
        val description: String,
        val glucose: Double,
        val delta: Double,
        val shortAvgDelta: Double,
        val carbsRequired: Boolean,
        val carbsReq: Int,
        val iob: Double,
        val minBgMgdl: Int,
        val maxSingleDoseMcg: Int,
        val minIntervalMinutes: Int,
        val maxDailyMcg: Int,
        val formulation: String,
        val maxGobMcg: Int,
        val priorDoses: List<PriorDose>,
        val expectedDoseMcg: Double,
        val expectedReason: String
    )

    // -------------------------------------------------------------------------
    // Setup
    // -------------------------------------------------------------------------

    @BeforeEach
    fun setUp() {
        fakePump = TestGlucagonPlugin()
    }

    // -------------------------------------------------------------------------
    // TestFactory: one DynamicTest per scenario file
    // -------------------------------------------------------------------------

    @TestFactory
    fun `glucagon scenario files`(): List<DynamicTest> {
        val resource = javaClass.classLoader!!.getResource("glucagon_scenarios")
            ?: error("glucagon_scenarios directory not found in test resources")
        return File(resource.toURI())
            .listFiles { f -> f.extension == "json" }!!
            .sortedBy { it.name }
            .map { file ->
                DynamicTest.dynamicTest(file.nameWithoutExtension) {
                    runScenario(parseScenario(JSONObject(file.readText())))
                }
            }
    }

    // -------------------------------------------------------------------------
    // JSON parsing
    // -------------------------------------------------------------------------

    private fun parseScenario(json: JSONObject): Scenario {
        val input = json.getJSONObject("input")
        val prefs = input.getJSONObject("preferences")
        val dosesArray = input.getJSONArray("priorDoses")
        val priorDoses = (0 until dosesArray.length()).map { i ->
            val d = dosesArray.getJSONObject(i)
            PriorDose(d.getLong("minutesAgo"), d.getDouble("doseMcg"))
        }
        val expected = json.getJSONObject("expected")
        return Scenario(
            name = json.getString("scenario"),
            description = json.getString("description"),
            glucose = input.getDouble("glucose"),
            delta = input.getDouble("delta"),
            shortAvgDelta = input.getDouble("shortAvgDelta"),
            carbsRequired = input.getBoolean("carbsRequired"),
            carbsReq = input.getInt("carbsReq"),
            iob = input.getDouble("iob"),
            minBgMgdl = prefs.getInt("minBgMgdl"),
            maxSingleDoseMcg = prefs.getInt("maxSingleDoseMcg"),
            minIntervalMinutes = prefs.getInt("minIntervalMinutes"),
            maxDailyMcg = prefs.getInt("maxDailyMcg"),
            formulation = prefs.getString("formulation"),
            maxGobMcg = prefs.getInt("maxGobMcg"),
            priorDoses = priorDoses,
            expectedDoseMcg = expected.getDouble("doseMcg"),
            expectedReason = expected.getString("reason")
        )
    }

    // -------------------------------------------------------------------------
    // Scenario runner
    // -------------------------------------------------------------------------

    private fun runScenario(s: Scenario) {
        fakePump.lastDoseMcg = 0.0
        fakePump.setPluginEnabled(PluginType.GENERAL, true)

        val plugin = GlucagonAlgorithmPlugin(
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

        // Preferences
        whenever(preferences.get(BooleanKey.GlucagonEnabled)).thenReturn(true)
        whenever(preferences.get(IntKey.GlucagonMinBgMgdl)).thenReturn(s.minBgMgdl)
        whenever(preferences.get(IntKey.GlucagonMaxSingleDoseMcg)).thenReturn(s.maxSingleDoseMcg)
        whenever(preferences.get(IntKey.GlucagonMinIntervalMinutes)).thenReturn(s.minIntervalMinutes)
        whenever(preferences.get(IntKey.GlucagonMaxDailyMcg)).thenReturn(s.maxDailyMcg)
        whenever(preferences.get(StringKey.GlucagonFormulation)).thenReturn(s.formulation)
        whenever(preferences.get(IntKey.GlucagonMaxGobMcg)).thenReturn(s.maxGobMcg)

        // APS result
        whenever(activePlugin.activeAPS).thenReturn(mockAps)
        whenever(mockAps.lastAPSResult).thenReturn(mockApsResult)
        whenever(mockApsResult.isCarbsRequired).thenReturn(s.carbsRequired)
        whenever(mockApsResult.carbsReq).thenReturn(s.carbsReq)
        whenever(mockApsResult.glucoseStatus).thenReturn(mockGlucoseStatus)
        val nowTs = dateUtil.now()
        whenever(mockApsResult.iobData).thenReturn(arrayOf(IobTotal(nowTs, iob = s.iob)))

        // Glucose status
        whenever(mockGlucoseStatus.glucose).thenReturn(s.glucose)
        whenever(mockGlucoseStatus.delta).thenReturn(s.delta)
        whenever(mockGlucoseStatus.shortAvgDelta).thenReturn(s.shortAvgDelta)

        // Prior glucagon doses, returned for all time-range queries
        val doses = s.priorDoses.map { d ->
            BS(
                timestamp = dateUtil.now() - d.minutesAgo * 60_000L,
                amount = d.doseMcg / 1000.0,
                type = BS.Type.GLUCAGON,
                isValid = true
            )
        }
        whenever(mockPersistenceLayer.getRunningModeActiveAt(any()))
            .thenReturn(RM(timestamp = nowTs, mode = RM.Mode.CLOSED_LOOP, duration = 0))
        whenever(mockPersistenceLayer.getGlucagonDosesFromTime(any(), any()))
            .thenReturn(Single.just(doses))

        // Active pump
        whenever(activePlugin.getSpecificPluginsListByInterface(GlucagonPump::class.java))
            .thenReturn(arrayListOf(fakePump as PluginBase))

        // Profile (validProfile: 1.0 U/h basal throughout)
        whenever(profileFunction.getProfile()).thenReturn(validProfile)

        // Execute
        plugin.evaluateAndDoseForTest()

        // Assert
        if (s.expectedDoseMcg == 0.0) {
            assertThat(fakePump.lastDoseMcg)
                .isWithin(0.001).of(0.0)
        } else {
            assertThat(fakePump.lastDoseMcg)
                .isWithin(0.001).of(s.expectedDoseMcg)
        }
    }
}
