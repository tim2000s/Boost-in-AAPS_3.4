package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.plugins.aps.openAPSBoostV5.TrancheThresholdDeriver.Label
import com.google.common.truth.Truth.assertThat
import org.json.JSONObject
import org.junit.jupiter.api.Test
import java.io.File

/**
 * The per-person tranche threshold derivation. The synthetic cases fix the threshold the grid must
 * choose; the fixture case checks that the Kotlin reproduces the offline replay
 * (backtesting/scripts/2026-10-tranche-autoconfig/tranche_derive.py) episode by episode.
 */
class TrancheThresholdDeriverTest {

    private fun ep(p: Double, label: Label?) =
        TrancheThresholdDeriver.Episode(0L, 120.0, 120.0, 0.0, 0.0, 0.0, 0.0, p, label)

    private fun smalls(vararg p: Double) = p.map { ep(it, Label.SMALL) }
    private fun larges(vararg p: Double) = p.map { ep(it, Label.LARGE) }

    @Test fun `the grid spans the preference range in steps of 0_05`() {
        assertThat(TrancheThresholdDeriver.GRID.first()).isEqualTo(0.20)
        assertThat(TrancheThresholdDeriver.GRID.last()).isEqualTo(0.80)
        assertThat(TrancheThresholdDeriver.GRID).hasSize(13)
    }

    @Test fun `known optimum - a clean gap picks the lowest grid value that separates the classes`() {
        // Small episodes all at p <= 0.41, large all at p >= 0.52: J = 1 at 0.45 and 0.50, and the
        // derivation keeps the lower of a tie.
        val eps = smalls(0.31, 0.31, 0.33, 0.33, 0.36, 0.36, 0.38, 0.38, 0.41, 0.41) +
            larges(0.52, 0.52, 0.60, 0.60, 0.70, 0.70, 0.80, 0.80, 0.90, 0.90)
        val d = TrancheThresholdDeriver.fromEpisodes(eps)
        assertThat(d.threshold).isEqualTo(0.45)
        assertThat(d.youdenJ!!).isWithin(1e-12).of(1.0)
        assertThat(d.nSmall).isEqualTo(10)
        assertThat(d.nLarge).isEqualTo(10)
    }

    @Test fun `known optimum - one small episode at 0_47 moves the threshold to 0_50`() {
        val eps = smalls(0.31, 0.31, 0.33, 0.33, 0.36, 0.36, 0.38, 0.38, 0.41, 0.41, 0.47) +
            larges(0.52, 0.52, 0.60, 0.60, 0.70, 0.70, 0.80, 0.80, 0.90, 0.90)
        val d = TrancheThresholdDeriver.fromEpisodes(eps)
        assertThat(d.threshold).isEqualTo(0.50)
        assertThat(d.youdenJ!!).isWithin(1e-12).of(1.0)
        assertThat(TrancheThresholdDeriver.youden(eps, 0.45)).isWithin(1e-12).of(10.0 / 11.0)
    }

    @Test fun `unlabelled episodes do not count towards the evidence`() {
        val eps = smalls(0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3) + larges(0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7) +
            List(20) { ep(0.5, null) }
        val d = TrancheThresholdDeriver.fromEpisodes(eps)
        assertThat(d.nLabelled).isEqualTo(14)
        assertThat(d.threshold).isNull()
        assertThat(d.shortfall).isEqualTo(TrancheThresholdDeriver.Shortfall.TOO_FEW_LABELLED)
    }

    @Test fun `too few labelled episodes gives no threshold`() {
        val d = TrancheThresholdDeriver.fromEpisodes(smalls(0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3) +
            larges(0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7))
        assertThat(d.threshold).isNull()
        assertThat(d.youdenJ).isNull()
        assertThat(d.shortfall).isEqualTo(TrancheThresholdDeriver.Shortfall.TOO_FEW_LABELLED)
    }

    @Test fun `one class missing gives no threshold however many episodes there are`() {
        val d = TrancheThresholdDeriver.fromEpisodes(List(40) { ep(0.3, Label.SMALL) })
        assertThat(d.threshold).isNull()
        assertThat(d.shortfall).isEqualTo(TrancheThresholdDeriver.Shortfall.CLASS_TOO_SMALL)
        val four = TrancheThresholdDeriver.fromEpisodes(List(30) { ep(0.3, Label.SMALL) } + larges(0.7, 0.7, 0.7, 0.7))
        assertThat(four.threshold).isNull()
        assertThat(four.shortfall).isEqualTo(TrancheThresholdDeriver.Shortfall.CLASS_TOO_SMALL)
        val five = TrancheThresholdDeriver.fromEpisodes(List(30) { ep(0.3, Label.SMALL) } + larges(0.7, 0.7, 0.7, 0.7, 0.7))
        assertThat(five.threshold).isNotNull()
    }

    @Test fun `onsets are the first confirmed cycle after any other state, counted once`() {
        val c = listOf(
            0L to "CONFIRMED",                 // first row, no predecessor: not counted
            60_000L to "OBSERVING",
            120_000L to "CONFIRMED",           // onset
            180_000L to "CONFIRMED",           // same episode
            240_000L to "COMMITTED",
            300_000L to "CONFIRMED",           // onset
            360_000L to null,
            420_000L to "CONFIRMED"            // onset after a cycle with no state
        )
        assertThat(TrancheThresholdDeriver.confirmOnsets(c.shuffled(java.util.Random(1))))
            .containsExactly(120_000L, 300_000L, 420_000L).inOrder()
    }

    @Test fun `features and label are read from the glucose series ten minutes on`() {
        // Five-minute series: flat at 120 until the confirm at t=60 min, then +3 per minute to +105.
        val min = 60_000L
        val g = (0..80).map { k ->
            val t = k * 5 * min
            val mins = k * 5 - 60
            t to (120.0 + if (mins <= 0) 0.0 else minOf(105.0, 3.0 * mins))
        }
        val eps = TrancheThresholdDeriver.episodes(listOf(60 * min), g)
        assertThat(eps).hasSize(1)
        val e = eps.single()
        assertThat(e.bgConfirm).isEqualTo(120.0)
        assertThat(e.bgNow).isEqualTo(150.0)
        assertThat(e.riseSince).isEqualTo(30.0)
        assertThat(e.maxRiseSince).isEqualTo(30.0)
        assertThat(e.slopeNow).isEqualTo(15.0)
        assertThat(e.peak).isEqualTo(105.0)
        assertThat(e.label).isEqualTo(Label.LARGE)
        assertThat(e.p).isEqualTo(ConfirmTrancheController.releaseProbability(120.0, 30.0, 30.0, 15.0, 150.0))
    }

    @Test fun `a confirm without enough readings after it is skipped`() {
        val min = 60_000L
        val g = (0..20).map { k -> k * 5 * min to 120.0 }
        assertThat(TrancheThresholdDeriver.episodes(listOf(60 * min), g)).isEmpty()     // 8 readings after
        assertThat(TrancheThresholdDeriver.episodes(listOf(0L), g)).isEmpty()           // none before
    }

    @Test fun `the controller's probability is unchanged by sharing it with the deriver`() {
        // The controller computed this inline before the shared function; the value is pinned.
        val c = ConfirmTrancheController(holdMinutes = 10.0, releaseThreshold = 0.48)
        c.onConfirm(0L, 110.0, 2.0)
        c.onCycle(5 * 60_000L, 130.0)
        assertThat(c.probeProbability(160.0)!!)
            .isEqualTo(ConfirmTrancheController.releaseProbability(110.0, 50.0, 50.0, 30.0, 160.0))
        val z = 2.48631 - 0.014480 * 110.0 - 0.003822 * 50.0 + 0.138821 * 50.0 + 0.072499 * 30.0 - 0.018302 * 160.0
        assertThat(ConfirmTrancheController.releaseProbability(110.0, 50.0, 50.0, 30.0, 160.0))
            .isWithin(1e-12).of(1.0 / (1.0 + Math.exp(-z)))
    }

    // ── agreement with the offline replay ──────────────────────────────────────────────────────

    private fun fixture(): JSONObject {
        val res = javaClass.getResource("/tranche_fixture.json")
        val text = res?.readText() ?: File("src/test/resources/tranche_fixture.json").readText()
        return JSONObject(text)
    }

    @Test fun `the derivation reproduces the Python replay on the shared fixture`() {
        val fx = fixture()
        val cyc = fx.getJSONArray("cycles")
        val cycles = (0 until cyc.length()).map { i ->
            val r = cyc.getJSONArray(i); r.getLong(0) to r.getString(1)
        }
        val gl = fx.getJSONArray("glucose")
        val glucose = (0 until gl.length()).map { i -> val r = gl.getJSONArray(i); r.getLong(0) to r.getDouble(1) }
        val exp = fx.getJSONObject("expected")

        val onsets = TrancheThresholdDeriver.confirmOnsets(cycles)
        val eo = exp.getJSONArray("onsets")
        assertThat(onsets).containsExactlyElementsIn((0 until eo.length()).map { eo.getLong(it) }).inOrder()

        val d = TrancheThresholdDeriver.derive(onsets, glucose)
        val ee = exp.getJSONArray("episodes")
        assertThat(d.episodes).hasSize(ee.length())
        for (i in 0 until ee.length()) {
            val x = ee.getJSONObject(i)
            val e = d.episodes[i]
            assertThat(e.confirmMs).isEqualTo(x.getLong("confirm_ms"))
            assertThat(e.p).isWithin(1e-12).of(x.getDouble("p"))
            assertThat(e.peak).isWithin(1e-9).of(x.getDouble("peak"))
            assertThat(e.label?.name).isEqualTo(if (x.isNull("label")) null else x.getString("label"))
        }
        assertThat(d.nSmall).isEqualTo(exp.getInt("n_small"))
        assertThat(d.nLarge).isEqualTo(exp.getInt("n_large"))
        assertThat(d.shortfall.name).isEqualTo(exp.getString("shortfall"))
        assertThat(d.threshold).isEqualTo(exp.getDouble("threshold"))
        assertThat(d.youdenJ!!).isWithin(1e-12).of(exp.getDouble("j"))
    }
}
