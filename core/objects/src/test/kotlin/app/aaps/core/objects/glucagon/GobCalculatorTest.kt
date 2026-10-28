package app.aaps.core.objects.glucagon

import app.aaps.core.data.model.BS
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.utils.DateUtil
import app.aaps.shared.tests.TestBase
import com.google.common.truth.Truth.assertThat
import io.reactivex.rxjava3.core.Single
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mock
import org.mockito.kotlin.whenever

/**
 * Unit tests for [GobCalculator].
 *
 * Expected values were computed independently from the oref curve with each
 * formulation's peak and duration, so a change to either moves them.
 */
class GobCalculatorTest : TestBase() {

    @Mock lateinit var persistenceLayer: PersistenceLayer
    @Mock lateinit var dateUtil: DateUtil

    private lateinit var gobCalculator: GobCalculator

    private val now = 1_700_000_000_000L   // fixed reference timestamp

    @BeforeEach
    fun setUp() {
        gobCalculator = GobCalculator(persistenceLayer, dateUtil)
        whenever(dateUtil.now()).thenReturn(now)
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    /** Build a valid GLUCAGON BS record at [minutesAgo] before [now]. */
    private fun glucagonDose(doseMcg: Double, minutesAgo: Long): BS =
        BS(
            timestamp = now - minutesAgo * 60_000L,
            amount = doseMcg / 1000.0,   // mcg → mg (storage unit)
            type = BS.Type.GLUCAGON,
            isValid = true
        )

    private fun stubDoses(vararg doses: BS) {
        whenever(persistenceLayer.getGlucagonDosesFromTime(org.mockito.kotlin.any(), org.mockito.kotlin.any()))
            .thenReturn(Single.just(doses.toList()))
    }

    // -------------------------------------------------------------------------
    // Tests
    // -------------------------------------------------------------------------

    @Test
    fun `returns zero GOB when no doses in lookback window`() {
        stubDoses()
        assertThat(gobCalculator.currentGob(GlucagonFormulation.DASIGLUCAGON)).isWithin(0.001).of(0.0)
    }

    @Test
    fun `dose counts in full at delivery`() {
        stubDoses(glucagonDose(100.0, minutesAgo = 0))
        assertThat(gobCalculator.currentGob(GlucagonFormulation.GLUCAGEN)).isWithin(0.01).of(100.0)
    }

    @Test
    fun `GlucaGen curve at known points`() {
        assertThat(100 * GobCalculator.fractionRemaining(10.0, GlucagonFormulation.GLUCAGEN)).isWithin(0.01).of(84.31)
        assertThat(100 * GobCalculator.fractionRemaining(20.0, GlucagonFormulation.GLUCAGEN)).isWithin(0.01).of(57.98)
        assertThat(100 * GobCalculator.fractionRemaining(60.0, GlucagonFormulation.GLUCAGEN)).isWithin(0.01).of(4.13)
        assertThat(GobCalculator.fractionRemaining(90.0, GlucagonFormulation.GLUCAGEN)).isEqualTo(0.0)
    }

    @Test
    fun `dasiglucagon curve at known points`() {
        assertThat(100 * GobCalculator.fractionRemaining(20.0, GlucagonFormulation.DASIGLUCAGON)).isWithin(0.01).of(84.31)
        assertThat(100 * GobCalculator.fractionRemaining(30.0, GlucagonFormulation.DASIGLUCAGON)).isWithin(0.01).of(71.18)
        assertThat(100 * GobCalculator.fractionRemaining(60.0, GlucagonFormulation.DASIGLUCAGON)).isWithin(0.01).of(35.33)
        assertThat(GobCalculator.fractionRemaining(180.0, GlucagonFormulation.DASIGLUCAGON)).isEqualTo(0.0)
    }

    @Test
    fun `Gvoke uses the dasiglucagon curve`() {
        assertThat(GlucagonFormulation.GVOKE.peakMinutes).isEqualTo(GlucagonFormulation.DASIGLUCAGON.peakMinutes)
        assertThat(GlucagonFormulation.GVOKE.durationMinutes).isEqualTo(GlucagonFormulation.DASIGLUCAGON.durationMinutes)
    }

    @Test
    fun `formulation changes GOB for the same history`() {
        stubDoses(glucagonDose(100.0, minutesAgo = 30))
        assertThat(gobCalculator.currentGob(GlucagonFormulation.GLUCAGEN)).isWithin(0.01).of(35.33)
        assertThat(gobCalculator.currentGob(GlucagonFormulation.DASIGLUCAGON)).isWithin(0.01).of(71.18)
    }

    @Test
    fun `multiple doses sum correctly`() {
        stubDoses(glucagonDose(100.0, minutesAgo = 10), glucagonDose(75.0, minutesAgo = 30))
        // 100 × 0.9517 + 75 × 0.7118
        assertThat(gobCalculator.currentGob(GlucagonFormulation.DASIGLUCAGON)).isWithin(0.01).of(148.56)
    }

    @Test
    fun `reads valid glucagon doses over the formulation duration`() {
        // Selecting valid GLUCAGON rows is the query's job, tested in BolusDaoTest
        stubDoses(glucagonDose(100.0, minutesAgo = 10))
        assertThat(gobCalculator.currentGob(GlucagonFormulation.DASIGLUCAGON)).isWithin(0.01).of(95.17)
        org.mockito.kotlin.verify(persistenceLayer).getGlucagonDosesFromTime(now - 180 * 60_000L, false)
    }

    @Test
    fun `unknown formulation key falls back to dasiglucagon`() {
        assertThat(GlucagonFormulation.fromKey("GLUCAGEN")).isEqualTo(GlucagonFormulation.GLUCAGEN)
        assertThat(GlucagonFormulation.fromKey("")).isEqualTo(GlucagonFormulation.DASIGLUCAGON)
    }
}
