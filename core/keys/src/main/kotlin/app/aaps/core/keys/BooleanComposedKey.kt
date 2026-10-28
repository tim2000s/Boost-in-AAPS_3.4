package app.aaps.core.keys

import app.aaps.core.keys.interfaces.BooleanComposedNonPreferenceKey

enum class BooleanComposedKey(
    override val key: String,
    override val format: String,
    override val defaultValue: Boolean,
    override val exportable: Boolean = true
) : BooleanComposedNonPreferenceKey {

    Log("log_", "%s", false),
    WidgetUseBlack("appwidget_use_black_", "%d", false),

    // Boost V5/V6 auto-config per-knob resolution: argument = the managed preference's key string.
    // True once that knob has been auto-configured OR skipped because the user had tuned it.
    // Replaces the legacy global BooleanKey.ApsBoostV5AutoConfigDone (see OpenAPSBoostV5Plugin).
    BoostV5AutoConfigResolved("boost_v5_autoconfig_resolved_", "%s", false),
}