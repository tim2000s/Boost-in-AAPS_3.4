package app.aaps.plugins.aps.openAPSBoostV3ML

import android.content.Context
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Lightweight on-device hypo risk model for Boost V3ML.
 *
 * Loads a LightGBM model exported as JSON (50 trees, depth 4, ~50KB) from the
 * APK's assets directory and runs inference via pure-Kotlin tree traversal.
 * No native library dependencies. Inference time: <5ms for 50 trees.
 *
 * Features (8, all available at decision time):
 *   0: cgm_mgdl          — current BG
 *   1: iob_iob            — total insulin on board
 *   2: iob_basaliob        — basal IOB component (signed deviation)
 *   3: bg_above_target     — BG minus algorithm target
 *   4: direction_num       — BG trend as numeric (-2 to +2)
 *   5: hour                — hour of day (0-23)
 *   6: iob_activity         — insulin activity (rate of IOB decay)
 *   7: sug_insulinReq       — algorithm's insulin requirement this cycle
 *
 * Output: P(hypo event in next 4h) as a Double in [0, 1].
 */
@Singleton
class BoostRiskModel @Inject constructor(
    private val context: Context,
    private val aapsLogger: AAPSLogger
) {

    private var trees: List<TreeNode>? = null
    private var featureNames: List<String>? = null
    @Volatile private var loaded = false
    @Volatile private var loadAttempted = false
    private val loadLock = Any()
    private val defaultAssetPath = "boost/hypo_risk_model.json"

    /**
     * Idempotent, thread-safe lazy loader. Called from predictHypoRisk()
     * so the model is guaranteed available on first inference after a
     * process restart, regardless of whether the user has opened the
     * settings screen. Falls back to no-op once a load attempt has been
     * made, so we don't retry on every cycle if the asset is missing.
     */
    private fun ensureLoaded() {
        if (loaded || loadAttempted) return
        synchronized(loadLock) {
            if (loaded || loadAttempted) return
            loadModel(context, defaultAssetPath)
            loadAttempted = true
        }
    }

    data class TreeNode(
        val isLeaf: Boolean,
        val leafValue: Double = 0.0,
        val featureIndex: Int = -1,
        val threshold: Double = 0.0,
        val left: TreeNode? = null,
        val right: TreeNode? = null,
    )

    /**
     * Load the model from a JSON asset file.
     * Call once during plugin initialization.
     */
    fun loadModel(context: Context, assetPath: String = "boost/hypo_risk_model.json"): Boolean {
        return try {
            val rawBytes = context.assets.open(assetPath).readBytes()
            val jsonStr = String(rawBytes, Charsets.UTF_8)
            aapsLogger.info(LTag.APS, "BoostRiskModel(V3ML) loading $assetPath (${rawBytes.size} bytes)")
            val json = JSONObject(jsonStr)

            featureNames = mutableListOf<String>().apply {
                val arr = json.getJSONArray("feature_names")
                for (i in 0 until arr.length()) add(arr.getString(i))
            }

            val treesArr = json.getJSONArray("trees")
            trees = mutableListOf<TreeNode>().apply {
                for (i in 0 until treesArr.length()) {
                    try {
                        add(parseNode(treesArr.getJSONObject(i)))
                    } catch (e: Exception) {
                        aapsLogger.error(LTag.APS, "BoostRiskModel(V3ML) tree $i parse failed: ${e.javaClass.simpleName}: ${e.message}")
                        aapsLogger.info(LTag.APS, "BoostRiskModel(V3ML) DIAG tree $i parse failed: ${e.javaClass.simpleName}: ${e.message}")
                        throw e
                    }
                }
            }

            loaded = true
            aapsLogger.info(LTag.APS, "BoostRiskModel(V3ML) loaded: ${trees?.size} trees, ${featureNames?.size} features from $assetPath")
            true
        } catch (e: Exception) {
            aapsLogger.error(LTag.APS, "BoostRiskModel(V3ML) failed to load from $assetPath: ${e.javaClass.simpleName}: ${e.message}")
            aapsLogger.info(LTag.APS, "BoostRiskModel(V3ML) DIAG load FAILED from $assetPath: ${e.javaClass.simpleName}: ${e.message}")
            loaded = false
            false
        }
    }

    private fun parseNode(json: JSONObject): TreeNode {
        if (json.has("leaf")) {
            return TreeNode(isLeaf = true, leafValue = json.getDouble("leaf"))
        }
        return TreeNode(
            isLeaf = false,
            featureIndex = json.getInt("feature"),
            threshold = json.getDouble("threshold"),
            left = parseNode(json.getJSONObject("left")),
            right = parseNode(json.getJSONObject("right")),
        )
    }

    /**
     * Predict P(hypo event in next 4h) given the 8 input features.
     * Returns a Double in [0, 1], or null if the model isn't loaded.
     *
     * @param cgmMgdl Current BG in mg/dL
     * @param iobTotal Total insulin on board (U)
     * @param iobBasal Basal IOB component (signed, U)
     * @param bgAboveTarget BG minus algorithm target (mg/dL)
     * @param directionNum BG trend as numeric (-2 to +2)
     * @param hour Hour of day (0-23)
     * @param iobActivity Insulin activity (U/5min)
     * @param insulinReq Algorithm's insulin requirement this cycle (U)
     */
    fun predictHypoRisk(
        cgmMgdl: Double,
        iobTotal: Double,
        iobBasal: Double,
        bgAboveTarget: Double,
        directionNum: Double,
        hour: Int,
        iobActivity: Double,
        insulinReq: Double
    ): Double? {
        ensureLoaded()
        if (!loaded || trees == null) return null
        val features = doubleArrayOf(
            cgmMgdl, iobTotal, iobBasal, bgAboveTarget,
            directionNum, hour.toDouble(), iobActivity, insulinReq
        )
        return predict(features)
    }

    /**
     * Generic predict — accepts a feature vector matching the model's declared
     * featureNames order. Used by callers that ship richer feature schemas (v10+).
     * Returns null if the model hasn't loaded or the vector size mismatches.
     */
    fun predict(features: DoubleArray): Double? {
        ensureLoaded()
        val modelTrees = trees ?: return null
        if (!loaded) return null
        val expected = featureNames?.size ?: features.size
        if (features.size != expected) {
            aapsLogger.error(LTag.APS, "BoostRiskModel feature size mismatch: got ${features.size}, expected $expected")
            return null
        }

        // Sum the raw leaf values from all trees
        var rawScore = 0.0
        for (tree in modelTrees) {
            rawScore += walkTree(tree, features)
        }

        // Apply sigmoid to convert raw score to probability
        return 1.0 / (1.0 + Math.exp(-rawScore))
    }

    private fun walkTree(node: TreeNode, features: DoubleArray): Double {
        if (node.isLeaf) return node.leafValue
        return if (features[node.featureIndex] <= node.threshold) {
            walkTree(node.left!!, features)
        } else {
            walkTree(node.right!!, features)
        }
    }

    fun isLoaded(): Boolean = loaded
    fun getFeatureNames(): List<String>? {
        // 2026-06-08: trigger lazy-load on first access so dual-path callers
        // actually load the asset instead of perpetually short-circuiting.
        ensureLoaded()
        return featureNames
    }
    fun getTreeCount(): Int = trees?.size ?: 0
}
