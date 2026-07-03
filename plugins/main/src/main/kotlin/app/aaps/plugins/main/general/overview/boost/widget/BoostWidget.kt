package app.aaps.plugins.main.general.overview.boost.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.util.TypedValue
import android.widget.RemoteViews
import app.aaps.core.data.model.GlucoseUnit
import app.aaps.core.interfaces.aps.Loop
import app.aaps.core.interfaces.configuration.Config
import app.aaps.core.interfaces.db.PersistenceLayer
import app.aaps.core.interfaces.iob.IobCobCalculator
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import app.aaps.core.interfaces.overview.LastBgData
import app.aaps.core.interfaces.profile.ProfileFunction
import app.aaps.core.interfaces.profile.ProfileUtil
import app.aaps.core.interfaces.resources.ResourceHelper
import app.aaps.core.interfaces.ui.UiInteraction
import app.aaps.core.interfaces.utils.DateUtil
import app.aaps.core.interfaces.utils.TrendCalculator
import app.aaps.core.keys.BooleanComposedKey
import app.aaps.core.keys.IntComposedKey
import app.aaps.core.keys.interfaces.Preferences
import app.aaps.core.objects.extensions.round
import app.aaps.plugins.main.R
import app.aaps.plugins.main.general.overview.boost.BgBobbleView
import app.aaps.plugins.main.general.overview.boost.BoostOverviewHelper
import dagger.android.HasAndroidInjector
import java.util.Locale
import javax.inject.Inject
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin

/**
 * Boost-specific home screen widget.
 *
 * Layout: BG bobble + tier on the left, 2x3 data table on the right
 * (DynISF, TDD, IOB, Activity, Profile%, Target).
 */
class BoostWidget : AppWidgetProvider() {

    @Inject lateinit var boostOverviewHelper: BoostOverviewHelper
    @Inject lateinit var profileFunction: ProfileFunction
    @Inject lateinit var profileUtil: ProfileUtil
    @Inject lateinit var lastBgData: LastBgData
    @Inject lateinit var trendCalculator: TrendCalculator
    @Inject lateinit var iobCobCalculator: IobCobCalculator
    @Inject lateinit var loop: Loop
    @Inject lateinit var persistenceLayer: PersistenceLayer
    @Inject lateinit var uiInteraction: UiInteraction
    @Inject lateinit var rh: ResourceHelper
    @Inject lateinit var dateUtil: DateUtil
    @Inject lateinit var aapsLogger: AAPSLogger
    @Inject lateinit var config: Config
    @Inject lateinit var preferences: Preferences

    companion object {

        private var handler = Handler(HandlerThread(BoostWidget::class.simpleName + "Handler").also { it.start() }.looper)

        fun updateWidget(context: Context, from: String) {
            context.sendBroadcast(Intent().also {
                it.component = ComponentName(context, BoostWidget::class.java)
                it.putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, AppWidgetManager.getInstance(context)?.getAppWidgetIds(ComponentName(context, BoostWidget::class.java)))
                it.putExtra("from", from)
                it.action = AppWidgetManager.ACTION_APPWIDGET_UPDATE
            })
        }

        private fun zoneColor(bgMgdl: Double): Int = when {
            bgMgdl > 250 -> Color.parseColor("#FF1744")
            bgMgdl > 180 -> Color.parseColor("#FFEB3B")
            bgMgdl >= 70 -> Color.parseColor("#4CAF50")
            bgMgdl >= 54 -> Color.parseColor("#FF5722")
            bgMgdl > 0   -> Color.parseColor("#D50000")
            else          -> Color.parseColor("#4CAF50")
        }
    }

    private val intentAction = "OpenApp"

    override fun onReceive(context: Context, intent: Intent?) {
        (context.applicationContext as HasAndroidInjector).androidInjector().inject(this)
        aapsLogger.debug(LTag.WIDGET, "BoostWidget onReceive ${intent?.extras?.getString("from")}")
        super.onReceive(context, intent)
    }

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        val myIds = AppWidgetManager.getInstance(context)?.getAppWidgetIds(ComponentName(context, BoostWidget::class.java)) ?: intArrayOf()
        val myIdSet = myIds.toSet()
        for (appWidgetId in appWidgetIds) {
            if (appWidgetId in myIdSet) {
                updateAppWidget(context, appWidgetManager, appWidgetId)
            }
        }
    }

    override fun onEnabled(context: Context) {}
    override fun onDisabled(context: Context) {}

    override fun onAppWidgetOptionsChanged(context: Context, appWidgetManager: AppWidgetManager, appWidgetId: Int, newOptions: Bundle?) {
        (context.applicationContext as HasAndroidInjector).androidInjector().inject(this)
        updateAppWidget(context, appWidgetManager, appWidgetId)
    }

    private fun updateAppWidget(context: Context, appWidgetManager: AppWidgetManager, appWidgetId: Int) {
        val views = RemoteViews(context.packageName, R.layout.boost_widget_layout)
        val alpha = preferences.get(IntComposedKey.WidgetOpacity, appWidgetId)
        val useBlack = preferences.get(BooleanComposedKey.WidgetUseBlack, appWidgetId)

        val intent = Intent(context, uiInteraction.mainActivity).also { it.action = intentAction }
        val pendingIntent = PendingIntent.getActivity(context, 0, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        views.setOnClickPendingIntent(R.id.boost_widget_layout, pendingIntent)

        if (config.APS || useBlack)
            views.setInt(R.id.boost_widget_layout, "setBackgroundColor", Color.argb(alpha, 0, 0, 0))

        // Compute text sizes based on actual widget dimensions
        val options = appWidgetManager.getAppWidgetOptions(appWidgetId)
        val widthDp = options.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH, 250)
        val heightDp = options.getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT, 110)
        val sizes = computeTextSizes(widthDp, heightDp)

        applyTextSizes(views, sizes)

        handler.post {
            if (config.appInitialized) {
                updateBgBobble(views, context, heightDp)
                updateBoostData(views)
                updateTarget(views)
                updateIob(views)
                appWidgetManager.updateAppWidget(appWidgetId, views)
            }
        }
    }

    /** Scale text sizes proportionally to widget dimensions. */
    private fun computeTextSizes(widthDp: Int, heightDp: Int): TextSizes {
        // Base sizes at 250x110dp (3x2 widget). Scale from there.
        val widthScale = widthDp / 250f
        val heightScale = heightDp / 110f
        val scale = minOf(widthScale, heightScale).coerceIn(0.8f, 2.5f)

        return TextSizes(
            label = (11f * scale).coerceIn(9f, 16f),
            value = (16f * scale).coerceIn(12f, 30f),
            tier = (14f * scale).coerceIn(12f, 24f),
            timeAgo = (11f * scale).coerceIn(9f, 16f)
        )
    }

    private data class TextSizes(val label: Float, val value: Float, val tier: Float, val timeAgo: Float)

    private fun applyTextSizes(views: RemoteViews, s: TextSizes) {
        // Tier + time ago
        views.setTextViewTextSize(R.id.tier_label, TypedValue.COMPLEX_UNIT_SP, s.tier)
        views.setTextViewTextSize(R.id.time_ago, TypedValue.COMPLEX_UNIT_SP, s.timeAgo)

        // Value fields
        val valueIds = intArrayOf(R.id.dynisf, R.id.tdd, R.id.iob, R.id.activity_mode, R.id.profile_pct, R.id.temp_target)
        for (id in valueIds) {
            views.setTextViewTextSize(id, TypedValue.COMPLEX_UNIT_SP, s.value)
        }

        // Label fields
        val labelIds = intArrayOf(R.id.label_dynisf, R.id.label_tdd, R.id.label_iob, R.id.label_activity, R.id.label_profile, R.id.label_target)
        for (id in labelIds) {
            views.setTextViewTextSize(id, TypedValue.COMPLEX_UNIT_SP, s.label)
        }
    }

    /** Render BG bobble as a high-res bitmap that fills the left panel. */
    private fun updateBgBobble(views: RemoteViews, context: Context, heightDp: Int) {
        val density = context.resources.displayMetrics.density
        // Scale bobble to ~80% of widget height, min 100dp, max 240dp
        val bobbleDp = (heightDp * 0.8f).coerceIn(100f, 240f)
        val sizePx = (bobbleDp * density).toInt()
        val bgMgdl = lastBgData.lastBg()?.recalculated ?: 0.0
        val bgText = lastBgData.lastBg()?.let { profileUtil.fromMgdlToStringInUnits(it.recalculated) } ?: "---"
        val isActual = lastBgData.isActualBg()
        val trend = trendCalculator.getTrendArrow(iobCobCalculator.ads)
        val (trendAngle, chevronRotation) = BgBobbleView.trendToAngles(trend)

        val bitmap = Bitmap.createBitmap(sizePx, sizePx, Bitmap.Config.ARGB_8888)
        val c = Canvas(bitmap)
        val dp = density
        val sz = sizePx.toFloat()
        val cx = sz / 2f
        val cy = sz / 2f
        val sw = 8f * dp
        val r = (sz - sw * 2 - 16 * dp) / 2f
        val br = 14f * dp
        val z = zoneColor(bgMgdl)

        // Ring background
        val ringBgP = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE; strokeWidth = sw
            color = Color.argb(15, Color.red(z), Color.green(z), Color.blue(z))
        }
        c.drawCircle(cx, cy, r, ringBgP)

        // Full ring
        val ringP = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE; strokeWidth = sw; strokeCap = Paint.Cap.ROUND; color = z
        }
        c.drawArc(cx - r, cy - r, cx + r, cy + r, -90f, 360f, false, ringP)

        // Inner fill
        val fillP = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.FILL
            color = Color.argb(30, Color.red(z), Color.green(z), Color.blue(z))
        }
        c.drawCircle(cx, cy, r - sw / 2f - 4f * dp, fillP)

        // BG text
        val ir = r - sw / 2f - 4f * dp
        val bgTxtP = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            textAlign = Paint.Align.CENTER; isFakeBoldText = true
            color = z; textSize = ir * 0.58f
            if (!isActual) flags = flags or Paint.STRIKE_THRU_TEXT_FLAG
        }
        c.drawText(bgText, cx, cy + bgTxtP.textSize * 0.15f, bgTxtP)

        // Units label
        val units = profileFunction.getUnits()
        val unitsLabel = if (units == GlucoseUnit.MGDL) "mg/dL" else "mmol/L"
        val unitP = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            textAlign = Paint.Align.CENTER; color = Color.argb(128, 255, 255, 255)
            textSize = ir * 0.16f
        }
        c.drawText(unitsLabel, cx, cy + bgTxtP.textSize * 0.15f + unitP.textSize * 1.8f, unitP)

        // Trend chevron badge on ring
        val rad = Math.toRadians((trendAngle - 90).toDouble())
        val bx = cx + r * cos(rad).toFloat()
        val by = cy + r * sin(rad).toFloat()

        val badgeP = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL; color = Color.parseColor("#121212") }
        c.drawCircle(bx, by, br, badgeP)
        badgeP.color = Color.parseColor("#1E1E1E")
        c.drawCircle(bx, by, br - 2f * dp, badgeP)
        val badgeBdrP = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 2.5f * dp; color = z }
        c.drawCircle(bx, by, br - 2f * dp, badgeBdrP)

        val cs = br * 0.45f
        val chevP = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE; strokeWidth = 3f * dp; strokeCap = Paint.Cap.ROUND
            strokeJoin = Paint.Join.ROUND; color = z
        }
        val path = Path().apply {
            moveTo(-cs * 0.6f, -cs)
            lineTo(cs * 0.6f, 0f)
            lineTo(-cs * 0.6f, cs)
        }
        c.save()
        c.translate(bx, by)
        c.rotate(chevronRotation)
        c.drawPath(path, chevP)
        c.restore()

        views.setImageViewBitmap(R.id.bg_bobble, bitmap)

        // Time ago
        views.setTextViewText(R.id.time_ago, dateUtil.minOrSecAgo(rh, lastBgData.lastBg()?.timestamp))
    }

    private fun updateBoostData(views: RemoteViews) {
        val status = boostOverviewHelper.getBoostStatus()
        val units = profileFunction.getUnits()

        // Tier
        views.setTextViewText(R.id.tier_label, status.tierLabel)
        views.setTextColor(R.id.tier_label, status.tier.colorHex.toInt())

        // DynISF
        val dynIsfText = if (status.variableSens > 0) {
            String.format(Locale.getDefault(), "%.1f", profileUtil.fromMgdlToUnits(status.variableSens, units))
        } else "--"
        views.setTextViewText(R.id.dynisf, dynIsfText)

        // TDD
        val tddValue = when {
            status.tddWeighted > 0  -> status.tddWeighted
            status.tddFromDebug > 0 -> status.tddFromDebug
            status.tdd7d > 0        -> status.tdd7d
            else                    -> 0.0
        }
        val tddText = if (tddValue > 0) String.format(Locale.getDefault(), "%.1f U", tddValue) else "--"
        views.setTextViewText(R.id.tdd, tddText)

        // Activity mode
        views.setTextViewText(R.id.activity_mode, status.activityDetail)
        val activityColor = when (status.activityMode) {
            BoostOverviewHelper.ActivityMode.ACTIVE   -> Color.parseColor("#42A5F5")
            BoostOverviewHelper.ActivityMode.INACTIVE  -> Color.parseColor("#FF9800")
            BoostOverviewHelper.ActivityMode.SLEEP_IN  -> Color.parseColor("#AB47BC")
            BoostOverviewHelper.ActivityMode.BOOST_OFF -> Color.parseColor("#78909C")
            BoostOverviewHelper.ActivityMode.NORMAL    -> Color.WHITE
        }
        views.setTextColor(R.id.activity_mode, activityColor)

        // Profile percentage
        val pctText = "${status.profilePercentage}%"
        views.setTextViewText(R.id.profile_pct, pctText)
        if (status.profilePercentage != 100) {
            views.setTextColor(R.id.profile_pct, rh.gc(app.aaps.core.ui.R.color.widget_ribbonWarning))
        } else {
            views.setTextColor(R.id.profile_pct, Color.WHITE)
        }
    }

    /** Target display — temp target with time remaining, algorithm-adjusted, or profile default. */
    private fun updateTarget(views: RemoteViews) {
        val units = profileFunction.getUnits()
        val tempTarget = persistenceLayer.getTemporaryTargetActiveAt(dateUtil.now())
        if (tempTarget != null) {
            views.setTextColor(R.id.temp_target, rh.gc(app.aaps.core.ui.R.color.widget_ribbonWarning))
            views.setTextViewText(
                R.id.temp_target,
                profileUtil.toTargetRangeString(tempTarget.lowTarget, tempTarget.highTarget, GlucoseUnit.MGDL, units) + " " + dateUtil.untilString(tempTarget.end, rh)
            )
        } else {
            profileFunction.getProfile()?.let { profile ->
                val targetUsed = loop.lastRun?.constraintsProcessed?.targetBG
                    ?: boostOverviewHelper.getBoostStatus().targetBgMgdl
                if (targetUsed != 0.0 && abs(profile.getTargetMgdl() - targetUsed) > 0.01) {
                    views.setTextViewText(R.id.temp_target, profileUtil.toTargetRangeString(targetUsed, targetUsed, GlucoseUnit.MGDL, units))
                    views.setTextColor(R.id.temp_target, rh.gc(app.aaps.core.ui.R.color.widget_ribbonWarning))
                } else {
                    views.setTextColor(R.id.temp_target, rh.gc(app.aaps.core.ui.R.color.widget_ribbonTextDefault))
                    views.setTextViewText(R.id.temp_target, profileUtil.toTargetRangeString(profile.getTargetLowMgdl(), profile.getTargetHighMgdl(), GlucoseUnit.MGDL, units))
                }
            } ?: run {
                views.setTextViewText(R.id.temp_target, "--")
                views.setTextColor(R.id.temp_target, Color.WHITE)
            }
        }
    }

    private fun updateIob(views: RemoteViews) {
        val bolusIob = iobCobCalculator.calculateIobFromBolus().round()
        val basalIob = iobCobCalculator.calculateIobFromTempBasalsIncludingConvertedExtended().round()
        val totalIob = bolusIob.iob + basalIob.basaliob
        views.setTextViewText(R.id.iob, rh.gs(app.aaps.core.ui.R.string.format_insulin_units, totalIob))
    }
}
