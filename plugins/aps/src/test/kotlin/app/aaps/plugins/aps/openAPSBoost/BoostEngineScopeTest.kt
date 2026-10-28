package app.aaps.plugins.aps.openAPSBoost

import app.aaps.plugins.aps.openAPSBoostV5.OpenAPSBoostV5Plugin
import com.google.common.truth.Truth.assertThat
import javax.inject.Singleton
import org.junit.jupiter.api.Test

/**
 * Regression guard for the 2026-07-30 → 08-04 "loop computes but never enacts" defect.
 *
 * WHAT HAPPENED. `@Singleton` sat directly above `open class OpenAPSBoostPlugin`. Commit 5fc7951452
 * inserted a KDoc, a constant and a helper function BETWEEN them. Kotlin ignores comments when
 * attaching an annotation, so `@Singleton` silently moved onto the constant and the engine became
 * unscoped. It still compiled and every unit test still passed.
 *
 * WHY THAT BROKE DOSING. OpenAPSBoostV5Plugin is the selectable APS plugin; it runs the engine and
 * then exposes the engine's `lastAPSResult` back to LoopPlugin. It injected the engine as a
 * `Provider`, and `Provider.get()` on an UNSCOPED binding constructs a new instance every call. So
 * each cycle ran determine_basal on one engine instance and read `lastAPSResult` from a different,
 * freshly-constructed one — always null. LoopPlugin logged "NO APS SELECTED OR PROVIDED RESULT" and
 * returned without enacting. The result was computed correctly and thrown away, every cycle, for
 * five days, with no error anywhere in the log.
 *
 * The two things asserted here are the two independent reasons it can't recur:
 *  1. the engine is scoped, so all injectors share one instance;
 *  2. the V5 plugin holds it via dagger.Lazy, which caches at the injection point, so even an
 *     unscoped engine could not split invoke() from the getters.
 */
class BoostEngineScopeTest {

    @Test fun `the Boost engine is a singleton`() {
        // Guards against the annotation drifting off the class again. If this fails, check that
        // nothing has been inserted between @Singleton and `open class OpenAPSBoostPlugin`.
        assertThat(OpenAPSBoostPlugin::class.java.isAnnotationPresent(Singleton::class.java)).isTrue()
    }

    @Test fun `the V5 plugin holds the engine as a Lazy, not a Provider`() {
        // Belt and braces: Lazy caches per injection point, so invoke() and the lastAPSResult
        // getter resolve to the same engine even if scoping regresses.
        val engineParams = OpenAPSBoostV5Plugin::class.java.declaredConstructors
            .flatMap { it.parameterTypes.toList() }
        assertThat(engineParams).contains(dagger.Lazy::class.java)
    }

    @Test fun `other Boost APS plugins are scoped too`() {
        // The same mistake anywhere else in this family has the same consequence.
        assertThat(OpenAPSBoostV5Plugin::class.java.isAnnotationPresent(Singleton::class.java)).isTrue()
    }
}
