package app.aaps.plugins.aps.openAPSBoost

import app.aaps.plugins.aps.openAPSBoost.DailyStepHistoryTracker.DailyTotal
import app.aaps.plugins.aps.openAPSBoost.DailyStepHistoryTracker.History
import app.aaps.plugins.aps.openAPSBoost.DailyStepHistoryTracker.MultiSourceHistory
import app.aaps.plugins.aps.openAPSBoost.StepSourceResolver.SourceState
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * Activity-load source abstraction (2026-06-28). StepSourceResolver selection + DailyStepHistoryTracker
 * multi-source history, overlap calibration, and scaled bridging. Pure — nothing here doses.
 *
 * Headline guarantee: when the primary device changes, the old source's days BRIDGE the new source's
 * window (no warmup reset) AND are scaled into the new source's units, so a phone that undercounts vs
 * a watch does not read as a false drop in activity.
 */
class StepSourceBridgeTest {

    private val T = DailyStepHistoryTracker

    private fun srcHist(src: String, days: Map<Long, Int>) =
        src to History(days.mapValues { (d, s) -> DailyTotal(d, s, src) }.toMutableMap())

    private fun msh(vararg srcDays: Pair<String, History>) =
        MultiSourceHistory(srcDays.toMap().toMutableMap())

    // ── Resolver: canonicalisation + trust order ────────────────────────────────────────────────

    @Test fun `canonical maps garmin pkg and bare HC pkg`() {
        assertThat(StepSourceResolver.canonical("com.garmin.android.apps.connectmobile")).isEqualTo("garmin")
        assertThat(StepSourceResolver.canonical("com.google.android.apps.fitness")).isEqualTo("hc:fitness")
        assertThat(StepSourceResolver.canonical("wear")).isEqualTo("wear")
        assertThat(StepSourceResolver.canonical("phone")).isEqualTo("phone")
    }

    @Test fun `trust order is wear then garmin then HC then phone`() {
        assertThat(StepSourceResolver.tier("wear")).isLessThan(StepSourceResolver.tier("garmin"))
        assertThat(StepSourceResolver.tier("garmin")).isLessThan(StepSourceResolver.tier("hc:fitness"))
        assertThat(StepSourceResolver.tier("hc:fitness")).isLessThan(StepSourceResolver.tier("phone"))
    }

    @Test fun `resolve picks highest-trust fresh source`() {
        val r = StepSourceResolver.resolve(
            listOf(
                SourceState("phone", fresh = true, coverageDays = 20, stepsToday = 5000),
                SourceState("wear", fresh = true, coverageDays = 2, stepsToday = 6000),
                SourceState("garmin", fresh = false, coverageDays = 20, stepsToday = 9000)
            )
        )
        assertThat(r.active).isEqualTo("wear")          // worn watch wins even with little history
        assertThat(r.stepsToday).isEqualTo(6000)
        assertThat(r.activeFresh).isTrue()
    }

    @Test fun `resolve falls back to highest-trust source with data when none fresh`() {
        val r = StepSourceResolver.resolve(
            listOf(
                SourceState("phone", fresh = false, coverageDays = 20, stepsToday = 5000),
                SourceState("garmin", fresh = false, coverageDays = 20, stepsToday = 9000)
            )
        )
        assertThat(r.active).isEqualTo("garmin")
    }

    @Test fun `resolve with nothing yields null active`() {
        val r = StepSourceResolver.resolve(emptyList())
        assertThat(r.active).isNull()
        assertThat(r.stepsToday).isEqualTo(0)
    }

    // ── Calibration ─────────────────────────────────────────────────────────────────────────────

    @Test fun `calibration is median ratio over overlapping days`() {
        val active = History((1L..5L).associateWith { DailyTotal(it, 9000, "phone") }.toMutableMap())
        val donor = History((1L..5L).associateWith { DailyTotal(it, 14000, "wear") }.toMutableMap())
        val cal = T.calibration(active, donor)!!
        assertThat(cal).isWithin(1e-6).of(9000.0 / 14000.0)
    }

    @Test fun `calibration null when too little overlap`() {
        val active = History(mutableMapOf(1L to DailyTotal(1, 9000, "phone"), 2L to DailyTotal(2, 9000, "phone")))
        val donor = History((1L..5L).associateWith { DailyTotal(it, 14000, "wear") }.toMutableMap())
        assertThat(T.calibration(active, donor)).isNull()   // only 2 overlap days < MIN_OVERLAP_DAYS
    }

    @Test fun `calibration ignores zero-step days`() {
        val active = History((1L..5L).associateWith { DailyTotal(it, 9000, "phone") }.toMutableMap())
        // donor has a zero day that must not pull the ratio to infinity
        val donor = History((1L..5L).associate { it to DailyTotal(it, if (it == 1L) 0 else 14000, "wear") }.toMutableMap())
        val cal = T.calibration(active, donor)!!
        assertThat(cal).isWithin(1e-6).of(9000.0 / 14000.0)
    }

    // ── Bridging: the headline device-switch guarantee ─────────────────────────────────────────

    @Test fun `watch dies, phone takes over - scaled bridge avoids false inactivity`() {
        // wear logged 14k/day for days 1..20 then died; phone (always carried) logged 9k/day and now
        // owns today (day 21). The window is wear-heavy but must read as NORMAL activity, not a drop.
        val multi = msh(
            srcHist("wear", (1L..20L).associateWith { 14000 }),
            srcHist("phone", (16L..20L).associateWith { 9000 })   // phone only has recent days
        )
        val bridged = T.bridgedWindow(multi, activeSource = "phone", todayIndex = 21)
        // coverage restored across the whole window from the scaled wear donor
        assertThat(bridged.history.days.keys).containsAtLeast(1L, 10L, 20L)
        assertThat(bridged.calibrated).isTrue()                  // ≥3 overlap days (16..20)
        // bridged wear days scaled phone-ward: 14000 * (9000/14000) ≈ 9000
        assertThat(bridged.history.days[1L]!!.steps).isWithin(50).of(9000)
        // baseline is in phone units, and yesterday (phone 9000) ≈ baseline → ratio ~1, NOT inactivity
        val f = T.shadowFactors(bridged.history, todayIndex = 21)
        assertThat(T.baseline(bridged.history, 21)).isWithin(200).of(9000)
        assertThat(f.note).isNotEqualTo("inactivity")
        assertThat(f.wouldDeltaIsfPct).isWithin(1.0).of(0.0)
    }

    @Test fun `bridging guarantees coverage so no warmup gap on device switch`() {
        // active source (wear, just adopted) has almost no history; donor (phone) carries the window.
        val multi = msh(
            srcHist("wear", mapOf(20L to 13000)),
            srcHist("phone", (1L..20L).associateWith { 9000 })
        )
        // single-source view of wear alone would be insufficient-history:
        assertThat(T.baseline(multi.sources["wear"]!!, 21)).isNull()
        // bridged view has full coverage → baseline forms (no warmup)
        val bridged = T.bridgedWindow(multi, activeSource = "wear", todayIndex = 21)
        assertThat(T.baseline(bridged.history, 21)).isNotNull()
    }

    @Test fun `bridge without enough overlap is flagged uncalibrated and spliced raw`() {
        val multi = msh(
            srcHist("wear", mapOf(20L to 13000)),                 // 1 day only → no overlap to calibrate
            srcHist("phone", (1L..20L).associateWith { 9000 })
        )
        val bridged = T.bridgedWindow(multi, activeSource = "wear", todayIndex = 21)
        assertThat(bridged.calibrated).isFalse()
        assertThat(bridged.history.days[1L]!!.steps).isEqualTo(9000)   // raw phone value, no scaling
    }

    @Test fun `highest-trust donor wins a bridged day`() {
        val multi = msh(
            srcHist("garmin", (1L..20L).associateWith { 12000 }),
            srcHist("phone", (1L..20L).associateWith { 9000 })
        )
        // active = wear (no days) → every day bridged; garmin (tier 1) should win over phone (tier 3)
        val bridged = T.bridgedWindow(multi, activeSource = "wear", todayIndex = 21)
        assertThat(bridged.history.days[5L]!!.source).isEqualTo("garmin")
    }

    @Test fun `active source days are never overwritten by donors`() {
        val multi = msh(
            srcHist("wear", mapOf(10L to 15000)),
            srcHist("phone", (1L..20L).associateWith { 9000 })
        )
        val bridged = T.bridgedWindow(multi, activeSource = "wear", todayIndex = 21)
        assertThat(bridged.history.days[10L]!!.steps).isEqualTo(15000)   // wear's own day kept
        assertThat(bridged.history.days[10L]!!.source).isEqualTo("wear")
    }

    // ── MultiSourceHistory: persistence + merge ────────────────────────────────────────────────

    @Test fun `multi-source serialize round-trips`() {
        val multi = msh(
            srcHist("wear", mapOf(1L to 14000, 2L to 15000)),
            srcHist("phone", mapOf(1L to 9000))
        )
        val back = MultiSourceHistory.deserialize(multi.serialize())
        assertThat(back.sources.keys).containsExactly("wear", "phone")
        assertThat(back.sources["wear"]!!.days[2L]!!.steps).isEqualTo(15000)
    }

    @Test fun `deserialize migrates old single-history format grouped by source`() {
        // old format: a flat History with per-day src tags
        val old = History(mutableMapOf(
            1L to DailyTotal(1, 14000, "wear"),
            2L to DailyTotal(2, 9000, "com.garmin.android.apps.connectmobile")
        ))
        val migrated = MultiSourceHistory.deserialize(old.serialize())
        assertThat(migrated.sources.keys).containsExactly("wear", "garmin")
        assertThat(migrated.sources["garmin"]!!.days[2L]!!.steps).isEqualTo(9000)
    }

    @Test fun `corrupt blob deserializes to empty multi-history`() {
        assertThat(MultiSourceHistory.deserialize("{{bad").sources).isEmpty()
        assertThat(MultiSourceHistory.deserialize("").sources).isEmpty()
    }

    @Test fun `mergeSource adds completed days to the right source and prunes empties`() {
        var multi = MultiSourceHistory()
        multi = T.mergeSource(multi, "wear", listOf(DailyTotal(100, 14000, "wear"), DailyTotal(101, 15000, "wear")), todayIndex = 102)
        assertThat(multi.sources["wear"]!!.days.keys).containsExactly(100L, 101L)
        // a source whose only days fall outside the window is pruned
        multi = T.mergeSource(multi, "phone", listOf(DailyTotal(1, 9000, "phone")), todayIndex = 102)
        assertThat(multi.sources).doesNotContainKey("phone")
    }

    // ── Phone-anchored window: the watch-SWAP case the old bridge could never calibrate ──────────

    /**
     * Garmin era (days 0–9) then a watch SWAP to Wear (days 10–19) with ZERO overlap between them;
     * the phone carries through both eras. The phone is the calibration frame, so both watch eras
     * scale into consistent phone units and the swap leaves no false jump — exactly what
     * watch-to-watch bridging could not do (no garmin↔wear overlap day exists).
     */
    @Test fun `phone-anchored window bridges a watch swap via the phone (no direct overlap)`() {
        val phone = srcHist("phone", (0L..19L).associateWith { 7000 })          // continuous, undercounts
        val garmin = srcHist("garmin", (0L..9L).associateWith { 9000 })          // era 1
        val wear = srcHist("wear", (10L..19L).associateWith { 14000 })           // era 2 — no overlap w/ garmin
        val multi = msh(phone, garmin, wear)

        // Old logic: anchored on wear, can't calibrate wear↔garmin (no shared day) → raw, inconsistent
        val old = T.bridgedWindow(multi, activeSource = "wear", todayIndex = 20)
        assertThat(old.calibrated).isFalse()

        // New logic: phone overlaps BOTH eras → every day expressed in phone units (~7000), calibrated
        val r = T.phoneAnchoredWindow(multi, todayIndex = 20)
        assertThat(r.calibrated).isTrue()
        assertThat(r.history.days.keys).containsExactlyElementsIn((0L..19L).toList())
        // garmin day (9000 × 7000/9000) and wear day (14000 × 7000/14000) both land ~7000 — no jump
        assertThat(r.history.days[5]!!.steps).isEqualTo(7000)
        assertThat(r.history.days[15]!!.steps).isEqualTo(7000)
        assertThat(r.donorsUsed).containsExactly("garmin", "wear")
        assertThat(T.baseline(r.history, todayIndex = 20)).isEqualTo(7000)
    }

    @Test fun `phone-anchored window prefers a scaled worn value over the phone's own day`() {
        // both phone and wear have every day; wear (worn, accurate) should drive, scaled to phone units
        val phone = srcHist("phone", (0L..9L).associateWith { 6000 })
        val wear = srcHist("wear", (0L..9L).associateWith { 12000 })             // phone/wear = 0.5
        val r = T.phoneAnchoredWindow(msh(phone, wear), todayIndex = 10)
        assertThat(r.calibrated).isTrue()
        assertThat(r.history.days[4]!!.steps).isEqualTo(6000)                     // 12000 × 0.5
        assertThat(r.history.days[4]!!.source).isEqualTo("wear")                  // worn drove it
    }

    @Test fun `phone-anchored window during phone warmup holds the higher raw worn count, flagged`() {
        // phone has only 2 days (< MIN_OVERLAP_DAYS) so wear can't be scaled yet. HOLD-HIGHER
        // (2026-07-03): the uncalibrated worn count is NOT discarded for the phone's lower own-day —
        // that cascade recorded 07-02 as the pocketed phone's 2227/3095 while the watch knew 6224.
        val phone = srcHist("phone", mapOf(8L to 7000, 9L to 7000))
        val wear = srcHist("wear", (0L..9L).associateWith { 14000 })
        val r = T.phoneAnchoredWindow(msh(phone, wear), todayIndex = 10)
        assertThat(r.calibrated).isFalse()                                       // raw fallback used
        assertThat(r.history.days[8]!!.steps).isEqualTo(14000)                   // wear raw held over phone 7000
        assertThat(r.history.days[8]!!.source).isEqualTo("wear")
        assertThat(r.history.days[0]!!.steps).isEqualTo(14000)                    // wear raw (flagged)
    }

    // ── Hold-higher rollover (2026-07-03 incident): wear 6224 @23:57 must not roll over as the
    //    phone's 2227, nor creep as a lower counter's intraday value tracks in as "yesterday". ────

    @Test fun `rollover holds the higher source - the 2026-07-02 case`() {
        // Yesterday (day 9): wear counted 6224; the pocketed phone only 2227. Wear can't be
        // calibrated yet (no phone overlap before day 8). The day must record 6224, not 2227.
        val phone = srcHist("phone", mapOf(8L to 3000, 9L to 2227))
        val wear = srcHist("wear", mapOf(9L to 6224))
        val r = T.phoneAnchoredWindow(msh(phone, wear), todayIndex = 10)
        assertThat(r.history.days[9]!!.steps).isEqualTo(6224)
        assertThat(r.history.days[9]!!.source).isEqualTo("wear")
        val f = T.shadowFactors(r.history, todayIndex = 10)
        assertThat(f.lastDaySteps).isEqualTo(6224)
    }

    @Test fun `a post-midnight lower HC value cannot drag yesterday down`() {
        // Yesterday recorded at 6224; after midnight the source re-syncs a stale/partial 3095 for
        // the same day. merge() holds the higher recorded total.
        var h = History(mutableMapOf(9L to DailyTotal(9, 6224, "wear")))
        h = T.merge(h, listOf(DailyTotal(9, 3095, "wear")), todayIndex = 10)
        assertThat(h.days[9]!!.steps).isEqualTo(6224)
        // an upward revision still applies
        h = T.merge(h, listOf(DailyTotal(9, 6500, "wear")), todayIndex = 10)
        assertThat(h.days[9]!!.steps).isEqualTo(6500)
    }

    @Test fun `heldNote breadcrumb fires when yesterday is held over a lower source`() {
        val phone = srcHist("phone", mapOf(8L to 3000, 9L to 3095))
        val wear = srcHist("wear", mapOf(9L to 6224))
        val r = T.phoneAnchoredWindow(msh(phone, wear), todayIndex = 10)
        assertThat(r.heldNote).isEqualTo("held wear 6224 over phone 3095")
        // single-candidate yesterday → no note
        val solo = T.phoneAnchoredWindow(msh(srcHist("wear", mapOf(9L to 6224))), todayIndex = 10)
        assertThat(solo.heldNote).isNull()
    }

    @Test fun `toPhoneUnits scales a worn today count and passes phone or uncalibrated through`() {
        val phone = srcHist("phone", (0L..9L).associateWith { 7000 })
        val wear = srcHist("wear", (0L..9L).associateWith { 14000 })             // phone/wear = 0.5
        val multi = msh(phone, wear)
        assertThat(T.toPhoneUnits(10000, "wear", multi)).isEqualTo(5000)         // 10000 × 0.5
        assertThat(T.toPhoneUnits(7000, "phone", multi)).isEqualTo(7000)         // phone → unchanged
        // no overlap to calibrate → returned raw
        val noOverlap = msh(srcHist("phone", mapOf(0L to 7000)), wear)
        assertThat(T.toPhoneUnits(10000, "wear", noOverlap)).isEqualTo(10000)
    }
}
