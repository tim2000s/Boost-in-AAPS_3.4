package app.aaps.plugins.aps.openAPSBoost

import android.content.Context
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.sin

/**
 * SHADOW. Scores whether a fall already under way is going somewhere that matters.
 *
 * The question is one a controller can still act on. Twenty minutes into a fall it can withhold
 * insulin, zero-temp or ask for carbohydrate; the decision is open in a way it is not once a rise
 * is thirty minutes old. Offline, eleven descriptors of the first twenty minutes reach an area
 * under the curve of 0.780 on sixteen Boost participants who contributed no training row, against
 * 0.746 for glucose at onset and the clock, better for all sixteen of them.
 *
 * This class computes and logs. It doses nothing, and there is no path from its output to a dose.
 *
 * Two things a reader should know before trusting the number.
 *
 * The onset rule here is deliberately stricter than the one that built the training anchors. Those
 * required a 25 mg/dL drop within thirty minutes of a point above 70, which is only knowable thirty
 * minutes after the fact. This requires the same drop within twenty minutes, which is knowable at
 * the moment of scoring. Every onset this finds would also have been an offline anchor; some
 * offline anchors will not be found here. The shadow's first job is to measure how many.
 *
 * The score is a probability of reaching 70 mg/dL within two hours of onset, calibrated to the
 * training base rate of 0.221. It is not comparable to mlHypoRisk, which answers a different
 * question over a different horizon, and neither is a threshold transferable between them.
 */
@Singleton
class FallConsequenceShadow @Inject constructor(
    private val context: Context,
    private val aapsLogger: AAPSLogger
) {

    data class Node(
        val feature: Int = -1,
        val threshold: Double = 0.0,
        val left: Node? = null,
        val right: Node? = null,
        val leaf: Double? = null
    )

    data class Result(
        val score: Double,
        val onsetAgeMin: Int,
        val onsetBg: Double,
        val fall: Double,
        val stillFalling: Boolean
    )

    private val assetPath = "boost/fall_consequence_v1.json"
    private val loadLock = Any()
    private var trees: List<Node>? = null
    private var featureCount = 0
    @Volatile private var loaded = false
    @Volatile private var loadAttempted = false

    // Mirrors the trainer. MIN_FALL and FLOOR_MGDL are its values; SHAPE_MIN is its horizon.
    companion object {

        const val MIN_FALL_MGDL = 25.0
        const val FLOOR_MGDL = 70.0
        const val SHAPE_MIN = 20
        const val PRE_SLOPE_LOOKBACK_MIN = 15
        const val REFRACTORY_MIN = 60
        private const val TOLERANCE_MIN = 4      // a reading lands within a cycle of the 20-min mark
        private const val MIN_POINTS = 3         // the trainer's floor for a usable shape
    }

    private fun ensureLoaded() {
        if (loaded || loadAttempted) return
        synchronized(loadLock) {
            if (loaded || loadAttempted) return
            loadAttempted = true
            try {
                val raw = context.assets.open(assetPath).bufferedReader().readText()
                val json = JSONObject(raw)
                featureCount = json.getJSONArray("feature_names").length()
                val arr = json.getJSONArray("trees")
                trees = buildList { for (i in 0 until arr.length()) add(parse(arr.getJSONObject(i))) }
                loaded = true
                aapsLogger.info(LTag.APS, "FallConsequenceShadow loaded: ${trees?.size} trees, $featureCount features")
            } catch (e: Exception) {
                aapsLogger.info(LTag.APS, "FallConsequenceShadow NOT loaded: ${e.javaClass.simpleName}: ${e.message}")
                loaded = false
            }
        }
    }

    private fun parse(o: JSONObject): Node =
        if (o.has("leaf")) Node(leaf = o.getDouble("leaf"))
        else Node(
            feature = o.getInt("feature"),
            threshold = o.getDouble("threshold"),
            left = parse(o.getJSONObject("left")),
            right = parse(o.getJSONObject("right"))
        )

    private fun walk(n: Node, x: DoubleArray): Double {
        var cur = n
        while (cur.leaf == null) {
            cur = if (x[cur.feature] <= cur.threshold) cur.left!! else cur.right!!
        }
        return cur.leaf!!
    }

    /**
     * Least-squares quadratic coefficient, the `curv` feature.
     *
     * numpy.polyfit(t, y, 2)[0] by the normal equations. Written out rather than approximated
     * because the trained thresholds were placed on that exact quantity, and a different curvature
     * definition would move rows across splits without any error being visible.
     */
    internal fun quadCoefficient(t: DoubleArray, y: DoubleArray): Double {
        val n = t.size
        if (n < 4) return 0.0
        var s0 = 0.0; var s1 = 0.0; var s2 = 0.0; var s3 = 0.0; var s4 = 0.0
        var b0 = 0.0; var b1 = 0.0; var b2 = 0.0
        for (i in 0 until n) {
            val x = t[i]; val x2 = x * x
            s0 += 1.0; s1 += x; s2 += x2; s3 += x2 * x; s4 += x2 * x2
            b0 += y[i]; b1 += x * y[i]; b2 += x2 * y[i]
        }
        // solve [[s4,s3,s2],[s3,s2,s1],[s2,s1,s0]] . [a,b,c] = [b2,b1,b0] for a
        val m = arrayOf(
            doubleArrayOf(s4, s3, s2, b2),
            doubleArrayOf(s3, s2, s1, b1),
            doubleArrayOf(s2, s1, s0, b0)
        )
        for (col in 0 until 3) {
            var piv = col
            for (r in col + 1 until 3) if (abs(m[r][col]) > abs(m[piv][col])) piv = r
            val tmp = m[col]; m[col] = m[piv]; m[piv] = tmp
            if (abs(m[col][col]) < 1e-12) return 0.0
            for (r in 0 until 3) {
                if (r == col) continue
                val f = m[r][col] / m[col][col]
                for (c in col until 4) m[r][c] -= f * m[col][c]
            }
        }
        return m[0][3] / m[0][0]
    }

    /**
     * Build the 14-element vector in the order the model was trained on.
     *
     * `times` are epoch milliseconds ascending and `values` the matching glucose in mg/dL.
     * `i0` indexes the onset. Returns null when the window holds too few points, which is the
     * trainer's own behaviour rather than a substituted default.
     */
    internal fun features(times: LongArray, values: DoubleArray, i0: Int, localHour: Double): DoubleArray? {
        val t0 = times[i0]
        var end = i0
        while (end + 1 < times.size && times[end + 1] <= t0 + SHAPE_MIN * 60_000L) end++
        val n = end - i0 + 1
        if (n < MIN_POINTS) return null

        val seg = DoubleArray(n) { values[i0 + it] }
        val tseg = DoubleArray(n) { (times[i0 + it] - t0) / 60_000.0 }
        val base = seg[0]
        val span = max(tseg[n - 1], 1.0)

        var minv = seg[0]
        for (v in seg) if (v < minv) minv = v

        var auc = 0.0
        for (i in 0 until n - 1) {
            val a = max(base - seg[i], 0.0)
            val b = max(base - seg[i + 1], 0.0)
            auc += 0.5 * (a + b) * (tseg[i + 1] - tseg[i])
        }

        var decMax = Double.NEGATIVE_INFINITY
        var decSum = 0.0
        val dFirst = seg[1] - seg[0]
        val dLast = seg[n - 1] - seg[n - 2]
        for (i in 0 until n - 1) {
            val d = seg[i + 1] - seg[i]
            if (-d > decMax) decMax = -d
            decSum += d
        }
        val decMean = -decSum / (n - 1)

        // pre-slope: mg/dL per minute over the quarter hour before the onset
        var p = i0
        while (p > 0 && times[p - 1] >= t0 - PRE_SLOPE_LOOKBACK_MIN * 60_000L) p--
        val preSlope =
            if (p < i0) (values[i0] - values[p]) / max((t0 - times[p]) / 60_000.0, 1.0) else 0.0

        val ang = 2.0 * PI * localHour / 24.0
        return doubleArrayOf(
            base - seg[n - 1],                    // fall
            (base - seg[n - 1]) / span,           // fall_rate
            base - minv,                          // nadir, the depth of the fall not a glucose level
            auc,
            decMax,
            -dLast,
            decMean,
            -(dLast - dFirst),                    // accel
            quadCoefficient(tseg, seg),           // curv
            preSlope,
            if (dLast < 0) 1.0 else 0.0,          // still_falling
            base,
            sin(ang),
            cos(ang)
        )
    }

    /**
     * Find an onset roughly [SHAPE_MIN] minutes before the newest reading, and score it.
     *
     * Returns null when no onset qualifies, which is the common case: on the Boost cohort these
     * anchors occur a few times a day, not every cycle.
     */
    fun evaluate(times: LongArray, values: DoubleArray, localHourAtOnset: (Long) -> Double): Result? {
        ensureLoaded()
        val t = trees ?: return null
        if (times.size < 4) return null
        val now = times[times.size - 1]

        val target = now - SHAPE_MIN * 60_000L
        var i0 = -1
        var bestGap = Long.MAX_VALUE
        for (i in times.indices) {
            val gap = abs(times[i] - target)
            if (gap < bestGap && gap <= TOLERANCE_MIN * 60_000L) { bestGap = gap; i0 = i }
        }
        if (i0 < 1) return null
        if (values[i0] <= FLOOR_MGDL) return null

        var minAfter = values[i0]
        for (i in i0 until times.size) if (values[i] < minAfter) minAfter = values[i]
        if (values[i0] - minAfter < MIN_FALL_MGDL) return null

        val f = features(times, values, i0, localHourAtOnset(times[i0])) ?: return null
        if (featureCount != 0 && f.size != featureCount) return null

        var raw = 0.0
        for (tree in t) raw += walk(tree, f)
        val score = 1.0 / (1.0 + exp(-raw))
        return Result(
            score = score,
            onsetAgeMin = ((now - times[i0]) / 60_000L).toInt(),
            onsetBg = values[i0],
            fall = f[0],
            stillFalling = f[10] > 0.5
        )
    }

    fun isLoaded(): Boolean { ensureLoaded(); return loaded }
}
