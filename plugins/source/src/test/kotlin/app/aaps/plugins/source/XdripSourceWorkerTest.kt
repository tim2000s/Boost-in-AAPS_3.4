package app.aaps.plugins.source

import androidx.work.ListenableWorker
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import app.aaps.core.data.model.GV
import app.aaps.core.data.model.SourceSensor
import app.aaps.core.data.model.TrendArrow
import app.aaps.core.data.ue.Sources
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.receivers.Intents
import app.aaps.core.keys.BooleanKey
import app.aaps.core.utils.receivers.DataInbox
import app.aaps.shared.tests.BundleMock
import app.aaps.shared.tests.TestBaseWithProfile
import io.reactivex.rxjava3.core.Single
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assertions
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mock
import org.mockito.kotlin.any
import org.mockito.kotlin.anyOrNull
import org.mockito.kotlin.eq
import org.mockito.kotlin.never
import org.mockito.kotlin.times
import org.mockito.kotlin.verify
import org.mockito.kotlin.whenever

class XdripSourceWorkerTest : TestBaseWithProfile() {

    private lateinit var worker: XdripSourcePlugin.XdripSourceWorker
    @Mock lateinit var xdripSourcePlugin: XdripSourcePlugin
    @Mock lateinit var persistenceLayer: PersistenceLayer
    @Mock lateinit var workerParameters: WorkerParameters
    @Mock lateinit var dataInbox: DataInbox

    init {
        addInjector { injector ->
            if (injector is XdripSourcePlugin.XdripSourceWorker) {
                injector.aapsLogger = aapsLogger
                injector.xdripSourcePlugin = xdripSourcePlugin
                injector.persistenceLayer = persistenceLayer
                injector.dataInbox = dataInbox
                injector.dateUtil = dateUtil
                injector.preferences = preferences
            }
        }
    }

    @BeforeEach
    fun setupMock() {
        whenever(workerParameters.inputData).thenReturn(workDataOf())
        worker = XdripSourcePlugin.XdripSourceWorker(context, workerParameters)
    }

    @Test
    fun `When plugin disabled then return success`() {
        runBlocking {
            whenever(xdripSourcePlugin.isEnabled()).thenReturn(false)

            val result = worker.doWork()

            Assertions.assertEquals(ListenableWorker.Result.success(workDataOf("Result" to "Plugin not enabled")), result)
            verify(persistenceLayer, never()).insertCgmSourceData(any(), any(), any(), any())
        }
    }

    @Test
    fun `When plugin enabled then insert G6 data`() {
        val timestamp = now - 60000
        runBlocking {
            whenever(xdripSourcePlugin.isEnabled()).thenReturn(true)
            whenever(preferences.get(BooleanKey.BgSourceCreateSensorChange)).thenReturn(true)
            whenever(persistenceLayer.insertCgmSourceData(anyOrNull(), anyOrNull(), anyOrNull(), anyOrNull())).thenReturn(Single.just(PersistenceLayer.TransactionResult()))
            val bundle = BundleMock.mocked().apply {
                putString(Intents.XDRIP_DATA_SOURCE, "G6 Native")
                putLong(Intents.EXTRA_TIMESTAMP, timestamp)
                putLong(Intents.EXTRA_SENSOR_STARTED_AT, timestamp)
                putDouble(Intents.EXTRA_BG_ESTIMATE, 150.0)
                putDouble(Intents.EXTRA_RAW, 150.0)
                putString(Intents.EXTRA_BG_SLOPE_NAME, "FortyFiveDown")
            }
            whenever(dataInbox.drain(XdripInbox)).thenReturn(listOf(bundle))

            val result = worker.doWork()

            Assertions.assertEquals(ListenableWorker.Result.success(), result)
            val expectedGv = GV(
                timestamp = timestamp,
                value = 150.0,
                raw = 150.0,
                noise = null,
                trendArrow = TrendArrow.FORTY_FIVE_DOWN,
                sourceSensor = SourceSensor.DEXCOM_G6_NATIVE_XDRIP
            )
            verify(persistenceLayer).insertCgmSourceData(Sources.Xdrip, listOf(expectedGv), emptyList(), timestamp)
        }
    }

    @Test
    fun `When the inbox is empty then return success with no data`() {
        runBlocking {
            whenever(xdripSourcePlugin.isEnabled()).thenReturn(true)
            whenever(dataInbox.drain(XdripInbox)).thenReturn(emptyList())

            val result = worker.doWork()

            Assertions.assertEquals(ListenableWorker.Result.success(workDataOf("Result" to "no data")), result)
        }
    }

    @Test
    fun `When glucoseValues are missing the bundle is skipped and the run succeeds`() {
        runBlocking {
            whenever(persistenceLayer.insertCgmSourceData(anyOrNull(), anyOrNull(), anyOrNull(), anyOrNull())).thenReturn(Single.just(PersistenceLayer.TransactionResult()))
            whenever(xdripSourcePlugin.isEnabled()).thenReturn(true)
            val bundle = BundleMock.mocked().apply {
                putString("sensorType", "G6")
            }
            whenever(dataInbox.drain(XdripInbox)).thenReturn(listOf(bundle))

            val result = worker.doWork()

            Assertions.assertEquals(ListenableWorker.Result.success(), result)
            verify(persistenceLayer, never()).insertCgmSourceData(any(), any(), any(), any())
        }
    }

    @Test
    fun `When plugin disabled the inbox is still drained so the pending gate clears`() {
        runBlocking {
            whenever(xdripSourcePlugin.isEnabled()).thenReturn(false)
            val bundle = BundleMock.mocked()
            whenever(dataInbox.drain(XdripInbox)).thenReturn(listOf(bundle))

            val result = worker.doWork()

            Assertions.assertEquals(ListenableWorker.Result.success(workDataOf("Result" to "Plugin not enabled")), result)
            verify(dataInbox).drain(XdripInbox)
            verify(persistenceLayer, never()).insertCgmSourceData(any(), any(), any(), any())
        }
    }

    @Test
    fun `When processing is cancelled the unprocessed bundles are re-queued and cancellation propagates`() {
        runBlocking {
            whenever(xdripSourcePlugin.isEnabled()).thenReturn(true)
            val bundles = listOf(validBundle(), validBundle())
            whenever(dataInbox.drain(XdripInbox)).thenReturn(bundles)
            whenever(persistenceLayer.insertCgmSourceData(anyOrNull(), anyOrNull(), anyOrNull(), anyOrNull()))
                .thenThrow(CancellationException("Job was cancelled"))

            val thrown = runCatching { worker.doWork() }.exceptionOrNull()

            Assertions.assertTrue(thrown is CancellationException)
            verify(dataInbox).requeue(eq(XdripInbox), eq(bundles))
        }
    }

    @Test
    fun `A failed bundle does not stop the batch and the run still succeeds`() {
        runBlocking {
            whenever(xdripSourcePlugin.isEnabled()).thenReturn(true)
            val bundles = listOf(validBundle(), validBundle())
            whenever(dataInbox.drain(XdripInbox)).thenReturn(bundles)
            whenever(persistenceLayer.insertCgmSourceData(anyOrNull(), anyOrNull(), anyOrNull(), anyOrNull()))
                .thenThrow(RuntimeException("db"))
                .thenReturn(Single.just(PersistenceLayer.TransactionResult()))

            val result = worker.doWork()

            // A FAILED result would make WorkManager fail the worker queued behind this one unrun.
            Assertions.assertEquals(ListenableWorker.Result.success(workDataOf("Error" to "1 of 2 bundles failed")), result)
            verify(persistenceLayer, times(2)).insertCgmSourceData(anyOrNull(), anyOrNull(), anyOrNull(), anyOrNull())
        }
    }

    private fun validBundle() = BundleMock.mocked().apply {
        putString(Intents.XDRIP_DATA_SOURCE, "G6 Native")
        putLong(Intents.EXTRA_TIMESTAMP, now - 60000)
        putDouble(Intents.EXTRA_BG_ESTIMATE, 150.0)
        putDouble(Intents.EXTRA_RAW, 150.0)
        putString(Intents.EXTRA_BG_SLOPE_NAME, "Flat")
    }
}
