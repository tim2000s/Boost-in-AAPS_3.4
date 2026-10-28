package app.aaps.plugins.aps.openAPSBoostV5

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * The property that has to hold whatever the rule decides is that this never delivers more than the
 * engine would have delivered without it. Everything else is a question of when.
 */
class ConfirmTrancheControllerTest {

    private val min = 60_000L

    @Test fun `the immediate part is the configured fraction and the rest is held`() {
        val c = ConfirmTrancheController(immediateFraction = 0.5)
        assertThat(c.onConfirm(0L, 120.0, 2.0)).isWithin(1e-9).of(1.0)
        assertThat(c.heldU()).isWithin(1e-9).of(1.0)
    }

    @Test fun `nothing is released before the hold window`() {
        val c = ConfirmTrancheController(holdMinutes = 10.0)
        c.onConfirm(0L, 120.0, 2.0)
        assertThat(c.onCycle(5 * min, 160.0)).isEqualTo(0.0)
        assertThat(c.heldU()).isWithin(1e-9).of(1.0)
    }

    @Test fun `a continuing rise releases the remainder`() {
        val c = ConfirmTrancheController(holdMinutes = 10.0, releaseThreshold = 0.48)
        c.onConfirm(0L, 110.0, 2.0)
        c.onCycle(5 * min, 130.0)
        assertThat(c.onCycle(10 * min, 160.0)).isWithin(1e-9).of(1.0)
        assertThat(c.heldU()).isEqualTo(0.0)
    }

    @Test fun `a rise that goes nowhere keeps the remainder`() {
        val c = ConfirmTrancheController(holdMinutes = 10.0, releaseThreshold = 0.48)
        c.onConfirm(0L, 180.0, 2.0)
        c.onCycle(5 * min, 181.0)
        assertThat(c.onCycle(10 * min, 180.0)).isEqualTo(0.0)
        assertThat(c.heldU()).isEqualTo(0.0)   // decided, not carried
    }

    @Test fun `a hold that outlives its window is dropped rather than carried`() {
        val c = ConfirmTrancheController(holdMinutes = 10.0, expiryMinutes = 30.0)
        c.onConfirm(0L, 110.0, 2.0)
        assertThat(c.onCycle(40 * min, 250.0)).isEqualTo(0.0)
        assertThat(c.heldU()).isEqualTo(0.0)
    }

    @Test fun `total delivered never exceeds the sized dose`() {
        for (thr in listOf(0.0, 0.3, 0.48, 0.9)) {
            for (bgEnd in listOf(90.0, 140.0, 200.0, 300.0)) {
                val c = ConfirmTrancheController(releaseThreshold = thr)
                val now = c.onConfirm(0L, 120.0, 2.0)
                c.onCycle(5 * min, (120.0 + bgEnd) / 2)
                val later = c.onCycle(10 * min, bgEnd)
                assertThat(now + later).isAtMost(2.0 + 1e-9)
            }
        }
    }

    @Test fun `a fraction of one delivers everything immediately and holds nothing`() {
        val c = ConfirmTrancheController(immediateFraction = 1.0)
        assertThat(c.onConfirm(0L, 120.0, 2.0)).isWithin(1e-9).of(2.0)
        assertThat(c.heldU()).isEqualTo(0.0)
        assertThat(c.onCycle(10 * min, 200.0)).isEqualTo(0.0)
    }

    @Test fun `a fresh confirm replaces an older hold`() {
        val c = ConfirmTrancheController()
        c.onConfirm(0L, 120.0, 2.0)
        c.onConfirm(15 * min, 150.0, 3.0)
        assertThat(c.heldU()).isWithin(1e-9).of(1.5)
    }

    @Test fun `reset drops the hold`() {
        val c = ConfirmTrancheController()
        c.onConfirm(0L, 120.0, 2.0)
        c.reset()
        assertThat(c.heldU()).isEqualTo(0.0)
        assertThat(c.onCycle(10 * min, 200.0)).isEqualTo(0.0)
    }

    @Test fun `a cycle landing just short of the window still decides`() {
        // 2026-08-27: the confirm at 14:52:11.459 was followed by a cycle at 15:02:10.934, which is
        // 9.991 minutes. An exact comparison deferred the decision by a whole cycle.
        val c = ConfirmTrancheController(holdMinutes = 10.0, releaseThreshold = 0.48)
        c.onConfirm(0L, 180.0, 2.0)
        c.onCycle(5 * min, 181.0)
        val short = (9.991 * 60_000).toLong()
        assertThat(c.onCycle(short, 180.0)).isEqualTo(0.0)
        assertThat(c.heldU()).isEqualTo(0.0)   // decided at 9.991, not deferred to 15 min
    }

    @Test fun `a cycle far short of the window still defers`() {
        val c = ConfirmTrancheController(holdMinutes = 10.0)
        c.onConfirm(0L, 120.0, 2.0)
        assertThat(c.onCycle(6 * min, 160.0)).isEqualTo(0.0)
        assertThat(c.heldU()).isWithin(1e-9).of(1.0)   // still held
    }

    // ─── bounds at the seam (2026-10-08, audit #1) ───────────────────────────────

    private fun open(ceiling: Double = 10.0) = ConfirmTrancheController.ReleaseBounds(
        inMealState = true, hardGateFired = false, postRescueWindow = false, ceilingU = ceiling
    )

    /** A confirm at 110 followed by a rise the rule releases on (as in `a continuing rise releases the remainder`). */
    private fun armed(): ConfirmTrancheController {
        val c = ConfirmTrancheController(holdMinutes = 10.0, releaseThreshold = 0.48)
        c.onConfirm(0L, 110.0, 2.0)
        c.onCycleBounded(5 * min, 130.0, open())
        return c
    }

    @Test fun `bounded - a release the rule grants within every bound is delivered whole`() {
        val r = armed().onCycleBounded(10 * min, 160.0, open())
        assertThat(r.units).isWithin(1e-9).of(1.0)
        assertThat(r.note).isEmpty()
    }

    @Test fun `bounded - leaving the meal states drops the hold and releases nothing`() {
        // Field case: releases in RECOVERING, one of 1.675 U with V6's own dose 0 and eventualBG 65.
        val c = armed()
        val r = c.onCycleBounded(10 * min, 160.0, open().copy(inMealState = false))
        assertThat(r.units).isEqualTo(0.0)
        assertThat(r.note).startsWith("dropped:state")
        assertThat(c.heldU()).isEqualTo(0.0)
        assertThat(c.onCycleBounded(15 * min, 180.0, open()).units).isEqualTo(0.0)
    }

    @Test fun `bounded - a phase-3 hard gate drops the hold`() {
        val c = armed()
        assertThat(c.onCycleBounded(10 * min, 160.0, open().copy(hardGateFired = true)).units).isEqualTo(0.0)
        assertThat(c.heldU()).isEqualTo(0.0)
    }

    @Test fun `bounded - the post-rescue window drops the hold`() {
        val c = armed()
        assertThat(c.onCycleBounded(10 * min, 160.0, open().copy(postRescueWindow = true)).units).isEqualTo(0.0)
        assertThat(c.heldU()).isEqualTo(0.0)
    }

    @Test fun `bounded - the release is clamped to what is left of maxIOB and the confirm cap`() {
        val r = armed().onCycleBounded(10 * min, 160.0, open(ceiling = 0.4))
        assertThat(r.units).isWithin(1e-9).of(0.4)
        assertThat(r.note).isEqualTo("clamped:1.0->0.4")
    }

    @Test fun `ceiling - the tighter of maxIOB headroom and the confirm cap, never negative`() {
        val ceil = app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion::trancheReleaseCeiling
        // headroom 3.0 - 1.8 - 0.5 = 0.7 against cap 2.0 - 0.5 = 1.5
        assertThat(ceil(0.5, 3.0, 1.8, 2.0)).isWithin(1e-9).of(0.7)
        // headroom 6.0 - 0.0 - 0.5 = 5.5 against cap 1.0 - 0.5 = 0.5
        assertThat(ceil(0.5, 6.0, 0.0, 1.0)).isWithin(1e-9).of(0.5)
        // IOB already above maxIOB
        assertThat(ceil(0.5, 2.0, 2.2, 2.0)).isEqualTo(0.0)
    }

    @Test fun `over an episode the bounded path never delivers more than the confirm shot`() {
        val c = ConfirmTrancheController(holdMinutes = 10.0, releaseThreshold = 0.0)   // always release
        var total = c.onConfirm(0L, 110.0, 2.0)
        for (t in 1..8) total += c.onCycleBounded(t * 5 * min, 110.0 + 20 * t, open()).units
        assertThat(total).isAtMost(2.0 + 1e-9)
    }
}
