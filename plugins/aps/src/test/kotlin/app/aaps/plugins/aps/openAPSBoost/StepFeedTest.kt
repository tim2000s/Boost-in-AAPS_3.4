package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * F1 (2026-07-07) — step-source availability guard.
 *
 * These exercise the exact predicates calculateBoostActivity now evaluates (extracted to StepFeed
 * so they're unit-testable): a NONE feed (phone never reported this boot, no fresh wear row) must
 * suppress the INACTIVE profile drop and the steps-based sleep-in backstop — 0 steps from a dead
 * feed is "unknown", not "sedentary" — while a LIVE feed with genuinely zero steps behaves exactly
 * as before.
 */
class StepFeedTest {

    private val FRESH = WearStepSource.FRESH_MS

    // ── Feed labels + availability (RT boostSteps_feed) ─────────────────────────────────────────

    @Test fun `both feeds live - phone+wear`() {
        val s = StepFeed.State(phoneLive = true, wearAgeMs = 3 * 60_000L)
        assertThat(s.available).isTrue()
        assertThat(s.label).isEqualTo("phone+wear")
    }

    @Test fun `phone only`() {
        val s = StepFeed.State(phoneLive = true, wearAgeMs = null)
        assertThat(s.available).isTrue()
        assertThat(s.label).isEqualTo("phone")
        // stale wear doesn't count towards the label either
        assertThat(StepFeed.State(true, FRESH + 60_000L).label).isEqualTo("phone")
    }

    @Test fun `wear only`() {
        val s = StepFeed.State(phoneLive = false, wearAgeMs = FRESH)   // exactly at the window edge = fresh
        assertThat(s.available).isTrue()
        assertThat(s.label).isEqualTo("wear")
    }

    @Test fun `no feed - none`() {
        val s = StepFeed.State(phoneLive = false, wearAgeMs = null)
        assertThat(s.available).isFalse()
        assertThat(s.label).isEqualTo("none")
        val stale = StepFeed.State(phoneLive = false, wearAgeMs = FRESH + 1)
        assertThat(stale.available).isFalse()
        assertThat(stale.label).isEqualTo("none")
    }

    @Test fun `unavailable breadcrumb names the failure per feed`() {
        assertThat(StepFeed.State(false, null).unavailableNote())
            .isEqualTo("steps:UNAVAILABLE(phone=none-this-boot, wear=none)")
        assertThat(StepFeed.State(false, 47 * 60_000L).unavailableNote())
            .isEqualTo("steps:UNAVAILABLE(phone=none-this-boot, wear=stale 47m)")
    }

    // ── INACTIVE branch guard ────────────────────────────────────────────────────────────────────

    @Test fun `NONE feed - INACTIVE never fires, even at zero steps`() {
        assertThat(StepFeed.inactivityEligible(stepsAvailable = false, currentProfileSwitch = 100, recentSteps60Min = 0, inactivitySteps = 200, sleepInActive = false, asleep = false, inNightWindow = false)).isFalse()
    }

    @Test fun `LIVE feed with zero steps - INACTIVE fires as today (real sedentary unchanged)`() {
        assertThat(StepFeed.inactivityEligible(stepsAvailable = true, currentProfileSwitch = 100, recentSteps60Min = 0, inactivitySteps = 200, sleepInActive = false, asleep = false, inNightWindow = false)).isTrue()
    }

    @Test fun `LIVE feed with steps above threshold or non-100 profile - not eligible`() {
        assertThat(StepFeed.inactivityEligible(true, 100, 250, 200, false, false, false)).isFalse()
        assertThat(StepFeed.inactivityEligible(true, 80, 0, 200, false, false, false)).isFalse()
    }

    // ── Sleep-in backstop guard ──────────────────────────────────────────────────────────────────

    private val nightEnd = 1_000_000_000L
    private val sleepInMs = 2 * 3_600_000L

    @Test fun `NONE feed - sleep-in gate never engages`() {
        assertThat(StepFeed.sleepInActive(stepsAvailable = false, nowMs = nightEnd + 60_000L, nightEndMs = nightEnd, sleepInMs = sleepInMs, recentSteps60Min = 0, sleepInSteps = 75)).isFalse()
    }

    @Test fun `LIVE feed - sleep-in fires inside the window below threshold, as today`() {
        assertThat(StepFeed.sleepInActive(true, nightEnd + 60_000L, nightEnd, sleepInMs, 10, 75)).isTrue()
        // steps at/above threshold → awake
        assertThat(StepFeed.sleepInActive(true, nightEnd + 60_000L, nightEnd, sleepInMs, 75, 75)).isFalse()
        // outside the window (before night end / after window close) → no gate
        assertThat(StepFeed.sleepInActive(true, nightEnd - 1, nightEnd, sleepInMs, 10, 75)).isFalse()
        assertThat(StepFeed.sleepInActive(true, nightEnd + sleepInMs, nightEnd, sleepInMs, 10, 75)).isFalse()
    }

    // ── Lie-in FAILSAFE decision (false-AWAKE gap) ───────────────────────────────────────────────

    @Test fun `sleep-in window inactive - failsafe never engages regardless of detector`() {
        assertThat(StepFeed.lieInFailsafeEngages(sleepInActive = false, nightModeEnabled = true, autoBySleepActive = false, detectorSleeping = false)).isFalse()
        assertThat(StepFeed.lieInFailsafeEngages(sleepInActive = false, nightModeEnabled = true, autoBySleepActive = true, detectorSleeping = true)).isFalse()
    }

    @Test fun `auto-by-sleep OFF - failsafe engages on low steps (clock-only night mode, unchanged)`() {
        assertThat(StepFeed.lieInFailsafeEngages(sleepInActive = true, nightModeEnabled = true, autoBySleepActive = false, detectorSleeping = false)).isTrue()
        // detector state is irrelevant when auto-by-sleep is off
        assertThat(StepFeed.lieInFailsafeEngages(sleepInActive = true, nightModeEnabled = true, autoBySleepActive = false, detectorSleeping = true)).isTrue()
    }

    @Test fun `auto-by-sleep ON and detector SLEEPING - failsafe stands down (detector drives)`() {
        assertThat(StepFeed.lieInFailsafeEngages(sleepInActive = true, nightModeEnabled = true, autoBySleepActive = true, detectorSleeping = true)).isFalse()
    }

    @Test fun `auto-by-sleep ON but detector AWAKE in the lie-in window - failsafe ENGAGES (false-AWAKE gap closed)`() {
        // The regression the fix targets: a dawn false-AWAKE with the user still in bed (low 60m steps)
        // previously left BOTH protections off. Steps are ground truth → the failsafe must re-engage.
        assertThat(StepFeed.lieInFailsafeEngages(sleepInActive = true, nightModeEnabled = true, autoBySleepActive = true, detectorSleeping = false)).isTrue()
    }

    // ── 2026-07-31: sleep-in and INACTIVE must be mutually exclusive ──────────────────────────
    // A sleeping user has near-zero steps by definition, so the step test passes every night. The
    // INACTIVE branch ADDS insulin (profile 130%), so without an explicit exclusion it runs the user
    // hot until morning. Reported live: INACTIVE-130% at BG 71 and falling, during sleep-in.

    @Test
    fun `inactivity is suppressed during the morning lie-in`() {
        assertThat(
            StepFeed.inactivityEligible(
                stepsAvailable = true, currentProfileSwitch = 100, recentSteps60Min = 0,
                inactivitySteps = 500, sleepInActive = true, asleep = false
            , inNightWindow = false)
        ).isFalse()
    }

    @Test
    fun `inactivity is suppressed while the detector reports sleep`() {
        // The core night, which the lie-in window cannot reach: it opens AT night end, so before
        // dawn sleepInActive is false by construction. The detector is what covers this.
        assertThat(
            StepFeed.inactivityEligible(
                stepsAvailable = true, currentProfileSwitch = 100, recentSteps60Min = 0,
                inactivitySteps = 500, sleepInActive = false, asleep = true
            , inNightWindow = false)
        ).isFalse()
    }

    @Test
    fun `inactivity still fires for a genuinely sedentary waking user`() {
        // The raise is intended behaviour when awake and sedentary; the fix must not remove it.
        assertThat(
            StepFeed.inactivityEligible(
                stepsAvailable = true, currentProfileSwitch = 100, recentSteps60Min = 40,
                inactivitySteps = 500, sleepInActive = false, asleep = false
            , inNightWindow = false)
        ).isTrue()
    }

    @Test
    fun `the 250 to 499 step band cannot leave both protections off`() {
        // sleepInSteps ships at 250 and inactivitySteps at 500, both read from the same blended
        // count, so in this band the lie-in stands down as awake-enough while INACTIVE fires as
        // sedentary-enough. The detector closes it.
        assertThat(
            StepFeed.inactivityEligible(
                stepsAvailable = true, currentProfileSwitch = 100, recentSteps60Min = 300,
                inactivitySteps = 500, sleepInActive = false, asleep = true
            , inNightWindow = false)
        ).isFalse()
    }

    @Test
    fun `failsafe engages when night mode is off even though the detector sleeps`() {
        // isInNightSleepPeriod() returns false on its FIRST line when night mode is disabled, so the
        // detector is never consulted. Deferring to it there disarmed both protections at once.
        assertThat(
            StepFeed.lieInFailsafeEngages(
                sleepInActive = true, nightModeEnabled = false,
                autoBySleepActive = true, detectorSleeping = true
            )
        ).isTrue()
    }

    @Test
    fun `failsafe still stands down when night mode is genuinely suppressing`() {
        assertThat(
            StepFeed.lieInFailsafeEngages(
                sleepInActive = true, nightModeEnabled = true,
                autoBySleepActive = true, detectorSleeping = true
            )
        ).isFalse()
    }

    @Test
    fun `inactivity is suppressed inside the configured night window`() {
        // The point of the 2026-07-31 clock guard: this holds whatever ApsBoostNightModeEnabled
        // says, and needs no HR, no steps and no sleep detector.
        assertThat(
            StepFeed.inactivityEligible(
                stepsAvailable = true, currentProfileSwitch = 100, recentSteps60Min = 0,
                inactivitySteps = 500, sleepInActive = false, asleep = false, inNightWindow = true
            )
        ).isFalse()
    }
}
