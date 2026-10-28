package app.aaps.plugins.aps.openAPSBoost

import app.aaps.plugins.aps.openAPSBoost.HrSourceResolver.Reading
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * HR source visibility (2026-06-28). HrSourceResolver classifies device tags and names the live HR
 * feed for NS without changing any consumer. Pure — nothing here doses.
 */
class HrSourceResolverTest {

    private val NOW = 1_000_000_000_000L
    private fun minsAgo(m: Int) = NOW - m * 60_000L

    @Test fun `canonical classifies garmin, worn model and health connect`() {
        assertThat(HrSourceResolver.canonical("Garmin")).isEqualTo("garmin")
        assertThat(HrSourceResolver.canonical("OPPO OWWE261")).isEqualTo("worn:OPPO OWWE261")
        assertThat(HrSourceResolver.canonical("HealthConnect")).isEqualTo("hc")
        assertThat(HrSourceResolver.canonical("")).isEqualTo("hc")
    }

    @Test fun `realtime worn feed outranks health connect`() {
        assertThat(HrSourceResolver.tier("garmin")).isLessThan(HrSourceResolver.tier("hc"))
        assertThat(HrSourceResolver.tier("worn:OPPO OWWE261")).isLessThan(HrSourceResolver.tier("hc"))
    }

    @Test fun `picks the fresh realtime source over a fresh HC feed`() {
        val r = HrSourceResolver.resolve(
            listOf(
                Reading("OPPO OWWE261", minsAgo(1)),
                Reading("OPPO OWWE261", minsAgo(3)),
                Reading("HealthConnect", minsAgo(2))
            ), NOW
        )
        assertThat(r.active).isEqualTo("worn:OPPO OWWE261")
        assertThat(r.anyFresh).isTrue()
    }

    @Test fun `silent death - no fresh source yields null active`() {
        val r = HrSourceResolver.resolve(
            listOf(Reading("Garmin", minsAgo(25)), Reading("OPPO OWWE261", minsAgo(40))), NOW
        )
        assertThat(r.active).isNull()
        assertThat(r.anyFresh).isFalse()
        // but the dead sources are still surfaced for diagnosis
        assertThat(r.note).contains("garmin(-,1,25m)")
    }

    @Test fun `falls back to HC when only HC is fresh`() {
        val r = HrSourceResolver.resolve(
            listOf(Reading("Garmin", minsAgo(30)), Reading("HealthConnect", minsAgo(2))), NOW
        )
        assertThat(r.active).isEqualTo("hc")
    }

    @Test fun `empty input is none`() {
        val r = HrSourceResolver.resolve(emptyList(), NOW)
        assertThat(r.active).isNull()
        assertThat(r.note).isEqualTo("none")
    }

    // ── HrFeedDarkTracker (F4 phone side, 2026-07-07) ──
    // Edge-detects the whole feed going dark and rations the notification to one per dark episode,
    // waking hours only.

    private fun resAt(vararg readings: Reading) = HrSourceResolver.resolve(readings.toList(), NOW)
    private fun fresh() = resAt(Reading("Garmin", minsAgo(1)))
    private fun dark() = resAt(Reading("Garmin", minsAgo(25)))

    @Test fun `notes exactly the fresh-to-dark edge, naming the last device and age`() {
        val t = HrFeedDarkTracker()
        assertThat(t.onCycle(fresh(), NOW, 12).wentDarkNote).isNull()
        val edge = t.onCycle(dark(), NOW, 12)
        assertThat(edge.wentDarkNote).isEqualTo("HR feed went dark (last garmin 25m ago)")
        // still dark next cycle -> no repeated note
        assertThat(t.onCycle(dark(), NOW + 5 * 60_000L, 12).wentDarkNote).isNull()
    }

    @Test fun `no edge note when the feed was never seen fresh (process start dark)`() {
        val t = HrFeedDarkTracker()
        assertThat(t.onCycle(dark(), NOW, 12).wentDarkNote).isNull()
    }

    @Test fun `notification after 60 dark minutes in waking hours, once per episode`() {
        val t = HrFeedDarkTracker()
        t.onCycle(fresh(), NOW, 12)
        assertThat(t.onCycle(dark(), NOW, 12).raiseNotification).isFalse()               // just went dark
        assertThat(t.onCycle(dark(), NOW + 59 * 60_000L, 12).raiseNotification).isFalse()
        val hit = t.onCycle(dark(), NOW + 60 * 60_000L, 12)
        assertThat(hit.raiseNotification).isTrue()
        assertThat(hit.darkMinutes).isEqualTo(60)
        // once per episode
        assertThat(t.onCycle(dark(), NOW + 65 * 60_000L, 12).raiseNotification).isFalse()
        // feed recovers -> a NEW episode may notify again
        t.onCycle(fresh(), NOW + 70 * 60_000L, 12)
        t.onCycle(dark(), NOW + 71 * 60_000L, 12)
        assertThat(t.onCycle(dark(), NOW + 131 * 60_000L, 12).raiseNotification).isTrue()
    }

    @Test fun `no notification outside 08-22 local (overnight watch charging must not nag)`() {
        val t = HrFeedDarkTracker()
        t.onCycle(fresh(), NOW, 3)
        t.onCycle(dark(), NOW, 3)
        assertThat(t.onCycle(dark(), NOW + 120 * 60_000L, 3).raiseNotification).isFalse()   // 03:00
        assertThat(t.onCycle(dark(), NOW + 130 * 60_000L, 22).raiseNotification).isFalse()  // 22:00 = outside
        // crosses into waking hours while still dark -> fires then
        assertThat(t.onCycle(dark(), NOW + 140 * 60_000L, 8).raiseNotification).isTrue()
    }

    @Test fun `note lists sources best-trust first with freshness flag and count`() {
        val r = HrSourceResolver.resolve(
            listOf(
                Reading("Garmin", minsAgo(1)),
                Reading("Garmin", minsAgo(2)),
                Reading("HealthConnect", minsAgo(20))
            ), NOW
        )
        assertThat(r.note).startsWith("garmin(f,2,")     // realtime first, fresh, 2 readings
        assertThat(r.note).contains("hc(-,1,20m)")       // HC stale
    }
}
