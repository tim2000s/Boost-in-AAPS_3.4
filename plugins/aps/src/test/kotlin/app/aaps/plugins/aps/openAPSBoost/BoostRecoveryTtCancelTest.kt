package app.aaps.plugins.aps.openAPSBoost

import app.aaps.core.data.model.TT
import app.aaps.plugins.aps.openAPSBoost.OpenAPSBoostPlugin.Companion.isBoostRecoveryTt
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.Test

/**
 * 2026-10-01. The hypo-rebound auto-cancel may remove only the post-exercise recovery target Boost
 * inserted. A user's own Activity target, set to sit out a rescue rebound, was cancelled within one
 * cycle because the check was the reason alone.
 */
class BoostRecoveryTtCancelTest {

    private val boostStart = 1_790_000_000_000L

    @Test fun `Boost's own recovery target is recognised`() {
        assertThat(isBoostRecoveryTt(boostStart, TT.Reason.ACTIVITY, boostStart)).isTrue()
    }

    @Test fun `a user's Activity target is never treated as Boost's`() {
        assertThat(isBoostRecoveryTt(boostStart + 60_000L, TT.Reason.ACTIVITY, boostStart)).isFalse()
        assertThat(isBoostRecoveryTt(boostStart, TT.Reason.ACTIVITY, null)).isFalse()
    }

    @Test fun `other reasons and no target are left alone`() {
        assertThat(isBoostRecoveryTt(boostStart, TT.Reason.CUSTOM, boostStart)).isFalse()
        assertThat(isBoostRecoveryTt(boostStart, TT.Reason.HYPOGLYCEMIA, boostStart)).isFalse()
        assertThat(isBoostRecoveryTt(null, null, boostStart)).isFalse()
    }
}
