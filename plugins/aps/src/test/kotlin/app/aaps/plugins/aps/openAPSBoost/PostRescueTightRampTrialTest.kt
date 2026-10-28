package app.aaps.plugins.aps.openAPSBoost

import app.aaps.plugins.aps.openAPSBoost.DetermineBasalBoost.Companion.TIGHT_RAMP_CAP
import app.aaps.plugins.aps.openAPSBoost.DetermineBasalBoost.Companion.postRescueReboundScale
import app.aaps.plugins.aps.openAPSBoost.DetermineBasalBoost.Companion.tightRampArm
import com.google.common.truth.Truth.assertThat
import kotlin.math.min
import org.junit.jupiter.api.Test

/**
 * 2026-08-03 post-rescue TIGHT-RAMP trial — arm assignment and the capped scale.
 * Pre-registration: backtesting/protocols/2026-08_postrescue_tight_ramp_PREREG.md
 *
 * The trial exists because the cohort evidence is UNPROVEN: the 2026-08-03 ramp study found
 * every candidate ramp's cluster-bootstrap CI over users overlaps zero, with only 2 of 8 users
 * showing favourable targeting. The safety property that makes a live trial acceptable is that
 * the treatment arm is a CAP — it can only lower the scale, so a treatment cycle never delivers
 * more insulin than the same cycle would today.
 */
class PostRescueTightRampTrialTest {

    private fun effective(bg: Double, tight: Boolean) =
        if (tight) min(postRescueReboundScale(bg), TIGHT_RAMP_CAP) else postRescueReboundScale(bg)

    // ── the safety property ────────────────────────────────────────────────────────────────
    @Test fun `treatment arm never scales above the shipped ramp`() {
        var bg = 40.0
        while (bg <= 400.0) {
            assertThat(effective(bg, true)).isAtMost(effective(bg, false))
            bg += 0.5
        }
    }

    @Test fun `treatment arm closes the 170 cliff`() {
        // shipped: guard does not apply at all at/above 170 (scale 1.0)
        assertThat(effective(180.0, false)).isEqualTo(1.0)
        assertThat(effective(250.0, false)).isEqualTo(1.0)
        // treatment: still capped
        assertThat(effective(180.0, true)).isEqualTo(TIGHT_RAMP_CAP)
        assertThat(effective(250.0, true)).isEqualTo(TIGHT_RAMP_CAP)
    }

    @Test fun `below the cap the two arms are identical`() {
        // 0.30 floor and the early ramp are already under 0.60
        assertThat(effective(70.0, true)).isEqualTo(effective(70.0, false))
        assertThat(effective(119.9, true)).isEqualTo(effective(119.9, false))
        assertThat(effective(140.0, true)).isEqualTo(effective(140.0, false))   // 0.44
    }

    @Test fun `the cap binds only above the crossover BG`() {
        // scale hits 0.60 at bg = 120 + 50*(0.60-0.30)/0.70 = 141.43
        assertThat(effective(141.0, true)).isWithin(1e-9).of(postRescueReboundScale(141.0))
        assertThat(effective(142.0, true)).isEqualTo(TIGHT_RAMP_CAP)
        // the live 2026-08-02 cycles: BG 143 was scaled 62% shipped, would be 60% on treatment
        assertThat(postRescueReboundScale(143.0)).isWithin(1e-3).of(0.622)
        assertThat(effective(143.0, true)).isEqualTo(0.60)
        // and BG 180, which the shipped guard did not touch at all
        assertThat(effective(180.0, true)).isEqualTo(0.60)
    }

    // ── arm assignment ─────────────────────────────────────────────────────────────────────
    @Test fun `no seed means no treatment`() {
        for (d in 0L..60L) assertThat(tightRampArm("", d)).isFalse()
    }

    @Test fun `assignment is deterministic for a seed`() {
        val seed = "3f1c9a20-0000-4000-8000-000000000001"
        for (d in 0L..400L) assertThat(tightRampArm(seed, d)).isEqualTo(tightRampArm(seed, d))
    }

    @Test fun `blocks of seven are balanced four then three`() {
        val seed = "balance-check-seed"
        for (block in 0L..40L) {
            val treated = (0L..6L).count { tightRampArm(seed, block * 7 + it) }
            assertThat(treated).isEqualTo(if (block % 2 == 0L) 4 else 3)
        }
    }

    @Test fun `arms stay near even over a fortnight`() {
        val seed = "fortnight-seed"
        for (start in 0L..30L step 14) {
            val treated = (0L..13L).count { tightRampArm(seed, start * 7 + it) }
            assertThat(treated).isIn(6..8)      // 14 days, balanced blocks
        }
    }

    @Test fun `arm is not confounded with weekday`() {
        // Over many blocks each weekday position must see both arms — the failure mode the
        // night-mode pre-registration calls out for odd or even calendar days.
        val seed = "weekday-seed"
        for (pos in 0L..6L) {
            val treated = (0L..99L).count { tightRampArm(seed, it * 7 + pos) }
            assertThat(treated).isGreaterThan(20)
            assertThat(treated).isLessThan(80)
        }
    }

    @Test fun `different seeds give different schedules`() {
        val a = (0L..69L).map { tightRampArm("seed-A", it) }
        val b = (0L..69L).map { tightRampArm("seed-B", it) }
        assertThat(a).isNotEqualTo(b)
    }
}
