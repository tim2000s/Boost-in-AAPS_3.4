package app.aaps.core.grap.data

import android.content.Context
import app.aaps.core.data.model.BS
import app.aaps.core.graph.data.BolusDataPoint
import app.aaps.core.interfaces.resources.ResourceHelper
import app.aaps.core.interfaces.utils.DecimalFormatter
import app.aaps.core.keys.interfaces.Preferences
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.extension.ExtendWith
import org.mockito.Mock
import org.mockito.junit.jupiter.MockitoExtension
import org.mockito.junit.jupiter.MockitoSettings
import org.mockito.kotlin.any
import org.mockito.kotlin.eq
import org.mockito.kotlin.whenever
import org.mockito.quality.Strictness

@ExtendWith(MockitoExtension::class)
@MockitoSettings(strictness = Strictness.LENIENT)
internal class BolusDataPointTest {

    @Mock lateinit var preferences: Preferences
    @Mock lateinit var rh: ResourceHelper
    @Mock lateinit var decimalFormatter: DecimalFormatter
    @Mock lateinit var context: Context

    @BeforeEach
    fun setup() {
        whenever(rh.gac(any(), eq(app.aaps.core.ui.R.attr.glucagonColor))).thenReturn(GLUCAGON)
        whenever(rh.gac(any(), eq(app.aaps.core.ui.R.attr.bolusDataPointColor))).thenReturn(BOLUS)
        whenever(decimalFormatter.toPumpSupportedBolus(any(), any())).thenReturn("0.10")
    }

    private fun point(type: BS.Type) = BolusDataPoint(BS(timestamp = 1000, amount = 0.1, type = type), rh, 0.05, preferences, decimalFormatter)

    @Test
    fun glucagonHasItsOwnColourAndAMicrogramLabel() {
        assertThat(point(BS.Type.GLUCAGON).color(context)).isEqualTo(GLUCAGON)
        assertThat(point(BS.Type.GLUCAGON).label).isEqualTo("100µg")
    }

    @Test
    fun insulinBolusKeepsBolusColourAndUnits() {
        assertThat(point(BS.Type.NORMAL).color(context)).isEqualTo(BOLUS)
        assertThat(point(BS.Type.NORMAL).label).isEqualTo("0.10")
    }

    private companion object {
        const val GLUCAGON = 0xFFEC407A.toInt()
        const val BOLUS = 0xFF1EA3E5.toInt()
    }
}
