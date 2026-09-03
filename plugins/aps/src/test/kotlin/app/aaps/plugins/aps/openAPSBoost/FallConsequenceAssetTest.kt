package app.aaps.plugins.aps.openAPSBoost

import android.content.Context
import android.content.res.AssetManager
import app.aaps.core.interfaces.logging.AAPSLogger
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test
import org.mockito.Mockito.mock
import org.mockito.kotlin.whenever
import java.io.File

/**
 * Loads the asset that actually ships and runs a fall through it.
 *
 * The unit test beside this one pins the feature builder against the training pipeline, which
 * catches train/serve skew but says nothing about whether the model file parses or whether
 * evaluate() ever returns a score. On the device it returned null on every cycle for two days
 * while logging nothing, because every failure in that path is a silent null by design.
 */
class FallConsequenceAssetTest {

    private val assetPath = "boost/fall_consequence_v1.json"

    private fun shadowWithRealAsset(): FallConsequenceShadow {
        val f = File("../../app/src/main/assets/$assetPath").let {
            if (it.exists()) it else File("app/src/main/assets/$assetPath")
        }
        assertThat(f.exists()).isTrue()
        val assets = mock(AssetManager::class.java)
        whenever(assets.open(assetPath)).thenAnswer { f.inputStream() }
        val ctx = mock(Context::class.java)
        whenever(ctx.assets).thenReturn(assets)
        return FallConsequenceShadow(ctx, mock(AAPSLogger::class.java))
    }

    @Test fun theShippedAssetParses() {
        assertThat(shadowWithRealAsset().isLoaded()).isTrue()
    }

    @Test fun aFallThatQualifiesProducesAScore() {
        val shadow = shadowWithRealAsset()
        // 70 minutes of 1-minute readings, falling 150 to 96 over the last 20
        val start = 1788400000_000L
        val n = 71
        val times = LongArray(n) { start + it * 60_000L }
        val values = DoubleArray(n) { i ->
            if (i < 50) 150.0 else 150.0 - (i - 50) * 2.7
        }
        val r = shadow.evaluate(times, values) { 12.0 }
        assertThat(r).isNotNull()
        assertThat(r!!.score).isIn(com.google.common.collect.Range.closed(0.0, 1.0))
        assertThat(r.onsetAgeMin).isEqualTo(20)
        assertThat(r.fall).isGreaterThan(25.0)
    }

    @Test fun aFlatTraceProducesNothing() {
        val start = 1788400000_000L
        val times = LongArray(71) { start + it * 60_000L }
        val values = DoubleArray(71) { 120.0 }
        assertThat(shadowWithRealAsset().evaluate(times, values) { 12.0 }).isNull()
    }
}
