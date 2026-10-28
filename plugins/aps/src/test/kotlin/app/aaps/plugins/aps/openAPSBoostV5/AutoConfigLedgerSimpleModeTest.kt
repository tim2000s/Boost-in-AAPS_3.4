package app.aaps.plugins.aps.openAPSBoostV5

import app.aaps.core.keys.DoubleKey
import app.aaps.core.keys.StringKey
import app.aaps.core.keys.interfaces.Preferences
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test
import org.mockito.kotlin.any
import org.mockito.kotlin.argumentCaptor
import org.mockito.kotlin.eq
import org.mockito.kotlin.mock
import org.mockito.kotlin.verify
import org.mockito.kotlin.whenever

/**
 * Auto-config's string state read in Simple Mode (dose-path audit item 14).
 *
 * Every StringKey auto-config keeps is `defaultedBySM = true`, so `Preferences.get` returns the
 * empty default while Simple Mode is on. The mock below models Simple Mode the way
 * BoostDosingPreferencesTest does: `get` returns the masked default and `getIfExists` the value
 * actually stored. A ledger read through `get` sees nothing, so every weekly re-derivation was a
 * first sight that recorded a baseline and moved nothing, and the written ledger read empty.
 */
class AutoConfigLedgerSimpleModeTest {

    private fun simpleMode(stored: Map<StringKey, String>): Preferences {
        val prefs = mock<Preferences>()
        for (k in StringKey.entries) {
            whenever(prefs.get(k)).thenReturn(k.defaultValue)          // the Simple-Mode mask
            whenever(prefs.getIfExists(k)).thenReturn(stored[k])       // what is actually stored
        }
        return prefs
    }

    @Test fun `the re-derivation baseline is read in Simple Mode`() {
        val prefs = simpleMode(mapOf(StringKey.ApsBoostV5RedriveBaseline to """{"boost_v5_committed_cap_u":1.1}"""))
        assertThat(AutoConfigLedger.read(prefs, StringKey.ApsBoostV5RedriveBaseline))
            .containsExactly(DoubleKey.ApsBoostV5CommittedCapU.key, 1.1)
    }

    @Test fun `the pending and written ledgers are read in Simple Mode`() {
        val prefs = simpleMode(mapOf(
            StringKey.ApsBoostV5AutoConfigPending to """{"boost_v5_aggression":0.92}""",
            StringKey.ApsBoostV5AutoConfigWritten to """{"boost_v5_tranche_threshold":0.65}"""))
        assertThat(AutoConfigLedger.read(prefs, StringKey.ApsBoostV5AutoConfigPending))
            .containsExactly(DoubleKey.ApsBoostV5Aggression.key, 0.92)
        assertThat(AutoConfigLedger.read(prefs, StringKey.ApsBoostV5AutoConfigWritten))
            .containsExactly(DoubleKey.ApsBoostV5TrancheThreshold.key, 0.65)
    }

    @Test fun `an update keeps the entries already stored`() {
        val prefs = simpleMode(mapOf(StringKey.ApsBoostV5RedriveBaseline to """{"boost_v5_committed_cap_u":1.1}"""))
        AutoConfigLedger.put(prefs, StringKey.ApsBoostV5RedriveBaseline, DoubleKey.ApsBoostV5ConfirmedCapU.key, 3.0)
        val written = argumentCaptor<String>()
        verify(prefs).put(eq(StringKey.ApsBoostV5RedriveBaseline), written.capture())
        assertThat(written.firstValue).contains("\"boost_v5_committed_cap_u\":1.1")
        assertThat(written.firstValue).contains("\"boost_v5_confirmed_cap_u\":3")
    }

    @Test fun `a baseline stored in Simple Mode lets the second re-derivation move a knob`() {
        // End to end through redrive(): the baseline is the only thing between first sight and a write.
        val prefs = simpleMode(mapOf(StringKey.ApsBoostV5RedriveBaseline to """{"boost_v5_committed_cap_u":1.0}"""))
        val baselines = AutoConfigLedger.read(prefs, StringKey.ApsBoostV5RedriveBaseline)
        val s = BoostV5AutoConfig.compute(
            BoostV5AutoConfig.V1Profile(
                daysWithData = 28, bgReadingCount = 6000, tddMedianU = 48.0,   // derived committedCap 1.2
                manualBolusesU = List(20) { 4.0 }, smbAmountsU = List(200) { 0.3 },
                tbrBelow70Pct = 1.0, timeBelow54Pct = 0.1, meanGlucoseMgdl = 130.0,
                currentMaxIobU = 6.0, currentMaxBolusU = 2.5))!!
        val stored = mutableMapOf(DoubleKey.ApsBoostV5CommittedCapU to 1.0, DoubleKey.ApsBoostV5ConfirmedCapU to 3.0)
        val res = BoostV5AutoConfigApply.redrive(
            s, 1.0, 0.1,
            storedValue = { stored[it] }, baselineValue = { baselines[it.key] }, pendingValue = { null },
            put = { k, v -> stored[k] = v }, setBaseline = { _, _ -> }, setPending = { _, _ -> })
        assertThat(res.first { it.key == DoubleKey.ApsBoostV5CommittedCapU }.outcome)
            .isEqualTo(BoostV5AutoConfigApply.Outcome.REDRIVEN)
        assertThat(stored[DoubleKey.ApsBoostV5CommittedCapU]!!).isWithin(1e-6).of(1.2)
    }

    @Test fun `the reason breadcrumbs survive Simple Mode`() {
        val prefs = simpleMode(mapOf(
            StringKey.ApsBoostV5AutoConfigSummary to "applied=3,heldTBR=0,keptUser=1",
            StringKey.ApsBoostV5RedriveSummary to "@2026-10-01,win=28d,ev=7,ch=1",
            StringKey.ApsBoostHistorySyncSummary to "ok"))
        assertThat(AutoConfigLedger.reasonBreadcrumbs(prefs)).isEqualTo(
            "autocfg=applied=3,heldTBR=0,keptUser=1; autordv=@2026-10-01,win=28d,ev=7,ch=1; histsync=ok; ")
    }

    @Test fun `nothing stored gives empty ledgers and no breadcrumbs`() {
        val prefs = simpleMode(emptyMap())
        assertThat(AutoConfigLedger.read(prefs, StringKey.ApsBoostV5RedriveBaseline)).isEmpty()
        assertThat(AutoConfigLedger.reasonBreadcrumbs(prefs)).isEmpty()
        assertThat(AutoConfigLedger.text(prefs, StringKey.ApsBoostV5RedriveHistory)).isEmpty()
    }

    @Test fun `the redrive history is read in Simple Mode`() {
        val prefs = simpleMode(mapOf(StringKey.ApsBoostV5RedriveHistory to "2026-10-01 CommittedCapU 1.2 (was 1.0)"))
        assertThat(AutoConfigLedger.text(prefs, StringKey.ApsBoostV5RedriveHistory))
            .isEqualTo("2026-10-01 CommittedCapU 1.2 (was 1.0)")
        verify(prefs, org.mockito.kotlin.never()).put(any<StringKey>(), any<String>())
    }
}
