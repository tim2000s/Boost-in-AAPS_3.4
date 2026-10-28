package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/** The site/reservoir age tag: format, missing records, and that the database is not read every cycle. */
class DeviceAgeTagTest {

    private val hour = 3_600_000L
    private val t0 = 1_790_000_000_000L

    @Test fun `ages are hours to one decimal and missing records are a dash`() {
        val tag = DeviceAgeTag { site -> if (site) t0 - (51.25 * hour).toLong() else null }
        assertThat(tag.tag(t0)).isEqualTo("siteAge=51.3; resAge=-; ")
        assertThat(DeviceAgeTag.hours(t0 + hour, t0)).isEqualTo("-")
    }

    @Test fun `change times are read at most once in ten minutes, and again after`() {
        var reads = 0
        var site = t0 - 2 * hour
        val tag = DeviceAgeTag { s -> if (s) { reads++; site } else t0 - 100 * hour }
        assertThat(tag.tag(t0)).isEqualTo("siteAge=2.0; resAge=100.0; ")
        site = t0 + 60_000L - 30_000L                                   // a change logged since
        assertThat(tag.tag(t0 + 60_000L)).isEqualTo("siteAge=2.0; resAge=100.0; ")   // cached: the new change is not seen yet
        assertThat(reads).isEqualTo(1)
        assertThat(tag.tag(t0 + DeviceAgeTag.REFRESH_MS)).startsWith("siteAge=0.2; ")
        assertThat(reads).isEqualTo(2)
    }
}
