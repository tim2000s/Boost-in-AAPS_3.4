package app.aaps.plugins.main.general.overview.boost

import android.annotation.SuppressLint
import android.content.res.ColorStateList
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView

import androidx.recyclerview.widget.LinearLayoutManager
import app.aaps.core.data.model.GlucoseUnit
import app.aaps.core.data.model.RM
import app.aaps.core.data.model.TE
import app.aaps.core.data.pump.defs.PumpType
import app.aaps.core.data.ue.Action
import app.aaps.core.data.ue.Sources
import app.aaps.core.graph.data.DataPointWithLabelInterface
import app.aaps.core.graph.data.PointsWithLabelGraphSeries
import app.aaps.core.interfaces.aps.Loop
import app.aaps.core.interfaces.automation.Automation
import app.aaps.core.interfaces.configuration.Config
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.iob.GlucoseStatusProvider
import app.aaps.core.interfaces.iob.IobCobCalculator
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import app.aaps.core.interfaces.logging.UserEntryLogger
import app.aaps.core.interfaces.nsclient.NSSettingsStatus
import app.aaps.core.interfaces.nsclient.ProcessedDeviceStatusData
import app.aaps.core.interfaces.overview.LastBgData
import app.aaps.core.interfaces.overview.OverviewData
import app.aaps.core.interfaces.overview.OverviewMenus
import app.aaps.core.interfaces.plugin.ActivePlugin
import app.aaps.core.interfaces.profile.ProfileFunction
import app.aaps.core.interfaces.profile.ProfileUtil
import app.aaps.core.interfaces.protection.ProtectionCheck
import app.aaps.core.interfaces.pump.BolusProgressData
import app.aaps.core.interfaces.pump.WarnColors
import app.aaps.core.interfaces.queue.CommandQueue
import app.aaps.core.interfaces.resources.ResourceHelper
import app.aaps.core.interfaces.rx.AapsSchedulers
import app.aaps.core.interfaces.rx.bus.RxBus
import app.aaps.core.interfaces.rx.events.EventAcceptOpenLoopChange
import app.aaps.core.interfaces.rx.events.EventBucketedDataCreated
import app.aaps.core.interfaces.rx.events.EventEffectiveProfileSwitchChanged
import app.aaps.core.interfaces.rx.events.EventExtendedBolusChange
import app.aaps.core.interfaces.rx.events.EventInitializationChanged
import app.aaps.core.interfaces.rx.events.EventNewOpenLoopNotification
import app.aaps.core.interfaces.rx.events.EventPreferenceChange
import app.aaps.core.interfaces.rx.events.EventPumpStatusChanged
import app.aaps.core.interfaces.rx.events.EventRefreshOverview
import app.aaps.core.interfaces.rx.events.EventRunningModeChange
import app.aaps.core.interfaces.rx.events.EventScale
import app.aaps.core.interfaces.rx.events.EventTempBasalChange
import app.aaps.core.interfaces.rx.events.EventTempTargetChange
import app.aaps.core.interfaces.rx.events.EventTherapyEventChange
import app.aaps.core.interfaces.rx.events.EventWearUpdateTiles
import app.aaps.core.interfaces.rx.events.EventUpdateOverviewCalcProgress
import app.aaps.core.interfaces.rx.events.EventUpdateOverviewGraph
import app.aaps.core.interfaces.rx.events.EventUpdateOverviewIobCob
import app.aaps.core.interfaces.rx.events.EventUpdateOverviewSensitivity
import app.aaps.core.interfaces.source.DexcomBoyda
import app.aaps.core.interfaces.source.XDripSource
import app.aaps.core.interfaces.ui.UiInteraction
import app.aaps.core.interfaces.utils.DateUtil
import app.aaps.core.interfaces.utils.DecimalFormatter
import app.aaps.core.interfaces.utils.TrendCalculator
import app.aaps.core.interfaces.utils.fabric.FabricPrivacy
import app.aaps.core.keys.BooleanKey
import app.aaps.core.keys.IntKey
import app.aaps.core.keys.IntNonKey
import app.aaps.core.keys.UnitDoubleKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.core.objects.extensions.round
import app.aaps.core.objects.profile.ProfileSealed
import app.aaps.core.objects.wizard.QuickWizard
import app.aaps.core.ui.UIRunnable
import app.aaps.core.ui.dialogs.OKDialog
import app.aaps.core.ui.extensions.runOnUiThread
import app.aaps.core.ui.extensions.toVisibility
import app.aaps.plugins.main.R
import app.aaps.plugins.main.databinding.BoostOverviewV2FragmentBinding
import app.aaps.plugins.main.general.overview.notifications.NotificationStore
import app.aaps.plugins.main.general.overview.notifications.events.EventUpdateOverviewNotification
import dagger.android.support.DaggerFragment
import io.reactivex.rxjava3.disposables.CompositeDisposable
import io.reactivex.rxjava3.kotlin.plusAssign
import java.util.Locale
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Provider

/**
 * BoostOverviewV2Fragment — Alternative dark-theme home screen for Boost.
 *
 * Modern card-based layout with stat pills, integrated time range selector,
 * and streamlined bottom action buttons. Uses the same data sources and
 * helpers as BoostOverviewFragment.
 */
class BoostOverviewV2Fragment : DaggerFragment(), View.OnClickListener {

    // --- Injection (same dependencies as BoostOverviewFragment) ---

    @Inject lateinit var aapsLogger: AAPSLogger
    @Inject lateinit var aapsSchedulers: AapsSchedulers
    @Inject lateinit var preferences: Preferences
    @Inject lateinit var rxBus: RxBus
    @Inject lateinit var rh: ResourceHelper
    @Inject lateinit var profileFunction: ProfileFunction
    @Inject lateinit var profileUtil: ProfileUtil
    @Inject lateinit var loop: Loop
    @Inject lateinit var activePlugin: ActivePlugin
    @Inject lateinit var iobCobCalculator: IobCobCalculator
    @Inject lateinit var notificationStore: NotificationStore
    @Inject lateinit var quickWizard: QuickWizard
    @Inject lateinit var config: Config
    @Inject lateinit var protectionCheck: ProtectionCheck
    @Inject lateinit var fabricPrivacy: FabricPrivacy
    @Inject lateinit var overviewMenus: OverviewMenus
    @Inject lateinit var trendCalculator: TrendCalculator
    @Inject lateinit var dateUtil: DateUtil
    @Inject lateinit var persistenceLayer: PersistenceLayer
    @Inject lateinit var glucoseStatusProvider: GlucoseStatusProvider
    @Inject lateinit var overviewData: OverviewData
    @Inject lateinit var lastBgData: LastBgData
    @Inject lateinit var automation: Automation
    @Inject lateinit var uiInteraction: UiInteraction
    @Inject lateinit var decimalFormatter: DecimalFormatter
    @Inject lateinit var graphDataProvider: Provider<BoostV2GraphData>
    @Inject lateinit var boostHelper: BoostOverviewHelper
    @Inject lateinit var commandQueue: CommandQueue
    @Inject lateinit var dexcomBoyda: DexcomBoyda
    @Inject lateinit var xDripSource: XDripSource
    @Inject lateinit var uel: UserEntryLogger
    @Inject lateinit var warnColors: WarnColors
    @Inject lateinit var processedDeviceStatusData: ProcessedDeviceStatusData
    @Inject lateinit var nsSettingsStatus: NSSettingsStatus

    // --- State ---

    private val disposable = CompositeDisposable()
    private var handler = Handler(HandlerThread("BoostOverviewV2Handler").also { it.start() }.looper)
    private lateinit var refreshLoop: Runnable
    private var _binding: BoostOverviewV2FragmentBinding? = null
    private val binding get() = _binding!!

    private var axisWidth: Int = 0
    private var lastUserAction = ""

    @Volatile private var lastBoostStatus: BoostOverviewHelper.BoostStatus = BoostOverviewHelper.BoostStatus()

    private var scheduledGuiUpdate: Runnable? = null

    // Time range button references for highlight management
    private val rangeButtons: List<Pair<Int, Int>> by lazy {
        listOf(3 to R.id.v2_range_3h, 6 to R.id.v2_range_6h, 12 to R.id.v2_range_12h, 24 to R.id.v2_range_24h)
    }

    // --- Lifecycle ---

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View =
        BoostOverviewV2FragmentBinding.inflate(inflater, container, false).also { _binding = it }.root

    @SuppressLint("SetTextI18n")
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        // Resolve theme colours for BgBobbleView
        binding.v2BgBobble.resolveThemeColors(rh)

        // Graph axis width
        axisWidth = when {
            resources.displayMetrics.densityDpi <= 120 -> 3
            resources.displayMetrics.densityDpi <= 160 -> 10
            resources.displayMetrics.densityDpi <= 320 -> 35
            resources.displayMetrics.densityDpi <= 420 -> 50
            resources.displayMetrics.densityDpi <= 560 -> 70
            else                                       -> 80
        }

        // Graph styling — dark theme colours
        val gridColor = Color.parseColor("#1a1d28")
        binding.v2BgGraph.gridLabelRenderer?.gridColor = gridColor
        binding.v2BgGraph.gridLabelRenderer?.reloadStyles()
        binding.v2BgGraph.gridLabelRenderer?.textSize = 11f * resources.displayMetrics.scaledDensity
        binding.v2BgGraph.gridLabelRenderer?.labelVerticalWidth = axisWidth
        binding.v2BgGraph.gridLabelRenderer?.horizontalLabelsColor = Color.parseColor("#aaaaaa")
        binding.v2BgGraph.gridLabelRenderer?.verticalLabelsColor = Color.parseColor("#aaaaaa")

        binding.v2IobGraph.gridLabelRenderer?.gridColor = gridColor
        binding.v2IobGraph.gridLabelRenderer?.reloadStyles()
        binding.v2IobGraph.gridLabelRenderer?.textSize = 11f * resources.displayMetrics.scaledDensity
        binding.v2IobGraph.gridLabelRenderer?.isHorizontalLabelsVisible = false
        binding.v2IobGraph.gridLabelRenderer?.labelVerticalWidth = axisWidth
        binding.v2IobGraph.gridLabelRenderer?.numVerticalLabels = 3
        binding.v2IobGraph.gridLabelRenderer?.verticalLabelsColor = Color.parseColor("#aaaaaa")

        // Activity graph (steps + heart rate) — same chrome as the IOB graph
        binding.v2SensitivityGraph.gridLabelRenderer?.gridColor = gridColor
        binding.v2SensitivityGraph.gridLabelRenderer?.reloadStyles()
        binding.v2SensitivityGraph.gridLabelRenderer?.textSize = 11f * resources.displayMetrics.scaledDensity
        binding.v2SensitivityGraph.gridLabelRenderer?.isHorizontalLabelsVisible = false
        binding.v2SensitivityGraph.gridLabelRenderer?.labelVerticalWidth = axisWidth
        binding.v2SensitivityGraph.gridLabelRenderer?.numVerticalLabels = 3
        binding.v2SensitivityGraph.gridLabelRenderer?.verticalLabelsColor = Color.parseColor("#aaaaaa")

        binding.v2Notifications.setHasFixedSize(false)
        binding.v2Notifications.layoutManager = LinearLayoutManager(view.context)

        // Chart menu (scale button hidden — V2 uses inline time range buttons instead)
        overviewMenus.setupChartMenu(binding.v2ChartMenuButton, binding.v2ScaleButton)

        // Time range buttons
        binding.v2Range3h.setOnClickListener { setRange(3) }
        binding.v2Range6h.setOnClickListener { setRange(6) }
        binding.v2Range12h.setOnClickListener { setRange(12) }
        binding.v2Range24h.setOnClickListener { setRange(24) }

        // Long-press BG graph to cycle range
        binding.v2BgGraph.setOnLongClickListener {
            overviewData.rangeToDisplay += 6
            overviewData.rangeToDisplay = if (overviewData.rangeToDisplay > 24) 6 else overviewData.rangeToDisplay
            preferences.put(IntNonKey.RangeToDisplay, overviewData.rangeToDisplay)
            rxBus.send(EventPreferenceChange(IntNonKey.RangeToDisplay.key))
            updateRangeButtons()
            false
        }

        // Tap BG graph to open Treatments
        binding.v2BgGraph.setOnClickListener {
            context?.let { ctx ->
                startActivity(android.content.Intent(ctx, uiInteraction.treatmentsActivity))
            }
        }

        // Stat pill click listeners
        binding.v2PillIob.setOnClickListener(this)
        binding.v2PillDynisf.setOnClickListener(this)
        binding.v2PillTdd.setOnClickListener(this)
        binding.v2PillProfile.setOnClickListener(this)
        binding.v2V5Strip.setOnClickListener(this)

        // Bottom action buttons (pref-toggled, same keys as the standard overview)
        binding.v2BtnInsulin.setOnClickListener(this)
        binding.v2BtnCalculator.setOnClickListener(this)
        binding.v2BtnCarbs.setOnClickListener(this)
        binding.v2BtnTreatment.setOnClickListener(this)
        binding.v2BtnCalibration.setOnClickListener(this)
        binding.v2BtnCgm.setOnClickListener(this)
        arrangeActionButtons()

        // Target value tap -> temp target dialog
        binding.v2TargetValue.setOnClickListener(this)

        // Exercise label tap -> activity details
        binding.v2ExerciseLabel.setOnClickListener(this)

        // Pump status bar tap
        binding.v2PumpStatusLayout.setOnClickListener(this)

        // AID status tap -> loop dialog
        binding.v2AidStatus.setOnClickListener(this)
        binding.v2AidDot.setOnClickListener(this)

        // Hidden standard buttons layout — wire up for compatibility
        binding.v2ButtonsLayout.acceptTempButton.setOnClickListener(this)
        binding.v2ButtonsLayout.quickWizardButton.setOnClickListener(this)

        updateRangeButtons()
    }

    override fun onResume() {
        super.onResume()

        // Progress bar
        disposable += activePlugin.activeOverview.overviewBus
            .toObservable(EventUpdateOverviewCalcProgress::class.java)
            .observeOn(aapsSchedulers.main)
            .subscribe({ updateCalcProgress() }, fabricPrivacy::logException)

        // Granular event-driven updates
        disposable += activePlugin.activeOverview.overviewBus
            .toObservable(EventUpdateOverviewIobCob::class.java)
            .debounce(1L, TimeUnit.SECONDS)
            .observeOn(aapsSchedulers.io)
            .subscribe({ updateIobAndBoost() }, fabricPrivacy::logException)
        disposable += activePlugin.activeOverview.overviewBus
            .toObservable(EventUpdateOverviewGraph::class.java)
            .debounce(1L, TimeUnit.SECONDS)
            .observeOn(aapsSchedulers.main)
            .subscribe({ updateGraph() }, fabricPrivacy::logException)
        if (config.AAPSCLIENT) {
            // In AAPSClient a new Nightscout device status ends in EventUpdateOverviewGraph
            // (NSDeviceStatusHandler -> runOnReceivedPredictions -> UpdateGraphWorker); it is the
            // only signal that the main phone's pump and uploader battery have changed.
            disposable += activePlugin.activeOverview.overviewBus
                .toObservable(EventUpdateOverviewGraph::class.java)
                .debounce(1L, TimeUnit.SECONDS)
                .observeOn(aapsSchedulers.io)
                .subscribe({ updatePumpInfo() }, fabricPrivacy::logException)
        }
        disposable += activePlugin.activeOverview.overviewBus
            .toObservable(EventUpdateOverviewNotification::class.java)
            .observeOn(aapsSchedulers.main)
            .subscribe({ updateNotification() }, fabricPrivacy::logException)
        disposable += rxBus
            .toObservable(EventBucketedDataCreated::class.java)
            .debounce(1L, TimeUnit.SECONDS)
            .observeOn(aapsSchedulers.io)
            .subscribe({
                boostHelper.invalidate()
                updateBg()
            }, fabricPrivacy::logException)

        // Full refresh events
        disposable += rxBus
            .toObservable(EventRefreshOverview::class.java)
            .observeOn(aapsSchedulers.io)
            .subscribe({
                boostHelper.invalidate()
                if (it.now) refreshAll() else scheduleUpdateGUI()
            }, fabricPrivacy::logException)
        disposable += rxBus
            .toObservable(EventEffectiveProfileSwitchChanged::class.java)
            .observeOn(aapsSchedulers.io)
            .subscribe({ scheduleUpdateGUI() }, fabricPrivacy::logException)
        disposable += rxBus
            .toObservable(EventPumpStatusChanged::class.java)
            .observeOn(aapsSchedulers.main)
            .delay(30, TimeUnit.MILLISECONDS, aapsSchedulers.main)
            .subscribe({
                context?.let { ctx -> overviewData.pumpStatus = it.getStatus(ctx) }
                updatePumpStatus()
            }, fabricPrivacy::logException)
        // The driver updates its battery and reservoir as it reads the pump; refresh the pump column
        // once the status burst settles rather than waiting for the 60 s loop.
        disposable += rxBus
            .toObservable(EventPumpStatusChanged::class.java)
            .debounce(1L, TimeUnit.SECONDS)
            .observeOn(aapsSchedulers.io)
            .subscribe({ updatePumpInfo() }, fabricPrivacy::logException)
        // A logged battery, cannula or sensor change moves the ages shown in the pump column.
        disposable += rxBus
            .toObservable(EventTherapyEventChange::class.java)
            .debounce(1L, TimeUnit.SECONDS)
            .observeOn(aapsSchedulers.io)
            .subscribe({
                boostHelper.invalidate()
                updatePumpInfo()
            }, fabricPrivacy::logException)
        disposable += rxBus
            .toObservable(EventNewOpenLoopNotification::class.java)
            .observeOn(aapsSchedulers.io)
            .subscribe({ scheduleUpdateGUI() }, fabricPrivacy::logException)
        disposable += rxBus
            .toObservable(EventAcceptOpenLoopChange::class.java)
            .observeOn(aapsSchedulers.io)
            .subscribe({ scheduleUpdateGUI() }, fabricPrivacy::logException)
        disposable += rxBus
            .toObservable(EventTempTargetChange::class.java)
            .observeOn(aapsSchedulers.io)
            .subscribe({ updateHeroRight() }, fabricPrivacy::logException)
        disposable += rxBus
            .toObservable(EventRunningModeChange::class.java)
            .observeOn(aapsSchedulers.io)
            .subscribe({
                updateAidStatus()
                runOnUiThread { processButtonsVisibility() }
            }, fabricPrivacy::logException)
        disposable += rxBus
            .toObservable(EventInitializationChanged::class.java)
            .observeOn(aapsSchedulers.main)
            .subscribe({ processButtonsVisibility() }, fabricPrivacy::logException)
        disposable += rxBus
            .toObservable(EventPreferenceChange::class.java)
            .observeOn(aapsSchedulers.io)
            .subscribe({
                // A RangeToDisplay (hours) change already drives a full recompute + graph repaint via
                // the calculation workflow (IobCobCalculator → runOnScaleChanged/EventNewHistoryData →
                // EventUpdateOverviewGraph → updateGraph). Running our own refreshAll on top repaints
                // all three graphs on the main thread 1–2 extra times per tap — the slow-load/jank on a
                // range change. Skip it for that key; every other pref change still refreshes.
                if (!it.isChanged(IntNonKey.RangeToDisplay.key)) scheduleUpdateGUI()
            }, fabricPrivacy::logException)
        disposable += rxBus
            .toObservable(EventScale::class.java)
            .observeOn(aapsSchedulers.main)
            .subscribe({
                overviewData.rangeToDisplay = it.hours
                preferences.put(IntNonKey.RangeToDisplay, it.hours)
                rxBus.send(EventPreferenceChange(IntNonKey.RangeToDisplay.key))
                updateRangeButtons()
            }, fabricPrivacy::logException)
        disposable += rxBus
            .toObservable(EventTempBasalChange::class.java)
            .observeOn(aapsSchedulers.io)
            .subscribe({ scheduleUpdateGUI() }, fabricPrivacy::logException)
        disposable += rxBus
            .toObservable(EventExtendedBolusChange::class.java)
            .observeOn(aapsSchedulers.io)
            .subscribe({ scheduleUpdateGUI() }, fabricPrivacy::logException)
        disposable += activePlugin.activeOverview.overviewBus
            .toObservable(EventUpdateOverviewSensitivity::class.java)
            .debounce(1L, TimeUnit.SECONDS)
            .observeOn(aapsSchedulers.io)
            .subscribe({ scheduleUpdateGUI() }, fabricPrivacy::logException)

        refreshLoop = Runnable { refreshAll(); handler.postDelayed(refreshLoop, 60_000L) }
        handler.postDelayed(refreshLoop, 60_000L)
        handler.post { refreshAll() }
        updatePumpStatus()
        updateCalcProgress()
        popupBolusDialogIfRunning(onClick = false)
    }

    override fun onPause() {
        super.onPause()
        disposable.clear()
        scheduledGuiUpdate?.let { handler.removeCallbacks(it) }
        scheduledGuiUpdate = null
        handler.removeCallbacksAndMessages(null)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding?.v2BgGraph?.let { graph ->
            graph.setOnLongClickListener(null)
            graph.setOnClickListener(null)
            detachAllSeries(graph)
        }
        _binding?.v2IobGraph?.let { graph ->
            detachAllSeries(graph)
        }
        _binding = null
    }

    private fun detachAllSeries(graph: com.jjoe64.graphview.GraphView) {
        graph.removeAllSeries()
        val allSeries = listOf(
            overviewData.bucketedGraphSeries, overviewData.bgReadingGraphSeries,
            overviewData.predictionsGraphSeries, overviewData.baseBasalGraphSeries,
            overviewData.tempBasalGraphSeries, overviewData.basalLineGraphSeries,
            overviewData.absoluteBasalGraphSeries, overviewData.temporaryTargetSeries,
            overviewData.runningModesSeries, overviewData.activitySeries,
            overviewData.activityPredictionSeries, overviewData.epsSeries,
            overviewData.treatmentsSeries, overviewData.therapyEventSeries,
            overviewData.iobSeries, overviewData.absIobSeries,
            overviewData.iobPredictions1Series, overviewData.minusBgiSeries,
            overviewData.minusBgiHistSeries, overviewData.cobSeries,
            overviewData.cobMinFailOverSeries, overviewData.deviationsSeries,
            overviewData.ratioSeries, overviewData.varSensSeries,
            overviewData.dsMaxSeries, overviewData.dsMinSeries,
            overviewData.heartRateGraphSeries, overviewData.stepsCountGraphSeries
        )
        for (s in allSeries) {
            (s as? com.jjoe64.graphview.series.Series<*>)?.onGraphViewDetached(graph)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacksAndMessages(null)
        handler.looper.quitSafely()
    }

    // --- Coalesced GUI update ---

    private fun scheduleUpdateGUI() {
        class UpdateRunnable : Runnable {
            override fun run() {
                refreshAll()
                scheduledGuiUpdate = null
            }
        }
        scheduledGuiUpdate?.let { handler.removeCallbacks(it) }
        scheduledGuiUpdate = UpdateRunnable()
        scheduledGuiUpdate?.let { handler.postDelayed(it, 500) }
    }

    // --- Progress bar ---

    private fun updateCalcProgress() {
        _binding ?: return
        binding.v2ProgressBar.visibility = (overviewData.calcProgressPct != 100).toVisibility()
        binding.v2ProgressBar.progress = overviewData.calcProgressPct
    }

    // --- Time range buttons ---

    private fun setRange(hours: Int) {
        overviewData.rangeToDisplay = hours
        preferences.put(IntNonKey.RangeToDisplay, hours)
        rxBus.send(EventPreferenceChange(IntNonKey.RangeToDisplay.key))
        updateRangeButtons()
    }

    private fun updateRangeButtons() {
        runOnUiThread {
            _binding ?: return@runOnUiThread
            val current = overviewData.rangeToDisplay
            val accentColor = Color.parseColor("#00d4ff")
            val dimColor = Color.parseColor("#aaaaaa")
            val activeBg = Color.parseColor("#1a00d4ff")
            val inactiveBg = Color.TRANSPARENT

            for ((hours, _) in rangeButtons) {
                val tv: TextView = when (hours) {
                    3 -> binding.v2Range3h
                    6 -> binding.v2Range6h
                    12 -> binding.v2Range12h
                    24 -> binding.v2Range24h
                    else -> continue
                }
                if (hours == current) {
                    tv.setTextColor(accentColor)
                    tv.setBackgroundColor(activeBg)
                } else {
                    tv.setTextColor(dimColor)
                    tv.setBackgroundColor(inactiveBg)
                }
            }
        }
    }

    // --- Refresh ---

    private fun refreshAll() {
        if (!config.appInitialized || !isAdded) return
        val cachedStatus = boostHelper.getBoostStatus()
        lastBoostStatus = cachedStatus
        updateBg()
        updateIobAndBoost(cachedStatus)
        updatePumpInfo(cachedStatus)
        updateHeroRight(cachedStatus)
        updateProfile()
        runOnUiThread {
            _binding ?: return@runOnUiThread
            processButtonsVisibility()
            updateGraph()
            updateNotification()
            updateRangeButtons()
            updateAidStatus()
        }
    }

    // --- BG Bobble ---

    @SuppressLint("SetTextI18n")
    private fun updateBg() {
        if (!isAdded) return
        val lastBg = lastBgData.lastBg()
        val isActual = lastBgData.isActualBg()
        val glucoseStatus = glucoseStatusProvider.glucoseStatusData
        val trendArrow = trendCalculator.getTrendArrow(iobCobCalculator.ads)
        val trendDesc = trendCalculator.getTrendDescription(iobCobCalculator.ads)
        val (trendAngle, chevronRot) = BgBobbleView.trendToAngles(trendArrow)

        runOnUiThread {
            _binding ?: return@runOnUiThread
            binding.v2BgBobble.bgValueMgdl = lastBg?.recalculated ?: 0.0
            binding.v2BgBobble.bgDisplayText = profileUtil.fromMgdlToStringInUnits(lastBg?.recalculated)
            binding.v2BgBobble.unitsLabel = if (profileFunction.getUnits() == GlucoseUnit.MGDL) "mg/dL" else "mmol/L"
            binding.v2BgBobble.isActualBg = isActual
            binding.v2BgBobble.trendAngleDeg = trendAngle
            binding.v2BgBobble.chevronRotateDeg = chevronRot

            if (glucoseStatus != null) {
                binding.v2DeltaText.text = "${profileUtil.fromMgdlToSignedStringInUnits(glucoseStatus.delta)} \u00B7 ${trendDesc ?: ""}"
            } else {
                binding.v2DeltaText.text = ""
            }

            binding.v2TimeAgo.text = dateUtil.minOrSecAgo(rh, lastBg?.timestamp)

            // TalkBack
            val bgStr = profileUtil.fromMgdlToStringInUnits(lastBg?.recalculated)
            val unitsStr = binding.v2BgBobble.unitsLabel
            val trendStr = trendDesc ?: ""
            val ageStr = binding.v2TimeAgo.text
            binding.v2BgBobble.contentDescription = "Blood glucose $bgStr $unitsStr, $trendStr, $ageStr"
        }
    }

    // --- AID Status (top-right indicator) ---

    private fun updateAidStatus() {
        runOnUiThread {
            _binding ?: return@runOnUiThread
            val pump = activePlugin.activePump
            if (!pump.pumpDescription.isTempBasalCapable) {
                binding.v2AidStatus.text = "NO AID"
                binding.v2AidDot.setBackgroundColor(Color.parseColor("#ff5252"))
                return@runOnUiThread
            }
            when (loop.runningMode) {
                RM.Mode.CLOSED_LOOP, RM.Mode.CLOSED_LOOP_LGS -> {
                    binding.v2AidStatus.text = "AID ON"
                    binding.v2AidDot.setBackgroundColor(Color.parseColor("#4caf50"))
                }
                RM.Mode.OPEN_LOOP -> {
                    binding.v2AidStatus.text = "OPEN"
                    binding.v2AidDot.setBackgroundColor(Color.parseColor("#ffb300"))
                }
                RM.Mode.SUSPENDED_BY_USER, RM.Mode.SUSPENDED_BY_PUMP, RM.Mode.SUSPENDED_BY_DST -> {
                    binding.v2AidStatus.text = "PAUSED"
                    binding.v2AidDot.setBackgroundColor(Color.parseColor("#ff5252"))
                }
                RM.Mode.DISCONNECTED_PUMP -> {
                    binding.v2AidStatus.text = "DISC"
                    binding.v2AidDot.setBackgroundColor(Color.parseColor("#ff5252"))
                }
                RM.Mode.DISABLED_LOOP -> {
                    binding.v2AidStatus.text = "OFF"
                    binding.v2AidDot.setBackgroundColor(Color.parseColor("#9aa0ad"))
                }
                RM.Mode.SUPER_BOLUS -> {
                    binding.v2AidStatus.text = "S.BOLUS"
                    binding.v2AidDot.setBackgroundColor(Color.parseColor("#ffb300"))
                }
                else -> {
                    binding.v2AidStatus.text = "AID ON"
                    binding.v2AidDot.setBackgroundColor(Color.parseColor("#4caf50"))
                }
            }
        }
    }

    // --- IOB + Boost stat pills ---

    @SuppressLint("SetTextI18n")
    private fun updateIobAndBoost(cached: BoostOverviewHelper.BoostStatus? = null) {
        if (!isAdded) return
        val bolusIob = iobCobCalculator.calculateIobFromBolus().round()
        val basalIob = iobCobCalculator.calculateIobFromTempBasalsIncludingConvertedExtended().round()
        val totalIob = bolusIob.iob + basalIob.basaliob
        val boostStatus = cached ?: boostHelper.getBoostStatus()
        lastBoostStatus = boostStatus

        runOnUiThread {
            _binding ?: return@runOnUiThread
            // IOB pill
            binding.v2PillIobValue.text = String.format(Locale.getDefault(), "%.2fu", totalIob)

            // DynISF pill
            val dynRaw = boostStatus.dynIsfValue
            val dynDisp = if (dynRaw > 0) {
                val converted = profileUtil.fromMgdlToUnits(dynRaw)
                if (profileFunction.getUnits() == GlucoseUnit.MGDL) String.format(Locale.getDefault(), "%.0f", converted)
                else String.format(Locale.getDefault(), "%.1f", converted)
            } else "---"
            binding.v2PillDynisfValue.text = dynDisp

            // TDD pill
            val tddDisplay = when {
                boostStatus.tddWeighted > 0  -> boostStatus.tddWeighted
                boostStatus.tddFromDebug > 0 -> boostStatus.tddFromDebug
                else                          -> boostStatus.tdd7d
            }
            binding.v2PillTddValue.text = if (tddDisplay > 0) String.format(Locale.getDefault(), "%.1fu", tddDisplay) else "---"

            // Profile pill — active profile name + percent only (meal-management state lives
            // in the V5 strip below). Tap opens the profile-switch dialog.
            binding.v2PillProfileTier.text = profileFunction.getOriginalProfileName()
            binding.v2PillProfileTier.setTextColor(Color.parseColor("#00d4ff"))
            binding.v2PillProfilePct.text = "${boostStatus.profilePercentage}%"

            // V5 state strip (active-only)
            updateV5Strip(boostStatus)

            // TalkBack
            binding.v2PillIob.contentDescription = "Insulin on board: ${String.format(Locale.getDefault(), "%.2f", totalIob)} units"
            val unitsStr = if (profileFunction.getUnits() == GlucoseUnit.MGDL) "mg/dL per unit" else "mmol/L per unit"
            binding.v2PillDynisf.contentDescription = "Dynamic ISF: $dynDisp $unitsStr"
            binding.v2PillTdd.contentDescription = "Total daily dose: ${if (tddDisplay > 0) String.format(Locale.getDefault(), "%.1f units", tddDisplay) else "unavailable"}"
            binding.v2PillProfile.contentDescription =
                "Profile ${profileFunction.getOriginalProfileName()}, ${boostStatus.profilePercentage} percent. Tap to change profile."
        }
    }

    // --- Boost V5 state strip (active-only) ---

    @SuppressLint("SetTextI18n")
    private fun updateV5Strip(bs: BoostOverviewHelper.BoostStatus) {
        _binding ?: return
        if (!bs.isV5Active) {
            binding.v2V5Strip.visibility = View.GONE
            return
        }
        binding.v2V5Strip.visibility = View.VISIBLE
        val color = bs.v5State.colorHex.toInt()

        // Row 1: state · action multiplier · age, then dose / budget
        binding.v2V5State.text = "${bs.v5State.label.uppercase(Locale.getDefault())}  ×${String.format(Locale.getDefault(), "%.1f", bs.v5ActionMult)} · ${bs.v5Age}c"
        binding.v2V5State.setTextColor(color)
        binding.v2V5Dose.text = "dose ${String.format(Locale.getDefault(), "%.2f", bs.v5FinalDose)}U · budget ${String.format(Locale.getDefault(), "%.2f", bs.v5Budget)}U"

        // Row 2: meal-score gauge (0..1 → 0..100), tinted by state colour
        binding.v2V5ScoreBar.progress = (bs.v5Score * 100).toInt().coerceIn(0, 100)
        binding.v2V5ScoreBar.progressTintList = ColorStateList.valueOf(color)
        binding.v2V5ScoreText.text = String.format(Locale.getDefault(), "%.2f", bs.v5Score)

        // Row 3: active brakes — red if any hard gate fired, else amber; hidden when none
        if (bs.v5Brakes.isEmpty()) {
            binding.v2V5Brakes.visibility = View.GONE
        } else {
            binding.v2V5Brakes.visibility = View.VISIBLE
            binding.v2V5Brakes.text = bs.v5Brakes.joinToString("   ·   ") { b ->
                if (b.isHard) "⛔ ${b.label}" else "${b.label} ${String.format(Locale.getDefault(), "%.2f", b.factor)}"
            }
            val hasHard = bs.v5Brakes.any { it.isHard }
            binding.v2V5Brakes.setTextColor(Color.parseColor(if (hasHard) "#ff5252" else "#fb923c"))
        }

        binding.v2V5Strip.contentDescription =
            "Boost V6 ${bs.v5State.verb}, score ${String.format(Locale.getDefault(), "%.2f", bs.v5Score)}, dose ${String.format(Locale.getDefault(), "%.2f", bs.v5FinalDose)} units"
    }

    @SuppressLint("SetTextI18n")
    private fun showV5Detail() {
        val a = activity ?: return
        val bs = lastBoostStatus
        val sb = StringBuilder()
        sb.append("State: ${bs.v5State.label} (${bs.v5State.verb}) · age ${bs.v5Age} cycle${if (bs.v5Age == 1) "" else "s"}")
        sb.append("\n\nMeal score: ${String.format(Locale.getDefault(), "%.2f", bs.v5Score)}   (enter 0.44 · confirm 0.55)")
        sb.append("\nAction multiplier: ×${String.format(Locale.getDefault(), "%.2f", bs.v5ActionMult)}")
        sb.append("\nAggression budget: ${String.format(Locale.getDefault(), "%.2f", bs.v5Budget)}U")
        sb.append("\nDose this cycle: ${String.format(Locale.getDefault(), "%.2f", bs.v5FinalDose)}U")
        sb.append("\n\nBrakes:")
        if (bs.v5Brakes.isEmpty()) sb.append("\n  none")
        else bs.v5Brakes.forEach { b ->
            if (b.isHard) sb.append("\n  ⛔ ${b.label} (hard disable)")
            else sb.append("\n  ${b.label}: ×${String.format(Locale.getDefault(), "%.2f", b.factor)}")
        }
        sb.append("\n\nDelta accel: ${String.format(Locale.getDefault(), "%.1f", bs.deltaAccl)}%")
        sb.append("\n\n--- Script Debug ---\n${bs.scriptDebugText.ifEmpty { "(no debug output)" }}")
        OKDialog.show(a, "Boost V6 decision", sb.toString())
    }

    // --- Profile ---

    private fun updateProfile() {
        if (!isAdded) return
        val profile = profileFunction.getProfile()
        val isModified = (profile as? ProfileSealed.EPS)?.let {
            it.value.originalPercentage != 100 || it.value.originalTimeshift != 0L || it.value.originalDuration != 0L
        } ?: false
        val pct = (profile as? ProfileSealed.EPS)?.value?.originalPercentage ?: 100

        runOnUiThread {
            _binding ?: return@runOnUiThread
            // Profile pill already shows boost tier; the pct reflects the profile percentage
            binding.v2PillProfilePct.text = "${pct}%"
            val color = if (isModified) Color.parseColor("#ffb300") else Color.parseColor("#00d4ff")
            binding.v2PillProfilePct.setTextColor(color)
        }
    }

    // --- Pump info (left hero column) ---

    @SuppressLint("SetTextI18n")
    private fun updatePumpInfo(cached: BoostOverviewHelper.BoostStatus? = null) {
        if (!isAdded) return
        val pump = activePlugin.activePump
        val boostStatus = cached ?: boostHelper.getBoostStatus()
        // Database lookups stay off the main thread; only the view writes go to it.
        val cannulaTE = persistenceLayer.getLastTherapyRecordUpToNow(TE.Type.CANNULA_CHANGE)
        val sensorTE = persistenceLayer.getLastTherapyRecordUpToNow(TE.Type.SENSOR_CHANGE)
        val batteryTE = persistenceLayer.getLastTherapyRecordUpToNow(TE.Type.PUMP_BATTERY_CHANGE)
        val battery = pumpBatteryReading(pump, batteryTE?.timestamp)
        val phoneBattery = uploaderBatteryReading()
        runOnUiThread {
            _binding ?: return@runOnUiThread
            val res = pump.reservoirLevel
            val maxReading = pump.pumpDescription.maxResorvoirReading.toDouble()
            if (pump.pumpDescription.isPatchPump && res >= maxReading) {
                binding.v2PumpReservoir.text = "${decimalFormatter.to0Decimal(maxReading)}+U"
            } else if (res > 0) {
                binding.v2PumpReservoir.text = "${decimalFormatter.to0Decimal(res)}U"
                warnColors.setColorInverse(binding.v2PumpReservoir, res,
                    preferences.get(IntKey.OverviewResWarning), preferences.get(IntKey.OverviewResCritical))
            } else {
                binding.v2PumpReservoir.text = "---"
            }

            binding.v2PumpBatteryRow.visibility = battery.visible.toVisibility()
            binding.v2PumpBattery.text = battery.text
            when (battery.kind) {
                BoostBatteryDisplay.Kind.PERCENT ->
                    warnColors.setColorInverse(binding.v2PumpBattery, (battery.percent ?: 0).toDouble(),
                        preferences.get(IntKey.OverviewBattWarning), preferences.get(IntKey.OverviewBattCritical))
                BoostBatteryDisplay.Kind.AGE     ->
                    if (batteryTE != null) warnColors.setColorByAge(binding.v2PumpBattery, batteryTE,
                        preferences.get(IntKey.OverviewBageWarning), preferences.get(IntKey.OverviewBageCritical))
                else                             -> binding.v2PumpBattery.setTextColor(Color.parseColor("#aaaaaa"))
            }

            binding.v2PhoneBatteryRow.visibility = phoneBattery.visible.toVisibility()
            binding.v2PhoneBattery.text = phoneBattery.text

            val cStr = formatAgeDaysHours(boostStatus.cannulaAgeDays)
            val sStr = formatAgeDaysHours(boostStatus.sensorAgeDays)
            binding.v2PumpCannulaAge.text = cStr
            binding.v2PumpSensorAge.text = sStr

            // Apply warning colours
            if (cannulaTE != null) {
                warnColors.setColorByAge(binding.v2PumpCannulaAge, cannulaTE,
                    preferences.get(IntKey.OverviewCageWarning), preferences.get(IntKey.OverviewCageCritical))
            }
            if (sensorTE != null) {
                warnColors.setColorByAge(binding.v2PumpSensorAge, sensorTE,
                    preferences.get(IntKey.OverviewSageWarning), preferences.get(IntKey.OverviewSageCritical))
            }

            // TalkBack
            val resDesc = if (res > 0) "${decimalFormatter.to0Decimal(res)} units" else "unknown"
            val parts = mutableListOf("reservoir $resDesc")
            if (battery.visible) parts += "pump battery ${battery.spoken}"
            if (phoneBattery.visible) parts += "main phone battery ${phoneBattery.spoken}"
            parts += "cannula $cStr"
            parts += "sensor $sStr"
            binding.v2PumpSection.contentDescription = "Pump: " + parts.joinToString(", ")
        }
    }

    /**
     * Pump battery for the pump column. The full app reads the local driver; AAPSClient's local pump
     * is the virtual pump (constant 50 %), so it reads the main phone's Nightscout device status.
     */
    private fun pumpBatteryReading(pump: app.aaps.core.interfaces.pump.Pump, batteryChangeTs: Long?): BoostBatteryDisplay.Reading {
        val now = dateUtil.now()
        return if (config.AAPSCLIENT) {
            val ns = processedDeviceStatusData.pumpData?.let {
                BoostBatteryDisplay.NsPump(
                    clock = it.clock,
                    percent = if (it.isPercent) it.percent else null,
                    voltage = if (!it.isPercent) it.voltage else null
                )
            }
            BoostBatteryDisplay.pumpBattery(true, null, ns, batteryChangeTs, now, nsStaleAfterMs())
        } else {
            val model = pump.model()
            val erosLink = model == PumpType.OMNIPOD_EROS && pump.isUseRileyLinkBatteryLevel()
            val local = BoostBatteryDisplay.LocalPump(
                level = pump.batteryLevel,
                supportsLevel = model.supportBatteryLevel || erosLink,
                batteryAgeApplies = pump.pumpDescription.isBatteryReplaceable || pump.isBatteryChangeLoggingEnabled(),
                patchWithoutLink = pump.pumpDescription.isPatchPump && !pump.pumpDescription.useHardwareLink
            )
            BoostBatteryDisplay.pumpBattery(false, local, null, batteryChangeTs, now, nsStaleAfterMs())
        }
    }

    private fun uploaderBatteryReading(): BoostBatteryDisplay.Reading {
        if (!config.AAPSCLIENT) return BoostBatteryDisplay.uploaderBattery(false, emptyList(), 0L, 0L)
        // uploaderMap is a plain HashMap written by the Nightscout handler on another thread.
        val uploaders = runCatching {
            processedDeviceStatusData.uploaderMap.values.toList().map { BoostBatteryDisplay.NsUploader(it.clock, it.battery, it.isCharging) }
        }.getOrDefault(emptyList())
        return BoostBatteryDisplay.uploaderBattery(true, uploaders, dateUtil.now(), nsStaleAfterMs())
    }

    /** The Nightscout "urgentClock" pump setting (default 60 min), which the stock client status uses for the same purpose. */
    private fun nsStaleAfterMs(): Long =
        (nsSettingsStatus.extendedPumpSettings("urgentClock").takeIf { it > 0 } ?: 60.0).let { (it * 60_000L).toLong() }

    // --- Hero right column (Target, Exercise) ---

    @SuppressLint("SetTextI18n")
    private fun updateHeroRight(cached: BoostOverviewHelper.BoostStatus? = null) {
        if (!isAdded) return
        val bs = cached ?: boostHelper.getBoostStatus()

        val tempTarget = persistenceLayer.getTemporaryTargetActiveAt(dateUtil.now())
        val hasTempTarget = tempTarget != null
        val profileTargetMgdl = profileFunction.getProfile()?.getTargetMgdl() ?: 0.0
        val targetMgdl: Double = when {
            hasTempTarget -> tempTarget!!.lowTarget
            bs.targetBgMgdl > 0 && profileTargetMgdl > 0 &&
                kotlin.math.abs(profileTargetMgdl - bs.targetBgMgdl) > 0.01 -> bs.targetBgMgdl
            else -> profileTargetMgdl.takeIf { it > 0 } ?: 100.0
        }
        val targetStr = profileUtil.fromMgdlToStringInUnits(targetMgdl)

        runOnUiThread {
            _binding ?: return@runOnUiThread
            binding.v2TargetValue.text = targetStr
            binding.v2TargetValue.setTextColor(
                when {
                    hasTempTarget -> Color.parseColor("#ffb300")
                    else          -> Color.parseColor("#e8eaf0")
                }
            )

            binding.v2ExerciseLabel.text = bs.activityDetail
            val actColor = when (bs.activityMode) {
                BoostOverviewHelper.ActivityMode.ACTIVE    -> Color.parseColor("#ffb300")
                BoostOverviewHelper.ActivityMode.INACTIVE  -> Color.parseColor("#60a5fa")
                BoostOverviewHelper.ActivityMode.SLEEP_IN  -> Color.parseColor("#c084fc")
                BoostOverviewHelper.ActivityMode.BOOST_OFF -> Color.parseColor("#9aa0ad")
                else                                       -> Color.parseColor("#aaaaaa")
            }
            binding.v2ExerciseLabel.setTextColor(actColor)
        }
    }

    // --- Pump status bar ---

    private fun updatePumpStatus() {
        runOnUiThread {
            _binding ?: return@runOnUiThread
            val status = overviewData.pumpStatus
            if (status.isEmpty()) binding.v2PumpStatusLayout.visibility = View.GONE
            else { binding.v2PumpStatus.text = status; binding.v2PumpStatusLayout.visibility = View.VISIBLE }
        }
    }

    // --- Graph ---

    private fun updateGraph() {
        _binding ?: return
        val ctx = context ?: return
        val pump = activePlugin.activePump
        val graphData = graphDataProvider.get().with(binding.v2BgGraph, overviewData)
        val menuChartSettings = overviewMenus.setting
        if (menuChartSettings.isEmpty()) return

        // Guarded so a render hiccup can never throw to the main looper and force-close the app.
        // updateGraph() runs on the main thread and reads overviewData series that the calculation
        // workers concurrently rebuild/reassign on a range change; a transient (e.g. a NaN scale
        // divisor on a just-reset series, or a partially-prepared window) must degrade to "no repaint
        // this pass", not a crash. The steps/HR block below has always had its own guard; this
        // extends the same protection to the BG+IOB render, which was the unguarded crash path
        // reached via refreshAll → runOnUiThread. (2026-07-16 — v2 hours-change crash.)
        try {
            graphData.addInRangeArea(overviewData.fromTime, overviewData.endTime,
                preferences.get(UnitDoubleKey.OverviewLowMark), preferences.get(UnitDoubleKey.OverviewHighMark))
            graphData.addBgReadings(menuChartSettings[0][OverviewMenus.CharType.PRE.ordinal], ctx)
            graphData.addBucketedData()
            graphData.addTreatments(ctx)
            graphData.addEps(ctx, 0.95)
            if (menuChartSettings[0][OverviewMenus.CharType.TREAT.ordinal]) graphData.addTherapyEvents()
            if (menuChartSettings[0][OverviewMenus.CharType.ACT.ordinal]) graphData.addActivity(0.8)
            if ((pump.pumpDescription.isTempBasalCapable || config.AAPSCLIENT) && menuChartSettings[0][OverviewMenus.CharType.BAS.ordinal])
                graphData.addBasals()
            graphData.addTargetLine()
            graphData.addRunningModes()
            graphData.addNowLine(dateUtil.now())
            graphData.setNumVerticalLabels()
            graphData.formatAxis(overviewData.fromTime, overviewData.endTime)
            graphData.performUpdate()
            graphData.applyV2Theme()

            // IOB graph
            val iobGraphData = graphDataProvider.get().with(binding.v2IobGraph, overviewData)
            iobGraphData.addIob(true, 1.0)
            iobGraphData.addNowLine(dateUtil.now())
            iobGraphData.formatAxis(overviewData.fromTime, overviewData.endTime)
            iobGraphData.performUpdate()
            iobGraphData.applyV2Theme()
        } catch (e: Exception) {
            aapsLogger.error(LTag.UI, "V2 BG/IOB graph render failed", e)
            return
        }

        // Activity graph (steps + heart rate) — replaces the old sensitivity preview. DATA-DRIVEN:
        // show whichever of steps/HR actually has data in the visible window; hide the whole card
        // only when neither does. The HR/steps series are populated unconditionally by
        // PrepareTreatmentsDataWorker, so this does NOT depend on the chart-menu HR/STEPS toggles
        // (those default OFF, which previously hid the graph entirely). Legacy "sensitivity" view
        // IDs are repurposed, not renamed. Wrapped so a graph hiccup can never break the overview.
        try {
            val hrSeries = overviewData.heartRateGraphSeries as PointsWithLabelGraphSeries<DataPointWithLabelInterface>
            val stepsSeries = overviewData.stepsCountGraphSeries as PointsWithLabelGraphSeries<DataPointWithLabelInterface>
            val plotHr = !hrSeries.isEmpty
            val plotSteps = !stepsSeries.isEmpty
            if (plotHr || plotSteps) {
                binding.v2SensitivityGraphContainer.visibility = View.VISIBLE
                val actGraphData = graphDataProvider.get().with(binding.v2SensitivityGraph, overviewData)
                val useHrForScale = plotHr && !plotSteps
                val useStepsForScale = plotSteps
                // Add the scale-OWNING series first so the other's multiplier is computed against the
                // established maxY (else HR added first vs an uninitialized maxY -> flat-line trace).
                if (plotSteps) actGraphData.addSteps(useStepsForScale, if (useStepsForScale) 1.0 else 0.8)
                if (plotHr) actGraphData.addHeartRate(useHrForScale, if (useHrForScale) 1.0 else 0.8)
                actGraphData.addNowLine(dateUtil.now())
                actGraphData.formatAxis(overviewData.fromTime, overviewData.endTime)
                actGraphData.performUpdate()
                actGraphData.applyV2Theme()
                binding.v2SensitivityGraphLabel.text = when {
                    plotHr && plotSteps -> "Heart rate · Steps"
                    plotHr              -> "Heart rate"
                    else                -> "Steps"
                }
            } else {
                binding.v2SensitivityGraphContainer.visibility = View.GONE
            }
        } catch (e: Exception) {
            aapsLogger.error(LTag.UI, "V2 activity (steps/HR) graph failed", e)
            binding.v2SensitivityGraphContainer.visibility = View.GONE
        }

        // TalkBack
        val hours = overviewData.rangeToDisplay
        binding.v2BgGraph.contentDescription = "Blood glucose graph, ${hours} hour view"
        binding.v2IobGraph.contentDescription = "Insulin on board graph, ${hours} hour view"
    }

    // --- Notifications ---

    private fun updateNotification() {
        _binding ?: return
        binding.v2Notifications.let { notificationStore.updateNotifications(it) }
    }

    // --- Button visibility (hidden standard buttons for accept temp, quick wizard) ---

    @SuppressLint("SetTextI18n")
    private fun processButtonsVisibility() {
        _binding ?: return
        val profile = profileFunction.getProfile()
        val pump = activePlugin.activePump
        val actualBG = iobCobCalculator.ads.actualBg()

        // Accept temp button (shown in hidden buttons layout when open loop has pending change)
        val lastRun = loop.lastRun
        if (lastRun?.request?.isChangeRequested == true && loop.runningMode != RM.Mode.DISCONNECTED_PUMP && loop.runningMode == RM.Mode.OPEN_LOOP) {
            binding.v2ButtonsLayout.acceptTempButton.visibility = View.VISIBLE
            binding.v2ButtonsLayout.root.visibility = View.VISIBLE
            binding.v2ButtonsLayout.acceptTempButton.text = "${rh.gs(R.string.set_basal_question)}\n${lastRun.constraintsProcessed?.resultAsString()}"
        } else {
            binding.v2ButtonsLayout.acceptTempButton.visibility = View.GONE
        }

        // Quick wizard
        val quickWizardEntry = quickWizard.getActive()
        if (quickWizardEntry != null && actualBG != null && profile != null) {
            binding.v2ButtonsLayout.quickWizardButton.visibility = View.VISIBLE
            binding.v2ButtonsLayout.root.visibility = View.VISIBLE
            val wizard = quickWizardEntry.doCalc(profile, profileFunction.getProfileName(), actualBG)
            binding.v2ButtonsLayout.quickWizardButton.text = quickWizardEntry.buttonText() + "\n" +
                rh.gs(app.aaps.core.objects.R.string.format_carbs, quickWizardEntry.carbs()) +
                " " + rh.gs(app.aaps.core.ui.R.string.format_insulin_units, wizard.calculatedTotalInsulin)
            if (wizard.calculatedTotalInsulin <= 0) binding.v2ButtonsLayout.quickWizardButton.visibility = View.GONE
        } else {
            binding.v2ButtonsLayout.quickWizardButton.visibility = View.GONE
        }

        // Hide the standard row's fixed treatment buttons — V2 renders its own card buttons instead.
        binding.v2ButtonsLayout.treatmentButton.visibility = View.GONE
        binding.v2ButtonsLayout.wizardButton.visibility = View.GONE
        binding.v2ButtonsLayout.insulinButton.visibility = View.GONE
        binding.v2ButtonsLayout.carbsButton.visibility = View.GONE
        binding.v2ButtonsLayout.calibrationButton.visibility = View.GONE
        binding.v2ButtonsLayout.cgmButton.visibility = View.GONE

        // Automation user-action buttons — dynamic/swappable row, same source as the standard overview.
        val hasUserActions = processUserActionButtons(pump, profile)

        // V2's own card buttons: pref-driven visibility using the SAME keys as the standard overview,
        // so they toggle from the same Config → Overview → Buttons settings.
        binding.v2BtnInsulin.visibility = preferences.get(BooleanKey.OverviewShowInsulinButton).toVisibility()
        binding.v2BtnCalculator.visibility = preferences.get(BooleanKey.OverviewShowWizardButton).toVisibility()
        binding.v2BtnCarbs.visibility = preferences.get(BooleanKey.OverviewShowCarbsButton).toVisibility()
        binding.v2BtnTreatment.visibility = preferences.get(BooleanKey.OverviewShowTreatmentButton).toVisibility()
        binding.v2BtnCalibration.visibility =
            (preferences.get(BooleanKey.OverviewShowCalibrationButton) && xDripSource.isEnabled()).toVisibility()
        binding.v2BtnCgm.visibility =
            (preferences.get(BooleanKey.OverviewShowCgmButton) && (xDripSource.isEnabled() || dexcomBoyda.isEnabled())).toVisibility()

        // Show the included standard layout when accept-temp, quick-wizard, or any user action is present.
        val anyVisible = binding.v2ButtonsLayout.acceptTempButton.visibility == View.VISIBLE ||
            binding.v2ButtonsLayout.quickWizardButton.visibility == View.VISIBLE ||
            hasUserActions
        binding.v2ButtonsLayout.root.visibility = anyVisible.toVisibility()
        arrangeActionButtons()
    }

    /** Re-flows the V2 action cards into rows of at most three, from whichever are visible now. */
    private fun arrangeActionButtons() {
        ButtonGrid.arrange(
            binding.v2ActionButtons,
            listOf(binding.v2BtnInsulin, binding.v2BtnCalculator, binding.v2BtnCarbs, binding.v2BtnTreatment, binding.v2BtnCalibration, binding.v2BtnCgm),
            gapPx = rh.dpToPx(8), rowGapPx = rh.dpToPx(8)
        )
    }

    /**
     * Populates the automation user-action button row (dynamic/swappable). Mirrors the standard
     * overview's mechanism: one [SingleClickButton] per enabled, runnable automation user event.
     * Returns true if any user-action button is showing.
     */
    private fun processUserActionButtons(
        pump: app.aaps.core.interfaces.pump.Pump,
        profile: app.aaps.core.interfaces.profile.Profile?
    ): Boolean {
        var list = ""
        val container = binding.v2ButtonsLayout.userButtonsLayout
        container.removeAllViews()
        val events = automation.userEvents()
        if (!loop.runningMode.isSuspended() && pump.isInitialized() && profile != null && !config.showUserActionsOnWatchOnly())
            for (event in events)
                if (event.isEnabled && event.canRun()) {
                    context?.let { ctx ->
                        app.aaps.core.ui.elements.SingleClickButton(ctx, null, app.aaps.core.ui.R.attr.customBtnStyle).also { btn ->
                            btn.setTextColor(rh.gac(ctx, app.aaps.core.ui.R.attr.userOptionColor))
                            btn.setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 10f)
                            btn.layoutParams = android.widget.LinearLayout.LayoutParams(0, android.view.ViewGroup.LayoutParams.MATCH_PARENT, 0.5f).also { l ->
                                l.setMargins(rh.dpToPx(1), 0, rh.dpToPx(1), 0)
                            }
                            btn.setPadding(rh.dpToPx(1), btn.paddingTop, rh.dpToPx(1), btn.paddingBottom)
                            btn.compoundDrawablePadding = rh.dpToPx(-4)
                            btn.setCompoundDrawablesWithIntrinsicBounds(
                                null,
                                rh.gd(event.firstActionIcon() ?: app.aaps.core.ui.R.drawable.ic_user_options_24dp).also { icon ->
                                    icon?.setBounds(rh.dpToPx(20), rh.dpToPx(20), rh.dpToPx(20), rh.dpToPx(20))
                                }, null, null
                            )
                            btn.text = event.title
                            btn.setOnClickListener {
                                OKDialog.showConfirmation(
                                    ctx, rh.gs(R.string.run_question, event.title),
                                    Runnable { handler.post { automation.processEvent(event) } }
                                )
                            }
                            container.addView(btn)
                            for (d in btn.compoundDrawables) {
                                d?.mutate()
                                d?.colorFilter = android.graphics.PorterDuffColorFilter(rh.gac(ctx, app.aaps.core.ui.R.attr.userOptionColor), android.graphics.PorterDuff.Mode.SRC_IN)
                            }
                        }
                    }
                    list += event.hashCode()
                }
        container.visibility = events.isNotEmpty().toVisibility()
        ButtonGrid.arrange(container, (0 until container.childCount).map { container.getChildAt(it) }, rh.dpToPx(2), rh.dpToPx(2))
        if (list != lastUserAction) {
            lastUserAction = list
            rxBus.send(EventWearUpdateTiles())
        }
        return events.isNotEmpty()
    }

    /** Opens an external CGM app (xDrip / Dexcom) — mirrors the standard overview's cgm button. */
    private fun openCgmApp(packageName: String) {
        context?.let {
            try {
                val intent = it.packageManager.getLaunchIntentForPackage(packageName)
                    ?: throw android.content.ActivityNotFoundException()
                intent.addCategory(android.content.Intent.CATEGORY_LAUNCHER)
                it.startActivity(intent)
            } catch (_: android.content.ActivityNotFoundException) {
                aapsLogger.debug(LTag.CORE, "Error opening CGM app")
            }
        }
    }

    // --- Click handlers ---

    @SuppressLint("SetTextI18n")
    override fun onClick(v: View) {
        if (childFragmentManager.isStateSaved) return
        activity?.let { a ->
            when (v.id) {
                // Stat pill clicks
                R.id.v2_pill_iob -> {
                    val bi = iobCobCalculator.calculateIobFromBolus().round()
                    val ba = iobCobCalculator.calculateIobFromTempBasalsIncludingConvertedExtended().round()
                    OKDialog.show(a, rh.gs(app.aaps.core.ui.R.string.iob),
                        "Total: ${String.format(Locale.getDefault(), "%.2f", bi.iob + ba.basaliob)}U\nBolus: ${String.format(Locale.getDefault(), "%.2f", bi.iob)}U\nBasal: ${String.format(Locale.getDefault(), "%.2f", ba.basaliob)}U")
                }
                R.id.v2_pill_dynisf -> {
                    val bs = lastBoostStatus
                    val units = profileFunction.getUnits()
                    val unitsStr = if (units == GlucoseUnit.MGDL) "mg/dL" else "mmol/L"
                    val details = StringBuilder()
                    val dynConverted = if (bs.variableSens > 0) profileUtil.fromMgdlToUnits(bs.variableSens) else 0.0
                    val dynFmt = if (units == GlucoseUnit.MGDL) "%.0f" else "%.1f"
                    details.append("Dynamic ISF: ${if (bs.variableSens > 0) String.format(Locale.getDefault(), dynFmt, dynConverted) else "---"} $unitsStr/U")
                    details.append("\n\nAlgorithm inputs:")
                    val bgConverted = if (bs.lastBg > 0) profileUtil.fromMgdlToStringInUnits(bs.lastBg) else "---"
                    details.append("\n  BG: $bgConverted $unitsStr")
                    details.append("\n  TDD (weighted): ${if (bs.tddWeighted > 0) String.format(Locale.getDefault(), "%.1f", bs.tddWeighted) else "---"}")
                    if (bs.insulinDivisor > 0) details.append("\n  Insulin divisor: ${bs.insulinDivisor}")
                    details.append("\n\nTDD 7d avg: ${String.format(Locale.getDefault(), "%.1f", bs.tdd7d)}")
                    details.append("\nTDD 24h: ${String.format(Locale.getDefault(), "%.1f", bs.tdd24h)}")
                    OKDialog.show(a, "Dynamic ISF", details.toString())
                }
                R.id.v2_pill_tdd -> {
                    val bs = lastBoostStatus
                    OKDialog.show(a, "Total Daily Dose",
                        "oapsProfile.TDD: ${if (bs.tddWeighted > 0) String.format(Locale.getDefault(), "%.1f", bs.tddWeighted) else "(not set)"}\n" +
                            "TDD from debug: ${if (bs.tddFromDebug > 0) String.format(Locale.getDefault(), "%.1f", bs.tddFromDebug) else "(not found)"}\n" +
                            "TDD 7d avg: ${String.format(Locale.getDefault(), "%.1f", bs.tdd7d)}\n" +
                            "TDD 24h: ${String.format(Locale.getDefault(), "%.1f", bs.tdd24h)}\n\n" +
                            "--- Script Debug ---\n${bs.scriptDebugText.ifEmpty { "(no debug output)" }}")
                }
                R.id.v2_pill_profile -> {
                    // Profile pill opens the standard profile-switch dialog. Meal-management
                    // state/detail is in the V5 strip below (tap it for the full decision).
                    uiInteraction.runProfileSwitchDialog(childFragmentManager)
                }

                // V5 state strip tap -> V5 decision detail
                R.id.v2_v5_strip -> showV5Detail()

                // Target value tap -> temp target dialog
                R.id.v2_target_value -> {
                    protectionCheck.queryProtection(a, ProtectionCheck.Protection.BOLUS,
                        UIRunnable { if (isAdded) uiInteraction.runTempTargetDialog(childFragmentManager) })
                }

                // Exercise label tap -> activity details
                R.id.v2_exercise_label -> {
                    val bs = lastBoostStatus
                    val units = profileFunction.getUnits()
                    val unitsLabel = if (units == GlucoseUnit.MGDL) "mg/dL" else "mmol/L"
                    val exerciseTargetStr = if (bs.targetBgMgdl > 0)
                        "${profileUtil.fromMgdlToStringInUnits(bs.targetBgMgdl)} $unitsLabel"
                    else "---"
                    OKDialog.show(a, "Exercise / Activity Mode",
                        "Current: ${bs.activityDetail}\n\n" +
                            "Exercise target: $exerciseTargetStr\n\n" +
                            "Profile: ${bs.profilePercentage}%\n\n" +
                            "--- Script Debug ---\n${bs.scriptDebugText.ifEmpty { "(no debug output)" }}")
                }

                // Bottom action buttons
                R.id.v2_btn_insulin -> {
                    protectionCheck.queryProtection(a, ProtectionCheck.Protection.BOLUS,
                        UIRunnable { if (isAdded) uiInteraction.runInsulinDialog(childFragmentManager) })
                }
                R.id.v2_btn_calculator -> {
                    protectionCheck.queryProtection(a, ProtectionCheck.Protection.BOLUS,
                        UIRunnable { if (isAdded) uiInteraction.runWizardDialog(childFragmentManager) })
                }
                R.id.v2_btn_carbs -> {
                    protectionCheck.queryProtection(a, ProtectionCheck.Protection.BOLUS,
                        UIRunnable { if (isAdded) uiInteraction.runCarbsDialog(childFragmentManager) })
                }
                R.id.v2_btn_treatment -> {
                    protectionCheck.queryProtection(a, ProtectionCheck.Protection.BOLUS,
                        UIRunnable { if (isAdded) uiInteraction.runTreatmentDialog(childFragmentManager) })
                }
                R.id.v2_btn_calibration -> {
                    if (xDripSource.isEnabled()) uiInteraction.runCalibrationDialog(childFragmentManager)
                }
                R.id.v2_btn_cgm -> {
                    if (xDripSource.isEnabled()) openCgmApp("com.eveningoutpost.dexdrip")
                    else if (dexcomBoyda.isEnabled()) dexcomBoyda.dexcomPackages().forEach { openCgmApp(it) }
                }

                // AID status tap -> loop dialog
                R.id.v2_aid_status, R.id.v2_aid_dot -> {
                    protectionCheck.queryProtection(a, ProtectionCheck.Protection.BOLUS, UIRunnable {
                        if (isAdded) uiInteraction.runLoopDialog(childFragmentManager, 1)
                    })
                }

                // Standard hidden buttons
                R.id.accept_temp_button -> {
                    protectionCheck.queryProtection(a, ProtectionCheck.Protection.BOLUS, UIRunnable {
                        if (isAdded) {
                            // Must ENACT the pending open-loop change, not re-run the loop. The old code
                            // called loop.invoke() (which just re-triggers the APS) and logged
                            // ACCEPTS_TEMP_BASAL without ever calling acceptChangeRequest() — so for an
                            // open-loop user the tap reached the pump with nothing while the audit trail
                            // said "accepted". Mirror stock OverviewFragment. (2026-07-16)
                            val lastRun = loop.lastRun
                            if (lastRun?.lastAPSRun != null && lastRun.constraintsProcessed?.isChangeRequested == true) {
                                uel.log(Action.ACCEPTS_TEMP_BASAL, Sources.Overview)
                                handler.post { loop.acceptChangeRequest() }
                                binding.v2ButtonsLayout.acceptTempButton.visibility = View.GONE
                            }
                        }
                    })
                }
                R.id.quick_wizard_button -> {
                    protectionCheck.queryProtection(a, ProtectionCheck.Protection.BOLUS,
                        UIRunnable { if (isAdded) onClickQuickWizard() })
                }

                // Pump status bar tap
                R.id.v2_pump_status_layout -> {
                    popupBolusDialogIfRunning(onClick = true)
                }
            }
        }
    }

    private fun onClickQuickWizard() {
        context?.let { ctx ->
            startActivity(android.content.Intent(ctx, uiInteraction.quickWizardListActivity))
        }
    }

    fun popupBolusDialogIfRunning(onClick: Boolean) {
        if (commandQueue.bolusInQueue()) {
            if (!BolusProgressData.bolusEnded && (!BolusProgressData.isSMB || onClick)) {
                activity?.let { activity ->
                    protectionCheck.queryProtection(activity, ProtectionCheck.Protection.BOLUS, UIRunnable {
                        if (isAdded)
                            uiInteraction.runBolusProgressDialog(childFragmentManager)
                    })
                }
            }
        }
    }

    private fun formatAgeDaysHours(ageDays: Double): String {
        if (ageDays < 0) return "?"
        val totalHours = (ageDays * 24).toLong()
        val days = totalHours / 24
        val hours = totalHours % 24
        return "${days}d ${hours}h"
    }
}
