package app.aaps.plugins.aps.openAPSBoost

import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-07-30 implausible-TDD guard for dynamic ISF.
 *
 * Field case: a cross-fork migration onto a fresh AAPS database reported TDD 3.1-4.1 U/day against a
 * true ~20. Dynamic ISF (1800/(tdd x logTerm)) reached 5550-8944 mg/dL/U against a profile ISF of 100,
 * insulinReq computed at or below zero, and the loop delivered nothing for 3.5 h while BG climbed to
 * 276 — 19 consecutive zero temp basals, no lows, no alarm. The pre-existing `tdd > 0` check passed
 * throughout, so the guard is anchored on the TDD the profile itself implies (1800 rule) instead.
 */
class DynIsfTddGuardTest {

    @Test fun `the field case is caught - profile ISF 100 implies TDD 18, reported 4`() {
        assertThat(tddImplausibleForProfile(tdd = 4.0, profileSens = 100.0)).isTrue()
        assertThat(tddImplausibleForProfile(tdd = 3.1, profileSens = 100.0)).isTrue()
    }

    @Test fun `a healthy TDD for the same profile passes`() {
        // implied 18.0, floor 6.3 — their true TDD was ~20, and it corrected to 20.2 in the field.
        assertThat(tddImplausibleForProfile(tdd = 20.2, profileSens = 100.0)).isFalse()
        assertThat(tddImplausibleForProfile(tdd = 6.4, profileSens = 100.0)).isFalse()
    }

    @Test fun `the floor is self-scaling - a U200 or low-TDD user is judged by their OWN profile`() {
        // Aggressive profile ISF 30 => implied 60 => floor 21.
        assertThat(tddImplausibleForProfile(tdd = 25.0, profileSens = 30.0)).isFalse()
        assertThat(tddImplausibleForProfile(tdd = 15.0, profileSens = 30.0)).isTrue()
        // Insensitive profile ISF 300 => implied 6 => floor 2.1. A genuinely small TDD is NOT flagged.
        assertThat(tddImplausibleForProfile(tdd = 4.0, profileSens = 300.0)).isFalse()
        // ...which is the case the old `tdd > 0` check could not distinguish from the field failure:
        // the SAME tdd of 4.0 is implausible on a 100 profile and perfectly normal on a 300 one.
    }

    @Test fun `fails OPEN with no usable profile reference`() {
        assertThat(tddImplausibleForProfile(tdd = 0.1, profileSens = 0.0)).isFalse()
        assertThat(tddImplausibleForProfile(tdd = 0.1, profileSens = -5.0)).isFalse()
    }

    @Test fun `boundary is exactly the implied fraction`() {
        // profileSens 100 => implied 18.0 => floor 6.3
        assertThat(tddImplausibleForProfile(tdd = 6.3, profileSens = 100.0)).isFalse()   // not below
        assertThat(tddImplausibleForProfile(tdd = 6.29, profileSens = 100.0)).isTrue()
    }
}
