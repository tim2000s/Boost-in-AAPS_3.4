package app.aaps.wear.heartrate

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorManager
import app.aaps.core.interfaces.rx.AapsSchedulers
import app.aaps.core.interfaces.rx.weardata.EventData.ActionHeartRate
import app.aaps.core.interfaces.sharedPreferences.SP
import app.aaps.wear.AAPSLoggerTest
import app.aaps.wear.R
import com.google.common.truth.Truth.assertThat
import io.reactivex.rxjava3.core.Scheduler
import io.reactivex.rxjava3.disposables.Disposable
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.ArgumentMatchers.any
import org.mockito.ArgumentMatchers.eq
import org.mockito.kotlin.mock
import org.mockito.kotlin.times
import org.mockito.kotlin.verify
import org.mockito.kotlin.verifyNoInteractions
import org.mockito.kotlin.verifyNoMoreInteractions
import org.mockito.kotlin.whenever
import java.util.concurrent.TimeUnit

internal class HeartRateListenerTest {

    private val aapsLogger = AAPSLoggerTest()
    private val aapsSchedulers = object : AapsSchedulers {
        override val main: Scheduler = mock()
        override val io: Scheduler = mock()
        override val cpu: Scheduler = mock()
        override val newThread: Scheduler = mock()
    }
    private val schedule: Disposable = mock()
    private val sp: SP = mock()
    private val heartRates = mutableListOf<ActionHeartRate>()
    private val device = "unknown unknown"

    private fun create(timestampMillis: Long): HeartRateListener {
        val ctx: Context = mock()
        whenever(
            aapsSchedulers.io.schedulePeriodicallyDirect(
                any(), eq(60_000L), eq(60_000L), eq(TimeUnit.MILLISECONDS)
            )
        ).thenReturn(schedule)
        val listener = HeartRateListener(ctx, aapsLogger, sp, aapsSchedulers, timestampMillis)
        verify(aapsSchedulers.io).schedulePeriodicallyDirect(
            any(), eq(60_000L), eq(60_000L), eq(TimeUnit.MILLISECONDS)
        )
        listener.sendHeartRate = { hr -> heartRates.add(hr) }
        return listener
    }

    private fun sendSensorEvent(
        listener: HeartRateListener,
        timestamp: Long,
        heartRate: Int,
        sensorType: Int? = Sensor.TYPE_HEART_RATE,
        accuracy: Int = SensorManager.SENSOR_STATUS_ACCURACY_HIGH
    ) {
        listener.onSensorChanged(sensorType, accuracy, timestamp, floatArrayOf(heartRate.toFloat()))
    }

    @BeforeEach
    fun before() {
        heartRates.clear()
    }

    @AfterEach
    fun cleanup() {
        verifyNoInteractions(aapsSchedulers.main)
        verifyNoMoreInteractions(aapsSchedulers.io)
        verifyNoInteractions(aapsSchedulers.cpu)
        verifyNoInteractions(aapsSchedulers.newThread)
        verify(schedule).dispose()
    }

    @Test
    fun onSensorChanged() {
        whenever(sp.getInt(R.string.key_heart_rate_smoothing, 1)).thenReturn(1)
        val start = System.currentTimeMillis()
        val d1 = 10_000L
        val d2 = 20_000L
        val listener = create(start)

        assertThat(listener.currentHeartRateBpm).isNull()
        sendSensorEvent(listener, start + d1, 80)
        assertThat(heartRates).isEmpty()
        assertThat(listener.currentHeartRateBpm).isEqualTo(80)

        listener.send(start + d2)
        assertThat(heartRates).containsExactly(ActionHeartRate(d2, start + d2, 80.0, device))
        listener.dispose()
    }

    @Test
    fun onSensorChanged2() {
        whenever(sp.getInt(R.string.key_heart_rate_smoothing, 1)).thenReturn(1)
        val start = System.currentTimeMillis()
        val d1 = 10_000L
        val d2 = 40_000L
        val listener = create(start)

        sendSensorEvent(listener, start, 80)
        assertThat(heartRates).isEmpty()
        assertThat(listener.currentHeartRateBpm).isEqualTo(80)
        sendSensorEvent(listener, start + d1, 100)
        assertThat(heartRates).isEmpty()
        assertThat(listener.currentHeartRateBpm).isEqualTo(100)


        listener.send(start + d2)
        assertThat(heartRates).containsExactly(ActionHeartRate(d2, start + d2, 95.0, device))
        listener.dispose()
    }

    @Test
    fun onSensorChangedMultiple() {
        whenever(sp.getInt(R.string.key_heart_rate_smoothing, 1)).thenReturn(1)
        val start = System.currentTimeMillis()
        val d1 = 10_000L
        val d2 = 40_000L
        val listener = create(start)

        sendSensorEvent(listener, start, 80)
        listener.send(start + d1)
        assertThat(heartRates).hasSize(1)

        sendSensorEvent(listener, start + d1, 100)
        assertThat(heartRates).hasSize(1)
        listener.send(start + d2)
        assertThat(heartRates).containsExactly(
            ActionHeartRate(d1, start + d1, 80.0, device),
            ActionHeartRate(d2 - d1, start + d2, 100.0, device),
        ).inOrder()
        listener.dispose()
    }

    @Test
    fun onSensorChangedNoContact() {
        whenever(sp.getInt(R.string.key_heart_rate_smoothing, 1)).thenReturn(1)
        val start = System.currentTimeMillis()
        val d1 = 10_000L
        val d2 = 40_000L
        val listener = create(start)

        sendSensorEvent(listener, start, 80)
        sendSensorEvent(listener, start + d1, 100, accuracy = SensorManager.SENSOR_STATUS_NO_CONTACT)
        assertThat(listener.currentHeartRateBpm).isNull()
        listener.send(start + d2)

        assertThat(heartRates).containsExactly(ActionHeartRate(d2, start + d2, 80.0, device))
        listener.dispose()
    }

    // ── F4 sensor-feed watchdog (2026-07-07) ──
    // Some devices silently stop delivering HR events while the registration stays alive; the 60s
    // send tick re-registers the listener after >=5 min of silence, and retries at most once per
    // timeout period. registerListener's boolean is now logged (previously ignored).

    private fun createWithSensor(timestampMillis: Long): Triple<HeartRateListener, SensorManager, Sensor> {
        val ctx: Context = mock()
        val sensorManager: SensorManager = mock()
        val sensor: Sensor = mock()
        whenever(ctx.getSystemService(Context.SENSOR_SERVICE)).thenReturn(sensorManager)
        whenever(sensorManager.getDefaultSensor(Sensor.TYPE_HEART_RATE)).thenReturn(sensor)
        whenever(sensorManager.registerListener(any(), eq(sensor), eq(SensorManager.SENSOR_DELAY_NORMAL))).thenReturn(true)
        whenever(
            aapsSchedulers.io.schedulePeriodicallyDirect(
                any(), eq(60_000L), eq(60_000L), eq(TimeUnit.MILLISECONDS)
            )
        ).thenReturn(schedule)
        val listener = HeartRateListener(ctx, aapsLogger, sp, aapsSchedulers, timestampMillis)
        verify(aapsSchedulers.io).schedulePeriodicallyDirect(
            any(), eq(60_000L), eq(60_000L), eq(TimeUnit.MILLISECONDS)
        )
        listener.sendHeartRate = { hr -> heartRates.add(hr) }
        return Triple(listener, sensorManager, sensor)
    }

    @Test
    fun watchdogReregistersAfterFiveSilentMinutes() {
        whenever(sp.getInt(R.string.key_heart_rate_smoothing, 1)).thenReturn(1)
        val start = System.currentTimeMillis()
        val (listener, sensorManager, sensor) = createWithSensor(start)
        verify(sensorManager, times(1)).registerListener(any(), eq(sensor), eq(SensorManager.SENSOR_DELAY_NORMAL))

        // quiet for less than the timeout -> no re-registration
        listener.watchdogCheck(start + 4 * 60_000L)
        verify(sensorManager, times(1)).registerListener(any(), eq(sensor), eq(SensorManager.SENSOR_DELAY_NORMAL))

        // >= 5 min of silence -> unregister + re-register
        listener.watchdogCheck(start + 5 * 60_000L)
        verify(sensorManager).unregisterListener(listener)
        verify(sensorManager, times(2)).registerListener(any(), eq(sensor), eq(SensorManager.SENSOR_DELAY_NORMAL))

        // stamp was reset: the next tick must NOT re-register again
        listener.watchdogCheck(start + 6 * 60_000L)
        verify(sensorManager, times(2)).registerListener(any(), eq(sensor), eq(SensorManager.SENSOR_DELAY_NORMAL))
        listener.dispose()
    }

    @Test
    fun watchdogQuiescentWhileEventsFlow() {
        whenever(sp.getInt(R.string.key_heart_rate_smoothing, 1)).thenReturn(1)
        val start = System.currentTimeMillis()
        val (listener, sensorManager, sensor) = createWithSensor(start)

        // events keep arriving -> the stamp advances -> never re-registers
        sendSensorEvent(listener, start + 4 * 60_000L, 80)
        listener.watchdogCheck(start + 8 * 60_000L)
        verify(sensorManager, times(1)).registerListener(any(), eq(sensor), eq(SensorManager.SENSOR_DELAY_NORMAL))
        listener.dispose()
    }

    @Test
    fun onAccuracyChanged() {
        whenever(sp.getInt(R.string.key_heart_rate_smoothing, 1)).thenReturn(1)
        val start = System.currentTimeMillis()
        val d1 = 10_000L
        val d2 = 40_000L
        val d3 = 70_000L
        val listener = create(start)

        sendSensorEvent(listener, start, 80)
        listener.onAccuracyChanged(Sensor.TYPE_HEART_RATE, SensorManager.SENSOR_STATUS_UNRELIABLE, start + d1)
        sendSensorEvent(listener, start + d2, 100)
        listener.send(start + d3)

        assertThat(heartRates).containsExactly(ActionHeartRate(d3, start + d3, 95.0, device))
        listener.dispose()
    }

}
