package app.aaps.plugins.aps.openAPSBoost

import android.content.Context
import app.aaps.core.interfaces.logging.AAPSLogger
import app.aaps.core.interfaces.logging.LTag
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Lightweight on-device hypo risk model for Boost.
 *
 * Loads a LightGBM model exported as JSON from the APK's assets and runs inference via
 * pure-Kotlin tree traversal — no native library dependencies.
 *
 * CURRENT model (v12, 2026-06-06): 100 trees, 53 features (17 static + 36 windowed lag0..5
 * lookback), ~368KB. The feature vector is assembled by [BoostMlFeatureBuilder] from cycle
 * state + a persisted 6-cycle ring buffer. The legacy 8-feature entry point
 * [predictHypoRisk] is retained for rollback to pre-v10 models (it no-ops via size-mismatch
 * → null when a 53-feature model is loaded).
 *
 * Trained on a 28-user cohort with Leave-One-User-Out cross-validation; out-of-cohort
 * transfer validated 2026-05-12.
 *
 * Output: P(hypo event in next 4h) as a Double in [0, 1].
 *
 * CONSUMPTION (doc updated 2026-07-02 — the old "Layer A observability-only" text was stale):
 * Layer B is LIVE in the V1 engine (graduated riskScale on the microBolus + tier downgrade at
 * risk > 0.6), the V5/V6 AggressionBudget consumes it as mlHypoRiskScale, and
 * [predictAtProjectedIob] powers V5's Phase-3 postActionRiskCheck (expected ~never to fire
 * with the v12 model — see its KDoc).
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

    fun loadModel(context: Context, assetPath: String = "boost/hypo_risk_model.json"): Boolean {
        return try {
            val rawBytes = context.assets.open(assetPath).readBytes()
            val jsonStr = String(rawBytes, Charsets.UTF_8)
            aapsLogger.info(LTag.APS, "BoostRiskModel loading $assetPath (${rawBytes.size} bytes)")
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
                        // Emit at BOTH error and info — exported log captures only info.
                        aapsLogger.error(LTag.APS, "BoostRiskModel tree $i parse failed: ${e.javaClass.simpleName}: ${e.message}")
                        aapsLogger.info(LTag.APS, "BoostRiskModel DIAG tree $i parse failed: ${e.javaClass.simpleName}: ${e.message}")
                        throw e
                    }
                }
            }

            loaded = true
            aapsLogger.info(LTag.APS, "BoostRiskModel loaded: ${trees?.size} trees, ${featureNames?.size} features from $assetPath")
            true
        } catch (e: Exception) {
            // Emit at BOTH error and info — exported log captures only info.
            aapsLogger.error(LTag.APS, "BoostRiskModel failed to load from $assetPath: ${e.javaClass.simpleName}: ${e.message}")
            aapsLogger.info(LTag.APS, "BoostRiskModel DIAG load FAILED from $assetPath: ${e.javaClass.simpleName}: ${e.message}")
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
        // Cache this cycle's vector so postActionRiskCheck can re-score at projected IOB. (2026-07-02)
        lastFeatures = features.copyOf()
        return score(modelTrees, features)
    }

    // Most recent successfully-scored feature vector (this cycle's, in practice — predict() runs
    // once per cycle before any projected re-score). Basis for [predictAtProjectedIob]. (2026-07-02)
    @Volatile private var lastFeatures: DoubleArray? = null

    /**
     * Re-score the hypo-risk model at the PROJECTED post-SMB state (current IOB + prospective dose),
     * reusing this cycle's cached feature vector with the post-state features adjusted: `iob_iob`
     * AND `iob_iob_lag0` (the schema duplicates current IOB in the lookback block — both must move
     * or the vector is internally inconsistent), `iob_bolusiob` += delta, `recent_smb_units_60m`
     * (+lag0) += delta, `time_since_last_smb_min` := 0. History lags (lag1..5) untouched.
     * Powers V5 Phase-3 `postActionRiskCheck` on the ACTIVE path.
     *
     * HONEST EXPECTATION (backtest 2026-07-02, offline tree re-run over 210 real meal-state dose
     * vectors incl. a forced falling-BG probe up to +3U): the v12 model's learned IOB→risk response
     * is flat-to-INVERTED (high IOB co-occurs with meals in training → fewer hypos in 4h), so
     * projected risk ≤ current and the gate is expected to ~never fire with THIS model. Kept wired
     * because it is zero-risk (lower projection → pass-through, identical to the old null wiring),
     * costs one tree-walk, and becomes live automatically if the model is retrained with a
     * causally-correct IOB response. The doses' actual post-action protection remains
     * iobHeadroomBrake + the maxIOB clamp + the state caps. A DETERMINISTIC post-action check
     * (projected eventualBG = eventualBG − dose×ISF vs target) is the candidate real brake — own
     * design + backtest, not smuggled in here.
     * Returns null (→ gate passes through) when the model/vector/feature names are unavailable.
     */
    fun predictAtProjectedIob(projectedIob: Double): Double? {
        val modelTrees = trees ?: return null
        if (!loaded) return null
        val base = lastFeatures ?: return null
        val names = featureNames ?: return null
        val iobIdx = names.indexOf("iob_iob")
        if (iobIdx < 0 || iobIdx >= base.size) return null
        val f = base.copyOf()
        val delta = projectedIob - f[iobIdx]
        f[iobIdx] = projectedIob
        fun set(name: String, v: (Double) -> Double) {
            val i = names.indexOf(name); if (i in f.indices) f[i] = v(f[i])
        }
        set("iob_iob_lag0") { projectedIob }
        set("iob_bolusiob") { (it + delta).coerceAtLeast(0.0) }
        set("recent_smb_units_60m") { (it + delta).coerceAtLeast(0.0) }
        set("recent_smb_units_60m_lag0") { (it + delta).coerceAtLeast(0.0) }
        set("time_since_last_smb_min") { 0.0 }
        return score(modelTrees, f)
    }

    private fun score(modelTrees: List<TreeNode>, features: DoubleArray): Double {
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
    fun getFeatureNames(): List<String>? {
        // 2026-06-08: trigger lazy-load on first access so callers that probe
        // the schema before the first predict() (e.g., dual-path inference
        // routing in DetermineBasalBoost) actually cause the asset to load.
        // Previously this was a plain getter that returned null forever if no
        // predict() had been called yet — which is exactly what the dual-path
        // code does on every cycle, perpetually short-circuiting load.
        ensureLoaded()
        return featureNames
    }
    fun getTreeCount(): Int = trees?.size ?: 0
}
