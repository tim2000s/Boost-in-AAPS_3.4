package app.aaps.core.keys

import app.aaps.core.keys.interfaces.IntNonPreferenceKey

@Suppress("SpellCheckingInspection")
enum class IntNonKey(
    override val key: String,
    override val defaultValue: Int,
    override val exportable: Boolean = true
) : IntNonPreferenceKey {

    ObjectivesManualEnacts("ObjectivesmanualEnacts", 0),
    RangeToDisplay("rangetodisplay", 6),

    // Boost V5/V6 auto-config persistence schema version (see BoostV5AutoConfigApply.
    // AUTO_CONFIG_SCHEMA_VERSION): bumped when the resolution semantics change so already-persisted
    // per-knob resolved flags can be re-audited (versioned re-migration). 0 = pre-versioning.
    BoostV5AutoConfigSchemaVersion("boost_v5_autoconfig_schema_version", 0),

    // Periodic re-derivation persistence schema. Bumped when stored re-derivation state written by
    // an EARLIER build must not be trusted by a later one. v2: rev 1 stamped the last-run clock and
    // returned from a dead code path without ever recording a baseline, which would have gated rev 2
    // out for a further 7 days on every existing install.
    BoostV5RedriveSchemaVersion("boost_v5_redrive_schema_version", 0),

    // Install-time history-gap backfill (2026-07-30, see BoostHistorySync). Attempt counter — capped
    // at BoostHistorySync.MAX_ATTEMPTS so a site that genuinely has no history is asked a bounded
    // number of times and then left alone. Reset to 0 once the gap closes.
    ApsBoostHistorySyncAttempts("boost_history_sync_attempts", 0),

    // Row counts sampled immediately BEFORE a backfill request, so the "filled" breadcrumb can report
    // what the backfill actually recovered (+treatments / +bg) rather than a bare absolute.
    ApsBoostHistorySyncPreBg("boost_history_sync_pre_bg", 0),
    ApsBoostHistorySyncPreTreatments("boost_history_sync_pre_treatments", 0)
}