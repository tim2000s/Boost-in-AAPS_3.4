package app.aaps.pump.glucagon

import app.aaps.core.data.model.BS
import app.aaps.core.data.plugin.PluginType
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.keys.IntKey
import app.aaps.core.keys.IntNonKey
import app.aaps.core.keys.LongNonKey
import app.aaps.shared.tests.TestBaseWithProfile
import com.google.common.truth.Truth.assertThat
import io.reactivex.rxjava3.core.Single
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mock
import org.mockito.kotlin.any
import org.mockito.kotlin.anyOrNull
import org.mockito.kotlin.never
import org.mockito.kotlin.verify
import org.mockito.kotlin.whenever

class VirtualGlucagonPumpTest : TestBaseWithProfile() {

    @Mock lateinit var mockPersistenceLayer: PersistenceLayer
    private lateinit var pump: VirtualGlucagonPump

    @BeforeEach
    fun setUp() {
        whenever(preferences.get(LongNonKey.GlucagonReservoirFilledAt)).thenReturn(1L)   // filled once already
        pump = VirtualGlucagonPump(aapsLogger, rh, rxBus, mockPersistenceLayer, dateUtil, preferences)
        pump.setPluginEnabled(PluginType.GENERAL, true)
        whenever(preferences.get(IntNonKey.GlucagonReservoirMcg)).thenReturn(120)
        whenever(mockPersistenceLayer.insertOrUpdateBolus(any(), any(), any(), anyOrNull()))
            .thenReturn(Single.just(PersistenceLayer.TransactionResult<BS>().also { it.inserted.add(BS(timestamp = 0, amount = 0.1, type = BS.Type.GLUCAGON)) }))
    }

    @Test
    fun `delivery takes the dose from the stored reservoir`() {
        assertThat(pump.deliverGlucagon(100.0)).isTrue()
        verify(preferences).put(IntNonKey.GlucagonReservoirMcg, 20)
    }

    @Test
    fun `a dose larger than the reservoir is refused and nothing is stored`() {
        assertThat(pump.deliverGlucagon(150.0)).isFalse()
        verify(mockPersistenceLayer, never()).insertOrUpdateBolus(any(), any(), any(), anyOrNull())
    }

    @Test
    fun `ready only with at least the minimum dose left`() {
        assertThat(pump.isGlucagonPumpReady()).isTrue()
        whenever(preferences.get(IntNonKey.GlucagonReservoirMcg)).thenReturn(20)
        assertThat(pump.isGlucagonPumpReady()).isFalse()
    }

    @Test
    fun `start without a fill time counts the reservoir from now`() {
        whenever(preferences.get(LongNonKey.GlucagonReservoirFilledAt)).thenReturn(0L)
        pump.onStart()
        verify(preferences).put(LongNonKey.GlucagonReservoirFilledAt, dateUtil.now())
    }

    @Test
    fun `refill sets the fill amount and the fill time`() {
        whenever(preferences.get(IntKey.GlucagonReservoirFillMcg)).thenReturn(1000)
        pump.refillReservoir()
        verify(preferences).put(IntNonKey.GlucagonReservoirMcg, 1000)
        verify(preferences).put(LongNonKey.GlucagonReservoirFilledAt, dateUtil.now())
    }
}
