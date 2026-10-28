package app.aaps.plugins.aps.openAPSBoostV3ML

import android.content.Context
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Lightweight on-device meal-likelihood model for Boost V3ML / V3MLG3.
 *
 * Sister model to BoostRiskModel — same 8 features, same JSON tree format,
 * different training target: P(BG peak >= current+50 mg/dL within next 90 min).
 *
 * Used for:
 * - V3ML (v4.4): observability only — emit `mlMealLikely` to NS.
 * - V3MLG3 (v4.4): G3 hold release condition — when `mlMealLikely > 0.65`
 *   the pre-UAM hold releases so OREF1 tiers can dose normally.
 *
 * Features (8, identical to BoostRiskModel):
 *   0: cgm_mgdl          — current BG
 *   1: iob_iob            — total insulin on board
 *   2: iob_basaliob        — basal IOB component (signed deviation)
 *   3: bg_above_target     — BG minus algorithm target
 *   4: direction_num       — BG trend as numeric (-2 to +2)
 *   5: hour                — hour of day (0-23)
 *   6: iob_activity         — insulin activity (rate of IOB decay)
 *   7: sug_insulinReq       — algorithm's insulin requirement this cycle
 */
@Singleton
class BoostMealModel @Inject constructor(
    private val context: Context,
    private val aapsLogger: AAPSLogger
) {

    private var trees: List<TreeNode>? = null
    private var featureNames: List<String>? = null
    @Volatile private var loaded = false
    @Volatile private var loadAttempted = false
    private val loadLock = Any()
    private val defaultAssetPath = "boost/meal_likelihood_model.json"

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

    fun loadModel(context: Context, assetPath: String = "boost/meal_likelihood_model.json"): Boolean {
        return try {
            val jsonStr = context.assets.open(assetPath).bufferedReader().readText()
            val json = JSONObject(jsonStr)

            featureNames = mutableListOf<String>().apply {
                val arr = json.getJSONArray("feature_names")
                for (i in 0 until arr.length()) add(arr.getString(i))
            }

            val treesArr = json.getJSONArray("trees")
            trees = mutableListOf<TreeNode>().apply {
                for (i in 0 until treesArr.length()) {
                    add(parseNode(treesArr.getJSONObject(i)))
                }
            }

            loaded = true
            aapsLogger.info(LTag.APS, "BoostMealModel loaded: ${trees?.size} trees, ${featureNames?.size} features from $assetPath")
            true
        } catch (e: Exception) {
            aapsLogger.error(LTag.APS, "BoostMealModel failed to load: ${e.message}")
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
     * Predict P(BG peak >= current+50 mg/dL within next 90 min).
     * Returns a Double in [0, 1], or null if the model isn't loaded.
     */
    fun predictMealLikelihood(
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
        val modelTrees = trees ?: return null
        if (!loaded) return null

        val features = doubleArrayOf(
            cgmMgdl, iobTotal, iobBasal, bgAboveTarget,
            directionNum, hour.toDouble(), iobActivity, insulinReq
        )

        var rawScore = 0.0
        for (tree in modelTrees) {
            rawScore += walkTree(tree, features)
        }

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
    fun getFeatureNames(): List<String>? = featureNames
    fun getTreeCount(): Int = trees?.size ?: 0
}
