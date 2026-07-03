package app.aaps.plugins.aps.openAPSBoost

import app.aaps.core.data.model.HR
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Unit tests for [HrActivityCalculator] — stateless Karvonen HR zone classifier + HR/step fusion.
 *
 * Uses real HR data objects (data class) with a fixed nowMillis.
 * No mocks needed — the calculator is a pure stateless object.
 */
class HrActivityCalculatorTest {

    private val NOW = 1_700_000_000_000L // fixed epoch ms
    private val WINDOW_MIN = 15

    // ─── helpers ────────────────────────────────────────────────────────────────

    /** Creates a valid HR reading whose timestamp falls INSIDE the window. */
    private fun hrInWindow(bpm: Double, durationMs: Long = 60_000L, offsetFromNow: Long = -60_000L): HR =
        HR(
            duration = durationMs,
            timestamp = NOW + offsetFromNow,
            beatsPerMinute = bpm,
            device = "test",
            isValid = true
        )

    /** Creates a reading at exactly the cutoff boundary (should be EXCLUDED — strictly >). */
    private fun hrAtCutoff(bpm: Double): HR =
        HR(
            duration = 60_000L,
            timestamp = NOW - WINDOW_MIN * 60_000L,   // exactly at cutoff
            beatsPerMinute = bpm,
            device = "test",
            isValid = true
        )

    /** Creates a reading exactly at nowMillis (should be INCLUDED — <= now). */
    private fun hrAtNow(bpm: Double): HR =
        HR(
            duration = 60_000L,
            timestamp = NOW,
            beatsPerMinute = bpm,
            device = "test",
            isValid = true
        )

    // ─── averageHrInWindow() ────────────────────────────────────────────────────

    @Test fun `averageHrInWindow - empty list returns null`() {
        assertThat(HrActivityCalculator.averageHrInWindow(emptyList(), NOW, WINDOW_MIN)).isNull()
    }

    @Test fun `averageHrInWindow - all readings outside window returns null`() {
        val outsideReading = HR(
            duration = 60_000L,
            timestamp = NOW - (WINDOW_MIN + 5) * 60_000L,  // well before cutoff
            beatsPerMinute = 80.0,
            device = "test",
            isValid = true
        )
        assertThat(HrActivityCalculator.averageHrInWindow(listOf(outsideReading), NOW, WINDOW_MIN)).isNull()
    }

    @Test fun `averageHrInWindow - single reading in window returns its bpm`() {
        val reading = hrInWindow(bpm = 72.0, durationMs = 60_000L)
        val result = HrActivityCalculator.averageHrInWindow(listOf(reading), NOW, WINDOW_MIN)
        assertThat(result).isNotNull()
        assertThat(result!!).isWithin(0.001).of(72.0)
    }

    @Test fun `averageHrInWindow - duration-weighted average not simple average`() {
        // Two readings with different durations: 100 bpm for 30s, 50 bpm for 90s
        // Duration-weighted avg = (100*30000 + 50*90000) / (30000+90000) = (3000000+4500000)/120000 = 62.5
        // Simple average would be (100+50)/2 = 75
        val r1 = HR(duration = 30_000L, timestamp = NOW - 30_000L, beatsPerMinute = 100.0, device = "test", isValid = true)
        val r2 = HR(duration = 90_000L, timestamp = NOW - 60_000L, beatsPerMinute = 50.0, device = "test", isValid = true)
        val result = HrActivityCalculator.averageHrInWindow(listOf(r1, r2), NOW, WINDOW_MIN)
        assertThat(result).isNotNull()
        assertThat(result!!).isWithin(0.001).of(62.5)
    }

    @Test fun `averageHrInWindow - invalid readings are excluded`() {
        val validReading = hrInWindow(bpm = 80.0, durationMs = 60_000L, offsetFromNow = -60_000L)
        val invalidReading = HR(
            duration = 60_000L,
            timestamp = NOW - 120_000L,
            beatsPerMinute = 200.0,  // high bpm — should be excluded
            device = "test",
            isValid = false
        )
        val result = HrActivityCalculator.averageHrInWindow(listOf(validReading, invalidReading), NOW, WINDOW_MIN)
        assertThat(result).isNotNull()
        assertThat(result!!).isWithin(0.001).of(80.0)
    }

    @Test fun `averageHrInWindow - reading exactly at nowMillis is included`() {
        val reading = hrAtNow(bpm = 90.0)
        val result = HrActivityCalculator.averageHrInWindow(listOf(reading), NOW, WINDOW_MIN)
        assertThat(result).isNotNull()
        assertThat(result!!).isWithin(0.001).of(90.0)
    }

    @Test fun `averageHrInWindow - reading exactly at cutoff boundary is excluded`() {
        // timestamp == NOW - windowMs → NOT strictly greater than cutoff → excluded
        val reading = hrAtCutoff(bpm = 100.0)
        assertThat(HrActivityCalculator.averageHrInWindow(listOf(reading), NOW, WINDOW_MIN)).isNull()
    }

    // ─── classifyZone() ─────────────────────────────────────────────────────────

    // For HRmax=180, HRrest=60 → reserve = 120
    // HRR% thresholds: 30% → 96 bpm, 40% → 108, 60% → 132, 80% → 156

    @Test fun `classifyZone - just below 30pct is ZONE_1`() {
        // HRR% = (95.9 - 60) / 120 * 100 = 29.92% → ZONE_1
        val zone = HrActivityCalculator.classifyZone(bpm = 95.9, hrMax = 180, hrResting = 60)
        assertThat(zone).isEqualTo(HrActivityCalculator.HrZone.ZONE_1_VERY_LIGHT)
    }

    @Test fun `classifyZone - exactly 30pct is ZONE_2`() {
        // 30% HRR: bpm = 60 + 0.30 * 120 = 96.0
        val zone = HrActivityCalculator.classifyZone(bpm = 96.0, hrMax = 180, hrResting = 60)
        assertThat(zone).isEqualTo(HrActivityCalculator.HrZone.ZONE_2_LIGHT)
    }

    @Test fun `classifyZone - just below 40pct is ZONE_2`() {
        // 39.9% HRR: bpm ≈ 107.88
        val bpm = 60.0 + 0.399 * 120.0
        val zone = HrActivityCalculator.classifyZone(bpm = bpm, hrMax = 180, hrResting = 60)
        assertThat(zone).isEqualTo(HrActivityCalculator.HrZone.ZONE_2_LIGHT)
    }

    @Test fun `classifyZone - exactly 40pct is ZONE_3`() {
        val bpm = 60.0 + 0.40 * 120.0  // = 108
        val zone = HrActivityCalculator.classifyZone(bpm = bpm, hrMax = 180, hrResting = 60)
        assertThat(zone).isEqualTo(HrActivityCalculator.HrZone.ZONE_3_MODERATE)
    }

    @Test fun `classifyZone - just below 60pct is ZONE_3`() {
        val bpm = 60.0 + 0.599 * 120.0
        val zone = HrActivityCalculator.classifyZone(bpm = bpm, hrMax = 180, hrResting = 60)
        assertThat(zone).isEqualTo(HrActivityCalculator.HrZone.ZONE_3_MODERATE)
    }

    @Test fun `classifyZone - exactly 60pct is ZONE_4`() {
        val bpm = 60.0 + 0.60 * 120.0  // = 132
        val zone = HrActivityCalculator.classifyZone(bpm = bpm, hrMax = 180, hrResting = 60)
        assertThat(zone).isEqualTo(HrActivityCalculator.HrZone.ZONE_4_HARD)
    }

    @Test fun `classifyZone - just below 80pct is ZONE_4`() {
        val bpm = 60.0 + 0.799 * 120.0
        val zone = HrActivityCalculator.classifyZone(bpm = bpm, hrMax = 180, hrResting = 60)
        assertThat(zone).isEqualTo(HrActivityCalculator.HrZone.ZONE_4_HARD)
    }

    @Test fun `classifyZone - exactly 80pct is ZONE_5`() {
        val bpm = 60.0 + 0.80 * 120.0  // = 156
        val zone = HrActivityCalculator.classifyZone(bpm = bpm, hrMax = 180, hrResting = 60)
        assertThat(zone).isEqualTo(HrActivityCalculator.HrZone.ZONE_5_MAX)
    }

    @Test fun `classifyZone - HRmax equals HRrest reserve coerced to 1`() {
        // reserve = (60-60).coerceAtLeast(1) = 1
        // HRR% = (61 - 60) / 1 * 100 = 100% → ZONE_5
        val zone = HrActivityCalculator.classifyZone(bpm = 61.0, hrMax = 60, hrResting = 60)
        assertThat(zone).isEqualTo(HrActivityCalculator.HrZone.ZONE_5_MAX)
    }

    @Test fun `classifyZone - HR below resting gives negative HRR percent → ZONE_1`() {
        // bpm = 50, rest = 60 → HRR% negative → ZONE_1
        val zone = HrActivityCalculator.classifyZone(bpm = 50.0, hrMax = 180, hrResting = 60)
        assertThat(zone).isEqualTo(HrActivityCalculator.HrZone.ZONE_1_VERY_LIGHT)
    }

    // ─── classify() — fusion logic ───────────────────────────────────────────────

    private fun makeReadings(bpm: Double, count: Int = 3): List<HR> =
        (1..count).map { i ->
            HR(
                duration = 60_000L,
                timestamp = NOW - i * 60_000L,
                beatsPerMinute = bpm,
                device = "test",
                isValid = true
            )
        }

    // HRmax=180, HRrest=60 → reserve=120
    // ZONE_3 starts at 40% = 108 bpm, ZONE_4 at 60% = 132 bpm

    @Test fun `classify - VIGOROUS_AEROBIC high steps and zone 3 or above`() {
        // 165 bpm: HRR% = (165-60)/120*100 = 87.5% → ZONE_5; steps=400 >= 300
        val result = HrActivityCalculator.classify(
            hrReadings = makeReadings(165.0),
            nowMillis = NOW,
            hrWindowMinutes = WINDOW_MIN,
            hrMax = 180,
            hrResting = 60,
            stepsLast15Min = 400,
            stressDetection = false
        )
        assertThat(result.exerciseState).isEqualTo(HrActivityCalculator.ExerciseState.VIGOROUS_AEROBIC)
        assertThat(result.confidence).isEqualTo(HrActivityCalculator.Confidence.HIGH)
    }

    @Test fun `classify - MODERATE_AEROBIC steps 100-299 and zone 2 plus`() {
        // 110 bpm: HRR% = (110-60)/120*100 = 41.7% → ZONE_3; steps=200
        val result = HrActivityCalculator.classify(
            hrReadings = makeReadings(110.0),
            nowMillis = NOW,
            hrWindowMinutes = WINDOW_MIN,
            hrMax = 180,
            hrResting = 60,
            stepsLast15Min = 200,
            stressDetection = false
        )
        assertThat(result.exerciseState).isEqualTo(HrActivityCalculator.ExerciseState.MODERATE_AEROBIC)
    }

    @Test fun `classify - LIGHT_AEROBIC steps 30-99 and zone 1-2`() {
        // 90 bpm: HRR% = (90-60)/120*100 = 25% → ZONE_1; steps=50
        val result = HrActivityCalculator.classify(
            hrReadings = makeReadings(90.0),
            nowMillis = NOW,
            hrWindowMinutes = WINDOW_MIN,
            hrMax = 180,
            hrResting = 60,
            stepsLast15Min = 50,
            stressDetection = false
        )
        assertThat(result.exerciseState).isEqualTo(HrActivityCalculator.ExerciseState.LIGHT_AEROBIC)
    }

    @Test fun `classify - RESISTANCE low steps and zone 3-4`() {
        // 140 bpm: HRR% = (140-60)/120*100 = 66.7% → ZONE_4; steps=10 < 30
        val result = HrActivityCalculator.classify(
            hrReadings = makeReadings(140.0),
            nowMillis = NOW,
            hrWindowMinutes = WINDOW_MIN,
            hrMax = 180,
            hrResting = 60,
            stepsLast15Min = 10,
            stressDetection = false
        )
        assertThat(result.exerciseState).isEqualTo(HrActivityCalculator.ExerciseState.RESISTANCE)
        assertThat(result.confidence).isEqualTo(HrActivityCalculator.Confidence.MEDIUM)
    }

    @Test fun `classify - STRESS low steps zone 2-3 with stressDetection true`() {
        // 100 bpm: HRR% = (100-60)/120*100 = 33.3% → ZONE_2; steps=5
        val result = HrActivityCalculator.classify(
            hrReadings = makeReadings(100.0),
            nowMillis = NOW,
            hrWindowMinutes = WINDOW_MIN,
            hrMax = 180,
            hrResting = 60,
            stepsLast15Min = 5,
            stressDetection = true
        )
        assertThat(result.exerciseState).isEqualTo(HrActivityCalculator.ExerciseState.STRESS)
    }

    @Test fun `classify - STRESS suppressed when stressDetection false`() {
        // Same as above but stressDetection=false — should NOT be STRESS
        val result = HrActivityCalculator.classify(
            hrReadings = makeReadings(100.0),
            nowMillis = NOW,
            hrWindowMinutes = WINDOW_MIN,
            hrMax = 180,
            hrResting = 60,
            stepsLast15Min = 5,
            stressDetection = false
        )
        assertThat(result.exerciseState).isNotEqualTo(HrActivityCalculator.ExerciseState.STRESS)
    }

    @Test fun `classify - INACTIVE low steps zone 1`() {
        // 65 bpm: HRR% = (65-60)/120*100 = 4.2% → ZONE_1; steps=5
        val result = HrActivityCalculator.classify(
            hrReadings = makeReadings(65.0),
            nowMillis = NOW,
            hrWindowMinutes = WINDOW_MIN,
            hrMax = 180,
            hrResting = 60,
            stepsLast15Min = 5,
            stressDetection = false
        )
        assertThat(result.exerciseState).isEqualTo(HrActivityCalculator.ExerciseState.INACTIVE)
    }

    @Test fun `classify - RESTING default fallback`() {
        // 120 bpm: HRR% = (120-60)/120*100 = 50% → ZONE_3; steps=200 = moderate
        // moderateSteps=true, zone>=ZONE_2 → MODERATE_AEROBIC (not RESTING)
        // To get RESTING: need a case that falls through all other branches.
        // Try high steps but very low zone (contradictory) — not covered by any specific branch:
        // steps=200 (moderate), zone=ZONE_1 (25% HRR, bpm=90): !lowSteps && zone<=ZONE_2 → LIGHT_AEROBIC
        // Try steps=50 (not low), zone=ZONE_3: !lowSteps && zone<=ZONE_2 is false, but lowSteps is also false
        //   → falls to else → RESTING
        val result = HrActivityCalculator.classify(
            hrReadings = makeReadings(115.0), // ZONE_3 ~46% HRR
            nowMillis = NOW,
            hrWindowMinutes = WINDOW_MIN,
            hrMax = 180,
            hrResting = 60,
            stepsLast15Min = 50,  // not low (>=30), not moderate (<100)
            stressDetection = false
        )
        // !lowSteps=true, zone=ZONE_3 > ZONE_2, so !lowSteps && zone<=ZONE_2 is false
        // lowSteps=false so RESISTANCE branch fails; falls to else → RESTING
        assertThat(result.exerciseState).isEqualTo(HrActivityCalculator.ExerciseState.RESTING)
    }

    @Test fun `classify - no HR data returns NONE zone and falls back gracefully`() {
        val result = HrActivityCalculator.classify(
            hrReadings = emptyList(),
            nowMillis = NOW,
            hrWindowMinutes = WINDOW_MIN,
            hrMax = 180,
            hrResting = 60,
            stepsLast15Min = 0,
            stressDetection = false
        )
        assertThat(result.hrZone).isEqualTo(HrActivityCalculator.HrZone.NONE)
        assertThat(result.averageHrBpm).isNull()
        assertThat(result.hrrPercent).isNull()
        assertThat(result.confidence).isEqualTo(HrActivityCalculator.Confidence.LOW)
    }

    @Test fun `classify - HIGH confidence when both signals agree vigorous`() {
        // steps >= 300 + zone >=3 → HIGH
        val result = HrActivityCalculator.classify(
            hrReadings = makeReadings(165.0),
            nowMillis = NOW,
            hrWindowMinutes = WINDOW_MIN,
            hrMax = 180,
            hrResting = 60,
            stepsLast15Min = 400,
            stressDetection = false
        )
        assertThat(result.confidence).isEqualTo(HrActivityCalculator.Confidence.HIGH)
    }

    @Test fun `classify - MEDIUM confidence for light aerobic (one signal)`() {
        val result = HrActivityCalculator.classify(
            hrReadings = makeReadings(90.0),
            nowMillis = NOW,
            hrWindowMinutes = WINDOW_MIN,
            hrMax = 180,
            hrResting = 60,
            stepsLast15Min = 50,
            stressDetection = false
        )
        assertThat(result.confidence).isEqualTo(HrActivityCalculator.Confidence.MEDIUM)
    }

    @Test fun `classify - LOW confidence when no HR data`() {
        val result = HrActivityCalculator.classify(
            hrReadings = emptyList(),
            nowMillis = NOW,
            hrWindowMinutes = WINDOW_MIN,
            hrMax = 180,
            hrResting = 60,
            stepsLast15Min = 400,
            stressDetection = false
        )
        assertThat(result.confidence).isEqualTo(HrActivityCalculator.Confidence.LOW)
    }
}
