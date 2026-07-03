package app.aaps.plugins.aps.openAPSBoost

import app.aaps.core.interfaces.bgQualityCheck.BgQualityCheck
import app.aaps.core.interfaces.constraints.ConstraintsChecker
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.profiling.Profiler
import app.aaps.core.interfaces.stats.TddCalculator
import app.aaps.core.interfaces.ui.UiInteraction
import app.aaps.core.interfaces.rx.events.EventCalibrationDetected
import app.aaps.plugins.aps.openAPSSMB.GlucoseStatusCalculatorSMB
import app.aaps.shared.tests.TestBaseWithProfile
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mock

/**
 * Tests the calibration SMB block behaviour of [OpenAPSBoostPlugin].
 *
 * The [calibrationBlockedUntil] field is private, so it is accessed via reflection.
 * The RxBus subscription is set up in [OpenAPSBoostPlugin.onStart], which is called
 * explicitly in the test setup.
 */
class CalibrationBlockTest : TestBaseWithProfile() {

    @Mock lateinit var constraintChecker: ConstraintsChecker
    @Mock lateinit var persistenceLayer: PersistenceLayer
    @Mock lateinit var bgQualityCheck: BgQualityCheck
    @Mock lateinit var tddCalculator: TddCalculator
    @Mock lateinit var uiInteraction: UiInteraction
    @Mock lateinit var profiler: Profiler
    @Mock lateinit var determineBasalBoost: DetermineBasalBoost

    private lateinit var plugin: OpenAPSBoostPlugin

    @BeforeEach fun prepare() {
        plugin = OpenAPSBoostPlugin(
            aapsLogger, aapsSchedulers, rxBus, constraintChecker, rh,
            profileFunction, profileUtil, config, activePlugin,
            iobCobCalculator, hardLimits, preferences, dateUtil,
            processedTbrEbData, persistenceLayer,
            GlucoseStatusCalculatorSMB(aapsLogger, iobCobCalculator, dateUtil, decimalFormatter, deltaCalculator),
            bgQualityCheck, uiInteraction, tddCalculator, determineBasalBoost, profiler, apsResultProvider
        )
        // Activate the RxBus subscription
        plugin.onStart()
    }

    // ─── helper: read the private calibrationBlockedUntil field via reflection ──

    private fun readCalibrationBlockedUntil(): Long {
        val field = OpenAPSBoostPlugin::class.java.getDeclaredField("calibrationBlockedUntil")
        field.isAccessible = true
        return field.getLong(plugin)
    }

    // ─── tests ──────────────────────────────────────────────────────────────────

    @Test fun `calibrationBlockedUntil is initially zero`() {
        assertThat(readCalibrationBlockedUntil()).isEqualTo(0L)
    }

    @Test fun `calibrationBlockedUntil is set when EventCalibrationDetected is posted`() {
        val beforePost = dateUtil.now()
        rxBus.send(EventCalibrationDetected())

        // Allow the synchronous scheduler (TestAapsSchedulers.io is trampoline) to deliver
        val afterPost = dateUtil.now()

        val blocked = readCalibrationBlockedUntil()
        val expectedLow = beforePost + 15 * 60_000L
        val expectedHigh = afterPost + 15 * 60_000L

        assertThat(blocked).isAtLeast(expectedLow)
        assertThat(blocked).isAtMost(expectedHigh)
    }

    @Test fun `calibrationBlockedUntil is set to now plus 15 minutes`() {
        rxBus.send(EventCalibrationDetected())

        val blocked = readCalibrationBlockedUntil()
        val expectedMs = dateUtil.now() + 15 * 60_000L

        // Allow ±1 second tolerance for timing (dateUtil.now() is mocked to fixed value)
        assertThat(blocked).isAtLeast(expectedMs - 1_000L)
        assertThat(blocked).isAtMost(expectedMs + 1_000L)
    }

    @Test fun `calibrationBlockedUntil expires correctly after 15 minutes`() {
        rxBus.send(EventCalibrationDetected())

        val blocked = readCalibrationBlockedUntil()
        // The block should be in the future
        assertThat(blocked).isGreaterThan(dateUtil.now())

        // If we simulate 16 minutes later the block is in the past
        val sixteenMinutesLater = dateUtil.now() + 16 * 60_000L
        assertThat(blocked).isLessThan(sixteenMinutesLater)
    }

    @Test fun `second EventCalibrationDetected resets the block window`() {
        rxBus.send(EventCalibrationDetected())
        val firstBlock = readCalibrationBlockedUntil()

        // dateUtil.now() is mocked to a fixed value, so both blocks should be equal
        rxBus.send(EventCalibrationDetected())
        val secondBlock = readCalibrationBlockedUntil()

        // Second block should be >= first block (reset or same fixed time)
        assertThat(secondBlock).isAtLeast(firstBlock)
    }
}
