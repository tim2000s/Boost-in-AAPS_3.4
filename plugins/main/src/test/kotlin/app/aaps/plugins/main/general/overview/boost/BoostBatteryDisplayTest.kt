package app.aaps.plugins.main.general.overview.boost

import app.aaps.plugins.main.general.overview.boost.BoostBatteryDisplay.Kind
import app.aaps.plugins.main.general.overview.boost.BoostBatteryDisplay.LocalPump
import app.aaps.plugins.main.general.overview.boost.BoostBatteryDisplay.NsPump
import app.aaps.plugins.main.general.overview.boost.BoostBatteryDisplay.NsUploader
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

class BoostBatteryDisplayTest {

    private val hour = 3_600_000L
    private val now = 1_800_000_000_000L
    private val stale = 60 * 60_000L

    private fun local(level: Int?, supports: Boolean = true, ageApplies: Boolean = false, patch: Boolean = false) =
        LocalPump(level, supports, ageApplies, patch)

    // --- full app ---

    @Test fun `pump that reports a level shows it`() {
        val r = BoostBatteryDisplay.pumpBattery(false, local(72, ageApplies = true), null, now - 30 * hour, now, stale)
        assertThat(r.kind).isEqualTo(Kind.PERCENT)
        assertThat(r.text).isEqualTo("72%")
        assertThat(r.percent).isEqualTo(72)
        assertThat(r.spoken).isEqualTo("72 percent")
    }

    @Test fun `Dana before first connection reports 0 and falls back to battery age`() {
        val r = BoostBatteryDisplay.pumpBattery(false, local(0, ageApplies = true), null, now - 50 * hour, now, stale)
        assertThat(r.kind).isEqualTo(Kind.AGE)
        assertThat(r.text).isEqualTo("2d 2h")
        assertThat(r.spoken).isEqualTo("changed 2 days 2 hours ago")
    }

    @Test fun `Combo coarse level is ignored because the model declares no battery level`() {
        // ComboV2 maps LOW_BATTERY to 25; PumpType.ACCU_CHEK_COMBO has supportBatteryLevel = false
        val r = BoostBatteryDisplay.pumpBattery(false, local(25, supports = false, ageApplies = true), null, now - 5 * hour, now, stale)
        assertThat(r.kind).isEqualTo(Kind.AGE)
        assertThat(r.text).isEqualTo("0d 5h")
    }

    @Test fun `replaceable battery with no change logged shows the placeholder`() {
        val r = BoostBatteryDisplay.pumpBattery(false, local(null, ageApplies = true), null, null, now, stale)
        assertThat(r.kind).isEqualTo(Kind.UNAVAILABLE)
        assertThat(r.text).isEqualTo(BoostBatteryDisplay.PLACEHOLDER)
        assertThat(r.visible).isTrue()
    }

    @Test fun `Omnipod Dash and Medtrum hide the row`() {
        // null level, no replaceable battery, patch without hardware link
        val r = BoostBatteryDisplay.pumpBattery(false, local(null, supports = false, patch = true), null, null, now, stale)
        assertThat(r.kind).isEqualTo(Kind.HIDDEN)
        assertThat(r.visible).isFalse()
    }

    @Test fun `battery age is not used where the pump has no replaceable battery`() {
        val r = BoostBatteryDisplay.pumpBattery(false, local(null, ageApplies = false, patch = true), null, now - 5 * hour, now, stale)
        assertThat(r.kind).isEqualTo(Kind.HIDDEN)
    }

    @Test fun `full app never reads Nightscout pump data`() {
        val ns = NsPump(clock = now, percent = 90, voltage = null)
        val r = BoostBatteryDisplay.pumpBattery(false, local(40), ns, null, now, stale)
        assertThat(r.text).isEqualTo("40%")
    }

    // --- AAPSClient ---

    @Test fun `client ignores the local virtual pump and shows the main phone's pump battery`() {
        val ns = NsPump(clock = now - 5 * 60_000L, percent = 83, voltage = null)
        val r = BoostBatteryDisplay.pumpBattery(true, local(50), ns, null, now, stale)
        assertThat(r.kind).isEqualTo(Kind.PERCENT)
        assertThat(r.text).isEqualTo("83%")
    }

    @Test fun `client shows voltage when the main phone reports only a voltage`() {
        val ns = NsPump(clock = now, percent = null, voltage = 1.354)
        val r = BoostBatteryDisplay.pumpBattery(true, null, ns, null, now, stale)
        assertThat(r.kind).isEqualTo(Kind.VOLTAGE)
        assertThat(r.text).isEqualTo("1.35V")
    }

    @Test fun `client does not show a stale pump level`() {
        val ns = NsPump(clock = now - 2 * hour, percent = 83, voltage = null)
        val r = BoostBatteryDisplay.pumpBattery(true, null, ns, null, now, stale)
        assertThat(r.kind).isEqualTo(Kind.UNAVAILABLE)
        assertThat(r.text).isEqualTo(BoostBatteryDisplay.PLACEHOLDER)
        assertThat(r.spoken).contains("no recent")
    }

    @Test fun `client falls back to battery age from synced therapy events`() {
        val ns = NsPump(clock = now - 2 * hour, percent = 83, voltage = null)
        val r = BoostBatteryDisplay.pumpBattery(true, null, ns, now - 26 * hour, now, stale)
        assertThat(r.kind).isEqualTo(Kind.AGE)
        assertThat(r.text).isEqualTo("1d 2h")
    }

    @Test fun `client with no device status shows the placeholder, never the virtual 50`() {
        val r = BoostBatteryDisplay.pumpBattery(true, local(50), null, null, now, stale)
        assertThat(r.kind).isEqualTo(Kind.UNAVAILABLE)
        assertThat(r.text).isEqualTo(BoostBatteryDisplay.PLACEHOLDER)
    }

    // --- uploader ---

    @Test fun `uploader row hidden in the full app`() {
        val r = BoostBatteryDisplay.uploaderBattery(false, listOf(NsUploader(now, 64, false)), now, stale)
        assertThat(r.visible).isFalse()
    }

    @Test fun `uploader shows the lowest fresh battery with charging marker`() {
        val ups = listOf(NsUploader(now, 80, false), NsUploader(now - 60_000L, 41, true), NsUploader(now - 3 * hour, 12, false))
        val r = BoostBatteryDisplay.uploaderBattery(true, ups, now, stale)
        assertThat(r.kind).isEqualTo(Kind.PERCENT)
        assertThat(r.text).isEqualTo("ᴪ 41%")
        assertThat(r.spoken).isEqualTo("41 percent, charging")
    }

    @Test fun `uploader with only stale entries shows the placeholder`() {
        val r = BoostBatteryDisplay.uploaderBattery(true, listOf(NsUploader(now - 3 * hour, 70, false)), now, stale)
        assertThat(r.kind).isEqualTo(Kind.UNAVAILABLE)
        assertThat(r.text).isEqualTo(BoostBatteryDisplay.PLACEHOLDER)
    }

    @Test fun `uploader with no entries shows the placeholder`() {
        val r = BoostBatteryDisplay.uploaderBattery(true, emptyList(), now, stale)
        assertThat(r.text).isEqualTo(BoostBatteryDisplay.PLACEHOLDER)
        assertThat(r.visible).isTrue()
    }
}
