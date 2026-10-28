package app.aaps.plugins.insulin

import app.aaps.core.interfaces.configuration.Config
import app.aaps.core.interfaces.profile.ProfileFunction
import app.aaps.core.interfaces.resources.ResourceHelper
import app.aaps.core.interfaces.ui.UiInteraction
import app.aaps.core.interfaces.utils.HardLimits
import app.aaps.shared.tests.TestBase
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mock

/**
 * The peak-time dose X must be the insulin delivered, whichever concentration carries it. 4 pump units
 * of U100 are 4 units of insulin and 4 pump units of U200 are 8, so X is 4 and 8. Until this was fixed
 * the two plugins gave 8 and 4.
 */
class InsulinLyumjevPDPluginTest : TestBase() {

    @Mock lateinit var rh: ResourceHelper
    @Mock lateinit var profileFunction: ProfileFunction
    @Mock lateinit var config: Config
    @Mock lateinit var hardLimits: HardLimits
    @Mock lateinit var uiInteraction: UiInteraction

    private lateinit var u100: InsulinLyumjevU100PDPlugin
    private lateinit var u200: InsulinLyumjevU200PDPlugin

    @BeforeEach
    fun setup() {
        u100 = InsulinLyumjevU100PDPlugin(rh, profileFunction, rxBus, aapsLogger, config, hardLimits, uiInteraction)
        u200 = InsulinLyumjevU200PDPlugin(rh, profileFunction, rxBus, aapsLogger, config, hardLimits, uiInteraction)
    }

    @Test
    fun `four pump units give the insulin they carry as the peak-time dose`() {
        assertThat(u100.effectiveDose(4.0)).isWithin(1e-12).of(4.0)
        assertThat(u200.effectiveDose(4.0)).isWithin(1e-12).of(8.0)
    }

    @Test
    fun `the same insulin gives the same peak-time dose on either concentration`() {
        // 5 units of insulin: 5 pump units of U100, 2.5 of U200.
        assertThat(u200.effectiveDose(2.5)).isWithin(1e-12).of(u100.effectiveDose(5.0))
    }
}
