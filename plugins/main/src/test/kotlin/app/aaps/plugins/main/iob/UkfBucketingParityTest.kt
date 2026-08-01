package app.aaps.plugins.main.iob

import app.aaps.core.data.model.GV
import app.aaps.core.data.model.SourceSensor
import app.aaps.core.data.model.TrendArrow
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.plugins.main.iob.iobCobCalculator.data.AutosensDataStoreObject
import app.aaps.shared.tests.TestBaseWithProfile
import org.junit.jupiter.api.Test
import org.mockito.kotlin.mock
import org.mockito.kotlin.whenever
import java.io.File

/**
 * Bucketer-parity harness: runs the REAL shipped AAPS `AutosensDataStoreObject.createBucketedData`
 * over the corpus and writes each trace's bucketed grid, so it can be diffed against Trio's Swift
 * `GlucoseBucketing.bucketed()`. `referenceTime = -1` per trace (single-pass anchoring — the same
 * convention the existing AutosensDataStoreTest uses, and what Trio's per-cycle bucketing does).
 */
class UkfBucketingParityTest : TestBaseWithProfile() {

    private val autosensDataStore = AutosensDataStoreObject()

    // Silent, non-recording logger: createBucketedData debug-logs per bucket, which over 334k points
    // floods stdout and (as a recording mock) exhausts the test-worker heap (cf. the earlier Kotlin
    // OOM). stubOnly = true → no invocation retention, no output.
    private val silentLogger: AAPSLogger = mock(stubOnly = true)

    private val corpusPath = System.getenv("BUCKET_CORPUS")
        ?: "/private/tmp/claude-501/-Users-timstreet-StudioProjects-Trio/5e20430b-530e-407c-8594-5683eb2070c4/scratchpad/corpus_full.flat"
    private val outPath = System.getenv("BUCKET_OUT")
        ?: "/private/tmp/claude-501/-Users-timstreet-StudioProjects-Trio/5e20430b-530e-407c-8594-5683eb2070c4/scratchpad/kotlin_buckets_full.flat"

    @Test fun `dump AAPS bucketed grid for every corpus trace`() {
        whenever(iobCobCalculator.ads).thenReturn(autosensDataStore)
        val corpus = File(corpusPath)
        if (!corpus.exists()) { println("CORPUS not found at $corpusPath — skipping"); return }

        val out = File(outPath).bufferedWriter()
        var traces = 0; var points = 0
        corpus.bufferedReader().use { br ->
            var line = br.readLine()
            while (line != null) {
                require(line.startsWith("T ")) { "expected header, got: $line" }
                val parts = line.split(" ")
                val name = parts[1]; val n = parts[2].toInt()
                val readings = ArrayList<GV>(n)
                for (i in 0 until n) {
                    val p = br.readLine().split(" ")
                    readings.add(
                        GV(
                            raw = 0.0, noise = 0.0,
                            value = p[1].toDouble(), timestamp = p[0].toLong(),
                            sourceSensor = SourceSensor.UNKNOWN, trendArrow = TrendArrow.FLAT
                        )
                    )
                }
                autosensDataStore.referenceTime = -1
                autosensDataStore.bgReadings = readings
                autosensDataStore.createBucketedData(silentLogger, dateUtil)
                val bucketed = autosensDataStore.bucketedData
                // <3 readings → AAPS leaves bucketedData null; Trio passes the input through. Emit the
                // raw input in that degenerate case so the two sides line up.
                if (bucketed == null) {
                    out.write("B $name $n\n")
                    for (r in readings) out.write("${r.timestamp} ${r.value}\n")
                    points += n
                } else {
                    out.write("B $name ${bucketed.size}\n")
                    for (b in bucketed) out.write("${b.timestamp} ${b.value}\n")
                    points += bucketed.size
                }
                traces++
                line = br.readLine()
            }
        }
        out.flush(); out.close()
        println("kotlin buckets: $traces traces, $points points -> $outPath")
    }
}
